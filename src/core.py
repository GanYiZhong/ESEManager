"""ESEManager logic without Qt: search, downloads, update checks, database and
ESE-Version-Sorting updates. Used by the GUI (through thin QThread wrappers in
workers.py) and directly by the command line (cli.py).

Paths and URLs are read from this module's globals at call time, so tests can
monkeypatch core.DB_PATH and friends.
"""

import collections
import hashlib
import json
import logging
import logging.handlers
import os
import pathlib
import re
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
import unicodedata
import urllib.parse
import zipfile
from concurrent.futures import ThreadPoolExecutor



class LazyModule:
    """Import a heavy module on first attribute access, so startup does not pay
    for it (requests + urllib3 cost ~0.2 s). Reads and writes pass through, so
    `core.requests.get` can still be patched in tests."""

    __slots__ = ("_name", "_mod")

    def __init__(self, name):
        object.__setattr__(self, "_name", name)
        object.__setattr__(self, "_mod", None)

    def _load(self):
        mod = object.__getattribute__(self, "_mod")
        if mod is None:
            import importlib
            mod = importlib.import_module(object.__getattribute__(self, "_name"))
            object.__setattr__(self, "_mod", mod)
        return mod

    @property
    def __dict__(self):          # lets monkeypatch save/restore the real attribute
        return self._load().__dict__

    def __getattr__(self, attr):
        return getattr(self._load(), attr)

    def __setattr__(self, attr, value):
        setattr(self._load(), attr, value)


requests = LazyModule("requests")

from appconfig import (APP_DIR, DB_PATH, LOCAL_DB_PATH, VERSION_FILE, ESE_RAW_BASE,
                       ESE_MIRROR_BASE,
                       DB_RELEASE_URL, USER_AGENT, SQLITE_MAGIC, live_url, safe_join,
                       UnsafePathError, LATEST_RELEASE_API, is_newer,
                       APP_VERSION, parse_version,
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


_env_proxy_cache = {}
_orig_get_environ_proxies = None


def _cached_environ_proxies(url, no_proxy=None):
    """requests re-reads the proxy environment (the Windows registry, too) on
    every request; for thousands of small files that dominates. Cache it per
    host, until the next new_session()."""
    parts = urllib.parse.urlsplit(url)
    key = (parts.scheme, parts.netloc, no_proxy)
    try:
        return dict(_env_proxy_cache[key])
    except KeyError:
        val = _orig_get_environ_proxies(url, no_proxy=no_proxy)
        _env_proxy_cache[key] = dict(val)
        return val


def new_session(pool_size=10):
    global _orig_get_environ_proxies
    _env_proxy_cache.clear()
    if _orig_get_environ_proxies is None:       # first use: requests loads lazily
        _orig_get_environ_proxies = requests.sessions.get_environ_proxies
        requests.sessions.get_environ_proxies = _cached_environ_proxies
    sess = requests.Session()
    sess.headers["User-Agent"] = USER_AGENT
    if pool_size > 10:      # requests' default pool is 10 connections per host
        ad = requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=pool_size)
        sess.mount("http://", ad)
        sess.mount("https://", ad)
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


class ChecksumError(RuntimeError):
    """A downloaded file does not match its published checksum."""


class AllHostsFailed(Exception):
    """Every candidate host failed for one file; `hosts` lists the hosts tried
    and `last` is the final underlying error."""

    def __init__(self, hosts, last):
        super().__init__(f"{', '.join(hosts)}: {last}")
        self.hosts = hosts
        self.last = last


def _default_tr(key, **kw):
    from i18n import TR
    s = TR["en"].get(key, key)
    return s.format(**kw) if kw else s


def _error_key(exc):
    """i18n key for the kind of failure `exc` is, or None when unknown."""
    import errno
    import ssl
    if isinstance(exc, ChecksumError):
        return "err_checksum"
    if isinstance(exc, requests.HTTPError):
        code = getattr(exc.response, "status_code", 0) or 0
        if code in (403, 429):
            return "err_rate_limit"
        if code == 404:
            return "err_not_found"
        if code >= 500:
            return "err_server"
        return None
    if isinstance(exc, (requests.exceptions.SSLError, ssl.SSLError)):
        return "err_tls"
    if isinstance(exc, (requests.Timeout, TimeoutError)):
        return "err_timeout"
    if isinstance(exc, requests.ConnectionError):
        # Some timeouts surface as ConnectionError wrapping a read timeout.
        return "err_timeout" if "timed out" in str(exc).lower() else "err_offline"
    if isinstance(exc, OSError):
        code = getattr(exc, "errno", None)
        if code == errno.ENOSPC:
            return "err_disk_full"
        if code in (errno.EACCES, errno.EPERM) or isinstance(exc, PermissionError):
            return "err_permission"
    return None


