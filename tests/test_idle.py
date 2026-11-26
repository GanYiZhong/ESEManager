"""Efficiency: no polling while idle, no leaked workers, no needless repaints."""

import time

import workers
from test_gui import window  # noqa: F401  (fixture)


def test_progress_timer_idle_and_no_thread_leak(window, qapp):
    # No job: the progress timer is not running.
    assert not hasattr(window, "dl_timer") or not window.dl_timer.isActive()
    # Rapid status scans and searches leave no worker behind.
    window.all_songs = [{"song_name": "a", "category": "c"}]
    for _ in range(3):
        window.refresh_download_status()
    window._run_search("", None)
    end = time.time() + 5
    while window._threads and time.time() < end:
        qapp.processEvents()
        time.sleep(0.01)
    assert window._threads == []


def test_unchanged_download_status_does_not_repaint(window):
    hits = []
    window.song_model.dataChanged.connect(lambda *a: hits.append(1))
    window._dl_seq = 1
    window.on_download_status(1, {("a", "c"): 1})
    n = len(hits)
    window.on_download_status(1, {("a", "c"): 1})
    assert len(hits) == n


def test_superseded_scan_skips_work(qapp):
    t = workers.DownloadStatusThread([], ".", seq=1)
    got = []
    t.done.connect(lambda *a: got.append(a))
    t.isInterruptionRequested = lambda: True
    t.run()
    assert got == []


def test_superseded_search_skips_work(qapp):
    t = workers.SearchThread("x", None, seq=1)
    got = []
    t.done.connect(lambda *a: got.append(a))
    t.isInterruptionRequested = lambda: True
    t.run()
    assert got == []
