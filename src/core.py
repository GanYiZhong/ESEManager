"""ESEManager logic without Qt: search, downloads, update checks, database and
ESE-Version-Sorting updates. Used by the GUI (through thin QThread wrappers in
workers.py) and directly by the command line (cli.py).

Paths and URLs are read from this module's globals at call time, so tests can
monkeypatch core.DB_PATH and friends.
"""

import collections
import gzip
import hashlib
import json
import logging
import logging.handlers
import os
import pathlib
import queue
import re
import shutil
import sqlite3
import statistics
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

from appconfig import (APP_DIR, DB_PATH, LOCAL_DB_PATH, VERSION_FILE, NEW_SONGS_FILE,
                       FAVOURITES_FILE, ESE_RAW_BASE,
                       ESE_MIRROR_BASE,
                       DB_RELEASE_URL, USER_AGENT, SQLITE_MAGIC, live_url, safe_join,
                       UnsafePathError, LATEST_RELEASE_API, RELEASE_TAG_API, is_newer,
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


def human_clock(sec):
    """ETA as m:ss (h:mm:ss from an hour up); an em dash when unknown."""
    if sec is None or sec <= 0 or sec == float("inf"):
        return "—"
    sec = int(sec)
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


_BYTE_UNITS = ("B", "KB", "MB", "GB", "TB")


def human_bytes(n):
    n = float(max(n, 0))
    i = 0
    while n >= 1024 and i < len(_BYTE_UNITS) - 1:
        n /= 1024
        i += 1
    return f"{n:.0f} B" if i == 0 else f"{n:.1f} {_BYTE_UNITS[i]}"


def human_bytes_pair(done, total):
    """'120 / 340 MB': both numbers in the unit of the total."""
    i = 0
    t = float(max(total, 0))
    while t >= 1024 and i < len(_BYTE_UNITS) - 1:
        t /= 1024
        i += 1
    d = max(done, 0) / (1024 ** i)
    prec = 0 if i == 0 or t >= 100 else 1
    return f"{d:.{prec}f} / {t:.{prec}f} {_BYTE_UNITS[i]}"


# Size guesses for files whose size is not in the database (charts mostly).
EST_CHART = 12 * 1024
EST_AUDIO = 4 * 1024 * 1024
DISK_MARGIN = 1.1


def default_estimate(path):
    return EST_AUDIO if is_lfs_path(path) else EST_CHART


def file_size_hint(f, lfs_map=None):
    """Exact size in bytes of file record f when the database knows it, else 0.
    Audio (LFS) sizes come from the pointer map; song_files.size of an audio
    row is only the pointer's own size, so it is ignored."""
    fp = f["file_path"]
    if is_lfs_path(fp):
        e = lfs_map.get(fp) if lfs_map else None
        return int(e[1]) if e and e[1] else 0
    return int(f.get("size") or 0)


_lfs_cache = [None, {}]


def lfs_map_cached():
    """load_lfs_map() reloaded only when the database file changes ({} on any error)."""
    try:
        st = os.stat(DB_PATH)
        key = (DB_PATH, st.st_mtime_ns, st.st_size)
    except OSError:
        return {}
    if _lfs_cache[0] != key:
        try:
            _lfs_cache[1] = load_lfs_map()
        except Exception:
            _lfs_cache[1] = {}
        _lfs_cache[0] = key
    return _lfs_cache[1]


def free_space(path):
    """Free bytes on the volume that holds (or would hold) path."""
    p = os.path.abspath(path)
    while p and not os.path.isdir(p):
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    return shutil.disk_usage(p).free


def plan_download(files, download_dir, overwrite=False, lfs_map=None):
    """Before a batch: expected bytes (known sizes plus guesses for the rest;
    files already on disk are skipped unless overwrite), free space and
    whether free >= expected x 1.1. Returns a dict; free is None if unreadable."""
    if lfs_map is None:
        lfs_map = lfs_map_cached()
    total = 0
    exact = True
    for _, f in files:
        fp = f["file_path"]
        if not overwrite:
            try:
                if os.path.exists(safe_join(download_dir, fp)):
                    continue
            except Exception:
                pass
        n = file_size_hint(f, lfs_map)
        if n <= 0:
            n = default_estimate(fp)
            exact = False
        total += n
    need = int(total * DISK_MARGIN)
    try:
        free = free_space(download_dir)
    except OSError:
        free = None
    return {"expected": total, "exact": exact, "need": need, "free": free,
            "ok": free is None or free >= need}


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


RETRY_BACKOFF = 1.0   # first backoff in seconds (doubles each retry); tests shrink it


def get_with_retry(sess, url, attempts=3, stop=None, **kw):
    """GET with a short exponential backoff on connection errors and 5xx/429."""
    delay = RETRY_BACKOFF
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


def category_counts():
    """{category name: number of songs with files} in one SQL query (box.def
    rows excluded). {} when there is no database. Call once per DB load."""
    if not os.path.exists(DB_PATH):
        return {}
    conn = connect_ro(DB_PATH)
    try:
        return {n: c for n, c in conn.execute(
            "SELECT c.name, COUNT(DISTINCT s.id) FROM songs s "
            "JOIN categories c ON s.category_id = c.id "
            "JOIN song_files f ON f.song_id = s.id "
            "WHERE lower(f.filename) != 'box.def' GROUP BY c.name")}
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
        self._sug = None         # typo-suggestion data, lazy (see _suggest_data)
        self._sug_ja = None
        self._kana = None        # (_kana_key names, trigram index), lazy

    def kana_keys(self):
        if self._kana is None:
            keys = [_kana_key(n) for n in self.names]
            tri = {}
            for i, k in enumerate(keys):
                for g in _grams(k, 3):
                    tri.setdefault(g, []).append(i)
            self._kana = (keys, tri)
        return self._kana

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


def _category_keys(category):
    """Normalised category filters: a string, or a list/tuple of strings (a song
    matches when its category contains any of them). Blank entries are ignored."""
    if not category:
        return []
    items = [category] if isinstance(category, str) else list(category)
    return [k for k in (norm_text(c).strip() for c in items if c) if k]


# ---------------------------------------------------------------- kana -> romaji
_KANA_BASE = dict(zip(*[iter((
    "あ a い i う u え e お o か ka き ki く ku け ke こ ko さ sa し shi す su せ se そ so "
    "た ta ち chi つ tsu て te と to な na に ni ぬ nu ね ne の no は ha ひ hi ふ fu へ he ほ ho "
    "ま ma み mi む mu め me も mo や ya ゆ yu よ yo ら ra り ri る ru れ re ろ ro "
    "わ wa ゐ i ゑ e を o が ga ぎ gi ぐ gu げ ge ご go ざ za じ ji ず zu ぜ ze ぞ zo "
    "だ da ぢ ji づ zu で de ど do ば ba び bi ぶ bu べ be ぼ bo ぱ pa ぴ pi ぷ pu ぺ pe ぽ po "
    "ゔ vu ぁ a ぃ i ぅ u ぇ e ぉ o ゃ ya ゅ yu ょ yo ゎ wa").split())] * 2))
_KANA_SMALL_Y = {"ゃ": "a", "ゅ": "u", "ょ": "o"}
_KANA_COMBO = {  # kana + small vowel kana -> romaji
    "ふぁ": "fa", "ふぃ": "fi", "ふぇ": "fe", "ふぉ": "fo", "うぃ": "wi", "うぇ": "we",
    "うぉ": "wo", "ゔぁ": "va", "ゔぃ": "vi", "ゔぇ": "ve", "ゔぉ": "vo", "てぃ": "ti",
    "でぃ": "di", "とぅ": "tu", "どぅ": "du", "しぇ": "she", "じぇ": "je", "ちぇ": "che",
    "つぁ": "tsa", "つぃ": "tsi", "つぇ": "tse", "つぉ": "tso", "いぇ": "ye"}
_KANA_Y_BASE = {"し": "sh", "ち": "ch", "じ": "j", "ぢ": "j"}
_VOWELS = "aiueo"


def _kana_syllable(t, i):
    """(romaji, chars consumed) of the kana syllable at t[i], or None."""
    base = _KANA_BASE.get(t[i]) if i < len(t) else None
    if base is None:
        return None
    nxt = t[i + 1] if i + 1 < len(t) else ""
    if nxt in _KANA_SMALL_Y and base.endswith("i") and t[i] != "い":
        return _KANA_Y_BASE.get(t[i], base[:-1] + "y") + _KANA_SMALL_Y[nxt], 2
    combo = _KANA_COMBO.get(t[i:i + 2])
    if combo:
        return combo, 2
    return base, 1


def kana_to_romaji(text, apostrophe=True):
    """Modified-Hepburn transliteration of the kana in `text` (katakana is
    folded to hiragana first, other characters pass through): digraphs
    (きゃ -> kya), small っ doubles the next consonant (っち -> tchi), ん is n
    (n' before a vowel or y when `apostrophe`), ー repeats the previous vowel."""
    t = norm_text(text)
    out = []
    i = 0
    while i < len(t):
        c = t[i]
        if c in "っん":
            nxt = _kana_syllable(t, i + 1)
            if c == "ん":
                vowelish = nxt and nxt[0][0] in _VOWELS + "y"
                out.append("n'" if apostrophe and vowelish else "n")
            elif nxt and nxt[0][0] not in _VOWELS + "n":
                out.append("t" if nxt[0].startswith("ch") else nxt[0][0])
            i += 1
        elif c == "ー":
            prev = "".join(out)[-1:]
            out.append(prev if prev in _VOWELS else "")
            i += 1
        else:
            syl = _kana_syllable(t, i)
            out.append(syl[0] if syl else c)
            i += syl[1] if syl else 1
    return "".join(out)


def _has_kana(text):
    return any('぀' <= c <= 'ヿ' and c not in "゠・" for c in text or "")


def _kana_key(text):
    """Loose comparison key for kana-derived romaji: _romaji_key plus l/r and
    long-vowel folding, spaces and punctuation dropped."""
    k = _romaji_key(text).replace("l", "r")
    k = "".join(c for c in k if c.isalnum()).replace("ngu", "ng")
    return re.sub(r"(.)\1+", r"\1", k)


def _kana_query(keyword):
    """Romaji reading of a query that is kana (plus Latin/digits/spaces), else
    None: a query still holding kanji cannot be transliterated."""
    if not _has_kana(keyword):
        return None
    r = kana_to_romaji(keyword, apostrophe=False)
    return None if has_cjk(r) else r


def search_songs(keyword, category=None):
    """Search the song database. Matching is width-, case- and kana-insensitive
    and ignores spaces/punctuation; several words must all match, in any
    order. A Japanese keyword also matches songs whose Japanese title (from
    the local title database) matches. With a keyword the results are ranked
    (exact title > prefix > word boundary > substring > multi-word >
    punctuation-insensitive), ties keep database order. Shared by the GUI and
    the command line. `category` is one name (part of it is enough) or a list of
    names (songs of any of them). The song list is cached until a database file
    changes."""
    idx = _song_index()
    kw = " ".join(norm_text(keyword).split()) if keyword else ""
    cats = _category_keys(category)
    cand = [i for i in range(len(idx.songs))
            if not cats or any(c in idx.cats[i] for c in cats)]
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
        rom = _kana_query(keyword)
        if rom and _kana_key(rom):
            # kana typed for a romaji title: match the transliteration (loosely
            # folded); Japanese-title hits (0-6) always rank before these (10+)
            rkeys, _ = idx.kana_keys()
            rk = _kana_key(rom)
            for i in cand:
                if i not in best:
                    t = _tier(rkeys[i], rk)
                    if t is not None:
                        best[i] = 10 + t
        out = sorted(best, key=lambda i: (best[i], i))
    # Callers get their own dicts, so mutating a result cannot corrupt the cache.
    return [dict(idx.songs[i], files=list(idx.songs[i]["files"])) for i in out]



# ---------------------------------------------------------------- suggestions
_ROMAJI_SUBS = (("sh", "s"), ("ch", "t"), ("ts", "t"), ("f", "h"), ("j", "z"),
                ("ou", "o"), ("oo", "o"), ("uu", "u"), ("mb", "nb"), ("mp", "np"))


def _romaji_key(word):
    """Lossy key that folds common romanisation variants together (ou/oo/o,
    uu/u, si/shi, tu/tsu, ti/chi, hu/fu, zi/ji, n/m before b/p) so 'hatune',
    'hatsune' and 'yuugao'/'yugao' compare equal. Used only for suggestions."""
    w = unicodedata.normalize("NFKD", word)
    w = "".join(c for c in w if not unicodedata.combining(c))
    for a, b in _ROMAJI_SUBS:
        w = w.replace(a, b)
    return w


def _bounded_dl(a, b, limit):
    """Damerau-Levenshtein (optimal string alignment) distance, or limit + 1
    as soon as it must exceed `limit`."""
    la, lb = len(a), len(b)
    if abs(la - lb) > limit:
        return limit + 1
    prev2 = None
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        ca = a[i - 1]
        for j in range(1, lb + 1):
            cost = 0 if ca == b[j - 1] else 1
            v = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if (prev2 is not None and i > 1 and j > 1 and ca == b[j - 2]
                    and a[i - 2] == b[j - 1]):
                v = min(v, prev2[j - 2] + 1)
            cur[j] = v
        if min(cur) > limit:
            return limit + 1
        prev2, prev = prev, cur
    return prev[lb]


def _word_cutoff(n):
    return 0 if n <= 3 else 1 if n <= 6 else 2


def _grams(text, n):
    return {text[i:i + n] for i in range(len(text) - n + 1)}


_WORD_RE = re.compile(r"[^\W_]+")


def _suggest_data(idx):
    """Vocabulary and trigram index over the titles, built once per index."""
    if idx._sug is not None:
        return idx._sug
    words = collections.Counter()
    shown = {}
    for s, name in zip(idx.songs, idx.names):
        words.update(_WORD_RE.findall(name))
        for raw in _WORD_RE.findall(s["song_name"]):
            shown.setdefault(raw.casefold(), raw)
    buckets = {}                      # romaji key length -> {key: [word, ...]}
    for w in words:
        k = _romaji_key(w)
        buckets.setdefault(len(k), {}).setdefault(k, []).append(w)
    tri = {}
    tkeys = []
    for i, name in enumerate(idx.names):
        key = "".join(_romaji_key(w) for w in _WORD_RE.findall(name))
        tkeys.append(key)
        for g in _grams(key, 3):
            tri.setdefault(g, []).append(i)
    idx._sug = (words, shown, buckets, tri, tkeys, "\n".join(idx.names))
    return idx._sug


def _suggest_ja(idx, kw, limit):
    if idx._sug_ja is None:
        titles = {}
        if os.path.exists(LOCAL_DB_PATH):
            try:
                lconn = connect_ro(LOCAL_DB_PATH)
                try:
                    for (ja,) in lconn.execute(
                            "SELECT DISTINCT title_ja FROM local_songs "
                            "WHERE title_ja IS NOT NULL AND title_ja != ''"):
                        c = _compact(norm_text(ja))
                        if len(c) >= 2:
                            titles[ja] = c
                finally:
                    lconn.close()
            except sqlite3.Error:
                log.warning("title lookup failed", exc_info=True)
        inv = {}
        for ja, c in titles.items():
            for g in _grams(c, 2):
                inv.setdefault(g, []).append(ja)
        idx._sug_ja = (titles, inv)
    titles, inv = idx._sug_ja
    ck = _compact(kw)
    qg = _grams(ck, 2)
    if len(ck) < 3 or not qg:
        return []
    hits = collections.Counter()
    for g in qg:
        for ja in inv.get(g, ()):
            hits[ja] += 1
    scored = []
    for ja, n in hits.items():
        cont = n / len(qg)
        if cont >= 0.5:
            dice = 2 * n / (len(qg) + len(_grams(titles[ja], 2)))
            scored.append((-cont, -dice, len(ja), ja))
    scored.sort()
    return [t[3] for t in scored[:limit]]


def _suggest_kana(idx, rom, limit):
    """Song titles close to a transliterated kana query (trigram containment
    on loosely folded keys, so ろーりんぐがーる ~ 'Rolling Girl')."""
    keys, tri = idx.kana_keys()
    qk = _kana_key(rom)
    qg = _grams(qk, 3)
    if len(qk) < 4 or not qg:
        return []
    hits = collections.Counter()
    for g in qg:
        for i in tri.get(g, ()):
            hits[i] += 1
    scored = []
    for i, n in hits.items():
        cont = n / len(qg)
        if cont >= 0.5:
            dice = 2 * n / (len(qg) + max(1, len(keys[i]) - 2))
            scored.append((-cont, -dice, i))
    scored.sort()
    return [idx.songs[i]["song_name"] for _, _, i in scored[:limit]]


def suggest(keyword, limit=3):
    """'Did you mean' candidates for a query that found little or nothing:
    up to `limit` strings, each a corrected query or a song title that can be
    searched directly. Latin keywords are corrected word by word (Damerau-
    Levenshtein with a cutoff scaled to word length, on romaji-folded keys),
    then matched against whole titles by trigram containment; Japanese
    keywords use character bigrams against the Japanese titles. The index is
    built once with the search cache."""
    kw = " ".join(norm_text(keyword).split()) if keyword else ""
    if not kw or limit <= 0:
        return []
    idx = _song_index()
    if has_cjk(kw):
        out = _suggest_ja(idx, kw, limit)
        rom = _kana_query(kw)
        if rom and len(out) < limit:
            out += [x for x in _suggest_kana(idx, rom, limit) if x not in out]
        return out[:limit]
    words, shown, buckets, tri, tkeys, blob = _suggest_data(idx)
    tokens = list(dict.fromkeys(_WORD_RE.findall(kw)))
    if not tokens:
        return []
    options = []
    for tok in tokens:
        if tok in words:
            options.append([(0, tok)])
            continue
        key = _romaji_key(tok)
        cut = _word_cutoff(len(key))
        found = []
        for ln in range(len(key) - cut, len(key) + cut + 1):
            for k, ws in buckets.get(ln, {}).items():
                d = _bounded_dl(key, k, cut)
                if d <= cut:
                    found.extend((d, -words[w], w) for w in ws)
        found.sort()
        found = [(d, w) for d, _, w in found[:2]]
        if tok in blob:          # a fragment of some word: keep it as an option
            found.append((cut + 1, tok))
        options.append(found)
    out = []
    seen = set()

    def add(text):
        k = norm_text(text)
        if k not in seen and k != kw:
            seen.add(k)
            out.append(text)

    if all(options):
        combos = [(0, [])]
        for o in options:
            combos = [(d + d2, ws + [w]) for d, ws in combos for d2, w in o]
        combos.sort(key=lambda c: c[0])
        for d, ws in combos[:6]:
            if ws == tokens or not any(all(w in n for w in ws) for n in idx.names):
                continue
            add(" ".join(shown.get(w, w) for w in ws))
            if len(out) >= limit:
                return out
    # whole-title match on the run-together key ('dokidoki' ~ 'Doki Doki ...')
    qkey = "".join(_romaji_key(t) for t in tokens)
    qg = _grams(qkey, 3)
    if len(qkey) >= 5 and qg:
        hits = collections.Counter()
        for g in qg:
            for i in tri.get(g, ()):
                hits[i] += 1
        scored = []
        for i, n in hits.items():
            cont = n / len(qg)
            if cont >= 0.6:
                dice = 2 * n / (len(qg) + max(1, len(tkeys[i]) - 2))
                scored.append((-cont, -dice, i))
        scored.sort()
        for _, _, i in scored:
            add(idx.songs[i]["song_name"])
            if len(out) >= limit:
                break
    return out


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


DL_NONE, DL_PARTIAL, DL_COMPLETE = 0, 1, 2


def song_key(song):
    """Identity of a song in status maps (names repeat across categories)."""
    return (song["song_name"], song["category"])


def download_status(songs, download_dir):
    """{song_key: DL_NONE | DL_PARTIAL | DL_COMPLETE} from ONE scan_tree walk.
    A song with no files, or whose paths are all unsafe, counts as DL_NONE."""
    present = scan_tree(download_dir)
    out = {}
    for s in songs:
        have = total = 0
        for f in s["files"]:
            key = _rel_key(f["file_path"])
            if key is None:
                continue
            total += 1
            if key in present:
                have += 1
        out[song_key(s)] = (DL_NONE if not have else
                            DL_COMPLETE if have == total else DL_PARTIAL)
    return out


def filter_by_download(songs, status, mode):
    """mode None/"all": everything; "missing": not fully downloaded (none or
    partial, so unfinished songs can be completed); "downloaded": complete.
    Songs not in `status` (scan pending) are kept in "all" and "missing"."""
    if mode in (None, "all"):
        return list(songs)
    if mode == "downloaded":
        return [s for s in songs if status.get(song_key(s)) == DL_COMPLETE]
    return [s for s in songs if status.get(song_key(s)) != DL_COMPLETE]


# ---------------------------------------------------------------- favourites
def fav_id(song_or_key):
    """JSON key of a song: "category/song_name". Accepts a song dict or a
    (song_name, category) tuple."""
    name, cat = (song_key(song_or_key) if isinstance(song_or_key, dict)
                 else song_or_key)
    return f"{cat}/{name}"


def load_favourites(path=None):
    """Set of (song_name, category) starred by the user. A missing or damaged
    file yields an empty set."""
    try:
        with open(path or FAVOURITES_FILE, encoding="utf-8") as f:
            data = json.load(f)
        items = data["songs"] if isinstance(data, dict) else data
        out = set()
        for it in items:
            if isinstance(it, str) and "/" in it:
                cat, _, name = it.partition("/")
                if cat and name:
                    out.add((name, cat))
        return out
    except (OSError, ValueError, KeyError, TypeError):
        return set()


def save_favourites(favs, path=None):
    """Write the favourites atomically (sorted, so the file diffs cleanly)."""
    data = {"version": 1, "songs": sorted(fav_id(k) for k in favs)}
    write_atomic(path or FAVOURITES_FILE,
                 json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8"))


def filter_favourites(songs, favs):
    return [s for s in songs if song_key(s) in favs]


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


def load_lfs_map(db_path=None):
    """{file_path: (sha256, size)} of the real content behind LFS audio, from
    the pointer files read at database build time. Empty for databases that
    predate the lfs_sha256/lfs_size columns."""
    conn = connect_ro(db_path or DB_PATH)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(song_files)")}
        if not {"lfs_sha256", "lfs_size"} <= cols:
            return {}
        return {fp: (sha, size) for fp, sha, size in conn.execute(
            "SELECT file_path, lfs_sha256, lfs_size FROM song_files "
            "WHERE lfs_sha256 IS NOT NULL AND lfs_sha256 != '' AND lfs_size IS NOT NULL")}
    finally:
        conn.close()


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class NoShaError(Exception):
    """The song database predates blob_sha; update checks need a newer one."""


def find_updates(download_dir, category=None, progress=None, only=None):
    """Downloaded files whose upstream content changed (git blob sha). Returns
    songs holding only the changed files, plus the song's LFS audio (an updated
    chart usually ships with new audio). LFS audio is compared through the
    pointer's sha256/size (databases without them skip audio): a different
    size flags it at once, an equal size is confirmed by a cached sha256.
    `only`: a set of (song_name, category) keys to restrict the check to."""
    progress = progress or (lambda done, total: None)
    songs = search_songs(None, category)
    if only is not None:
        songs = [s for s in songs if song_key(s) in only]
    sha_map = load_sha_map()
    if not sha_map:
        raise NoShaError()

    try:
        lfs_map = load_lfs_map()
    except Exception:
        lfs_map = {}

    present = scan_tree(download_dir)
    candidates = []     # (song, file, key, remote_sha); key "sha256:<rel>" = LFS audio
    size_changed = []   # (song, file): audio whose length differs from the pointer's
    for s in songs:
        for f in s["files"]:
            fp = f["file_path"]
            if is_lfs_path(fp):
                lfs = lfs_map.get(fp)
                rel = _rel_key(fp) if lfs else None
                if rel is not None and rel in present:
                    if present[rel][1] != lfs[1]:
                        size_changed.append((s, f))
                    else:
                        candidates.append((s, f, "sha256:" + rel, lfs[0]))
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
        mt, size = present[key.removeprefix("sha256:")]
        full = os.path.normcase(os.path.join(base, *key.removeprefix("sha256:").split("/")))
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
            path = safe_join(download_dir, fp)
            return key, (file_sha256(path) if key.startswith("sha256:")
                         else git_blob_sha(path))
        except (OSError, UnsafePathError):
            return key, None

    if todo:
        with ThreadPoolExecutor(max_workers=min(16, (os.cpu_count() or 4) * 2)) as ex:
            for key, sha in ex.map(hash_one, todo, chunksize=1):
                done += 1
                if sha is not None:
                    mt, size = present[key.removeprefix("sha256:")]
                    shas[key] = sha
                    fresh[key] = (mt, size, sha)
                report(done == total)
        with _sha_cache_lock:
            for key, _ in todo:
                _sha_forgotten.discard(os.path.normcase(
                    os.path.join(base, *key.removeprefix("sha256:").split("/"))))
    report(True)

    # keep entries for files still on disk (other categories), drop deleted ones
    keep = {k: v for k, v in disk.items() if k.removeprefix("sha256:") in present}
    keep.update(fresh)
    if keep != disk:
        save_sha_disk_cache(download_dir, keep)

    changed = {}    # id(song) -> song dict with only the changed files
    for s, f, key, sha in candidates:
        local = shas.get(key)
        if local is not None and local != sha:
            entry = changed.setdefault(id(s), dict(s, files=[], _orig=s))
            entry["files"].append(f)
    for s, f in size_changed:
        entry = changed.setdefault(id(s), dict(s, files=[], _orig=s))
        if f not in entry["files"]:
            entry["files"].append(f)

    out = []
    for entry in changed.values():
        orig = entry.pop("_orig")
        have = {f["file_path"] for f in entry["files"]}
        entry["files"] += [f for f in orig["files"]
                           if is_lfs_path(f["file_path"]) and f["file_path"] not in have]
        out.append(entry)
    return out


AUTO_FULL_CHECK_SECS = 24 * 3600


def changed_song_keys():
    """{(song_name, category)} the last DB update marked as changed."""
    return {(n, c) for c, n in load_new_songs()["changed"]}


def auto_check_updates(download_dir, last_full=0.0, now=None, progress=None):
    """Background "are my downloaded songs current?" check. Fast path: only the
    songs the last DB update changed; a full find_updates when the last full
    check is over a day old. Returns (songs, was_full)."""
    now = time.time() if now is None else now
    full = not (0 <= now - (last_full or 0) < AUTO_FULL_CHECK_SECS)
    only = None if full else changed_song_keys()
    if only is not None and not only:
        return [], False
    return find_updates(download_dir, progress=progress, only=only), full


# ---------------------------------------------------------------- cleanup
# Top-level names of the download folder that are never category folders and
# never touched, even if a database category happened to share the name.
CLEANUP_PROTECTED = {"config", "config.toml", "ese_songs.db", "ese_local.db",
                     VSORT_FOLDER.lower(), ".update"}
CLEANUP_EXPECTED = {"box.def"}      # written by the app, not in the song file listing


def _cleanup_db(db_path=None):
    """({category folder names}, {db file keys}, {dir keys incl. ancestors}),
    or None without a database."""
    path = db_path or DB_PATH
    if not os.path.exists(path):
        return None
    conn = connect_ro(path)
    try:
        rows = [r[0] for r in conn.execute("SELECT file_path FROM song_files")]
        cat_rows = [r[0] for r in conn.execute("SELECT path FROM categories")]
    finally:
        conn.close()
    cats, files, dirs = set(), set(), set()
    for p in cat_rows:
        k = _rel_key(p)
        if k and "/" not in k:
            cats.add(k)
    for p in rows:
        k = _rel_key(p)
        if not k or "/" not in k:
            continue
        files.add(k)
        parts = k.split("/")
        cats.add(parts[0])
        for i in range(2, len(parts)):
            dirs.add("/".join(parts[:i]))
    cats = {c for c in cats if c.lower() not in CLEANUP_PROTECTED}   # any OS case
    return cats, files, dirs


def _dir_list(path):
    """[(name, is_dir, size, mtime, is_link)] of a folder; symlinks count as
    plain files of size 0 so nothing is ever followed out of the tree."""
    out = []
    try:
        it = os.scandir(path)
    except OSError:
        return out
    with it:
        for e in it:
            try:
                if e.is_symlink():
                    out.append((e.name, False, 0, 0, True))
                elif e.is_dir(follow_symlinks=False):
                    out.append((e.name, True, 0, 0, False))
                else:
                    st = e.stat()
                    out.append((e.name, False, st.st_size, st.st_mtime, False))
            except OSError:
                continue
    return sorted(out)


def _tree_size(path):
    size = n = 0
    stack = [path]
    while stack:
        d = stack.pop()
        for name, is_dir, fsize, _m, _l in _dir_list(d):
            if is_dir:
                stack.append(os.path.join(d, name))
            else:
                size += fsize
                n += 1
    return size, n


def analyze_library(download_dir, db_path=None, now=None):
    """What has piled up in the download folder: one walk of the category
    folders plus the database listing. None without a database, otherwise:
      orphans     song folders no longer in the database
      strays      files inside known song folders that the database does not list
      parts       leftover *.part files (with "age" in seconds)
      empty       empty folders (topmost only)
      categories  {folder: {"size": bytes, "files": n}}
    Items: {"kind", "path", "rel", "category", "size", ...}. Only folders of
    categories known to the database are looked at; config, the databases
    and ESE-Version-Sorting are skipped; box.def is expected."""
    known = _cleanup_db(db_path)
    if known is None:
        return None
    cats, db_files, db_dirs = known
    now = time.time() if now is None else now
    res = {"orphans": [], "strays": [], "parts": [], "empty": [], "categories": {}}
    lower = os.name == "nt"

    def key(rel):
        return rel.lower() if lower else rel

    folders = []
    try:
        top = os.scandir(download_dir)
    except OSError:
        return res
    with top:
        for e in top:
            try:
                if e.is_dir(follow_symlinks=False) and not e.is_symlink() \
                        and key(e.name) in cats:
                    folders.append(e.name)
            except OSError:
                continue

    def walk(path, rel, cat, empties):
        """(size, file count) of a known folder; collects empty subfolders."""
        size = files = 0
        for name, is_dir, fsize, mtime, link in _dir_list(path):
            r = rel + "/" + name
            full = os.path.join(path, name)
            if is_dir:
                if key(r) in db_dirs:
                    s, n = walk(full, r, cat, empties)
                    if n == 0:
                        empties.append((full, r))
                else:
                    s, n = _tree_size(full)
                    if n == 0:
                        empties.append((full, r))
                    else:
                        res["orphans"].append({"kind": "orphan", "path": full, "rel": r,
                                               "category": cat, "size": s, "files": n})
                size += s
                files += n
                continue
            size += fsize
            files += 1
            if name.lower().endswith(".part"):
                res["parts"].append({"kind": "part", "path": full, "rel": r, "category": cat,
                                     "size": fsize, "age": max(0.0, now - mtime)})
            elif link or name.lower() in CLEANUP_EXPECTED or key(r) in db_files:
                continue
            elif rel.count("/") >= 1:        # inside a song folder, not the category root
                res["strays"].append({"kind": "stray", "path": full, "rel": r,
                                      "category": cat, "size": fsize})
        return size, files

    for cat in sorted(folders):
        empties = []
        size, files = walk(os.path.join(download_dir, cat), cat, cat, empties)
        res["categories"][cat] = {"size": size, "files": files}
        paths = {p for p, _r in empties}
        for p, r in empties:
            if os.path.dirname(p) not in paths:      # topmost empty folders only
                res["empty"].append({"kind": "empty", "path": p, "rel": r,
                                     "category": cat, "size": 0, "files": 0})
    return res


def cleanup_default_selection(item):
    """Only .part files older than a day are pre-selected."""
    return item["kind"] == "part" and item.get("age", 0) > PART_MAX_AGE


def cleanup_safe(download_dir, path, db_path=None):
    """True if path lies strictly inside a known (and unprotected) category folder."""
    known = _cleanup_db(db_path)
    if known is None:
        return False
    rel = os.path.relpath(os.path.realpath(path), os.path.realpath(download_dir))
    if rel.startswith("..") or os.path.isabs(rel):
        return False
    parts = rel.replace("\\", "/").split("/")
    first = parts[0].lower() if os.name == "nt" else parts[0]
    return len(parts) >= 2 and first in known[0] and first.lower() not in CLEANUP_PROTECTED


def cleanup_apply(download_dir, items, mover, db_path=None):
    """Move each item with mover(path) -> bool (the trash). Items outside the
    known category folders are refused. Returns (done, failed)."""
    done, failed = [], []
    for it in items:
        if not os.path.lexists(it["path"]) or not cleanup_safe(download_dir, it["path"], db_path):
            failed.append(it)
            continue
        try:
            ok = bool(mover(it["path"]))
        except Exception:
            log.warning("cleanup failed: %s", it["path"], exc_info=True)
            ok = False
        (done if ok else failed).append(it)
    return done, failed


def delete_permanently(path):
    """Hard delete; only ever called after the user explicitly agreed."""
    try:
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
        return True
    except OSError:
        return False


def move_to_trash(path):
    """Send a file or folder to the OS trash without Qt (CLI). False on failure."""
    path = os.path.abspath(path)
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            class SHFILEOPSTRUCTW(ctypes.Structure):
                _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT),
                            ("pFrom", wintypes.LPCWSTR), ("pTo", wintypes.LPCWSTR),
                            ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL),
                            ("hNameMappings", ctypes.c_void_p),
                            ("lpszProgressTitle", wintypes.LPCWSTR)]
            op = SHFILEOPSTRUCTW()
            op.wFunc = 3                                   # FO_DELETE
            op.pFrom = path + "\0\0"
            op.fFlags = 0x40 | 0x10 | 0x4 | 0x400          # UNDO|NOCONFIRM|SILENT|NOERRORUI
            return (ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op)) == 0
                    and not op.fAnyOperationsAborted)
        import subprocess
        if sys.platform == "darwin":
            script = 'tell application "Finder" to delete POSIX file "%s"' % path.replace('"', '\\"')
            return subprocess.run(["osascript", "-e", script], capture_output=True,
                                  timeout=30).returncode == 0
        for cmd in (["gio", "trash", path], ["trash-put", path]):
            if shutil.which(cmd[0]):
                return subprocess.run(cmd, capture_output=True, timeout=30).returncode == 0
    except Exception:
        log.warning("move_to_trash failed: %s", path, exc_info=True)
    return False