def friendly_error(exc, tr=None):
    """Short localized message for a failure. Unknown errors fall back to the
    exception's own text. Keep the technical detail in the log, not the UI."""
    tr = tr or _default_tr
    if isinstance(exc, AllHostsFailed):
        msg = friendly_error(exc.last, tr)
        return msg + tr("err_tried", hosts=", ".join(exc.hosts))
    key = _error_key(exc)
    if key:
        return tr(key)
    return str(exc) or exc.__class__.__name__


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


def norm_text(text):
    """Search key: NFKC (full-width -> half-width, half-width kana -> full-width),
    case-folded, katakana folded to hiragana, so 'ＬＯＶＥ' finds 'love' and
    'ミク' finds 'みく'."""
    t = unicodedata.normalize("NFKC", text or "").casefold()
    if any('ァ' <= c <= 'ヶ' for c in t):
        t = "".join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in t)
    return t


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


def _stamp(path):
    try:
        st = os.stat(path)
        return (path, st.st_mtime_ns, st.st_size)
    except OSError:
        return (path, None, None)


class _SongIndex:
    """All songs loaded once, with normalized search keys, so a keystroke is a
    Python substring scan instead of a database round trip."""

    def __init__(self):
        conn = connect_ro(DB_PATH)
        try:
            self.songs = _query_songs(conn)
        finally:
            conn.close()
        self.names = [norm_text(s["song_name"]) for s in self.songs]
        self.cats = [norm_text(s["category"]) for s in self.songs]
        self.cnames = [_compact(n) for n in self.names]
        self._ja = None          # [(title_ja, compact title_ja, title)] normalized, lazy

    def ja_titles(self):
        if self._ja is None:
            pairs = set()
            if os.path.exists(LOCAL_DB_PATH):
                try:
                    lconn = connect_ro(LOCAL_DB_PATH)
                    try:
                        for title, ja in lconn.execute(
                                "SELECT title, title_ja FROM local_songs "
                                "WHERE title_ja IS NOT NULL AND title_ja != ''"):
                            if title and norm_text(title):
                                nja = norm_text(ja)
                                pairs.add((nja, _compact(nja), norm_text(title)))
                    finally:
                        lconn.close()
                except sqlite3.Error:
                    log.warning("title lookup failed", exc_info=True)
            self._ja = list(pairs)
        return self._ja


_index = None
_index_key = None
_index_lock = threading.Lock()


def _song_index():
    global _index, _index_key
    key = (_stamp(DB_PATH), _stamp(LOCAL_DB_PATH))
    with _index_lock:
        if _index is None or _index_key != key:
            _index = _SongIndex()
            _index_key = key
        return _index


def clear_search_cache():
    global _index, _index_key
    with _index_lock:
        _index = _index_key = None


def _compact(text):
    """Letters and digits only (any script): 'a-b c' -> 'abc'."""
    return "".join(c for c in text if c.isalnum())


def _tier(text, kw):
    """Match quality of normalized `kw` inside normalized `text`: 0 exact,
    1 prefix, 2 word-boundary, 3 substring, None no match."""
    pos = text.find(kw)
    if pos < 0:
        return None
    if text == kw:
        return 0
    if pos == 0:
        return 1
    while pos >= 0:
        if not text[pos - 1].isalnum():
            return 2
        pos = text.find(kw, pos + 1)
    return 3


def _score(text, ctext, kw, words, ckw):
    """Rank of one normalized title for the query (lower is better, None = no
    match). 0-3: whole query as a phrase (see _tier); 4/5: every word present
    in any order (first word is a prefix / not); 6: equal once spaces and
    punctuation are ignored ('365nichi' ~ '365 nichi no ...')."""
    t = _tier(text, kw)
    if t is not None:
        return t
    if len(words) > 1 and all(w in text for w in words):
        return 4 if text.startswith(words[0]) else 5
    if ckw and ckw in ctext:
        return 6
    return None


