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
    assert window.welcome_title.text() == ese_qt.TR[lang]["welcome_title"]


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
    # "Stop and quit / keep in background?" -> stop and quit
    monkeypatch.setattr(window, "_ask_close_during_download", lambda can_bg: "quit")
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


def test_download_source_setting_is_saved(window, tmp_path):
    import tomllib
    window.source_combo.setCurrentIndex(window.source_combo.findData("taiko.ac"))
    assert core._download_source == "taiko.ac"
    with open(tmp_path / "config.toml", "rb") as f:
        assert tomllib.load(f)["download"]["source"] == "taiko.ac"


SONGS = [{"song_name": n, "category": "01 Pop", "files": [
    {"filename": n + ".tja", "file_path": f"01 Pop/{n}/{n}.tja", "download_url": ""}]}
    for n in ("Alpha", "Beta")]


def test_space_toggles_current_row(window):
    window.song_model.set_songs(SONGS)
    window.table.setCurrentIndex(window.song_model.index(1, 1))
    window.toggle_current_rows()
    assert window.song_model.is_checked(1) and not window.song_model.is_checked(0)
    window.toggle_current_rows()
    assert not window.song_model.is_checked(1)


def test_double_click_opens_folder_if_downloaded_else_toggles(window, tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr(window, "_open_path", opened.append)
    window.dir_edit.setText(str(tmp_path))
    window.song_model.set_songs(SONGS)
    window.on_row_double_clicked(window.song_model.index(0, 1))
    assert not opened and window.song_model.is_checked(0)
    (tmp_path / "01 Pop" / "Beta").mkdir(parents=True)
    window.on_row_double_clicked(window.song_model.index(1, 1))
    assert len(opened) == 1 and opened[0].endswith("Beta")
    assert not window.song_model.is_checked(1)


def test_empty_state_message(window, monkeypatch):
    monkeypatch.setattr(window, "has_song_db", lambda: True)
    window.search_edit.setText("zzz")
    window.all_songs = []
    window.apply_filters()
    assert not window.empty_label.isHidden()
    assert window.empty_label.text() == window.tr("no_results")
    window.all_songs = SONGS
    window.apply_filters()
    assert window.empty_label.isHidden()


def test_last_category_is_remembered(window, tmp_path, monkeypatch):
    import tomllib
    monkeypatch.setattr(core, "list_categories", lambda: ["01 Pop", "02 Anime"])
    window.load_categories()
    window.cat_combo.setCurrentIndex(window.cat_combo.findData("02 Anime"))
    with open(tmp_path / "config.toml", "rb") as f:
        assert tomllib.load(f)["display"]["category"] == "02 Anime"
    window.load_categories()          # reload restores the saved choice
    assert window.cat_combo.currentData() == "02 Anime"


@pytest.mark.parametrize("lang", ["zh_TW", "en", "ja"])
def test_new_strings_exist(lang):
    from i18n import TR
    for k in ("ctx_toggle", "ctx_download", "ctx_open_folder", "ctx_copy_title",
              "no_results", "no_songs"):
        assert TR[lang][k]


def test_progress_shows_in_window_title_and_resets(window, monkeypatch):
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)   # never block on the summary
    class T:
        stopped = False
        failed = []
        def isRunning(self): return False
        def snapshot(self): return (3, 6, 0, 0, [])
        def is_paused(self): return False
    window.dl_thread = T()
    window.refresh_progress()
    assert window.windowTitle().startswith("50%")
    window.on_download_done(6, 0, 0, 6)
    assert not window.windowTitle().startswith("50%")
    assert window.download_btn.isEnabled()
    assert not window.pause_btn.isEnabled() and not window.stop_btn.isEnabled()


def test_summary_dialog_has_open_and_retry_buttons(window, monkeypatch, tmp_path):
    seen = {}
    def fake_exec(self):
        seen["texts"] = [b.text() for b in self.buttons()]
        seen["retry"] = [b for b in self.buttons() if b.text() == window.tr("dl_retry_failed")]
        self._chosen = seen["retry"][0] if seen["retry"] else None
    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: getattr(self, "_chosen", None))
    called = []

    class T:
        def isRunning(self): return False
        def wait(self, ms): called.append("wait")
    window.dl_thread = T()
    monkeypatch.setattr(window, "retry_failed", lambda: called.append("retry"))
    window._show_summary("x", 2)
    assert window.tr("dl_open_folder") in seen["texts"] and window.tr("dl_retry_failed") in seen["texts"]
    assert called == ["wait", "retry"]
    window._show_summary("x", 0)
    assert window.tr("dl_retry_failed") not in seen["texts"]


