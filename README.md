# ESE Song Database Manager

ESE (Every Song Ever) 歌曲資料庫管理工具 - 用於抓取和管理太鼓達人歌曲資料

> **🎉 V2 版本已發布！**
>
> 新版本支援：
> - ✅ 智能歌曲識別（將 .tja、.ogg 等檔案關聯為同一首歌）
> - ✅ 自動跳過已存在的檔案（避免重複抓取）
> - ✅ 更精確的歌曲統計
>
> **推薦使用 V2 版本：** [`ese_scraper_git_v2.py`](V2_GUIDE.md)
>
> 詳細說明請參考 [V2 使用指南](V2_GUIDE.md)

## 功能特色

- 自動抓取 ESE Repository 的目錄結構和歌曲資訊
- 儲存到本地 SQLite 資料庫
- 支援分類、檔案名稱、檔案類型等多種查詢方式
- 可匯出歌曲列表到 CSV 檔案
- 提供詳細的統計資訊
- **提供三種不同速度的抓取方式**
- **支援歌曲下載功能（保持目錄結構、自動跳過已下載）**
- **支援本地 TJA 檔案解析（日文標題查詢）**

## 三種抓取方式比較

| 方式 | 檔案 | 速度 | 需求 | 適用場景 |
|------|------|------|------|----------|
| **Git Clone** | `ese_scraper_git.py` | ⚡ 最快 | 需要安裝 Git | 推薦使用，適合首次抓取或完整更新 |
| **多線程 API** | `ese_scraper_fast.py` | 🚀 快 | 只需 Python | 不想安裝 Git 但想要快速抓取 |
| **標準 API** | `ese_scraper.py` | 🐌 慢 | 只需 Python | 網路不穩定或需要詳細日誌 |

### 推薦使用順序
1. 優先使用 `ese_scraper_git.py`（需要安裝 Git）
2. 如果沒有 Git，使用 `ese_scraper_fast.py`
3. 如果遇到問題，使用 `ese_scraper.py`

## 檔案說明

### ⭐ V2 版本（推薦）
- `ese_scraper_git_v2.py` - **最快** - Git Clone 版本，支援智能去重和歌曲關聯（需要 Git）
- `ese_scraper_fast_v2.py` - **快** - 多線程版本，支援智能去重和歌曲關聯（不需要 Git）
- `query_songs_v2.py` - V2 查詢工具，支援歌曲詳細資訊
- `migrate_db.py` - 資料庫遷移工具（V1 → V2）
- `V2_GUIDE.md` - V2 完整使用指南

### 🆕 本地 TJA 檔案支援（日文標題）
- `tja_parser.py` - TJA 檔案解析器，提取日文標題
- `build_local_db.py` - 建立本地 TJA 資料庫
- `link_databases.py` - 關聯線上和本地資料庫，雙向查詢
- `query_combined.py` - 整合查詢工具（自動顯示日文標題）
- `LOCAL_DB_GUIDE.md` - 本地資料庫完整使用指南

### 🖥️ GUI 圖形介面（推薦使用）

#### ✨ Modern Edition - Liquid Glass 風格（最新）
- `ese_gui_modern.py` - **現代化玻璃態介面**
  - 🎨 Liquid Glass 設計風格
  - 🌓 深色模式支援
  - 📱 卡片式歌曲顯示
  - 🌈 分類彩色標識
  - 🔍 強大的搜尋功能（支援英文、日文）
  - 🎌 **優先顯示日文歌名**（自動偵測並優先顯示日文標題）
  - ✨ **現代化對話框**（美觀的通知和確認對話框）
  - ✅ 一鍵選擇/取消選擇
  - 📊 動態進度顯示
  - ⚙️ 可自訂下載目錄和並行下載數
  - 詳細說明請參考 [Modern GUI 使用指南](MODERN_GUI_GUIDE.md)