def search_songs(keyword, category=None):
    """Search the song database. Matching is width-, case- and kana-insensitive
    and ignores spaces/punctuation; several words must all match, in any
    order. A Japanese keyword also matches songs whose Japanese title (from
    the local title database) matches. With a keyword the results are ranked
    (exact title > prefix > word boundary > substring > multi-word >
    punctuation-insensitive), ties keep database order. Shared by the GUI and
    the command line. The song list is cached until a database file changes."""
    idx = _song_index()
    kw = " ".join(norm_text(keyword).split()) if keyword else ""
    cat = norm_text(category).strip() if category else ""
    cand = [i for i in range(len(idx.songs)) if not cat or cat in idx.cats[i]]
    if not kw:
        out = cand
    else:
        words = list(dict.fromkeys(kw.split()))
        kw = " ".join(words)
        ckw = _compact(kw)
        best = {}
        for i in cand:
            sc = _score(idx.names[i], idx.cnames[i], kw, words, ckw)
            if sc is not None:
                best[i] = sc
        if has_cjk(keyword):
            by_title = {}
            for ja, cja, t in idx.ja_titles():
                sc = _score(ja, cja, kw, words, ckw)
                if sc is not None and sc < by_title.get(t, 99):
                    by_title[t] = sc
            if by_title:
                # this song's own Japanese title ranks as such; longer names
                # merely containing it count as a substring hit (>= 3)
                groups = {}
                for t, sc in by_title.items():
                    groups.setdefault(max(sc, 3), []).append(t)
                pats = sorted(((sc, re.compile("|".join(map(re.escape, ts))))
                              for sc, ts in groups.items()), key=lambda p: p[0])
                for i in cand:
                    name = idx.names[i]
                    sc = by_title.get(name)
                    if sc is None:
                        sc = next((g for g, pat in pats if pat.search(name)), None)
                    if sc is not None and sc < best.get(i, 99):
                        best[i] = sc
        out = sorted(best, key=lambda i: (best[i], i))
    # Callers get their own dicts, so mutating a result cannot corrupt the cache.
    return [dict(idx.songs[i], files=list(idx.songs[i]["files"])) for i in out]


def _rel_key(rel):
    """Normalised lookup key for a database-relative path, or None if it is
    unsafe (same rules as safe_join, without the per-path abspath cost)."""
    if not rel:
        return None
    norm = rel.replace("\\", "/")
    if norm.startswith("/") or (len(norm) > 1 and norm[1] == ":"):
        return None
    parts = [p for p in norm.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." or "\0" in p or ":" in p for p in parts):
        return None
    key = "/".join(parts)
    return key.lower() if os.name == "nt" else key


def scan_tree(root):
    """One scandir walk of root: {key: (mtime_ns, size)} for every file, keyed
    like _rel_key. DirEntry.stat() reuses the listing data on Windows, so this
    costs one directory read per folder instead of one stat per file."""
    out = {}
    stack = [(root, "")]
    lower = os.name == "nt"
    while stack:
        d, prefix = stack.pop()
        try:
            it = os.scandir(d)
        except OSError:
            continue
        with it:
            for e in it:
                try:
                    name = e.name.lower() if lower else e.name
                    if e.is_dir(follow_symlinks=False):
                        stack.append((e.path, prefix + name + "/"))
                    else:
                        st = e.stat()
                        out[prefix + name] = (st.st_mtime_ns, st.st_size)
                except OSError:
                    continue
    return out


def find_missing(songs, download_dir):
    """Songs with at least one file not present in download_dir. A single
    directory walk replaces one os.path.exists per file; for a handful of
    files the plain existence check is cheaper, so it is kept for those."""
    songs = list(songs)
    nfiles = sum(len(s["files"]) for s in songs)
    present = None
    if nfiles > 64:
        present = scan_tree(download_dir)
    missing = []
    for s in songs:
        for f in s["files"]:
            if present is None:
                try:
                    path = safe_join(download_dir, f["file_path"])
                except UnsafePathError:
                    continue
                gone = not os.path.exists(path)
            else:
                key = _rel_key(f["file_path"])
                if key is None:
                    continue
                gone = key not in present
            if gone:
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
# paths whose on-disk cache entry must not be trusted (file replaced by us)
_sha_forgotten = set()

SHA_CACHE_NAME = ".ese_sha_cache.json"
SHA_CACHE_VERSION = 1


def load_sha_disk_cache(download_dir):
    """{key: [mtime_ns, size, sha]} saved by a previous check, or {} if absent,
    corrupt or from another format version."""
    try:
        with open(os.path.join(download_dir, SHA_CACHE_NAME), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if data.get("v") != SHA_CACHE_VERSION or not isinstance(data.get("files"), dict):
            return {}
        return {k: tuple(v) for k, v in data["files"].items()
                if isinstance(v, list) and len(v) == 3}
    except (OSError, ValueError, AttributeError):
        return {}


def save_sha_disk_cache(download_dir, files):
    """Atomically write the cache (temp file + os.replace). Failure is harmless."""
    path = os.path.join(download_dir, SHA_CACHE_NAME)
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"v": SHA_CACHE_VERSION,
                       "files": {k: list(v) for k, v in files.items()}},
                      fh, separators=(",", ":"))
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass


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


