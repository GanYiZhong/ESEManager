"""
ESEManager command-line mode.

    ESEManager-cli status
    ESEManager-cli update-db [--force]
    ESEManager-cli search KEYWORD [-c CATEGORY]
    ESEManager-cli download [KEYWORD] [-c CATEGORY] [--all] [-y]
    ESEManager-cli missing [--download] [-y]
    ESEManager-cli updates [--download] [-y]
    ESEManager-cli version-sorting [--force]

Common options: --dir DIR (download folder; default from config.toml or
./Downloads next to the app), --workers N, --lang zh_TW|en|ja.

Uses the same databases, download folder and verification as the GUI.
From source: python src/cli.py ...   Release builds: ESEManager-cli(.exe).
Exit codes: 0 success, 1 something failed, 2 bad usage / nothing to work on.
"""

import argparse
import os
import sys
import threading
import time

try:
    import tomllib
except ImportError:          # Python < 3.11
    import tomli as tomllib

from appconfig import (APP_DIR, APP_VERSION, CONFIG_FILE, DB_PATH, DEFAULT_DOWNLOAD_DIR,
                       VSORT_FOLDER, resolve_dir)
from i18n import TR, CATEGORY_NAMES, detect_system_lang


# ---------------------------------------------------------------- helpers
def load_config():
    try:
        with open(CONFIG_FILE, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}


def make_tr(lang):
    def tr(key, **kw):
        s = TR.get(lang, TR["zh_TW"]).get(key, TR["zh_TW"].get(key, key))
        return s.format(**kw) if kw else s
    return tr


def out(msg=""):
    print(msg, flush=True)


def confirm(question, assume_yes):
    if assume_yes:
        return True
    if not sys.stdin or not sys.stdin.isatty():
        return False
    try:
        return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


def need_db(tr):
    if not (os.path.exists(DB_PATH) and os.path.getsize(DB_PATH) > 0):
        out(tr("cli_no_db"))
        return False
    return True


def search(keyword, category):
    from workers import search_songs
    return search_songs(keyword, category)


def run_download(files, ddir, workers, tr, overwrite=False):
    """Run the GUI's DownloadThread logic synchronously with a progress line."""
    from PySide6.QtCore import QCoreApplication, Qt
    from workers import DownloadThread
    from models import human_speed, human_eta

    QCoreApplication.instance() or QCoreApplication([])
    t = DownloadThread(files, ddir, workers, overwrite=overwrite, tr=tr)
    # Direct connection: print from the worker threads, no event loop needed.
    tty = sys.stdout.isatty()

    def log(m):
        if tty:                      # clear the progress line first
            sys.stdout.write("\r" + " " * 79 + "\r")
        out(m)
    t.log.connect(log, Qt.DirectConnection)
    runner = threading.Thread(target=t.run, daemon=True)
    runner.start()
    last = 0.0
    try:
        while runner.is_alive():
            runner.join(0.5)
            done, total, spd, eta, _ = t.snapshot()
            now = time.time()
            if tty:
                sys.stdout.write(f"\r{done}/{total}  {human_speed(spd)}  ETA {human_eta(eta)}   ")
                sys.stdout.flush()
            elif now - last > 10:
                last = now
                out(f"{done}/{total}")
    except KeyboardInterrupt:
        out("\n" + tr("log_dl_stopping"))
        t.stop()
        runner.join()
    if tty:
        sys.stdout.write("\r" + " " * 79 + "\r")
    out(tr("log_dl_done", d=t.dl, s=t.skip, f=t.fail))
    for song, f in t.failed:
        out(f"  ✗ {f['file_path']}")
    return 1 if t.fail or t.stopped else 0


def song_files(songs):
    return [(s, f) for s in songs for f in s["files"]]


# ---------------------------------------------------------------- commands
def cmd_status(args, tr):
    from workers import read_local_version, fetch_remote_version, vsort_installed_commit
    out(f"ESEManager {APP_VERSION}")
    out(f"{tr('cli_app_dir')}: {APP_DIR}")
    out(f"{tr('dir')}: {args.dir}")
    local = read_local_version()
    out(f"{tr('cli_db_local')}: {local or tr('dbv_none')}")
    remote = fetch_remote_version()
    out(f"{tr('cli_db_remote')}: {remote or '?'}")
    if os.path.exists(DB_PATH) and os.path.getsize(DB_PATH) > 0:
        out(tr("total", n=len(search("", None))))
    vs = vsort_installed_commit(args.dir)
    out(f"{VSORT_FOLDER}: {vs[:7] if vs else tr('dbv_none')}")
    return 0


def cmd_update_db(args, tr):
    from workers import read_local_version, fetch_remote_version, update_databases
    remote = fetch_remote_version()
    if not remote:
        out(tr("db_offline"))
        return 1
    local = read_local_version()
    if remote == local and not args.force and os.path.exists(DB_PATH):
        out(tr("db_latest", v=local))
        return 0
    try:
        v = update_databases(remote, log=out, tr=tr)
    except Exception as e:
        out(tr("db_fail", e=e))
        return 1
    out(f"{tr('dbv_ok')} ({v})")
    return 0


def print_songs(songs, limit):
    from workers import load_jp_map
    jp = load_jp_map()
    for s in songs[:limit] if limit else songs:
        cat = CATEGORY_NAMES.get(s["category"], s["category"])
        ja = jp.get(s["song_name"], "")
        out(f"{s['song_name']}" + (f"  /  {ja}" if ja and ja != s["song_name"] else "")
            + f"   [{cat}]  {len(s['files'])}")
    if limit and len(songs) > limit:
        out(f"… (+{len(songs) - limit})")


