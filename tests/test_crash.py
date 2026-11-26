"""Crash reporter: hooks, dedupe/rate limit, scrubbing, CLI, marker lifecycle."""

import os
import shutil
import subprocess
import sys
import threading
import urllib.parse

import pytest

import crash
import i18n

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def clean(tmp_path, monkeypatch):
    """Hooks restored, state reset, marker/log redirected to tmp_path."""
    saved = (sys.excepthook, threading.excepthook)
    monkeypatch.setattr(crash, "APP_DIR", str(tmp_path))
    crash.reset()
    yield
    sys.excepthook, threading.excepthook = saved
    crash._state["prev_hooks"] = None
    crash.reset()


def boom(exc=ValueError("bad"), line=None):
    try:
        raise exc
    except BaseException as e:
        return type(e), e, e.__traceback__


# ------------------------------------------------------------------ hooks
def test_install_and_uninstall_restore_hooks():
    s0, t0 = sys.excepthook, threading.excepthook
    crash.install()
    assert sys.excepthook is crash._sys_hook
    assert threading.excepthook is crash._thread_hook
    crash.install()          # idempotent: still restores the originals
    crash.uninstall()
    assert (sys.excepthook, threading.excepthook) == (s0, t0)


def test_sys_hook_logs_and_presents_when_ready(qapp, monkeypatch):
    shown = []
    monkeypatch.setattr(crash, "_show", lambda d, modal: shown.append((d, modal)))
    crash.install()
    crash.set_ready(True, lang="en")
    sys.excepthook(*boom())
    assert len(shown) == 1 and shown[0][1] is False
    dlg = shown[0][0]
    assert dlg.continue_button.isDefault()
    assert dlg.quit_button is not None


def test_thread_hook_marshals_to_gui_thread(qapp, monkeypatch):
    shown = []
    monkeypatch.setattr(crash, "_show", lambda d, modal: shown.append(d))
    crash.install()
    crash.set_ready(True, lang="en")

    def work():
        raise RuntimeError("in thread")
    t = threading.Thread(target=work)
    t.start()
    t.join()
    assert shown == []                       # queued, not shown from the worker
    qapp.processEvents()
    assert len(shown) == 1


def test_startup_error_is_fatal_with_marker(qapp, monkeypatch):
    calls = {}
    monkeypatch.setattr(crash, "_show", lambda d, modal: calls.update(modal=modal, cont=d.continue_button))
    monkeypatch.setattr(crash, "_terminate", lambda code: calls.update(code=code))
    crash.install()
    sys.excepthook(*boom())
    assert calls == {"modal": True, "cont": None, "code": 1}
    assert os.path.exists(crash.marker_path())


def test_fatal_works_without_qapplication(monkeypatch):
    """_ensure_app creates a QApplication when none exists."""
    made = []
    monkeypatch.setattr(crash, "_ensure_app", lambda: made.append(1))
    monkeypatch.setattr(crash, "_build_dialog", lambda *a, **k: object())
    monkeypatch.setattr(crash, "_show", lambda d, modal: None)
    monkeypatch.setattr(crash, "_terminate", lambda code: None)
    crash.fatal(*boom())
    assert made == [1]


def test_keyboard_interrupt_ignored(monkeypatch):
    monkeypatch.setattr(crash, "_terminate", lambda c: pytest.fail("terminated"))
    crash.install()
    crash.handle(*boom(KeyboardInterrupt()))


# ------------------------------------------------------------------ dedupe / rate limit
def test_dedupe_same_type_and_frame(qapp, monkeypatch):
    shown = []
    monkeypatch.setattr(crash, "_show", lambda d, modal: shown.append(d))
    crash.set_ready(True, lang="en")
    for _ in range(5):
        crash.handle(*boom())
        crash._state["open"] = None          # as if the user dismissed it
    assert len(shown) == 1
    crash._state["open"] = None
    crash.handle(*boom(KeyError("other")))   # different type -> new dialog
    assert len(shown) == 2


def test_rate_limit():
    ok = [crash._rate_ok(now=100 + i) for i in range(crash.RATE_MAX + 2)]
    assert ok == [True] * crash.RATE_MAX + [False, False]
    assert crash._rate_ok(now=100 + crash.RATE_WINDOW + 5)


def test_one_dialog_at_a_time(qapp, monkeypatch):
    shown = []
    monkeypatch.setattr(crash, "_show", lambda d, modal: shown.append(d))
    crash.set_ready(True, lang="en")
    crash.handle(*boom(ValueError("a")))
    crash.handle(*boom(KeyError("b")))       # first still open
    assert len(shown) == 1


# ------------------------------------------------------------------ privacy
def test_scrub_home_user_and_email():
    home = os.path.expanduser("~")
    user = os.path.basename(home)
    text = f'File "{home}\\Docs\\x.py"\n{home.replace(chr(92), "/")}/a\nC:\\Users\\{user}\\z\\f contact me@example.com'
    out = crash.scrub(text)
    assert home not in out and home.replace("\\", "/") not in out
    assert "~" in out and "<email>" in out and "me@example.com" not in out
    assert f"\\{user}\\" not in out