def forget_blob_sha(path):
    """Drop a cached hash, e.g. after replacing the file. The cache key is
    (mtime, size), which a same-size rewrite within the file system's time
    resolution would not change."""
    with _sha_cache_lock:
        _sha_cache.pop(path, None)
        _sha_forgotten.add(os.path.normcase(os.path.abspath(path)))


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

    present = scan_tree(download_dir)
    candidates = []     # (song, file, key, remote_sha)
    for s in songs:
        for f in s["files"]:
            fp = f["file_path"]
            if is_lfs_path(fp):
                continue
            sha = sha_map.get(fp)
            if not sha:
                continue
            key = _rel_key(fp)
            if key is not None and key in present:
                candidates.append((s, f, key, sha))

    total = len(candidates)
    progress(0, total)

    disk = load_sha_disk_cache(download_dir)
    base = os.path.abspath(download_dir)
    fresh = {}          # key -> (mtime_ns, size, sha) for files seen this run
    shas = {}           # key -> local sha
    todo = []           # keys that need hashing
    with _sha_cache_lock:
        forgotten = set(_sha_forgotten)
    for _, f, key, _ in candidates:
        mt, size = present[key]
        full = os.path.normcase(os.path.join(base, *key.split("/")))
        hit = disk.get(key)
        if hit and hit[0] == mt and hit[1] == size and full not in forgotten:
            fresh[key] = hit
            shas[key] = hit[2]
        else:
            todo.append((key, f["file_path"]))

    done = total - len(todo)
    last = [0.0]

    def report(force=False):
        now = time.monotonic()
        if force or now - last[0] >= 0.05:
            last[0] = now
            progress(done, total)

    report(True)

    def hash_one(item):
        key, fp = item
        try:
            return key, git_blob_sha(safe_join(download_dir, fp))
        except (OSError, UnsafePathError):
            return key, None

    if todo:
        with ThreadPoolExecutor(max_workers=min(16, (os.cpu_count() or 4) * 2)) as ex:
            for key, sha in ex.map(hash_one, todo, chunksize=1):
                done += 1
                if sha is not None:
                    mt, size = present[key]
                    shas[key] = sha
                    fresh[key] = (mt, size, sha)
                report(done == total)
        with _sha_cache_lock:
            for key, _ in todo:
                _sha_forgotten.discard(os.path.normcase(os.path.join(base, *key.split("/"))))
    report(True)

    # keep entries for files still on disk (other categories), drop deleted ones
    keep = {k: v for k, v in disk.items() if k in present}
    keep.update(fresh)
    if keep != disk:
        save_sha_disk_cache(download_dir, keep)

    changed = {}    # id(song) -> song dict with only the changed files
    for s, f, key, sha in candidates:
        local = shas.get(key)
        if local is not None and local != sha:
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
_download_source = "ese"
PART_MAX_AGE = 24 * 3600        # seconds a stopped download's .part may be resumed


def set_download_source(pref):
    """Preferred download host from config (download.source): a name from
    DOWNLOAD_SOURCES or an http(s) base URL. Unknown values mean "ese"."""
    global _download_source
    _download_source = pref if isinstance(pref, str) and pref.strip() else "ese"


def source_bases(pref=None):
    """Base URLs to try for a song file, preferred first; the other known
    hosts follow as fallbacks (they serve the same repository paths)."""
    pref = (pref or _download_source).strip()
    known = {"ese": ESE_RAW_BASE, "taiko.ac": ESE_MIRROR_BASE}
    first = known.get(pref)
    if first is None and pref.lower().startswith(("http://", "https://")):
        first = pref if pref.endswith("/") else pref + "/"
    first = first or ESE_RAW_BASE
    return [first] + [b for b in (ESE_RAW_BASE, ESE_MIRROR_BASE) if b != first]


def _host(url):
    return urllib.parse.urlsplit(url).netloc or url


