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
  latest one (about 5 MB), and the app offers it on startup when a newer one exists
- Downloads are verified (TLS, size and git blob hash for charts) and written to a `.part` file
  first, so an interrupted download never leaves a broken file behind
- Light / dark theme and UI language auto-detect (English / 繁體中文 / 日本語)
- One-click download of [ESE-Version-Sorting](https://ese.tjadataba.se/Yonokid/ESE-Version-Sorting)
  (YataiDON version folders) into the download folder: **File → Download version sorting**
- Command-line mode (`ESEManager-cli`) for scripts and servers
- Rolling releases: the status bar tells you when a newer version is available

## Quick start

Download the latest release for your platform from the
[Releases page](https://github.com/GanYiZhong/ESEManager/releases/latest), extract it and run
`ESEManager` (`ESEManager.exe` on Windows). On first start the app offers to download the song
database; after that, search and download.

Settings, databases and the default `Downloads` folder live next to the executable, so you can
extract a new version over the old folder.

On Linux, if Qt reports it cannot load the `xcb` platform plugin, install `libxcb-cursor0`
(Debian/Ubuntu) or `xcb-util-cursor` (Fedora/Arch).

## Command-line mode

Release builds include `ESEManager-cli` (`ESEManager-cli.exe` on Windows) next to the GUI; from
source run `python src/cli.py`. It uses the same databases, settings and download folder.

```
ESEManager-cli status                      # versions, folders, song count
ESEManager-cli update-db                   # download the latest song database
ESEManager-cli search 千本桜               # Japanese titles work too
ESEManager-cli download Senbonzakura -y    # download matching songs
ESEManager-cli download --all -y           # everything
ESEManager-cli missing --download -y       # songs you don't have yet
ESEManager-cli updates --download -y       # charts changed upstream
ESEManager-cli version-sorting             # install/refresh ESE-Version-Sorting
```

Options: `--dir DIR`, `--workers N`, `--lang zh_TW|en|ja`. Exit code 0 = success,
1 = something failed, 2 = nothing to do / bad usage.

## Run from source

Requires Python 3.9+.

```
pip install -r requirements.txt
python src/ese_qt.py
```

Data files are kept in the repository root when running from source.

## Tests

```
pip install -r requirements.txt pytest
python -m pytest tests
```

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
   `ESEManager_<version>_windows-x86_64.7z`, `ESEManager_<version>_linux-x86_64.tar.gz` and a
   `.sha256` for each.

Pushes that only touch tests, docs or the workflow build without publishing. Add
`[skip release]` to a commit message to skip publishing on purpose. Pull requests are built and
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
  appconfig.py         data paths, URLs, version, safe path joining
  i18n.py              UI strings (zh_TW / en / ja)
  models.py            song list and download table models
  workers.py           background threads (search, download, update checks, DB download)
  theme.py, notify.py  light/dark theme; icon and completion notifications
  tja_parser.py        TJA parsing and the shared text decoder
  download_songs.py    song search (also a CLI downloader)
  ese_scraper_git_v2.py, build_local_db.py   database builders (used by CI)
scripts/     GitHub Pages database builder, release database fetcher, icon generator
tests/       pytest suite
.github/     workflows: database publishing and rolling releases
packaging/   PyInstaller spec
```

## Data source

Charts come from the ESE project: <https://ese.tjadataba.se/ESE/ESE>
(The former host `git.vanillaaaa.org` is no longer available.)
