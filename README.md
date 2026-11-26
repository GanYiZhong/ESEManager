# ESEManager

A fast desktop GUI to browse and download Taiko no Tatsujin (太鼓の達人) TJA charts
from the **ESE (Every Song Ever)** project.

**English** | [繁體中文](README.zh-TW.md)

## Features

- Fast song browser — thousands of songs in one sortable list, no pagination
- Search as you type (Japanese titles supported) and filter by category
- **Filter by BPM range and difficulty level** (Easy / Normal / Hard / Oni / Ura)
- Batch download with **pause / resume / stop**, live progress and one-click retry of failed files
- **Check missing** and **check updates**: find songs you have not downloaded yet, or
  downloaded charts that changed upstream (compared by git blob hash)
- Song databases are rebuilt from ESE every 6 hours on GitHub; **Update DB** downloads the
  latest one, and the app offers it on startup when a newer one exists
- Downloads are verified (TLS, size and git blob hash for charts) and written to a `.part` file
  first, so an interrupted download never leaves a broken file behind
- **Mirror**: choose the download source in Settings (ESE official or the
  [git.taiko.ac](https://git.taiko.ac/zdon/ESE) mirror); when it is down, lacks a file or serves
  outdated content, the other one is used automatically
- Light / dark theme and UI language auto-detect (English / 繁體中文 / 日本語)
- One-click download of [ESE-Version-Sorting](https://ese.tjadataba.se/Yonokid/ESE-Version-Sorting)
  (YataiDON version folders) into the download folder: **File → Download version sorting**
- Command-line mode (`ESEManager-cli`) for scripts and servers
- Rolling releases with **one-click self-update**: when a newer version exists, click the notice
  in the status bar; the app downloads it, checks its SHA-256, installs it over itself and
  restarts (settings, databases and downloads are kept)

## Quick start

Download the latest release for your platform from the
[Releases page](https://github.com/GanYiZhong/ESEManager/releases/latest), extract it and run
`ESEManager` (`ESEManager.exe` on Windows). On first start the app offers to download the song
database; after that, search and download.

Settings, databases and the default `Downloads` folder live next to the executable, so you can
update in place: click the update notice in the status bar, run `ESEManager-cli self-update`, or
extract a new version over the old folder by hand.

On Linux, if Qt reports it cannot load the `xcb` platform plugin, install `libxcb-cursor0`
(Debian/Ubuntu) or `xcb-util-cursor` (Fedora/Arch).

## Command-line mode

Release builds include `ESEManager-cli` (`ESEManager-cli.exe` on Windows) next to the GUI; from
source run `python src/cli.py`. It uses the same databases, settings and download folder.

```
ESEManager-cli status [--offline]          # versions, folders, song count
ESEManager-cli update-db                   # download the latest song database
ESEManager-cli search 千本桜               # Japanese titles work too
ESEManager-cli download Senbonzakura -y    # download matching songs
ESEManager-cli download --all -y           # everything
ESEManager-cli missing --download -y       # songs you don't have yet
ESEManager-cli updates --download -y       # charts changed upstream
ESEManager-cli version-sorting             # install/refresh ESE-Version-Sorting
ESEManager-cli self-update                 # install the latest ESEManager over this one
```

| Option | Commands | Meaning |
|---|---|---|
| `--dir DIR` | all | download folder (default: `config.toml`, else `Downloads` next to the app) |
| `--workers N` | download, missing, updates | parallel downloads, 1–8 (default: `config.toml`, else 3) |
| `--source S` | download, updates | download host: `ese`, `taiko.ac` or a base URL (default: `config.toml`, else `ese`; the other is the fallback) |
| `--lang zh_TW\|en\|ja` | all | message language |
| `--json` | all | one JSON object per line on stdout; messages go to stderr |
| `-q`, `--quiet` | all | Results and errors only; `search` prints one song name per line |
| `-c`, `--category NAME` | search, download | category, or part of its name (`-c Anime`) |
| `--limit N` | search, missing, updates | rows to print (default 50, 0 = all) |
| `--all` | download | download every song |
| `--download` | missing, updates | download what was found instead of listing it |
| `-y`, `--yes` | download, missing, updates, self-update | do not ask for confirmation |
| `--force` | update-db, version-sorting | download even if already up to date |
| `--offline` | status | do not ask GitHub Pages for the latest database version |
| `--check` | self-update | only report whether a newer version exists |

On a terminal you get a progress bar (percent, speed, ETA) and coloured results; set `NO_COLOR` to turn colour off (it is never used when piped). `search` ends with a hint for the matching `download` command.

Exit code 0 = success, 1 = something failed, 2 = nothing to do / bad usage. Without a
terminal (scripts, cron) confirmation prompts answer "no", so pass `-y` there.

```
ESEManager-cli search Senbonzakura --json | jq -r .song
```

## Run from source

Requires Python 3.9+ (Windows or Linux; macOS should work but is not tested).

```
pip install -r requirements.txt
python src/ese_qt.py
```

Data files are kept in the repository root when running from source. `config.toml` is created
on first run; see `config.toml.example` for the settings. `update_databases.bat` /
`update_databases.sh` download the latest prebuilt databases (same as `cli.py update-db`).
Warnings and errors are written to `ESEManager.log` next to the app.

## Tests

```
pip install -r requirements.txt -r requirements-test.txt
python -m pytest tests --cov=src
```

CI runs the tests on Windows and Linux with a minimum coverage.

## Build the executable

```
pip install -r requirements-build.txt
pyinstaller --noconfirm --clean packaging/ESEManager.spec
python scripts/fetch_release_dbs.py dist/ESEManager   # optional: bundle the current databases
```

Output: the `dist/ESEManager/` folder (onedir build). Ship the whole folder.

## Releases (rolling)

Every push to `main` that changes the app (`src/`, `packaging/`, `assets/`, requirements) is
released automatically by `.github/workflows/release.yml`:

1. run the tests, build Windows and Linux, and smoke-test both;
2. publish a release named by date — `v2026.11.18`, then `v2026.11.18.2` for a second release
   the same day (Asia/Taipei date) — with the commit list as release notes and
   `ESEManager_<version>_windows-x86_64.zip`, `ESEManager_<version>_linux-x86_64.tar.gz` and a
   `.sha256` for each.

Pushes that only touch tests, docs or the workflow build without publishing. Add
`[skip release]` to a commit's first line to skip publishing on purpose. Pull requests are built and
tested only. To rebuild an existing release's files, run the workflow manually with its tag.

## Prebuilt databases (GitHub Pages)

`.github/workflows/pages-db.yml` rebuilds `ese_songs.db` and `ese_local.db` from ESE every
6 hours and publishes them to
<https://ganyizhong.github.io/ESEManager/> together with `version.txt` and `manifest.json`
(sizes + SHA-256). Run the workflow manually with **force** to rebuild anyway.

It is designed to be light on ESE's server:

- one `git ls-remote` every 6 hours; nothing else when ESE has not changed;
- a shallow, blobless clone (file list only, no audio) that is cached between runs, so an
  update only fetches the new commit's tree;
- chart files (`.tja`) are fetched through git in batched requests, and only those whose
  content changed (tracked by git blob hash) — never one HTTP request per file;
- audio (Git LFS) is never downloaded.

One-time setup: **Settings → Pages → Source: GitHub Actions**.

Build the same databases locally (needs Git):

```
python scripts/build_pages_db.py --out site
```

## Project layout

```
src/
  ese_qt.py            main window and entry point
  cli.py               command-line mode
  core.py              search, downloads, update checks, DB / version-sorting updates (no Qt)
  workers.py           thin QThread wrappers around core.py for the GUI
  appconfig.py         data paths, URLs, version, safe path joining
  i18n.py              UI strings (zh_TW / en / ja)
  models.py            song list and download table models
  theme.py, notify.py  light/dark theme; icon and completion notifications
  ese_scraper_git_v2.py, build_local_db.py, tja_parser.py   database builders (used by CI)
scripts/     GitHub Pages database builder, release database fetcher, icon generator
tests/       pytest suite
.github/     workflows: database publishing and rolling releases
packaging/   PyInstaller spec
```

## Contributing

- Keep logic that does not need Qt in `core.py`, so the CLI and tests can use it; the GUI calls
  it through `workers.py`.
- Every user-visible string goes into `i18n.py` in all three languages.
- Add or update tests in `tests/` and run `python -m pytest tests` before opening a pull request.
- Be gentle with the ESE server: no per-file HTTP loops for metadata, keep download
  parallelism low.

## Data source

Charts come from the ESE project: <https://ese.tjadataba.se/ESE/ESE>
Mirror: <https://git.taiko.ac/zdon/ESE> (same paths, may sync a little later; downloads are still
checked against the hashes in the database)
(The former host `git.vanillaaaa.org` is no longer available.)
