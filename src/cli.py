"""
ESEManager command-line mode.

    ESEManager-cli status [--offline]
    ESEManager-cli update-db [--force]
    ESEManager-cli search KEYWORD [-c CATEGORY] [--limit N]
    ESEManager-cli download [KEYWORD] [-c CATEGORY] [--all] [-y]
    ESEManager-cli missing [--download] [-y] [--limit N]
    ESEManager-cli updates [--download] [-y] [--limit N]
    ESEManager-cli version-sorting [--force]
    ESEManager-cli self-update [--check] [-y]

Common options: --dir DIR (download folder; default from config.toml or
./Downloads next to the app), --workers N (parallel downloads, 1-8, default 3
or config.toml), --lang zh_TW|en|ja, --json (machine-readable output on
stdout: one JSON object per line; messages go to stderr).

Uses the same databases, download folder and verification as the GUI.
From source: python src/cli.py ...   Release builds: ESEManager-cli(.exe).
Exit codes: 0 success, 1 something failed, 2 bad usage / nothing to work on.
"""

import argparse
import json
import os
import sys
import threading
import time

try:
    import tomllib
except ImportError:          # Python < 3.11
    import tomli as tomllib

import core
from appconfig import (APP_DIR, APP_VERSION, CONFIG_FILE, DEFAULT_DOWNLOAD_DIR,
                       VSORT_FOLDER, resolve_dir)
from i18n import TR, CATEGORY_NAMES, detect_system_lang

MAX_WORKERS = 8              # be gentle with the ESE server
DEFAULT_WORKERS = 3


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


class Output:
    """Human text on stdout, or (with --json) JSON lines on stdout and the
    human messages on stderr, so scripts can parse stdout safely."""

    def __init__(self, as_json=False):
        self.json = as_json

    def msg(self, text=""):
        print(text, file=sys.stderr if self.json else sys.stdout, flush=True)

    def data(self, obj):
        if self.json:
            print(json.dumps(obj, ensure_ascii=False), flush=True)


out = Output()


def confirm(question, assume_yes):
    if assume_yes:
        return True
    if not sys.stdin or not sys.stdin.isatty():
        return False
    try:
        out.msg(f"{question} [y/N] ")
        return input().strip().lower() in ("y", "yes")
    except EOFError:
        return False


def need_db(tr):
    if not core.has_song_db():
        out.msg(tr("cli_no_db"))
        return False
    return True


def song_record(s, jp):
    return {"song": s["song_name"], "title_ja": jp.get(s["song_name"]) or None,
            "category": s["category"], "files": [f["file_path"] for f in s["files"]]}


def run_download(files, ddir, workers, tr, overwrite=False):
    """Download with a progress line on a terminal (every 10 s otherwise)."""
    tty = sys.stderr.isatty() if out.json else sys.stdout.isatty()
    stream = sys.stderr if out.json else sys.stdout

    def log(m):
        if tty:                      # clear the progress line first
            stream.write("\r" + " " * 79 + "\r")
        out.msg(m)

    job = core.Downloader(files, ddir, workers, overwrite=overwrite, tr=tr, log=log)
    runner = threading.Thread(target=job.run, daemon=True)
    runner.start()
    last = 0.0
    try:
        while runner.is_alive():
            runner.join(0.5)
            done, total, spd, eta, _ = job.snapshot()
            now = time.time()
            if tty:
                stream.write(f"\r{done}/{total}  {core.human_speed(spd)}  "
                             f"ETA {core.human_eta(eta)}   ")
                stream.flush()
            elif now - last > 10:
                last = now
                out.msg(f"{done}/{total}")
    except KeyboardInterrupt:
        out.msg("\n" + tr("log_dl_stopping"))
        job.stop()
        runner.join()
    if tty:
        stream.write("\r" + " " * 79 + "\r")
    out.msg(tr("log_dl_done", d=job.dl, s=job.skip, f=job.fail))
    for song, f in job.failed:
        out.msg(f"  ✗ {f['file_path']}")
    out.data({"downloaded": job.dl, "skipped": job.skip, "failed": job.fail,
              "total": job.total, "stopped": job.stopped,
              "failed_files": [f["file_path"] for _, f in job.failed]})
    return 1 if job.fail or job.stopped else 0


def song_files(songs):
    return [(s, f) for s in songs for f in s["files"]]


