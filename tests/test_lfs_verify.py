"""LFS audio verification: pointer parsing, DB migration/build from a git repo,
Downloader sha256/size checks and find_updates for audio."""

import hashlib
import os
import shutil
import sqlite3
import subprocess

import pytest

import core
import workers
from appconfig import parse_lfs_pointer
from ese_scraper_git_v2 import ESEScraperGitV2
from test_workers import env, make_song_db, put, run_download, song_files  # noqa: F401


def pointer(data):
    return (b"version https://git-lfs.github.com/spec/v1\n"
            b"oid sha256:" + hashlib.sha256(data).hexdigest().encode() + b"\n"
            b"size %d\n" % len(data))


def test_parse_lfs_pointer():
    audio = b"OggS" * 100
    assert parse_lfs_pointer(pointer(audio)) == (hashlib.sha256(audio).hexdigest(), 400)
    assert parse_lfs_pointer(b"OggS" + b"\0" * 50) is None
    assert parse_lfs_pointer(b"") is None
    assert parse_lfs_pointer(b"version https://git-lfs.github.com/spec/v1\noid sha256:zz\nsize 1\n") is None
    assert parse_lfs_pointer(b"version https://git-lfs.github.com/spec/v1\nsize 1\n") is None


def set_lfs(path, fp, data):
    conn = sqlite3.connect(str(path))
    if "lfs_sha256" not in {r[1] for r in conn.execute("PRAGMA table_info(song_files)")}:
        conn.execute("ALTER TABLE song_files ADD COLUMN lfs_sha256 TEXT")
        conn.execute("ALTER TABLE song_files ADD COLUMN lfs_size INTEGER")
    conn.execute("UPDATE song_files SET lfs_sha256=?, lfs_size=? WHERE file_path=?",
                 (hashlib.sha256(data).hexdigest(), len(data), fp))
    conn.commit()
    conn.close()


OGG = "01 Pop/Song/Song.ogg"


def test_migration_adds_columns_and_old_db_reads_empty(tmp_path):
    old = tmp_path / "old.db"
    conn = sqlite3.connect(str(old))
    conn.execute("CREATE TABLE song_files (id INTEGER PRIMARY KEY, song_id INTEGER, "
                 "filename TEXT, file_path TEXT UNIQUE, file_type TEXT, size INTEGER, "
                 "download_url TEXT)")
    conn.commit()
    conn.close()
    assert core.load_lfs_map(str(old)) == {}            # no columns: still readable
    s = ESEScraperGitV2(db_path=str(old), clone_dir="unused", git_exe="git")
    s.init_database()
    s.close()
    cols = {r[1] for r in sqlite3.connect(str(old)).execute("PRAGMA table_info(song_files)")}
    assert {"blob_sha", "lfs_sha256", "lfs_size"} <= cols
    assert core.load_lfs_map(str(old)) == {}            # NULL values


def test_download_accepts_matching_sha256(env):
    www, tmp, dl = env
    ogg = b"OggS" + b"\1" * 5000
    put(www, OGG, ogg)
    make_song_db(core.DB_PATH, [(OGG, "0" * 40)])
    set_lfs(core.DB_PATH, OGG, ogg)
    t, res = run_download(song_files([OGG]), dl)
    assert res["d"] == 1 and res["f"] == 0
    assert (dl / OGG).read_bytes() == ogg


def test_download_rejects_stale_audio(env):
    www, tmp, dl = env
    good = b"OggS" + b"\1" * 5000
    put(www, OGG, b"OggS" + b"\2" * 5000)               # same size, other content
    make_song_db(core.DB_PATH, [(OGG, "0" * 40)])
    set_lfs(core.DB_PATH, OGG, good)
    t, res = run_download(song_files([OGG]), dl)
    assert res["f"] == 1 and res["d"] == 0
    assert not (dl / OGG).exists() and not list(dl.rglob("*.part"))


def test_download_rejects_wrong_length(env):
    www, tmp, dl = env
    good = b"OggS" + b"\1" * 5000
    put(www, OGG, good + b"extra")
    make_song_db(core.DB_PATH, [(OGG, "0" * 40)])
    set_lfs(core.DB_PATH, OGG, good)
    t, res = run_download(song_files([OGG]), dl)
    assert res["f"] == 1 and not (dl / OGG).exists()


