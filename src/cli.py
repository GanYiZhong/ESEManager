"""
ESEManager command-line mode.

    ESEManager-cli status [--offline]
    ESEManager-cli update-db [--force]
    ESEManager-cli search KEYWORD [-c CATEGORY]... [--new] [--favourites] [--limit N]
    ESEManager-cli download [KEYWORD] [-c CATEGORY]... [--all] [--favourites] [-y]
    ESEManager-cli export [KEYWORD] [-c CATEGORY]... [--favourites] [--text] [-o FILE]
    ESEManager-cli download --from-list FILE
    ESEManager-cli missing [--download] [-y] [--limit N]
    ESEManager-cli updates [--changed-only] [--download] [-y] [--limit N]
    ESEManager-cli version-sorting [--force]
    ESEManager-cli cleanup [--dry-run] [--yes] [--part-files-only|--orphans|--strays|--empty|--all]
                           [--permanent]
    ESEManager-cli self-update [--check] [-y]

Common options: --dir DIR (download folder; default from config.toml or
./Downloads next to the app), --workers N (parallel downloads, 1-8, default 3
or config.toml), --lang zh_TW|en|ja, --json (machine-readable output on
stdout: one JSON object per line; messages go to stderr), --quiet (results
and errors only). Colour only on a terminal; NO_COLOR turns it off.

Uses the same databases, download folder and verification as the GUI.
From source: python src/cli.py ...   Release builds: ESEManager-cli(.exe).
Exit codes: 0 success, 1 something failed, 2 bad usage / nothing to work on.
"""

import argparse
import json
import os
import shutil
import sys
import threading
import time
import unicodedata

try:
    import tomllib
except ImportError:          # Python < 3.11
    import tomli as tomllib