# ---------------------------------------------------------------- downloads
_download_source = "auto"
PART_MAX_AGE = 24 * 3600        # seconds a stopped download's .part may be resumed


def set_download_source(pref):
    """Preferred download host from config (download.source): a name from
    DOWNLOAD_SOURCES, "auto" (pick the fastest host) or an http(s) base URL.
    Empty means "auto"; other unknown values behave like "ese"."""
    global _download_source
    _download_source = pref.strip() if isinstance(pref, str) and pref.strip() else "auto"


def source_bases(pref=None):
    """Base URLs to try for a song file, preferred first; the other known
    hosts follow as fallbacks (they serve the same repository paths)."""
    pref = (pref or _download_source).strip()
    known = {"ese": ESE_RAW_BASE, "taiko.ac": ESE_MIRROR_BASE}
    first = known.get(pref)
    if first is None and pref.lower().startswith(("http://", "https://")):
        first = pref if pref.endswith("/") else pref + "/"
    first = first or ESE_RAW_BASE        # also "auto": ese first until measured
    return [first] + [b for b in (ESE_RAW_BASE, ESE_MIRROR_BASE) if b != first]


RANK_FILE = "host_rank.json"
RANK_VERSION = 1
ESE_MAX_CONN = 3                # concurrent connections we allow to ese.tjadataba.se