def cmd_search(args, tr):
    if not need_db(tr):
        return 2
    songs = search(args.keyword, args.category)
    print_songs(songs, args.limit)
    out(tr("total", n=len(songs)))
    return 0 if songs else 2


def cmd_download(args, tr):
    if not need_db(tr):
        return 2
    if not args.keyword and not args.category and not args.all:
        out(tr("cli_download_what"))
        return 2
    songs = search(args.keyword, args.category)
    if not songs:
        out(tr("total", n=0))
        return 2
    files = song_files(songs)
    out(tr("cli_found", n=len(songs), f=len(files)))
    if len(files) > 50 and not confirm(tr("cli_continue"), args.yes):
        return 2
    return run_download(files, args.dir, args.workers, tr)


def cmd_missing(args, tr):
    from appconfig import safe_join, UnsafePathError
    if not need_db(tr):
        return 2
    missing = []
    for s in search("", None):
        for f in s["files"]:
            try:
                if not os.path.exists(safe_join(args.dir, f["file_path"])):
                    missing.append(s)
                    break
            except UnsafePathError:
                continue
    if not missing:
        out(tr("missing_none"))
        return 0
    files = song_files(missing)
    out(tr("cli_missing", n=len(missing), f=len(files)))
    if not args.download:
        print_songs(missing, args.limit)
        return 0
    if not confirm(tr("cli_continue"), args.yes):
        return 2
    return run_download(files, args.dir, args.workers, tr)


def cmd_updates(args, tr):
    from PySide6.QtCore import QCoreApplication
    from workers import CheckUpdatesThread
    if not need_db(tr):
        return 2
    if not os.path.isdir(args.dir):
        out(tr("dir_missing"))
        return 2
    QCoreApplication.instance() or QCoreApplication([])
    t = CheckUpdatesThread(args.dir)
    res = {}
    t.done.connect(lambda songs: res.update(songs=songs))
    t.fail.connect(lambda e: res.update(err=e))
    out(tr("upd_checking"))
    t.run()
    if "err" in res:
        out(tr("upd_no_sha") if res["err"] == "__NO_SHA__" else res["err"])
        return 1
    songs = res.get("songs") or []
    if not songs:
        out(tr("upd_none"))
        return 0
    files = song_files(songs)
    out(tr("cli_updated", n=len(songs), f=len(files)))
    if not args.download:
        print_songs(songs, args.limit)
        return 0
    if not confirm(tr("cli_continue"), args.yes):
        return 2
    return run_download(files, args.dir, args.workers, tr, overwrite=True)


def cmd_version_sorting(args, tr):
    from workers import download_version_sorting
    try:
        status, commit = download_version_sorting(args.dir, log=out, force=args.force)
    except Exception as e:
        out(tr("vsort_fail", e=e))
        return 1
    out(tr("vsort_latest" if status == "latest" else "vsort_done", c=commit[:7]))
    return 0


# ---------------------------------------------------------------- entry point
def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--dir", help="download folder (default: config.toml or ./Downloads)")
    common.add_argument("--workers", type=int, default=None, help="parallel downloads (1-16)")
    common.add_argument("--lang", choices=["zh_TW", "en", "ja"], help="output language")

    p = argparse.ArgumentParser(
        prog="ESEManager-cli", description="ESEManager command-line mode",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__.split("\n\n")[1])
    p.add_argument("--version", action="version", version=f"ESEManager {APP_VERSION}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("status", parents=[common], help="versions, folders, song count")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("update-db", parents=[common], help="download the latest song database")
    sp.add_argument("--force", action="store_true", help="download even if up to date")
    sp.set_defaults(func=cmd_update_db)

    sp = sub.add_parser("search", parents=[common], help="search songs")
    sp.add_argument("keyword", nargs="?", default="")
    sp.add_argument("-c", "--category")
    sp.add_argument("--limit", type=int, default=50, help="max rows to print (0 = all)")
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("download", parents=[common], help="download matching songs")
    sp.add_argument("keyword", nargs="?", default="")
    sp.add_argument("-c", "--category")
    sp.add_argument("--all", action="store_true", help="download every song")
    sp.add_argument("-y", "--yes", action="store_true", help="do not ask for confirmation")
    sp.set_defaults(func=cmd_download)

    for name, func, helptext in (("missing", cmd_missing, "songs not downloaded yet"),
                                 ("updates", cmd_updates, "downloaded charts changed upstream")):
        sp = sub.add_parser(name, parents=[common], help=helptext)
        sp.add_argument("--download", action="store_true", help="download them")
        sp.add_argument("-y", "--yes", action="store_true", help="do not ask for confirmation")
        sp.add_argument("--limit", type=int, default=50, help="max rows to print (0 = all)")
        sp.set_defaults(func=func)

    sp = sub.add_parser("version-sorting", parents=[common],
                        help=f"download {VSORT_FOLDER} into the download folder")
    sp.add_argument("--force", action="store_true", help="download even if up to date")
    sp.set_defaults(func=cmd_version_sorting)
    return p


def main(argv=None):
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    os.chdir(APP_DIR)
    args = build_parser().parse_args(argv)
    cfg = load_config()
    pref = args.lang or cfg.get("display", {}).get("ui_language", "auto")
    tr = make_tr(detect_system_lang() if pref in (None, "auto") else pref)
    args.dir = resolve_dir(args.dir or cfg.get("download", {}).get("directory")
                           or DEFAULT_DOWNLOAD_DIR)
    if args.workers is None:
        args.workers = cfg.get("download", {}).get("workers", 5)
    args.workers = max(1, min(16, int(args.workers)))
    return args.func(args, tr)


if __name__ == "__main__":
    sys.exit(main())
