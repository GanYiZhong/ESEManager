"""Column visibility / order / widths persistence and density (offscreen)."""
import tomllib

import pytest
from PySide6.QtWidgets import QMessageBox

import appconfig
import columns
import core
import ese_qt
import workers
from models import SongModel


def _make(qapp, tmp_path, monkeypatch):
    for mod in (appconfig, ese_qt, workers, core):
        for name, val in (("DB_PATH", tmp_path / "ese_songs.db"),
                          ("LOCAL_DB_PATH", tmp_path / "ese_local.db"),
                          ("CONFIG_FILE", tmp_path / "config.toml"),
                          ("VERSION_FILE", tmp_path / "version.txt"),
                          ("NEW_SONGS_FILE", tmp_path / "new_songs.json")):
            if hasattr(mod, name):
                monkeypatch.setattr(mod, name, str(val))
    monkeypatch.setattr(ese_qt, "APP_DIR", str(tmp_path))
    monkeypatch.setattr(appconfig, "APP_DIR", str(tmp_path))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    return ese_qt.MainWindow()


@pytest.fixture
def make_window(qapp, tmp_path, monkeypatch):
    made = []

    def make(config_text=None):
        if config_text is not None:
            (tmp_path / "config.toml").write_text(config_text, encoding="utf-8")
        w = _make(qapp, tmp_path, monkeypatch)
        made.append(w)
        return w

    yield make
    for w in made:
        w._closing = True
        w.close()


@pytest.fixture
def window(make_window):
    return make_window()


def _saved(tmp_path):
    with open(tmp_path / "config.toml", "rb") as f:
        return tomllib.load(f)["display"]


def _hidden(w):
    h = w.table.horizontalHeader()
    return {k for c, k in enumerate(SongModel.COLS) if h.isSectionHidden(c)}


def _pick(monkeypatch, label_key):
    """Replace the modal popup to choose the action whose text/data matches."""
    def fake_exec(self, *a, **k):
        for act in self.actions():
            if act.data() == label_key or act.text() == label_key:
                act.setChecked(not act.isChecked())   # what a click does
                return act
        return None
    monkeypatch.setattr(columns.ColumnManager, "_popup", staticmethod(lambda m, p: fake_exec(m)))


def test_header_menu_lists_every_column_and_name_is_locked(window, monkeypatch):
    seen = {}

    def fake_exec(self, *a, **k):
        seen["acts"] = [(x.data(), x.isCheckable(), x.isChecked(), x.isEnabled())
                        for x in self.actions() if not x.isSeparator()]
        return None
    monkeypatch.setattr(columns.ColumnManager, "_popup", staticmethod(lambda m, p: fake_exec(m)))
    window.colmgr.show_menu()
    cols = [a for a in seen["acts"] if a[0] is not None]
    assert [a[0] for a in cols] == SongModel.COLS
    assert all(a[1] and a[2] for a in cols)
    assert [a[3] for a in cols if a[0] == "c_song"] == [False]
    assert len(seen["acts"]) == len(SongModel.COLS) + 1   # + reset


def test_toggle_hide_and_persist_roundtrip(make_window, tmp_path, monkeypatch):
    w = make_window()
    _pick(monkeypatch, "c_bpm")
    w.colmgr.show_menu()
    assert _hidden(w) == {"c_bpm"}
    assert _saved(tmp_path)["columns_hidden"] == ["c_bpm"]
    _pick(monkeypatch, "c_song")             # name can never be hidden
    w.colmgr.show_menu()
    assert "c_song" not in _hidden(w)
    h = w.table.horizontalHeader()
    h.moveSection(h.visualIndex(SongModel.COLS.index("c_cat")), 1)
    h.resizeSection(SongModel.COLS.index("c_oni"), 77)
    w.save_config()
    w._closing = True
    w.close()
    w2 = make_window()
    assert _hidden(w2) == {"c_bpm"}
    h2 = w2.table.horizontalHeader()
    assert h2.logicalIndex(1) == SongModel.COLS.index("c_cat")
    assert h2.sectionSize(SongModel.COLS.index("c_oni")) == 77


