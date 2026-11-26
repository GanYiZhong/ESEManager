import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import functools  # noqa: E402
import http.server  # noqa: E402
import threading  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def http_dir(tmp_path):
    """Serve tmp_path/www over HTTP on localhost; yields (www_dir, base_url)."""
    www = tmp_path / "www"
    www.mkdir()

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    handler = functools.partial(Quiet, directory=str(www))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        yield www, f"http://127.0.0.1:{server.server_address[1]}/"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture(autouse=True)
def _no_real_mirror(monkeypatch):
    """Downloads fall back to the public mirror; keep tests off the network
    (port 9 on localhost refuses at once)."""
    import core
    monkeypatch.setattr(core, "ESE_MIRROR_BASE", "http://127.0.0.1:9/mirror/")
    monkeypatch.setattr(core, "_download_source", "ese")


def dispose_window(w):
    """Close a MainWindow and really destroy it. Parentless top-level widgets
    otherwise live for the whole session and every later app-wide style-sheet
    change (test_theme) has to restyle all of them."""
    from PySide6.QtCore import QCoreApplication, QEvent
    w._closing = True
    w.close()
    w.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


@pytest.fixture(autouse=True)
def _fast_retry_backoff(monkeypatch):
    """Retry backoff is real wall time (1s, 2s, ...); shrink it for tests."""
    import core
    monkeypatch.setattr(core, "RETRY_BACKOFF", 0.01)


@pytest.fixture(autouse=True)
def _sync_config_writes(request, monkeypatch):
    """The window debounces config writes (~300 ms); most tests read the file
    right after a change, so write through unless the test is about the
    debounce itself (mark it `real_debounce`)."""
    if request.node.get_closest_marker("real_debounce"):
        return
    try:
        import ese_qt
    except Exception:
        return
    orig = ese_qt.MainWindow.save_config

    def save_now(self):
        orig(self)
        self.flush_config()
    monkeypatch.setattr(ese_qt.MainWindow, "save_config", save_now)


def pytest_configure(config):
    config.addinivalue_line("markers", "real_debounce: keep the window's config-save debounce")
