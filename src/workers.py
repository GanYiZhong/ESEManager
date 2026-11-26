"""Background QThreads for the GUI. Each one wraps a function or class from
core.py (which has no Qt dependency) and reports through signals.

Workers never touch widgets. Downloads report progress through a snapshot that
the main thread polls with a QTimer, not a signal per chunk.
"""

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

    def __init__(self, download_dir, category=None, tr=None):
        super().__init__()
        self.tr = tr
        self.download_dir = download_dir
        self.category = category

    def run(self):
        try:
            self.done.emit(core.find_updates(self.download_dir, self.category,
                                             progress=self.progress.emit))
        except core.NoShaError:
            self.fail.emit("__NO_SHA__")
        except Exception as e:
            core.log.warning("update check failed", exc_info=True)
            self.fail.emit(core.friendly_error(e, self.tr))


class DownloadThread(QThread):
    """Runs a core.Downloader. Control (stop/pause/resume/snapshot) and the
    counters (dl, skip, fail, total, failed, stopped) go to the downloader."""
    log = Signal(str)
    finished_all = Signal(int, int, int, int)      # downloaded, skipped, failed, total

    _DELEGATE = {"stop", "pause", "resume", "is_paused", "snapshot", "stopped",
                 "failed", "dl", "skip", "fail", "total", "done", "add"}

    def __init__(self, files, download_dir, workers, overwrite=False, tr=None):
        super().__init__()
        self.job = core.Downloader(files, download_dir, workers, overwrite=overwrite,
                                   tr=tr, log=self.log.emit)

    def __getattr__(self, name):
        if name in DownloadThread._DELEGATE:
            return getattr(self.__dict__["job"], name)
        raise AttributeError(name)

    def run(self):
        self.finished_all.emit(*self.job.run())


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
