"""Offscreen smoke tests for the main window."""

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

import appconfig
import ese_qt
import core
import workers


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    # Point every data path at an empty temp folder (no databases yet).
    for mod in (appconfig, ese_qt, workers, core):
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


def test_check_result_banner_and_show_all(window):
    songs = [{"song_name": "A", "category": "01 Pop", "files": [{"filename": "A.tja",
              "file_path": "01 Pop/A/A.tja", "download_url": ""}]}]
    window._show_view("view_missing", songs)
    assert not window.view_bar.isHidden()
    assert "1" in window.view_label.text()
    assert window.song_model.rowCount() == 1 and len(window.song_model.checked) == 1
    window.show_all()                  # no database: the search returns at once
    assert window.view_bar.isHidden()


def test_language_change_asks_before_restart(window, monkeypatch):
    restarted = []
    monkeypatch.setattr(window, "_restart", lambda: restarted.append(1))
    asked = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: asked.append(a[2]) or QMessageBox.No)
    window.lang_combo.setCurrentIndex(window.lang_combo.findData("ja"))
    assert asked and not restarted
    assert window.lang_pref == "ja"    # saved for the next launch


def test_window_fits_small_screen(window):
    area = QApplication.primaryScreen().availableGeometry()
    w, h = window._fit_to_screen(5000, 5000)
    assert w <= max(640, area.width()) and h <= max(480, area.height())


def test_busy_bar_is_balanced(window):
    window._set_busy(True)
    assert window.overall_bar.maximum() == 0          # indeterminate
    window._set_busy(False)
    assert window.overall_bar.maximum() == 1
    window._set_busy(False)                           # never below zero
    assert window._busy == 0


def test_damaged_database_warns_once(window, monkeypatch):
    seen = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: seen.append(a[2]))
    window._search_seq = 3
    window.on_search_fail(3, "database disk image is malformed")
    window.on_search_fail(3, "database disk image is malformed")
    assert len(seen) == 1 and "malformed" in seen[0]


def test_update_button_from_source_opens_release_page(window, monkeypatch):
    opened = []
    monkeypatch.setattr(ese_qt.webbrowser, "open", opened.append)
    window.on_app_update("v2099.1.1", "https://github.com/x/y/releases/tag/v2099.1.1")
    assert not window.app_update_btn.isHidden()
    window.app_update_btn.click()
    assert opened == ["https://github.com/x/y/releases/tag/v2099.1.1"]
