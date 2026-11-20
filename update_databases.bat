@echo off
chcp 65001 >nul
rem Download the latest prebuilt song databases (rebuilt from ESE every 6 hours
rem by GitHub Actions). Same as the GUI's "Update DB" button.
cd /d "%~dp0"
python src\cli.py update-db %*
pause
