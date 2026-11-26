"""find_updates/find_missing: persistent sha cache and single-walk scanning."""

import json
import os

import core


def make_lib(tmp_path, n=5):
    songs, shas = [], {}
    for i in range(n):
        rel = f"01 Pop/S{i}/S{i}.tja"
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        body = b"chart %d" % i
        p.write_bytes(body)
        shas[rel] = core.git_blob_sha_bytes(body if i else b"newer")
        songs.append({"id": i, "files": [{"file_path": rel, "filename": f"S{i}.tja"}]})
    return songs, shas


def patch(monkeypatch, songs, shas):
    monkeypatch.setattr(core, "search_songs", lambda *a, **k: songs)
    monkeypatch.setattr(core, "load_sha_map", lambda *a, **k: shas)
    core._sha_cache.clear()
    core._sha_forgotten.clear()


def test_disk_cache_written_and_reused(tmp_path, monkeypatch):
    songs, shas = make_lib(tmp_path)
    patch(monkeypatch, songs, shas)
    assert [s["id"] for s in core.find_updates(str(tmp_path))] == [0]
    cache = json.loads((tmp_path / core.SHA_CACHE_NAME).read_text())
    assert cache["v"] == core.SHA_CACHE_VERSION and len(cache["files"]) == 5
    assert not (tmp_path / (core.SHA_CACHE_NAME + ".tmp")).exists()

    calls = []
    real = core.git_blob_sha
    monkeypatch.setattr(core, "git_blob_sha", lambda p: calls.append(p) or real(p))
    assert [s["id"] for s in core.find_updates(str(tmp_path))] == [0]
    assert calls == []          # everything came from the disk cache


def test_modified_file_is_rehashed(tmp_path, monkeypatch):
    songs, shas = make_lib(tmp_path)
    patch(monkeypatch, songs, shas)
    core.find_updates(str(tmp_path))
    (tmp_path / "01 Pop/S0/S0.tja").write_bytes(b"newer")   # size changes
    assert core.find_updates(str(tmp_path)) == []


def test_forget_invalidates_disk_entry(tmp_path, monkeypatch):
    songs, shas = make_lib(tmp_path)
    patch(monkeypatch, songs, shas)
    core.find_updates(str(tmp_path))
    p = tmp_path / "01 Pop/S0/S0.tja"
    st = p.stat()
    p.write_bytes(b"newer!!")               # same size as b"chart 0"
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns))
    core.forget_blob_sha(str(p))
    shas["01 Pop/S0/S0.tja"] = core.git_blob_sha_bytes(b"newer!!")
    assert core.find_updates(str(tmp_path)) == []


def test_corrupt_or_old_cache_ignored(tmp_path, monkeypatch):
    songs, shas = make_lib(tmp_path)
    patch(monkeypatch, songs, shas)
    cp = tmp_path / core.SHA_CACHE_NAME
    for junk in ("{not json", json.dumps({"v": 999, "files": {}}), "[]"):
        cp.write_text(junk)
        assert [s["id"] for s in core.find_updates(str(tmp_path))] == [0]
    assert core.load_sha_disk_cache(str(tmp_path))      # rewritten valid


def test_progress_monotonic_and_ends_at_total(tmp_path, monkeypatch):
    songs, shas = make_lib(tmp_path, 20)
    patch(monkeypatch, songs, shas)
    seen = []
    core.find_updates(str(tmp_path), progress=lambda d, t: seen.append((d, t)))
    assert seen[0] == (0, 20) and seen[-1] == (20, 20)
    assert [d for d, _ in seen] == sorted(d for d, _ in seen)


def test_find_missing_walk_matches_exists(tmp_path):
    songs, _ = make_lib(tmp_path, 100)          # > 64 files: uses the scan path
    assert core.find_missing(songs, str(tmp_path)) == []
    os.remove(tmp_path / "01 Pop/S7/S7.tja")
    songs.append({"id": 999, "files": [{"file_path": "../evil.tja", "filename": "x"}]})
    assert [s["id"] for s in core.find_missing(songs, str(tmp_path))] == [7]
    assert len(core.find_missing(songs, str(tmp_path / "nope"))) == 100
