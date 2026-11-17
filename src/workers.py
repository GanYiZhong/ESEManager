"""Background QThreads: search, downloads, update checks and database updates.

Workers never touch widgets; they report through signals (or, for downloads,
through a snapshot that the main thread polls with a QTimer).
"""

import os
import time
import sqlite3
import threading
import hashlib
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

import requests
from PySide6.QtCore import QThread, Signal

from appconfig import (DB_PATH, LOCAL_DB_PATH, VERSION_FILE, ESE_RAW_BASE,
                       DB_RELEASE_URL, USER_AGENT, SQLITE_MAGIC, live_url, safe_join,
                       UnsafePathError, APP_VERSION, LATEST_RELEASE_API, is_newer,
                       VSORT_REPO, VSORT_FOLDER, VSORT_BRANCH_API, VSORT_ARCHIVE_URL)
from download_songs import SongDownloader
from tja_parser import decode_tja_bytes

# ESE stores these through Git LFS: the blob sha recorded by `git ls-tree` is the
# sha of the small LFS pointer file, not of the audio, so it cannot be compared
# with a downloaded file. (ESE's .gitattributes: "*.ogg filter=lfs".)
LFS_EXTS = {".ogg"}

RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}


def is_lfs_path(path):
    return os.path.splitext(path)[1].lower() in LFS_EXTS


def new_session():
    sess = requests.Session()
    sess.headers["User-Agent"] = USER_AGENT
    return sess


def get_with_retry(sess, url, attempts=3, stop=None, **kw):
    """GET with a short exponential backoff on connection errors and 5xx/429."""
    delay = 1.0
    for i in range(attempts):
        try:
            r = sess.get(url, **kw)
            if r.status_code in RETRY_STATUS and i < attempts - 1:
                r.close()
                raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
            r.raise_for_status()
            return r
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
            resp = getattr(e, "response", None)
            retryable = resp is None or resp.status_code in RETRY_STATUS
            if not retryable or i == attempts - 1 or (stop and stop()):
                raise
            time.sleep(delay)
            delay *= 2


def connect_ro(path):
    """Open a SQLite database read-only. Unlike sqlite3.connect(path) this never
    creates an empty file when the database is missing (it raises instead)."""
    import pathlib
    return sqlite3.connect(pathlib.Path(os.path.abspath(path)).as_uri() + "?mode=ro",
                           uri=True)


def write_atomic(path, data):
    part = path + ".part"
    with open(part, "wb") as f:
        f.write(data)
    os.replace(part, path)


# ---------------------------------------------------------------- local metadata
def load_jp_map(local_db=None):
    """song_name -> Japanese title. song_name is the .tja file stem, so match on
    file_name first (~93% hit rate) and fill gaps by title (~72% alone)."""
    local_db = local_db or LOCAL_DB_PATH
    m = {}
    if not os.path.exists(local_db):
        return m
    try:
        conn = connect_ro(local_db)
        try:
            rows = conn.execute(
                "SELECT title, file_name, title_ja FROM local_songs "
                "WHERE title_ja IS NOT NULL AND title_ja != ''").fetchall()
        finally:
            conn.close()
        for title, file_name, ja in rows:
            if file_name and ja:
                m.setdefault(os.path.splitext(file_name)[0], ja)
        for title, file_name, ja in rows:
            if title and ja:
                m.setdefault(title, ja)
    except Exception as e:
        print("load_jp_map:", e)
    return m


def load_meta_map(local_db=None):
    """song_name -> {bpm, level_*}, keyed like load_jp_map. Older ese_local.db
    files may lack the level columns, so check which exist first."""
    local_db = local_db or LOCAL_DB_PATH
    m = {}
    if not os.path.exists(local_db):
        return m
    try:
        conn = connect_ro(local_db)
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(local_songs)")}
            lvl_cols = [c for c in ("level_easy", "level_normal", "level_hard",
                                    "level_oni", "level_ura") if c in cols]
            sel = ["title", "file_name", "bpm"] + lvl_cols
            rows = conn.execute(f"SELECT {', '.join(sel)} FROM local_songs").fetchall()
        finally:
            conn.close()

        def to_meta(row):
            d = {"bpm": (row[2] or "").strip()}
            for i, c in enumerate(lvl_cols):
                d[c] = row[3 + i]
            return d

        def has_levels(row):
            return any(row[3 + i] is not None for i in range(len(lvl_cols)))

        # One file name can have several rows (an old local-scan row plus a remote
        # row) and only one carries levels; put those first so setdefault keeps it.
        rows = sorted(rows, key=lambda r: not has_levels(r))
        for row in rows:
            if row[1]:
                m.setdefault(os.path.splitext(row[1])[0], to_meta(row))
        for row in rows:
            if row[0]:
                m.setdefault(row[0], to_meta(row))
    except Exception as e:
        print("load_meta_map:", e)
    return m


