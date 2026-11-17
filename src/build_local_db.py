"""
建立本地 TJA 檔案資料庫
掃描本地 TJA 檔案並建立包含日文標題的資料庫
"""

import sqlite3
import os
import sys
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
                level_easy INTEGER,
                level_normal INTEGER,
                level_hard INTEGER,
                level_oni INTEGER,
                level_ura INTEGER,
                file_path TEXT NOT NULL UNIQUE,
                file_name TEXT,
                directory TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 舊資料庫升級：補上難度欄位（已存在則略過）
        existing_cols = {r[1] for r in cursor.execute("PRAGMA table_info(local_songs)")}
        for col in ("level_easy", "level_normal", "level_hard", "level_oni", "level_ura"):
            if col not in existing_cols:
                cursor.execute(f"ALTER TABLE local_songs ADD COLUMN {col} INTEGER")

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
                    category = ?, bpm = ?, wave_file = ?,
                    level_easy = ?, level_normal = ?, level_hard = ?,
                    level_oni = ?, level_ura = ?,
                    file_name = ?, directory = ?
                WHERE file_path = ?
            """, (
                metadata.get('title'),
                metadata.get('titleja'),
                metadata.get('subtitle'),
                metadata.get('subtitleja'),
                metadata.get('category'),
                metadata.get('bpm'),
                metadata.get('wave'),
                metadata.get('level_easy'),
                metadata.get('level_normal'),
                metadata.get('level_hard'),
                metadata.get('level_oni'),
                metadata.get('level_ura'),
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
                 level_easy, level_normal, level_hard, level_oni, level_ura,
                 file_path, file_name, directory)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                metadata.get('title'),
                metadata.get('titleja'),
                metadata.get('subtitle'),
                metadata.get('subtitleja'),
                metadata.get('category'),
                metadata.get('bpm'),
                metadata.get('wave'),
                metadata.get('level_easy'),
                metadata.get('level_normal'),
                metadata.get('level_hard'),
                metadata.get('level_oni'),
                metadata.get('level_ura'),
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
    import time
    import requests
    import urllib.parse
    from concurrent.futures import ThreadPoolExecutor

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
    parser = TJAParser()
    sess = requests.Session()
    sess.headers["User-Agent"] = "ESEManager"

    db = LocalTJADatabase(db_path=local_db)
    db.init_database()

    # 增量：已解析過難度的 .tja 就略過，只抓還沒處理的（新歌）。
    # 以難度欄位為準（任一難度有值即代表處理過），這樣舊資料庫升級後會自動
    # 重抓一次補上難度/BPM，之後維持增量。
    existing = {fp for (fp,) in db.conn.execute(
        "SELECT file_path FROM local_songs WHERE "
        "level_easy IS NOT NULL OR level_normal IS NOT NULL OR level_hard IS NOT NULL "
        "OR level_oni IS NOT NULL OR level_ura IS NOT NULL")}
    todo = [r for r in rows if r[0] not in existing]
    print(f"資料庫已有日文標題 {len(existing)} 首；本次需抓取 {len(todo)} 首（總 {total}）")

    # 清除已不在歌曲庫（ese_songs.db）中的過期日文標題列，避免累積幽靈列
    # （與 ese_songs.db 對齊；重複的 file_name stem 會在 GUI 互相遮蔽，曾造成難度空白）。
    # 就算本次沒有新歌要抓，上游刪歌也要在此清掉，故放在 todo 判斷之前。
    def _prune_stale():
        current_paths = {r[0] for r in rows}
        if not current_paths:
            return
        cur = db.conn.cursor()
        cur.execute("CREATE TEMP TABLE IF NOT EXISTS _keep(fp TEXT PRIMARY KEY)")
        cur.execute("DELETE FROM _keep")
        cur.executemany("INSERT OR IGNORE INTO _keep(fp) VALUES(?)",
                        [(p,) for p in current_paths])
        cur.execute("DELETE FROM local_songs WHERE file_path NOT IN (SELECT fp FROM _keep)")
        pruned = cur.rowcount
        cur.execute("DROP TABLE _keep")
        db.conn.commit()
        if pruned:
            print(f"🧹 清除過期日文標題 {pruned} 首（歌曲庫已刪/改名）")

    _prune_stale()
    if not todo:
        print("✓ 日文標題已是最新，略過抓取")
        db.close()
        return
    print("-" * 60)

    # 下載連結是 file_path 的決定性衍生值；舊資料庫可能有 download_url 為空的列，
    # 缺就即時補上，避免解析日文標題時整首漏掉。
    from appconfig import ESE_RAW_BASE, live_url
    failures = []

    def fetch(row):
        file_path, url, filename, category = row
        if not url:
            url = ESE_RAW_BASE + urllib.parse.quote(file_path)
        try:
            r = None
            for attempt in range(3):
                try:
                    r = sess.get(live_url(url), timeout=30)
                    if r.status_code < 500 and r.status_code != 429:
                        break
                except (requests.ConnectionError, requests.Timeout):
                    if attempt == 2:
                        raise
                time.sleep(1 + attempt * 2)
            r.raise_for_status()
            text = TJAParser.decode_bytes(r.content)
            meta = parser.parse_text(text)
            for diff, lv in parser.parse_courses(text).items():
                meta[f"level_{diff}"] = lv
            meta["file_path"] = file_path
            meta["file_name"] = filename
            meta["directory"] = os.path.dirname(file_path)
            if category:
                meta["category"] = category
            return meta
        except Exception as e:
            failures.append(f"{file_path}: {e}")
            return None

    done = 0
    new_count = ja_count = 0
    todo_total = len(todo)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        for meta in ex.map(fetch, todo):
            done += 1
            if meta:
                db.insert_song(meta)
                new_count += 1
                if meta.get("titleja"):
                    ja_count += 1
            if done % 200 == 0:
                print(f"進度: {done}/{todo_total} ({done*100//todo_total}%)")

    db.conn.commit()   # 一次性提交
    sess.close()
    if failures:
        print(f"✗ {len(failures)} 個 .tja 下載失敗，例如: {failures[0]}")
    # Every fetch failing (or most of them) means no network or a broken host:
    # report it instead of claiming success with stale data.
    if failures and len(failures) >= max(1, todo_total // 2):
        db.close()
        raise RuntimeError(f"{len(failures)}/{todo_total} .tja downloads failed "
                           f"(network problem?): {failures[0]}")
    print("-" * 60)
    print(f"✓ 完成：本次新增 {new_count} 首，其中 {ja_count} 首有日文標題")
    db.show_stats()
    db.close()


# ============================================================ git-batched build
# Used by the GitHub Pages builder. Compared with build_from_remote (one HTTP
# request per .tja), this asks ESE's git server for all needed .tja blobs in a
# few batched requests, and only for charts whose content changed since the
# previous build (tracked by git blob sha), which is much lighter for ESE.

FETCH_BATCH = 2000          # object ids per `git fetch` request


def _git_env():
    # Never let git fetch missing objects one at a time behind our back
    # (honoured by git >= 2.45; older versions ignore it, and we only read
    # objects after checking they are present).
    return dict(os.environ, GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0",
                GIT_HTTP_LOW_SPEED_LIMIT="1000", GIT_HTTP_LOW_SPEED_TIME="60")


def _missing_blobs(git_exe, clone_dir, ref, wanted):
    """Which of `wanted` object ids are not in the local (partial) clone.
    `rev-list --missing=print` reports them without fetching anything."""
    import subprocess
    out = subprocess.run(
        [git_exe, "-C", clone_dir, "rev-list", "--objects", "--missing=print",
         "--no-object-names", ref],
        capture_output=True, text=True, env=_git_env(), timeout=600, check=True).stdout
    missing = {line[1:].strip() for line in out.splitlines() if line.startswith("?")}
    return [oid for oid in wanted if oid in missing]


def _fetch_blobs(git_exe, clone_dir, oids):
    """Fetch the given blob ids from origin in batches (one request each)."""
    import subprocess
    for i in range(0, len(oids), FETCH_BATCH):
        chunk = oids[i:i + FETCH_BATCH]
        print(f"git fetch: {len(chunk)} .tja blobs "
              f"(batch {i // FETCH_BATCH + 1}/{(len(oids) - 1) // FETCH_BATCH + 1})")
        subprocess.run(
            [git_exe, "-C", clone_dir, "-c", "fetch.negotiationAlgorithm=noop",
             "fetch", "--no-tags", "--no-write-fetch-head", "--recurse-submodules=no",
             "--filter=blob:none", "--stdin", "origin"],
            # bytes, not text: on Windows text mode would send "\r\n"
            input=("\n".join(chunk) + "\n").encode("ascii"), env=_git_env(),
            timeout=1800, check=True)


def _read_blobs(git_exe, clone_dir, oids):
    """Yield (oid, bytes) for objects already present locally."""
    import subprocess
    proc = subprocess.Popen([git_exe, "-C", clone_dir, "cat-file", "--batch"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            env=_git_env())
    try:
        for oid in oids:
            proc.stdin.write(oid.encode() + b"\n")
            proc.stdin.flush()
            header = proc.stdout.readline().decode().split()
            if len(header) != 3 or header[1] != "blob":
                raise RuntimeError(f"git cat-file: unexpected reply for {oid}: {header}")
            size = int(header[2])
            data = proc.stdout.read(size)
            proc.stdout.read(1)              # trailing newline
            yield oid, data
    finally:
        proc.stdin.close()
        proc.wait(timeout=60)


def build_from_git(song_db: str, local_db: str, clone_dir: str, git_exe: str = "git",
                   ref: str = "master"):
    """Build/refresh ese_local.db from the .tja files in a partial ESE clone.

    Incremental by content: a chart is (re)parsed only when its git blob sha
    differs from the one recorded in local_db. Missing blobs are fetched in
    batches; nothing is downloaded one file at a time.
    """
    if not os.path.exists(song_db):
        raise FileNotFoundError(f"song database not found: {song_db}")

    conn = sqlite3.connect(song_db)
    try:
        rows = conn.execute(
            "SELECT f.file_path, f.filename, c.name, f.blob_sha "
            "FROM song_files f "
            "LEFT JOIN songs s ON f.song_id = s.id "
            "LEFT JOIN categories c ON s.category_id = c.id "
            "WHERE f.file_type = '.tja'").fetchall()
    finally:
        conn.close()
    if any(not r[3] for r in rows):
        raise RuntimeError("song database has .tja rows without blob_sha; rebuild it first")

    db = LocalTJADatabase(db_path=local_db)
    db.init_database()
    cur = db.conn.cursor()
    if "blob_sha" not in {r[1] for r in cur.execute("PRAGMA table_info(local_songs)")}:
        cur.execute("ALTER TABLE local_songs ADD COLUMN blob_sha TEXT")

    # Drop rows for charts that no longer exist upstream.
    cur.execute("CREATE TEMP TABLE IF NOT EXISTS _keep(fp TEXT PRIMARY KEY)")
    cur.execute("DELETE FROM _keep")
    cur.executemany("INSERT OR IGNORE INTO _keep(fp) VALUES(?)", [(r[0],) for r in rows])
    cur.execute("DELETE FROM local_songs WHERE file_path NOT IN (SELECT fp FROM _keep)")
    pruned = cur.rowcount
    cur.execute("DROP TABLE _keep")
    db.conn.commit()
    if pruned:
        print(f"Pruned {pruned} charts no longer in ESE")

    known = {fp: sha for fp, sha in cur.execute(
        "SELECT file_path, blob_sha FROM local_songs WHERE blob_sha IS NOT NULL")}
    todo = [r for r in rows if known.get(r[0]) != r[3]]
    print(f"{len(rows)} charts; {len(todo)} new or changed since the last build")
    if not todo:
        db.close()
        return 0

    wanted = sorted({r[3] for r in todo})
    missing = _missing_blobs(git_exe, clone_dir, ref, wanted)
    if missing:
        _fetch_blobs(git_exe, clone_dir, missing)
        still = _missing_blobs(git_exe, clone_dir, ref, missing)
        if still:
            db.close()
            raise RuntimeError(f"{len(still)} .tja blobs could not be fetched, e.g. {still[0]}")
    else:
        print("All needed .tja blobs are already in the local clone")

    parser = TJAParser()
    by_sha = {}
    for r in todo:
        by_sha.setdefault(r[3], []).append(r)
    done = ja = 0
    for oid, data in _read_blobs(git_exe, clone_dir, wanted):
        text = TJAParser.decode_bytes(data)
        base = parser.parse_text(text)
        for diff, lv in parser.parse_courses(text).items():
            base[f"level_{diff}"] = lv
        for file_path, filename, category, sha in by_sha[oid]:
            meta = dict(base, file_path=file_path, file_name=filename,
                        directory=os.path.dirname(file_path))
            if category:
                meta["category"] = category
            db.insert_song(meta)
            cur.execute("UPDATE local_songs SET blob_sha = ? WHERE file_path = ?",
                        (sha, file_path))
            done += 1
            if meta.get("titleja"):
                ja += 1
    db.conn.commit()
    print(f"Parsed {done} charts ({ja} with Japanese titles)")
    db.close()
    return done


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
                       help='TJA 檔案所在目錄（本機掃描模式）')
    parser.add_argument('--db', default='ese_local.db',
                       help='資料庫路徑（預設: ese_local.db）')
    parser.add_argument('--remote', action='store_true',
                       help='從 ESE 直接抓 .tja 解析 TITLEJA（增量；需先有 ese_songs.db）')
    parser.add_argument('--song-db', default='ese_songs.db',
                       help='--remote 用的歌曲資料庫（預設: ese_songs.db）')

    args = parser.parse_args()

    # 遠端模式：直接從 ESE 抓 .tja 建日文標題（增量）
    if args.remote:
        build_from_remote(song_db=args.song_db, local_db=args.db)
        return

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
