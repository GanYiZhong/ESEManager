"""
建立本地 TJA 檔案資料庫
掃描本地 TJA 檔案並建立包含日文標題的資料庫
"""

import sqlite3
import os
import sys
from pathlib import Path
from tja_parser import TJAParser

# 修復 Windows 控制台編碼問題
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass


class LocalTJADatabase:
    """本地 TJA 檔案資料庫管理器"""

    def __init__(self, db_path: str = "ese_local.db"):
        """
        初始化資料庫管理器

        Args:
            db_path: 資料庫檔案路徑
        """
        self.db_path = db_path
        self.conn = None
        self.parser = TJAParser()

    def init_database(self):
        """建立資料庫結構"""
        self.conn = sqlite3.connect(self.db_path)
        cursor = self.conn.cursor()

        # 建立本地歌曲表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS local_songs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                title_ja TEXT,
                subtitle TEXT,
                subtitle_ja TEXT,
                category TEXT,
                bpm TEXT,
                wave_file TEXT,
                file_path TEXT NOT NULL UNIQUE,
                file_name TEXT,
                directory TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 建立索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_local_title ON local_songs(title)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_local_title_ja ON local_songs(title_ja)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_local_category ON local_songs(category)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_local_file_path ON local_songs(file_path)")

        self.conn.commit()
        print(f"✓ 資料庫初始化完成: {self.db_path}")

    def insert_song(self, metadata: dict) -> bool:
        """
        插入歌曲記錄

        Args:
            metadata: 歌曲 metadata

        Returns:
            是否成功插入
        """
        cursor = self.conn.cursor()

        # 檢查是否已存在
        file_path = metadata.get('file_path')
        cursor.execute("SELECT id FROM local_songs WHERE file_path = ?", (file_path,))

        if cursor.fetchone():
            # 更新現有記錄
            cursor.execute("""
                UPDATE local_songs
                SET title = ?, title_ja = ?, subtitle = ?, subtitle_ja = ?,
                    category = ?, bpm = ?, wave_file = ?, file_name = ?, directory = ?
                WHERE file_path = ?
            """, (
                metadata.get('title'),
                metadata.get('titleja'),
                metadata.get('subtitle'),
                metadata.get('subtitleja'),
                metadata.get('category'),
                metadata.get('bpm'),
                metadata.get('wave'),
                metadata.get('file_name'),
                metadata.get('directory'),
                file_path
            ))
            # 不在此處 commit；統一在掃描結束後一次性 commit
            return False
        else:
            # 插入新記錄
            cursor.execute("""
                INSERT INTO local_songs
                (title, title_ja, subtitle, subtitle_ja, category, bpm, wave_file,
                 file_path, file_name, directory)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                metadata.get('title'),
                metadata.get('titleja'),
                metadata.get('subtitle'),
                metadata.get('subtitleja'),
                metadata.get('category'),
                metadata.get('bpm'),
                metadata.get('wave'),
                file_path,
                metadata.get('file_name'),
                metadata.get('directory')
            ))
            # 不在此處 commit；統一在掃描結束後一次性 commit
            return True

    def scan_and_build(self, tja_directory: str):
        """
        掃描目錄並建立資料庫

        Args:
            tja_directory: TJA 檔案所在目錄
        """
        print("=" * 60)
        print("本地 TJA 檔案資料庫建立工具")
        print("=" * 60)
        print()

        # 初始化資料庫
        self.init_database()
        print()

        # 掃描並解析 TJA 檔案
        print(f"掃描目錄: {tja_directory}")
        print("-" * 60)

        songs = self.parser.parse_directory(tja_directory, recursive=True, show_progress=True)

        print()
        print("正在儲存到資料庫...")
        print("-" * 60)

        new_count = 0
        updated_count = 0

        for song in songs:
            is_new = self.insert_song(song)
            if is_new:
                new_count += 1
            else:
                updated_count += 1

        # 一次性提交所有變更（取代每筆 commit，大幅減少磁碟 fsync）
        self.conn.commit()

        print()
        print("完成!")
        print(f"✓ 新增 {new_count} 首歌曲")
        print(f"✓ 更新 {updated_count} 首歌曲")
        print()

        # 顯示統計
        self.show_stats()

        print()
        print(f"資料庫位置: {os.path.abspath(self.db_path)}")
        print("=" * 60)

    def show_stats(self):
        """顯示資料庫統計"""
        cursor = self.conn.cursor()

        # 總歌曲數
        cursor.execute("SELECT COUNT(*) FROM local_songs")
        total = cursor.fetchone()[0]

        # 有日文標題的數量
        cursor.execute("SELECT COUNT(*) FROM local_songs WHERE title_ja IS NOT NULL AND title_ja != ''")
        ja_count = cursor.fetchone()[0]

        # 分類統計
        cursor.execute("""
            SELECT category, COUNT(*) as count
            FROM local_songs
            WHERE category IS NOT NULL
            GROUP BY category
            ORDER BY category
        """)
        categories = cursor.fetchall()

        print("資料庫統計:")
        print(f"  總歌曲數: {total}")
        print(f"  有日文標題: {ja_count} ({ja_count*100//total if total > 0 else 0}%)")
        print()
        print("  分類分布:")
        for cat, count in categories:
            print(f"    {cat:<30} {count:>4} 首")

    def close(self):
        """關閉資料庫連接"""
        if self.conn:
            self.conn.close()


def build_from_remote(song_db: str = "ese_songs.db", local_db: str = "ese_local.db",
                      workers: int = 12):
    """
    直接從 ESE 抓每個 .tja 文字檔，解析 TITLEJA 等 metadata 建立日文標題資料庫。
    不需本機曲庫、不下載音檔；涵蓋資料庫中全部歌曲（.tja 檔很小，總量約 10MB）。
    .tja 清單與下載網址直接取自已建好的 ese_songs.db。
    """
    import requests
    import urllib3
    from concurrent.futures import ThreadPoolExecutor
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    if not os.path.exists(song_db):
        print(f"✗ 找不到歌曲資料庫: {song_db}（請先更新歌曲庫）")
        return

    conn = sqlite3.connect(song_db)
    rows = conn.execute(
        "SELECT f.file_path, f.download_url, f.filename, c.name "
        "FROM song_files f "
        "LEFT JOIN songs s ON f.song_id = s.id "
        "LEFT JOIN categories c ON s.category_id = c.id "
        "WHERE f.file_type = '.tja'"
    ).fetchall()
    conn.close()

    total = len(rows)
    print(f"準備從 ESE 抓取 {total} 個 .tja 解析日文標題...")
    print("-" * 60)

    parser = TJAParser()
    sess = requests.Session()
    sess.headers["User-Agent"] = "ESEManager"

    def fetch(row):
        file_path, url, filename, category = row
        try:
            r = sess.get(url, timeout=30, verify=False)
            r.raise_for_status()
            text = TJAParser.decode_bytes(r.content)
            if text is None:
                return None
            meta = parser.parse_text(text)
            meta["file_path"] = file_path
            meta["file_name"] = filename
            meta["directory"] = os.path.dirname(file_path)
            if category:
                meta["category"] = category
            return meta
        except Exception:
            return None

    db = LocalTJADatabase(db_path=local_db)
    db.init_database()

    done = 0
    new_count = ja_count = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        for meta in ex.map(fetch, rows):
            done += 1
            if meta:
                db.insert_song(meta)
                new_count += 1
                if meta.get("titleja"):
                    ja_count += 1
            if done % 200 == 0:
                print(f"進度: {done}/{total} ({done*100//total}%)")

    db.conn.commit()   # 一次性提交
    print("-" * 60)
    print(f"✓ 完成：寫入 {new_count} 首，其中 {ja_count} 首有日文標題")
    db.show_stats()
    db.close()


def main():
    """主程式"""
    import argparse

    parser = argparse.ArgumentParser(
        description='建立本地 TJA 檔案資料庫',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用範例:
  python build_local_db.py
  python build_local_db.py --dir "Z:\\[TJA ESE]\\Songs\\Songs"
  python build_local_db.py --db my_local.db
        """
    )

    parser.add_argument('--dir', default=r'Z:\[TJA ESE]\Songs\Songs',
                       help='TJA 檔案所在目錄')
    parser.add_argument('--db', default='ese_local.db',
                       help='資料庫路徑（預設: ese_local.db）')

    args = parser.parse_args()

    # 檢查目錄是否存在
    if not os.path.exists(args.dir):
        print(f"✗ 目錄不存在: {args.dir}")
        print("\n請使用 --dir 參數指定 TJA 檔案所在目錄")
        return

    # 建立資料庫
    db = LocalTJADatabase(db_path=args.db)

    try:
        import time
        start_time = time.time()

        db.scan_and_build(args.dir)

        elapsed_time = time.time() - start_time
        print(f"\n總耗時: {elapsed_time:.2f} 秒")

    finally:
        db.close()


if __name__ == "__main__":
    main()
