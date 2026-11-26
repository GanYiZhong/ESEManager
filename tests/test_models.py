"""Tests for SongModel sorting, checked-state tracking and tooltips."""

from PySide6.QtCore import Qt, QPersistentModelIndex

from i18n import CATEGORY_NAMES
from models import SongModel, DownloadModel, natural_key


def tr(key, **kw):
    return key          # keep translation keys visible in assertions


SONGS = [
    {"song_name": "Bravo", "category": "POPS",
     "files": [{"file_path": "b1"}, {"file_path": "b2"}]},
    {"song_name": "alpha", "category": "ANIME", "files": [{"file_path": "a1"}]},
    {"song_name": "Charlie", "category": "POPS", "files": []},      # no metadata
]
JP = {"Bravo": "ブラボー", "alpha": "アルファ"}          # Charlie has no JP title
META = {
    "Bravo": {"bpm": "180", "level_easy": 3, "level_normal": 5,
              "level_hard": None, "level_oni": 10, "level_ura": None},
    "alpha": {"bpm": "95.5 - 100", "level_easy": 1, "level_normal": None,
              "level_hard": 7, "level_oni": None, "level_ura": None},
}


def make_model(songs=SONGS):
    m = SongModel(tr, dict(JP), dict(META))
    m.set_songs(list(songs))
    return m


def names(m):
    return [m.data(m.index(r, 1)) for r in range(m.rowCount())]


def row_of(m, name):
    return names(m).index(name)


def check(m, name):
    m.setData(m.index(row_of(m, name), 0), Qt.Checked, Qt.CheckStateRole)


# ---------------------------------------------------------------- sorting
def test_sort_song_name_case_insensitive(qapp):
    m = make_model()
    m.sort(1, Qt.AscendingOrder)
    assert names(m) == ["alpha", "Bravo", "Charlie"]
    m.sort(1, Qt.DescendingOrder)
    assert names(m) == ["Charlie", "Bravo", "alpha"]


def test_sort_japanese_title_as_text(qapp):
    m = make_model()
    m.sort(2, Qt.AscendingOrder)
    # Charlie has no JP title, so it goes last in both directions
    assert names(m) == ["alpha", "Bravo", "Charlie"]
    m.sort(2, Qt.DescendingOrder)
    assert names(m)[-1] == "Charlie"


def test_sort_category_as_text(qapp):
    m = make_model()
    m.sort(3, Qt.AscendingOrder)
    assert m.data(m.index(0, 3)) == CATEGORY_NAMES.get("ANIME", "ANIME")
    assert names(m)[0] == "alpha"


def test_sort_bpm_numeric_missing_last(qapp):
    m = make_model()
    m.sort(4, Qt.AscendingOrder)
    # 95.5 < 180 numerically (lexically "180" < "95.5"); Charlie has no BPM
    assert names(m) == ["alpha", "Bravo", "Charlie"]
    m.sort(4, Qt.DescendingOrder)
    assert names(m) == ["Bravo", "alpha", "Charlie"]


def test_sort_level_numeric_missing_last(qapp):
    m = make_model()
    m.sort(5, Qt.AscendingOrder)          # level_easy: alpha=1, Bravo=3, Charlie=missing
    assert names(m) == ["alpha", "Bravo", "Charlie"]
    m.sort(5, Qt.DescendingOrder)
    assert names(m) == ["Bravo", "alpha", "Charlie"]
    m.sort(7, Qt.AscendingOrder)          # level_hard: only alpha has a value
    assert names(m) == ["alpha", "Bravo", "Charlie"]


def test_sort_file_count_numeric(qapp):
    m = make_model()
    m.sort(10, Qt.AscendingOrder)         # Charlie=0, alpha=1, Bravo=2
    assert names(m) == ["Charlie", "alpha", "Bravo"]


def test_sort_checkbox_checked_first(qapp):
    m = make_model()
    check(m, "Charlie")
    m.sort(0, Qt.AscendingOrder)
    assert names(m)[0] == "Charlie"
    m.sort(0, Qt.DescendingOrder)
    assert names(m)[-1] == "Charlie"


def test_restore_original_order(qapp):
    m = make_model()
    m.sort(1, Qt.DescendingOrder)
    m.sort(-1, Qt.AscendingOrder)         # what the view does for "no sort"
    assert names(m) == ["Bravo", "alpha", "Charlie"]


