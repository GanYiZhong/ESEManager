"""Auto download source: routing by measured throughput (two local throttled servers)."""

import http.server
import json
import threading
import time

import pytest

import core

BODY = b"x" * (48 * 1024)


def make_server(delay, fail=False):
    """Serves BODY for any path, `delay` seconds per 16 KiB chunk; counts hits and
    the peak number of concurrent connections."""
    state = {"hits": [], "active": 0, "peak": 0, "fail": fail, "lock": threading.Lock()}

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            with state["lock"]:
                state["hits"].append(self.path)
                state["active"] += 1
                state["peak"] = max(state["peak"], state["active"])
            try:
                if state["fail"]:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(BODY)))
                self.end_headers()
                for i in range(0, len(BODY), 16384):
                    time.sleep(delay)
                    self.wfile.write(BODY[i:i + 16384])
            finally:
                with state["lock"]:
                    state["active"] -= 1

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    state["server"] = srv
    state["base"] = f"http://127.0.0.1:{srv.server_address[1]}/"
    return state


@pytest.fixture
def servers():
    made = []

    def factory(delay, fail=False):
        s = make_server(delay, fail)
        made.append(s)
        return s
    yield factory
    for s in made:
        s["server"].shutdown()
        s["server"].server_close()


@pytest.fixture(autouse=True)
def _no_sha_db(monkeypatch):
    monkeypatch.setattr(core, "load_sha_map", lambda *a, **k: {})
    monkeypatch.setattr(core, "DB_PATH", "nonexistent.db")


def files(n):
    return [({"song_name": "S"}, {"filename": f"{i}.tja", "file_path": f"c/{i}.tja",
                                  "download_url": ""}) for i in range(n)]


def run(tmp_path, bases, n, workers=1, **kw):
    logs = []
    job = core.Downloader(files(n), str(tmp_path / "dl"), workers, bases=bases, auto=True,
                          log=logs.append, rank_path=kw.pop("rank_path", None))
    return job, job.run(), logs


def test_routes_to_faster_host_and_probes_slower(servers, tmp_path):
    slow = servers(0.05)
    fast = servers(0.002)
    # slow listed first: it is measured first, then loses the ranking
    job, res, logs = run(tmp_path, [slow["base"], fast["base"]], 41)
    assert res == (41, 0, 0, 41)
    assert len(fast["hits"]) > len(slow["hits"]) * 3
    assert 2 <= len(slow["hits"]) <= 6            # initial measurement + periodic probes
    assert sum("log_mirror" in m for m in logs) == 1   # switched once, logged once
    assert job.router.speeds()[fast["base"]] > job.router.speeds()[slow["base"]]


def test_failing_host_falls_back_and_is_avoided(servers, tmp_path):
    bad = servers(0.0, fail=True)
    good = servers(0.002)
    job, res, _ = run(tmp_path, [bad["base"], good["base"]], 12)
    assert res == (12, 0, 0, 12)
    # one attempt to find out it fails, then it is only probed rarely
    assert len(bad["hits"]) <= 3
    assert len(good["hits"]) == 12


def test_all_hosts_failing_reports_failure(servers, tmp_path):
    a = servers(0.0, fail=True)
    b = servers(0.0, fail=True)
    job, res, _ = run(tmp_path, [a["base"], b["base"]], 2)
    assert res == (0, 0, 2, 2)
    assert len(a["hits"]) == 2 and len(b["hits"]) == 2   # each host tried once per file


def test_never_retries_host_that_failed_the_file():
    r = core.HostRouter(["a/", "b/"])
    first = r.pick("f")
    r.report(first, "f", False)
    second = r.pick("f", [first])
    assert second != first
    r.report(second, "f", False)
    assert r.pick("f", [first, second]) is None
    # a later pass over the same file offers the failed hosts last
    r2 = core.HostRouter(["a/", "b/"])
    x = r2.pick("g")
    r2.report(x, "g", False)
    assert r2.pick("g") != x


def test_concurrency_limit_per_host():
    r = core.HostRouter(["ese/", "mir/"], limits={"ese/": 3})
    # both unmeasured: ese would be preferred, but only 3 slots exist
    picks = [r.pick(f"f{i}") for i in range(8)]
    assert picks.count("ese/") == 3
    assert picks.count("mir/") == 5


def test_concurrency_limit_end_to_end(servers, tmp_path, monkeypatch):
    ese = servers(0.01)
    mirror = servers(0.01)
    monkeypatch.setattr(core, "ESE_RAW_BASE", ese["base"])
    job, res, _ = run(tmp_path, [ese["base"], mirror["base"]], 24, workers=8)
    assert res == (24, 0, 0, 24)
    assert ese["peak"] <= core.ESE_MAX_CONN
    assert mirror["hits"]


def test_ranking_persisted_and_seeds_next_run(servers, tmp_path):
    slow = servers(0.05)
    fast = servers(0.002)
    rank = tmp_path / "rank.json"
    bases = [slow["base"], fast["base"]]
    run(tmp_path, bases, 6, rank_path=str(rank))
    data = json.loads(rank.read_text())
    assert data["hosts"][fast["base"]]["speed"] > data["hosts"][slow["base"]]["speed"]
    r = core.HostRouter(bases, path=str(rank))
    assert r.initial[0] == fast["base"]            # next run starts with the faster host
    assert r.pick("new") == fast["base"]


def test_auto_is_default_source():
    core.set_download_source(None)
    assert core._download_source == "auto"
    assert core.source_bases()[0] == core.ESE_RAW_BASE
    core.set_download_source("ese")
    assert core.Downloader([], "x", 1).router is None
    core.set_download_source(None)
