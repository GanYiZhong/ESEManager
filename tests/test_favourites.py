"""Favourites: storage, filter, window integration, CLI flags."""

import json
import os

import core
from models import SongModel
from test_cli import app, make_db              # noqa: F401  (fixture re-export)
from test_gui import window                    # noqa: F401  (fixture re-export)

SONGS = [
    {"song_name": "Alpha", "category": "01 Pop", "files": [{"file_path": "a", "filename": "a"}]},
    {"song_name": "Beta", "category": "02 Anime", "files": [{"file_path": "b", "filename": "b"}]},
]


def test_storage_roundtrip_and_damage(tmp_path):
    p = str(tmp_path / "favourites.json")
    assert core.load_favourites(p) == set()
    core.save_favourites({("Beta", "02 Anime"), ("Alpha", "01 Pop")}, p)
    assert json.load(open(p, encoding="utf-8"))["songs"] == ["01 Pop/Alpha", "02 Anime/Beta"]
    assert core.load_favourites(p) == {("Alpha", "01 Pop"), ("Beta", "02 Anime")}
    assert not os.path.exists(p + ".part")
    open(p, "w").write("{not json")
    assert core.load_favourites(p) == set()


def test_update_keeps_favourites_file():
    assert "favourites.json" in core.UPDATE_KEEP_FILES


def test_filter_favourites():
    assert core.filter_favourites(SONGS, {("Beta", "02 Anime")}) == [SONGS[1]]
    assert core.filter_favourites(SONGS, {("Beta", "01 Pop")}) == []


def test_window_toggle_filter_select_and_persist(window, tmp_path, monkeypatch):
    monkeypatch.setattr(core, "FAVOURITES_FILE", str(tmp_path / "favourites.json"))
    window.all_songs = SONGS
    window.apply_filters()
    window.toggle_favourite(SONGS[1])
    assert core.load_favourites() == {("Beta", "02 Anime")}
    window.fav_only.setChecked(True)
    assert window.song_model.rowCount() == 1 and window.active_filter_count() == 1
    window.act_sel_fav.trigger()
    assert window.song_model.checked == {("Beta", "02 Anime")}
    window.toggle_favourite(SONGS[1])               # unstar while filtered: leaves list
    assert window.song_model.rowCount() == 0
    window.reset_filters()
    assert not window.fav_only.isChecked() and window.song_model.rowCount() == 2


def test_cell_click_and_double_click_on_star(window, tmp_path, monkeypatch):
    monkeypatch.setattr(core, "FAVOURITES_FILE", str(tmp_path / "favourites.json"))
    window.all_songs = SONGS
    window.apply_filters()
    idx = window.song_model.index(0, SongModel.FAV_COL)
    window.on_cell_clicked(idx)
    assert window.song_model.is_favourite(window.song_model._view[0])
    window.on_row_double_clicked(idx)               # must not check the row
    assert not window.song_model.checked
    window.on_cell_clicked(window.song_model.index(0, 1))   # other column: no toggle
    assert len(window.song_model.favourites) == 1


def test_context_menu_and_detail_button(window, tmp_path, monkeypatch):
    monkeypatch.setattr(core, "FAVOURITES_FILE", str(tmp_path / "favourites.json"))
    window.all_songs = SONGS
    window.apply_filters()
    song = window.song_model._view[0]
    texts = [a_.text() for a_ in window.build_row_menu(song).actions()]
    assert window.tr("fav_add") in texts
    window.act_ctx_fav.trigger()
    texts = [a_.text() for a_ in window.build_row_menu(song).actions()]
    assert window.tr("fav_remove") in texts and window.tr("fav_add") not in texts
    window.table.setCurrentIndex(window.song_model.index(0, 1))
    window.set_detail_open(True)
    assert window.detail_panel.fav_btn.text() == window.tr("fav_remove")
    window.detail_panel.fav_btn.click()
    assert not window.song_model.favourites
    assert window.detail_panel.fav_btn.text() == window.tr("fav_add")


def test_cli_favourites_flags(app):
    tmp, run = app
    make_db(tmp / "ese_songs.db")
    rc, out = run("search", "--favourites")
    assert rc == 2
    core.save_favourites({("Song", "01 Pop")}, str(tmp / "favourites.json"))
    rc, out = run("search", "--favourites")
    assert rc == 0 and "Song" in out
    rc, out = run("download", "--favourites", "-y", "--dir", str(tmp / "dl"))
    assert "1 songs" in out