def test_pause_ignored_once_stopping(window):
    class T:
        stopped = True
        running = True
        def isRunning(self): return self.running
        def is_paused(self): raise AssertionError("must not toggle")
    window.dl_thread = T()
    window.toggle_pause()
    window.dl_thread.running = False


@pytest.mark.parametrize("lang", ["zh_TW", "en", "ja"])
def test_download_summary_strings_exist(lang):
    from i18n import TR
    assert TR[lang]["dl_open_folder"] and TR[lang]["dl_retry_failed"]


def test_first_run_welcome_panel(window):
    assert not window.welcome_panel.isHidden()
    assert window.welcome_btn.isEnabled()
    assert window.count_label.text() == ""
    assert not window.missing_btn.isEnabled()
    assert window.download_dir in window.welcome_dir.text() or \
        window.dir_edit.text() in window.welcome_dir.text()


def test_welcome_button_runs_db_update(window, monkeypatch):
    calls = []
    monkeypatch.setattr(window, "update_database", lambda: calls.append(1))
    window.welcome_btn.click()
    assert calls == [1]


def test_welcome_change_dir_updates_label(window, monkeypatch, tmp_path):
    new = str(tmp_path / "songs_here")
    monkeypatch.setattr(ese_qt.QFileDialog, "getExistingDirectory",
                        staticmethod(lambda *a, **k: new))
    window.browse_dir()
    assert new in window.welcome_dir.text()


def test_first_db_download_loads_list_and_focuses_search(window, monkeypatch):
    shown = []
    monkeypatch.setattr(window, "reload_databases", lambda m=None: shown.append(("reload", m)))
    monkeypatch.setattr(window, "show_all", lambda: shown.append("all"))
    focused = []
    monkeypatch.setattr(window.search_edit, "setFocus", lambda *a: focused.append(1))
    window.on_db_updated(True, "")
    assert shown == [("reload", None), "all"]
    assert focused


def test_no_startup_prompt_dialog_without_db(window, monkeypatch):
    asked = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: asked.append(1) or QMessageBox.No)
    window.on_version("v9", "", manual=False)
    assert not asked


# ---- keyboard, accessibility, scaling
def _songs(n=3):
    return [{"title": f"Song {i}", "category": "Pop", "files": [], "id": i} for i in range(n)]


def test_tab_order_runs_search_to_download(window):
    pos = {}
    w = window.search_edit
    for i in range(300):
        pos.setdefault(w, i)
        w = w.nextInFocusChain()
    assert pos[window.search_edit] < pos[window.cat_combo] < pos[window.filter_btn] \
        < pos[window.table] < pos[window.download_btn] < pos[window.selall_btn]


def test_accessible_names_and_shortcut_tooltips(window):
    for w in (window.search_edit, window.cat_combo, window.table, window.pause_btn,
              window.stop_btn, window.selall_btn, window.monitor_btn):
        assert w.accessibleName() and w.accessibleDescription()
    assert window.accessibleName() is not None
    assert "Ctrl+D" in window.download_btn.toolTip()
    assert "Ctrl+A" in window.selall_btn.toolTip()
    assert "Ctrl+F" in window.search_edit.toolTip()


def test_ctrl_a_checks_all_and_down_enters_table(window):
    window.song_model.set_songs(SONGS)
    assert window.song_model.selected_songs() == []
    window._check_all_visible()
    assert len(window.song_model.selected_songs()) == len(SONGS)
    window._search_down()
    assert window.table.currentIndex().isValid()


def test_f5_reruns_search(window, monkeypatch):
    calls = []
    monkeypatch.setattr(window, "do_search", lambda: calls.append(1))
    window._refresh_current()
    assert calls == [1]


def test_font_scale_applies_and_persists(window, qapp, tmp_path):
    import tomllib
    base_h = window.table.fontMetrics().height()
    try:
        window.font_combo.setCurrentIndex(window.font_combo.findData(130))
        assert window.font_scale == 130
        fm = window.table.fontMetrics()
        assert window.table.verticalHeader().defaultSectionSize() >= fm.height() + 10
        assert window.table.font().pointSizeF() > 9.5
        window.save_config()
        with open(tmp_path / "config.toml", "rb") as f:
            assert tomllib.load(f)["display"]["font_scale"] == 130
    finally:
        window.font_combo.setCurrentIndex(window.font_combo.findData(100))
    assert ese_qt.MainWindow._valid_font_scale(77) == 100
    assert ese_qt.MainWindow._valid_font_scale("130") == 100


