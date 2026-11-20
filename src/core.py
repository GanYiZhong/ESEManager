"""ESEManager logic without Qt: search, downloads, update checks, database and
ESE-Version-Sorting updates. Used by the GUI (through thin QThread wrappers in
workers.py) and directly by the command line (cli.py).

Paths and URLs are read from this module's globals at call time, so tests can
monkeypatch core.DB_PATH and friends.
"""

import hashlib
import logging
import logging.handlers
import os
import pathlib
import shutil
import sqlite3
import tempfile
import threading
import time
import urllib.parse
import zipfile
from concurrent.futures import ThreadPoolExecutor

import requests

from appconfig import (APP_DIR, DB_PATH, LOCAL_DB_PATH, VERSION_FILE, ESE_RAW_BASE,
                       DB_RELEASE_URL, USER_AGENT, SQLITE_MAGIC, live_url, safe_join,
                       UnsafePathError, LATEST_RELEASE_API, is_newer,
                       VSORT_REPO, VSORT_FOLDER, VSORT_SKIP, VSORT_BRANCH_API,
                       VSORT_ARCHIVE_URL)

__all__ = ["UnsafePathError"]   # re-exported for callers that catch it

log = logging.getLogger("ESEManager")

# ESE stores these through Git LFS: the blob sha recorded by `git ls-tree` is the
# sha of the small LFS pointer file, not of the audio, so it cannot be compared
# with a downloaded file. (ESE's .gitattributes: "*.ogg filter=lfs".)
LFS_EXTS = {".ogg"}

RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}


# ---------------------------------------------------------------- logging
def setup_logging(console=False):
    """Log warnings and errors to ESEManager.log next to the app (rotated at
    1 MB). A windowed build has no console, so this is where problems end up."""
    if getattr(setup_logging, "_done", False):
        return
    setup_logging._done = True
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    try:
        fh = logging.handlers.RotatingFileHandler(
            os.path.join(APP_DIR, "ESEManager.log"), maxBytes=1 << 20, backupCount=1,
            encoding="utf-8", delay=True)
        fh.setFormatter(fmt)
        log.addHandler(fh)
    except OSError:
        pass
    if console:
        sh = logging.StreamHandler()
        sh.setLevel(logging.WARNING)
        sh.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        log.addHandler(sh)


# ---------------------------------------------------------------- small helpers
def is_lfs_path(path):
    return os.path.splitext(path)[1].lower() in LFS_EXTS


def human_speed(mbps):
    if mbps <= 0:
        return "—"
    if mbps < 1:
        return f"{mbps*1024:.0f} KB/s"
    return f"{mbps:.2f} MB/s"


def human_eta(sec):
    if sec is None or sec <= 0 or sec == float("inf"):
        return "—"
    sec = int(sec)
    if sec < 60:
        return f"{sec}s"
    m, s = divmod(sec, 60)
    if m < 60:
        return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m"


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
            # Sleep in short steps so a cancel takes effect during the backoff.
            end = time.monotonic() + delay
            while time.monotonic() < end:
                if stop and stop():
                    raise
                time.sleep(0.1)
            delay *= 2


def connect_ro(path):
    """Open a SQLite database read-only. Unlike sqlite3.connect(path) this never
    creates an empty file when the database is missing (it raises instead)."""
    return sqlite3.connect(pathlib.Path(os.path.abspath(path)).as_uri() + "?mode=ro",
                           uri=True)


def sqlite_ok(path):
    """True when path is a readable SQLite database that passes a quick check."""
    try:
        conn = connect_ro(path)
        try:
            return conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        finally:
            conn.close()
    except sqlite3.Error:
        return False


def write_atomic(path, data):
    part = path + ".part"
    with open(part, "wb") as f:
        f.write(data)
    os.replace(part, path)


def has_song_db():
    return os.path.exists(DB_PATH) and os.path.getsize(DB_PATH) > 0


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
    except Exception:
        log.warning("load_jp_map failed", exc_info=True)
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
    except Exception:
        log.warning("load_meta_map failed", exc_info=True)
    return m


def list_categories():
    """Category names in the song database ([] when there is none)."""
    if not os.path.exists(DB_PATH):
        return []
    conn = connect_ro(DB_PATH)
    try:
        return [n for (n,) in conn.execute(
            "SELECT DISTINCT name FROM categories ORDER BY name")]
    finally:
        conn.close()


