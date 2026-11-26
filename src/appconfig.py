"""
Shared paths, URLs and small helpers for ESEManager.

Data files (databases, config.toml, version.txt, Downloads)
live next to the executable when frozen, or in the repository root when running
from source. Using absolute paths means launching from a shortcut or another
working directory still finds the same data.
"""

import os
import sys

# ---------------------------------------------------------------- locations
if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def app_path(*parts):
    return os.path.join(APP_DIR, *parts)


CONFIG_FILE = app_path("config.toml")
DB_PATH = app_path("ese_songs.db")
LOCAL_DB_PATH = app_path("ese_local.db")
VERSION_FILE = app_path("version.txt")
NEW_SONGS_FILE = app_path("new_songs.json")
FAVOURITES_FILE = app_path("favourites.json")
CLONE_DIR = app_path("ESE_clone")
DEFAULT_DOWNLOAD_DIR = "Downloads"

# ---------------------------------------------------------------- remote hosts
ESE_GIT = "https://ese.tjadataba.se/ESE/ESE.git"
# /media/ serves real file contents for Git LFS files (.ogg); /raw/ would return
# only the LFS pointer text.
ESE_RAW_BASE = "https://ese.tjadataba.se/ESE/ESE/media/branch/master/"
# Mirror of the same repository (same paths); used as a fallback, or first
# when download.source = "taiko.ac".
ESE_MIRROR_BASE = "https://git.taiko.ac/zdon/ESE/media/branch/master/"
# download.source values shown in the settings: name -> host label.
DOWNLOAD_SOURCES = {"auto": "auto", "ese": "ese.tjadataba.se", "taiko.ac": "git.taiko.ac"}
# Prebuilt databases, rebuilt by .github/workflows/pages-db.yml.
DB_RELEASE_URL = "https://ganyizhong.github.io/ESEManager/"
USER_AGENT = "ESEManager"
# Version-sorted folder layout for YataiDON (box.def + song lists), installed
# as one folder inside the download (Songs) directory.
VSORT_REPO = "Yonokid/ESE-Version-Sorting"
VSORT_FOLDER = "ESE-Version-Sorting"
VSORT_SKIP = {"template"}      # top-level folders of the repo not installed (lower case)
VSORT_BRANCH_API = f"https://ese.tjadataba.se/api/v1/repos/{VSORT_REPO}/branches/master"
VSORT_ARCHIVE_URL = f"https://ese.tjadataba.se/{VSORT_REPO}/archive/{{ref}}.zip"
GITHUB_REPO = "GanYiZhong/ESEManager"
RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases"
LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASE_TAG_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/tags/"

# Release builds write src/app_version.py (see .github/workflows/release.yml);
# running from source has no such file and reports "dev".
try:
    from app_version import VERSION as APP_VERSION
except ImportError:
    APP_VERSION = "dev"


def parse_version(tag):
    """'v2026.11.18.2' / 'v1.2.1' -> tuple of ints for comparison; None if the
    string is not a plain dotted number (e.g. 'dev' or 'ci-abc1234')."""
    t = (tag or "").strip().lstrip("vV")
    parts = t.split(".")
    if not parts or not all(p.isdigit() for p in parts):
        return None
    return tuple(int(p) for p in parts)


def is_newer(latest, current):
    """True when release tag `latest` is newer than the running version.
    Development builds (unparseable current version) never prompt."""
    a, b = parse_version(latest), parse_version(current)
    return a is not None and b is not None and a > b

SQLITE_MAGIC = b"SQLite format 3\x00"


def live_url(url):
    """Rewrite links from the retired host so rows in old databases still work."""
    if not url:
        return url
    return (url.replace("git.vanillaaaa.org", "ese.tjadataba.se")
               .replace("/raw/branch/", "/media/branch/"))


def resolve_dir(path):
    """Resolve a user directory setting; relative paths are relative to APP_DIR."""
    path = os.path.expanduser(path or DEFAULT_DOWNLOAD_DIR)
    return path if os.path.isabs(path) else app_path(path)


# ---------------------------------------------------------------- path safety
class UnsafePathError(ValueError):
    pass


def safe_join(base, rel):
    """Join a relative path from untrusted data (database rows, TJA fields) onto
    base, refusing absolute paths, drive letters and any '..' component so the
    result always stays inside base."""
    if not rel:
        raise UnsafePathError("empty path")
    norm = rel.replace("\\", "/")
    if norm.startswith("/") or (len(norm) > 1 and norm[1] == ":"):
        raise UnsafePathError(f"absolute path not allowed: {rel!r}")
    parts = [p for p in norm.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        raise UnsafePathError(f"path escapes target folder: {rel!r}")
    if any("\0" in p or ":" in p for p in parts):
        raise UnsafePathError(f"invalid path: {rel!r}")
    base_abs = os.path.abspath(base)
    full = os.path.abspath(os.path.join(base_abs, *parts))
    if os.path.commonpath([base_abs, full]) != base_abs:
        raise UnsafePathError(f"path escapes target folder: {rel!r}")
    return full
