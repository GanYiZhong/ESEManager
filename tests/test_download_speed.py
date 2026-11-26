"""Downloader scheduling, resume, pooling and rate reporting (local server only)."""

import functools
import http.server
import threading

import pytest

import core


class RangeHandler(http.server.SimpleHTTPRequestHandler):
    seen = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        rng = self.headers.get("Range")
        RangeHandler.seen.append(rng)
        path = self.translate_path(self.path)
        try:
            data = open(path, "rb").read()
        except OSError:
            self.send_error(404)
            return
        start = 0
        if rng and rng.startswith("bytes="):
            start = int(rng[6:].split("-")[0])
        if start >= len(data) and rng:
            self.send_error(416)
            return
        self.send_response(206 if rng else 200)
        if rng:
            self.send_header("Content-Range", f"bytes {start}-{len(data) - 1}/{len(data)}")
        self.send_header("Content-Length", str(len(data) - start))
        self.end_headers()
        self.wfile.write(data[start:])


@pytest.fixture
def range_server(tmp_path):
    www = tmp_path / "www"
    www.mkdir()
    RangeHandler.seen = []
    handler = functools.partial(RangeHandler, directory=str(www))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield www, f"http://127.0.0.1:{server.server_address[1]}/"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture(autouse=True)
def _no_sha_db(monkeypatch):
    monkeypatch.setattr(core, "load_sha_map", lambda *a, **k: {})
    monkeypatch.setattr(core, "DB_PATH", "nonexistent.db")


def _files(names):
    return [({"song_name": "S"}, {"filename": n.split("/")[-1], "file_path": n,
                                  "download_url": ""}) for n in names]


def test_resumes_part_with_range(range_server, tmp_path):
    www, base = range_server
    (www / "c").mkdir()
    data = bytes(range(256)) * 400
    (www / "c/A.tja").write_bytes(data)
    dest = tmp_path / "dl" / "c"
    dest.mkdir(parents=True)
    (dest / "A.tja.part").write_bytes(data[:5000])
    job = core.Downloader(_files(["c/A.tja"]), str(tmp_path / "dl"), 1, bases=[base])
    assert job.run() == (1, 0, 0, 1)
    assert (dest / "A.tja").read_bytes() == data
    assert "bytes=5000-" in RangeHandler.seen
    assert job.bytes_total == len(data) - 5000      # only the fetched remainder counts


def test_oversized_part_restarts(range_server, tmp_path):
    www, base = range_server
    (www / "c").mkdir()
    (www / "c/A.tja").write_bytes(b"short")
    dest = tmp_path / "dl" / "c"
    dest.mkdir(parents=True)
    (dest / "A.tja.part").write_bytes(b"x" * 100)    # server answers 416
    job = core.Downloader(_files(["c/A.tja"]), str(tmp_path / "dl"), 1, bases=[base])
    assert job.run() == (1, 0, 0, 1)
    assert (dest / "A.tja").read_bytes() == b"short"


def test_part_ignored_when_server_has_no_range(http_dir, tmp_path):
    www, base = http_dir
    (www / "c").mkdir()
    (www / "c/A.tja").write_bytes(b"0123456789")
    dest = tmp_path / "dl" / "c"
    dest.mkdir(parents=True)
    (dest / "A.tja.part").write_bytes(b"junk")
    job = core.Downloader(_files(["c/A.tja"]), str(tmp_path / "dl"), 1, bases=[base])
    assert job.run() == (1, 0, 0, 1)
    assert (dest / "A.tja").read_bytes() == b"0123456789"


def test_charts_download_before_audio(range_server, tmp_path):
    www, base = range_server
    (www / "c").mkdir()
    names = ["c/A.ogg", "c/A.tja", "c/B.ogg", "c/B.tja"]
    for n in names:
        (www / n).write_bytes(b"data")
    logs = []
    job = core.Downloader(_files(names), str(tmp_path / "dl"), 1, bases=[base],
                          log=logs.append)
    assert job.run() == (4, 0, 0, 4)
    order = [m.split()[1] for m in logs if m.startswith("✓")]
    assert order == ["A.tja", "B.tja", "A.ogg", "B.ogg"]


def test_session_pool_matches_workers():
    sess = core.new_session(24)
    assert sess.get_adapter("https://x/")._pool_maxsize == 24


def test_snapshot_uses_recent_window(monkeypatch):
    job = core.Downloader(_files(["c/%d.tja" % i for i in range(100)]), "x", 1)
    clock = {"t": 1000.0}
    monkeypatch.setattr(core.time, "time", lambda: clock["t"])
    job.t0 = 1000.0
    # 100 s of slow progress ...
    clock["t"] = 1100.0
    job.bytes_total, job.done = 10 * 1024 * 1024, 10
    job.snapshot()
    # ... then a fast 4 s: 40 MB and 40 files
    clock["t"] = 1104.0
    job.bytes_total, job.done = 50 * 1024 * 1024, 50
    done, total, spd, eta, _ = job.snapshot()
    assert spd == pytest.approx(10.0)                # recent pace, not the 0.5 MB/s average
    assert eta == pytest.approx(50 / 10.0)           # 50 left at 10 files/s


def test_old_part_is_not_resumed(range_server, tmp_path):
    import os
    import time
    www, base = range_server
    (www / "c").mkdir()
    (www / "c/A.ogg").write_bytes(b"new audio data")
    dest = tmp_path / "dl" / "c"
    dest.mkdir(parents=True)
    part = dest / "A.ogg.part"
    part.write_bytes(b"old au")
    old = time.time() - core.PART_MAX_AGE - 60
    os.utime(part, (old, old))
    job = core.Downloader(_files(["c/A.ogg"]), str(tmp_path / "dl"), 1, bases=[base])
    assert job.run() == (1, 0, 0, 1)
    assert (dest / "A.ogg").read_bytes() == b"new audio data"
    assert all(r is None for r in RangeHandler.seen)
