"""core.py: the Qt-free logic shared by the GUI and the command line."""

import sqlite3
import time

import pytest
import requests

import core
from appconfig import SQLITE_MAGIC
from test_workers import make_song_db


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "DB_PATH", str(tmp_path / "ese_songs.db"))
    monkeypatch.setattr(core, "LOCAL_DB_PATH", str(tmp_path / "ese_local.db"))
    make_song_db(core.DB_PATH, [("01 Pop/Song/Song.tja", "a" * 40),
                                ("01 Pop/Song/Song.ogg", "b" * 40),
                                ("01 Pop/box.def", "c" * 40)])
    return tmp_path


def test_categories_count_and_search_drop_box_def(db):
    assert core.list_categories() == ["01 Pop"]
    assert core.count_songs() == 1
    songs = core.search_songs("song")
    assert [f["filename"] for f in songs[0]["files"]] == ["Song.ogg", "Song.tja"]


def test_qt_free():
    """The command line must not need Qt."""
    import ast
    import pathlib
    src = pathlib.Path(core.__file__).read_text(encoding="utf-8")
    names = {n.module or "" for n in ast.walk(ast.parse(src)) if isinstance(n, ast.ImportFrom)}
    names |= {a.name for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Import)
              for a in n.names}
    assert not any(n.startswith("PySide6") for n in names)


def test_japanese_search_with_many_titles(db):
    """More matching titles than SQLite allows as query parameters."""
    conn = sqlite3.connect(core.LOCAL_DB_PATH)
    conn.execute("CREATE TABLE local_songs (title TEXT, file_name TEXT, title_ja TEXT)")
    conn.executemany("INSERT INTO local_songs VALUES (?, ?, ?)",
                     [(f"Other {i}", "", "千本桜") for i in range(40000)] + [("Song", "", "千本桜")])
    conn.commit()
    conn.close()
    assert [s["song_name"] for s in core.search_songs("千本")] == ["Song"]


def test_find_missing(db, tmp_path):
    songs = core.search_songs("")
    dl = tmp_path / "dl"
    assert len(core.find_missing(songs, str(dl))) == 1
    (dl / "01 Pop/Song").mkdir(parents=True)
    for n in ("Song.tja", "Song.ogg"):
        (dl / "01 Pop/Song" / n).write_bytes(b"x")
    assert core.find_missing(songs, str(dl)) == []


def test_sqlite_ok_rejects_damaged_file(tmp_path):
    good = tmp_path / "good.db"
    conn = sqlite3.connect(good)
    conn.execute("CREATE TABLE t (x)")
    conn.commit()
    conn.close()
    assert core.sqlite_ok(str(good))
    bad = tmp_path / "bad.db"
    bad.write_bytes(SQLITE_MAGIC + b"\xff" * 4000)
    assert not core.sqlite_ok(str(bad))
    assert not core.sqlite_ok(str(tmp_path / "missing.db"))
    assert not (tmp_path / "missing.db").exists()


def test_retry_backoff_stops_quickly(monkeypatch):
    class Sess:
        def get(self, *a, **k):
            raise requests.ConnectionError("down")
    t0 = time.monotonic()
    calls = {"n": 0}

    def stop():
        calls["n"] += 1
        return calls["n"] > 2          # cancel during the first backoff
    with pytest.raises(requests.ConnectionError):
        core.get_with_retry(Sess(), "http://x", attempts=5, stop=stop)
    assert time.monotonic() - t0 < 0.9


def test_downloader_runs_without_qt(db, tmp_path, http_dir):
    www, base = http_dir
    (www / "01 Pop/Song").mkdir(parents=True)
    (www / "01 Pop/Song/Song.tja").write_bytes(b"x")
    conn = sqlite3.connect(core.DB_PATH)       # make the recorded sha match
    conn.execute("UPDATE song_files SET blob_sha=? WHERE filename='Song.tja'",
                 (core.git_blob_sha_bytes(b"x"),))
    conn.commit()
    conn.close()
    core_files = [({"song_name": "Song"}, {"filename": "Song.tja",
                                           "file_path": "01 Pop/Song/Song.tja",
                                           "download_url": base + "01 Pop/Song/Song.tja"})]
    logs = []
    job = core.Downloader(core_files, str(tmp_path / "dl"), 1, log=logs.append)
    assert job.run() == (1, 0, 0, 1)
    assert (tmp_path / "dl/01 Pop/Song/Song.tja").read_bytes() == b"x"
    assert any("Song.tja" in m for m in logs)
