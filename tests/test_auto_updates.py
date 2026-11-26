"""Automatic check of downloaded songs: fast path, daily full check, UI marks."""

import json
import time

import cli
import core
from test_update_cache import make_lib, patch


def setup(tmp_path, monkeypatch, changed):
    songs, shas = make_lib(tmp_path)          # only S0 is outdated
    for i, s in enumerate(songs):
        s["song_name"], s["category"] = f"S{i}", "01 Pop"
    patch(monkeypatch, songs, shas)
    ns = tmp_path / "new_songs.json"
    ns.write_text(json.dumps({"changed": [["01 Pop", n] for n in changed], "added": []}))
    monkeypatch.setattr(core, "NEW_SONGS_FILE", str(ns))


def test_fast_path_only_checks_changed_songs(tmp_path, monkeypatch):
    now = time.time()
    setup(tmp_path, monkeypatch, ["S0"])
    songs, full = core.auto_check_updates(str(tmp_path), last_full=now, now=now)
    assert not full and [s["id"] for s in songs] == [0]
    setup(tmp_path, monkeypatch, ["S3"])      # S0 is outdated but not listed
    assert core.auto_check_updates(str(tmp_path), last_full=now, now=now) == ([], False)
    setup(tmp_path, monkeypatch, [])
    assert core.auto_check_updates(str(tmp_path), last_full=now, now=now) == ([], False)


def test_full_check_when_due(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, [])
    now = time.time()
    songs, full = core.auto_check_updates(str(tmp_path), last_full=now - 90000, now=now)
    assert full and [s["id"] for s in songs] == [0]
    assert core.auto_check_updates(str(tmp_path), last_full=0, now=now)[1] is True


def test_cli_changed_only_flag(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, ["S0"])
    args = cli.build_parser().parse_args(["updates", "--changed-only"])
    assert args.changed_only is True
    assert core.changed_song_keys() == {("S0", "01 Pop")}
    assert [s["id"] for s in core.find_updates(
        str(tmp_path), only=core.changed_song_keys())] == [0]
    assert core.find_updates(str(tmp_path), only={("S1", "01 Pop")}) == []


def test_model_marks_update(qapp):
    from PySide6.QtCore import Qt
    from models import SongModel
    m = SongModel(lambda k, **kw: k, {})
    m.set_songs([{"song_name": "A", "category": "C", "files": []}])
    m.set_download_status({("A", "C"): core.DL_COMPLETE})
    idx = m.index(0, m.DL_COL)
    m.set_update_keys({("A", "C")})
    assert m.data(idx, Qt.DisplayRole) == "⟳"
    assert m.data(idx, Qt.ToolTipRole) == "dl_update_avail"
    m.set_update_keys(())
    assert m.data(idx, Qt.DisplayRole) == "●"


def test_window_notice_never_downloads_by_itself(qapp, tmp_path, monkeypatch):
    import test_gui
    from PySide6.QtWidgets import QMessageBox
    import appconfig
    import ese_qt
    import workers
    for mod in (appconfig, ese_qt, workers, core):
        for name, val in (("DB_PATH", "ese_songs.db"), ("LOCAL_DB_PATH", "ese_local.db"),
                          ("CONFIG_FILE", "config.toml"), ("VERSION_FILE", "version.txt"),
                          ("NEW_SONGS_FILE", "new_songs.json")):
            if hasattr(mod, name):
                monkeypatch.setattr(mod, name, str(tmp_path / val))
    monkeypatch.setattr(ese_qt, "APP_DIR", str(tmp_path))
    monkeypatch.setattr(appconfig, "APP_DIR", str(tmp_path))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)
    w = ese_qt.MainWindow()
    try:
        started = []
        monkeypatch.setattr(w, "start_download", lambda *a, **k: started.append((a, k)))
        song = {"song_name": "A", "category": "C", "files": [{"file_path": "x"}]}
        w.on_auto_updates([song], True)
        assert not w.auto_upd_btn.isHidden() and "1" in w.auto_upd_btn.text()
        assert started == [] and w._last_full_check > 0
        w.apply_auto_updates()
        assert len(started) == 1 and started[0][1] == {"overwrite": True}
        assert w.auto_upd_btn.isHidden()
    finally:
        test_gui.__dict__  # keep import used
        from conftest import dispose_window
        dispose_window(w)
