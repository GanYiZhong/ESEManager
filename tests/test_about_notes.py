"""About dialog, release notes in the update confirm, What's new on startup."""

from PySide6.QtWidgets import QApplication, QDialog

import appconfig
import core
import dialogs
import ese_qt
from i18n import TR
from test_gui import window  # noqa: F401  (fixture)


def test_i18n_keys_everywhere():
    for k in ("about_title", "about_version", "about_data_dir", "about_log", "about_open",
              "about_copy_diag", "about_copied", "about_close", "whatsnew_title",
              "whatsnew_none"):
        assert all(k in TR[lang] for lang in ("zh_TW", "en", "ja"))


def test_diagnostics_text():
    t = dialogs.diagnostics_text("abc123")
    for part in (appconfig.APP_VERSION, "Python:", "Qt:", "abc123", "Download source:"):
        assert part in t


def test_about_dialog_copy(qapp):
    d = dialogs.AboutDialog(None, lambda k, **kw: TR["en"][k], "dbv")
    d.copy_diagnostics()
    assert "dbv" in QApplication.clipboard().text()
    d.close()


def test_about_menu_opens(window, monkeypatch):
    seen = []
    monkeypatch.setattr(dialogs.AboutDialog, "exec", lambda self: seen.append(self))
    window.act_about.trigger()
    assert len(seen) == 1


def test_fetch_release_by_tag(monkeypatch):
    class R:
        def json(self):
            return {"body": "x"}
    urls = []
    monkeypatch.setattr(core, "get_with_retry", lambda s, u, **k: urls.append(u) or R())
    monkeypatch.setattr(core, "new_session", lambda: None)
    assert core.fetch_release_by_tag("v1.2.3")["body"] == "x"
    assert urls[0].endswith("/releases/tags/v1.2.3")


def test_update_confirm_shows_notes(window, monkeypatch):
    monkeypatch.setattr(core, "can_self_update", lambda: True)
    window._app_update_tag = "v9.9.9"
    window._app_update_notes = ("v9.9.9", "# Hi\n- thing")
    shown = []

    def fake_exec(self):
        shown.append(self.browser.toPlainText())
        return QDialog.Rejected
    monkeypatch.setattr(dialogs.ReleaseNotesDialog, "exec", fake_exec)
    window.install_app_update()
    assert shown and "thing" in shown[0]
    assert getattr(window, "_selfupd", None) is None


def test_whats_new_after_upgrade(window, monkeypatch):
    monkeypatch.setattr(ese_qt, "APP_VERSION", "v2.0.0")
    window.config = {"display": {"last_seen_version": "v1.0.0"}}
    started = []
    monkeypatch.setattr(ese_qt.ReleaseNotesThread, "start",
                        lambda self: started.append(self.tag))
    window.check_whats_new()
    assert started == ["v2.0.0"]
    assert window._last_seen_version == "v2.0.0"
    window._show_whats_new("v2.0.0", "- new")
    dlg = window._whats_new
    assert isinstance(dlg, dialogs.WhatsNewDialog) and dlg.isVisible()
    dlg.close()


def test_no_whats_new_when_same_or_dev(window, monkeypatch):
    started = []
    monkeypatch.setattr(ese_qt.ReleaseNotesThread, "start", lambda self: started.append(1))
    monkeypatch.setattr(ese_qt, "APP_VERSION", "v2.0.0")
    window.config = {"display": {"last_seen_version": "v2.0.0"}}
    window.check_whats_new()
    window.config = {"display": {}}            # first run: just record
    window.check_whats_new()
    monkeypatch.setattr(ese_qt, "APP_VERSION", "dev")
    window.check_whats_new()
    assert not started