def print_songs(songs, limit):
    jp = core.load_jp_map()
    shown = songs[:limit] if limit else songs
    for s in shown:
        if out.json:
            out.data(song_record(s, jp))
            continue
        cat = CATEGORY_NAMES.get(s["category"], s["category"])
        ja = jp.get(s["song_name"], "")
        out.msg(f"{s['song_name']}" + (f"  /  {ja}" if ja and ja != s["song_name"] else "")
                + f"   [{cat}]  {len(s['files'])}")
    if limit and len(songs) > limit:
        out.msg(f"… (+{len(songs) - limit})")


# ---------------------------------------------------------------- commands
def cmd_status(args, tr):
    local = core.read_local_version()
    remote = "" if args.offline else core.fetch_remote_version(timeout=5)
    songs = None
    if core.has_song_db():
        try:
            songs = core.count_songs()
        except Exception as e:
            out.msg(tr("db_corrupt", e=e))
    vs = core.vsort_installed_commit(args.dir)
    out.data({"app_version": APP_VERSION, "app_dir": APP_DIR, "download_dir": args.dir,
              "db_version": local or None, "db_latest": remote or None, "songs": songs,
              "version_sorting": vs or None})
    if out.json:
        return 0
    out.msg(f"ESEManager {APP_VERSION}")
    out.msg(f"{tr('cli_app_dir')}: {APP_DIR}")
    out.msg(f"{tr('dir')}: {args.dir}")
    out.msg(f"{tr('cli_db_local')}: {local or tr('dbv_none')}")
    if not args.offline:
        out.msg(f"{tr('cli_db_remote')}: {remote or '?'}")
    if songs is not None:
        out.msg(tr("total", n=songs))
    out.msg(f"{VSORT_FOLDER}: {vs[:7] if vs else tr('dbv_none')}")
    return 0


def cmd_update_db(args, tr):
    remote = core.fetch_remote_version()
    if not remote:
        out.msg(tr("db_offline"))
        return 1
    local = core.read_local_version()
    if remote == local and not args.force and core.has_song_db():
        out.msg(tr("db_latest", v=local))
        out.data({"status": "latest", "version": local})
        return 0
    try:
        v = core.update_databases(remote, log=out.msg, tr=tr)
    except Exception as e:
        out.msg(tr("db_fail", e=e))
        return 1
    out.msg(f"{tr('dbv_ok')} ({v})")
    out.data({"status": "updated", "version": v})
    return 0


def cmd_search(args, tr):
    if not need_db(tr):
        return 2
    songs = core.search_songs(args.keyword, args.category)
    print_songs(songs, args.limit)
    out.msg(tr("total", n=len(songs)))
    return 0 if songs else 2


def cmd_download(args, tr):
    if not need_db(tr):
        return 2
    if not args.keyword and not args.category and not args.all:
        out.msg(tr("cli_download_what"))
        return 2
    songs = core.search_songs(args.keyword, args.category)
    if not songs:
        out.msg(tr("total", n=0))
        return 2
    files = song_files(songs)
    out.msg(tr("cli_found", n=len(songs), f=len(files)))
    if len(files) > 50 and not confirm(tr("cli_continue"), args.yes):
        return 2
    return run_download(files, args.dir, args.workers, tr)


def _report_found(songs, key, args, tr, overwrite):
    files = song_files(songs)
    out.msg(tr(key, n=len(songs), f=len(files)))
    if not args.download:
        print_songs(songs, args.limit)
        return 0
    if not confirm(tr("cli_continue"), args.yes):
        return 2
    return run_download(files, args.dir, args.workers, tr, overwrite=overwrite)


def cmd_missing(args, tr):
    if not need_db(tr):
        return 2
    missing = core.find_missing(core.search_songs("", None), args.dir)
    if not missing:
        out.msg(tr("missing_none"))
        return 0
    return _report_found(missing, "cli_missing", args, tr, overwrite=False)


def cmd_updates(args, tr):
    if not need_db(tr):
        return 2
    if not os.path.isdir(args.dir):
        out.msg(tr("dir_missing", d=args.dir))
        return 2
    out.msg(tr("upd_checking"))
    try:
        songs = core.find_updates(args.dir)
    except core.NoShaError:
        out.msg(tr("upd_no_sha"))
        return 1
    except Exception as e:
        out.msg(str(e))
        return 1
    if not songs:
        out.msg(tr("upd_none"))
        return 0
    return _report_found(songs, "cli_updated", args, tr, overwrite=True)


def cmd_version_sorting(args, tr):
    try:
        status, commit = core.download_version_sorting(args.dir, log=out.msg,
                                                       force=args.force)
    except Exception as e:
        out.msg(tr("vsort_fail", e=e))
        return 1
    out.msg(tr("vsort_latest" if status == "latest" else "vsort_done", c=commit[:7]))
    out.data({"status": status, "commit": commit})
    return 0


