"""Worker-thread tests against a local HTTP server (runs the threads' run()
synchronously, so no event loop is needed)."""

import hashlib
import json
import os
import sqlite3

import pytest

import core
import workers
from appconfig import SQLITE_MAGIC
from ese_scraper_git_v2 import ESEScraperGitV2


def blob_sha(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def make_song_db(path, files):
    """files: list of (file_path, blob_sha) for one song in category '01 Pop'."""
    s = ESEScraperGitV2(db_path=str(path), clone_dir="unused", git_exe="git")
    s.init_database()
    s.close()
    conn = sqlite3.connect(str(path))
    conn.execute("INSERT INTO categories(id, name, path) VALUES (1, '01 Pop', '01 Pop')")
    conn.execute("INSERT INTO songs(id, category_id, song_name, base_path) "
                 "VALUES (1, 1, 'Song', '01 Pop/Song')")
    for fp, sha in files:
        conn.execute("INSERT INTO song_files(song_id, filename, file_path, file_type, size, "
                     "download_url, blob_sha) VALUES (1, ?, ?, ?, 0, '', ?)",
                     (fp.split("/")[-1], fp, os.path.splitext(fp)[1], sha))
    conn.commit()
    conn.close()


def song_files(fps):
    song = {"song_name": "Song", "category": "01 Pop", "files": []}
    for fp in fps:
        song["files"].append({"filename": fp.split("/")[-1], "file_path": fp,
                              "download_url": "", "size": 0})
    return [(song, f) for f in song["files"]]


@pytest.fixture
def env(tmp_path, http_dir, monkeypatch, qapp):
    www, base = http_dir
    monkeypatch.setattr(core, "ESE_RAW_BASE", base)
    monkeypatch.setattr(core, "DB_RELEASE_URL", base)
    monkeypatch.setattr(core, "DB_PATH", str(tmp_path / "ese_songs.db"))
    monkeypatch.setattr(core, "LOCAL_DB_PATH", str(tmp_path / "ese_local.db"))
    monkeypatch.setattr(core, "VERSION_FILE", str(tmp_path / "version.txt"))
    dl = tmp_path / "Downloads"
    dl.mkdir()
    return www, tmp_path, dl


def put(www, rel, data):
    p = www.joinpath(*rel.split("/"))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)


def run_download(files, dl, **kw):
    t = workers.DownloadThread(files, str(dl), 2, **kw)
    result = {}
    t.finished_all.connect(lambda d, s, f, n: result.update(d=d, s=s, f=f, n=n))
    t.run()
    return t, result


# ---------------------------------------------------------------- downloads
def test_download_verifies_and_writes_atomically(env):
    www, tmp, dl = env
    tja = "TITLE:Song\n".encode()
    ogg = b"OggS" + b"\0" * 5000
    put(www, "01 Pop/Song/Song.tja", tja)
    put(www, "01 Pop/Song/Song.ogg", ogg)
    # The .ogg sha is the LFS pointer's, so it must not be compared.
    make_song_db(core.DB_PATH, [("01 Pop/Song/Song.tja", blob_sha(tja)),
                                   ("01 Pop/Song/Song.ogg", "0" * 40)])
    t, res = run_download(song_files(["01 Pop/Song/Song.tja", "01 Pop/Song/Song.ogg"]), dl)
    assert res == {"d": 2, "s": 0, "f": 0, "n": 2}
    assert (dl / "01 Pop/Song/Song.tja").read_bytes() == tja
    assert (dl / "01 Pop/Song/Song.ogg").read_bytes() == ogg
    assert not list(dl.rglob("*.part"))


def test_download_rejects_checksum_mismatch_and_keeps_old_file(env):
    www, tmp, dl = env
    put(www, "01 Pop/Song/Song.tja", b"tampered")
    make_song_db(core.DB_PATH, [("01 Pop/Song/Song.tja", blob_sha(b"expected"))])
    target = dl / "01 Pop/Song/Song.tja"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"old good copy")
    t, res = run_download(song_files(["01 Pop/Song/Song.tja"]), dl, overwrite=True)
    assert res["f"] == 1 and res["d"] == 0
    assert target.read_bytes() == b"old good copy"     # not truncated or deleted
    assert not list(dl.rglob("*.part"))


def test_download_refuses_path_traversal(env):
    www, tmp, dl = env
    put(www, "x.tja", b"x")
    make_song_db(core.DB_PATH, [])
    t, res = run_download(song_files(["../escape.tja"]), dl)
    assert res["f"] == 1
    assert not (tmp / "escape.tja").exists()


def test_download_skips_existing_and_reports_404(env):
    www, tmp, dl = env
    make_song_db(core.DB_PATH, [])
    (dl / "01 Pop/Song").mkdir(parents=True)
    (dl / "01 Pop/Song/Have.tja").write_bytes(b"x")
    t, res = run_download(song_files(["01 Pop/Song/Have.tja", "01 Pop/Song/Missing.tja"]), dl)
    assert res == {"d": 0, "s": 1, "f": 1, "n": 2}
    assert [f["file_path"] for _, f in t.failed] == ["01 Pop/Song/Missing.tja"]


def test_stop_before_start_downloads_nothing(env):
    www, tmp, dl = env
    put(www, "01 Pop/Song/Song.tja", b"x")
    make_song_db(core.DB_PATH, [])
    t = workers.DownloadThread(song_files(["01 Pop/Song/Song.tja"]), str(dl), 1)
    t.stop()
    t.run()
    assert t.stopped and not (dl / "01 Pop/Song/Song.tja").exists()