def count_songs():
    """Number of songs that have files (box.def rows excluded)."""
    conn = connect_ro(DB_PATH)
    try:
        return conn.execute(
            "SELECT COUNT(DISTINCT song_id) FROM song_files "
            "WHERE lower(filename) != 'box.def'").fetchone()[0]
    finally:
        conn.close()


# ---------------------------------------------------------------- search
def has_cjk(text):
    return any('぀' <= c <= 'ヿ' or '一' <= c <= '鿿' for c in text or "")


def _query_songs(conn, keyword=None, category=None):
    """Songs with their files in one query (no N+1). Box.def rows are dropped
    and songs without files are left out."""
    query = """
        SELECT s.id, s.song_name, c.name, s.base_path,
               f.filename, f.file_path, f.file_type, f.size, f.download_url
        FROM songs s
        LEFT JOIN categories c ON s.category_id = c.id
        JOIN song_files f ON f.song_id = s.id
        WHERE lower(f.filename) != 'box.def'
    """
    params = []
    if keyword:
        query += " AND s.song_name LIKE ?"
        params.append(f"%{keyword}%")
    if category:
        query += " AND c.name LIKE ?"
        params.append(f"%{category}%")
    query += " ORDER BY s.id, f.file_type"
    songs = {}
    for sid, name, cat, base, fn, fp, ftype, size, url in conn.execute(query, params):
        song = songs.get(sid)
        if song is None:
            song = songs[sid] = {"song_name": name, "category": cat,
                                 "base_path": base, "files": []}
        song["files"].append({"filename": fn, "file_path": fp, "file_type": ftype,
                              "size": size, "download_url": url})
    return list(songs.values())


def search_songs(keyword, category=None):
    """Search the song database. A Japanese keyword also matches songs whose
    Japanese title (from the local title database) contains it. Shared by the
    GUI and the command line."""
    conn = connect_ro(DB_PATH)
    try:
        songs = _query_songs(conn, keyword or None, category)
        if keyword and has_cjk(keyword) and os.path.exists(LOCAL_DB_PATH):
            lconn = connect_ro(LOCAL_DB_PATH)
            try:
                titles = {r[0].lower() for r in lconn.execute(
                    "SELECT title FROM local_songs WHERE title_ja LIKE ?",
                    (f"%{keyword}%",)) if r[0]}
            finally:
                lconn.close()
            if titles:
                # Match in Python: one query, no limit on the number of titles.
                seen = {(s["song_name"], s["category"]) for s in songs}
                for s in _query_songs(conn, None, category):
                    name = (s["song_name"] or "").lower()
                    key = (s["song_name"], s["category"])
                    if key not in seen and any(t in name for t in titles):
                        seen.add(key)
                        songs.append(s)
    finally:
        conn.close()
    return songs


def find_missing(songs, download_dir):
    """Songs with at least one file not present in download_dir."""
    missing = []
    for s in songs:
        for f in s["files"]:
            try:
                path = safe_join(download_dir, f["file_path"])
            except UnsafePathError:
                continue
            if not os.path.exists(path):
                missing.append(s)
                break
    return missing


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


class NoShaError(Exception):
    """The song database predates blob_sha; update checks need a newer one."""


def find_updates(download_dir, category=None, progress=None):
    """Downloaded files whose upstream content changed (git blob sha). Returns
    songs holding only the changed files, plus the song's LFS audio (an updated
    chart usually ships with new audio). LFS files themselves are not compared:
    their recorded sha belongs to the pointer file."""
    progress = progress or (lambda done, total: None)
    songs = search_songs(None, category)
    sha_map = load_sha_map()
    if not sha_map:
        raise NoShaError()

    candidates = []     # (song, file, local_path, remote_sha)
    for s in songs:
        for f in s["files"]:
            fp = f["file_path"]
            if is_lfs_path(fp):
                continue
            sha = sha_map.get(fp)
            if not sha:
                continue
            try:
                lp = safe_join(download_dir, fp)
            except UnsafePathError:
                continue
            if os.path.exists(lp):
                candidates.append((s, f, lp, sha))

    total = len(candidates)
    progress(0, total)

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
                progress(done, total)
            if res:
                s, f = res
                entry = changed.setdefault(id(s), dict(s, files=[], _orig=s))
                entry["files"].append(f)

    out = []
    for entry in changed.values():
        orig = entry.pop("_orig")
        have = {f["file_path"] for f in entry["files"]}
        entry["files"] += [f for f in orig["files"]
                           if is_lfs_path(f["file_path"]) and f["file_path"] not in have]
        out.append(entry)
    return out