class Downloader:
    """Download (song, file) pairs in parallel into download_dir.

    Each file is written to <name>.part, checked (length, git blob sha for
    non-LFS files) and only then moved into place, so an interrupted or bad
    download never replaces a good file. Progress is kept in shared counters
    that the caller polls with snapshot() (the GUI every ~200 ms), instead of
    a callback per chunk.
    """

    def __init__(self, files, download_dir, workers, overwrite=False, tr=None, log=None,
                 bases=None):
        self.files = files
        # Hosts tried in order for each file; a host that works after the
        # first one failed moves to the front for the rest of the job.
        self.bases = list(bases) if bases else source_bases()
        self._switched = set()
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
        self._samples = collections.deque()   # (time, bytes_total, done) for rates

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
            now = time.time()
            el = now - self.t0
            # Rates over a sliding window (~8 s) so speed/ETA follow the
            # current pace instead of the whole-job average.
            sm = self._samples
            sm.append((now, self.bytes_total, self.done))
            while len(sm) > 2 and now - sm[0][0] > 8.0:
                sm.popleft()
            t_old, b_old, d_old = sm[0]
            win = now - t_old
            if win >= 1.0:
                spd = (self.bytes_total - b_old) / 1024 / 1024 / win
                rate = (self.done - d_old) / win
            else:
                spd = (self.bytes_total / 1024 / 1024) / el if el > 0 else 0
                rate = self.done / el if el > 0 else 0
            if rate <= 0 and self.done > 0 and el > 0:
                rate = self.done / el
            eta = (self.total - self.done) / rate if rate > 0 and self.done < self.total else 0
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
        sess = new_session(self.workers + 2)
        try:
            sha_map = load_sha_map()
        except Exception:
            sha_map = {}
        try:
            # On first download into a category folder, also fetch ESE's box.def.
            self._fetch_boxdefs(sess)
            with ThreadPoolExecutor(max_workers=self.workers) as ex:
                # Small files (charts) before LFS audio: the list fills quickly
                # and a stop leaves complete charts rather than half an .ogg.
                order = sorted(self.files, key=lambda it: is_lfs_path(it[1]["file_path"]))
                list(ex.map(lambda item: self._one(sess, sha_map, item), order))
        finally:
            sess.close()
        return self.dl, self.skip, self.fail, self.total

    def _urls(self, f):
        """Candidate URLs for one file: the known hosts (same repository paths)
        in the current order. A recorded link to some other host (an old
        database row, a test server) is tried first."""
        fp = f["file_path"]
        q = urllib.parse.quote(fp)
        with self._lock:
            bases = list(self.bases)
        urls = [b + q for b in bases]
        rec = live_url(f["download_url"] or "")
        if rec and rec not in urls and not rec.startswith(ESE_RAW_BASE):
            urls.insert(0, rec)
        return urls

    def _worked(self, url):
        """Move the host that served `url` to the front (logged once)."""
        with self._lock:
            base = next((b for b in self.bases if url.startswith(b)), None)
            if base is None or self.bases[0] == base:
                return
            self.bases.remove(base)
            self.bases.insert(0, base)
            first = base not in self._switched
            self._switched.add(base)
        if first:
            self.log(self.tr("log_mirror", host=_host(base)))

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
            part = save_path + ".part"
            want = sha_map.get(fp)
            check = want if want and not is_lfs_path(fp) else None
            err = None
            tried = []
            for url in self._urls(f):
                if self._stop:
                    raise InterruptedError(self.tr("log_cancelled"))
                try:
                    got = self._fetch(sess, url, part, fp, check)
                    self._worked(url)
                    break
                except InterruptedError:
                    raise
                except Exception as e:              # try the next host
                    log.info("%s: %s", url, e)
                    err = e
                    tried.append(_host(url))
            else:
                if err is None:
                    raise IOError("no download source")
                raise AllHostsFailed(tried, err) from err
            os.replace(part, save_path)
            part = None
            forget_blob_sha(save_path)
            self._count("dl")
            self._mark(fp, "done", 100.0, 0.0)
            self.log(f"✓ {disp} ({got/1024/1024:.2f} MB)")
        except Exception as e:
            with self._lock:
                self.failed.append((song, f))
            self._count("fail")
            self._mark(fp, "failed", 0.0, 0.0)
            log.warning("download failed: %s", disp, exc_info=True)
            self.log(self.tr("log_fail", f=disp, e=friendly_error(e, self.tr)))
        finally:
            # A stopped download keeps its .part so the next run can resume it
            # with a Range request; any other failure discards it.
            if part and os.path.exists(part) and not self._stop:
                try:
                    os.remove(part)
                except OSError:
                    pass

    def _fetch(self, sess, url, part, fp, want_sha):
        """Download url into part and check its length and (non-LFS) git blob
        sha. Returns the byte count; raises on any problem. A leftover .part
        is resumed with a Range request when the server honours it."""
        got = 0
        have = os.path.getsize(part) if os.path.exists(part) else 0
        # Audio (LFS) has no hash to catch a resume onto a file that changed
        # upstream since; only resume recent leftovers.
        if have and time.time() - os.path.getmtime(part) > PART_MAX_AGE:
            os.remove(part)
            have = 0
        hdrs = {"Range": f"bytes={have}-"} if have > 0 else {}
        try:
            resp = get_with_retry(sess, url, stream=True, timeout=60, headers=hdrs,
                                  stop=lambda: self._stop)
        except requests.HTTPError as e:
            if have and getattr(e.response, "status_code", 0) == 416:
                have, hdrs = 0, {}          # stale/oversized part: start over
                resp = get_with_retry(sess, url, stream=True, timeout=60,
                                      stop=lambda: self._stop)
            else:
                raise
        with resp as r:
            clen = int(r.headers.get("content-length", 0) or 0)
            mode = "wb"
            if have and r.status_code == 206:
                mode = "ab"
                got = have
                clen += have
            base = got
            ft0 = time.time()
            last = 0.0
            pending = 0                       # bytes not yet added to bytes_total
            with open(part, mode) as out:
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
                    pending += len(chunk)
                    now = time.time()
                    if now - last >= 0.2:            # at most 5 updates/s per file
                        last = now
                        fe = now - ft0
                        spd = ((got - base) / 1024 / 1024) / fe if fe > 0 else 0
                        pct = (got / clen * 100) if clen else 50.0
                        with self._lock:             # one lock take per tick, not per chunk
                            self.bytes_total += pending
                            self._dirty[fp] = ("downloading", pct, spd)
                        pending = 0
            if pending:
                with self._lock:
                    self.bytes_total += pending
        try:
            if clen and got != clen:
                raise IOError(self.tr("log_short", got=got, want=clen))
            # Re-hash as a git blob (needs the size prefix, so hash the file).
            # A mirror that lags behind fails here and the next host is tried.
            if want_sha and git_blob_sha(part) != want_sha:
                raise ChecksumError(self.tr("log_sha_mismatch"))
        except (IOError, ChecksumError):
            try:                    # a bad (possibly resumed) part must not be reused
                os.remove(part)
            except OSError:
                pass
            raise
        return got

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
                data, err = None, None
                for url in self._urls({"file_path": fp, "download_url": ""}):
                    try:
                        data = get_with_retry(sess, url, timeout=30,
                                              stop=lambda: self._stop).content
                        break
                    except Exception as e:
                        err = e
                if data is None:
                    raise err
                write_atomic(dest, data)
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
                raise ChecksumError(tr("log_db_sha", n=name))
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


