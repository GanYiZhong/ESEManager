"""Keep-awake and close-during-download behaviour (no real dialogs, no real ctypes)."""
import sys
import tomllib
from types import SimpleNamespace

import ese_qt
import power
from test_gui import window  # noqa: F401  (fixture)


def test_windows_acquire_release_flags(monkeypatch):
    calls = []
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(power, "_win_set", lambda f: calls.append(f) or 1)
    k = power.KeepAwake()
    assert k.acquire() and k.acquire()          # idempotent
    k.release()
    k.release()
    assert calls == [power.ES_CONTINUOUS | power.ES_SYSTEM_REQUIRED, power.ES_CONTINUOUS]


def test_failure_is_a_noop(monkeypatch):
    def boom(f):
        raise OSError
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(power, "_win_set", boom)
    k = power.KeepAwake()
    assert k.acquire() is False
    k.release()


def test_linux_without_dbus_service(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(power.KeepAwake, "_dbus_inhibit", lambda self: False)
    k = power.KeepAwake()
    assert k.acquire() is False and not k.active
    k.release()


class FakeThread:
    stopped = False

    def __init__(self):
        self.calls = []

    def isRunning(self):
        return True

    def stop(self):
        self.calls.append("stop")

    def wait(self, ms):
        return True

    def is_paused(self):
        return False


def _arm(window, monkeypatch, choice, tray=True):
    t = FakeThread()
    window.dl_thread = t
    window._threads.append(t)
    window.notifier.tray = object() if tray else None
    seen = {}

    def ask(can_bg):
        seen["can_bg"] = can_bg
        return choice
    monkeypatch.setattr(window, "_ask_close_during_download", ask)
    monkeypatch.setattr(window, "_enter_background", lambda: seen.setdefault("bg", True))
    window.awake = SimpleNamespace(release=lambda: seen.setdefault("released", True))
    return t, seen


def _close(window, t):
    from PySide6.QtGui import QCloseEvent
    ev = QCloseEvent()
    window.closeEvent(ev)
    window._threads.remove(t)
    window.dl_thread = None
    window.notifier.tray = None
    return ev


def test_close_cancel(window, monkeypatch):
    t, seen = _arm(window, monkeypatch, "cancel")
    ev = _close(window, t)
    assert not ev.isAccepted() and not window._closing and "released" not in seen


def test_close_background(window, monkeypatch):
    t, seen = _arm(window, monkeypatch, "background")
    ev = _close(window, t)
    assert not ev.isAccepted() and seen.get("bg") and t.calls == []


def test_close_quit_stops_and_releases(window, monkeypatch):
    t, seen = _arm(window, monkeypatch, "quit", tray=False)
    ev = _close(window, t)
    assert ev.isAccepted() and t.calls == ["stop"] and seen["released"]
    assert seen["can_bg"] is False


def test_settings_checkbox_default_and_saved(window):
    assert window.keep_awake_chk.isChecked()
    window.keep_awake_chk.setChecked(False)
    with open(ese_qt.CONFIG_FILE, "rb") as f:
        assert tomllib.load(f)["download"]["keep_awake"] is False
