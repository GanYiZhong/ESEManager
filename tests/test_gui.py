"""Offscreen smoke tests for the main window."""

import pytest
from PySide6.QtWidgets import QMessageBox

import appconfig
import ese_qt
import workers


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    # Point every data path at an empty temp folder (no databases yet).
    for mod in (appconfig, ese_qt, workers):
        for name, val in (("DB_PATH", tmp_path / "ese_songs.db"),
                          ("LOCAL_DB_PATH", tmp_path / "ese_local.db"),
                          ("CONFIG_FILE", tmp_path / "config.toml"),
                          ("VERSION_FILE", tmp_path / "version.txt")):
            if hasattr(mod, name):
                monkeypatch.setattr(mod, name, str(val))
    monkeypatch.setattr(ese_qt, "APP_DIR", str(tmp_path))
    monkeypatch.setattr(appconfig, "APP_DIR", str(tmp_path))
    # Never block on a dialog in tests; answer "No".
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    w = ese_qt.MainWindow()
    yield w
    w._closing = True
    w.close()


@pytest.mark.parametrize("lang", ["zh_TW", "en", "ja"])
def test_window_builds_in_each_language(window, lang):
    window.lang = lang
    window.build_ui()
    assert window.count_label.text()


def test_empty_database_shows_hint_and_does_not_create_db(window, tmp_path):
    assert not window.empty_hint.isHidden()
    window.load_categories()
    window.do_search()
    assert not (tmp_path / "ese_songs.db").exists()


def test_no_selection_warning_uses_its_own_text(window, monkeypatch):
    seen = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: seen.append(a[2]))
    window.start_download_selected()
    assert seen == [window.tr("no_selection")]


def test_stale_search_results_are_ignored(window):
    window._search_seq = 5
    window.all_songs = ["keep"]
    window.on_search_done(4, [{"song_name": "old"}])
    assert window.all_songs == ["keep"]


def test_close_stops_running_download(window, qapp, monkeypatch):
    class SlowThread(workers.QThread):
        def __init__(self):
            super().__init__()
            self._stop = False

        def stop(self):
            self._stop = True

        def run(self):
            while not self._stop:
                self.msleep(20)

    t = window._track(SlowThread())
    window.dl_thread = t
    t.start()
    # "Quit while busy?" -> Yes
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    window.close()
    assert window._closing
    assert t.wait(3000) and not t.isRunning()