def test_download_without_lfs_columns_or_null_still_works(env):
    www, tmp, dl = env
    ogg = b"OggS" + b"\3" * 100
    put(www, OGG, ogg)
    make_song_db(core.DB_PATH, [(OGG, "0" * 40)])        # NULL lfs columns
    t, res = run_download(song_files([OGG]), dl)
    assert res["d"] == 1 and (dl / OGG).read_bytes() == ogg


def test_resumed_download_hashes_kept_prefix(env, tmp_path):
    www, tmp, dl = env
    ogg = b"OggS" + bytes(range(256)) * 40
    put(www, OGG, ogg)
    make_song_db(core.DB_PATH, [(OGG, "0" * 40)])
    set_lfs(core.DB_PATH, OGG, ogg)
    part = dl / (OGG + ".part")
    part.parent.mkdir(parents=True)
    part.write_bytes(ogg[:3000])
    t2, res = run_download(song_files([OGG]), dl)
    assert res["d"] == 1 and (dl / OGG).read_bytes() == ogg


def test_find_updates_flags_changed_audio(tmp_path, monkeypatch):
    new = b"OggS" + b"\5" * 1000
    p = tmp_path / OGG
    p.parent.mkdir(parents=True)
    p.write_bytes(b"OggS" + b"\6" * 1000)                # same size, other content
    songs = [{"id": 1, "files": [{"file_path": OGG, "filename": "Song.ogg"}]}]
    monkeypatch.setattr(core, "search_songs", lambda *a, **k: songs)
    monkeypatch.setattr(core, "load_sha_map", lambda *a, **k: {"x": "y"})
    lfs = {OGG: (hashlib.sha256(new).hexdigest(), len(new))}
    monkeypatch.setattr(core, "load_lfs_map", lambda *a, **k: lfs)
    core._sha_cache.clear()
    core._sha_forgotten.clear()
    assert [s["id"] for s in core.find_updates(str(tmp_path))] == [1]
    # second run: sha256 comes from the disk cache, no re-hash
    calls = []
    monkeypatch.setattr(core, "file_sha256", lambda p: calls.append(p) or "")
    assert [s["id"] for s in core.find_updates(str(tmp_path))] == [1]
    assert calls == []
    # different length is flagged without hashing; matching file is clean
    lfs[OGG] = (lfs[OGG][0], 5)
    assert [s["id"] for s in core.find_updates(str(tmp_path))] == [1]
    p.write_bytes(new)
    lfs[OGG] = (hashlib.sha256(new).hexdigest(), len(new))
    monkeypatch.undo()
    monkeypatch.setattr(core, "search_songs", lambda *a, **k: songs)
    monkeypatch.setattr(core, "load_sha_map", lambda *a, **k: {"x": "y"})
    monkeypatch.setattr(core, "load_lfs_map", lambda *a, **k: lfs)
    assert core.find_updates(str(tmp_path)) == []


@pytest.mark.skipif(not shutil.which("git"), reason="git not installed")
def test_scraper_records_pointers_from_git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    audio = b"OggS" + b"\7" * 777

    def git(*a):
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t",
                        *a], check=True, capture_output=True)

    git("init", "-q", "-b", "master")
    (repo / "01 Pop" / "Song").mkdir(parents=True)
    (repo / "01 Pop/Song/Song.tja").write_bytes(b"TITLE:x\n")
    (repo / "01 Pop/Song/Song.ogg").write_bytes(pointer(audio))
    git("add", "-A")
    git("commit", "-q", "-m", "one")

    s = ESEScraperGitV2(db_path=str(tmp_path / "s.db"), clone_dir=str(repo), git_exe="git")
    s.init_database()
    s.build_from_git_tree()
    s.conn.commit()
    s.close()
    m = core.load_lfs_map(str(tmp_path / "s.db"))
    assert m == {OGG: (hashlib.sha256(audio).hexdigest(), len(audio))}

    # audio replaced upstream: the pointer is re-read on the next build
    audio2 = b"OggS" + bytes([8]) * 10
    (repo / "01 Pop/Song/Song.ogg").write_bytes(pointer(audio2))
    git("commit", "-q", "-am", "two")
    s = ESEScraperGitV2(db_path=str(tmp_path / "s.db"), clone_dir=str(repo), git_exe="git")
    s.init_database()
    s.build_from_git_tree()
    s.conn.commit()
    s.close()
    assert core.load_lfs_map(str(tmp_path / "s.db")) == {
        OGG: (hashlib.sha256(audio2).hexdigest(), len(audio2))}