import core
import crash
import songlist
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
    human messages on stderr, so scripts can parse stdout safely.
    --quiet drops the chatter; errors (err) are always shown on stderr."""

    def __init__(self, as_json=False, quiet=False):
        self.json = as_json
        self.quiet = quiet

    def stream(self):
        return sys.stderr if self.json else sys.stdout

    def msg(self, text=""):
        if not self.quiet:
            print(text, file=self.stream(), flush=True)

    def err(self, text):
        print(paint(text, "31", sys.stderr), file=sys.stderr, flush=True)

    def data(self, obj):
        if self.json:
            print(json.dumps(obj, ensure_ascii=False), flush=True)


out = Output()


def use_color(stream):
    """Colour only on a terminal, and never when NO_COLOR is set."""
    if os.environ.get("NO_COLOR"):
        return False
    try:
        return bool(stream.isatty())
    except Exception:
        return False


def paint(text, code, stream=None):
    stream = stream or out.stream()
    return f"\033[{code}m{text}\033[0m" if use_color(stream) else text


def disp_width(text):
    """Terminal cells the text occupies (CJK full-width characters take two)."""
    return sum(0 if unicodedata.combining(ch) else
               2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def fit(text, width):
    """Pad with spaces to `width` cells, or cut with an ellipsis if longer."""
    w = disp_width(text)
    if w <= width:
        return text + " " * (width - w)
    cut, used = "", 0
    for ch in text:
        cw = disp_width(ch)
        if used + cw > width - 1:
            break
        cut += ch
        used += cw
    return cut + "…" + " " * (width - used - 1)


def render_progress(done, total, spd, eta, cols, bytes_done=None, bytes_total=None,
                    exact=True):
    """One progress line: bar, percent, count, speed, ETA; never wider than cols-1.
    With bytes_* the percentage and bar follow bytes and the line reads
    '35%  120 / 340 MB  3.2 MB/s  ETA 1:05  42/120 files'."""
    if bytes_total:
        frac = min(1.0, (bytes_done or 0) / bytes_total)
        pct = int(frac * 100)
        size = ("" if exact else "~") + core.human_bytes_pair(bytes_done or 0, bytes_total)
        tail = (f" {pct:3d}%  {size}  {core.human_speed(spd)}  "
                f"ETA {core.human_clock(eta)}  {done}/{total} files")
        if len(tail) > cols - 1 - 10:       # narrow terminal: drop the file count
            tail = f" {pct:3d}%  {size}  {core.human_speed(spd)}  ETA {core.human_clock(eta)}"
        done_f, total_f = frac, 1.0
    else:
        pct = int(done * 100 / total) if total else 100
        tail = f" {pct:3d}%  {done}/{total}  {core.human_speed(spd)}  ETA {core.human_eta(eta)}"
        done_f, total_f = done, total
    bar_w = max(0, min(30, cols - 1 - len(tail) - 2))
    if bar_w < 8:
        return tail.strip()[:max(0, cols - 1)]
    fill = int(bar_w * done_f / total_f) if total_f else bar_w
    return f"[{'#' * fill}{'-' * (bar_w - fill)}]{tail}"


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
        out.err(tr("cli_no_db"))
        return False
    return True


def song_record(s, jp):
    return {"song": s["song_name"], "title_ja": jp.get(s["song_name"]) or None,
            "category": s["category"], "files": [f["file_path"] for f in s["files"]]}


def run_download(files, ddir, workers, tr, overwrite=False, force=False):
    """Download with a progress bar on a terminal (every 10 s otherwise).
    Refuses (exit 2) when the expected size x 1.1 exceeds the free disk
    space, unless force."""
    plan = core.plan_download(files, ddir, overwrite)
    if plan["expected"] > 0:
        free = core.human_bytes(plan["free"]) if plan["free"] is not None else "?"
        out.msg(tr("cli_expected", size=core.human_bytes(plan["expected"]), free=free))
    if not plan["ok"] and not force:
        out.err(tr("cli_disk_short", free=core.human_bytes(plan["free"]),
                   need=core.human_bytes(plan["need"])))
        return 2
    stream = out.stream()
    tty = stream.isatty() and not out.quiet

    def clear():
        if tty:
            cols = shutil.get_terminal_size((80, 24)).columns
            stream.write("\r" + " " * (cols - 1) + "\r")

    def log(m):
        clear()
        out.msg(m)

    job = core.Downloader(files, ddir, workers, overwrite=overwrite, tr=tr, log=log)
    runner = threading.Thread(target=job.run, daemon=True)
    runner.start()
    last = 0.0
    try:
        while runner.is_alive():
            runner.join(0.5)
            info, _ = job.snapshot_ex()
            done, total = info["done"], info["total"]
            now = time.time()
            if tty:
                cols = shutil.get_terminal_size((80, 24)).columns
                line = render_progress(done, total, info["speed"], info["eta"], cols,
                                       info["bytes_done"], info["bytes_total"],
                                       info["exact"])
                stream.write("\r" + line + " " * max(0, cols - 1 - len(line)))
                stream.flush()
            elif not out.quiet and now - last > 10:
                last = now
                out.msg(f"{done}/{total}")
    except KeyboardInterrupt:
        clear()
        out.msg(tr("log_dl_stopping"))
        job.stop()
        runner.join()
    clear()
    summary = tr("log_dl_done", d=job.dl, s=job.skip, f=job.fail)
    out.msg(paint(summary, "31" if job.fail else "32"))
    if job.saved_text():
        out.msg(job.saved_text())
    for song, f in job.failed:
        out.err(f"  ✗ {f['file_path']}")
    out.data({"downloaded": job.dl, "skipped": job.skip, "failed": job.fail,
              "total": job.total, "stopped": job.stopped,
              "copied": job.copied, "saved_bytes": job.saved_bytes,
              "failed_files": [f["file_path"] for _, f in job.failed]})
    return 1 if job.fail or job.stopped else 0


def song_files(songs):
    return [(s, f) for s in songs for f in s["files"]]


def print_songs(songs, limit):
    jp = core.load_jp_map()
    shown = songs[:limit] if limit else songs
    if out.json:
        for s in shown:
            out.data(song_record(s, jp))
        return
    if out.quiet:                    # one song per line, nothing else
        for s in shown:
            print(s["song_name"], flush=True)
        return
    rows = [(s["song_name"],
             jp.get(s["song_name"], "") if jp.get(s["song_name"]) != s["song_name"] else "",
             CATEGORY_NAMES.get(s["category"], s["category"]), str(len(s["files"])))
            for s in shown]
    w1 = min(36, max((disp_width(r[0]) for r in rows), default=0))
    w2 = min(30, max((disp_width(r[1]) for r in rows), default=0))
    w3 = max((disp_width(r[2]) for r in rows), default=0)
    for name, ja, cat, n in rows:
        line = "  ".join((paint(fit(name, w1), "1"), paint(fit(ja, w2), "36"),
                          fit(cat, w3), n.rjust(3)))
        out.msg(line.rstrip())
    if limit and len(songs) > limit:
        out.msg(f"… (+{len(songs) - limit})")


def quote_arg(text):
    return f'"{text}"' if text and any(c in text for c in " \t()&|;<>") else text


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
    if songs is None and not core.has_song_db():
        out.msg(tr("cli_no_db"))
    return 0


def cmd_detect_folders(args, tr):
    found = core.find_song_folders()
    out.data({"folders": found})
    if out.json:
        return 0
    if not found:
        out.msg(tr("cli_detect_none"))
        return 0
    for c in found:
        out.msg(f"{c['path']}  ({core.describe_song_folder(c, tr)})")
    return 0


def cmd_update_db(args, tr):
    remote = core.fetch_remote_version()
    if not remote:
        out.err(tr("db_offline"))
        return 1
    local = core.read_local_version()
    if remote == local and not args.force and core.has_song_db():
        out.msg(tr("db_latest", v=local))
        out.data({"status": "latest", "version": local})
        return 0
    try:
        v = core.update_databases(remote, log=out.msg, tr=tr)
    except Exception as e:
        core.log.warning("database update failed", exc_info=True)
        out.err(tr("db_fail", e=core.friendly_error(e, tr)))
        return 1
    out.msg(f"{tr('dbv_ok')} ({v})")
    d = core.load_new_songs()
    out.msg(tr("sn_summary", new=len(d["added"]), upd=len(d["changed"])))
    out.data({"status": "updated", "version": v,
              "new": len(d["added"]), "updated": len(d["changed"])})
    return 0


def cmd_search(args, tr):
    if not need_db(tr):
        return 2
    songs = core.search_songs(args.keyword, args.category)
    if args.new:
        songs = core.filter_new_songs(songs, core.new_song_marks())
    if args.favourites:
        songs = core.filter_favourites(songs, core.load_favourites())
    print_songs(songs, args.limit)
    if not songs:
        out.err(tr("sn_none" if args.new else "total", n=0))
        sug = core.suggest(args.keyword, 3) if args.keyword else []
        if sug:
            out.msg(tr("did_you_mean", items=", ".join(sug)))
        return 2
    out.msg(tr("total", n=len(songs)))
    if args.keyword or args.category:
        cmd = "ESEManager-cli download"
        if args.keyword:
            cmd += " " + quote_arg(args.keyword)
        for c in args.category or ():
            cmd += " -c " + quote_arg(c)
        out.msg(paint(tr("cli_next", cmd=cmd), "2"))
    return 0


def cmd_download(args, tr):
    if not need_db(tr):
        return 2
    if args.from_list:
        songs = load_list_songs(args.from_list, tr)
        if songs is None:
            return 2
    elif not args.keyword and not args.category and not args.all and not args.favourites:
        out.err(tr("cli_download_what"))
        return 2
    else:
        songs = core.search_songs(args.keyword, args.category)
        if args.favourites:
            songs = core.filter_favourites(songs, core.load_favourites())
    if not songs:
        out.err(tr("total", n=0))
        return 2
    files = song_files(songs)
    out.msg(tr("cli_found", n=len(songs), f=len(files)))
    if len(files) > 50 and not confirm(tr("cli_continue"), args.yes):
        return 2
    return run_download(files, args.dir, args.workers, tr,
                        force=getattr(args, "force", False))


def load_list_songs(path, tr):
    """Songs of a song-list file (JSON or text; '-' = stdin); None on error."""
    try:
        if path == "-":
            text = sys.stdin.read()
        else:
            with open(path, encoding="utf-8-sig") as fh:
                text = fh.read()
        entries, _ = songlist.parse(text)
    except (OSError, ValueError, UnicodeDecodeError) as e:
        out.err(tr("sl_open_fail", e=e))
        return None
    if not entries:
        out.err(tr("sl_bad"))
        return None
    res = songlist.match(entries, core.search_songs("", None))
    out.msg(songlist.report(res, tr))
    if not res.songs:
        out.err(tr("cli_list_none"))
        return None
    return res.songs


def cmd_export(args, tr):
    if not need_db(tr):
        return 2
    if not args.keyword and not args.category and not args.favourites and not args.all:
        out.err(tr("cli_export_what"))
        return 2
    songs = core.search_songs(args.keyword, args.category)
    if args.favourites:
        songs = core.filter_favourites(songs, core.load_favourites())
    if not songs:
        out.err(tr("total", n=0))
        return 2
    entries = songlist.entries_from_songs(songs)
    as_text = args.text or bool(args.output and args.output.lower().endswith(".txt"))
    data = songlist.to_text(entries) if as_text else songlist.to_json(entries, args.name or "")
    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as fh:
                fh.write(data)
        except OSError as e:
            out.err(tr("sl_save_fail", e=e))
            return 1
        out.msg(tr("sl_saved", n=len(songs), p=args.output))
    else:
        sys.stdout.write(data)
        sys.stdout.flush()
    return 0


def _report_found(songs, key, args, tr, overwrite):
    files = song_files(songs)
    out.msg(tr(key, n=len(songs), f=len(files)))
    if not args.download:
        print_songs(songs, args.limit)
        return 0
    if not confirm(tr("cli_continue"), args.yes):
        return 2
    return run_download(files, args.dir, args.workers, tr, overwrite=overwrite,
                        force=getattr(args, "force", False))


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
        out.err(tr("dir_missing", d=args.dir))
        return 2
    out.msg(tr("upd_checking"))
    try:
        songs = core.find_updates(
            args.dir, only=core.changed_song_keys() if args.changed_only else None)
    except core.NoShaError:
        out.err(tr("upd_no_sha"))
        return 1
    except Exception as e:
        core.log.warning("update check failed", exc_info=True)
        out.err(core.friendly_error(e, tr))
        return 1
    if not songs:
        out.msg(tr("upd_none"))
        return 0
    return _report_found(songs, "cli_updated", args, tr, overwrite=True)


def _size(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def cmd_cleanup(args, tr):
    """Report leftovers; with --yes trash the chosen kinds (--permanent: delete)."""
    if not need_db(tr):
        return 2
    if not os.path.isdir(args.dir):
        out.err(tr("dir_missing", d=args.dir))
        return 2
    rep = core.analyze_library(args.dir)
    groups = (("orphans", "cleanup_g_orphan", args.orphans or args.all),
              ("strays", "cleanup_g_stray", args.strays or args.all),
              ("parts", "cleanup_g_part", args.part_files_only or args.all),
              ("empty", "cleanup_g_empty", args.empty or args.all))
    found = 0
    for key, label, _sel in groups:
        items = rep[key]
        if not items:
            continue
        out.msg(f"{tr(label)}: {len(items)}, {_size(sum(i['size'] for i in items))}")
        for i in items:
            extra = f"  ({int(i['age'] // 3600)} h)" if key == "parts" else ""
            out.msg(f"  {i['rel']}  {_size(i['size'])}{extra}")
            out.data({"kind": i["kind"], "path": i["path"], "size": i["size"],
                      **({"age": i["age"]} if key == "parts" else {})})
            found += 1
    cats = ", ".join(f"{c} {_size(v['size'])}" for c, v in sorted(rep["categories"].items()))
    out.msg(tr("cleanup_cat_sizes", s=cats))
    if not found:
        out.msg(tr("cleanup_none"))
        return 0
    if args.dry_run or not args.yes:
        if not args.dry_run:
            out.msg(tr("cli_cleanup_hint"))
        return 0
    wanted = [k for k, _l, sel in groups if sel]
    if not wanted:
        out.err(tr("cli_cleanup_need"))
        return 2
    chosen = []
    for k in wanted:
        for i in rep[k]:
            # .part files: all with --all, otherwise only those older than a day
            if k != "parts" or args.all or core.cleanup_default_selection(i):
                chosen.append(i)
    mover = core.delete_permanently if args.permanent else core.move_to_trash
    done, failed = core.cleanup_apply(args.dir, chosen, mover)
    out.msg(tr("cleanup_done", n=len(done), size=_size(sum(i["size"] for i in done))))
    for i in failed:
        out.err(tr("cli_cleanup_trash_fail", p=i["path"]))
    return 1 if failed else 0


def cmd_version_sorting(args, tr):
    try:
        status, commit = core.download_version_sorting(args.dir, log=out.msg,
                                                       force=args.force)
    except Exception as e:
        core.log.warning("version sorting download failed", exc_info=True)
        out.err(tr("vsort_fail", e=core.friendly_error(e, tr)))
        return 1
    out.msg(tr("vsort_latest" if status == "latest" else "vsort_done", c=commit[:7]))
    out.data({"status": status, "commit": commit})
    return 0


def cmd_self_update(args, tr):
    try:
        release = core.fetch_latest_release()
    except Exception as e:
        core.log.warning("self-update failed", exc_info=True)
        out.err(tr("upd_app_fail_cli", e=core.friendly_error(e, tr)))
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
        core.log.warning("self-update failed", exc_info=True)
        out.err(tr("upd_app_fail_cli", e=core.friendly_error(e, tr)))
        return 1
    out.msg(tr("upd_app_scheduled_cli" if how == "scheduled" else "upd_app_done_cli", v=tag))
    return 0


# ---------------------------------------------------------------- entry point
def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--dir", help="download folder (default: config.toml or ./Downloads)")
    common.add_argument("--source", help="download host: auto (fastest), ese, taiko.ac or a "
                        "base URL (default: config.toml or auto; the other host is the fallback)")
    common.add_argument("--workers", type=int, default=None,
                        help=f"parallel downloads, 1-{MAX_WORKERS} "
                             f"(default: config.toml or {DEFAULT_WORKERS})")
    common.add_argument("--lang", choices=["zh_TW", "en", "ja"], help="message language")
    common.add_argument("--json", action="store_true",
                        help="JSON lines on stdout (messages go to stderr)")

    common.add_argument("--debug", action="store_true",
                        help="show the full traceback on an unexpected error")
    common.add_argument("-q", "--quiet", action="store_true",
                        help="only results and errors (search prints one song name per line)")

    p = argparse.ArgumentParser(
        prog="ESEManager-cli", description="ESEManager command-line mode",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__.split("\n\n")[1])
    p.add_argument("--version", action="version", version=f"ESEManager {APP_VERSION}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("status", parents=[common], help="versions, folders, song count")
    sp.add_argument("--offline", action="store_true",
                    help="do not ask GitHub Pages for the latest database version")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("detect-folders", parents=[common],
                        help="list likely Taiko simulator song folders")
    sp.set_defaults(func=cmd_detect_folders)

    sp = sub.add_parser("update-db", parents=[common], help="download the latest song database")
    sp.add_argument("--force", action="store_true", help="download even if up to date")
    sp.set_defaults(func=cmd_update_db)

    sp = sub.add_parser("search", parents=[common], help="search songs")
    sp.add_argument("keyword", nargs="?", default="")
    sp.add_argument("-c", "--category", action="append",
                    help="category name or part of it, e.g. Anime (repeat for several)")
    sp.add_argument("--new", action="store_true",
                    help="only songs added or changed by the last database update")
    sp.add_argument("--limit", type=int, default=50, help="max rows to print (0 = all)")
    sp.add_argument("--favourites", action="store_true", help="only starred songs")
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("download", parents=[common], help="download matching songs")
    sp.add_argument("keyword", nargs="?", default="")
    sp.add_argument("-c", "--category", action="append",
                    help="category name or part of it, e.g. Anime (repeat for several)")
    sp.add_argument("--all", action="store_true", help="download every song")
    sp.add_argument("--favourites", action="store_true", help="download the starred songs")
    sp.add_argument("--from-list", metavar="FILE",
                    help="download the songs of a song-list file (JSON or text, - = stdin)")
    sp.add_argument("-y", "--yes", action="store_true", help="do not ask for confirmation")
    sp.add_argument("--force", action="store_true",
                    help="download even if the free disk space looks too small")
    sp.set_defaults(func=cmd_download)

    sp = sub.add_parser("export", parents=[common], help="write matching songs to a song-list file")
    sp.add_argument("keyword", nargs="?", default="")
    sp.add_argument("-c", "--category", action="append",
                    help="category name or part of it (repeat for several)")
    sp.add_argument("--all", action="store_true", help="every song")
    sp.add_argument("--favourites", action="store_true", help="only starred songs")
    sp.add_argument("--text", action="store_true", help="plain text (Category/Song per line)")
    sp.add_argument("--name", help="list name stored in the JSON file")
    sp.add_argument("-o", "--output", metavar="FILE",
                    help="write to FILE (.txt = text format); default: stdout")
    sp.set_defaults(func=cmd_export)

    for name, func, helptext in (("missing", cmd_missing, "songs not downloaded yet"),
                                 ("updates", cmd_updates, "downloaded charts changed upstream")):
        sp = sub.add_parser(name, parents=[common], help=helptext)
        sp.add_argument("--download", action="store_true", help="download them")
        sp.add_argument("--force", action="store_true",
                        help="download even if the free disk space looks too small")
        sp.add_argument("-y", "--yes", action="store_true", help="do not ask for confirmation")
        sp.add_argument("--limit", type=int, default=50, help="max rows to print (0 = all)")
        if name == "updates":
            sp.add_argument("--changed-only", action="store_true",
                            help="only check songs changed by the last database update (fast)")
        sp.set_defaults(func=func)

    sp = sub.add_parser("version-sorting", parents=[common],
                        help=f"download {VSORT_FOLDER} into the download folder")
    sp.add_argument("--force", action="store_true", help="download even if up to date")
    sp.set_defaults(func=cmd_version_sorting)

    sp = sub.add_parser("cleanup", parents=[common],
                        help="list (default) or trash leftovers in the download folder")
    sp.add_argument("--dry-run", action="store_true", help="only print the report (default)")
    sp.add_argument("-y", "--yes", action="store_true", help="actually clean up the chosen kinds")
    sp.add_argument("--part-files-only", action="store_true",
                    help="leftover .part files older than a day")
    sp.add_argument("--orphans", action="store_true", help="song folders not in the database")
    sp.add_argument("--strays", action="store_true", help="files the database does not list")
    sp.add_argument("--empty", action="store_true", help="empty folders")
    sp.add_argument("--all", action="store_true", help="every kind (incl. all .part files)")
    sp.add_argument("--permanent", action="store_true",
                    help="delete for good instead of moving to the trash")
    sp.set_defaults(func=cmd_cleanup)

    sp = sub.add_parser("self-update", parents=[common],
                        help="download the latest ESEManager release over this folder")
    sp.add_argument("--check", action="store_true", help="only report whether one is available")
    sp.add_argument("-y", "--yes", action="store_true", help="do not ask for confirmation")
    sp.set_defaults(func=cmd_self_update)
    return p


def _main(argv=None):
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
    out.quiet = args.quiet
    cfg = load_config()
    pref = args.lang or cfg.get("display", {}).get("ui_language", "auto")
    tr = make_tr(detect_system_lang() if pref in (None, "auto") else pref)
    args.dir = resolve_dir(args.dir or cfg.get("download", {}).get("directory")
                           or DEFAULT_DOWNLOAD_DIR)
    core.set_download_source(args.source or cfg.get("download", {}).get("source"))
    if args.workers is None:
        args.workers = cfg.get("download", {}).get("workers", DEFAULT_WORKERS)
    try:
        args.workers = max(1, min(MAX_WORKERS, int(args.workers)))
    except (TypeError, ValueError):
        args.workers = DEFAULT_WORKERS
    return args.func(args, tr)


def main(argv=None):
    try:
        return _main(argv)
    except Exception as e:      # SystemExit / KeyboardInterrupt pass through
        return crash.cli_fail(e, argv if argv is not None else sys.argv)


if __name__ == "__main__":
    sys.exit(main())
