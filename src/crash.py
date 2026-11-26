"""Crash reporter: never let an unhandled exception vanish silently.

Installs sys.excepthook / threading.excepthook (exceptions escaping Qt slots
land in sys.excepthook under PySide6), logs the full traceback, and shows one
friendly dialog per distinct error. A startup crash shows a minimal fatal
dialog and leaves a marker file so the next launch can offer to open the log.
Qt is imported lazily so the CLI can use this module without it.
"""

import os
import re
import sys
import threading
import time
import traceback
import urllib.parse
from collections import deque

import core
from appconfig import APP_DIR, APP_VERSION, GITHUB_REPO
from i18n import TR, detect_system_lang

LOG_NAME = "ESEManager.log"
MARKER_NAME = "ESEManager.crash"
RATE_MAX = 3            # dialogs per RATE_WINDOW seconds
RATE_WINDOW = 60.0

_state = {"ready": False, "lang": None, "seen": set(), "stamps": deque(),
          "open": None, "bridge": None, "prev_hooks": None, "prev_box": None}


# ------------------------------------------------------------------ helpers
def tr(key, **kw):
    lang = _state["lang"] or detect_system_lang()
    s = TR.get(lang, TR["zh_TW"]).get(key, TR["zh_TW"].get(key, key))
    return s.format(**kw) if kw else s


def log_path():
    return os.path.join(APP_DIR, LOG_NAME)


def marker_path():
    return os.path.join(APP_DIR, MARKER_NAME)


def debug_enabled(argv=None):
    return os.environ.get("ESEMANAGER_DEBUG") == "1" or "--debug" in (sys.argv if argv is None else argv)


def scrub(text):
    """Remove personal data: home directory -> ~, user-named path segments, emails."""
    text = str(text)
    home = os.path.expanduser("~")
    if home and home not in ("~", os.sep, "/"):
        for variant in {home, home.replace("\\", "/"), home.replace("/", "\\")}:
            text = re.sub(re.escape(variant), "~", text, flags=re.IGNORECASE)
        user = os.path.basename(home.rstrip("\\/"))
        if user:
            text = re.sub(r"(?<=[\\/])" + re.escape(user) + r"(?=[\\/])", "~user", text,
                          flags=re.IGNORECASE)
    return re.sub(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", "<email>", text)


def error_key(exc_type, tb):
    """Identity of an error: exception type + innermost frame (file, function)."""
    frames = traceback.extract_tb(tb) if tb is not None else []
    top = frames[-1] if frames else None
    where = (os.path.basename(top.filename), top.name) if top else ("?", "?")
    return (getattr(exc_type, "__qualname__", str(exc_type)), *where)


def summary_line(exc_type, exc):
    name = getattr(exc_type, "__name__", str(exc_type))
    msg = scrub(str(exc)).strip().splitlines()[0] if str(exc).strip() else ""
    return f"{name}: {msg[:200]}" if msg else name


def diagnostics():
    import platform
    try:
        import PySide6
        from PySide6.QtCore import qVersion
        qt = f"{qVersion()} (PySide6 {PySide6.__version__})"
    except Exception:
        qt = "-"
    return "\n".join([
        f"ESEManager {APP_VERSION}",
        f"OS: {platform.platform()}",
        f"Python: {platform.python_version()}",
        f"Qt: {qt}",
        f"Download source: {getattr(core, '_download_source', '-')}",
        f"Frozen: {bool(getattr(sys, 'frozen', False))}",
    ])


def format_report(exc_type, exc, tb):
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    return scrub(text).rstrip() + "\n\n" + diagnostics()


def issue_url(exc_type, tb):
    """New-issue URL with a title only: no traceback, message or personal data."""
    _, fname, func = error_key(exc_type, tb)
    title = f"Crash: {getattr(exc_type, '__name__', 'Error')} in {fname}:{func}"
    return (f"https://github.com/{GITHUB_REPO}/issues/new?"
            + urllib.parse.urlencode({"title": title}))


def _rate_ok(now=None):
    now = time.monotonic() if now is None else now
    stamps = _state["stamps"]
    while stamps and now - stamps[0] > RATE_WINDOW:
        stamps.popleft()
    if len(stamps) >= RATE_MAX:
        return False
    stamps.append(now)
    return True


# ------------------------------------------------------------------ marker
def write_marker(note=""):
    try:
        with open(marker_path(), "w", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {APP_VERSION} {scrub(note)}\n")
    except OSError:
        pass


def clear_marker():
    try:
        os.remove(marker_path())
    except OSError:
        pass


def consume_marker():
    """True if the previous run died on the fatal path; removes the marker."""
    found = os.path.exists(marker_path())
    if found:
        clear_marker()
    return found


# ------------------------------------------------------------------ logging
def log_exception(exc_type, exc, tb, where=""):
    first = error_key(exc_type, tb) not in _state["seen"]
    try:
        if first:
            core.log.error("Unhandled exception%s", where, exc_info=(exc_type, exc, tb))
        else:
            core.log.error("Unhandled exception (repeat)%s: %s", where, summary_line(exc_type, exc))
    except Exception:
        pass


# ------------------------------------------------------------------ dialogs
def _open_log_folder():
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(log_path()) or APP_DIR))