class HostRouter:
    """Picks the host for each file in "auto" download mode.

    Per host it keeps EWMAs of bytes and seconds per completed file (speed =
    bytes / seconds) and of the failure rate; score = speed * (1 - fail)^2.
    pick() routes to the best host that is under its concurrency limit, sends
    every `probe_every`-th file to the runner-up so its estimate stays fresh,
    and never offers a host that already failed this file. A host without any
    measurement scores infinite, so each host gets measured at job start. The
    last ranking is persisted to a small JSON file to seed the next run."""

    ALPHA = 0.3

    def __init__(self, bases, limits=None, probe_every=20, path=None, on_switch=None):
        self.bases = list(bases)
        self.limits = dict(limits or {})
        self.probe_every = max(2, probe_every)
        self.path = path
        self.on_switch = on_switch
        self._lock = threading.Lock()
        self._st = {b: {"b": None, "t": None, "fail": 0.0, "n": 0, "active": 0}
                    for b in self.bases}
        self._failed = {}              # file_path -> {bases that failed it}
        self._n = 0                    # first attempts so far (probe clock)
        self._dirty = False
        self._load()
        self.initial = self._ranked()
        self._best = self.initial[0]

    # --- persistence
    def _load(self):
        if not self.path:
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if data.get("v") != RANK_VERSION:
                return
            for b, rec in data.get("hosts", {}).items():
                st = self._st.get(b)
                spd = float(rec.get("speed", 0) or 0)
                if st and spd > 0:
                    st["b"], st["t"] = spd, 1.0
                    st["fail"] = min(1.0, max(0.0, float(rec.get("fail", 0) or 0)))
        except Exception:
            pass

    def save(self):
        if not self.path:
            return
        with self._lock:
            if not self._dirty:
                return
            hosts = {b: {"speed": round(st["b"] / st["t"], 1), "fail": round(st["fail"], 3)}
                     for b, st in self._st.items() if st["b"] and st["t"]}
            self._dirty = False
        if not hosts:
            return
        try:
            write_atomic(self.path, json.dumps({"v": RANK_VERSION, "hosts": hosts}).encode())
        except Exception:
            log.info("could not save host ranking", exc_info=True)

    # --- scoring
    @staticmethod
    def _speed(st):
        return st["b"] / st["t"] if st["b"] and st["t"] else None

    def _score(self, b):
        st = self._st[b]
        spd = self._speed(st)
        if spd is None:
            return float("inf") if st["n"] == 0 else 0.0
        return spd * (1.0 - st["fail"]) ** 2

    def _ranked(self):
        return sorted(self.bases, key=lambda b: -self._score(b))

    def speeds(self):
        with self._lock:
            return {b: self._speed(st) for b, st in self._st.items()}

    # --- routing
    def pick(self, fp, tried=()):
        """Reserve and return the next host to try for `fp`, or None when
        every host has been tried. Pair with report()."""
        with self._lock:
            prior = self._failed.get(fp, ())
            ranked = [b for b in self._ranked() if b not in tried]
            if not ranked:
                return None
            ranked.sort(key=lambda b: b in prior)          # past failures last
            free = [b for b in ranked
                    if self._st[b]["active"] < self.limits.get(b, 1 << 30)]
            pool = free or ranked[:1]
            choice = pool[0]
            if not tried:
                self._n += 1
                if self._n % self.probe_every == 0:
                    others = [b for b in pool[1:] if b not in prior]
                    if others:
                        choice = others[0]
            self._st[choice]["active"] += 1
            switched = self._check_best()
        if switched and self.on_switch:
            self.on_switch(switched)
        return choice

    def _check_best(self):
        best = self._ranked()[0]
        if best != self._best:
            self._best = best
            return best
        return None

    def report(self, base, fp, ok, nbytes=0, secs=0.0):
        """Finish an attempt: ok True/False update the estimates, None (cancelled)
        only releases the slot."""
        with self._lock:
            st = self._st[base]
            st["active"] -= 1
            if ok is None:
                return
            a = self.ALPHA
            st["fail"] = st["fail"] * (1 - a) + (0.0 if ok else a)
            st["n"] += 1
            if ok:
                secs = max(secs, 1e-3)
                if st["b"] is None:
                    st["b"], st["t"] = float(nbytes), secs
                else:
                    st["b"] = st["b"] * (1 - a) + nbytes * a
                    st["t"] = st["t"] * (1 - a) + secs * a
            else:
                self._failed.setdefault(fp, set()).add(base)
            self._dirty = True
            switched = self._check_best()
        if switched and self.on_switch:
            self.on_switch(switched)


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
                 bases=None, auto=None, rank_path=None):
        self.files = files
        # Hosts tried in order for each file; a host that works after the
        # first one failed moves to the front for the rest of the job.
        # auto: route each file to the measured-fastest host (the default
        # source, or auto=True with explicit bases).
        self.auto = auto if auto is not None else (not bases and _download_source == "auto")
        self.bases = list(bases) if bases else source_bases()
        self._switched = set()
        self.router = None
        if self.auto and len(self.bases) > 1:
            if rank_path is None and not bases:
                rank_path = os.path.join(APP_DIR, RANK_FILE)
            self.router = HostRouter(
                self.bases, limits={ESE_RAW_BASE: ESE_MAX_CONN}, path=rank_path,
                on_switch=self._announce)
            self.bases = list(self.router.initial)
        self.download_dir = download_dir
        self.workers = max(1, workers)
        self.overwrite = overwrite     # True = replace existing files (update mode)
        self.tr = tr or (lambda key, **kw: key)
        self.log = log or (lambda msg: None)
        self._stop = False
        self._lfs_map = {}
        self._by_hash = {}             # sha256 -> every file_path with that audio
        self._hash_locks = {}          # sha256 -> Lock (one fetch/copy per content)
        self.copied = 0                # files satisfied by a local copy
        self.saved_bytes = 0           # download bytes avoided by those copies
        self._pause = threading.Event()
        self._pause.set()              # set = running, clear = paused
        self.failed = []               # [(song, file_info)]
        self.fail_reasons = {}         # file_path -> friendly reason text
        self._lock = threading.Lock()
        self._dirty = {}               # file_path -> (status, pct, speed) since last pull
        self.total = len(files)
        self._initial = list(files)
        self._known = {f["file_path"] for _, f in files}   # queued or already run
        self._queue = queue.Queue()
        self._outstanding = 0          # queued + running items (and box.def jobs)
        self._closed = False           # run() has drained the queue; add() refused
        self.done = 0
        self.dl = self.skip = self.fail = 0
        self.bytes_total = 0
        self.t0 = time.time()
        self._samples = collections.deque()   # (time, bytes_total, done) for rates
        # Byte accounting: expected transfer per file once known (database
        # size, Content-Length, or the real count after it ran); files still
        # unknown are counted by extension and guessed from the median of
        # that extension's finished files.
        self._fexp = {}                # file_path -> expected bytes (known)
        self._fsum = 0
        self._unk = collections.Counter()      # ext -> files of unknown size
        self._ext_sizes = {}           # ext -> recent finished sizes
        self._xfer = {}                # file_path -> bytes transferred so far
        for _, f in files:
            self._register(f)

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

    # ---- byte accounting (call with self._lock held, except in __init__)
    @staticmethod
    def _ext(fp):
        return os.path.splitext(fp)[1].lower()

    def _register(self, f):
        fp = f["file_path"]
        n = file_size_hint(f, self._lfs_map)
        if n > 0:
            self._fexp[fp] = n
            self._fsum += n
        else:
            self._unk[self._ext(fp)] += 1

    def _set_known(self, fp, n):
        old = self._fexp.get(fp)
        if old is None:
            self._unk[self._ext(fp)] -= 1
            old = 0
        self._fexp[fp] = n
        self._fsum += n - old

    def _guess(self, ext):
        sizes = self._ext_sizes.get(ext)
        if sizes:
            return statistics.median(sizes)
        return EST_AUDIO if ext in LFS_EXTS else EST_CHART

    def _expected_locked(self):
        """(expected bytes of the whole job, True when no size is a guess)."""
        total = self._fsum
        exact = True
        for ext, cnt in self._unk.items():
            if cnt > 0:
                total += cnt * self._guess(ext)
                exact = False
        return max(total, self.bytes_total), exact

    def _rates_locked(self, now):
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
        return spd, eta

    def snapshot(self):
        """Counters plus the rows that changed since the previous call.
        ETA here is by file count; see snapshot_ex() for the byte-based one."""
        with self._lock:
            spd, eta = self._rates_locked(time.time())
            dirty = self._dirty
            self._dirty = {}
            return (self.done, self.total, spd, eta, dirty)

    def snapshot_ex(self):
        """(info, dirty): like snapshot() but info is a dict with byte
        progress: done/total (files), bytes_done, bytes_total (expected, grows
        or shrinks as sizes become known), exact (False while some sizes are
        still guesses), speed (MB/s over the recent window) and eta (remaining
        bytes / windowed speed; by file count until a speed is measured)."""
        with self._lock:
            spd, eta_files = self._rates_locked(time.time())
            expected, exact = self._expected_locked()
            remaining = expected - self.bytes_total
            if self.done >= self.total:
                eta = 0
            elif spd > 0:
                eta = max(remaining, 0) / (spd * 1024 * 1024)
            else:
                eta = eta_files
            info = {"done": self.done, "total": self.total, "speed": spd, "eta": eta,
                    "bytes_done": self.bytes_total, "bytes_total": expected,
                    "exact": exact, "copied": self.copied,
                    "saved_bytes": self.saved_bytes}
            dirty = self._dirty
            self._dirty = {}
            return info, dirty

    def _mark(self, file_path, status, pct, speed):
        with self._lock:
            self._dirty[file_path] = (status, pct, speed)

    def _count(self, kind):
        with self._lock:
            self.done += 1
            setattr(self, kind, getattr(self, kind) + 1)

    def _ordered(self, files):
        # Small files (charts) before LFS audio: the list fills quickly and a
        # stop leaves complete charts rather than half an .ogg. Among audio,
        # the first file of each identical-content group goes before its
        # repeats, so the repeats can be copied instead of downloaded.
        seen = set()

        def rank(it):
            fp = it[1]["file_path"]
            if not is_lfs_path(fp):
                return 0
            lfs = self._lfs_map.get(fp)
            if lfs is None:
                return 1
            if lfs[0] in seen:
                return 2
            seen.add(lfs[0])
            return 1
        return sorted(files, key=rank)

    def saved_text(self):
        """'Saved X MB by reusing identical audio (n files)', or "" when nothing
        was reused."""
        with self._lock:
            n, b = self.copied, self.saved_bytes
        return self.tr("log_dedup_saved", size=human_bytes(b), n=n) if n else ""

    def _local_source(self, fp, lfs):
        """Existing files in the download folder that should hold the same
        audio as fp: same database hash and exact size (verified on copy)."""
        for other in self._by_hash.get(lfs[0], ()):
            if other == fp:
                continue
            try:
                path = safe_join(self.download_dir, other)
                if os.path.isfile(path) and os.path.getsize(path) == lfs[1]:
                    yield path
            except (OSError, ValueError):
                continue

    def _copy_local(self, src, part, lfs):
        """Copy src to part and verify size + sha256; False (part removed) if
        the source turned out not to hold the expected content."""
        try:
            shutil.copyfile(src, part)
            if os.path.getsize(part) == lfs[1] and file_sha256(part) == lfs[0]:
                return True
        except OSError:
            pass
        try:
            os.remove(part)
        except OSError:
            pass
        return False

    def add(self, files):
        """Append (song, file) pairs to the running job (thread-safe). Files
        already queued, running or finished in this job are skipped. Returns
        the list of pairs added, or None when the job has already drained (the
        caller should start a new one)."""
        with self._lock:
            if self._closed:
                return None
            new = []
            for song, f in files:
                fp = f["file_path"]
                if fp not in self._known:
                    self._known.add(fp)
                    new.append((song, f))
            if not new:
                return []
            new = self._ordered(new)
            self.files.extend(new)
            for _, f in new:
                self._register(f)
            self.total += len(new)
            self._outstanding += len(new) + 1
            self._queue.put(("boxdef", new))
            for item in new:
                self._queue.put(("file", item))
        return new

    def _finish_item(self):
        with self._lock:
            self._outstanding -= 1
            if self._outstanding > 0 or self._closed:
                return
            self._closed = True
        for _ in range(self.workers):
            self._queue.put(None)

    def _worker(self, sess, sha_map):
        while True:
            job = self._queue.get()
            if job is None:
                return
            try:
                kind, payload = job
                if kind == "boxdef":
                    self._fetch_boxdefs(sess, payload)
                else:
                    self._one(sess, sha_map, payload)
            except Exception:
                log.warning("download worker error", exc_info=True)
            finally:
                self._finish_item()

    def run(self):
        sess = new_session(self.workers + 2)
        try:
            sha_map = load_sha_map()
        except Exception:
            sha_map = {}
        try:
            self._lfs_map = load_lfs_map()
        except Exception:
            self._lfs_map = {}
        with self._lock:
            for _, f in self.files:
                fp = f["file_path"]
                n = file_size_hint(f, self._lfs_map)
                if n > 0 and fp not in self._fexp:
                    self._set_known(fp, n)
        try:
            # On first download into a category folder, also fetch ESE's box.def.
            self._fetch_boxdefs(sess, self._initial)
            for fp_, (sha_, _n) in self._lfs_map.items():
                self._by_hash.setdefault(sha_, []).append(fp_)
            with self._lock:
                initial = self._ordered(self._initial)
                self._outstanding += len(initial)
                for item in initial:
                    self._queue.put(("file", item))
            if not initial:
                self._outstanding += 1
                self._finish_item()
            threads = [threading.Thread(target=self._worker, args=(sess, sha_map),
                                        daemon=True) for _ in range(self.workers)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        finally:
            with self._lock:
                self._closed = True
            sess.close()
            if self.router:
                self.router.save()
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

    def _announce(self, base):
        with self._lock:
            first = base not in self._switched
            self._switched.add(base)
        if first:
            self.log(self.tr("log_mirror", host=_host(base)))

    def _next_url(self, f, tried):
        """(url, router_base) of the next host to try for file f, or (None, None).
        router_base is set only in auto mode (that slot must be report()ed)."""
        if not self.router:
            for u in self._urls(f):
                if u not in tried:
                    return u, None
            return None, None
        fp = f["file_path"]
        rec = live_url(f["download_url"] or "")
        if rec and not rec.startswith(ESE_RAW_BASE) and rec not in tried and \
                not any(rec.startswith(b) for b in self.bases):
            return rec, None
        base = self.router.pick(fp, tried)
        if base is None:
            return None, None
        return base + urllib.parse.quote(fp), base

    def _worked(self, url):
        """Move the host that served `url` to the front (logged once)."""
        if self.router:
            return                  # the router tracks the ranking
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
        hlock = None
        try:
            save_path = safe_join(self.download_dir, fp)
            if os.path.exists(save_path) and not self.overwrite:
                with self._lock:
                    self._set_known(fp, 0)
                self._count("skip")
                self._mark(fp, "skipped", 100.0, 0.0)
                return
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            part = save_path + ".part"
            want = sha_map.get(fp)
            check = want if want and not is_lfs_path(fp) else None
            lfs = self._lfs_map.get(fp) if is_lfs_path(fp) else None
            if lfs:
                # One fetch per distinct audio: a second worker with the same
                # content waits here, then finds the first one's file on disk.
                with self._lock:
                    hlock = self._hash_locks.setdefault(lfs[0], threading.Lock())
                hlock.acquire()
                if self._stop:
                    raise InterruptedError(self.tr("log_cancelled"))
                for src in self._local_source(fp, lfs):
                    if self._copy_local(src, part, lfs):
                        os.replace(part, save_path)
                        part = None
                        forget_blob_sha(save_path)
                        with self._lock:
                            self._set_known(fp, 0)
                            self.copied += 1
                            self.saved_bytes += lfs[1]
                        self._count("dl")
                        self._mark(fp, "done", 100.0, 0.0)
                        self.log(self.tr("log_dedup", f=disp,
                                         size=human_bytes(lfs[1])))
                        return
            err = None
            tried = []
            while True:
                if self._stop:
                    raise InterruptedError(self.tr("log_cancelled"))
                url, base = self._next_url(f, tried)
                if url is None:
                    if err is None:
                        raise IOError("no download source")
                    raise AllHostsFailed([_host(t) for t in tried], err) from err
                t0 = time.time()
                have = os.path.getsize(part) if os.path.exists(part) else 0
                try:
                    got = self._fetch(sess, url, part, fp, check, lfs)
                    if base:
                        self.router.report(base, fp, True, max(got - have, 1),
                                           time.time() - t0)
                    self._worked(url)
                    break
                except InterruptedError:
                    if base:
                        self.router.report(base, fp, None)
                    raise
                except Exception as e:              # try the next host
                    if base:
                        self.router.report(base, fp, False)
                    log.info("%s: %s", url, e)
                    err = e
                    tried.append(base or url)
            os.replace(part, save_path)
            part = None
            forget_blob_sha(save_path)
            with self._lock:
                self._set_known(fp, self._xfer.pop(fp, 0))
                self._ext_sizes.setdefault(self._ext(fp), collections.deque(maxlen=200)).append(got)
            self._count("dl")
            self._mark(fp, "done", 100.0, 0.0)
            self.log(f"✓ {disp} ({got/1024/1024:.2f} MB)")
        except Exception as e:
            reason = friendly_error(e, self.tr)
            with self._lock:
                self._set_known(fp, self._xfer.pop(fp, 0))
                self.failed.append((song, f))
                self.fail_reasons[f["file_path"]] = reason
            self._count("fail")
            self._mark(fp, "failed", 0.0, 0.0)
            log.warning("download failed: %s", disp, exc_info=True)
            self.log(self.tr("log_fail", f=disp, e=reason))
        finally:
            if hlock is not None:
                hlock.release()
            # A stopped download keeps its .part so the next run can resume it
            # with a Range request; any other failure discards it.
            if part and os.path.exists(part) and not self._stop:
                try:
                    os.remove(part)
                except OSError:
                    pass

    def _fetch(self, sess, url, part, fp, want_sha, lfs=None):
        """Download url into part and check its length and git blob sha, or for
        LFS audio with a known pointer `lfs` = (sha256, size) the exact length
        and the sha256 (hashed while streaming). Returns the byte count; raises
        on any problem. A leftover .part is resumed with a Range request when
        the server honours it."""
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
            if clen and not lfs:           # the real size beats a guess
                with self._lock:
                    self._set_known(fp, clen - got)
            h256 = hashlib.sha256() if lfs else None
            if h256 is not None and got:        # resumed: hash the kept prefix
                with open(part, "rb") as old:
                    left = got
                    while left > 0:
                        b = old.read(min(1 << 20, left))
                        if not b:
                            break
                        h256.update(b)
                        left -= len(b)
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
                    if h256 is not None:
                        h256.update(chunk)
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
                            self._xfer[fp] = self._xfer.get(fp, 0) + pending
                            self._dirty[fp] = ("downloading", pct, spd)
                        pending = 0
            if pending:
                with self._lock:
                    self.bytes_total += pending
                    self._xfer[fp] = self._xfer.get(fp, 0) + pending
        try:
            if clen and got != clen:
                raise IOError(self.tr("log_short", got=got, want=clen))
            if lfs:
                if got != lfs[1]:
                    raise IOError(self.tr("log_short", got=got, want=lfs[1]))
                if h256.hexdigest() != lfs[0]:
                    raise ChecksumError(self.tr("log_sha_mismatch"))
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

    def _fetch_boxdefs(self, sess, files):
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
        cats = {f["file_path"].split("/")[0] for _, f in files if "/" in f["file_path"]}
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


MAX_DB_BYTES = 64 * 1024 * 1024   # cap on a decompressed database (gzip-bomb guard)


def _download_db_gz(sess, gz, want, part, log, max_out=None):
    """Fetch the gzip copy of a database into `part`. Verifies the .gz sha256,
    decompresses with a size cap, then the plain sha256. Raises on any problem
    (the caller falls back to the plain file); `part` is removed on failure."""
    max_out = max_out or MAX_DB_BYTES
    gz_part = part + ".gz"
    try:
        hz = hashlib.sha256()
        total = 0
        with get_with_retry(sess, DB_RELEASE_URL + gz["name"], stream=True, timeout=120) as r:
            with open(gz_part, "wb") as f:
                for chunk in r.iter_content(1 << 16):
                    if chunk:
                        f.write(chunk)
                        hz.update(chunk)
                        total += len(chunk)
        log(f"{gz['name']}: {total / 1048576:.2f} MB")
        if hz.hexdigest() != gz["sha256"]:
            raise ChecksumError(gz["name"])
        h = hashlib.sha256()
        out = 0
        with gzip.open(gz_part, "rb") as src, open(part, "wb") as dst:
            while True:
                chunk = src.read(1 << 16)
                if not chunk:
                    break
                out += len(chunk)
                if out > max_out:
                    raise ValueError("decompressed database too large")
                dst.write(chunk)
                h.update(chunk)
        with open(part, "rb") as f:
            if f.read(16) != SQLITE_MAGIC:
                raise ValueError("not a SQLite file")
        if h.hexdigest() != want:
            raise ChecksumError(gz["name"])
    except BaseException:
        try:
            os.remove(part)
        except OSError:
            pass
        raise
    finally:
        try:
            os.remove(gz_part)
        except OSError:
            pass


def _download_db_plain(sess, name, want, part, tr):
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
            info = files.get(name) or {}
            got = False
            gz = info.get("gz") or {}
            if gz.get("name") and gz.get("sha256"):
                try:
                    _download_db_gz(sess, gz, want, part, log)
                    got = True
                except Exception as e:
                    logging.getLogger("ESEManager").warning("%s: compressed download failed (%s); using plain file", name, e)
            if not got:
                _download_db_plain(sess, name, want, part, tr)
            if not sqlite_ok(part):
                raise ValueError(tr("log_db_bad", n=name))
        # What is new compared with the database being replaced (best effort).
        diff = None
        if os.path.exists(targets[0]):
            try:
                diff = diff_song_sets(targets[0], parts[0])
            except Exception:
                logging.getLogger("ESEManager").warning("song diff failed", exc_info=True)
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
        try:
            save_new_songs(diff or {"added": [], "changed": []}, installed)
        except Exception:
            logging.getLogger("ESEManager").warning("saving new-songs list failed", exc_info=True)
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


# ---------------------------------------------------------------- what's new
def diff_song_sets(old_db, new_db):
    """Compare two song databases with SQL. Returns {"added": [...], "changed":
    [...]} of [category, song_name]: added = songs only in new_db; changed =
    songs in both where some file is new or has a different blob_sha."""
    conn = connect_ro(new_db)
    try:
        conn.execute("ATTACH DATABASE ? AS old", (
            pathlib.Path(os.path.abspath(old_db)).as_uri() + "?mode=ro",))
        songs = ("SELECT c.name AS cat, s.song_name AS name "
                 "FROM {db}.songs s JOIN {db}.categories c ON c.id = s.category_id")
        files = ("SELECT c.name AS cat, s.song_name AS name, f.file_path AS fp, "
                 "f.blob_sha AS sha FROM {db}.song_files f "
                 "JOIN {db}.songs s ON s.id = f.song_id "
                 "JOIN {db}.categories c ON c.id = s.category_id")
        added = conn.execute(
            f"SELECT cat, name FROM ({songs.format(db='main')}) "
            f"EXCEPT SELECT cat, name FROM ({songs.format(db='old')}) "
            "ORDER BY 1, 2").fetchall()
        changed = conn.execute(
            f"SELECT DISTINCT cat, name FROM (SELECT cat, name, fp, sha FROM ({files.format(db='main')}) "
            f"EXCEPT SELECT cat, name, fp, sha FROM ({files.format(db='old')})) "
            f"WHERE (cat, name) IN (SELECT cat, name FROM ({songs.format(db='old')})) "
            "ORDER BY 1, 2").fetchall()
        return {"added": [list(r) for r in added], "changed": [list(r) for r in changed]}
    finally:
        conn.close()


def save_new_songs(diff, version=""):
    """Persist the last update's diff (atomic) next to the config."""
    data = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "version": version,
            "added": [list(x) for x in diff.get("added", [])],
            "changed": [list(x) for x in diff.get("changed", [])]}
    write_atomic(NEW_SONGS_FILE, json.dumps(data, ensure_ascii=False).encode("utf-8"))
    return data