# ---------------------------------------------------------------- downloads
class Downloader:
    """Download (song, file) pairs in parallel into download_dir.

    Each file is written to <name>.part, checked (length, git blob sha for
    non-LFS files) and only then moved into place, so an interrupted or bad
    download never replaces a good file. Progress is kept in shared counters
    that the caller polls with snapshot() (the GUI every ~200 ms), instead of
    a callback per chunk.
    """

    def __init__(self, files, download_dir, workers, overwrite=False, tr=None, log=None):
        self.files = files
        self.download_dir = download_dir
        self.workers = max(1, workers)
        self.overwrite = overwrite     # True = replace existing files (update mode)
        self.tr = tr or (lambda key, **kw: key)
        self.log = log or (lambda msg: None)
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
        """Counters plus the rows that changed since the previous call."""
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
        try:
            # On first download into a category folder, also fetch ESE's box.def.
            self._fetch_boxdefs(sess)
            with ThreadPoolExecutor(max_workers=self.workers) as ex:
                list(ex.map(lambda item: self._one(sess, sha_map, item), self.files))
        finally:
            sess.close()
        return self.dl, self.skip, self.fail, self.total

    def _one(self, sess, sha_map, item):
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
                                stop=lambda: self._stop) as r:
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
            self.log(f"✓ {disp} ({got/1024/1024:.2f} MB)")
        except Exception as e:
            with self._lock:
                self.failed.append((song, f))
            self._count("fail")
            self._mark(fp, "failed", 0.0, 0.0)
            self.log(self.tr("log_fail", f=disp, e=e))
        finally:
            if part and os.path.exists(part):
                try:
                    os.remove(part)
                except OSError:
                    pass

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
                r = get_with_retry(sess, ESE_RAW_BASE + urllib.parse.quote(fp), timeout=30,
                                   stop=lambda: self._stop)
                write_atomic(dest, r.content)
                self.log(f"📦 box.def: {cat}")
            except Exception as e:
                self.log(f"box.def {cat}: {e}")


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


def fetch_remote_version(timeout=10):
    """Published database version from GitHub Pages; "" if unreachable or invalid."""
    try:
        r = requests.get(DB_RELEASE_URL + "version.txt", timeout=timeout,
                         headers={"User-Agent": USER_AGENT})
        r.raise_for_status()
        text = r.text.strip()
        if looks_like_version(text):
            return text
        log.warning("version.txt: unexpected response, ignored")
    except Exception as e:
        log.warning("version.txt: %s", e)
    return ""


def update_databases(version="", log=print, tr=None):
    """Download the prebuilt databases from GitHub Pages, verify them against
    manifest.json (sha256) and with SQLite's own check, then swap them in
    together (rolling back on failure). Raises on any error; returns the
    installed version."""
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
            if not sqlite_ok(part):
                raise ValueError(tr("log_db_bad", n=name))
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
        write_atomic(VERSION_FILE, installed.encode("utf-8"))
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


# ---------------------------------------------------------------- app update check
def latest_app_release(current):
    """(tag, page_url) of the latest GitHub release when it is newer than
    `current`; None otherwise or on any error (offline, rate limit)."""
    try:
        r = requests.get(LATEST_RELEASE_API, timeout=10,
                         headers={"User-Agent": USER_AGENT,
                                  "Accept": "application/vnd.github+json"})
        r.raise_for_status()
        data = r.json()
        tag = data.get("tag_name") or ""
        url = data.get("html_url") or ""
        if is_newer(tag, current) and url.startswith("https://github.com/"):
            return tag, url
    except Exception as e:
        log.info("app update check: %s", e)
    return None


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
    own = sess is None
    sess = sess or new_session()
    try:
        commit = vsort_latest_commit(sess)
        if not force and vsort_installed_commit(download_dir) == commit:
            # Earlier versions installed the skipped folders; remove them now.
            for name in os.listdir(os.path.join(download_dir, VSORT_FOLDER)):
                path = os.path.join(download_dir, VSORT_FOLDER, name)
                if name.lower() in VSORT_SKIP and os.path.isdir(path):
                    shutil.rmtree(path, ignore_errors=True)
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
                    if parts[1].split("/", 1)[0].lower() in VSORT_SKIP:
                        continue                       # e.g. Template/: not for players
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