def _open_url(url):
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    QDesktopServices.openUrl(QUrl(url))


def _build_dialog(exc_type, exc, tb, fatal):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout
    dlg = QDialog()
    dlg.setWindowTitle(tr("crash_title"))
    dlg.setMinimumWidth(420)
    lay = QVBoxLayout(dlg)
    lbl = QLabel(tr("crash_text_fatal" if fatal else "crash_text",
                    summary=summary_line(exc_type, exc)))
    lbl.setWordWrap(True)
    lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
    lay.addWidget(lbl)
    row = QHBoxLayout()
    copy = QPushButton(tr("crash_copy"))
    report_text = format_report(exc_type, exc, tb)

    def do_copy():
        QGuiApplication.clipboard().setText(report_text)
        copy.setText(tr("crash_copied"))
    copy.clicked.connect(do_copy)
    logb = QPushButton(tr("crash_open_log"))
    logb.clicked.connect(_open_log_folder)
    rep = QPushButton(tr("crash_report"))
    rep.clicked.connect(lambda: _open_url(issue_url(exc_type, tb)))
    for b in (copy, logb, rep):
        b.setAutoDefault(False)
        row.addWidget(b)
    lay.addLayout(row)
    row2 = QHBoxLayout()
    row2.addStretch(1)
    quit_b = QPushButton(tr("crash_quit"))
    quit_b.setAutoDefault(False)
    cont = None
    if fatal:
        quit_b.clicked.connect(dlg.accept)
        quit_b.setDefault(True)
    else:
        def do_quit():
            dlg.accept()
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app:
                app.quit()
        quit_b.clicked.connect(do_quit)
        cont = QPushButton(tr("crash_continue"))
        cont.setDefault(True)
        cont.clicked.connect(dlg.accept)
        row2.addWidget(cont)
    row2.addWidget(quit_b)
    lay.addLayout(row2)
    dlg.copy_button, dlg.log_button, dlg.report_button = copy, logb, rep
    dlg.continue_button, dlg.quit_button = cont, quit_b
    return dlg


def _show(dlg, modal):
    """Single seam for tests: modal exec (startup) or non-blocking show."""
    if modal:
        dlg.exec()
    else:
        dlg.show()


def _ensure_app():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    return app


def _flush_log():
    for h in list(core.log.handlers):
        try:
            h.flush()
        except Exception:
            pass


def _terminate(code):
    _flush_log()
    os._exit(code)


def _present(exc_type, exc, tb):
    """Show the non-fatal dialog (GUI thread only), one at a time."""
    if _state["open"] is not None:
        return                      # the rest are in the log
    dlg = _build_dialog(exc_type, exc, tb, fatal=False)
    _state["open"] = dlg
    dlg.finished.connect(lambda *_: _state.update(open=None))
    _show(dlg, modal=False)


