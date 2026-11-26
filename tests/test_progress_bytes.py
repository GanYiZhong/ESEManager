"""Byte-based progress/ETA, size estimates and the free-space check."""

import collections

import pytest

import core
import cli

MB = 1024 * 1024
Usage = collections.namedtuple("Usage", "total used free")


def _f(fp, size=0):
    return ({"song_name": "S"}, {"filename": fp.rsplit("/", 1)[-1], "file_path": fp,
                                 "size": size, "download_url": ""})


def _expected(job):
    with job._lock:
        return job._expected_locked()


def test_human_formats():
    assert core.human_clock(65) == "1:05"
    assert core.human_clock(3725) == "1:02:05"
    assert core.human_clock(0) == "—" and core.human_clock(None) == "—"
    assert core.human_bytes_pair(120 * MB, 340 * MB) == "120 / 340 MB"
    assert core.human_bytes_pair(1.5 * MB, 4 * MB) == "1.5 / 4.0 MB"
    assert core.human_bytes(0) == "0 B" and core.human_bytes(1536) == "1.5 KB"


def test_size_hint_ignores_pointer_size_of_audio():
    lfs = {"a/S.ogg": ("sha", 7 * MB)}
    assert core.file_size_hint({"file_path": "a/S.ogg", "size": 130}, lfs) == 7 * MB
    assert core.file_size_hint({"file_path": "a/S.ogg", "size": 130}, {}) == 0
    assert core.file_size_hint({"file_path": "a/S.tja", "size": 900}, lfs) == 900
    assert core.file_size_hint({"file_path": "a/S.tja", "size": None}, lfs) == 0


def test_expected_mixes_known_and_unknown_sizes():
    files = [_f("a/1.tja", 20_000), _f("a/2.tja"), _f("a/3.tja"), _f("a/4.ogg")]
    job = core.Downloader(files, "x", 1)
    total, exact = _expected(job)
    assert not exact
    assert total == 20_000 + 2 * core.EST_CHART + core.EST_AUDIO
    # the audio size becomes exact when the pointer map is read (run() does it)
    with job._lock:
        job._set_known("a/4.ogg", 9 * MB)
    assert _expected(job)[0] == 20_000 + 2 * core.EST_CHART + 9 * MB
    # finished files: median of their extension replaces the 12 KB guess
    with job._lock:
        job._ext_sizes["tja"] = collections.deque([100, 300, 200])
        job._ext_sizes[".tja"] = collections.deque([100, 300, 200])
    assert _expected(job)[0] == 20_000 + 2 * 200 + 9 * MB


def test_skipped_files_leave_the_expected_total():
    job = core.Downloader([_f("a/1.tja", 1000), _f("a/2.tja")], "x", 1)
    with job._lock:
        job._set_known("a/1.tja", 0)
        job._set_known("a/2.tja", 0)
    assert _expected(job) == (0, True)


def test_added_files_are_counted():
    job = core.Downloader([_f("a/1.tja", 1000)], "x", 1)
    job.add([_f("a/2.tja", 5000), _f("a/3.ogg")])
    assert _expected(job)[0] == 6000 + core.EST_AUDIO


def test_eta_comes_from_remaining_bytes(monkeypatch):
    files = [_f("c/big1.bin", 50 * MB), _f("c/big2.bin", 50 * MB)]
    job = core.Downloader(files, "x", 1)
    clock = {"t": 1000.0}
    monkeypatch.setattr(core.time, "time", lambda: clock["t"])
    job.t0 = 1000.0
    clock["t"] = 1100.0
    job.bytes_total = 10 * MB
    job.snapshot_ex()
    clock["t"] = 1104.0
    job.bytes_total, job.done = 50 * MB, 1       # 40 MB in the last 4 s
    info, _ = job.snapshot_ex()
    assert info["speed"] == pytest.approx(10.0)
    assert info["bytes_total"] == 100 * MB and info["exact"]
    assert info["eta"] == pytest.approx(5.0)      # 50 MB left at 10 MB/s
    # the old tuple API still reports the by-file-count ETA
    done, total, spd, eta, _ = job.snapshot()
    assert (done, total) == (1, 2)