# ---------------------------------------------------------------- app update
def fetch_latest_release(sess=None):
    """GitHub's JSON for the latest release (raises on network errors)."""
    sess = sess or new_session()
    r = get_with_retry(sess, LATEST_RELEASE_API, timeout=15,
                       headers={"Accept": "application/vnd.github+json"})
    return r.json()


def latest_app_release(current):
    """(tag, page_url) of the latest GitHub release when it is newer than
    `current`; None otherwise or on any error (offline, rate limit)."""
    try:
        data = fetch_latest_release()
        tag = data.get("tag_name") or ""
        url = data.get("html_url") or ""
        if is_newer(tag, current) and url.startswith("https://github.com/"):
            return tag, url
    except Exception as e:
        log.info("app update check: %s", e)
    return None


def update_platform():
    """(platform name in release file names, archive extension) for this OS,
    or (None, None) where no build is published."""
    if sys.platform == "win32":
        return "windows-x86_64", ".zip"
    if sys.platform.startswith("linux"):
        return "linux-x86_64", ".tar.gz"
    return None, None


def can_self_update():
    """Only a release build (frozen, with a real version) replaces itself;
    running from source never does."""
    return bool(getattr(sys, "frozen", False) and parse_version(APP_VERSION)
                and update_platform()[0])


# Files and folders in the app folder that an update never touches: the
# user's settings, databases (the release bundles older copies) and downloads.
UPDATE_KEEP_FILES = {"config.toml", "version.txt", "manifest.json",
                     "ese_songs.db", "ese_local.db"}
UPDATE_KEEP_DIRS = {"downloads", ".update"}
UPDATE_WORK = ".update"
UPDATE_OLD_LIST = ".update_old.txt"


def pick_update_asset(release):
    """(archive asset, .sha256 asset) for this platform from a release JSON."""
    plat, ext = update_platform()
    if not plat:
        raise RuntimeError(f"no release build for {sys.platform}")
    tag = release.get("tag_name") or ""
    name = f"ESEManager_{tag}_{plat}{ext}"
    assets = {a.get("name"): a for a in release.get("assets", [])}
    if name not in assets or name + ".sha256" not in assets:
        raise RuntimeError(f"{name} not found in release {tag}")
    return assets[name], assets[name + ".sha256"]


def _github_url(url):
    if not (url or "").startswith("https://github.com/"):
        raise RuntimeError(f"unexpected download URL: {url!r}")
    return url