def _get_bridge():
    if _state["bridge"] is None:
        from PySide6.QtCore import QObject, Signal, Slot
        from PySide6.QtWidgets import QApplication

        class Bridge(QObject):
            raised = Signal(object, object, object)

            @Slot(object, object, object)
            def on_raised(self, et, e, tb):
                _present(et, e, tb)

        br = Bridge()
        br.moveToThread(QApplication.instance().thread())   # queued delivery to the GUI thread
        br.raised.connect(br.on_raised)
        _state["bridge"] = br
    return _state["bridge"]


def fatal(exc_type, exc, tb):
    """Startup crash: leave the marker, show a minimal dialog, exit 1."""
    write_marker(summary_line(exc_type, exc))
    try:
        _ensure_app()
        _show(_build_dialog(exc_type, exc, tb, fatal=True), modal=True)
    except Exception:
        core.log.error("could not show the fatal-error dialog", exc_info=True)
    _terminate(1)


# ------------------------------------------------------------------ hooks
def handle(exc_type, exc, tb, where=""):
    """Common entry for every hook. Never raises."""
    try:
        if issubclass(exc_type, KeyboardInterrupt):
            return
        core.setup_logging()
        log_exception(exc_type, exc, tb, where)
        key = error_key(exc_type, tb)
        if not _state["ready"]:
            _state["seen"].add(key)
            fatal(exc_type, exc, tb)
            return
        if key in _state["seen"]:
            return
        _state["seen"].add(key)
        if not _rate_ok():
            return
        from PySide6.QtWidgets import QApplication
        if QApplication.instance() is None:
            return
        if threading.current_thread() is threading.main_thread():
            _present(exc_type, exc, tb)
        else:
            _get_bridge().raised.emit(exc_type, exc, tb)
    except Exception:
        try:
            core.log.error("crash reporter failed", exc_info=True)
        except Exception:
            pass


def _sys_hook(exc_type, exc, tb):
    handle(exc_type, exc, tb)


def _thread_hook(args):
    if args.exc_type is SystemExit:
        return
    name = getattr(args.thread, "name", "?")
    handle(args.exc_type, args.exc_value, args.exc_traceback, where=f" in thread {name}")


def install(lang=None):
    """Install both hooks (idempotent). Call as early as possible in main()."""
    if _state["prev_hooks"] is None:
        _state["prev_hooks"] = (sys.excepthook, threading.excepthook)
    _state["lang"] = lang
    sys.excepthook = _sys_hook
    threading.excepthook = _thread_hook


def reset():
    _state.update(ready=False, lang=None, open=None, bridge=None, prev_box=None)
    _state["seen"].clear()
    _state["stamps"].clear()


def uninstall():
    prev = _state["prev_hooks"]
    if prev is not None:
        sys.excepthook, threading.excepthook = prev
    _state["prev_hooks"] = None
    reset()


def set_ready(ready=True, lang=None):
    """Main window is up: later errors get the Continue/Quit dialog."""
    _state["ready"] = ready
    if lang:
        _state["lang"] = lang


# ------------------------------------------------------------------ previous crash
def offer_previous_crash(parent=None):
    """After a fatal run, offer to open the log (non-blocking)."""
    from PySide6.QtWidgets import QMessageBox
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Warning)
    box.setWindowTitle(tr("crash_title"))
    box.setText(tr("crash_prev"))
    open_b = box.addButton(tr("crash_prev_open"), QMessageBox.AcceptRole)
    box.addButton(tr("crash_continue"), QMessageBox.RejectRole)
    box.finished.connect(lambda *_: box.clickedButton() is open_b and _open_log_folder())
    _state["prev_box"] = box
    box.open()
    return box


# ------------------------------------------------------------------ CLI
def cli_fail(exc, argv=None, stream=None):
    """One friendly stderr line + log; the raw traceback only with --debug."""
    stream = stream or sys.stderr
    try:
        core.setup_logging()
        core.log.error("CLI failed", exc_info=(type(exc), exc, exc.__traceback__))
    except Exception:
        pass
    if debug_enabled(argv):
        traceback.print_exception(type(exc), exc, exc.__traceback__, file=stream)
        return 1
    print(tr("crash_cli", err=summary_line(type(exc), exc), log=scrub(log_path())),
          file=stream)
    return 1
