"""Tests for SongModel sorting, checked-state tracking and tooltips."""

from PySide6.QtCore import Qt

from i18n import CATEGORY_NAMES
from models import SongModel


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


def test_set_songs_resets_checked(qapp):
    m = make_model()
    check(m, "Bravo")
    m.set_songs(list(SONGS))
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