def test_report_is_scrubbed(monkeypatch):
    home = os.path.expanduser("~")
    exc = ValueError(f"cannot open {home}\\secret.txt for a@b.co")
    rep = crash.format_report(*boom(exc))
    assert home not in rep and "a@b.co" not in rep
    assert "ESEManager" in rep and "Python:" in rep


def test_issue_url_has_title_only():
    et, e, tb = boom(ValueError("secret detail " + os.path.expanduser("~")))
    url = crash.issue_url(et, tb)
    q = urllib.parse.urlparse(url)
    assert q.path.endswith("/issues/new")
    params = urllib.parse.parse_qs(q.query)
    assert list(params) == ["title"]
    assert "secret" not in url and os.path.basename(os.path.expanduser("~")) not in url
    assert params["title"][0].startswith("Crash: ValueError in ")


def test_dialog_buttons_copy_and_report(qapp, monkeypatch):
    opened = []
    monkeypatch.setattr(crash, "_open_url", opened.append)
    monkeypatch.setattr(crash, "_open_log_folder", lambda: opened.append("log"))
    crash.set_ready(True, lang="en")
    dlg = crash._build_dialog(*boom(), fatal=False)
    dlg.copy_button.click()
    from PySide6.QtGui import QGuiApplication
    assert "ValueError" in QGuiApplication.clipboard().text()
    dlg.log_button.click()
    dlg.report_button.click()
    assert opened[0] == "log" and "issues/new" in opened[1]


# ------------------------------------------------------------------ marker
def test_marker_lifecycle():
    assert not crash.consume_marker()
    crash.write_marker("x")
    assert os.path.exists(crash.marker_path())
    assert crash.consume_marker()
    assert not os.path.exists(crash.marker_path())
    crash.write_marker()
    crash.clear_marker()
    crash.clear_marker()                     # no error when absent
    assert not crash.consume_marker()


def test_offer_previous_crash_nonblocking(qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "open", lambda self: None)
    crash.set_ready(True, lang="en")
    box = crash.offer_previous_crash()
    assert "unexpectedly" in box.text()


# ------------------------------------------------------------------ i18n
def test_all_languages_have_crash_keys():
    keys = [k for k in i18n.TR["en"] if k.startswith("crash_")]
    assert len(keys) >= 10
    for lang in ("zh_TW", "ja"):
        assert [k for k in keys if k not in i18n.TR[lang]] == []


# ------------------------------------------------------------------ CLI
def test_cli_fail_friendly_and_debug(monkeypatch, capsys):
    import io
    crash.set_ready(lang="en")
    monkeypatch.delenv("ESEMANAGER_DEBUG", raising=False)
    et, e, tb = boom(RuntimeError("kaput"))
    buf = io.StringIO()
    assert crash.cli_fail(e, argv=[], stream=buf) == 1
    out = buf.getvalue()
    assert out.count("\n") == 1 and "kaput" in out and "ESEManager.log" in out
    assert "Traceback" not in out
    buf = io.StringIO()
    crash.cli_fail(e, argv=["--debug"], stream=buf)
    assert "Traceback" in buf.getvalue()
    monkeypatch.setenv("ESEMANAGER_DEBUG", "1")
    buf = io.StringIO()
    crash.cli_fail(e, argv=[], stream=buf)
    assert "Traceback" in buf.getvalue()


@pytest.fixture
def cli_app(tmp_path):
    shutil.copytree(os.path.join(ROOT, "src"), tmp_path / "src",
                    ignore=shutil.ignore_patterns("__pycache__", "app_version.py"))
    # make a command blow up unexpectedly
    cli = tmp_path / "src" / "cli.py"
    cli.write_text(cli.read_text(encoding="utf-8").replace(
        "    args = build_parser().parse_args(argv)",
        "    args = build_parser().parse_args(argv)\n    raise RuntimeError('simulated failure')", 1),
        encoding="utf-8")

    def run(*args, **env):
        e = dict(os.environ, PYTHONUTF8="1", QT_QPA_PLATFORM="offscreen", **env)
        e.pop("ESEMANAGER_DEBUG", None) if "ESEMANAGER_DEBUG" not in env else None
        return subprocess.run([sys.executable, str(cli), *args], capture_output=True,
                              text=True, encoding="utf-8", env=e, timeout=120)
    return run


def test_cli_exits_1_with_one_line(cli_app):
    r = cli_app("status", "--lang", "en")
    assert r.returncode == 1
    assert "Traceback" not in r.stderr and "simulated failure" in r.stderr
    assert len(r.stderr.strip().splitlines()) == 1


def test_cli_debug_shows_traceback(cli_app):
    assert "Traceback" in cli_app("status", "--lang", "en", "--debug").stderr
    assert "Traceback" in cli_app("status", "--lang", "en", ESEMANAGER_DEBUG="1").stderr
