"""Background QThreads for the GUI. Each one wraps a function or class from
core.py (which has no Qt dependency) and reports through signals.

Workers never touch widgets. Downloads report progress through a snapshot that
the main thread polls with a QTimer, not a signal per chunk.
"""

import threading

from PySide6.QtCore import QThread, Signal

import core
from appconfig import APP_VERSION


class MetaLoadThread(QThread):
    """Reload the Japanese-title and BPM/level maps off the UI thread."""
    done = Signal(object, object)    # jp_map, meta_map

    def run(self):
        self.done.emit(core.load_jp_map(), core.load_meta_map())


class SearchThread(QThread):
    done = Signal(int, object)       # seq, songs
    fail = Signal(int, str)          # seq, message

    def __init__(self, keyword, category, seq=0, tr=None):
        super().__init__()
        self.tr = tr
        self.keyword = keyword
        self.category = category
        self.seq = seq

    def run(self):
        if self.isInterruptionRequested():     # superseded before it began
            return
        try:
            self.done.emit(self.seq, core.search_songs(self.keyword, self.category))
        except Exception as e:
            core.log.warning("search failed: %s", e)
            self.fail.emit(self.seq, core.friendly_error(e, self.tr))


class DownloadStatusThread(QThread):
    """core.download_status off the UI thread (one directory walk)."""
    done = Signal(int, object)       # seq, {song_key: status}

    def __init__(self, songs, download_dir, seq=0):
        super().__init__()
        self.songs = songs
        self.download_dir = download_dir
        self.seq = seq

    def run(self):
        if self.isInterruptionRequested():     # superseded before it began
            return
        try:
            self.done.emit(self.seq, core.download_status(self.songs, self.download_dir))
        except Exception:
            core.log.warning("download status scan failed", exc_info=True)


class CheckUpdatesThread(QThread):
    """core.find_updates on a worker thread. fail("__NO_SHA__") means the
    song database is too old to compare files."""
    progress = Signal(int, int)     # done, total
    done = Signal(object)           # list[song] with only the changed files
    fail = Signal(str)

    def __init__(self, download_dir, category=None, tr=None, only=None):
        super().__init__()
        self.tr = tr
        self.download_dir = download_dir
        self.category = category
        self.only = only

    def run(self):
        try:
            self.done.emit(core.find_updates(self.download_dir, self.category,
                                             progress=self.progress.emit, only=self.only))
        except core.NoShaError:
            self.fail.emit("__NO_SHA__")
        except Exception as e:
            core.log.warning("update check failed", exc_info=True)
            self.fail.emit(core.friendly_error(e, self.tr))


class AutoUpdateCheckThread(QThread):
    """Quiet background check of downloaded songs (core.auto_check_updates).
    Start it with QThread.LowPriority; failures are silent."""
    done = Signal(object, bool)     # songs with changed files, was_full_check

    def __init__(self, download_dir, last_full=0.0):
        super().__init__()
        self.download_dir = download_dir
        self.last_full = last_full

    def run(self):
        try:
            songs, full = core.auto_check_updates(self.download_dir, self.last_full)
        except Exception:
            core.log.info("auto update check skipped", exc_info=True)
            return
        self.done.emit(songs, full)


