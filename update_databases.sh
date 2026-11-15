#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
python3 src/ese_scraper_git_v2.py --keep
python3 src/build_local_db.py --remote