def download_app_update(release=None, app_dir=None, log=print, progress=None,
                        sess=None, stop=None):
    """Download this platform's archive from a release, check its SHA-256
    (from the .sha256 file and GitHub's own digest when present) and extract
    it into <app_dir>/.update/new. Returns the folder holding the new files.
    Nothing in the app folder is changed yet."""
    app_dir = app_dir or APP_DIR
    progress = progress or (lambda got, total: None)
    own = sess is None
    sess = sess or new_session()
    try:
        release = release or fetch_latest_release(sess)
        asset, sha_asset = pick_update_asset(release)
        url = asset["browser_download_url"]
        sha_url = sha_asset["browser_download_url"]
        if not url.startswith("http://127.0.0.1"):       # tests use a local server
            _github_url(url)
            _github_url(sha_url)
        want = get_with_retry(sess, sha_url, timeout=30).text.split()[0].lower()
        digest = (asset.get("digest") or "").lower()
        if digest.startswith("sha256:") and digest[7:] != want:
            raise ChecksumError("release checksums disagree (SHA-256)")

        work = os.path.join(app_dir, UPDATE_WORK)
        shutil.rmtree(work, ignore_errors=True)
        os.makedirs(work)
        archive = os.path.join(work, asset["name"])
        log(f"⬇ {asset['name']}")
        h = hashlib.sha256()
        total = int(asset.get("size") or 0)
        got = 0
        with get_with_retry(sess, url, stream=True, timeout=120, stop=stop) as r:
            total = int(r.headers.get("content-length") or 0) or total
            with open(archive, "wb") as f:
                for chunk in r.iter_content(1 << 16):
                    if stop and stop():
                        raise InterruptedError("cancelled")
                    if chunk:
                        f.write(chunk)
                        h.update(chunk)
                        got += len(chunk)
                        progress(got, total)
        if h.hexdigest() != want:
            raise ChecksumError("SHA-256 mismatch; the download is damaged")

        new = os.path.join(work, "new")
        os.makedirs(new)
        if archive.endswith(".zip"):
            with zipfile.ZipFile(archive) as z:
                for info in z.infolist():
                    if info.is_dir() or (info.external_attr >> 16) & 0o170000 == 0o120000:
                        continue
                    dest = safe_join(new, info.filename)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with z.open(info) as src, open(dest, "wb") as out:
                        shutil.copyfileobj(src, out)
        else:
            import tarfile
            with tarfile.open(archive) as t:
                for m in t.getmembers():
                    safe_join(new, m.name)          # rejects ../ and absolute paths
                    if m.issym() or m.islnk() or m.isdev():
                        raise RuntimeError(f"unexpected entry in archive: {m.name}")
                if hasattr(tarfile, "data_filter"):
                    t.extractall(new, filter="data")
                else:                               # Python < 3.12
                    t.extractall(new)
        os.remove(archive)
        # The archive holds one top folder (ESEManager/).
        entries = os.listdir(new)
        root = os.path.join(new, entries[0]) if len(entries) == 1 else new
        if not os.path.isdir(root):
            raise RuntimeError("archive is empty")
        return root
    finally:
        if own:
            sess.close()


def _skip_on_update(rel, app_dir):
    parts = rel.replace("\\", "/").split("/")
    if parts[0].lower() in UPDATE_KEEP_DIRS:
        return True
    # Keep the user's copy; install a bundled file only if there is none yet.
    return (len(parts) == 1 and parts[0].lower() in UPDATE_KEEP_FILES
            and os.path.exists(os.path.join(app_dir, parts[0])))


def apply_app_update(new_root, app_dir=None):
    """Overwrite the app folder with the files in new_root.

    A running program cannot be overwritten on Windows but it can be renamed,
    so every existing file is first renamed to <name>.old and the new file is
    moved into its place. The .old files are deleted on the next start
    (cleanup_app_update). Any error rolls back to the old files.
    Returns the number of files installed."""
    app_dir = app_dir or APP_DIR
    moved = []       # (old_name, target)
    created = []     # targets that did not exist before
    try:
        for dirpath, _dirs, files in os.walk(new_root):
            for fn in files:
                src = os.path.join(dirpath, fn)
                rel = os.path.relpath(src, new_root)
                if _skip_on_update(rel, app_dir):
                    continue
                target = safe_join(app_dir, rel.replace(os.sep, "/"))
                os.makedirs(os.path.dirname(target), exist_ok=True)
                if os.path.exists(target):
                    old = target + ".old"
                    if os.path.exists(old):
                        try:
                            os.remove(old)
                        except OSError:          # still in use: pick another name
                            old = f"{target}.{int(time.time() * 1000)}.old"
                    os.replace(target, old)
                    moved.append((old, target))
                else:
                    created.append(target)
                os.replace(src, target)
    except Exception:
        for target in created:
            try:
                os.remove(target)
            except OSError:
                pass
        for old, target in reversed(moved):
            try:
                os.replace(old, target)
            except OSError:
                log.error("update rollback failed for %s", target)
        raise
    with open(os.path.join(app_dir, UPDATE_OLD_LIST), "a", encoding="utf-8") as f:
        for old, _ in moved:
            f.write(old + "\n")
    shutil.rmtree(os.path.join(app_dir, UPDATE_WORK), ignore_errors=True)
    return len(moved) + len(created)


