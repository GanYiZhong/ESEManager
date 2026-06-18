"""
ESE Song Database Scraper (Git Clone Version V2 - Fastest)
使用 git clone 方式抓取 ESE Repository（最快速度）
V2: 支援智能去重和歌曲檔案關聯
"""

import sqlite3
import os
import sys
import subprocess
import shutil
import urllib.parse
from pathlib import Path
from typing import Dict, Optional

# 檔案下載來源（git.vanillaaaa.org 已停用，改用官方 ese.tjadataba.se）
DOWNLOAD_BASE = "https://ese.tjadataba.se/ESE/ESE/raw/branch/master/"

# 可攜版 git 解壓後的位置（找不到系統 git 時的備援）
PORTABLE_GIT_DIR = os.path.join(os.getcwd(), "portablegit")


def find_git() -> Optional[str]:
    """回傳可用的 git 執行檔路徑：先找系統 PATH，再找本機可攜版；都沒有回 None。"""
    sys_git = shutil.which("git")
    if sys_git:
        return sys_git
    for sub in ("cmd/git.exe", "bin/git.exe", "mingw64/bin/git.exe"):
        cand = os.path.join(PORTABLE_GIT_DIR, sub)
        if os.path.exists(cand):
            return cand
    return None


def download_portable_git(dest_dir: str = PORTABLE_GIT_DIR) -> Optional[str]:
    """
    下載 git-for-windows 的可攜版 MinGit 並解壓到 dest_dir，回傳 git.exe 路徑。
    透過 GitHub API 找最新版的 MinGit-*-64-bit.zip（不需安裝、不需管理員）。
    """
    import requests
    import zipfile
    import io

    if sys.platform != "win32":
        print("✗ 自動下載可攜版 git 僅支援 Windows，請手動安裝 git")
        return None

    print("正在查詢最新版可攜版 git (MinGit)...")
    api = "https://api.github.com/repos/git-for-windows/git/releases/latest"
    r = requests.get(api, timeout=30, headers={"User-Agent": "ESEManager"})
    r.raise_for_status()
    asset = None
    for a in r.json().get("assets", []):
        n = a.get("name", "")
        if n.startswith("MinGit-") and n.endswith("-64-bit.zip") and "busybox" not in n:
            asset = a
            break
    if not asset:
        print("✗ 找不到 MinGit 下載連結，請手動安裝 git: https://git-scm.com/downloads")
        return None

    url = asset["browser_download_url"]
    size_mb = asset.get("size", 0) / 1024 / 1024
    print(f"下載 {asset['name']} ({size_mb:.0f} MB)...")
    dl = requests.get(url, timeout=300, stream=True, headers={"User-Agent": "ESEManager"})
    dl.raise_for_status()
    buf = io.BytesIO()
    got = 0
    for chunk in dl.iter_content(1 << 16):
        if chunk:
            buf.write(chunk)
            got += len(chunk)
            if got % (4 << 20) < (1 << 16):
                print(f"  已下載 {got/1024/1024:.0f} MB...")

    print("解壓中...")
    if os.path.exists(dest_dir):
        shutil.rmtree(dest_dir, ignore_errors=True)
    os.makedirs(dest_dir, exist_ok=True)
    with zipfile.ZipFile(buf) as z:
        z.extractall(dest_dir)

    git_exe = find_git()
    if git_exe:
        print(f"✓ 可攜版 git 就緒: {git_exe}")
    else:
        print("✗ 解壓後仍找不到 git.exe")
    return git_exe


