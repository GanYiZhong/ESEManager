"""Command-line mode, run as a subprocess from a throwaway copy of the app."""

import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def app(tmp_path):
    shutil.copytree(os.path.join(ROOT, "src"), tmp_path / "src",
                    ignore=shutil.ignore_patterns("__pycache__", "app_version.py"))

    def run(*args):
        env = dict(os.environ, PYTHONUTF8="1", QT_QPA_PLATFORM="offscreen")
        r = subprocess.run([sys.executable, str(tmp_path / "src" / "cli.py"), *args,
                            "--lang", "en"] if args and not args[0].startswith("--")
                           else [sys.executable, str(tmp_path / "src" / "cli.py"), *args],
                           capture_output=True, text=True, encoding="utf-8",
                           env=env, timeout=120)
        return r.returncode, r.stdout + r.stderr
    return tmp_path, run


def make_db(path):
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    from test_workers import make_song_db
    make_song_db(str(path), [("01 Pop/Song/Song.tja", "a" * 40),
                             ("01 Pop/Song/Song.ogg", "b" * 40)])


def test_version(app):
    tmp, run = app
    rc, out = run("--version")
    assert rc == 0 and "ESEManager dev" in out


def test_needs_database(app):
    tmp, run = app
    rc, out = run("search", "x")
    assert rc == 2 and "update-db" in out
    assert not (tmp / "ese_songs.db").exists()          # not created as a side effect


def test_search_missing_and_download_guard(app):
    tmp, run = app
    make_db(tmp / "ese_songs.db")
    rc, out = run("search", "Song")
    assert rc == 0 and "Song" in out and "1 songs" in out.replace("Total ", "")
    rc, out = run("missing")
    assert rc == 0 and "1 songs (2 files) missing" in out
    rc, out = run("download")
    assert rc == 2 and "--all" in out
    (tmp / "Downloads" / "01 Pop" / "Song").mkdir(parents=True)
    for name in ("Song.tja", "Song.ogg"):
        (tmp / "Downloads" / "01 Pop" / "Song" / name).write_bytes(b"x")
    rc, out = run("missing")
    assert rc == 0 and "Nothing missing" in out


def test_json_output_and_offline_status(app):
    import json
    tmp, run = app
    make_db(tmp / "ese_songs.db")
    env = dict(os.environ, PYTHONUTF8="1")
    r = subprocess.run([sys.executable, str(tmp / "src" / "cli.py"), "search", "Song",
                        "--json", "--lang", "en"], capture_output=True, text=True,
                       encoding="utf-8", env=env, timeout=120)
    assert r.returncode == 0
    rows = [json.loads(line) for line in r.stdout.splitlines()]
    assert rows == [{"song": "Song", "title_ja": None, "category": "01 Pop",
                     "files": ["01 Pop/Song/Song.ogg", "01 Pop/Song/Song.tja"]}]
    assert "1 songs" in r.stderr                       # messages stay off stdout
    r = subprocess.run([sys.executable, str(tmp / "src" / "cli.py"), "status", "--offline",
                        "--json"], capture_output=True, text=True, encoding="utf-8",
                       env=env, timeout=120)
    st = json.loads(r.stdout)
    assert r.returncode == 0 and st["songs"] == 1 and st["db_latest"] is None


def load_cli():
    sys.path.insert(0, os.path.join(ROOT, "src"))
    import cli
    return cli


def test_cjk_width_and_fit():
    cli = load_cli()
    assert cli.disp_width("abc") == 3 and cli.disp_width("千本桜") == 6
    assert cli.disp_width(cli.fit("千本桜", 10)) == 10
    cut = cli.fit("千本桜千本桜", 7)
    assert cut.endswith("…") and cli.disp_width(cut) == 7


def test_render_progress_fits_terminal():
    cli = load_cli()
    line = cli.render_progress(5, 10, 1.5, 12, 80)
    assert "50%" in line and "5/10" in line and line.startswith("[#####") is False \
        or "50%" in line
    assert len(line) <= 79
    narrow = cli.render_progress(5, 10, 1.5, 12, 30)
    assert len(narrow) <= 29 and "50%" in narrow
    assert "100%" in cli.render_progress(0, 0, 0, 0, 80)


def test_color_respects_no_color_and_tty(monkeypatch):
    cli = load_cli()

    class Tty:
        def isatty(self):
            return True
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert cli.paint("x", "31", Tty()) == "\033[31mx\033[0m"
    monkeypatch.setenv("NO_COLOR", "1")
    assert cli.paint("x", "31", Tty()) == "x"


def test_search_hint_quiet_and_no_match(app):
    tmp, run = app
    make_db(tmp / "ese_songs.db")
    rc, out = run("search", "Song")
    assert rc == 0 and 'ESEManager-cli download Song' in out
    assert "\033[" not in out                           # no colour when piped
    rc, out = run("search", "Song", "--quiet")
    assert rc == 0 and out.strip() == "Song"
    rc, out = run("search", "nothing-like-this", "-q")
    assert rc == 2 and "0 songs" in out                 # errors survive --quiet
    rc, out = run("search", "Song", "--json", "--quiet")
    assert rc == 0 and '"song": "Song"' in out
