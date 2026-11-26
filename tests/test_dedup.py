"""Identical LFS audio (same sha256) is fetched once and copied afterwards."""

import http.server

import core
from test_lfs_verify import set_lfs
from test_workers import env, make_song_db, put, run_download, song_files  # noqa: F401

A = "01 Pop/Song/New Audio/a.ogg"
B = "01 Pop/Song/Old Audio/b.ogg"
C = "01 Pop/Song/Other/c.ogg"
OGG = b"OggS" + b"\3" * 6000


def count_server(monkeypatch):
    """Record every GET path the test HTTP server handles."""
    seen = []
    orig = http.server.SimpleHTTPRequestHandler.do_GET

    def do_get(self):
        seen.append(self.path)
        return orig(self)
    monkeypatch.setattr(http.server.SimpleHTTPRequestHandler, "do_GET", do_get)
    return seen


def ogg_hits(seen):
    return [p for p in seen if p.endswith(".ogg")]


def setup(www, data_by_fp):
    for fp, d in data_by_fp.items():
        put(www, fp, d)
    make_song_db(core.DB_PATH, [(fp, "0" * 40) for fp in data_by_fp])
    for fp, d in data_by_fp.items():
        set_lfs(core.DB_PATH, fp, d)


def test_job_downloads_identical_audio_once(env, monkeypatch):
    www, tmp, dl = env
    other = b"OggS" + b"\4" * 3000
    setup(www, {A: OGG, B: OGG, C: other})
    seen = count_server(monkeypatch)
    t, res = run_download(song_files([A, B, C]), dl)
    assert res["d"] == 3 and res["f"] == 0
    assert (dl / A).read_bytes() == OGG and (dl / B).read_bytes() == OGG
    assert len(ogg_hits(seen)) == 2                    # one of A/B, and C
    assert t.copied == 1 and t.saved_bytes == len(OGG)
    assert t.saved_text() == "log_dedup_saved"         # identity tr in tests
    assert t.snapshot_ex()[0]["saved_bytes"] == len(OGG)
    assert not list(dl.rglob("*.part"))


def test_existing_local_copy_is_reused(env, monkeypatch):
    www, tmp, dl = env
    setup(www, {A: OGG, B: OGG})
    (dl / A).parent.mkdir(parents=True)
    (dl / A).write_bytes(OGG)                          # already on disk
    seen = count_server(monkeypatch)
    t, res = run_download(song_files([B]), dl)
    assert res["d"] == 1 and (dl / B).read_bytes() == OGG
    assert not ogg_hits(seen)
    assert t.copied == 1


def test_corrupt_local_source_falls_back_to_download(env, monkeypatch):
    www, tmp, dl = env
    setup(www, {A: OGG, B: OGG})
    (dl / A).parent.mkdir(parents=True)
    (dl / A).write_bytes(b"OggS" + b"\x09" * (len(OGG) - 4))   # same size, other bytes
    seen = count_server(monkeypatch)
    t, res = run_download(song_files([B]), dl)
    assert res["d"] == 1 and (dl / B).read_bytes() == OGG
    assert len(ogg_hits(seen)) == 1
    assert t.copied == 0 and t.saved_text() == ""


def test_copies_are_independent_files(env):
    www, tmp, dl = env
    setup(www, {A: OGG, B: OGG})
    run_download(song_files([A, B]), dl)
    (dl / A).write_bytes(b"edited")
    assert (dl / B).read_bytes() == OGG
