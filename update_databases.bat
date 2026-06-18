@echo off
chcp 65001 >nul
echo ============================================
echo   ESEManager - Update databases
echo ============================================
echo.
echo [1/2] Updating song list (blobless git clone of ESE)...
python src\ese_scraper_git_v2.py --keep
echo.
echo [2/2] Updating Japanese titles (from ESE .tja TITLEJA, incremental)...
python src\build_local_db.py --remote
echo.
echo Done. You can also do this from the GUI button.
pause
