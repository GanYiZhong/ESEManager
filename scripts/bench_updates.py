"""Benchmark find_updates/find_missing on a synthetic ~6000-file library.
Usage: python scripts/bench_updates.py [path/to/core.py]  (default: src/core.py)
"""
import importlib.util
import os
import shutil
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "src", "core.py")
spec = importlib.util.spec_from_file_location("core_bench", path)
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)

N = 2000                      # songs: .tja + .ogg + .png each -> 6000 files
tmp = tempfile.mkdtemp()
songs, shas = [], {}
for i in range(N):
    d = f"01 Pop/Song{i:05d}"
    os.makedirs(os.path.join(tmp, d), exist_ok=True)
    files = []
    for ext, body in ((".tja", b"TITLE:x%d\n" % i), (".ogg", b"o" * 64), (".png", b"p" * 64)):
        rel = f"{d}/Song{i:05d}{ext}"
        with open(os.path.join(tmp, rel), "wb") as fh:
            fh.write(body)
        shas[rel] = core.git_blob_sha_bytes(body if i % 50 else b"stale")
        files.append({"file_path": rel, "filename": os.path.basename(rel)})
    songs.append({"id": i, "files": files})
core.search_songs = lambda *a, **k: songs
core.load_sha_map = lambda *a, **k: shas


def t(label, fn):
    s = time.perf_counter()
    r = fn()
    print(f"{label:28s} {time.perf_counter() - s:7.3f}s")
    return r


try:
    for run in ("cold", "warm (new process)"):
        if hasattr(core, "_sha_cache"):
            core._sha_cache.clear()      # simulate a fresh process
        r = t(f"find_updates {run}", lambda: core.find_updates(tmp))
        print("   changed songs:", len(r))
    t("find_missing", lambda: core.find_missing(songs, tmp))
finally:
    shutil.rmtree(tmp, ignore_errors=True)
