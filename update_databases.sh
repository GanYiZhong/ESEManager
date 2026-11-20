#!/usr/bin/env bash
# Download the latest prebuilt song databases (rebuilt from ESE every 6 hours
# by GitHub Actions). Same as the GUI's "Update DB" button.
set -e
cd "$(dirname "$0")"
python3 src/cli.py update-db "$@"
