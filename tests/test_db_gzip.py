import gzip
import hashlib
import json
import os
import sqlite3

import pytest

import core
import build_pages_db


def make_db(path, rows=2000):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (a TEXT)")
    conn.executemany("INSERT INTO t VALUES (?)", [("row %d" % i,) for i in range(rows)])
    conn.commit()
    conn.close()
    with open(path, "rb") as f:
        return f.read()


def sha(b):
    return hashlib.sha256(b).hexdigest()


@pytest.fixture
def env(tmp_path, http_dir, monkeypatch):
    www, base = http_dir
    monkeypatch.setattr(core, "DB_RELEASE_URL", base)
    monkeypatch.setattr(core, "DB_PATH", str(tmp_path / "ese_songs.db"))
    monkeypatch.setattr(core, "LOCAL_DB_PATH", str(tmp_path / "ese_local.db"))
    monkeypatch.setattr(core, "VERSION_FILE", str(tmp_path / "version.txt"))
    return www, tmp_path


def publish(www, tmp, gz=True, bad_gz_sha=False, bomb=False, plain_ok=True):
    files = {}
    for name in core.DB_NAMES:
        raw = make_db(str(tmp / ("src_" + name)))
        (www / name).write_bytes(raw if plain_ok else b"garbage")
        info = {"size": len(raw), "sha256": sha(raw)}
        if gz:
            payload = gzip.compress(b"\0" * (3 << 20), 9) if bomb else gzip.compress(raw, 9)
            (www / (name + ".gz")).write_bytes(payload)
            info["gz"] = {"name": name + ".gz", "size": len(payload),
                          "sha256": "0" * 64 if bad_gz_sha else sha(payload)}
        files[name] = info
    (www / "manifest.json").write_text(json.dumps({"version": "v1", "files": files}))
    return files


def tr(key, **kw):
    return key


def test_gz_preferred(env):
    www, tmp = env
    publish(www, tmp, plain_ok=False)      # plain copy is broken: only the .gz can succeed
    logs = []
    assert core.update_databases("", log=logs.append, tr=tr) == "v1"
    assert any(".gz" in m and "MB" in m for m in logs)
    assert open(core.DB_PATH, "rb").read() == open(tmp / "src_ese_songs.db", "rb").read()


def test_bad_gz_sha_falls_back_to_plain(env):
    www, tmp = env
    publish(www, tmp, bad_gz_sha=True)
    assert core.update_databases("", log=lambda m: None, tr=tr) == "v1"
    assert os.path.exists(core.LOCAL_DB_PATH)
    assert not [p for p in os.listdir(tmp) if p.endswith((".part", ".gz"))]


def test_oversized_decompression_rejected(env, monkeypatch):
    www, tmp = env
    files = publish(www, tmp, bomb=True)
    monkeypatch.setattr(core, "MAX_DB_BYTES", 1 << 20)
    # the bomb's own plain sha is irrelevant: the size cap must trip first
    with pytest.raises(ValueError):
        core._download_db_gz(core.new_session(), files["ese_songs.db"]["gz"], "x",
                             str(tmp / "p.part"), lambda m: None)
    assert not os.path.exists(tmp / "p.part")
    # end to end: bomb is rejected, plain fallback still installs
    assert core.update_databases("", log=lambda m: None, tr=tr) == "v1"


def test_old_manifest_without_gz(env):
    www, tmp = env
    publish(www, tmp, gz=False)
    assert core.update_databases("", log=lambda m: None, tr=tr) == "v1"


def test_build_script_gzip_deterministic(tmp_path):
    src = tmp_path / "a.db"
    make_db(str(src))
    a, b = tmp_path / "a.gz", tmp_path / "b.gz"
    build_pages_db.write_gzip(str(src), str(a))
    build_pages_db.write_gzip(str(src), str(b))
    assert a.read_bytes() == b.read_bytes()
    assert gzip.decompress(a.read_bytes()) == src.read_bytes()
    assert a.read_bytes()[4:8] == b"\0\0\0\0"          # mtime 0
    assert a.read_bytes()[3] == 0                      # no FNAME flag
