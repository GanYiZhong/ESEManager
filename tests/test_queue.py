"""Queueing: adding files to a running Downloader / download job."""

import threading
import time

from PySide6.QtWidgets import QMessageBox

import core
from test_gui import window  # noqa: F401  (fixture)


def _item(name, base, ext="tja"):
    fp = f"01 Pop/{name}/{name}.{ext}"
    return ({"song_name": name}, {"filename": f"{name}.{ext}", "file_path": fp,
                                  "download_url": base + fp})


def _serve(www, name, ext="tja"):
    d = www / "01 Pop" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.{ext}").write_bytes(b"data-" + name.encode())


def test_add_before_run_is_processed_and_deduped(tmp_path, http_dir):
    www, base = http_dir
    for n in "ABC":
        _serve(www, n)
    job = core.Downloader([_item("A", base)], str(tmp_path / "dl"), 2, bases=[base])
    added = job.add([_item("A", base), _item("B", base), _item("C", base)])
    assert [f["filename"] for _, f in added] == ["B.tja", "C.tja"]
    assert job.add([_item("B", base)]) == []
    assert job.total == 3
    assert job.run() == (3, 0, 0, 3)
    for n in "ABC":
        assert (tmp_path / "dl/01 Pop" / n / f"{n}.tja").read_bytes() == b"data-" + n.encode()


def test_add_while_running_extends_job_and_orders_charts_first(tmp_path, http_dir):
    www, base = http_dir
    for n in "AB":
        _serve(www, n)
    _serve(www, "B", "ogg")
    gate = threading.Event()
    order = []
    job = core.Downloader([_item("A", base)], str(tmp_path / "dl"), 1, bases=[base])
    orig = job._one

    def slow(sess, sha, item):
        order.append(item[1]["filename"])
        if item[1]["filename"] == "A.tja":
            gate.wait(5)
        return orig(sess, sha, item)
    job._one = slow
    res = []
    t = threading.Thread(target=lambda: res.append(job.run()))
    t.start()
    deadline = time.time() + 5
    while not order and time.time() < deadline:
        time.sleep(0.01)
    added = job.add([_item("B", base, "ogg"), _item("B", base)])   # audio listed first
    assert len(added) == 2 and job.total == 3
    gate.set()
    t.join(10)
    assert res == [(3, 0, 0, 3)]
    assert order == ["A.tja", "B.tja", "B.ogg"]          # chart before audio


def test_add_after_drain_returns_none(tmp_path, http_dir):
    www, base = http_dir
    _serve(www, "A")
    job = core.Downloader([_item("A", base)], str(tmp_path / "dl"), 1, bases=[base])
    job.run()
    assert job.add([_item("B", base)]) is None
    assert job.total == 1


def test_stop_ends_run_with_queued_items(tmp_path, http_dir):
    www, base = http_dir
    for n in "AB":
        _serve(www, n)
    job = core.Downloader([], str(tmp_path / "dl"), 1, bases=[base])
    job.add([_item("A", base), _item("B", base)])
    job.stop()
    assert job.run()[3] == 2
    assert job.add([_item("C", base)]) is None


def test_empty_job_returns(tmp_path):
    job = core.Downloader([], str(tmp_path), 2, bases=["http://127.0.0.1:9/"])
    assert job.run() == (0, 0, 0, 0)


class FakeThread:
    total = 5

    def __init__(self, ret):
        self.stopped = False
        self.ret = ret

    def isRunning(self):
        return not self.stopped

    def stop(self):
        self.stopped = True

    def add(self, files):
        return self.ret


def _running(window, monkeypatch, ret):
    window.dl_thread = FakeThread(ret)
    seen = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: seen.append(a))
    return seen


def _file(name):
    return ({"song_name": "S"}, {"filename": name, "file_path": "x/" + name,
                                 "download_url": ""})


def test_gui_start_during_run_queues_instead_of_warning(window, monkeypatch):
    files = [_file("S.tja"), _file("S.ogg")]
    seen = _running(window, monkeypatch, files[1:])
    window.dl_model.load(files[:1])
    window.start_download(files)
    assert seen == []
    assert window.dl_model.rowCount() == 2
    assert window.overall_bar.maximum() != 5          # the bar is by bytes, not file count
    assert window.statusBar().currentMessage() == window.tr("dl_queued", n=1, f=1)


def test_gui_drained_job_defers_files(window, monkeypatch):
    seen = _running(window, monkeypatch, None)
    files = [_file("S.tja")]
    window.start_download(files)
    assert seen == [] and window._deferred_files == files


def test_gui_nothing_new_says_so(window, monkeypatch):
    _running(window, monkeypatch, [])
    window.start_download([_file("S.tja")])
    assert window.statusBar().currentMessage() == window.tr("dl_queued_none")