def test_many_small_charts_then_big_audio_has_honest_eta(monkeypatch):
    files = [_f(f"c/{i}.tja", 10_000) for i in range(100)] + [_f("c/x.bin", 100 * MB)]
    job = core.Downloader(files, "x", 1)
    clock = {"t": 1000.0}
    monkeypatch.setattr(core.time, "time", lambda: clock["t"])
    job.t0 = 1000.0
    clock["t"] = 1001.0
    job.snapshot_ex()
    clock["t"] = 1003.0
    job.bytes_total, job.done = 1_000_000, 100        # all charts done in 3 s
    info, _ = job.snapshot_ex()
    # by file count the ETA would be a fraction of a second; by bytes it is not
    assert info["eta"] > 30


def test_real_download_settles_expected_to_actual(tmp_path, http_dir, monkeypatch):
    www, base = http_dir
    (www / "c").mkdir()
    (www / "c/A.tja").write_bytes(b"a" * 5000)
    (www / "c/B.tja").write_bytes(b"b" * 3000)
    (www / "c/S.ogg").write_bytes(b"o" * 70000)
    sha = core.hashlib.sha256(b"o" * 70000).hexdigest()
    monkeypatch.setattr(core, "load_lfs_map", lambda *a: {"c/S.ogg": (sha, 70000)})
    files = [_f("c/A.tja"), _f("c/B.tja"), _f("c/S.ogg")]
    job = core.Downloader(files, str(tmp_path / "dl"), 1, bases=[base])
    assert job.run() == (3, 0, 0, 3)
    info, _ = job.snapshot_ex()
    assert info["bytes_done"] == 78000 and info["bytes_total"] == 78000 and info["exact"]


def test_content_length_refines_unknown_size(tmp_path, http_dir):
    www, base = http_dir
    (www / "c").mkdir()
    (www / "c/A.tja").write_bytes(b"a" * 5000)
    job = core.Downloader([_f("c/A.tja")], str(tmp_path / "dl"), 1, bases=[base])
    assert _expected(job)[0] == core.EST_CHART
    job.run()
    assert _expected(job) == (5000, True)


# ---------------------------------------------------------------- disk space
def test_plan_download_flags_short_space(tmp_path, monkeypatch):
    files = [_f("c/A.tja", 10 * MB), _f("c/B.tja", 10 * MB)]
    monkeypatch.setattr(core.shutil, "disk_usage", lambda p: Usage(10**12, 0, 21 * MB))
    plan = core.plan_download(files, str(tmp_path), lfs_map={})
    assert plan["expected"] == 20 * MB and plan["exact"]
    assert plan["need"] == int(20 * MB * 1.1) and plan["free"] == 21 * MB
    assert not plan["ok"]                       # 21 MB < 22 MB needed
    monkeypatch.setattr(core.shutil, "disk_usage", lambda p: Usage(10**12, 0, 23 * MB))
    assert core.plan_download(files, str(tmp_path), lfs_map={})["ok"]


def test_plan_download_skips_existing_unless_overwrite(tmp_path):
    (tmp_path / "c").mkdir()
    (tmp_path / "c/A.tja").write_bytes(b"x")
    files = [_f("c/A.tja", 1000), _f("c/B.tja", 500)]
    assert core.plan_download(files, str(tmp_path), lfs_map={})["expected"] == 500
    assert core.plan_download(files, str(tmp_path), overwrite=True,
                              lfs_map={})["expected"] == 1500