# ---------------------------------------------------------------- update check
def test_check_updates_ignores_lfs_audio(env):
    www, tmp, dl = env
    tja_old, tja_new = b"old chart", b"new chart"
    make_song_db(core.DB_PATH, [("01 Pop/Song/Song.tja", blob_sha(tja_new)),
                                   ("01 Pop/Song/Song.ogg", "f" * 40)])
    (dl / "01 Pop/Song").mkdir(parents=True)
    (dl / "01 Pop/Song/Song.tja").write_bytes(tja_old)
    (dl / "01 Pop/Song/Song.ogg").write_bytes(b"audio")
    t = workers.CheckUpdatesThread(str(dl))
    out = {}
    t.done.connect(lambda songs: out.setdefault("songs", songs))
    t.fail.connect(lambda e: out.setdefault("err", e))
    t.run()
    assert "err" not in out
    [song] = out["songs"]
    # The chart changed; its audio is re-fetched with it.
    assert sorted(f["filename"] for f in song["files"]) == ["Song.ogg", "Song.tja"]

    # Up-to-date chart: nothing to update, even though the .ogg "sha" differs.
    (dl / "01 Pop/Song/Song.tja").write_bytes(tja_new)
    # Same size, and Windows may give the same mtime: simulate the app having
    # replaced the file (the downloader drops the cached hash).
    core.forget_blob_sha(str(dl / "01 Pop/Song/Song.tja"))
    out.clear()
    t.run()
    assert out["songs"] == []


# ---------------------------------------------------------------- prebuilt DB update
def make_sqlite(path, marker):
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE t(x)")
    conn.execute("INSERT INTO t VALUES (?)", (marker,))
    conn.commit()
    conn.close()
    return path.read_bytes()


def publish(www, tmp, version="v2", corrupt=None):
    """Publish both DBs + manifest; `corrupt` serves damaged bytes for that file
    while the manifest keeps the good checksum."""
    files = {}
    for name in core.DB_NAMES:
        good = make_sqlite(tmp / f"src_{version}_{name}", f"{name}-{version}")
        served = good[:-10] + b"x" * 10 if corrupt == name else good
        put(www, name, served)
        files[name] = {"size": len(good), "sha256": hashlib.sha256(good).hexdigest()}
    put(www, "manifest.json", json.dumps({"version": version, "files": files}).encode())
    put(www, "version.txt", version.encode())


def run_update(version):
    t = workers.DBUpdateThread(version)
    out = {}
    t.done.connect(lambda ok, msg: out.update(ok=ok, msg=msg))
    t.run()
    return out


def installed(tmp, name):
    conn = sqlite3.connect(str(tmp / name))
    try:
        return conn.execute("SELECT x FROM t").fetchone()[0]
    finally:
        conn.close()


def test_db_update_success(env):
    www, tmp, dl = env
    publish(www, tmp, "v2")
    assert run_update("v2") == {"ok": True, "msg": "ok"}
    assert installed(tmp, "ese_songs.db") == "ese_songs.db-v2"
    assert installed(tmp, "ese_local.db") == "ese_local.db-v2"
    assert (tmp / "version.txt").read_text() == "v2"
    assert not list(tmp.glob("*.part")) and not list(tmp.glob("*.bak"))


def test_db_update_rejects_bad_checksum_and_keeps_old(env):
    www, tmp, dl = env
    publish(www, tmp, "v1")
    assert run_update("v1")["ok"]
    publish(www, tmp, "v2", corrupt="ese_local.db")
    out = run_update("v2")
    assert out["ok"] is False
    assert installed(tmp, "ese_songs.db") == "ese_songs.db-v1"     # untouched
    assert installed(tmp, "ese_local.db") == "ese_local.db-v1"
    assert (tmp / "version.txt").read_text() == "v1"
    assert not list(tmp.glob("*.part"))


def test_db_update_requires_manifest(env):
    www, tmp, dl = env
    for name in core.DB_NAMES:
        put(www, name, SQLITE_MAGIC + b"\0" * 100)
    out = run_update("v9")
    assert out["ok"] is False
    assert not (tmp / "ese_songs.db").exists()


def test_version_check(env, monkeypatch):
    www, tmp, dl = env
    put(www, "version.txt", b"20261118-0000-abcdef0\n")
    (tmp / "version.txt").write_text("old")
    t = workers.VersionThread()
    out = []
    t.result.connect(lambda r, l: out.append((r, l)))
    t.run()
    assert out == [("20261118-0000-abcdef0", "old")]
    put(www, "version.txt", b"<html>moved</html>")
    out.clear()
    t.run()
    assert out == [("", "old")]


# ---------------------------------------------------------------- metadata maps
def test_load_maps(tmp_path):
    import build_local_db
    db = build_local_db.LocalTJADatabase(db_path=str(tmp_path / "l.db"))
    db.init_database()
    db.insert_song({"file_path": "01 Pop/A/A.tja", "file_name": "A.tja", "directory": "x",
                    "title": "A title", "titleja": "エー", "bpm": "120", "level_oni": 8})
    db.conn.commit()
    db.close()
    jp = core.load_jp_map(str(tmp_path / "l.db"))
    meta = core.load_meta_map(str(tmp_path / "l.db"))
    assert jp["A"] == "エー" and jp["A title"] == "エー"
    assert meta["A"]["bpm"] == "120" and meta["A"]["level_oni"] == 8
    assert core.load_jp_map(str(tmp_path / "missing.db")) == {}
