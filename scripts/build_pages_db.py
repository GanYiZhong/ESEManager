"""
Build the prebuilt ESEManager databases for GitHub Pages.

Used by .github/workflows/pages-db.yml. Produces a static site folder with:
  ese_songs.db    song list (from a blobless clone of ESE)
  ese_local.db    Japanese titles / BPM / levels (parsed from each .tja)
  version.txt     version string the app compares against its local copy
  manifest.json   version, ESE commit, sizes and sha256 of each database
  index.html      small human-readable status page

The previous release is downloaded from the live Pages site first, so the
.tja parsing stays incremental (only new/changed songs are fetched), and the
whole build is skipped when ESE's master commit has not changed.

Usage (from the repo root):
  python scripts/build_pages_db.py --out site [--force]
"""

import argparse
import datetime as dt
import hashlib
import html
import json
import os
import sqlite3
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import time  # noqa: E402

import requests  # noqa: E402

from appconfig import ESE_GIT, DB_RELEASE_URL as DEFAULT_PAGES_URL, SQLITE_MAGIC  # noqa: E402

DB_FILES = ("ese_songs.db", "ese_local.db")

# Refuse to publish a database that is obviously broken (e.g. ESE was down).
MIN_SONGS = 1000
MAX_SHRINK = 0.5   # new song count must be at least 50% of the previous one


def set_output(key, value):
    """Write a step output for GitHub Actions (no-op when run locally)."""
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{key}={value}\n")
    print(f"[output] {key}={value}")


def retry(fn, attempts=3, what="request"):
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:
            if i == attempts - 1:
                raise
            print(f"{what} failed ({e}); retrying in {5 * (i + 1)}s")
            time.sleep(5 * (i + 1))


def upstream_commit():
    out = retry(lambda: subprocess.run(
        ["git", "ls-remote", ESE_GIT, "refs/heads/master"],
        capture_output=True, text=True, timeout=120, check=True).stdout, what="git ls-remote")
    sha = out.split()[0] if out.strip() else ""
    if len(sha) != 40:
        raise RuntimeError(f"Could not read ESE master commit: {out!r}")
    return sha


def fetch_previous(pages_url, work):
    """Download the currently published manifest + databases.

    Returns {} only when the site has no release yet (404). Any other failure
    raises: without the previous song count the shrink guard below cannot work,
    so a transient Pages error must not lead to publishing a truncated build."""
    sess = requests.Session()
    sess.headers["User-Agent"] = "ESEManager-pages-builder"

    def get_manifest():
        r = sess.get(pages_url + "manifest.json", timeout=30)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    manifest = retry(get_manifest, what="manifest.json")
    if manifest is None:
        print("No previous release (404); building from scratch")
        return {}

    for name in DB_FILES:
        dest = os.path.join(work, name)
        try:
            r = sess.get(pages_url + name, timeout=300)
            r.raise_for_status()
            if not r.content.startswith(SQLITE_MAGIC):
                raise ValueError("not a SQLite file")
            with open(dest, "wb") as f:
                f.write(r.content)
            print(f"Reusing previous {name} ({len(r.content) / 1048576:.1f} MB)")
        except Exception as e:
            print(f"Could not reuse previous {name}: {e}")
            if os.path.exists(dest):
                os.remove(dest)
    return manifest


def count(db, sql):
    conn = sqlite3.connect(db)
    try:
        return conn.execute(sql).fetchone()[0]
    finally:
        conn.close()


def vacuum(db):
    conn = sqlite3.connect(db)
    try:
        conn.execute("VACUUM")
        result = conn.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        conn.close()
    if result != "ok":
        raise SystemExit(f"Refusing to publish: integrity_check failed for {db}: {result}")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_index(out, manifest):
    rows = "".join(
        f"<tr><td><a href='{html.escape(n)}'>{html.escape(n)}</a></td>"
        f"<td>{info['size'] / 1048576:.2f} MB</td><td><code>{info['sha256'][:16]}…</code></td></tr>"
        for n, info in manifest["files"].items())
    stats = manifest["stats"]
    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ESEManager database</title>
