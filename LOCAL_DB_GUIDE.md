# 本地 TJA 資料庫使用指南

## 功能說明

這套工具可以讀取你本地已下載的 TJA 檔案，提取日文標題（TITLEJA），並建立一個新的資料庫。
兩個資料庫可以互通，實現以下功能：

1. **線上資料庫** (ese_songs.db) - 儲存線上 ESE Repository 的歌曲資訊（英文標題）
2. **本地資料庫** (ese_local.db) - 儲存本地 TJA 檔案的資訊（日文標題）
3. **雙向查詢** - 可以用英文找日文，或用日文找英文

## 快速開始

### 步驟 1: 建立本地 TJA 資料庫

```bash
# 掃描本地 TJA 檔案並建立資料庫
python build_local_db.py
```

**預設路徑：** `Z:\[TJA ESE]\Songs\Songs`

如果你的 TJA 檔案在其他位置：

```bash
python build_local_db.py --dir "你的TJA目錄路徑"
```

### 步驟 2: 使用整合查詢

```bash
# 搜尋歌曲（自動顯示日文標題）
python query_combined.py --search "sakura"

# 列出所有分類（顯示日文標題統計）
python query_combined.py --list

# 查詢特定分類
python query_combined.py --category Anime
```

## 詳細使用說明

### 工具 1: tja_parser.py

TJA 檔案解析器，用於讀取 TJA 檔案的 metadata。

#### 測試單個檔案

```bash
python tja_parser.py "Z:\[TJA ESE]\Songs\Songs\02 Anime\Guren no Yumiya\Guren no Yumiya.tja"
```

輸出：
```
解析檔案: Z:\[TJA ESE]\Songs\Songs\02 Anime\Guren no Yumiya\Guren no Yumiya.tja
============================================================
file_path: Z:\[TJA ESE]\Songs\Songs\02 Anime\Guren no Yumiya\Guren no Yumiya.tja
file_name: Guren no Yumiya.tja
title: Guren no Yumiya -Cover Version-
titleja: 紅蓮の弓矢 -Cover Version-
subtitle: --Linked Horizon/Attack on Titan
subtitleja: 「進撃の巨人」より
bpm: 180.62
wave: Guren no Yumiya -Cover Version-.ogg
category: 02 Anime
```

#### 掃描整個目錄

```bash
python tja_parser.py "Z:\[TJA ESE]\Songs\Songs"
```

### 工具 2: build_local_db.py

建立本地 TJA 資料庫。

#### 基本使用

```bash
# 使用預設路徑
python build_local_db.py

# 指定 TJA 目錄
python build_local_db.py --dir "Z:\[TJA ESE]\Songs\Songs"

# 自訂資料庫位置
python build_local_db.py --db my_local.db
```

#### 輸出範例

```
============================================================
本地 TJA 檔案資料庫建立工具
============================================================

✓ 資料庫初始化完成: ese_local.db

掃描目錄: Z:\[TJA ESE]\Songs\Songs
------------------------------------------------------------
找到 1523 個 TJA 檔案
開始解析...
進度: 50/1523 (3%)
進度: 100/1523 (6%)
...
✓ 成功解析 1523 首歌曲

正在儲存到資料庫...
------------------------------------------------------------

完成!
✓ 新增 1523 首歌曲
✓ 更新 0 首歌曲

資料庫統計:
  總歌曲數: 1523
  有日文標題: 1498 (98%)

  分類分布:
    01 Pop                         245 首
    02 Anime                       456 首
    03 Vocaloid                    189 首
    04 Children and Folk            78 首
    05 Variety                     123 首
    06 Classical                    56 首
    07 Game Music                  234 首
    09 Namco Original              142 首

資料庫位置: C:\Users\User\Desktop\ESEManager\ese_local.db
============================================================

總耗時: 15.34 秒
```

### 工具 3: link_databases.py

關聯線上和本地資料庫，提供雙向查詢。

#### 用英文搜尋，顯示日文