def load_new_songs():
    """The saved diff, or an empty one (missing or damaged file)."""
    try:
        with open(NEW_SONGS_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        return {"time": str(d.get("time", "")), "version": str(d.get("version", "")),
                "added": [tuple(x) for x in d.get("added", [])],
                "changed": [tuple(x) for x in d.get("changed", [])]}
    except (OSError, ValueError, TypeError, AttributeError):
        return {"time": "", "version": "", "added": [], "changed": []}


def new_song_marks():
    """{(song_name, category): "new" | "updated"} for the last DB update."""
    d = load_new_songs()
    marks = {(n, c): "updated" for c, n in d["changed"]}
    marks.update({(n, c): "new" for c, n in d["added"]})
    return marks


def filter_new_songs(songs, marks):
    return [s for s in songs if song_key(s) in marks]


# ---------------------------------------------------------------- app update
def fetch_latest_release(sess=None):
    """GitHub's JSON for the latest release (raises on network errors)."""
    sess = sess or new_session()
    r = get_with_retry(sess, LATEST_RELEASE_API, timeout=15,
                       headers={"Accept": "application/vnd.github+json"})
    return r.json()


def fetch_release_by_tag(tag, sess=None):
    """GitHub's JSON for the release tagged `tag` (raises on network errors)."""
    from urllib.parse import quote
    sess = sess or new_session()
    r = get_with_retry(sess, RELEASE_TAG_API + quote(tag, safe=""), timeout=15,
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
                     "ese_songs.db", "ese_local.db", "new_songs.json",
                     "favourites.json"}
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


# ------------------------------------------------- simulator song-folder detection
SONG_DIR_NAMES = ("songs", "song", "tja")
SIM_EXE_PATTERNS = (("OpenTaiko", "opentaiko"), ("TJAPlayer3", "tjaplayer3"),
                    ("YataiDON", "yataidon"), ("TaikoJiro", "taikojiro"))
FIND_MAX_ENTRIES = 2000
FIND_MAX_SECONDS = 1.0


def _sim_from_names(names):
    for n in names:
        low = n.lower()
        for label, key in SIM_EXE_PATTERNS:
            if low.startswith(key) and (low.endswith((".exe", ".x86_64", ".appimage"))
                                        or "." not in low):
                return label
    return ""


def _steam_library_roots():
    """steamapps/common of every Steam library listed in libraryfolders.vdf."""
    home = os.path.expanduser("~")
    cands = [os.path.join(os.environ[v], "Steam", "steamapps", "libraryfolders.vdf")
             for v in ("ProgramFiles(x86)", "ProgramFiles") if os.environ.get(v)]
    cands += [os.path.join(home, ".steam", "steam", "steamapps", "libraryfolders.vdf"),
              os.path.join(home, ".local", "share", "Steam", "steamapps", "libraryfolders.vdf")]
    roots = []
    for vdf in cands:
        try:
            with open(vdf, "r", encoding="utf-8", errors="replace") as f:
                text = f.read(1 << 20)
        except OSError:
            continue
        roots.append(os.path.join(os.path.dirname(vdf), "common"))
        for m in re.finditer(r'"path"\s+"([^"]+)"', text):
            roots.append(os.path.join(m.group(1).replace("\\\\", "\\"), "steamapps", "common"))
    return roots


def _song_search_roots():
    """Places a Taiko simulator tends to live, most likely first."""
    home = os.path.expanduser("~")
    roots = [os.path.dirname(APP_DIR)]
    for sub in ("Documents", "Desktop", "Downloads", "Games"):
        roots.append(os.path.join(home, sub))
    roots += _steam_library_roots()
    for var in ("LOCALAPPDATA", "ProgramFiles", "ProgramFiles(x86)"):
        if os.environ.get(var):
            roots.append(os.environ[var])
    return roots


def find_song_folders(roots=None, max_entries=FIND_MAX_ENTRIES, max_seconds=FIND_MAX_SECONDS):
    """Best-effort, read-only hunt for a Taiko simulator's song folder.

    Returns [{"path", "simulator", "tja_count", "truncated"}], simulator-known
    first, then by chart count. Scans at most `max_entries` directory entries
    (plus as many again to count charts) and `max_seconds`; never follows links.
    """
    deadline = time.monotonic() + max_seconds
    state = {"left": max_entries, "count_left": max_entries}

    def spent(key="left"):
        return state[key] <= 0 or time.monotonic() > deadline

    def listing(path, key="left"):
        if spent(key):
            return None
        out = []
        try:
            with os.scandir(path) as it:
                for e in it:
                    state[key] -= 1
                    out.append(e)
                    if spent(key):
                        break
        except OSError:
            return None
        return out

    def is_dir(e):
        try:
            return e.is_dir(follow_symlinks=False)
        except OSError:
            return False

    def count_tja(path, depth=0):
        n = 0
        for e in listing(path, "count_left") or ():
            if is_dir(e):
                if depth < 3:
                    n += count_tja(e.path, depth + 1)
            elif e.name.lower().endswith(".tja"):
                n += 1
        return n

    found, seen = [], set()

    def add(path, sim):
        key = os.path.normcase(os.path.realpath(path))
        if key in seen:
            return
        seen.add(key)
        n = count_tja(path)
        if n == 0 and not sim:
            return
        found.append({"path": path, "simulator": sim, "tja_count": n,
                      "truncated": spent("count_left")})

    def walk(path, depth, sim):
        ents = listing(path)
        if ents is None:
            return
        sim = _sim_from_names([e.name for e in ents if not is_dir(e)]) or sim
        for e in ents:
            if not is_dir(e):
                continue
            if e.name.lower() in SONG_DIR_NAMES:
                add(e.path, sim)
            elif depth < 3 and not spent():
                walk(e.path, depth + 1, sim)

    seen_roots = set()
    for root in (roots if roots is not None else _song_search_roots()):
        if spent():
            break
        key = os.path.normcase(os.path.realpath(root))
        if key in seen_roots or os.path.islink(root) or not os.path.isdir(root):
            continue
        seen_roots.add(key)
        walk(root, 0, "")
    found.sort(key=lambda f: (not f["simulator"], -f["tja_count"], f["path"]))
    return found


def describe_song_folder(c, tr):
    """'OpenTaiko, 1234 charts' style text for a find_song_folders() entry."""
    n = ("%d+" if c.get("truncated") else "%d") % c["tja_count"]
    return tr("detect_item_sim", sim=c["simulator"], n=n) if c["simulator"] \
        else tr("detect_item", n=n)
