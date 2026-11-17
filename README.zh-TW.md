# ESEManager

從 **ESE（Every Song Ever）** 專案瀏覽與下載太鼓達人 TJA 譜面的高速桌面程式。

[English](README.md) | **繁體中文**

## 功能

- 高速歌曲清單 — 上千首一次顯示、無需分頁
- 依名稱（支援日文）與分類搜尋
- **依 BPM 區間與難度等級篩選**（簡單／普通／困難／魔王／裏）— 以欄位顯示，從各譜面解析
- 批次下載，可**暫停／繼續／停止**
- 即時監控：整體進度 + 速度／ETA、每檔狀態、Log、失敗一鍵重試
- 一鍵**更新資料庫**：
  - 歌曲清單用 *blobless* git clone 抓取（只取檔案清單、不下載音檔）
  - 日文標題直接解析每個譜面的 `TITLEJA` 欄位（增量更新，已存在的會略過）
- **段位工具**（🥋）：
  - **段位生成** — 輸入太鼓 Wiki 段位道場頁面網址，依段位名稱與合格條件，生成 TaikøNauts 等可用的段位檔（`dan.def` + 各段位 `Dan.json`）
  - **段位變換** — 把 OpenTaiko 等的 tja 段位（以 `#NEXTSONG` 分隔多曲）變換成 TaikøNauts 等可用的段位檔
- **檢查缺漏**（🔍）與**檢查更新**（🆕）：找出尚未下載的歌，或上游已更新的譜面（以 git blob 雜湊比對）
- **box.def 工具**：OpenTaiko box.def 編輯器（📦）與 YataiDON box.def 產生器（🎮）
- 下載會驗證（TLS、檔案大小、譜面的 git blob 雜湊），並先寫到 `.part` 檔，中斷也不會留下壞檔
- 未安裝 Git 時可自動下載可攜版 Git（只有手動按「更新資料庫」才需要）
- 介面語言自動偵測（English／繁體中文／日本語）

## 快速開始

從 [Releases 頁面](https://github.com/GanYiZhong/ESEManager/releases)下載對應平台的壓縮檔，
解壓後執行 `ESEManager`（Windows 為 `ESEManager.exe`）。第一次啟動時程式會詢問是否下載預先建好的
歌曲資料庫（約 5 MB），之後即可搜尋與下載。

設定檔、資料庫和預設的 `Downloads` 資料夾都放在執行檔旁邊。

Linux 若出現無法載入 Qt `xcb` 外掛的錯誤，請安裝 `libxcb-cursor0`（Debian/Ubuntu）或
`xcb-util-cursor`（Fedora/Arch）。

## 從原始碼執行

需要 Python 3.9+（Windows、Linux、macOS 皆可）。只有自行重建資料庫時才需要 Git。

```
pip install -r requirements.txt
python src/ese_qt.py
```

從原始碼執行時，資料檔放在專案根目錄。

## 測試

```
pip install -r requirements.txt pytest
python -m pytest tests
```

## 打包成執行檔

```
pip install -r requirements-build.txt
pyinstaller --noconfirm --clean packaging/ESEManager.spec
python scripts/fetch_release_dbs.py dist/ESEManager   # 選用：一併放入目前的資料庫
```

輸出：`dist/ESEManager/` 資料夾（onedir），發佈時整個資料夾一起打包。

## 發佈流程

1. 推送到 `main`。**Release builds** workflow（`.github/workflows/release.yml`）會在每次推送和
   PR 時打包並測試 Windows 與 Linux 版。
2. 建立並發佈 GitHub release（例如 `gh release create v1.2.0 --generate-notes`）。
3. 同一個 workflow 會從該 tag 打包兩個平台、放入經 `manifest.json` 驗證的資料庫，並上傳
   `ESEManager_<tag>_windows-x86_64.7z`、`ESEManager_<tag>_linux-x86_64.tar.gz` 及各自的 `.sha256`。

要重新打包既有 release 的檔案，可手動執行該 workflow 並填入 tag。

## 預先建好的資料庫（GitHub Pages）

`.github/workflows/pages-db.yml` 每 6 小時從 ESE 重建 `ese_songs.db` 與 `ese_local.db`（ESE 沒有新
commit 時直接略過），發佈到 <https://ganyizhong.github.io/ESEManager/>，並附上 `version.txt` 與含
SHA-256 的 `manifest.json`。程式啟動時會比對版本並詢問是否更新。

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
src/         GUI 程式（ese_qt.py 主視窗；appconfig、i18n、models、workers、boxdef、dialogs 等模組）、
             下載器、爬蟲、TJA 解析
scripts/     GitHub Pages 資料庫建置、發佈用資料庫下載
tests/       pytest 測試
.github/     workflows：發佈資料庫、打包 release
packaging/   PyInstaller spec
```

## 致謝

- **段位生成**與**段位變換**功能移植自
  [bluetaiko/SongConvertor](https://github.com/bluetaiko/SongConvertor)（MIT License），特此感謝原作者。

## 資料來源

譜面來自 ESE 專案：<https://ese.tjadataba.se/ESE/ESE>
（舊主機 `git.vanillaaaa.org` 已停用、無法訪問。）