class MetaLoadThread(QThread):
    """Reload the Japanese-title and BPM/level maps off the UI thread."""
    done = Signal(object, object)    # jp_map, meta_map

    def run(self):
        self.done.emit(load_jp_map(), load_meta_map())


# ---------------------------------------------------------------- search
def has_cjk(text):
    return any('぀' <= c <= 'ヿ' or '一' <= c <= '鿿' for c in text or "")


def search_songs(keyword, category=None):
    """Search the song database. A Japanese keyword also matches songs whose
    Japanese title (from the local title database) contains it. box.def rows
    are dropped and only songs with files are returned. Shared by GUI and CLI."""
    d = SongDownloader(db_path=DB_PATH)
    try:
        songs = d.search_songs(keyword=keyword or None, category=category)
        if keyword and has_cjk(keyword) and os.path.exists(LOCAL_DB_PATH):
            conn = connect_ro(LOCAL_DB_PATH)
            try:
                titles = [r[0] for r in conn.execute(
                    "SELECT title FROM local_songs WHERE title_ja LIKE ?",
                    (f"%{keyword}%",)) if r[0]]
            finally:
                conn.close()
            if titles:
                extra = d.search_songs(keywords=titles, category=category)
                seen = {(s["song_name"], s["category"]) for s in songs}
                for s in extra:
                    k = (s["song_name"], s["category"])
                    if k not in seen:
                        seen.add(k)
                        songs.append(s)
    finally:
        d.close()
    out = []
    for s in songs:
        s["files"] = [f for f in s["files"] if f["filename"].lower() != "box.def"]
        if s["files"]:
            out.append(s)
    return out


class SearchThread(QThread):
    done = Signal(int, object)       # seq, songs
    fail = Signal(int, str)          # seq, message

    def __init__(self, keyword, category, has_local=True, seq=0):
        super().__init__()
        self.keyword = keyword
        self.category = category
        self.seq = seq

    def run(self):
        try:
            self.done.emit(self.seq, search_songs(self.keyword, self.category))
        except Exception as e:
            self.fail.emit(self.seq, str(e))


