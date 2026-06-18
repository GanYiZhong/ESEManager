"""
ESE 歌曲下載工具
支援下載指定歌曲的 TJA 和 OGG 檔案，保持目錄結構
"""

import sqlite3
import os
import sys
import requests
from pathlib import Path
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# 修復 Windows 控制台編碼問題
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass


def safe_print(text):
    """安全打印，避免編碼錯誤"""
    try:
        print(text)
    except UnicodeEncodeError:
        text = text.encode(sys.stdout.encoding, errors='replace').decode(sys.stdout.encoding)
        print(text)


class SongDownloader:
    """歌曲下載器"""

    def __init__(self, db_path: str = "ese_songs.db", download_dir: str = "Downloads"):
        """
        初始化下載器

        Args:
            db_path: 資料庫路徑
            download_dir: 下載目錄
        """
        self.db_path = db_path
        self.download_dir = download_dir
        self.conn = None
        self.is_v2 = False

        # 統計
        self.stats = {
            "total_files": 0,
            "downloaded": 0,
            "skipped": 0,
            "failed": 0
        }

    def connect(self) -> bool:
        """連接資料庫"""
        if not os.path.exists(self.db_path):
            print(f"✗ 資料庫不存在: {self.db_path}")
            print("請先執行爬蟲程式建立資料庫")
            return False

        self.conn = sqlite3.connect(self.db_path)

        # 檢查資料庫版本
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='song_files'
        """)
        self.is_v2 = cursor.fetchone() is not None

        return True

    def search_songs(self, keyword: str = None, category: str = None,
                     keywords: List[str] = None) -> List[Dict]:
        """
        搜尋歌曲

        Args:
            keyword: 搜尋關鍵字（None 表示所有歌曲）
            category: 分類篩選
            keywords: 多個關鍵字（任一符合即命中，OR 條件）。用於日文標題
                      對應的多個英文標題，避免一個一個查造成多次往返

        Returns:
            歌曲列表
        """
        if not self.connect():
            return []

        cursor = self.conn.cursor()
        results = []

        if self.is_v2:
            # V2 資料庫
            # 使用單次 LEFT JOIN 一併撈出歌曲與檔案，避免 N+1 查詢
            # （舊版會對每首歌各跑一次 song_files 查詢，3000+ 首歌 = 3000+ 次往返）
            query = """
                SELECT s.id, s.song_name, c.name as category, s.base_path,
                       f.filename, f.file_path, f.file_type, f.size, f.download_url
                FROM songs s
                LEFT JOIN categories c ON s.category_id = c.id
                LEFT JOIN song_files f ON f.song_id = s.id
                WHERE 1=1
            """
            params = []

            if keyword:
                query += " AND s.song_name LIKE ?"
                params.append(f"%{keyword}%")

            if keywords:
                ors = " OR ".join(["s.song_name LIKE ?"] * len(keywords))
                query += f" AND ({ors})"
                params.extend(f"%{kw}%" for kw in keywords)

            if category:
                query += " AND c.name LIKE ?"
                params.append(f"%{category}%")

            query += " ORDER BY s.id, f.file_type"

            cursor.execute(query, params)

            # 依 song_id 分組，保留歌曲首次出現順序
            songs_by_id = {}
            for row in cursor.fetchall():
                song_id, song_name, cat, base_path = row[0], row[1], row[2], row[3]
                filename = row[4]

                song = songs_by_id.get(song_id)
                if song is None:
                    song = {
                        'song_name': song_name,
                        'category': cat,
                        'base_path': base_path,
                        'files': []
                    }
                    songs_by_id[song_id] = song
                    results.append(song)

                # 因為 LEFT JOIN，沒有檔案的歌曲此欄位為 None
                if filename is not None:
                    song['files'].append({
                        'filename': filename,
                        'file_path': row[5],
                        'file_type': row[6],
                        'size': row[7],
                        'download_url': row[8]
                    })

        else:
            # V1 資料庫
            query = """
                SELECT s.filename, c.name as category, s.path, s.file_type, s.size, s.download_url
                FROM songs s
                LEFT JOIN categories c ON s.category_id = c.id
                WHERE 1=1
            """
            params = []

            if keyword:
                query += " AND s.filename LIKE ?"
                params.append(f"%{keyword}%")

            if category:
                query += " AND c.name LIKE ?"
                params.append(f"%{category}%")

            cursor.execute(query, params)

            # 將 V1 格式轉換為類似 V2 的結構
            songs_dict = {}
            for row in cursor.fetchall():
                filename, cat, path, file_type, size, download_url = row
                song_name = os.path.splitext(filename)[0]

                if song_name not in songs_dict:
                    songs_dict[song_name] = {
                        'song_name': song_name,
                        'category': cat,
                        'base_path': os.path.dirname(path),
                        'files': []
                    }

                songs_dict[song_name]['files'].append({
                    'filename': filename,
                    'file_path': path,
                    'file_type': file_type,
                    'size': size,
                    'download_url': download_url
                })

            results = list(songs_dict.values())

        return results

    def download_file(self, url: str, save_path: str, file_size: int = None) -> bool:
        """
        下載單個檔案

        Args:
            url: 下載連結
            save_path: 儲存路徑
            file_size: 檔案大小（用於顯示）

        Returns:
            是否成功
        """
        try:
            # 檢查檔案是否已存在
            if os.path.exists(save_path):
                safe_print(f"  ⊘ 已存在: {os.path.basename(save_path)}")
                self.stats["skipped"] += 1
                return True

            # 建立目錄
            os.makedirs(os.path.dirname(save_path), exist_ok=True)

            # 下載
            response = requests.get(url, stream=True, timeout=60)
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0)) or file_size or 0
            downloaded = 0

            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

            # 顯示檔案大小
            size_mb = downloaded / 1024 / 1024
            safe_print(f"  ✓ 下載完成: {os.path.basename(save_path)} ({size_mb:.2f} MB)")
            self.stats["downloaded"] += 1
            return True

        except requests.RequestException as e:
            safe_print(f"  ✗ 下載失敗: {os.path.basename(save_path)} - {e}")
            self.stats["failed"] += 1
            # 刪除不完整的檔案
            if os.path.exists(save_path):
                os.remove(save_path)
            return False
        except Exception as e:
            safe_print(f"  ✗ 錯誤: {os.path.basename(save_path)} - {e}")
            self.stats["failed"] += 1
            if os.path.exists(save_path):
                os.remove(save_path)
            return False

    def download_song(self, song: Dict, file_types: List[str] = None) -> bool:
        """
        下載單首歌曲的所有檔案

        Args:
            song: 歌曲資訊
            file_types: 要下載的檔案類型（None 表示全部）

        Returns:
            是否成功
        """
        song_name = song['song_name']
        base_path = song['base_path']
        files = song['files']

        safe_print(f"\n[下載] {song_name}")
        safe_print(f"  分類: {song['category']}")
        safe_print(f"  路徑: {base_path}")

        # 篩選檔案類型
        if file_types:
            files = [f for f in files if f['file_type'] in file_types]

        if not files:
            safe_print(f"  ⚠ 沒有找到要下載的檔案")
            return False

        safe_print(f"  檔案數: {len(files)}")

        # 下載所有檔案
        success_count = 0
        for file_info in files:
            file_path = file_info['file_path']
            download_url = file_info['download_url']
            file_size = file_info.get('size', 0)

            # 建立完整的儲存路徑
            save_path = os.path.join(self.download_dir, file_path)

            # 下載
            self.stats["total_files"] += 1
            if self.download_file(download_url, save_path, file_size):
                success_count += 1

        return success_count == len(files)

    def download_by_keyword(self, keyword: str = None, category: str = None,
                           file_types: List[str] = None, limit: int = None,
                           max_workers: int = 1, auto_yes: bool = False) -> None:
        """
        根據關鍵字下載歌曲

        Args:
            keyword: 搜尋關鍵字（None 表示下載所有歌曲）
            category: 分類篩選
            file_types: 要下載的檔案類型（例如 ['.tja', '.ogg']）
            limit: 限制下載數量
            max_workers: 並行下載數（預設 1，建議不超過 3）
            auto_yes: 自動確認下載，不詢問
        """
        safe_print("=" * 80)
        safe_print("ESE 歌曲下載工具")
        safe_print("=" * 80)
        if keyword:
            safe_print(f"搜尋關鍵字: {keyword}")
        else:
            safe_print(f"模式: 下載所有歌曲")
        if category:
            safe_print(f"分類篩選: {category}")
        if file_types:
            safe_print(f"檔案類型: {', '.join(file_types)}")
        safe_print(f"下載目錄: {os.path.abspath(self.download_dir)}")
        safe_print("=" * 80)

        # 搜尋歌曲
        songs = self.search_songs(keyword, category)

        if not songs:
            safe_print("\n✗ 沒有找到符合條件的歌曲")
            return

        safe_print(f"\n找到 {len(songs)} 首歌曲")

        # 限制數量
        if limit and limit < len(songs):
            songs = songs[:limit]
            safe_print(f"限制下載前 {limit} 首")

        # 確認下載
        safe_print("\n即將下載以下歌曲:")
        for i, song in enumerate(songs, 1):
            files = song['files']
            if file_types:
                files = [f for f in files if f['file_type'] in file_types]
            safe_print(f"  {i}. {song['song_name']} ({len(files)} 個檔案)")

        if not auto_yes:
            response = input("\n是否繼續? (y/N): ")
            if response.lower() != 'y':
                safe_print("取消下載")
                return
        else:
            safe_print("\n自動確認模式，開始下載...")

        safe_print("\n開始下載...")
        safe_print("-" * 80)

        start_time = time.time()

        # 下載歌曲
        if max_workers > 1:
            # 並行下載
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = []
                for song in songs:
                    future = executor.submit(self.download_song, song, file_types)
                    futures.append(future)

                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as e:
                        safe_print(f"✗ 下載時發生錯誤: {e}")
        else:
            # 順序下載
            for song in songs:
                self.download_song(song, file_types)

        elapsed_time = time.time() - start_time

        # 顯示統計
        safe_print("-" * 80)
        safe_print("\n下載完成!")
        safe_print(f"  總檔案數: {self.stats['total_files']}")
        safe_print(f"  成功下載: {self.stats['downloaded']}")
        safe_print(f"  已存在跳過: {self.stats['skipped']}")
        safe_print(f"  下載失敗: {self.stats['failed']}")
        safe_print(f"  總耗時: {elapsed_time:.2f} 秒")
        safe_print(f"\n下載位置: {os.path.abspath(self.download_dir)}")
        safe_print("=" * 80)

    def close(self):
        """關閉資料庫連接"""
        if self.conn:
            self.conn.close()


def main():
    """主程式"""
    import argparse

    parser = argparse.ArgumentParser(
        description='ESE 歌曲下載工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用範例:
  # 下載包含 "千本桜" 的歌曲（所有檔案）
  python download_songs.py --search "Senbonzakura"

  # 只下載 .tja 和 .ogg 檔案
  python download_songs.py --search "Senbonzakura" --types .tja .ogg

  # 下載所有歌曲的 .tja 檔案
  python download_songs.py --all --types .tja

  # 下載所有歌曲的 .ogg 檔案
  python download_songs.py --all --types .ogg

  # 下載所有歌曲（所有檔案）
  python download_songs.py --all

  # 下載 Anime 分類的所有歌曲
  python download_songs.py --all --category Anime

  # 下載 Anime 分類的所有 .tja 檔案
  python download_songs.py --all --category Anime --types .tja

  # 指定下載目錄
  python download_songs.py --all --types .tja --dir "D:\\TJA Downloads"

  # 限制下載數量
  python download_songs.py --all --limit 10

  # 並行下載（最多建議 3 個線程）
  python download_songs.py --all --workers 3 --yes
        """
    )

    parser.add_argument('--search', metavar='KEYWORD',
                       help='搜尋關鍵字（歌曲名稱）')
    parser.add_argument('--all', action='store_true',
                       help='下載所有歌曲（可搭配 --category 和 --types 使用）')
    parser.add_argument('--category', metavar='CATEGORY',
                       help='分類篩選（例如: Anime, Pop）')
    parser.add_argument('--types', nargs='+', metavar='TYPE',
                       help='要下載的檔案類型（例如: .tja .ogg）')
    parser.add_argument('--dir', default='Downloads',
                       help='下載目錄（預設: Downloads）')
    parser.add_argument('--db', default='ese_songs.db',
                       help='資料庫路徑（預設: ese_songs.db）')
    parser.add_argument('--limit', type=int, metavar='N',
                       help='限制下載數量')
    parser.add_argument('--workers', type=int, default=1, metavar='N',
                       help='並行下載線程數（預設: 1，建議不超過 3）')
    parser.add_argument('-y', '--yes', action='store_true',
                       help='自動確認下載，不詢問')

    args = parser.parse_args()

    # 參數驗證
    if not args.search and not args.all:
        parser.error("請指定 --search 或 --all 參數")

    # 建立下載器
    downloader = SongDownloader(db_path=args.db, download_dir=args.dir)

    try:
        # 決定搜尋關鍵字
        keyword = args.search if not args.all else None

        # 執行下載
        downloader.download_by_keyword(
            keyword=keyword,
            category=args.category,
            file_types=args.types,
            limit=args.limit,
            max_workers=args.workers,
            auto_yes=args.yes
        )
    finally:
        downloader.close()


if __name__ == "__main__":
    main()
