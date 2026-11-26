"""In-window toasts: lifecycle, hover pause, stacking, actions, and that
info-only messages no longer open modal QMessageBoxes."""

import pytest
from PySide6.QtWidgets import QMessageBox, QWidget

import toast as toast_mod
from test_gui import window                    # noqa: F401  (fixture re-export)
from toast import ToastManager


@pytest.fixture
def host(qapp):
    w = QWidget()
    w.resize(800, 600)
    w.show()
    mgr = ToastManager(w, lambda k: "Close", lambda: 560)
    yield w, mgr
    w.close()
    w.deleteLater()


def test_show_positions_bottom_right_above_anchor(host):
    w, mgr = host
    t = mgr.info("hello")
    assert t.isVisible()
    assert t.x() + t.width() <= w.width()
    assert t.y() + t.height() <= 560
    assert t.accessibleDescription() == "hello" and t.accessibleName()
    assert t.close_btn.accessibleName() == "Close"


def test_auto_dismiss_with_short_timeout(host, qapp):
    w, mgr = host
    t = mgr.show("bye", timeout=30)
    assert t in mgr.toasts
    from PySide6.QtTest import QTest
    QTest.qWait(150)
    assert mgr.toasts == [] and t._closed


def test_default_durations_and_sticky_error(host):
    w, mgr = host
    assert mgr.info("a").timeout == toast_mod.INFO_MS
    assert mgr.warning("b").timeout == toast_mod.WARNING_MS > toast_mod.INFO_MS
    e = mgr.error("c")
    assert e.timeout == 0 and not e._timer.isActive()   # sticky until closed
    e.close_btn.click()
    assert e not in mgr.toasts


def test_hover_pauses_and_resumes(host):
    w, mgr = host
    t = mgr.show("x", timeout=60000)
    assert t._timer.isActive()
    t.pause()
    assert not t._timer.isActive() and t._remaining > 1000
    t.resume()
    assert t._timer.isActive()


def test_stacking_limit_drops_oldest(host):
    w, mgr = host
    ts = [mgr.info(f"m{i}") for i in range(5)]
    assert len(mgr.toasts) == toast_mod.MAX_VISIBLE == 3
    assert mgr.toasts == ts[2:] and ts[0]._closed and ts[1]._closed
    ys = [t.y() for t in mgr.toasts]
    assert ys == sorted(ys)                 # newest sits lowest
    assert len({t.y() for t in mgr.toasts}) == 3


def test_duplicate_text_does_not_stack(host):
    w, mgr = host
    a = mgr.info("same")
    b = mgr.info("same")
    assert a is b and len(mgr.toasts) == 1


def test_action_callback_runs_and_dismisses(host):
    w, mgr = host
    got = []
    t = mgr.info("done", actions=[("Show", lambda: got.append(1)),
                                  ("Undo", lambda: got.append(2))])
    assert [b.text() for b in t.action_buttons] == ["Show", "Undo"]
    t.action_buttons[0].click()
    assert got == [1] and t._closed and t not in mgr.toasts


def test_follows_window_resize(host):
    w, mgr = host
    t = mgr.info("r")
    w.resize(500, 400)
    from PySide6.QtTest import QTest
    QTest.qWait(20)
    mgr.reposition()
    assert t.x() + t.width() <= 500


@pytest.mark.parametrize("mode", ["light", "dark", "high_contrast"])
def test_restyle_each_mode(host, mode):
    import theme
    from PySide6.QtWidgets import QApplication
    w, mgr = host
    t = mgr.warning("w")
    theme.apply_theme(QApplication.instance(), mode)
    try:
        t.restyle()
        assert theme.colours()["hint_bg"].lower() in t.styleSheet().lower()
    finally:
        theme.apply_theme(QApplication.instance(), "light")


# ---- previously modal messages are now toasts

def _boom(*a, **k):
    raise AssertionError("modal QMessageBox for an info-only message")


def test_window_info_messages_do_not_open_modals(window, monkeypatch):   # noqa: F811
    for name in ("information", "warning", "critical", "question"):
        monkeypatch.setattr(QMessageBox, name, staticmethod(_boom))
    monkeypatch.setattr(QMessageBox, "exec", _boom)
    seen = []
    orig = window.toasts.show
    monkeypatch.setattr(window.toasts, "show",
                        lambda text, *a, **k: seen.append(text) or orig(text, *a, **k))
    window.start_download_selected()                 # nothing selected
    window.check_missing()                           # no song database yet
    window.on_version("v1", "v1", manual=True)       # up to date or offline
    window.on_version("", "v1", manual=True)         # offline
    window.on_updates_loaded([])                     # nothing to update
    window.on_version_sorting_done(True, "latest", "abcdef0123")
    window._show_summary("all done", 0)
    window._db_done_box("db ok", True)
    texts = seen
    assert window.tr("no_selection") in texts
    assert window.tr("db_offline") in texts
    assert window.tr("upd_none") in texts
    assert any(t.action_buttons for t in window.toasts.toasts)
    assert len(window.toasts.toasts) <= toast_mod.MAX_VISIBLE