def cmd_self_update(args, tr):
    try:
        release = core.fetch_latest_release()
    except Exception as e:
        out.msg(tr("upd_app_fail_cli", e=e))
        return 1
    tag = release.get("tag_name") or ""
    # A source checkout ("dev") has no version to compare: always offer the latest.
    newer = core.is_newer(tag, APP_VERSION) or core.parse_version(APP_VERSION) is None
    out.data({"current": APP_VERSION, "latest": tag, "newer": newer,
              "can_self_update": core.can_self_update()})
    if not newer:
        out.msg(tr("upd_app_latest", v=APP_VERSION))
        return 0
    out.msg(tr("upd_app_available", cur=APP_VERSION, v=tag))
    if args.check:
        return 0
    if not core.can_self_update():
        out.msg(tr("upd_app_manual", url=release.get("html_url") or ""))
        return 2
    if not confirm(tr("cli_continue"), args.yes):
        return 2
    try:
        last = [-1]

        def progress(got, total):
            pct = int(got * 100 / total) if total else 0
            if pct >= last[0] + 10:
                last[0] = pct
                out.msg(tr("upd_app_downloading", p=pct))
        root = core.download_app_update(release, log=out.msg, progress=progress)
        how = core.install_app_update(root)
    except Exception as e:
        out.msg(tr("upd_app_fail_cli", e=e))
        return 1
    out.msg(tr("upd_app_scheduled_cli" if how == "scheduled" else "upd_app_done_cli", v=tag))
    return 0


# ---------------------------------------------------------------- entry point
def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--dir", help="download folder (default: config.toml or ./Downloads)")
    common.add_argument("--workers", type=int, default=None,
                        help=f"parallel downloads, 1-{MAX_WORKERS} "
                             f"(default: config.toml or {DEFAULT_WORKERS})")
    common.add_argument("--lang", choices=["zh_TW", "en", "ja"], help="message language")
    common.add_argument("--json", action="store_true",
                        help="JSON lines on stdout (messages go to stderr)")

    p = argparse.ArgumentParser(
        prog="ESEManager-cli", description="ESEManager command-line mode",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__.split("\n\n")[1])
    p.add_argument("--version", action="version", version=f"ESEManager {APP_VERSION}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("status", parents=[common], help="versions, folders, song count")
    sp.add_argument("--offline", action="store_true",
                    help="do not ask GitHub Pages for the latest database version")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("update-db", parents=[common], help="download the latest song database")
    sp.add_argument("--force", action="store_true", help="download even if up to date")
    sp.set_defaults(func=cmd_update_db)

    sp = sub.add_parser("search", parents=[common], help="search songs")
    sp.add_argument("keyword", nargs="?", default="")
    sp.add_argument("-c", "--category", help="category name or part of it, e.g. Anime")
    sp.add_argument("--limit", type=int, default=50, help="max rows to print (0 = all)")
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("download", parents=[common], help="download matching songs")
    sp.add_argument("keyword", nargs="?", default="")
    sp.add_argument("-c", "--category", help="category name or part of it, e.g. Anime")
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

    sp = sub.add_parser("self-update", parents=[common],
                        help="download the latest ESEManager release over this folder")
    sp.add_argument("--check", action="store_true", help="only report whether one is available")
    sp.add_argument("-y", "--yes", action="store_true", help="do not ask for confirmation")
    sp.set_defaults(func=cmd_self_update)
    return p


def main(argv=None):
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    os.chdir(APP_DIR)
    core.setup_logging()
    try:
        core.cleanup_app_update()
    except Exception:
        pass
    args = build_parser().parse_args(argv)
    out.json = args.json
    cfg = load_config()
    pref = args.lang or cfg.get("display", {}).get("ui_language", "auto")
    tr = make_tr(detect_system_lang() if pref in (None, "auto") else pref)
    args.dir = resolve_dir(args.dir or cfg.get("download", {}).get("directory")
                           or DEFAULT_DOWNLOAD_DIR)
    if args.workers is None:
        args.workers = cfg.get("download", {}).get("workers", DEFAULT_WORKERS)
    try:
        args.workers = max(1, min(MAX_WORKERS, int(args.workers)))
    except (TypeError, ValueError):
        args.workers = DEFAULT_WORKERS
    return args.func(args, tr)


if __name__ == "__main__":
    sys.exit(main())
