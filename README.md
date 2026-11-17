# ESEManager

A fast desktop GUI to browse and download Taiko no Tatsujin (太鼓の達人) TJA charts
from the **ESE (Every Song Ever)** project.

**English** | [繁體中文](README.zh-TW.md)

## Features

- Fast song browser — thousands of songs in a single list, no pagination
- Search by name (Japanese supported) and by category
- **Filter by BPM range and difficulty level** (Easy / Normal / Hard / Oni / Ura) — shown as columns and parsed from each chart
- Batch download with **pause / resume / stop**
- Live monitor: overall progress + speed/ETA, per-file status, log, one-click retry of failed files
- One-click **database update**:
  - song list via a *blobless* git clone of ESE (file list only — no audio downloaded)
  - Japanese titles parsed directly from each chart's `TITLEJA` field (incremental — already-known titles are skipped)
- **Dan tools** (🥋):
  - **Dan Generator** — turn a Taiko Wiki Dan-dojo page URL into TaikøNauts-compatible Dan files (`dan.def` + per-rank `Dan.json`) from the rank names and clear conditions
  - **Dan Convertor** — convert an OpenTaiko-style Dan `.tja` (multiple songs split by `#NEXTSONG`) into TaikøNauts-compatible Dan files
- **Check missing** (🔍) and **check updates** (🆕): find songs you have not downloaded yet, or
  downloaded charts that changed upstream (compared by git blob hash)
- **box.def tools**: an OpenTaiko box.def editor (📦) and a YataiDON box.def generator (🎮)
- Downloads are verified (TLS, size and git blob hash for charts) and written to a `.part` file
  first, so an interrupted download never leaves a broken file behind
- Auto-downloads a portable Git if Git isn't installed (only needed for the manual
  **Update database** button)
- UI language auto-detect (English / 繁體中文 / 日本語)

## Quick start

Download the release for your platform from the
[Releases page](https://github.com/GanYiZhong/ESEManager/releases), extract it and run
`ESEManager` (`ESEManager.exe` on Windows). On first start the app offers to download the
prebuilt song database (about 5 MB); after that, search and download.

Settings, databases and the default `Downloads` folder live next to the executable.

On Linux, if Qt reports it cannot load the `xcb` platform plugin, install `libxcb-cursor0`
(Debian/Ubuntu) or `xcb-util-cursor` (Fedora/Arch).

## Run from source

Requires Python 3.9+. Git is only needed to rebuild the database yourself.

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

## Releasing

1. Bump the version as needed and push to `main`. The **Release builds** workflow
   (`.github/workflows/release.yml`) builds and smoke-tests Windows and Linux on every push and
   pull request that touches the app.
2. Create and publish a GitHub release (for example `gh release create v1.2.0 --generate-notes`).
3. The same workflow builds both platforms from the tag, bundles the current databases
   (verified against `manifest.json`), and uploads
   `ESEManager_<tag>_windows-x86_64.7z`, `ESEManager_<tag>_linux-x86_64.tar.gz` and a
   `.sha256` file for each.

To rebuild the assets of an existing release, run the workflow manually with its tag.

## Update databases from the command line (optional)

The in-app **Update database** button already does this. The CLI equivalent:

**Windows:**
```
update_databases.bat
```

**Linux / macOS:**
```
./update_databases.sh
```

or manually:

```
python src/ese_scraper_git_v2.py --keep     # song list  -> ese_songs.db
python src/build_local_db.py --remote        # JP titles  -> ese_local.db
```

## Prebuilt databases (GitHub Pages)

`.github/workflows/pages-db.yml` rebuilds `ese_songs.db` and `ese_local.db` from ESE every
6 hours (skipped when ESE's master commit has not changed) and publishes them to
<https://ganyizhong.github.io/ESEManager/> together with `version.txt` and `manifest.json`
(sizes + SHA-256). On startup the app compares `version.txt` with its local copy and offers
to download the new databases. Run the workflow manually with **force** to rebuild anyway.

One-time setup: **Settings → Pages → Source: GitHub Actions**.

Build the same site locally:

```
python scripts/build_pages_db.py --out site
```

## Project layout

```
src/
  ese_qt.py            main window and entry point
  appconfig.py         data paths, URLs, safe path joining
  i18n.py              UI strings (zh_TW / en / ja)
  models.py            song list and download table models
  workers.py           background threads (search, download, updates, DB update)
  boxdef.py            box.def generators
  dialogs.py           box.def editor, YataiDON generator, Dan tools
  dan_tools.py         Dan generator / convertor
  tja_parser.py        TJA parsing and the shared text decoder
  download_songs.py    song search (also a CLI downloader)
  ese_scraper_git_v2.py, build_local_db.py   database builders
scripts/     GitHub Pages database builder, release database fetcher
tests/       pytest suite
.github/     workflows: database publishing and release builds
packaging/   PyInstaller spec
```

## Credits

- The **Dan Generator** and **Dan Convertor** features are ported from
  [bluetaiko/SongConvertor](https://github.com/bluetaiko/SongConvertor) (MIT License).
  Many thanks to the author.

## Data source

Charts come from the ESE project: <https://ese.tjadataba.se/ESE/ESE>
(The former host `git.vanillaaaa.org` is no longer available.)