def cleanup_app_update(app_dir=None):
    """Delete the .old files left by the last update (they were in use until
    the program restarted). Files still locked are kept for the next start."""
    app_dir = app_dir or APP_DIR
    path = os.path.join(app_dir, UPDATE_OLD_LIST)
    if not update_failed(app_dir):
        discard_update_work(app_dir)          # an update that was never applied
    if not os.path.exists(path):
        return 0
    try:
        with open(path, encoding="utf-8") as f:
            olds = [line.strip() for line in f if line.strip()]
    except OSError:
        return 0
    left = []
    for old in olds:
        try:
            if old.endswith(".old") and os.path.exists(old):
                os.remove(old)
        except OSError:
            left.append(old)
    try:
        if left:
            write_atomic(path, ("\n".join(left) + "\n").encode("utf-8"))
        else:
            os.remove(path)
    except OSError:
        pass
    return len(olds) - len(left)


UPDATE_FAILED = "FAILED"


def update_failed(app_dir=None):
    """Error text when the last scheduled (Windows) update could not copy its
    files, else "". The old files then stay in use; see .update/robocopy.log."""
    path = os.path.join(app_dir or APP_DIR, UPDATE_WORK, UPDATE_FAILED)
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read().strip() or "robocopy failed"
    except OSError:
        return ""


def discard_update_work(app_dir=None):
    shutil.rmtree(os.path.join(app_dir or APP_DIR, UPDATE_WORK), ignore_errors=True)


def _cmd_quote(path):
    # cmd expands %VAR% even inside quotes; refuse such paths (the caller then
    # falls back to the release page).
    if any(c in path for c in '"%\r\n'):
        raise RuntimeError(f"unsupported character in path: {path!r}")
    return f'"{path}"'


def schedule_app_update(new_root, app_dir=None, pid=None, restart=None):
    """Windows: a running program's files cannot all be replaced (some stay
    open), so write a small script that waits for this process to exit, moves
    the new files into place with robocopy (keeping the user's settings,
    databases and Downloads), then starts `restart` (an exe path) if given.
    The script runs hidden and deletes itself. The caller must exit soon."""
    import subprocess
    app_dir = os.path.abspath(app_dir or APP_DIR)
    new_root = os.path.abspath(new_root)
    pid = int(pid or os.getpid())
    work = os.path.join(app_dir, UPDATE_WORK)
    log_path = os.path.join(work, "robocopy.log")
    failed = os.path.join(work, UPDATE_FAILED)
    keep_files = " ".join(sorted(UPDATE_KEEP_FILES))
    lines = [
        "@echo off",
        "chcp 65001 >nul",
        ":wait",
        f'tasklist /FI "PID eq {pid}" /NH 2>nul | find " {pid} " >nul && '
        f'(ping -n 2 127.0.0.1 >nul & goto wait)',
        f"robocopy {_cmd_quote(new_root)} {_cmd_quote(app_dir)} /E /MOVE /R:30 /W:1 "
        f"/NP /NJH /XF {keep_files} /XD Downloads > {_cmd_quote(log_path)} 2>&1",
        f"if errorlevel 8 (echo robocopy exit %errorlevel% > {_cmd_quote(failed)}) "
        f"else (rmdir /s /q {_cmd_quote(work)})",
    ]
    if restart:
        lines.append(f"start \"\" /D {_cmd_quote(app_dir)} {_cmd_quote(restart)}")
    lines.append('(goto) 2>nul & del "%~f0"')
    script = os.path.join(tempfile.gettempdir(), f"ESEManager-update-{pid}.cmd")
    with open(script, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("\n".join(lines) + "\n")
    flags = 0x08000000 | 0x00000200          # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(["cmd.exe", "/d", "/c", script], creationflags=flags,
                     close_fds=True, cwd=tempfile.gettempdir())
    return script


def install_app_update(new_root, restart_exe=None, app_dir=None):
    """Install downloaded files: "applied" when done now (Linux; restart the
    program to use them), "scheduled" when a helper finishes after this
    process exits (Windows; exit now)."""
    if sys.platform == "win32":
        schedule_app_update(new_root, app_dir, restart=restart_exe)
        return "scheduled"
    apply_app_update(new_root, app_dir)
    return "applied"


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