```bash
python link_databases.py --english "sakura"
```

輸出：
```
================================================================================
英文搜尋結果: 'sakura' (共 3 首)
================================================================================

🎵 Sakura Sakura
   日文: さくらさくら
   分類: 04 Children and Folk
   匹配: exact

🎵 Senbonzakura
   日文: 千本桜
   分類: 03 Vocaloid
   匹配: partial

🎵 Sakurairo Time Capsule
   日文: 桜色タイムカプセル
   分類: 02 Anime
   匹配: partial
```

#### 用日文搜尋，顯示英文

```bash
python link_databases.py --japanese "千本桜"
```

輸出：
```
================================================================================
日文搜尋結果: '千本桜' (共 1 首)
================================================================================

🎵 千本桜
   英文: Senbonzakura
   分類: 03 Vocaloid
```

#### 列出所有有日文標題的歌曲

```bash
# 列出所有
python link_databases.py --all

# 只列出 Anime 分類
python link_databases.py --all --category Anime

# 限制結果數量
python link_databases.py --all --limit 50
```

### 工具 4: query_combined.py

整合查詢工具，自動顯示日文標題。

#### 列出所有分類

```bash
python query_combined.py --list
```

輸出：
```
================================================================================
所有分類
================================================================================
📁 01 Pop                        (245 首歌曲, 240 有日文標題)
📁 02 Anime                      (456 首歌曲, 450 有日文標題)
📁 03 Vocaloid                   (189 首歌曲, 189 有日文標題)
📁 04 Children and Folk          (78 首歌曲, 75 有日文標題)
📁 05 Variety                    (123 首歌曲, 120 有日文標題)
📁 06 Classical                  (56 首歌曲, 50 有日文標題)
📁 07 Game Music                 (234 首歌曲, 230 有日文標題)
📁 09 Namco Original             (142 首歌曲, 140 有日文標題)
================================================================================
```

#### 搜尋歌曲

```bash
# 基本搜尋
python query_combined.py --search "千本桜"

# 依分類搜尋
python query_combined.py --category Anime

# 限制結果數量
python query_combined.py --search "sakura" --limit 10
```

輸出：
```
================================================================================
搜尋結果 (共 3 首)
關鍵字: sakura
================================================================================

🎵 Sakura Sakura
   日文: さくらさくら
   副標: 日本古謡
   分類: 04 Children and Folk

🎵 Senbonzakura
   日文: 千本桜
   副標: 黒うさP feat. 初音ミク
   分類: 03 Vocaloid

🎵 Sakurairo Time Capsule
   日文: 桜色タイムカプセル
   副標: 「Charlotte」より
   分類: 02 Anime

總共找到 3 首歌曲
================================================================================
```

## 資料庫結構

### ese_local.db（本地資料庫）

#### local_songs 表

| 欄位 | 類型 | 說明 |
|------|------|------|
| id | INTEGER | 主鍵 |
| title | TEXT | 英文標題（TITLE）|
| title_ja | TEXT | 日文標題（TITLEJA）|
| subtitle | TEXT | 英文副標題（SUBTITLE）|
| subtitle_ja | TEXT | 日文副標題（SUBTITLEJA）|
| category | TEXT | 分類 |
| bpm | TEXT | BPM |
| wave_file | TEXT | 音訊檔案名稱 |
| file_path | TEXT | TJA 檔案完整路徑（唯一）|
| file_name | TEXT | TJA 檔案名稱 |
| directory | TEXT | 所在目錄 |
| created_at | TIMESTAMP | 建立時間 |

## 工作流程

### 完整流程

```bash
# 1. 建立線上資料庫（如果還沒有）
python ese_scraper_git_v2.py
# 或
python ese_scraper_fast_v2.py

# 2. 建立本地 TJA 資料庫
python build_local_db.py

# 3. 使用整合查詢
python query_combined.py --search "你的搜尋關鍵字"
```

### 更新流程

當你下載了新的 TJA 檔案：

