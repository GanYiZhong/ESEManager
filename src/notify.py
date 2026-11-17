"""Application icon and completion notifications.

- resource_path / app_icon / set_app_icon: load assets/icon.ico from the source tree
  or from the PyInstaller onedir bundle (sys._MEIPASS).
- Notifier: tells the user a long task has finished. It flashes the taskbar button and,
  when a system tray is available, shows a tray balloon. Both happen only when the
  main window is not the active window, so nothing pops up while the user is watching.
"""
import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

ICON_FILE = "icon.ico"
BALLOON_MS = 6000


def resource_path(*parts):
    """Path to a bundled resource. Frozen: inside sys._MEIPASS. Source: repo root."""
    if getattr(sys, "frozen", False):
        root = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, *parts)


def app_icon():
    return QIcon(resource_path("assets", ICON_FILE))


def set_app_icon(app):
    """Set the icon every top-level window inherits. Returns the QIcon (may be null)."""
    icon = app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    return icon


class Notifier:
    """Notify the user when `window` is in the background. Safe without a system tray."""

    def __init__(self, window):
        self.window = window
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(app_icon(), window)

    def notify(self, title, message):
        """Flash the taskbar and show a tray balloon if the window is not active.
        Returns True when a notification was raised, False when the window was active."""
        win = self.window
        if win is None or win.isActiveWindow():
            return False
        QApplication.alert(win)
        if self.tray is not None:
            if not self.tray.isVisible():
                self.tray.show()
            self.tray.showMessage(title, message,
                                  QSystemTrayIcon.MessageIcon.Information, BALLOON_MS)
            # Remove the tray icon again once the balloon is gone.
            QTimer.singleShot(BALLOON_MS + 2000, self.tray.hide)
        return True
