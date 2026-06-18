# 快速開始指南

> **🎉 推薦使用 V2 版本！**
>
> V2 版本支援智能去重和歌曲關聯，避免重複抓取。
> 詳細說明請參考 [V2 使用指南](V2_GUIDE.md)

## 最快速的使用方式（V2 推薦）

### 步驟 1: 安裝 Git（如果還沒安裝）

前往 https://git-scm.com/downloads 下載並安裝 Git

### 步驟 2: 安裝 Python 依賴

```bash
pip install -r requirements.txt
```

### 步驟 3: 執行 V2 爬蟲

```bash
python ese_scraper_git_v2.py
```

等待 1-3 分鐘，完成！

**V2 優點：**
- ✅ 自動跳過已存在的檔案（再次執行時超快）
- ✅ 將 .tja、.ogg 等檔案識別為同一首歌
- ✅ 更精確的歌曲統計

### 步驟 4: 查詢歌曲（V2）

```bash
# 列出所有分類（顯示歌曲數和檔案數）
python query_songs_v2.py --list

# 搜尋歌曲
python query_songs_v2.py --search "千本桜"

# 查看歌曲詳細資訊（包含所有檔案）
python query_songs_v2.py --details "千本桜"

# 查看 Anime 分類
python query_songs_v2.py --category Anime
```

## 如果使用舊版（V1）

### 步驟 3: 執行爬蟲

```bash
python ese_scraper_git.py
```

### 步驟 4: 查詢歌曲

```bash
# 列出所有分類
python query_songs.py --list

# 搜尋歌曲
python query_songs.py --search "千本桜"

# 查看 Anime 分類
python query_songs.py --category Anime
```

### 從 V1 升級到 V2

如果你已經有 V1 資料庫，可以輕鬆遷移：

```bash
# 檢查資料庫版本
python migrate_db.py --check

# 遷移到 V2
python migrate_db.py
```

## 如果沒有 Git

使用多線程 V2 版本（推薦）：

```bash
python ese_scraper_fast_v2.py
```

**優點：**
- ✅ 不需要安裝 Git
- ✅ 支援智能去重（再次執行時超快）
- ✅ 支援歌曲檔案關聯
- 🚀 速度：首次 5-10 分鐘，更新 < 2 分鐘

或使用舊版多線程：

```bash
python ese_scraper_fast.py
```

速度稍慢（約 5-10 分鐘），但不需要安裝 Git。

## 常用指令速查表

### V2 版本（推薦）

| 功能 | 指令 |
|------|------|
| **建立資料庫（V2 最快，需要 Git）** | `python ese_scraper_git_v2.py` |
| **建立資料庫（V2 快，不需要 Git）** | `python ese_scraper_fast_v2.py` |
| **列出所有分類** | `python query_songs_v2.py --list` |
| **顯示統計** | `python query_songs_v2.py --stats` |
| **搜尋歌曲** | `python query_songs_v2.py --search "關鍵字"` |
| **查看歌曲詳情** | `python query_songs_v2.py --details "歌名"` |
| **查詢分類** | `python query_songs_v2.py --category "Anime"` |
| **匯出 CSV** | `python query_songs_v2.py --export songs.csv` |
| **遷移資料庫** | `python migrate_db.py` |

### V1 版本（舊版）

| 功能 | 指令 |
|------|------|
| **建立資料庫（最快）** | `python ese_scraper_git.py` |
| **建立資料庫（快）** | `python ese_scraper_fast.py` |
| **列出所有分類** | `python query_songs.py --list` |
| **顯示統計** | `python query_songs.py --stats` |
| **搜尋歌曲** | `python query_songs.py --search "關鍵字"` |
| **查詢分類** | `python query_songs.py --category "Anime"` |
| **匯出 CSV** | `python query_songs.py --export songs.csv` |

## 版本比較

### V2 vs V1

| 功能 | V1 | V2 |
|------|----|----|
| 歌曲識別 | 以檔案為單位 | ✅ 以歌曲為單位 |
| 去重 | ❌ 會重複抓取 | ✅ 自動跳過已存在 |
| 統計 | 檔案數量 | ✅ 歌曲數 + 檔案數 |
| 檔案關聯 | ❌ 無 | ✅ .tja + .ogg 關聯 |
| 速度（首次） | 1-3 分鐘 | 1-3 分鐘 |
| 速度（更新） | 1-3 分鐘 | ✅ < 1 分鐘（跳過已存在）|

### 速度比較

```
V2 版本（推薦）
⚡ Git Clone V2      →  首次: 1-3 分鐘, 更新: <1 分鐘   →  ★ 最推薦（需要 Git）
🚀 多線程 V2         →  首次: 5-10 分鐘, 更新: <2 分鐘  →  ★ 不需要 Git

V1 版本（舊版）
⚡ Git Clone         →  1-3 分鐘    →  需要 Git
🚀 多線程版本        →  5-10 分鐘   →  不需要 Git
🐌 標準版本          →  10-30 分鐘  →  除錯用
```

## 完整文檔

詳細說明請參考 [README.md](README.md)