@pytest.mark.parametrize("lang", ["zh_TW", "en", "ja"])
def test_new_i18n_keys_present(lang):
    from i18n import TR
    for key in ("search_tip", "acc_category", "acc_table", "selall_tip",
                "font_label", "font_tip"):
        assert TR[lang][key]
    assert "F5" in TR[lang]["shortcuts_text"] and "Ctrl+A" in TR[lang]["shortcuts_text"]


def test_settings_dialog_fits_its_rows(window):
    """The folder row (field + two buttons) must not be wider than the dialog."""
    dlg = window.settings_dlg
    dlg.show()
    QApplication.processEvents()
    try:
        assert window.opendir_btn.geometry().right() <= window.opendir_btn.parentWidget().width()
        assert dlg.width() >= dlg.layout().minimumSize().width()
    finally:
        dlg.hide()


def test_download_filter_and_status_column(window):
    songs = [{"song_name": n, "category": "01 Pop", "files": []} for n in ("a", "b", "c")]
    window.all_songs = songs
    window.song_model.dl_status = {("a", "01 Pop"): 2, ("b", "01 Pop"): 1}
    window.dl_combo.setCurrentIndex(window.dl_combo.findData("downloaded"))
    assert [s["song_name"] for s in window.song_model.songs] == ["a"]
    window.dl_combo.setCurrentIndex(window.dl_combo.findData("missing"))
    assert [s["song_name"] for s in window.song_model.songs] == ["b", "c"]
    assert window.active_filter_count() == 1
    window.reset_filters()
    assert len(window.song_model.songs) == 3


# ---------------------------------------------------------------- detail panel
_SONG = {"song_name": "Test Song", "category": "01 Pop",
         "files": [{"filename": "a.tja", "file_path": "01 Pop/Test Song/a.tja",
                    "file_type": "tja", "size": 2048},
                   {"filename": "a.ogg", "file_path": "01 Pop/Test Song/a.ogg",
                    "file_type": "ogg", "size": 0}]}


def _load_song(window):
    window.jp_map = window.song_model.jp_map = {"Test Song": "テスト"}
    window.meta_map = window.song_model.meta_map = {
        "Test Song": {"bpm": "150", "level_easy": 2, "level_oni": 9}}
    window.song_model.set_songs([_SONG])
    window.table.setCurrentIndex(window.song_model.index(0, 1))


def test_detail_panel_shows_current_song(window):
    window.set_detail_open(True)
    _load_song(window)
    dp = window.detail_panel
    assert dp.title.text() == "Test Song"
    assert dp.jp.text() == "テスト"
    assert "150" in dp.bpm.text()
    assert [n.text() for n in dp.level_nums] == ["2", "−", "−", "9", "−"]
    assert dp.files.count() == 2
    assert not dp.open_btn.isEnabled()          # not downloaded
    window.song_model.set_songs([])
    assert dp.title.isHidden()                   # no current row -> placeholder


def test_detail_panel_toggle_and_config(window, tmp_path):
    import tomllib
    window.set_detail_open(True)
    assert window.detail_btn.isChecked() and window.act_detail.isChecked()
    window.act_detail.trigger()                  # View menu toggles it off
    assert not window.detail_btn.isChecked()
    assert window.detail_panel.isHidden()
    window.detail_btn.setChecked(True)
    window._detail_w = 333
    window.save_config()
    with open(tmp_path / "config.toml", "rb") as f:
        disp = tomllib.load(f)["display"]
    assert disp["detail_open"] is True and disp["detail_w"] >= 220


def test_detail_panel_buttons_never_take_focus(window):
    from PySide6.QtCore import Qt
    dp = window.detail_panel
    for b in (dp.dl_btn, dp.open_btn, dp.copy_btn, window.detail_btn):
        assert b.focusPolicy() == Qt.NoFocus


def test_detail_panel_copy_and_download(window, monkeypatch):
    from PySide6.QtGui import QGuiApplication
    window.set_detail_open(True)
    _load_song(window)
    got = []
    monkeypatch.setattr(window, "start_download", lambda files, **k: got.append(files))
    window.detail_panel.copy_btn.click()
    assert QGuiApplication.clipboard().text() == "Test Song"
    window.detail_panel.dl_btn.click()
    assert len(got) == 1 and len(got[0]) == 2


