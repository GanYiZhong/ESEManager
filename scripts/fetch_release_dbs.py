"""
Download the published databases into a build folder and verify them.

Used by .github/workflows/release.yml to bundle the current databases with a
release. Every file is checked against manifest.json (sha256), the SQLite header
and PRAGMA integrity_check; manifest.json and version.txt are copied alongside
so the bundle records exactly which database build it contains.

Usage: python scripts/fetch_release_dbs.py <dest_dir> [--pages-url URL]
"""

import argparse
import hashlib
import json
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import requests  # noqa: E402

from appconfig import DB_RELEASE_URL, SQLITE_MAGIC  # noqa: E402
from core import get_with_retry  # noqa: E402

DB_FILES = ("ese_songs.db", "ese_local.db")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dest")
    ap.add_argument("--pages-url", default=os.environ.get("PAGES_URL") or DB_RELEASE_URL)
    args = ap.parse_args()
    base = args.pages_url.rstrip("/") + "/"
    os.makedirs(args.dest, exist_ok=True)

    sess = requests.Session()
    sess.headers["User-Agent"] = "ESEManager-release-builder"
    # A brief GitHub Pages hiccup should not fail the release build.
    r = get_with_retry(sess, base + "manifest.json", attempts=5, timeout=30)
    manifest = r.json()

    for name in DB_FILES:
        want = manifest["files"][name]["sha256"]
        r = get_with_retry(sess, base + name, attempts=5, timeout=300)
        data = r.content
        if not data.startswith(SQLITE_MAGIC):
            raise SystemExit(f"{name}: not a SQLite file")
        got = hashlib.sha256(data).hexdigest()
        if got != want:
            raise SystemExit(f"{name}: sha256 {got} does not match manifest {want}")
        path = os.path.join(args.dest, name)
        with open(path, "wb") as f:
            f.write(data)
        conn = sqlite3.connect(path)
        try:
            result = conn.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            conn.close()
        if result != "ok":
            raise SystemExit(f"{name}: integrity_check failed: {result}")
        print(f"{name}: {len(data)} bytes, sha256 OK, integrity OK")

    with open(os.path.join(args.dest, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    with open(os.path.join(args.dest, "version.txt"), "w", encoding="utf-8") as f:
        f.write(manifest["version"])
    print(f"Bundled database version {manifest['version']}")


if __name__ == "__main__":
    main()