class ESEScraperGitV2:
    def __init__(self, db_path: str = "ese_songs.db", clone_dir: str = "ESE_clone",
                 git_exe: str = "git"):
        """
        初始化 ESE 爬蟲（Git Clone 版本 V2）

        Args:
            db_path: SQLite 資料庫路徑
            clone_dir: Git clone 目錄
            git_exe: git 執行檔路徑（預設 "git"，GUI 可傳入可攜版路徑）
        """
        self.git_url = "https://ese.tjadataba.se/ESE/ESE.git"
        self.db_path = db_path
        self.clone_dir = clone_dir
        self.git_exe = git_exe or "git"
        self.conn = None

        # 統計資料
        self.stats = {
            "folders": 0,
            "songs": 0,
            "files": 0,
            "skipped": 0,
            "categories": 0
        }

    def init_database(self):
        """建立資料庫表結構（V2 - 分離歌曲和檔案）"""
        self.conn = sqlite3.connect(self.db_path)
        cursor = self.conn.cursor()

        # 建立分類表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                path TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 建立歌曲主表（一首歌只有一條記錄）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS songs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER,
                song_name TEXT NOT NULL,
                base_path TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (category_id) REFERENCES categories (id),
                UNIQUE(category_id, song_name)
            )
        """)

        # 建立歌曲檔案表（一首歌可以有多個檔案）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS song_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                song_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                file_path TEXT NOT NULL UNIQUE,
                file_type TEXT,
                size INTEGER,
                download_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (song_id) REFERENCES songs (id) ON DELETE CASCADE
            )
        """)

        # 建立索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_songs_category ON songs(category_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_songs_name ON songs(song_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_song ON song_files(song_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_path ON song_files(file_path)")

        self.conn.commit()
        print(f"✓ 資料庫初始化完成: {self.db_path}")

    def _run_git(self, args, timeout) -> int:
        """執行 git 並逐行 print 其輸出（讓 GUI 可用 stdout 重導擷取、CLI 也看得到）。"""
        proc = subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, encoding="utf-8", errors="replace"
        )
        try:
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    print(line)
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise
        return proc.returncode

    def clone_repository(self) -> bool:
        """
        Clone Git Repository

        Returns:
            是否成功
        """
        print(f"正在 clone repository 到 {self.clone_dir}...")
        print("-" * 60)

        try:
            # 如果目錄已存在，先檢查是否需要更新
            if os.path.exists(self.clone_dir):
                print(f"發現現有目錄 {self.clone_dir}，正在更新 (git pull)...")
                try:
                    if self._run_git([self.git_exe, "-C", self.clone_dir, "pull", "--progress"], 1800) == 0:
                        print("✓ Repository 已更新")
                        return True
                    print("更新失敗，重新 clone...")
                    shutil.rmtree(self.clone_dir)
                except subprocess.TimeoutExpired:
                    raise
                except Exception:
                    print("更新失敗，重新 clone...")
                    shutil.rmtree(self.clone_dir)

            # Clone repository
            # --filter=blob:none --no-checkout：只抓 commit/tree（檔案清單），
            #   不下載任何檔案內容（音檔數 GB）。建 DB 只需檔名/路徑，數秒即可完成。
            rc = self._run_git(
                [self.git_exe, "clone", "--depth", "1", "-b", "master", "--single-branch",
                 "--filter=blob:none", "--no-checkout", "--progress",
                 self.git_url, self.clone_dir],
                3600  # 60 分鐘超時（保險用；blobless 通常數秒）
            )
            if rc != 0:
                print(f"✗ Clone 失敗 (git 回傳碼 {rc})，請見上方 git 訊息")
                return False

            print("✓ Repository clone 完成")
            return True

        except FileNotFoundError:
            print("✗ 錯誤: 找不到 git 命令")
            print("請確認已安裝 Git: https://git-scm.com/downloads")
            return False
        except subprocess.TimeoutExpired:
            print("✗ Clone 超時")
            return False
        except Exception as e:
            print(f"✗ Clone 時發生錯誤: {e}")
            return False

    def insert_category(self, name: str, path: str) -> int:
        """
        插入或更新分類

        Args:
            name: 分類名稱
            path: 分類路徑

        Returns:
            分類 ID
        """
        cursor = self.conn.cursor()

        # 檢查是否已存在
        cursor.execute("SELECT id FROM categories WHERE path = ?", (path,))
        result = cursor.fetchone()

        if result:
            return result[0]

        cursor.execute("""
            INSERT INTO categories (name, path) VALUES (?, ?)
        """, (name, path))
        # 不在此處 commit；統一在掃描結束後一次性 commit（避免每筆都 fsync）

        return cursor.lastrowid

    def get_song_name(self, filename: str) -> str:
        """
        從檔案名稱提取歌曲名稱（去除副檔名）

        Args:
            filename: 檔案名稱

        Returns:
            歌曲名稱
        """
        return os.path.splitext(filename)[0]

    def file_exists(self, file_path: str) -> bool:
        """
        檢查檔案是否已存在於資料庫

        Args:
            file_path: 檔案路徑

        Returns:
            是否已存在
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT id FROM song_files WHERE file_path = ?", (file_path,))
        return cursor.fetchone() is not None

    def get_or_create_song(self, category_id: int, song_name: str, base_path: str) -> int:
        """
        獲取或建立歌曲記錄

        Args:
            category_id: 分類 ID
            song_name: 歌曲名稱
            base_path: 基礎路徑

        Returns:
            歌曲 ID
        """
        cursor = self.conn.cursor()

        # 檢查是否已存在
        cursor.execute("""
            SELECT id FROM songs
            WHERE category_id = ? AND song_name = ?
        """, (category_id, song_name))

        result = cursor.fetchone()
        if result:
            return result[0]

        # 建立新記錄
        cursor.execute("""
            INSERT INTO songs (category_id, song_name, base_path)
            VALUES (?, ?, ?)
        """, (category_id, song_name, base_path))
        # 不在此處 commit；統一在掃描結束後一次性 commit

        return cursor.lastrowid

    def insert_song_file(self, song_id: int, filename: str, file_path: str,
                        file_type: str, size: int) -> bool:
        """
        插入歌曲檔案

        Args:
            song_id: 歌曲 ID
            filename: 檔案名稱
            file_path: 檔案路徑
            file_type: 檔案類型
            size: 檔案大小

        Returns:
            是否成功插入（False 表示已存在，跳過）
        """
        # 檢查是否已存在
        if self.file_exists(file_path):
            return False

        cursor = self.conn.cursor()

        # 建立下載 URL（路徑含空白/日文，需 URL 編碼，否則 requests 會拒絕）
        download_url = DOWNLOAD_BASE + urllib.parse.quote(file_path)

        cursor.execute("""
            INSERT INTO song_files (song_id, filename, file_path, file_type, size, download_url)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (song_id, filename, file_path, file_type, size, download_url))
        # 不在此處 commit；統一在掃描結束後一次性 commit
        return True

    def scan_directory(self, directory: Path, category_id: int = None,
                      base_path: Path = None, level: int = 0):
        """
        遞迴掃描本地目錄

        Args:
            directory: 要掃描的目錄
            category_id: 分類 ID
            base_path: 基準路徑（用於計算相對路徑）
            level: 層級深度
        """
        if base_path is None:
            base_path = directory

        try:
            for item in directory.iterdir():
                # 跳過 .git 目錄
                if item.name == '.git':
                    continue

                # 計算相對路徑（用於資料庫）
                rel_path = str(item.relative_to(base_path)).replace('\\', '/')

                if item.is_dir():
                    self.stats["folders"] += 1

                    # 第一層目錄視為分類
                    if level == 0:
                        cat_id = self.insert_category(item.name, rel_path)
                        self.stats["categories"] += 1
                        print(f"📁 {item.name}")

                        # 遞迴掃描
                        self.scan_directory(item, cat_id, base_path, level + 1)
                    else:
                        # 非第一層，繼續使用父分類
                        self.scan_directory(item, category_id, base_path, level + 1)

                elif item.is_file():
                    if category_id:
                        # 提取歌曲名稱（不含副檔名）
                        song_name = self.get_song_name(item.name)
                        file_size = item.stat().st_size
                        file_ext = item.suffix

                        # 獲取或建立歌曲記錄
                        song_id = self.get_or_create_song(
                            category_id=category_id,
                            song_name=song_name,
                            base_path=os.path.dirname(rel_path)
                        )

                        # 插入檔案記錄
                        is_new = self.insert_song_file(
                            song_id=song_id,
                            filename=item.name,
                            file_path=rel_path,
                            file_type=file_ext,
                            size=file_size
                        )

                        if is_new:
                            self.stats["files"] += 1
                        else:
                            self.stats["skipped"] += 1

        except PermissionError:
            print(f"✗ 無權限訪問: {directory}")
        except Exception as e:
            print(f"✗ 掃描目錄時發生錯誤: {e}")

    def build_from_git_tree(self, ref: str = "master"):
        """
        從 git tree 讀取檔案清單建立資料庫（無需 checkout、不下載檔案內容）。

        使用 `git ls-tree -r -z <ref>`：
          -r 遞迴列出所有檔案；-z 以 NUL 分隔且不對路徑做引號轉義，
          可直接拿到含日文/空白的原始路徑，免處理 git 的 C-style 八進位轉義。
        blobless clone 沒有檔案內容，故檔案大小一律設 0（僅影響 GUI 顯示，
        不影響搜尋與下載；下載時以 HTTP content-length 為準）。
        """
        result = subprocess.run(
            [self.git_exe, "-C", self.clone_dir, "ls-tree", "-r", "-z", ref],
            capture_output=True, timeout=300
        )
        if result.returncode != 0:
            err = result.stderr.decode("utf-8", "replace") if result.stderr else ""
            print(f"✗ 讀取 git 檔案清單失敗: {err}")
            return

        raw = result.stdout.decode("utf-8", "replace")
        cat_ids = {}       # category name -> id（快取，避免每檔 SELECT/INSERT）
        folder_set = set()  # 統計不重複資料夾數
        for record in raw.split("\0"):
            if not record:
                continue
            # 格式: "<mode> <type> <sha>\t<path>"
            try:
                meta, path = record.split("\t", 1)
            except ValueError:
                continue
            fields = meta.split()
            if len(fields) < 2 or fields[1] != "blob":
                continue  # 只處理 blob（檔案），略過 submodule（commit）等

            path = path.replace("\\", "/")
            parts = path.split("/")
            if len(parts) < 2:
                continue  # 根目錄檔案（如 .gitignore）無分類，略過

            category_name = parts[0]
            filename = parts[-1]
            base_path = "/".join(parts[:-1])
            song_name = self.get_song_name(filename)
            file_ext = os.path.splitext(filename)[1]
            folder_set.add(base_path)

            cat_id = cat_ids.get(category_name)
            if cat_id is None:
                cat_id = self.insert_category(category_name, category_name)
                cat_ids[category_name] = cat_id
                self.stats["categories"] += 1
                print(f"📁 {category_name}")

            song_id = self.get_or_create_song(
                category_id=cat_id, song_name=song_name, base_path=base_path
            )
            is_new = self.insert_song_file(
                song_id=song_id, filename=filename, file_path=path,
                file_type=file_ext, size=0
            )
            if is_new:
                self.stats["files"] += 1
            else:
                self.stats["skipped"] += 1

        self.stats["folders"] = len(folder_set)

    def scrape(self, keep_clone: bool = False):
        """
        執行完整的抓取流程

        Args:
            keep_clone: 是否保留 clone 的目錄（預設: False）
        """
        print("=" * 60)
        print("ESE Song Database Scraper V2 (Git Clone - Fastest)")
        print("支援智能去重和歌曲檔案關聯")
        print("=" * 60)
        print()

        # 初始化資料庫
        self.init_database()
        print()

        # Clone repository
        if not self.clone_repository():
            print("\n✗ 無法 clone repository，請檢查網路連接或 Git 安裝")
            return

        print()
        print("開始讀取 git 檔案清單（不下載檔案內容）...")
        print("-" * 60)

        # 從 git tree 讀取檔案清單建立資料庫
        self.build_from_git_tree()

        # 一次性提交所有變更（取代每筆 commit，大幅減少磁碟 fsync）
        self.conn.commit()

        print("-" * 60)
        print()

        # 顯示統計
        print("掃描完成!")
        print(f"✓ 總共找到 {self.stats['categories']} 個分類")
        print(f"✓ 總共找到 {self.stats['folders']} 個資料夾")
        print(f"✓ 新增 {self.stats['files']} 個檔案")
        print(f"⊘ 跳過 {self.stats['skipped']} 個已存在的檔案")
        print()

        # 資料庫統計
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM categories")
        cat_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM songs")
        song_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM song_files")
        file_count = cursor.fetchone()[0]

        print("資料庫統計:")
        print(f"✓ {cat_count} 個分類")
        print(f"✓ {song_count} 首歌曲")
        print(f"✓ {file_count} 個檔案")

        # 顯示平均每首歌有多少個檔案
        if song_count > 0:
            avg_files = file_count / song_count
            print(f"ℹ 平均每首歌有 {avg_files:.1f} 個檔案")

        print()
        print(f"資料庫位置: {os.path.abspath(self.db_path)}")

        # 清理 clone 的目錄
        if not keep_clone:
            print()
            print("正在清理 clone 的目錄...")
            try:
                shutil.rmtree(self.clone_dir)
                print(f"✓ 已刪除 {self.clone_dir}")
            except Exception as e:
                print(f"✗ 無法刪除 {self.clone_dir}: {e}")
        else:
            print()
            print(f"✓ Clone 的目錄保留在: {os.path.abspath(self.clone_dir)}")

        print("=" * 60)

    def close(self):
        """關閉資料庫連接"""
        if self.conn:
            self.conn.close()


def main():
    """主程式"""
    import argparse

    parser = argparse.ArgumentParser(
        description='ESE 歌曲資料庫爬蟲 V2（Git Clone 版本 - 最快，支援智能去重）'
    )
    parser.add_argument('--db', default='ese_songs.db',
                       help='資料庫路徑（預設: ese_songs.db）')
    parser.add_argument('--clone-dir', default='ESE_clone',
                       help='Clone 目錄（預設: ESE_clone）')
    parser.add_argument('--keep', action='store_true',
                       help='保留 clone 的目錄（預設會刪除）')

    args = parser.parse_args()

    scraper = ESEScraperGitV2(db_path=args.db, clone_dir=args.clone_dir)

    try:
        import time
        start_time = time.time()

        # 執行爬蟲
        scraper.scrape(keep_clone=args.keep)

        elapsed_time = time.time() - start_time
        print(f"\n總耗時: {elapsed_time:.2f} 秒")

    finally:
        scraper.close()


if __name__ == "__main__":
    main()