- `modern_dialog.py` - **現代化對話框組件庫**
  - 資訊、成功、警告、錯誤對話框
  - 詢問對話框（是/否）
  - 下載完成特殊對話框
  - 完整的 Liquid Glass 設計風格

#### 標準版 GUI
- `ese_gui.py` - **標準圖形化介面**
  - 🔍 強大的搜尋功能（歌曲名稱、分類篩選）
  - ✅ 支援 Shift/Ctrl 多選批次下載
  - 📁 分類背景顏色標識
  - 📊 即時下載進度顯示
  - ⚙️ 可自訂下載目錄和並行下載數
  - 📋 雙擊查看歌曲詳細資訊
  - 詳細說明請參考 [GUI 使用指南](GUI_GUIDE.md)

### 🎮 歌曲管理器（新功能）
- `song_manager.py` - **本地歌曲資料夾管理工具**
  - 📁 掃描 Songs 資料夾中的所有歌曲
  - 🗑️ 刪除不需要的歌曲資料夾
  - 📦 批次移動歌曲到其他位置
  - ✅ 支援多選操作
  - 🎨 Modern Liquid Glass 風格介面
  - 🔍 自動檢測 TJA 和 OGG 檔案

### 📥 歌曲下載工具（命令列）
- `download_songs.py` - 命令列下載工具
  - 搜尋並下載指定歌曲（TJA、OGG 等檔案）
  - 保持 ESE 原始目錄結構
  - 自動跳過已存在的檔案
  - 支援並行下載（可設定線程數）
  - 可自訂下載目錄和檔案類型

### 爬蟲程式（V1 - 舊版）
- `ese_scraper_git.py` - **最快** - Git Clone 版本，直接 clone repository
- `ese_scraper_fast.py` - **快** - 多線程版本，使用並行 API 請求
- `ese_scraper.py` - **慢** - 標準版本，單線程 API 請求

### 其他工具
- `query_songs.py` - 查詢工具（V1）
- `requirements.txt` - Python 套件依賴
- `QUICKSTART.md` - 快速開始指南
- `ese_songs.db` - SQLite 資料庫（執行爬蟲後自動建立）

## 安裝步驟

### 1. 安裝 Python

確保你的系統已安裝 Python 3.7 或更新版本

### 2. 安裝依賴套件

```bash
pip install -r requirements.txt
```

## 使用方法

### 🖥️ 使用 GUI 介面（推薦）

最簡單的使用方式是透過圖形介面：

#### ✨ Modern Edition（推薦）

**Windows 使用者**
```bash
# 雙擊啟動（推薦）
start_gui_modern.bat

# 或使用命令列
python ese_gui_modern.py
```

**其他系統**
```bash
# 安裝依賴
pip install customtkinter Pillow

# 啟動程式
python ese_gui_modern.py
```

**Modern Edition 特色：**
- 🎨 Liquid Glass 玻璃態設計
- 🌓 深色模式
- 📱 美觀的卡片式介面
- 🌈 彩色分類標識
- ✨ 現代化控制元件

詳細使用說明請參考 [Modern GUI 使用指南](MODERN_GUI_GUIDE.md)

#### 標準版 GUI

**Windows 使用者**
```bash
# 雙擊啟動
start_gui.bat

# 或使用命令列
python ese_gui.py
```

**其他系統**
```bash
python ese_gui.py
```

**標準版功能：**
- 🔍 搜尋歌曲（英文、日文）
- ✅ Shift/Ctrl 多選
- 📁 分類顏色標識
- 📊 進度顯示

詳細使用說明請參考 [GUI 使用指南](GUI_GUIDE.md)

---

### 建立資料庫

選擇以下三種方式之一來抓取資料：

#### 方式 1: Git Clone 版本（⚡ 最快，推薦）

```bash
python ese_scraper_git.py
```

**優點:**
- 速度最快（通常 1-3 分鐘完成）
- 直接 clone repository，一次性下載所有資料
- 自動清理臨時檔案