<style>body{{font-family:system-ui,sans-serif;max-width:760px;margin:2rem auto;padding:0 1rem;line-height:1.5}}
table{{border-collapse:collapse}}td,th{{padding:.3rem .8rem;border-bottom:1px solid #ddd;text-align:left}}</style>
</head><body>
<h1>ESEManager database</h1>
<p>Prebuilt databases for <a href="https://github.com/GanYiZhong/ESEManager">ESEManager</a>,
rebuilt automatically from <a href="https://ese.tjadataba.se/ESE/ESE">ESE</a>.</p>
<p><b>Version:</b> <code>{html.escape(manifest['version'])}</code><br>
<b>Built:</b> {html.escape(manifest['built_at'])}<br>
<b>ESE commit:</b> <code>{html.escape(manifest['ese_commit'])}</code><br>
<b>Songs:</b> {stats['songs']} · <b>Files:</b> {stats['files']} ·
<b>Japanese titles:</b> {stats['titles_ja']}</p>
<table><tr><th>File</th><th>Size</th><th>SHA-256</th></tr>{rows}</table>
<p><a href="version.txt">version.txt</a> · <a href="manifest.json">manifest.json</a></p>
</body></html>
"""
    with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="site", help="output folder (default: site)")
    ap.add_argument("--work", default="pages_work", help="scratch folder (default: pages_work)")
    ap.add_argument("--pages-url", default=os.environ.get("PAGES_URL") or DEFAULT_PAGES_URL)
    ap.add_argument("--force", action="store_true",
                    help="rebuild even if ESE has not changed since the last release")
    args = ap.parse_args()
    pages_url = args.pages_url.rstrip("/") + "/"

    os.makedirs(args.work, exist_ok=True)
    commit = upstream_commit()
    print(f"ESE master: {commit}")

    prev = fetch_previous(pages_url, args.work)
    if prev.get("ese_commit") == commit and not args.force:
        print("ESE has not changed since the published release; nothing to do")
        set_output("changed", "false")
        return

    from ese_scraper_git_v2 import ESEScraperGitV2
    import build_local_db

    songs_db = os.path.join(args.work, "ese_songs.db")
    local_db = os.path.join(args.work, "ese_local.db")

    scraper = ESEScraperGitV2(db_path=songs_db, clone_dir=os.path.join(args.work, "ESE_clone"))
    try:
        scraper.scrape(keep_clone=False)
    finally:
        scraper.close()

    songs = count(songs_db, "SELECT COUNT(*) FROM songs")
    prev_songs = prev.get("stats", {}).get("songs") or 0
    if songs < MIN_SONGS or (prev_songs and songs < prev_songs * MAX_SHRINK):
        raise SystemExit(f"Refusing to publish: only {songs} songs (previous release had {prev_songs})")

    build_local_db.build_from_remote(song_db=songs_db, local_db=local_db, workers=12)

    for db in (songs_db, local_db):
        vacuum(db)

    now = dt.datetime.now(dt.timezone.utc)
    version = f"{now:%Y%m%d-%H%M}-{commit[:7]}"
    os.makedirs(args.out, exist_ok=True)
    files = {}
    for name, src in (("ese_songs.db", songs_db), ("ese_local.db", local_db)):
        dest = os.path.join(args.out, name)
        with open(src, "rb") as fi, open(dest, "wb") as fo:
            fo.write(fi.read())
        files[name] = {"size": os.path.getsize(dest), "sha256": sha256(dest)}

    manifest = {
        "version": version,
        "built_at": now.strftime("%Y-%m-%d %H:%M UTC"),
        "ese_commit": commit,
        "files": files,
        "stats": {
            "songs": songs,
            "files": count(songs_db, "SELECT COUNT(*) FROM song_files"),
            "titles_ja": count(local_db, "SELECT COUNT(*) FROM local_songs "
                                         "WHERE title_ja IS NOT NULL AND title_ja != ''"),
        },
    }
    with open(os.path.join(args.out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    with open(os.path.join(args.out, "version.txt"), "w", encoding="utf-8") as f:
        f.write(version + "\n")
    open(os.path.join(args.out, ".nojekyll"), "w").close()
    write_index(args.out, manifest)

    print(f"Built release {version}: {manifest['stats']}")
    set_output("changed", "true")
    set_output("version", version)


if __name__ == "__main__":
    main()