# ---------------------------------------------------------------- update check
def git_blob_sha(path):
    """git blob object hash: sha1(b"blob <size>\\0" + content), the same value
    `git ls-tree` reports, so a local file can be compared with upstream."""
    size = os.path.getsize(path)
    h = hashlib.sha1()
    h.update(b"blob %d\0" % size)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_blob_sha_bytes(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


# path -> (mtime_ns, size, sha); avoids re-hashing unchanged files on every check
_sha_cache = {}
_sha_cache_lock = threading.Lock()


def cached_blob_sha(path):
    st = os.stat(path)
    key = (st.st_mtime_ns, st.st_size)
    with _sha_cache_lock:
        hit = _sha_cache.get(path)
    if hit and hit[0] == key:
        return hit[1]
    sha = git_blob_sha(path)
    with _sha_cache_lock:
        _sha_cache[path] = (key, sha)
    return sha


def load_sha_map(db_path=None):
    conn = connect_ro(db_path or DB_PATH)
    try:
        return {fp: sha for fp, sha in conn.execute(
            "SELECT file_path, blob_sha FROM song_files "
            "WHERE blob_sha IS NOT NULL AND blob_sha != ''")}
    finally:
        conn.close()


class CheckUpdatesThread(QThread):
    """Find downloaded files whose upstream content changed (git blob sha).
    LFS audio is skipped: its recorded sha belongs to the pointer file."""
    progress = Signal(int, int)     # done, total
    done = Signal(object)           # list[song] with only the changed files
    fail = Signal(str)

    def __init__(self, download_dir, category=None):
        super().__init__()
        self.download_dir = download_dir
        self.category = category

    def run(self):
        try:
            d = SongDownloader(db_path=DB_PATH)
            try:
                songs = d.search_songs(keyword=None, category=self.category)
            finally:
                d.close()

            sha_map = load_sha_map()
            if not sha_map:
                self.fail.emit("__NO_SHA__")    # old DB without blob_sha
                return

            candidates = []     # (song, file, local_path, remote_sha)
            for s in songs:
                for f in s["files"]:
                    fp = f["file_path"]
                    if f["filename"].lower() == "box.def" or is_lfs_path(fp):
                        continue
                    sha = sha_map.get(fp)
                    if not sha:
                        continue
                    try:
                        lp = safe_join(self.download_dir, fp)
                    except UnsafePathError:
                        continue
                    if os.path.exists(lp):
                        candidates.append((s, f, lp, sha))

            total = len(candidates)
            self.progress.emit(0, total)

            def check(item):
                s, f, lp, sha = item
                try:
                    return (s, f) if cached_blob_sha(lp) != sha else None
                except OSError:
                    return None

            changed = {}    # id(song) -> song dict with only the changed files
            done = 0
            with ThreadPoolExecutor(max_workers=8) as ex:
                for res in ex.map(check, candidates):
                    done += 1
                    if done % 100 == 0 or done == total:
                        self.progress.emit(done, total)
                    if res:
                        s, f = res
                        entry = changed.setdefault(id(s), dict(s, files=[]))
                        entry["files"].append(f)

            # An updated chart usually ships with new audio; include the song's
            # LFS files too so the pair stays consistent.
            for entry in changed.values():
                have = {f["file_path"] for f in entry["files"]}
                orig = next(s for s in songs if s["song_name"] == entry["song_name"]
                            and s["category"] == entry["category"])
                entry["files"] += [f for f in orig["files"]
                                   if is_lfs_path(f["file_path"]) and f["file_path"] not in have]

            self.done.emit(list(changed.values()))
        except Exception as e:
            self.fail.emit(str(e))


# ---------------------------------------------------------------- downloads
# Workers do not emit a signal per chunk: downloading thousands of files in
# parallel would flood the main thread's event queue. Progress goes into shared
# state that the main thread pulls every ~200 ms with snapshot().
class DownloadThread(QThread):
    log = Signal(str)
    finished_all = Signal(int, int, int, int)      # downloaded, skipped, failed, total

    def __init__(self, files, download_dir, workers, overwrite=False, tr=None):
        super().__init__()
        self.files = files
        self.download_dir = download_dir
        self.workers = max(1, workers)
        self.overwrite = overwrite     # True = replace existing files (update mode)
        self.tr = tr or (lambda key, **kw: key)
        self._stop = False
        self._pause = threading.Event()
        self._pause.set()              # set = running, clear = paused
        self.failed = []               # [(song, file_info)]
        self._lock = threading.Lock()
        self._dirty = {}               # file_path -> (status, pct, speed) since last pull
        self.total = len(files)
        self.done = 0
        self.dl = self.skip = self.fail = 0
        self.bytes_total = 0
        self.t0 = time.time()

    @property
    def stopped(self):
        return self._stop

    def stop(self):
        self._stop = True
        self._pause.set()              # wake paused workers so they can exit

    def pause(self):
        self._pause.clear()

    def resume(self):
        self._pause.set()

    def is_paused(self):
        return not self._pause.is_set()

    def snapshot(self):
        """Called from the main thread: counters plus changed rows since last call."""
        with self._lock:
            el = time.time() - self.t0
            spd = (self.bytes_total / 1024 / 1024) / el if el > 0 else 0
            eta = (self.total - self.done) / (self.done / el) if self.done > 0 and el > 0 else 0
            dirty = self._dirty
            self._dirty = {}
            return (self.done, self.total, spd, eta, dirty)

    def _mark(self, file_path, status, pct, speed):
        with self._lock:
            self._dirty[file_path] = (status, pct, speed)

    def _count(self, kind):
        with self._lock:
            self.done += 1
            setattr(self, kind, getattr(self, kind) + 1)

    def run(self):
        sess = new_session()
        try:
            sha_map = load_sha_map()
        except Exception:
            sha_map = {}

        def cancelled():
            return self._stop

        def worker(item):
            song, f = item
            self._pause.wait()             # wait here while paused (before a file starts)
            if self._stop:
                return
            fp = f["file_path"]
            disp = f["filename"]
            part = None
            try:
                save_path = safe_join(self.download_dir, fp)
                if os.path.exists(save_path) and not self.overwrite:
                    self._count("skip")
                    self._mark(fp, "skipped", 100.0, 0.0)
                    return
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                # Old databases may have rows with an empty download_url; the link
                # follows from file_path, so derive it when missing.
                dl_url = f["download_url"] or (ESE_RAW_BASE + urllib.parse.quote(fp))
                part = save_path + ".part"
                with get_with_retry(sess, live_url(dl_url), stream=True, timeout=60,
                                    stop=cancelled) as r:
                    clen = int(r.headers.get("content-length", 0) or 0)
                    got = 0
                    ft0 = time.time()
                    last = 0.0
                    with open(part, "wb") as out:
                        for chunk in r.iter_content(chunk_size=65536):
                            if self._stop:
                                raise InterruptedError(self.tr("log_cancelled"))
                            if not self._pause.is_set():       # paused mid-file
                                self._mark(fp, "paused", 0.0, 0.0)
                                self._pause.wait()
                                if self._stop:
                                    raise InterruptedError(self.tr("log_cancelled"))
                            if not chunk:
                                continue
                            out.write(chunk)
                            got += len(chunk)
                            with self._lock:
                                self.bytes_total += len(chunk)
                            now = time.time()
                            if now - last >= 0.2:            # at most 5 updates/s per file
                                last = now
                                fe = now - ft0
                                spd = (got / 1024 / 1024) / fe if fe > 0 else 0
                                pct = (got / clen * 100) if clen else 50.0
                                self._mark(fp, "downloading", pct, spd)
                if clen and got != clen:
                    raise IOError(self.tr("log_short", got=got, want=clen))
                want = sha_map.get(fp)
                if want and not is_lfs_path(fp):
                    # Re-hash as a git blob (needs the size prefix, so hash the file).
                    if git_blob_sha(part) != want:
                        raise IOError(self.tr("log_sha_mismatch"))
                os.replace(part, save_path)
                part = None
                self._count("dl")
                self._mark(fp, "done", 100.0, 0.0)
                self.log.emit(f"✓ {disp} ({got/1024/1024:.2f} MB)")
            except Exception as e:
                with self._lock:
                    self.failed.append((song, f))
                self._count("fail")
                self._mark(fp, "failed", 0.0, 0.0)
                self.log.emit(self.tr("log_fail", f=disp, e=e))
            finally:
                if part and os.path.exists(part):
                    try:
                        os.remove(part)
                    except OSError:
                        pass

        try:
            # On first download into a category folder, also fetch ESE's box.def.
            self._fetch_boxdefs(sess)
            with ThreadPoolExecutor(max_workers=self.workers) as ex:
                list(ex.map(worker, self.files))
        finally:
            sess.close()
        self.finished_all.emit(self.dl, self.skip, self.fail, self.total)

    def _fetch_boxdefs(self, sess):
        """Create box.def for each category folder touched by this download."""
        try:
            conn = connect_ro(DB_PATH)
            try:
                boxmap = {fp.split("/")[0]: fp for (fp,) in conn.execute(
                    "SELECT file_path FROM song_files WHERE lower(filename)='box.def'")}
            finally:
                conn.close()
        except Exception:
            return
        cats = {f["file_path"].split("/")[0] for _, f in self.files if "/" in f["file_path"]}
        for cat in sorted(cats):
            if self._stop:
                break
            fp = boxmap.get(cat)
            if not fp:
                continue
            try:
                dest = safe_join(self.download_dir, cat + "/box.def")
                if os.path.exists(dest):
                    continue
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                r = get_with_retry(sess, ESE_RAW_BASE + urllib.parse.quote(fp), timeout=30)
                write_atomic(dest, r.content)
                self.log.emit(f"📦 box.def: {cat}")
            except Exception as e:
                self.log.emit(f"box.def {cat}: {e}")


class BoxDefFetchThread(QThread):
    """Download one official box.def from ESE (used by the box.def editor)."""
    done = Signal(bool, str, str)    # ok, text or error, ESE path

    def __init__(self, ese_path):
        super().__init__()
        self.ese_path = ese_path

    def run(self):
        sess = new_session()
        try:
            r = get_with_retry(sess, ESE_RAW_BASE + urllib.parse.quote(self.ese_path),
                               timeout=30)
            self.done.emit(True, decode_tja_bytes(r.content), self.ese_path)
        except Exception as e:
            self.done.emit(False, str(e), self.ese_path)
        finally:
            sess.close()


# ---------------------------------------------------------------- prebuilt DB update
DB_NAMES = ("ese_songs.db", "ese_local.db")


def looks_like_version(text):
    """version.txt is one short line; reject HTML error/redirect pages."""
    return bool(text) and len(text) <= 64 and "\n" not in text and "<" not in text


def read_local_version():
    try:
        with open(VERSION_FILE, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def fetch_remote_version():
    """Published database version from GitHub Pages; "" if unreachable or invalid."""
    try:
        r = requests.get(DB_RELEASE_URL + "version.txt", timeout=10,
                         headers={"User-Agent": USER_AGENT})
        r.raise_for_status()
        text = r.text.strip()
        if looks_like_version(text):
            return text
        print("version: unexpected response, ignored")
    except Exception as e:
        print("version:", e)
    return ""


class VersionThread(QThread):
    result = Signal(str, str)  # remote, local

    def run(self):
        self.result.emit(fetch_remote_version(), read_local_version())


def update_databases(version="", log=print, tr=None):
    """Download the prebuilt databases from GitHub Pages, verify them against
    manifest.json, then swap them in together (rolling back on failure).
    Raises on any error; returns the installed version."""
    tr = tr or (lambda key, **kw: f"{key} {kw}")
    app_dir = os.path.dirname(DB_PATH)
    targets = [os.path.join(app_dir, n) for n in DB_NAMES]
    parts = [t + ".part" for t in targets]
    backups = []
    sess = new_session()
    try:
        r = get_with_retry(sess, DB_RELEASE_URL + "manifest.json", timeout=15)
        manifest = r.json()
        files = manifest["files"]
        for name, target, part in zip(DB_NAMES, targets, parts):
            log(tr("log_db_dl", n=name))
            want = (files.get(name) or {}).get("sha256")
            if not want:
                raise ValueError(tr("log_db_bad", n=name))
            h = hashlib.sha256()
            with get_with_retry(sess, DB_RELEASE_URL + name, stream=True, timeout=120) as r:
                with open(part, "wb") as f:
                    for chunk in r.iter_content(1 << 16):
                        if chunk:
                            f.write(chunk)
                            h.update(chunk)
            with open(part, "rb") as f:
                if f.read(16) != SQLITE_MAGIC:
                    raise ValueError(tr("log_db_bad", n=name))
            if h.hexdigest() != want:
                raise ValueError(tr("log_db_sha", n=name))
        # Swap both in; keep backups so a failed second replace can roll back.
        try:
            for target, part in zip(targets, parts):
                if os.path.exists(target):
                    bak = target + ".bak"
                    os.replace(target, bak)
                    backups.append((bak, target))
                os.replace(part, target)
        except Exception:
            for bak, target in backups:
                try:
                    os.replace(bak, target)
                except OSError:
                    pass
            backups = []
            raise
        installed = manifest.get("version") or version
        with open(VERSION_FILE, "w", encoding="utf-8") as f:
            f.write(installed)
        return installed
    finally:
        sess.close()
        for bak, _ in backups:
            try:
                os.remove(bak)
            except OSError:
                pass
        for part in parts:
            try:
                os.remove(part)
            except OSError:
                pass


class DBUpdateThread(QThread):
    log = Signal(str)
    done = Signal(bool, str)

    def __init__(self, version, tr=None):
        super().__init__()
        self.version = version
        self.tr = tr or (lambda key, **kw: key)

    def run(self):
        try:
            update_databases(self.version, log=self.log.emit, tr=self.tr)
            self.done.emit(True, "ok")
        except Exception as e:
            self.done.emit(False, str(e))


# ---------------------------------------------------------------- app update check
class AppUpdateThread(QThread):
    """Ask GitHub for the latest release; emit (tag, page_url) when it is newer
    than the running build. Silent on any error (offline, rate limit)."""
    found = Signal(str, str)

    def __init__(self, current=None):
        super().__init__()
        self.current = current or APP_VERSION

    def run(self):
        try:
            r = requests.get(LATEST_RELEASE_API, timeout=10,
                             headers={"User-Agent": USER_AGENT,
                                      "Accept": "application/vnd.github+json"})
            r.raise_for_status()
            data = r.json()
            tag = data.get("tag_name") or ""
            url = data.get("html_url") or ""
            if is_newer(tag, self.current) and url.startswith("https://github.com/"):
                self.found.emit(tag, url)
        except Exception as e:
            print("app update check:", e)


# ---------------------------------------------------------------- ESE-Version-Sorting
VSORT_MARKER = ".ese_commit"


def vsort_latest_commit(sess=None):
    """Latest commit id of the version-sorting repo (one small API request)."""
    sess = sess or new_session()
    r = get_with_retry(sess, VSORT_BRANCH_API, timeout=20)
    return r.json()["commit"]["id"]


def vsort_installed_commit(download_dir):
    try:
        with open(os.path.join(download_dir, VSORT_FOLDER, VSORT_MARKER), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def download_version_sorting(download_dir, log=print, force=False, sess=None):
    """Download Yonokid/ESE-Version-Sorting as one zip archive and install it
    as <download_dir>/ESE-Version-Sorting (YataiDON version folders).

    Skips the download when the installed commit is already the latest. The
    new copy is extracted next to the old one and swapped in only when complete.
    Returns (status, commit): status is "updated" or "latest".
    """
    import shutil
    import tempfile
    import zipfile

    own = sess is None
    sess = sess or new_session()
    try:
        commit = vsort_latest_commit(sess)
        if not force and vsort_installed_commit(download_dir) == commit:
            return "latest", commit
        os.makedirs(download_dir, exist_ok=True)
        target = os.path.join(download_dir, VSORT_FOLDER)
        work = tempfile.mkdtemp(prefix=".vsort-", dir=download_dir)
        try:
            archive = os.path.join(work, "repo.zip")
            log(f"⬇ {VSORT_REPO} ({commit[:7]})")
            with get_with_retry(sess, VSORT_ARCHIVE_URL.format(ref=commit),
                                stream=True, timeout=120) as r:
                with open(archive, "wb") as f:
                    for chunk in r.iter_content(1 << 16):
                        if chunk:
                            f.write(chunk)
            staging = os.path.join(work, VSORT_FOLDER)
            os.makedirs(staging)
            count = 0
            with zipfile.ZipFile(archive) as z:
                for info in z.infolist():
                    # Archives wrap everything in one top folder ("ese-version-sorting/").
                    parts = info.filename.replace("\\", "/").split("/", 1)
                    if len(parts) < 2 or not parts[1] or info.is_dir():
                        continue
                    if (info.external_attr >> 16) & 0o170000 == 0o120000:
                        continue                       # never extract symlinks
                    dest = safe_join(staging, parts[1])   # rejects ../ and absolute paths
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with z.open(info) as src, open(dest, "wb") as out:
                        shutil.copyfileobj(src, out)
                    count += 1
            if count == 0:
                raise IOError("archive is empty")
            with open(os.path.join(staging, VSORT_MARKER), "w", encoding="utf-8") as f:
                f.write(commit)
            # Swap: old -> backup, new -> target, then drop the backup.
            backup = os.path.join(work, "old")
            if os.path.exists(target):
                os.replace(target, backup)
            try:
                os.replace(staging, target)
            except OSError:
                if os.path.exists(backup):
                    os.replace(backup, target)
                raise
            log(f"✓ {VSORT_FOLDER}: {count} files")
            return "updated", commit
        finally:
            shutil.rmtree(work, ignore_errors=True)
    finally:
        if own:
            sess.close()


class VersionSortingThread(QThread):
    log = Signal(str)
    done = Signal(bool, str, str)    # ok, "updated"/"latest" or error, commit

    def __init__(self, download_dir):
        super().__init__()
        self.download_dir = download_dir

    def run(self):
        try:
            status, commit = download_version_sorting(self.download_dir, log=self.log.emit)
            self.done.emit(True, status, commit)
        except Exception as e:
            self.done.emit(False, str(e), "")
