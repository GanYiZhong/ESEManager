"""Keep the computer awake while a long download runs.

Windows: SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED) on acquire and
ES_CONTINUOUS on release. The state belongs to the calling thread, so acquire and
release must happen on the same (GUI) thread.
Linux: org.freedesktop.ScreenSaver Inhibit/UnInhibit over QtDBus, only if the
service is available. Anything else (or any failure): silently does nothing.
"""
import sys

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def _win_set(flags):
    import ctypes
    return ctypes.windll.kernel32.SetThreadExecutionState(flags)


class KeepAwake:
    """acquire()/release() are idempotent and never raise."""

    def __init__(self, reason="Downloading songs"):
        self.reason = reason
        self.active = False
        self._cookie = None
        self._iface = None

    def acquire(self):
        if self.active:
            return True
        try:
            if sys.platform == "win32":
                ok = bool(_win_set(ES_CONTINUOUS | ES_SYSTEM_REQUIRED))
            elif sys.platform.startswith("linux"):
                ok = self._dbus_inhibit()
            else:
                ok = False
        except Exception:
            ok = False
        self.active = ok
        return ok

    def release(self):
        if not self.active:
            return
        self.active = False
        try:
            if sys.platform == "win32":
                _win_set(ES_CONTINUOUS)
            elif self._iface is not None and self._cookie is not None:
                self._iface.call("UnInhibit", self._cookie)
        except Exception:
            pass
        self._cookie = None
        self._iface = None

    def _dbus_inhibit(self):
        from PySide6.QtDBus import QDBusConnection, QDBusInterface
        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            return False
        iface = QDBusInterface("org.freedesktop.ScreenSaver", "/org/freedesktop/ScreenSaver",
                               "org.freedesktop.ScreenSaver", bus)
        if not iface.isValid():
            return False
        reply = iface.call("Inhibit", "ESEManager", self.reason)
        args = reply.arguments()
        if not args:
            return False
        self._iface, self._cookie = iface, args[0]
        return True