def test_reset_columns(make_window, tmp_path, monkeypatch):
    w = make_window()
    _pick(monkeypatch, "c_bpm")
    w.colmgr.show_menu()
    h = w.table.horizontalHeader()
    h.moveSection(h.visualIndex(3), 1)
    w.colmgr.user_widths["c_oni"] = 90
    _pick(monkeypatch, w.tr("col_reset"))
    w.colmgr.show_menu()
    assert _hidden(w) == set()
    assert [h.logicalIndex(v) for v in range(h.count())] == list(range(h.count()))
    assert w.colmgr.user_widths == {}
    d = _saved(tmp_path)
    assert d["columns_hidden"] == [] and d["columns_widths"] == {}


def test_unknown_and_malformed_keys_are_ignored(make_window):
    w = make_window(
        '[display]\n'
        'columns_hidden = ["c_bpm", "c_from_the_future", 5, "c_song"]\n'
        'columns_order = ["c_fav", "c_bogus", "c_fav", "c_song"]\n'
        '[display.columns_widths]\n'
        'c_bpm = 120\nc_bogus = 50\nc_oni = "wide"\nc_hard = -4\nc_song = 400\n')
    assert _hidden(w) == {"c_bpm"}
    h = w.table.horizontalHeader()
    order = [SongModel.COLS[h.logicalIndex(v)] for v in range(h.count())]
    assert order[:2] == ["c_fav", "c_song"]
    assert sorted(order) == sorted(SongModel.COLS)        # none lost or duplicated
    assert w.colmgr.user_widths == {"c_bpm": 120}


def test_missing_and_wrong_type_config_values(make_window):
    w = make_window('[display]\ncolumns_hidden = "c_bpm"\ncolumns_order = 3\n'
                    'columns_widths = [1, 2]\ndensity = "huge"\n')
    assert _hidden(w) == set()
    assert w.density == "comfortable"


def test_new_columns_are_appended_when_order_is_old(make_window):
    w = make_window('[display]\ncolumns_order = ["c_song", "c_jp"]\n')
    h = w.table.horizontalHeader()
    order = [SongModel.COLS[h.logicalIndex(v)] for v in range(h.count())]
    assert order[:2] == ["c_song", "c_jp"]
    assert len(order) == len(SongModel.COLS)


def test_default_resize_modes():
    from PySide6.QtWidgets import QHeaderView as H
    # pure policy: names stretch, icon columns fixed, the rest interactive
    assert columns.STRETCH == {"c_song", "c_jp"}
    assert columns.FIXED <= set(SongModel.COLS)
    assert H.Stretch != H.Fixed


def test_header_modes_and_fit_once(window):
    h = window.table.horizontalHeader()
    from PySide6.QtWidgets import QHeaderView as H
    modes = {k: h.sectionResizeMode(c) for c, k in enumerate(SongModel.COLS)}
    assert modes["c_song"] == modes["c_jp"] == H.Stretch
    assert all(modes[k] == H.Fixed for k in columns.FIXED)
    assert modes["c_bpm"] == H.Interactive
    assert h.sectionsMovable()
    assert not window.colmgr._fitted
    calls = []
    orig = window.colmgr.apply_widths
    window.colmgr.apply_widths = lambda: (calls.append(1), orig())[1]
    window.colmgr.fit_once()          # no rows yet -> nothing measured
    assert not calls
    window.song_model.beginResetModel()
    window.song_model.endResetModel()  # still empty
    assert not calls


def test_density_changes_row_height_padding_and_persists(make_window, tmp_path):
    w = make_window()
    vh = w.table.verticalHeader()
    comfy = vh.defaultSectionSize()
    assert "padding:0 6px" in w.table.styleSheet()
    w.density_combo.setCurrentIndex(w.density_combo.findData("compact"))
    assert w.density == "compact"
    assert vh.defaultSectionSize() < comfy
    assert "padding:0 3px" in w.table.styleSheet()
    assert _saved(tmp_path)["density"] == "compact"
    w._closing = True
    w.close()
    w2 = make_window()
    assert w2.density == "compact"
    assert w2.density_combo.currentData() == "compact"
    assert w2.table.verticalHeader().defaultSectionSize() == vh.defaultSectionSize()


def test_i18n_keys_exist_in_all_languages():
    from i18n import TR
    for lang in ("zh_TW", "en", "ja"):
        for k in ("col_reset", "density_label", "density_tip",
                  "density_comfortable", "density_compact"):
            assert TR[lang].get(k), (lang, k)
