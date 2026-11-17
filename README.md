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
- Auto-downloads a portable Git if Git isn't installed
- UI language auto-detect (English / 繁體中文 / 日本語)

## Quick start

Download the release for your platform and run it. The first time, click **🔄 Update database** to
fetch the song list and Japanese titles, then search and download.

## Run from source

Requires Python 3.9+ and Git installed.

```
pip install -r requirements.txt
python src/ese_qt.py
```

## Build the executable

```
pip install pyinstaller
pyinstaller --noconfirm --clean packaging/ESEManager.spec
```

Output: `dist/ESEManager` (Linux/macOS) or `dist/ESEManager.exe` (Windows).

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
src/         GUI app, downloader, scrapers
scripts/     GitHub Pages database builder
.github/     CI workflow that publishes the databases
packaging/   PyInstaller spec
```

## Credits

- The **Dan Generator** and **Dan Convertor** features are ported from
  [bluetaiko/SongConvertor](https://github.com/bluetaiko/SongConvertor) (MIT License).
  Many thanks to the author.

## Data source

Charts come from the ESE project: <https://ese.tjadataba.se/ESE/ESE>
(The former host `git.vanillaaaa.org` is no longer available.)
