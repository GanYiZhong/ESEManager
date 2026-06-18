@echo off
chcp 65001 > nul
echo ========================================
echo 資料庫更新工具（管理員專用）
echo ========================================
echo.

echo [1/5] 切換到原始碼目錄...
cd archive\source_code
echo.

echo [2/5] 從 Git 更新 ese_songs.db...
echo 首次執行需完整 clone（數分鐘）；之後保留 clone 目錄改用增量 pull，會快很多
python ese_scraper_git_v2.py --keep
echo.

echo [3/5] 更新 ese_local.db...
echo 請確認本地 TJA 檔案目錄是否正確
set /p TJA_DIR="請輸入 TJA 檔案目錄路徑（直接按 Enter 使用預設）: "

if "%TJA_DIR%"=="" (
    echo 使用預設路徑: Z:\[TJA ESE]\Songs\Songs
    python build_local_db.py
) else (
    python build_local_db.py --dir "%TJA_DIR%"
)
echo.

echo [4/5] 複製資料庫到主目錄...
cd ..\..
copy /Y archive\source_code\ese_songs.db .
copy /Y archive\source_code\ese_local.db .
echo.

echo [5/5] 更新版本號...
echo 請手動編輯 version.txt 檔案
notepad version.txt
echo.

echo ========================================
echo 更新完成！
echo ========================================
echo.
echo 接下來請上傳以下檔案到伺服器:
echo   1. ese_songs.db
echo   2. ese_local.db
echo   3. version.txt
echo.
echo 上傳位置: https://taikozhong.me/tjamanager/
echo ========================================
pause
