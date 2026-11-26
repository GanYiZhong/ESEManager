"""Automatic app update: download in the background when a newer release is
found, install when the window closes (or right away via "Restart now")."""

import sys

import pytest
from PySide6.QtCore import QObject, Signal

import core
import ese_qt


class FakeUpdateThread(QObject):
    done = Signal(bool, str)
    progress = Signal(int, int)
    finished = Signal()
    instances = []

    def __init__(self, tr=None, install=True):
        super().__init__()
        self.install = install
        self.root = None
        self.started = False
        self.stopped = False
        FakeUpdateThread.instances.append(self)

    def start(self, *a):
        self.started = True

    def isRunning(self):
        return self.started and self.root is None and not self.stopped

    def stop(self):
        self.stopped = True

    def wait(self, *a):
        return True

    def finish(self, root="R", tag="v2099.1.1"):
        self.root = root
        self.done.emit(True, f"downloaded:{tag}")
        self.finished.emit()


@pytest.fixture
def win(qapp, tmp_path, monkeypatch):
    import appconfig
    import workers
    for mod in (appconfig, ese_qt, workers, core):
        for name, val in (("DB_PATH", tmp_path / "ese_songs.db"),
                          ("LOCAL_DB_PATH", tmp_path / "ese_local.db"),
                          ("CONFIG_FILE", tmp_path / "config.toml"),
                          ("VERSION_FILE", tmp_path / "version.txt")):
            if hasattr(mod, name):
                monkeypatch.setattr(mod, name, str(val))
    monkeypatch.setattr(ese_qt.QMessageBox, "question", lambda *a, **k: ese_qt.QMessageBox.No)
    FakeUpdateThread.instances = []
    monkeypatch.setattr(ese_qt, "AppSelfUpdateThread", FakeUpdateThread)
    monkeypatch.setattr(core, "can_self_update", lambda: True)
    installs = []
    monkeypatch.setattr(core, "install_app_update",
                        lambda root, restart_exe=None, app_dir=None:
                        installs.append((root, restart_exe)) or "scheduled")
    w = ese_qt.MainWindow()
    w._toasts_seen = []
    monkeypatch.setattr(w, "toast", lambda text, kind="info", actions=(), timeout=None:
                        w._toasts_seen.append((text, actions)))
    w._installs = installs
    yield w
    w._closing = True
    w.close()


def test_new_version_downloads_automatically(win):
    win.on_app_update("v2099.1.1", "https://example.invalid")
    (t,) = [x for x in FakeUpdateThread.instances if not x.install]
    assert t.started
    t.finish()
    assert win._pending_update == ("R", "v2099.1.1")
    text, actions = win._toasts_seen[-1]
    assert "v2099.1.1" in text and actions            # "Restart now" action
    assert win._installs == []                         # nothing installed yet


def test_close_installs_without_restart(win):
    win.on_app_update("v2099.1.1", "u")
    FakeUpdateThread.instances[-1].finish()
    win._closing = False
    win.close()
    assert win._installs == [("R", None)]


def test_restart_now_installs_with_restart(win, monkeypatch):
    win.on_app_update("v2099.1.1", "u")
    FakeUpdateThread.instances[-1].finish()
    closed = []
    monkeypatch.setattr(win, "close", lambda: closed.append(1))
    win.install_app_update()                           # the status-bar button
    assert win._installs == [("R", sys.executable)]
    assert closed and win._pending_update is None


def test_setting_off_keeps_manual_flow(win):
    win.auto_app_chk.setChecked(False)
    win.on_app_update("v2099.1.1", "u")
    assert not [x for x in FakeUpdateThread.instances if not x.install]
    assert not win.app_update_btn.isHidden()


def test_close_during_background_download_stops_it(win):
    win.on_app_update("v2099.1.1", "u")
    t = FakeUpdateThread.instances[-1]
    win._closing = False
    win.close()
    assert t.stopped and win._installs == []
