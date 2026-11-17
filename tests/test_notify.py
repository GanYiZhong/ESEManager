import os
import struct
import sys

import notify

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICON_PNG = os.path.join(ROOT, "assets", "icon.png")
ICON_ICO = os.path.join(ROOT, "assets", "icon.ico")


def test_icon_files_exist_and_load(qapp):
    from PySide6.QtGui import QIcon, QImage
    assert os.path.isfile(ICON_PNG) and os.path.isfile(ICON_ICO)
    assert not QIcon(ICON_PNG).isNull()
    assert not QIcon(ICON_ICO).isNull()
    img = QImage(ICON_PNG)
    assert not img.isNull()
    assert (img.width(), img.height()) == (256, 256)


def test_ico_contains_expected_sizes():
    with open(ICON_ICO, "rb") as f:
        data = f.read()
    reserved, kind, count = struct.unpack("<HHH", data[:6])
    assert reserved == 0 and kind == 1
    sizes = set()
    for i in range(count):
        w, h = struct.unpack("<BB", data[6 + 16 * i:8 + 16 * i])
        sizes.add(w or 256)
        assert (h or 256) == (w or 256)
    assert sizes == {16, 32, 48, 256}


def test_app_icon_and_set_app_icon(qapp):
    assert not notify.app_icon().isNull()
    assert not notify.set_app_icon(qapp).isNull()


def test_resource_path_uses_meipass_when_frozen(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert notify.resource_path("assets", "icon.ico") == os.path.join(
        str(tmp_path), "assets", "icon.ico")


def test_notifier_without_tray_does_not_crash(qapp, monkeypatch):
    from PySide6.QtWidgets import QMainWindow, QSystemTrayIcon
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: False))
    win = QMainWindow()           # never shown, so it is not the active window
    n = notify.Notifier(win)
    assert n.tray is None
    assert n.notify("title", "done") is True


def test_notifier_skips_when_window_active(qapp, monkeypatch):
    from PySide6.QtWidgets import QMainWindow, QSystemTrayIcon
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: False))
    win = QMainWindow()
    win.isActiveWindow = lambda: True
    n = notify.Notifier(win)
    assert n.notify("title", "done") is False


def test_notifier_with_none_window(qapp, monkeypatch):
    from PySide6.QtWidgets import QSystemTrayIcon
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: False))
    assert notify.Notifier(None).notify("t", "m") is False