**需求:** 需要安裝 Git（[下載 Git](https://git-scm.com/downloads)）

**選項:**
```bash
# 保留 clone 的目錄（不刪除）
python ese_scraper_git.py --keep

# 自訂 clone 目錄
python ese_scraper_git.py --clone-dir my_ese_folder

# 自訂資料庫位置
python ese_scraper_git.py --db custom.db
```

#### 方式 2: 多線程 API 版本（🚀 快）

```bash
python ese_scraper_fast.py
```

**優點:**
- 不需要 Git，只需要 Python
- 使用多線程並行抓取，比標準版本快 5-10 倍
- 可自訂線程數

**選項:**
```bash
# 使用 20 個線程（預設 10）
python ese_scraper_fast.py --workers 20

# 自訂資料庫位置
python ese_scraper_fast.py --db custom.db
```

#### 方式 3: 標準 API 版本（🐌 慢）

```bash
python ese_scraper.py
```

**優點:**
- 最簡單，不需要額外設定
- 提供詳細的掃描日誌
- 適合網路不穩定的環境

**注意:** 這個方式可能需要較長時間（10-30 分鐘）

---

所有方式都會：
1. 自動建立 SQLite 資料庫
2. 掃描所有 11 個分類的歌曲
3. 儲存檔案資訊、大小、下載連結等
4. 顯示詳細的統計資訊

### 查詢歌曲

建立資料庫後，可以使用查詢工具來搜尋歌曲：

#### 列出所有分類

```bash
python query_songs.py --list
```

#### 顯示統計資訊

```bash
python query_songs.py --stats
```

#### 搜尋歌曲（依檔案名稱）

```bash
python query_songs.py --search "千本桜"
```

#### 依分類搜尋

```bash
python query_songs.py --category "Anime"
```

#### 依檔案類型搜尋

```bash
python query_songs.py --type tja
```

#### 組合查詢

```bash
python query_songs.py --category "Anime" --type tja --limit 10
```

#### 匯出到 CSV

```bash
python query_songs.py --export songs.csv
```

### 下載歌曲

建立資料庫後，可以使用下載工具來下載特定歌曲的檔案：

#### 搜尋並下載歌曲

```bash
# 下載包含 "Senbonzakura" 的歌曲（所有檔案）
python download_songs.py --search "Senbonzakura"

# 只下載 .tja 和 .ogg 檔案
python download_songs.py --search "Senbonzakura" --types .tja .ogg

# 下載 Anime 分類的歌曲
python download_songs.py --search "千本桜" --category Anime
```

#### 下載所有歌曲（批次下載）

```bash
# 下載所有歌曲的 .tja 檔案
python download_songs.py --all --types .tja --yes

# 下載所有歌曲的 .ogg 檔案
python download_songs.py --all --types .ogg --yes

# 下載所有歌曲（所有檔案類型）
python download_songs.py --all --yes

# 下載 Anime 分類的所有歌曲
python download_songs.py --all --category "02 Anime" --yes

# 下載 Pop 分類的所有 .tja 檔案
python download_songs.py --all --category "01 Pop" --types .tja --yes
```

#### 進階選項

```bash
# 自訂下載目錄
python download_songs.py --all --types .tja --dir "D:\TJA Downloads"

# 限制下載數量（測試用）
python download_songs.py --all --limit 10 --yes

# 並行下載（加快速度，建議不超過 3）
python download_songs.py --all --types .tja --workers 3 --yes

# 自動確認下載，不詢問
python download_songs.py --search "sakura" --yes
```

**功能特色:**
- ✅ 自動跳過已下載的檔案
- ✅ 保持 ESE 原始目錄結構
- ✅ 支援檔案類型篩選（.tja、.ogg 等）
- ✅ 支援分類篩選
- ✅ 支援批次下載所有歌曲
- ✅ 支援並行下載加速
- ✅ 顯示下載進度和統計

### 更新資料庫

如果 ESE Repository 有更新，可以重新執行任何一個爬蟲程式來更新資料庫：

```bash
# 推薦使用 Git 版本更新（最快）
python ese_scraper_git.py

# 或使用多線程版本
python ese_scraper_fast.py

# 或使用標準版本
python ese_scraper.py
```

程式會自動：
- 更新已存在的歌曲資訊
- 新增新發現的歌曲
- 保留原有的資料庫記錄

## 資料庫結構

### categories 表（分類）

| 欄位 | 類型 | 說明 |
|------|------|------|
| id | INTEGER | 主鍵 |
| name | TEXT | 分類名稱 |
| path | TEXT | 分類路徑 |
| created_at | TIMESTAMP | 建立時間 |

### songs 表（歌曲）

| 欄位 | 類型 | 說明 |
|------|------|------|
| id | INTEGER | 主鍵 |
| category_id | INTEGER | 分類 ID |
| filename | TEXT | 檔案名稱 |
| path | TEXT | 檔案路徑 |
| file_type | TEXT | 檔案類型 |
| size | INTEGER | 檔案大小（bytes）|
| download_url | TEXT | 下載連結 |
| created_at | TIMESTAMP | 建立時間 |
| updated_at | TIMESTAMP | 更新時間 |

## 進階使用

### 在 Python 程式中使用

```python
from ese_scraper import ESEScraper

# 建立爬蟲實例
scraper = ESEScraper(db_path="custom_db.db")

# 初始化資料庫
scraper.init_database()

# 執行爬蟲
scraper.scrape()

# 查詢歌曲
songs = scraper.query_songs(category="Anime", filename="千本桜")

# 關閉連接
scraper.close()
```

### 直接操作資料庫

```python
import sqlite3

conn = sqlite3.connect("ese_songs.db")
cursor = conn.cursor()

# 自訂查詢
cursor.execute("""
    SELECT s.filename, c.name
    FROM songs s
    JOIN categories c ON s.category_id = c.id
    WHERE s.size > 1000000
""")

for row in cursor.fetchall():
    print(row)

conn.close()
```

## 常見問題

### Q: 哪個版本最快？

A: **Git Clone 版本（`ese_scraper_git.py`）最快**，通常 1-3 分鐘完成。多線程版本次之，標準版本最慢（可能需要 10-30 分鐘）。

### Q: Git Clone 版本出現 "找不到 git 命令" 錯誤

A: 需要先安裝 Git：
1. 前往 https://git-scm.com/downloads 下載安裝
2. 安裝後重啟命令提示字元
3. 輸入 `git --version` 確認安裝成功

如果不想安裝 Git，可以使用多線程版本 `ese_scraper_fast.py`。

### Q: 執行爬蟲時出現 "無法獲取路徑" 錯誤

A: 請檢查：
1. 網路連接是否正常
2. ESE Repository 網站 (https://git.vanillaaaa.org) 是否可以訪問
3. 是否被防火牆阻擋
4. 嘗試使用其他版本的爬蟲（如 Git Clone 版本通常更穩定）

### Q: 多線程版本可以使用多少線程？

A: 預設是 10 個線程，可以用 `--workers` 參數調整：
```bash
python ese_scraper_fast.py --workers 20
```
建議不要超過 20，以免對伺服器造成負擔。

### Q: 如何只更新特定分類的歌曲？

A: 目前程式會掃描所有分類。如需只更新特定分類，可以：
1. 手動修改爬蟲程式碼
2. 或先完整抓取，再使用 `query_songs.py` 篩選需要的分類

### Q: 資料庫檔案太大怎麼辦？

A: SQLite 資料庫非常高效，即使儲存數千首歌曲也不會太大。如果需要，可以使用 SQLite 的 VACUUM 命令來壓縮資料庫：

```python
import sqlite3
conn = sqlite3.connect("ese_songs.db")
conn.execute("VACUUM")
conn.close()
```

## 注意事項

- 本工具僅用於個人學習和研究目的
- 請遵守 ESE Repository 的使用條款
- 不要過於頻繁地執行爬蟲，以免對伺服器造成負擔
- 建議每次更新資料庫的間隔至少為 1 天

## 授權

本專案僅供學習使用，請尊重原始資料來源的版權

## 相關連結

- ESE Repository: https://git.vanillaaaa.org/ESE/ESE
- Taiko no Tatsujin: https://taiko.namco-ch.net/

## 更新日誌

### v3.1.0 (2025-10-21) 🆕

**Modern GUI 重大更新**

- ✨ **優先顯示日文歌名**
  - 當歌曲有日文標題時，優先顯示日文名稱（大字體、粗體）
  - 英文名稱作為副標題顯示（小字體、灰色）
  - 自動偵測 ese_local.db 資料庫中的日文標題
- ✨ **現代化對話框系統**
  - 新增 `modern_dialog.py` - 完整的 Liquid Glass 風格對話框
  - 資訊、成功、警告、錯誤對話框（彩色圖標和主題）
  - 詢問對話框（是/否按鈕）
  - 特殊的下載完成對話框（顯示歌曲數和下載位置）
  - 所有對話框均採用 Liquid Glass 設計風格
  - 完全替換舊式 tkinter messagebox
- ✨ **歌曲管理器**
  - 新增 `song_manager.py` - 本地歌曲資料夾管理工具
  - 掃描 Songs 資料夾，卡片式顯示所有歌曲
  - 批次刪除歌曲資料夾（含確認對話框）
  - 批次移動歌曲到其他位置
  - 多選操作支援
  - Modern Liquid Glass 介面風格
  - 自動檢測 TJA 和 OGG 檔案
  - 開啟資料夾功能（直接在檔案總管中開啟）
- ✨ 新增 `start_song_manager.bat` - 歌曲管理器啟動腳本

### v3.0.0 (2025-10-20)

**全新 Modern Edition - Liquid Glass 風格介面**

- ✨ 新增 `ese_gui_modern.py` - 現代化玻璃態介面
  - 🎨 **Liquid Glass 設計風格**
    - 深色模式支援
    - 玻璃態美學設計
    - 柔和的視覺效果
  - 📱 **卡片式歌曲顯示**
    - 清晰的視覺層次
    - 分類彩色標籤
    - 即時選擇狀態回饋
  - 🎯 **現代化控制元件**
    - 圓角按鈕
    - 滑桿控制
    - 動態進度條
  - 🌈 **分類顏色系統**
    - 每個分類專屬顏色
    - 視覺化標識
    - 選擇狀態高亮
  - 🔍 **智能搜尋**
    - 支援英文/日文搜尋
    - Enter 快速搜尋
    - 分類自動篩選
  - 📊 **動態進度顯示**
    - 僅在下載時顯示
    - 實時狀態更新
    - 彩色狀態標識
- ✨ 新增 `start_gui_modern.bat` - Modern GUI 啟動腳本
- 📝 新增 `MODERN_GUI_GUIDE.md` - Modern GUI 完整使用指南
- 📦 更新依賴：customtkinter, Pillow

### v2.3.0 (2025-10-20) 🆕

**新功能 - GUI 圖形介面**

- ✨ 新增 `ese_gui.py` - 圖形化介面管理工具
  - 🔍 搜尋功能（歌曲名稱、分類篩選）
  - ✅ **Shift/Ctrl 多選功能**
    - Shift + 點擊：連續多選
    - Ctrl + 點擊：不連續多選
    - 支援全選/取消選擇
  - 📥 批次下載功能
    - 一次下載多首選中的歌曲
    - 即時進度顯示
  - 📁 檔案類型篩選（TJA、OGG、其他）
  - 📋 歌曲詳細資訊查看（雙擊歌曲）
  - ⚙️ 下載設定
    - 自訂下載目錄
    - 設定並行下載數
  - 📊 下載進度條和狀態顯示
- ✨ 新增 `start_gui.bat` - Windows 快速啟動腳本
- 📝 新增 `GUI_GUIDE.md` - 完整的 GUI 使用指南

### v2.2.0 (2025-10-19) 🆕

**新功能 - 歌曲下載工具**

- ✨ 新增 `download_songs.py` - 歌曲下載工具
  - 搜尋並下載指定歌曲的檔案（TJA、OGG 等）
  - 📥 **批次下載功能**（--all 參數）
    - 下載所有歌曲的 .tja 檔案
    - 下載所有歌曲的 .ogg 檔案
    - 下載所有歌曲（所有檔案類型）
    - 可搭配分類篩選使用
  - 自動保持 ESE 原始目錄結構
  - 智能跳過已下載的檔案
  - 支援檔案類型篩選（--types 參數）
  - 支援分類篩選（--category 參數）
  - 支援並行下載加速（--workers 參數）
  - 支援自訂下載目錄（--dir 參數）
  - 支援自動確認模式（--yes 參數）
  - 詳細的下載統計和進度顯示

### v2.1.0 (2025-10-19) 🆕

**新功能 - 本地 TJA 檔案支援**

- ✨ 新增 `tja_parser.py` - TJA 檔案解析器
  - 自動提取 TITLEJA（日文標題）、SUBTITLEJA（日文副標題）
  - 支援多種編碼（UTF-8, Shift-JIS, CP932 等）
- ✨ 新增 `build_local_db.py` - 本地 TJA 資料庫建立工具
  - 掃描本地已下載的 TJA 檔案
  - 建立獨立的日文標題資料庫
- ✨ 新增 `link_databases.py` - 雙向查詢工具
  - 英文 → 日文標題查詢
  - 日文 → 英文標題查詢
  - 智能名稱匹配
- ✨ 新增 `query_combined.py` - 整合查詢工具
  - 自動關聯線上和本地資料庫
  - 查詢時同時顯示英文和日文標題
- 📝 新增 `LOCAL_DB_GUIDE.md` - 本地資料庫完整使用指南
- ✨ 新增 `ese_scraper_fast_v2.py` - 多線程 V2 版本（不需要 Git）

### v2.0.0 (2025-10-19) 🎉

**重大更新 - V2 版本發布**

- ✨ 新增智能歌曲識別功能
  - 自動將相同歌曲的不同檔案（.tja, .ogg 等）關聯在一起
  - 以歌曲為單位而非檔案為單位進行管理
- ✨ 新增智能去重功能
  - 自動檢查並跳過已存在的檔案
  - 更新資料庫時只抓取新增的檔案
- ✨ 新增 `ese_scraper_git_v2.py` - V2 版本爬蟲
- ✨ 新增 `query_songs_v2.py` - V2 版本查詢工具
  - 支援顯示歌曲詳細資訊
  - 支援列出每首歌的所有檔案
  - 更精確的統計資訊
- ✨ 新增 `migrate_db.py` - 資料庫遷移工具
  - 可將舊版資料庫轉換為 V2 格式
- 📝 新增 `V2_GUIDE.md` - 完整的 V2 使用指南
- 🔧 重新設計資料庫結構（songs + song_files 分離）
- 📊 更精確的歌曲統計（歌曲數 vs 檔案數）

### v1.1.0 (2025-10-19)

- 新增 Git Clone 版本爬蟲（最快）
- 新增多線程版本爬蟲（快速）
- 優化效能，提供三種不同速度的抓取方式
- 更新說明文件

### v1.0.0 (2025-10-19)

- 初始版本
- 支援抓取 ESE Repository 的目錄和歌曲
- 支援 SQLite 資料庫儲存
- 提供查詢工具
- 支援匯出 CSV
