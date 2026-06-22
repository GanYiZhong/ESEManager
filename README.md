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
- Auto-downloads a portable Git if Git isn't installed
- UI language auto-detect (English / 繁體中文 / 日本語)

## Quick start

Download `ESEManager.exe` and run it. The first time, click **🔄 Update database** to
fetch the song list and Japanese titles, then search and download.

## Run from source

Requires Python 3.9+ on Windows.

```
pip install -r requirements.txt
python src/ese_qt.py
```

## Build the executable

```
pip install pyinstaller
pyinstaller --noconfirm --clean packaging/ESEManager.spec
```

Output: `dist/ESEManager.exe`.

## Update databases from the command line (optional)

The in-app **Update database** button already does this. The CLI equivalent:

```
update_databases.bat
```

or manually:

```
python src/ese_scraper_git_v2.py --keep     # song list  -> ese_songs.db
python src/build_local_db.py --remote        # JP titles  -> ese_local.db
```

## Project layout

```
src/         GUI app, downloader, scrapers
packaging/   PyInstaller spec
```

## Data source

Charts come from the ESE project: <https://ese.tjadataba.se/ESE/ESE>
(The former host `git.vanillaaaa.org` is no longer available.)