def test_sort_survives_set_songs(qapp):
    m = make_model()
    m.sort(1, Qt.AscendingOrder)
    m.set_songs(list(SONGS))
    assert names(m) == ["alpha", "Bravo", "Charlie"]


# ---------------------------------------------------------- checked state
def test_checked_follows_song_after_sort(qapp):
    m = make_model()
    check(m, "Bravo")
    assert row_of(m, "Bravo") == 0
    m.sort(1, Qt.AscendingOrder)           # Bravo moves to row 1
    r = row_of(m, "Bravo")
    assert r == 1
    assert m.is_checked(r)
    assert m.data(m.index(r, 0), Qt.CheckStateRole) == Qt.Checked
    assert m.data(m.index(row_of(m, "alpha"), 0), Qt.CheckStateRole) == Qt.Unchecked
    assert m.data(m.index(row_of(m, "Charlie"), 0), Qt.CheckStateRole) == Qt.Unchecked
    assert len(m.checked) == 1


def test_selected_songs_in_display_order(qapp):
    m = make_model()
    m.set_all(True)
    assert len(m.checked) == 3
    m.sort(1, Qt.DescendingOrder)
    assert [s["song_name"] for s in m.selected_songs()] == ["Charlie", "Bravo", "alpha"]


def test_selected_songs_excludes_unchecked(qapp):
    m = make_model()
    check(m, "alpha")
    m.sort(4, Qt.DescendingOrder)
    assert [s["song_name"] for s in m.selected_songs()] == ["alpha"]


def test_set_all_false_clears(qapp):
    m = make_model()
    m.set_all(True)
    m.set_all(False)
    assert m.checked == set()
    assert m.selected_songs() == []


def test_set_songs_keeps_checked_for_remaining_songs(qapp):
    m = make_model()
    check(m, "Bravo")
    check(m, "alpha")
    m.set_songs([SONGS[0], SONGS[2]])            # alpha dropped, Bravo stays
    assert m.checked == {("Bravo", "POPS")}
    m.set_songs([])
    assert m.checked == set()


# ---------------------------------------------------------------- tooltips
def test_name_and_jp_tooltips_show_both_titles_and_category(qapp):
    m = make_model()
    m.sort(1, Qt.AscendingOrder)
    r = row_of(m, "Bravo")
    cat = CATEGORY_NAMES.get("POPS", "POPS")
    for col in (1, 2):
        tip = m.data(m.index(r, col), Qt.ToolTipRole)
        assert "Bravo" in tip
        assert "ブラボー" in tip
        assert cat in tip


def test_tooltip_omits_empty_jp_title(qapp):
    m = make_model()
    r = row_of(m, "Charlie")
    tip = m.data(m.index(r, 1), Qt.ToolTipRole)
    assert tip.split("\n")[0] == "Charlie"
    assert len(tip.split("\n")) == 2       # title + category only


def test_level_tooltip_shows_difficulty_and_level(qapp):
    m = make_model()
    r = row_of(m, "Bravo")
    assert m.data(m.index(r, 5), Qt.ToolTipRole) == "c_easy: 3"
    assert m.data(m.index(r, 8), Qt.ToolTipRole) == "c_oni: 10"
    assert m.data(m.index(r, 9), Qt.ToolTipRole) == "c_ura: −"


def test_level_tooltip_missing_value(qapp):
    m = make_model()
    r = row_of(m, "Charlie")
    assert m.data(m.index(r, 5), Qt.ToolTipRole) == "c_easy: −"


# ------------------------------------------------------- natural sorting
def test_natural_key_numbers_and_kana():
    assert natural_key("Song 2") < natural_key("Song 10")
    assert natural_key("ｱ") == natural_key("あ") == natural_key("ア")   # width + kana
    assert natural_key("１０") > natural_key("９")                     # fullwidth digits
    natural_key("")
    natural_key(None)                                                  # never raises


def test_sort_names_numerically(qapp):
    songs = [{"song_name": n, "category": "POPS", "files": []}
             for n in ("Song 10", "song 2", "Song 1")]
    m = make_model(songs)
    m.sort(1, Qt.AscendingOrder)
    assert names(m) == ["Song 1", "song 2", "Song 10"]


