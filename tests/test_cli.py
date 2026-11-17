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