```bash
# 重新掃描本地檔案（會自動更新）
python build_local_db.py
```

當線上 ESE Repository 有更新：

```bash
# 更新線上資料庫
python ese_scraper_git_v2.py
```

## 常見問題

### Q: 為什麼有些歌曲沒有日文標題？

A: 可能原因：
1. TJA 檔案本身沒有 TITLEJA 欄位
2. 本地沒有對應的 TJA 檔案
3. 檔案名稱不完全匹配

### Q: 如何提高匹配準確度？

A: 工具使用以下匹配策略：
1. 完全匹配（最準確）
2. 模糊匹配（包含關係）
3. 正規化匹配（忽略大小寫和特殊字元）

### Q: 可以同時查詢多個資料庫版本嗎？

A: 可以！工具支援 V1 和 V2 資料庫：

```bash
# V2 資料庫
python query_combined.py --online-db ese_songs.db --search "sakura"

# V1 資料庫
python query_combined.py --online-db old_songs.db --search "sakura"
```

### Q: TJA 檔案的編碼問題

A: 解析器會自動嘗試多種編碼：
- UTF-8
- UTF-8 with BOM
- Shift-JIS（日文）
- CP932（日文）
- Latin-1

如果仍有問題，請檢查 TJA 檔案的編碼。

## 進階使用

### 在 Python 程式中使用

```python
from tja_parser import TJAParser
from build_local_db import LocalTJADatabase

# 解析單個 TJA 檔案
parser = TJAParser()
metadata = parser.parse_file("path/to/song.tja")
print(f"日文標題: {metadata.get('titleja')}")

# 建立資料庫
db = LocalTJADatabase("my_db.db")
db.init_database()
db.scan_and_build("Z:\\[TJA ESE]\\Songs\\Songs")
db.close()
```

### 自訂 SQL 查詢

```python
import sqlite3

conn = sqlite3.connect("ese_local.db")
cursor = conn.cursor()

# 查詢所有日文標題包含「桜」的歌曲
cursor.execute("""
    SELECT title, title_ja, category
    FROM local_songs
    WHERE title_ja LIKE '%桜%'
    ORDER BY category
""")

for title, title_ja, category in cursor.fetchall():
    print(f"{category} - {title} ({title_ja})")

conn.close()
```

## 指令速查表

| 功能 | 指令 |
|------|------|
| **建立本地資料庫** | `python build_local_db.py` |
| **測試解析單個檔案** | `python tja_parser.py "檔案路徑"` |
| **英文→日文查詢** | `python link_databases.py --english "sakura"` |
| **日文→英文查詢** | `python link_databases.py --japanese "千本桜"` |
| **整合查詢（推薦）** | `python query_combined.py --search "關鍵字"` |
| **列出分類（含日文統計）** | `python query_combined.py --list` |

## 注意事項

1. **路徑設定**: 預設 TJA 路徑是 `Z:\[TJA ESE]\Songs\Songs`，請根據實際情況調整
2. **編碼問題**: TJA 檔案可能使用不同編碼，工具會自動嘗試多種編碼
3. **檔案名稱匹配**: 匹配基於檔案名稱，建議保持 TJA 檔名與線上資料一致
4. **資料庫更新**: 重新執行 `build_local_db.py` 會更新現有記錄，不會重複

## 完整範例

```bash
# 假設你已經下載了 TJA 檔案到 Z:\[TJA ESE]\Songs\Songs

# 1. 建立線上資料庫
python ese_scraper_fast_v2.py

# 2. 建立本地資料庫
python build_local_db.py

# 3. 整合查詢 - 搜尋 Anime 分類的歌曲
python query_combined.py --category Anime --limit 20

# 輸出會同時顯示英文和日文標題：
# 🎵 Attack on Titan
#    日文: 進撃の巨人
#    副標: 「進撃の巨人」より
#    分類: 02 Anime
```

這樣就能完美結合線上 ESE 資料庫和本地 TJA 檔案，實現雙語查詢！