def test_sort_is_stable_for_ties(qapp):
    songs = [{"song_name": f"S{i}", "category": "POPS", "files": []} for i in range(5)]
    m = make_model(songs)
    m.sort(10, Qt.AscendingOrder)      # all equal file counts
    assert names(m) == ["S0", "S1", "S2", "S3", "S4"]
    m.sort(10, Qt.DescendingOrder)
    assert names(m) == ["S0", "S1", "S2", "S3", "S4"]


def test_sort_keeps_persistent_index(qapp):
    m = make_model()
    pi = QPersistentModelIndex(m.index(0, 1))      # Bravo
    m.sort(1, Qt.AscendingOrder)
    assert pi.row() == 1 and m.data(m.index(pi.row(), 1)) == "Bravo"


def test_meta_replacement_refreshes_cells_and_sort(qapp):
    m = make_model()
    m.sort(5, Qt.AscendingOrder)
    m.meta_map = {"Charlie": {"level_easy": 0}}
    m.sort(5, Qt.AscendingOrder)
    assert names(m)[0] == "Charlie"
    assert m.data(m.index(0, 5)) == "0"


# ------------------------------------------------------ selection signals
def test_set_all_emits_single_range(qapp):
    m = make_model()
    got = []
    m.dataChanged.connect(lambda tl, br, roles: got.append((tl.row(), br.row(), tl.column(), br.column())))
    m.set_all(True)
    assert got == [(0, 2, 0, 0)]
    m.set_all(True)                     # no change -> no signal
    assert len(got) == 1


# ------------------------------------------------------- download model
def make_dl(n=10):
    d = DownloadModel(tr)
    d.load([({"song_name": "S"}, {"file_path": f"p{i}", "filename": f"f{i}"}) for i in range(n)])
    return d


def test_update_many_batches_adjacent_rows(qapp):
    d = make_dl()
    got = []
    d.dataChanged.connect(lambda tl, br, roles: got.append((tl.row(), br.row(), tl.column(), br.column())))
    d.update_many({"p5": ("downloading", 10, 1), "p1": ("done", 100, 0),
                   "p2": ("done", 100, 0), "p3": ("failed", 0, 0), "nope": ("x", 0, 0)})
    assert got == [(1, 3, 2, 4), (5, 5, 2, 4)]     # never touches file/song columns
    assert d.data(d.index(5, 3)) == "10%"
    assert d.data(d.index(1, 2)) == "st_done"
    got.clear()
    d.update_many({"zzz": ("x", 0, 0)})
    assert got == []


# ------------------------------------------------------- downloaded column
def test_download_column_display_and_sort(qapp):
    m = make_model()
    col = SongModel.DL_COL
    assert m.data(m.index(0, col)) == ""          # not scanned yet
    m.set_download_status({("alpha", "ANIME"): 2, ("Bravo", "POPS"): 0, ("Charlie", "POPS"): 1})
    shown = {n: m.data(m.index(row_of(m, n), col)) for n in names(m)}
    assert len(set(shown.values())) == 3
    m.sort(col, Qt.DescendingOrder)
    assert names(m)[0] == "alpha" and names(m)[-1] == "Bravo"
    # a fresh scan result re-sorts an already sorted column
    m.set_download_status({("alpha", "ANIME"): 0, ("Bravo", "POPS"): 2, ("Charlie", "POPS"): 1})
    assert names(m) == ["Bravo", "Charlie", "alpha"]


# ---------------------------------------------------------------- favourites
def test_favourite_column_toggle_and_sort():
    m = make_model()
    col = SongModel.FAV_COL
    assert SongModel.COLS[col] == "c_fav" and col == len(SongModel.COLS) - 1
    assert m.data(m.index(0, col)) == "☆"
    assert m.toggle_favourite(SONGS[1]) is True
    assert m.data(m.index(row_of(m, "alpha"), col)) == "★"
    m.sort(col, Qt.AscendingOrder)
    assert names(m)[0] == "alpha"                    # starred first
    assert m.toggle_favourite(SONGS[1]) is False
    assert not m.favourites


def test_check_favourites_and_key_includes_category():
    m = make_model()
    m.set_favourites({("alpha", "ANIME"), ("Bravo", "OTHER")})   # wrong category: ignored
    assert m.check_favourites()
    assert m.checked == {("alpha", "ANIME")}