@pytest.mark.parametrize("lang", ["zh_TW", "en", "ja"])
def test_detail_panel_strings_exist(lang):
    for k in ("dp_title", "dp_files", "dp_download", "dp_copy", "dp_empty",
              "mw_menu_view", "dp_toggle", "dp_toggle_tip"):
        assert ese_qt.TR[lang].get(k)


# ---- download monitor: log toolbar and failed list
def test_log_filter_errors_only_and_counts(window):
    lv = window.log_view
    lv.clear_log()
    lv.appendPlainText("hello world")
    lv.appendPlainText(window.tr("log_fail", f="a.tja", e="boom"))
    assert lv.error_count == 1
    assert "(1" in window.tabs.tabText(1) or "1" in window.tabs.tabText(1)
    assert lv.toPlainText().count("[") == 2          # timestamps on every line
    window.log_filter.setText("HELLO")
    assert "hello world" in lv.toPlainText() and "boom" not in lv.toPlainText()
    window.log_filter.setText("")
    window.log_err_chk.setChecked(True)
    assert "boom" in lv.toPlainText() and "hello" not in lv.toPlainText()
    window.log_err_chk.setChecked(False)
    window.copy_log()
    assert "hello world" in QApplication.clipboard().text()


def test_log_save_and_clear(window, tmp_path, monkeypatch):
    out = tmp_path / "log.txt"
    monkeypatch.setattr(ese_qt.QFileDialog, "getSaveFileName",
                        lambda *a, **k: (str(out), ""))
    window.log_view.clear_log()
    window.log_view.appendPlainText("line one")
    window.save_log()
    assert "line one" in out.read_text(encoding="utf-8")
    window.log_clear_btn.click()
    assert window.log_view.toPlainText() == ""


def test_failed_tab_reasons_and_selective_retry(window, monkeypatch):
    s = {"song_name": "S"}
    fa = {"filename": "a.tja", "file_path": "x/a.tja", "download_url": None}
    fb = {"filename": "b.tja", "file_path": "x/b.tja",
          "download_url": "https://h/ESE/media/branch/master/x/b.tja"}

    class Job:
        failed = [(s, fa), (s, fb)]
        fail_reasons = {"x/a.tja": "no network", "x/b.tja": "disk full"}
        stopped = False

        def snapshot(self):
            return 2, 2, 0.0, 0.0, []

        def is_paused(self):
            return False

    window.dl_thread = Job()
    monkeypatch.setattr(window, "_show_summary", lambda *a, **k: None)   # no modal
    monkeypatch.setattr(window.notifier, "notify", lambda *a, **k: None)
    window.on_download_done(0, 0, 2, 2)
    assert window.fail_list.count() == 2
    assert "no network" in window.fail_list.item(0).text()
    assert "2" in window.tabs.tabText(2)
    assert not window.retry_sel_btn.isEnabled()
    started = []
    monkeypatch.setattr(window, "start_download", lambda files, **k: started.append(files))
    window.fail_list.item(1).setSelected(True)
    assert window.retry_sel_btn.isEnabled()
    window.retry_sel_btn.click()
    assert started == [[(s, fb)]]
    opened = []
    monkeypatch.setattr(ese_qt.webbrowser, "open", lambda u: opened.append(u))
    window.fail_page_btn.click()
    assert opened == ["https://h/ESE/src/branch/master/x"]
    window.copy_fail_paths()
    assert QApplication.clipboard().text().endswith("b.tja")
    window.dl_thread = None


def test_downloader_remembers_failure_reason(tmp_path):
    job = core.Downloader([], str(tmp_path), 1)
    assert job.fail_reasons == {}


def test_log_batch_is_split_into_lines(window):
    """DownloadThread.flush_log sends many lines at once; each is its own entry."""
    lv = window.log_view
    lv.clear_log()
    lv.appendPlainText("ok one\n" + window.tr("log_fail", f="b.tja", e="x") + "\nok two")
    assert lv.error_count == 1
    assert lv.toPlainText().count("[") == 3
    window.log_err_chk.setChecked(True)
    assert "ok one" not in lv.toPlainText() and "b.tja" in lv.toPlainText()
    window.log_err_chk.setChecked(False)
