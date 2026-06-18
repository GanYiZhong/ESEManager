# ESEManager

從 **ESE（Every Song Ever）** 專案瀏覽與下載太鼓達人 TJA 譜面的高速桌面程式。

[English](README.md) | **繁體中文**

## 功能

- 高速歌曲清單 — 上千首一次顯示、無需分頁
- 依名稱（支援日文）與分類搜尋
- 批次下載，可**暫停／繼續／停止**
- 即時監控：整體進度 + 速度／ETA、每檔狀態、Log、失敗一鍵重試
- 一鍵**更新資料庫**：
  - 歌曲清單用 *blobless* git clone 抓取（只取檔案清單、不下載音檔）
  - 日文標題直接解析每個譜面的 `TITLEJA` 欄位（增量更新，已存在的會略過）
- 未安裝 Git 時可自動下載可攜版 Git
- 介面語言自動偵測（English／繁體中文／日本語）

## 快速開始

下載 `ESEManager.exe` 執行。第一次請按 **🔄 更新資料庫** 取得歌曲清單與日文標題，
接著即可搜尋與下載。

## 從原始碼執行

需要 Windows 上的 Python 3.9+。

```
pip install -r requirements.txt
python src/ese_qt.py
```

## 打包成執行檔

```
pip install pyinstaller
pyinstaller --noconfirm --clean packaging/ESEManager.spec
```

輸出：`dist/ESEManager.exe`。

## 用命令列更新資料庫（選用）

程式內的 **更新資料庫** 按鈕已涵蓋此流程。命令列等效做法：

```
update_databases.bat
```

或手動：

```
python src/ese_scraper_git_v2.py --keep     # 歌曲清單 -> ese_songs.db
python src/build_local_db.py --remote        # 日文標題 -> ese_local.db
```

## 專案結構

```
src/         GUI 程式、下載器、爬蟲
packaging/   PyInstaller spec
```

## 資料來源

譜面來自 ESE 專案：<https://ese.tjadataba.se/ESE/ESE>
（舊主機 `git.vanillaaaa.org` 已停用、無法訪問。）
