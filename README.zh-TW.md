# ESEManager

從 **ESE（Every Song Ever）** 專案瀏覽與下載太鼓達人 TJA 譜面的高速桌面程式。

[English](README.md) | **繁體中文**

## 功能

- 高速歌曲清單：上千首一次顯示、可依欄位排序、無需分頁
- 即打即搜（支援日文標題），可依分類篩選
- **依 BPM 區間與難度等級篩選**（簡單／普通／困難／魔王／裏）
- 批次下載，可**暫停／繼續／停止**，即時進度、失敗一鍵重試
- **檢查缺漏**與**檢查更新**：找出尚未下載的歌，或上游已更新的譜面（以 git blob 雜湊比對）
- 歌曲資料庫由 GitHub 每 6 小時從 ESE 自動重建；按「更新資料庫」即下載最新版（約 5 MB），
  啟動時有新版也會詢問
- 下載會驗證（TLS、檔案大小、譜面的 git blob 雜湊），並先寫到 `.part` 檔，中斷也不會留下壞檔
- 淺色／深色主題，介面語言自動偵測（English／繁體中文／日本語）
- 一鍵下載 [ESE-Version-Sorting](https://ese.tjadataba.se/Yonokid/ESE-Version-Sorting)（YataiDON 版本分類資料夾）
  到下載目錄：**檔案 → 下載版本分類**
- 命令列模式（`ESEManager-cli`），方便寫腳本或在伺服器上使用
- Rolling release：有新版本時狀態列會提示

## 快速開始

從 [Releases 頁面](https://github.com/GanYiZhong/ESEManager/releases/latest)下載對應平台的最新版，
解壓後執行 `ESEManager`（Windows 為 `ESEManager.exe`）。第一次啟動時程式會詢問是否下載歌曲資料庫，
之後即可搜尋與下載。

設定檔、資料庫和預設的 `Downloads` 資料夾都放在執行檔旁邊，新版直接解壓覆蓋舊資料夾即可。

Linux 若出現無法載入 Qt `xcb` 外掛的錯誤，請安裝 `libxcb-cursor0`（Debian/Ubuntu）或
`xcb-util-cursor`（Fedora/Arch）。

## 命令列模式

Release 版在主程式旁附有 `ESEManager-cli`（Windows 為 `ESEManager-cli.exe`）；從原始碼執行則用
`python src/cli.py`。與 GUI 共用同一份資料庫、設定與下載目錄。

```
ESEManager-cli status                      # 版本、資料夾、歌曲數
ESEManager-cli update-db                   # 下載最新歌曲資料庫
ESEManager-cli search 千本桜               # 也支援日文標題
ESEManager-cli download Senbonzakura -y    # 下載符合的歌
ESEManager-cli download --all -y           # 全部下載
ESEManager-cli missing --download -y       # 下載缺少的歌
ESEManager-cli updates --download -y       # 下載上游更新過的譜面
ESEManager-cli version-sorting             # 安裝／更新 ESE-Version-Sorting
```

選項：`--dir 資料夾`、`--workers 數量`、`--lang zh_TW|en|ja`。結束碼 0＝成功、1＝有失敗、2＝沒事可做或用法錯誤。

## 從原始碼執行

需要 Python 3.9+（Windows、Linux、macOS 皆可）。

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

## 發佈方式（rolling release）

每次推送到 `main` 且有改到程式（`src/`、`packaging/`、`assets/`、requirements），
`.github/workflows/release.yml` 就會自動：

1. 跑測試、打包 Windows 與 Linux 版並做冒煙測試；
2. 以日期為版本號發佈 release：`v2026.11.18`，同一天第二版為 `v2026.11.18.2`（台北時間），
   release notes 為這次的 commit 清單，附上
   `ESEManager_<版本>_windows-x86_64.7z`、`ESEManager_<版本>_linux-x86_64.tar.gz` 及各自的 `.sha256`。

只改測試、文件或 workflow 的推送只會打包不發佈。commit 訊息加上 `[skip release]` 可刻意不發佈。
PR 只會打包與測試。要重新打包既有 release 的檔案，可手動執行該 workflow 並填入 tag。

## 預先建好的資料庫（GitHub Pages）

`.github/workflows/pages-db.yml` 每 6 小時從 ESE 重建 `ese_songs.db` 與 `ese_local.db`（ESE 沒有新
commit 時直接略過），發佈到 <https://ganyizhong.github.io/ESEManager/>，並附上 `version.txt` 與含
SHA-256 的 `manifest.json`。手動執行時勾選 **force** 可強制重建。

這個流程盡量不佔用 ESE 伺服器：

- 每 6 小時只做一次 `git ls-remote`，ESE 沒更新就到此為止；
- 用淺層、blobless clone（只有檔案清單、不含音檔），並在每次執行之間快取，更新時只抓新 commit 的目錄樹；
- 譜面（`.tja`）透過 git 批次取得，而且只抓內容有變的（以 git blob 雜湊判斷），不會一個檔案一個 HTTP 請求；
- 音檔（Git LFS）永遠不下載。

在本機建立同樣的資料庫（需要 Git）：

```
python scripts/build_pages_db.py --out site
```

## 專案結構

```
src/         GUI 程式（ese_qt.py 主視窗；appconfig、i18n、models、workers、theme、notify）、
             下載器、TJA 解析、資料庫建置（CI 使用）
scripts/     GitHub Pages 資料庫建置、發佈用資料庫下載、圖示產生
tests/       pytest 測試
.github/     workflows：發佈資料庫、rolling release
packaging/   PyInstaller spec
```

## 資料來源

譜面來自 ESE 專案：<https://ese.tjadataba.se/ESE/ESE>
（舊主機 `git.vanillaaaa.org` 已停用、無法訪問。）