class DownloadThread(QThread):
    """Runs a core.Downloader. Control (stop/pause/resume/snapshot) and the
    counters (dl, skip, fail, total, failed, stopped) go to the downloader."""
    log = Signal(str)       # one or more lines joined by newlines, batched
    finished_all = Signal(int, int, int, int)      # downloaded, skipped, failed, total

    _DELEGATE = {"stop", "pause", "resume", "is_paused", "snapshot", "stopped",
                 "failed", "fail_reasons", "dl", "skip", "fail", "total", "done", "add"}

    def __init__(self, files, download_dir, workers, overwrite=False, tr=None):
        super().__init__()
        # Log lines are buffered and emitted in batches (flush_log, called by
        # the GUI's progress timer): a signal per line floods the event loop
        # when thousands of small files finish in a few seconds.
        self._log_buf = []
        self._log_lock = threading.Lock()
        self.job = core.Downloader(files, download_dir, workers, overwrite=overwrite,
                                   tr=tr, log=self._buffer_log)

    def _buffer_log(self, msg):
        with self._log_lock:
            self._log_buf.append(msg)

    def flush_log(self):
        """Emit all buffered log lines as one signal (no-op when empty)."""
        with self._log_lock:
            buf, self._log_buf = self._log_buf, []
        if buf:
            self.log.emit(chr(10).join(buf))

    def __getattr__(self, name):
        if name in DownloadThread._DELEGATE:
            return getattr(self.__dict__["job"], name)
        raise AttributeError(name)

    def run(self):
        result = self.job.run()
        self.flush_log()
        self.finished_all.emit(*result)


class VersionThread(QThread):
    result = Signal(str, str)  # remote, local

    def run(self):
        self.result.emit(core.fetch_remote_version(), core.read_local_version())


class DBUpdateThread(QThread):
    log = Signal(str)
    done = Signal(bool, str)

    def __init__(self, version, tr=None):
        super().__init__()
        self.version = version
        self.tr = tr or (lambda key, **kw: key)

    def run(self):
        try:
            core.update_databases(self.version, log=self.log.emit, tr=self.tr)
            self.done.emit(True, "ok")
        except Exception as e:
            core.log.warning("database update failed", exc_info=True)
            self.done.emit(False, core.friendly_error(e, self.tr))


class AppUpdateThread(QThread):
    """Emit (tag, page_url) when GitHub has a release newer than this build."""
    found = Signal(str, str)

    def __init__(self, current=None):
        super().__init__()
        self.current = current or APP_VERSION

    def run(self):
        hit = core.latest_app_release(self.current)
        if hit:
            self.found.emit(*hit)


class ReleaseNotesThread(QThread):
    """Fetch a release's Markdown notes by tag; emits loaded(tag, body) only on
    success (offline / unknown tag: silent)."""
    loaded = Signal(str, str)

    def __init__(self, tag):
        super().__init__()
        self.tag = tag

    def run(self):
        try:
            data = core.fetch_release_by_tag(self.tag)
            self.loaded.emit(self.tag, (data.get("body") or "").strip())
        except Exception:
            core.log.info("release notes unavailable for %s", self.tag)


class VersionSortingThread(QThread):
    log = Signal(str)
    done = Signal(bool, str, str)    # ok, "updated"/"latest" or error, commit

    def __init__(self, download_dir, tr=None):
        super().__init__()
        self.tr = tr
        self.download_dir = download_dir

    def run(self):
        try:
            status, commit = core.download_version_sorting(self.download_dir,
                                                           log=self.log.emit)
            self.done.emit(True, status, commit)
        except Exception as e:
            core.log.warning("version sorting download failed", exc_info=True)
            self.done.emit(False, core.friendly_error(e, self.tr), "")


class AppSelfUpdateThread(QThread):
    """Download, verify and install the latest release over the app folder.
    done(True, "applied:<tag>") -> restart now; done(True, "scheduled:<tag>")
    -> quit now, a helper copies the files and starts the new version."""
    progress = Signal(int, int)      # bytes so far, total
    done = Signal(bool, str)

    restart_exe = None               # program the Windows helper starts afterwards

    def __init__(self, tr=None):
        super().__init__()
        self.tr = tr
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            release = core.fetch_latest_release()
            root = core.download_app_update(release, progress=self.progress.emit,
                                            log=core.log.info, stop=lambda: self._stop)
            how = core.install_app_update(root, restart_exe=self.restart_exe)
            self.done.emit(True, f"{how}:{release.get('tag_name') or ''}")
        except Exception as e:
            core.log.warning("self-update failed", exc_info=True)
            self.done.emit(False, core.friendly_error(e, self.tr))