def test_free_space_walks_up_to_existing_parent(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(core.shutil, "disk_usage",
                        lambda p: seen.append(p) or Usage(1, 0, 5))
    assert core.free_space(str(tmp_path / "not" / "there")) == 5
    assert seen == [str(tmp_path)]


# ---------------------------------------------------------------- CLI
@pytest.fixture
def cli_env(tmp_path, http_dir, monkeypatch):
    www, base = http_dir
    (www / "c").mkdir()
    (www / "c/A.tja").write_bytes(b"a" * 100)
    monkeypatch.setattr(core, "source_bases", lambda: [base])
    monkeypatch.setattr(core, "_download_source", "ese")
    monkeypatch.setattr(core.shutil, "disk_usage", lambda p: Usage(10**12, 0, 1000))
    cli.out.quiet = True
    yield tmp_path / "dl"
    cli.out.quiet = False


def _tr(key, **kw):
    return key + " " + " ".join(f"{k}={v}" for k, v in sorted(kw.items()))


def test_cli_refuses_when_disk_is_short(cli_env):
    files = [_f("c/A.tja", 10 * MB)]
    assert cli.run_download(files, str(cli_env), 1, _tr) == 2
    assert not (cli_env / "c/A.tja").exists()


def test_cli_force_downloads_anyway(cli_env):
    files = [_f("c/A.tja", 10 * MB)]
    assert cli.run_download(files, str(cli_env), 1, _tr, force=True) == 0
    assert (cli_env / "c/A.tja").read_bytes() == b"a" * 100


from PySide6.QtWidgets import QMessageBox  # noqa: E402
from test_gui import window  # noqa: E402,F401  (fixture)


def test_gui_selection_uses_lfs_sizes(window, monkeypatch):
    lfs = {"Pop/s0/S.ogg": ("sha", 30 * MB)}
    import models
    monkeypatch.setattr(models, "lfs_map_cached", lambda: lfs)
    songs = [{"song_name": "S0", "category": "Pop", "files": [
        {"filename": "S.tja", "file_path": "Pop/s0/S.tja", "size": 1 * MB},
        {"filename": "S.ogg", "file_path": "Pop/s0/S.ogg", "size": 130}]}]
    window.song_model.set_songs(songs)
    window.song_model.set_all(True)
    window.update_sel_count()
    assert window.sel_label.text() == window.tr("sel_detail_size", n=1, f=2, size="31.0 MB")


def test_gui_warns_before_starting_when_disk_is_short(window, monkeypatch, tmp_path):
    asked = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: asked.append(a[2]) or QMessageBox.No)
    monkeypatch.setattr(core.shutil, "disk_usage", lambda p: Usage(10**12, 0, 10))
    window.dir_edit.setText(str(tmp_path / "dl"))
    window.start_download([_f("c/A.tja", 5 * MB)])
    assert len(asked) == 1 and "5.5 MB" in asked[0]
    assert window.dl_thread is None or not window.dl_thread.isRunning()


def test_gui_progress_label_shows_bytes_files_and_eta(window):
    class Fake:
        def flush_log(self):
            pass

        def is_paused(self):
            return False

        def snapshot_ex(self):
            return ({"done": 42, "total": 120, "speed": 3.2, "eta": 65,
                     "bytes_done": 120 * MB, "bytes_total": 340 * MB, "exact": True}, {})
    window.overall_bar.setRange(0, window.BAR_STEPS)
    window.dl_thread = Fake()
    window.refresh_progress()
    t = window.overall_label.text()
    assert "120 / 340 MB" in t and "ETA 1:05" in t and window.tr(
        "dl_files_count", done=42, total=120) in t
    assert window.overall_bar.value() == 352            # 35.3 % of 1000 steps
    window.dl_thread = None


def test_cli_progress_line_by_bytes():
    line = cli.render_progress(42, 120, 3.2, 65, 100, 120 * MB, 340 * MB)
    assert "35%" in line and "120 / 340 MB" in line and "ETA 1:05" in line
    assert "3.20 MB/s" in line and "42/120 files" in line and len(line) <= 99
    assert "~" in cli.render_progress(1, 2, 1, 5, 100, 1 * MB, 4 * MB, exact=False)
    narrow = cli.render_progress(42, 120, 3.2, 65, 50, 120 * MB, 340 * MB)
    assert len(narrow) <= 49 and "35%" in narrow
