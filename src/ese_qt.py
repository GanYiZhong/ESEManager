"""
ESE 歌曲管理器 - PySide6 高速版
- QTableView + 自訂 model：上千首歌瞬間顯示、虛擬捲動（無需分頁）
- 下載監控：整體進度 + 即時速度/ETA、每檔狀態、即時 log、失敗清單 + 一鍵重試
後端沿用 download_songs.SongDownloader（搜尋）與本地 ese_local.db（日文標題）。
"""

import os
import sys
import time
import sqlite3
import threading
import webbrowser
from concurrent.futures import ThreadPoolExecutor

import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from PySide6.QtCore import (Qt, QThread, Signal, QObject, QAbstractTableModel,
                            QModelIndex, QTimer, QSortFilterProxyModel, QProcess)
from PySide6.QtGui import QColor, QFont, QAction
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QTableView, QHeaderView, QSpinBox,
    QFileDialog, QPlainTextEdit, QProgressBar, QTabWidget, QListWidget,
    QListWidgetItem, QMessageBox, QSplitter, QAbstractItemView, QStyleFactory,
    QGroupBox, QDialog, QFormLayout, QColorDialog, QFrame, QScrollArea
)
import re

# 確保能 import 同目錄的 download_songs
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from download_songs import SongDownloader  # noqa: E402

# TOML
try:
    import tomllib
except ImportError:
    import tomli as tomllib
import tomli_w

CONFIG_FILE = "config.toml"

CATEGORY_NAMES = {
    "01 Pop": "Pop 流行音樂",
    "02 Anime": "Anime 動漫音樂",
    "03 Vocaloid": "Vocaloid 音樂",
    "04 Children and Folk": "Children 兒童音樂",
    "05 Variety": "Variety 綜合音樂",
    "06 Classical": "Classical 古典音樂",
    "07 Game Music": "Game Music 遊戲音樂",
    "09 Namco Original": "Namco 原創音樂",
    "08 Live Festival Mode": "Live Festival 模式",
    "10 Taiko Towers": "Taiko Towers",
    "11 Dan Dojo": "Dan Dojo 段位道場",
}
CATEGORY_COLORS = {
    "01 Pop": "#1E88E5", "02 Anime": "#FB8C00", "03 Vocaloid": "#AB47BC",
    "04 Children and Folk": "#EC407A", "05 Variety": "#66BB6A",
    "06 Classical": "#C9A227", "07 Game Music": "#7E57C2",
    "09 Namco Original": "#EF5350", "08 Live Festival Mode": "#26A69A",
    "10 Taiko Towers": "#8D6E63", "11 Dan Dojo": "#78909C",
}

TR = {
    "zh_TW": {
        "title": "🎵 ESEManager", "search": "搜尋", "show_all": "顯示全部",
        "clear": "清除", "ph": "搜尋歌曲名稱 (支援日文)...", "category": "分類",
        "all_cat": "全部分類", "official": "🌐 盅鼓官方網站", "check_missing": "🔍 檢查缺漏",
        "download": "⬇ 下載選中的歌曲", "sel_all": "全選", "desel_all": "取消",
        "selected": "已選擇 {n} 首", "dir": "下載目錄", "browse": "瀏覽", "workers": "並行數",
        "lang": "語言", "c_sel": "✓", "c_song": "歌曲名稱", "c_jp": "日文標題",
        "c_cat": "分類", "c_files": "檔案數", "monitor": "下載監控", "tab_prog": "進度",
        "tab_log": "Log", "tab_fail": "失敗清單", "overall": "整體進度", "retry": "🔁 重試失敗項目",
        "ready": "就緒", "total": "共 {n} 首歌曲", "f_file": "檔案", "f_song": "歌曲",
        "f_status": "狀態", "f_pct": "進度", "f_speed": "速度", "open_dir": "📂 開啟下載資料夾",
        "st_dl": "下載中", "st_done": "完成", "st_skip": "已存在", "st_fail": "失敗",
        "st_pause": "暫停", "pause": "⏸ 暫停", "resume": "▶ 繼續", "stop": "⏹ 停止",
        "paused_label": "已暫停",
        "done_msg": "下載完成！\n成功 {d}．跳過 {s}．失敗 {f}（共 {t} 檔）",
        "db_update": "🔄 更新資料庫", "db_building": "資料庫更新中…",
        "db_done": "資料庫已更新（歌曲清單 + 日文標題）！", "db_fail": "資料庫更新失敗：{e}",
        "db_confirm": "將從 ESE 更新資料庫：\n1. 歌曲清單（blobless，只抓檔名、不下載音檔）\n2. 日文標題（抓各 .tja 解析 TITLEJA，約 10MB）\n\n是否繼續？",
        "db_no_git_q": "未偵測到 git（更新歌曲清單需要）。\n是否自動下載可攜版 git（約 50MB，免安裝、免管理員）？\n\n選「否」則需自行安裝 git：https://git-scm.com/downloads",
        "db_no_git_fail": "沒有可用的 git，已取消更新。請安裝 git 後再試。",
        "lang_busy": "工作進行中，語言將於下次啟動時套用。",
        "boxdef_btn": "📦 box.def", "boxdef_title": "box.def 編輯器",
        "boxdef_load": "讀取", "boxdef_gen": "自動生成", "boxdef_save": "儲存",
        "boxdef_batch": "為所有子資料夾生成",
        "boxdef_saved": "已儲存：{p}", "boxdef_no_dir": "資料夾不存在",
        "boxdef_no_sub": "此資料夾沒有子資料夾",
        "boxdef_batch_q": "將為 {n} 個子資料夾建立 box.def（已存在的會略過），是否繼續？",
        "boxdef_batch_done": "完成：新建 {c} 個、略過 {s} 個（已存在）",
        "boxdef_pick": "選擇顏色",
    },
    "en": {
        "title": "🎵 ESEManager", "search": "Search", "show_all": "Show All",
        "clear": "Clear", "ph": "Search songs (Japanese supported)...", "category": "Category",
        "all_cat": "All Categories", "official": "🌐 Official Site", "check_missing": "🔍 Check Missing",
        "download": "⬇ Download Selected", "sel_all": "Select All", "desel_all": "Deselect",
        "selected": "{n} selected", "dir": "Download Dir", "browse": "Browse", "workers": "Workers",
        "lang": "Language", "c_sel": "✓", "c_song": "Song", "c_jp": "Japanese",
        "c_cat": "Category", "c_files": "Files", "monitor": "Download Monitor", "tab_prog": "Progress",
        "tab_log": "Log", "tab_fail": "Failed", "overall": "Overall", "retry": "🔁 Retry Failed",
        "ready": "Ready", "total": "{n} songs", "f_file": "File", "f_song": "Song",
        "f_status": "Status", "f_pct": "Progress", "f_speed": "Speed", "open_dir": "📂 Open Folder",
        "st_dl": "downloading", "st_done": "done", "st_skip": "skipped", "st_fail": "failed",
        "done_msg": "Done!\nOK {d} · skipped {s} · failed {f} (of {t})",
        "st_pause": "paused", "pause": "⏸ Pause", "resume": "▶ Resume", "stop": "⏹ Stop",
        "paused_label": "Paused",
        "db_update": "🔄 Update DB", "db_building": "Updating database…",
        "db_done": "Database updated (song list + Japanese titles)!",
        "db_fail": "Database update failed: {e}",
        "db_confirm": "Update databases from ESE:\n1. Song list (blobless — file list only, no audio)\n2. Japanese titles (parse TITLEJA from each .tja, ~10MB)\n\nContinue?",
        "db_no_git_q": "Git not found (needed to fetch the song list).\nDownload a portable Git automatically (~50MB, no install, no admin)?\n\nChoose No to install Git yourself: https://git-scm.com/downloads",
        "db_no_git_fail": "No Git available; update cancelled. Install Git and try again.",
        "lang_busy": "A task is running; the language will apply on next launch.",
        "boxdef_btn": "📦 box.def", "boxdef_title": "box.def editor",
        "boxdef_load": "Load", "boxdef_gen": "Generate", "boxdef_save": "Save",
        "boxdef_batch": "Generate for all subfolders",
        "boxdef_saved": "Saved: {p}", "boxdef_no_dir": "Folder does not exist",
        "boxdef_no_sub": "No subfolders in this folder",
        "boxdef_batch_q": "Create box.def for {n} subfolders (existing ones are skipped). Continue?",
        "boxdef_batch_done": "Done: created {c}, skipped {s} (existing)",
        "boxdef_pick": "Pick color",
    },
    "ja": {
        "title": "🎵 ESEManager", "search": "検索", "show_all": "すべて表示",
        "clear": "クリア", "ph": "楽曲名を検索（日本語対応）...", "category": "カテゴリー",
        "all_cat": "すべて", "official": "🌐 公式サイト", "check_missing": "🔍 不足チェック",
        "download": "⬇ 選択をダウンロード", "sel_all": "全選択", "desel_all": "解除",
        "selected": "{n} 曲選択", "dir": "保存先", "browse": "参照", "workers": "並列数",
        "lang": "言語", "c_sel": "✓", "c_song": "楽曲名", "c_jp": "日本語",
        "c_cat": "カテゴリー", "c_files": "ファイル", "monitor": "ダウンロード状況", "tab_prog": "進捗",
        "tab_log": "ログ", "tab_fail": "失敗", "overall": "全体", "retry": "🔁 失敗を再試行",
        "ready": "準備完了", "total": "{n} 曲", "f_file": "ファイル", "f_song": "楽曲",
        "f_status": "状態", "f_pct": "進捗", "f_speed": "速度", "open_dir": "📂 フォルダを開く",
        "st_dl": "DL中", "st_done": "完了", "st_skip": "既存", "st_fail": "失敗",
        "done_msg": "完了！\n成功 {d}・スキップ {s}・失敗 {f}（計 {t}）",
        "st_pause": "一時停止", "pause": "⏸ 一時停止", "resume": "▶ 再開", "stop": "⏹ 停止",
        "paused_label": "一時停止中",
        "db_update": "🔄 データベース更新", "db_building": "データベース更新中…",
        "db_done": "データベースを更新しました（曲リスト＋日本語タイトル）！",
        "db_fail": "データベース更新に失敗: {e}",
        "db_confirm": "ESE からデータベースを更新します：\n1. 曲リスト（blobless・一覧のみ／音声なし）\n2. 日本語タイトル（各 .tja の TITLEJA を解析、約10MB）\n\n続行しますか？",
        "db_no_git_q": "Git が見つかりません（曲リスト取得に必要）。\nポータブル版 Git を自動ダウンロードしますか（約50MB、インストール不要・管理者不要）？\n\n「いいえ」で手動インストール：https://git-scm.com/downloads",
        "db_no_git_fail": "利用可能な Git がありません。更新を中止しました。",
        "lang_busy": "処理の実行中です。言語は次回起動時に適用されます。",
        "boxdef_btn": "📦 box.def", "boxdef_title": "box.def エディター",
        "boxdef_load": "読み込み", "boxdef_gen": "自動生成", "boxdef_save": "保存",
        "boxdef_batch": "全サブフォルダに生成",
        "boxdef_saved": "保存しました：{p}", "boxdef_no_dir": "フォルダが存在しません",
        "boxdef_no_sub": "サブフォルダがありません",
        "boxdef_batch_q": "{n} 個のサブフォルダに box.def を作成します（既存はスキップ）。続行しますか？",
        "boxdef_batch_done": "完了：作成 {c}、スキップ {s}（既存）",
        "boxdef_pick": "色を選択",
    },
}


def detect_system_lang():
    """偵測系統語言 → 'zh_TW' / 'ja' / 'en'（預設 en）。"""
    code = ""
    try:
        if sys.platform == "win32":
            import ctypes
            buf = ctypes.create_unicode_buffer(85)
            if ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, 85):
                code = buf.value          # 例如 "zh-TW" / "ja-JP" / "en-US"
    except Exception:
        pass
    if not code:
        try:
            import locale
            code = locale.getdefaultlocale()[0] or ""
        except Exception:
            code = ""
    code = code.replace("_", "-").lower()
    if code.startswith("ja"):
        return "ja"
    if code.startswith("zh"):
        return "zh_TW"
    return "en"

DB_PATH = "ese_songs.db"
LOCAL_DB_PATH = "ese_local.db"


def human_speed(mbps):
    if mbps <= 0:
        return "—"
    if mbps < 1:
        return f"{mbps*1024:.0f} KB/s"
    return f"{mbps:.2f} MB/s"


def human_eta(sec):
    if sec is None or sec <= 0 or sec == float("inf"):
        return "—"
    sec = int(sec)
    if sec < 60:
        return f"{sec}s"
    m, s = divmod(sec, 60)
    if m < 60:
        return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m"


# ---------------------------------------------------------------- 歌曲清單 model
class SongModel(QAbstractTableModel):
    COLS = ["c_sel", "c_song", "c_jp", "c_cat", "c_files"]

    def __init__(self, tr, jp_map):
        super().__init__()
        self.tr = tr
        self.jp_map = jp_map
        self.songs = []
        self.checked = set()

    def set_songs(self, songs):
        self.beginResetModel()
        self.songs = songs
        self.checked = set()
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self.songs)

    def columnCount(self, parent=QModelIndex()):
        return len(self.COLS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.tr(self.COLS[section])
        return None

    def flags(self, index):
        f = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if index.column() == 0:
            f |= Qt.ItemIsUserCheckable
        return f

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row, col = index.row(), index.column()
        song = self.songs[row]
        if col == 0:
            if role == Qt.CheckStateRole:
                return Qt.Checked if row in self.checked else Qt.Unchecked
            return None
        if role == Qt.DisplayRole:
            if col == 1:
                return song["song_name"]
            if col == 2:
                return self.jp_map.get(song["song_name"], "")
            if col == 3:
                return CATEGORY_NAMES.get(song["category"], song["category"])
            if col == 4:
                return str(len(song["files"]))
        if role == Qt.ForegroundRole and col == 3:
            c = CATEGORY_COLORS.get(song["category"])
            if c:
                return QColor(c)
        if role == Qt.TextAlignmentRole and col == 4:
            return int(Qt.AlignCenter)
        return None

    def setData(self, index, value, role=Qt.EditRole):
        if index.column() == 0 and role == Qt.CheckStateRole:
            row = index.row()
            if Qt.CheckState(value) == Qt.Checked:
                self.checked.add(row)
            else:
                self.checked.discard(row)
            self.dataChanged.emit(index, index, [Qt.CheckStateRole])
            return True
        return False

    def set_all(self, checked):
        self.checked = set(range(len(self.songs))) if checked else set()
        if self.songs:
            self.dataChanged.emit(self.index(0, 0),
                                  self.index(len(self.songs) - 1, 0),
                                  [Qt.CheckStateRole])

    def selected_songs(self):
        return [self.songs[i] for i in sorted(self.checked)]


# ------------------------------------------------------------- 下載清單 model
class DownloadModel(QAbstractTableModel):
    COLS = ["f_file", "f_song", "f_status", "f_pct", "f_speed"]
    STATUS_COLOR = {"downloading": "#42A5F5", "done": "#66BB6A",
                    "skipped": "#9E9E9E", "failed": "#EF5350", "paused": "#FFA726"}

    def __init__(self, tr):
        super().__init__()
        self.tr = tr
        self.rows = []          # [filename, song, status, pct, speed]
        self.index_of = {}      # file_path -> row

    def load(self, files):
        self.beginResetModel()
        self.rows = []
        self.index_of = {}
        for song, f in files:
            self.index_of[f["file_path"]] = len(self.rows)
            self.rows.append([f["filename"], song["song_name"], "", 0.0, 0.0])
        self.endResetModel()

    def update(self, file_path, status, pct, speed):
        r = self.index_of.get(file_path)
        if r is None:
            return
        self.rows[r][2] = status
        self.rows[r][3] = pct
        self.rows[r][4] = speed
        self.dataChanged.emit(self.index(r, 0), self.index(r, 4))

    def rowCount(self, parent=QModelIndex()):
        return len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return len(self.COLS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.tr(self.COLS[section])
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row, col = index.row(), index.column()
        fn, song, status, pct, speed = self.rows[row]
        if role == Qt.DisplayRole:
            if col == 0:
                return fn
            if col == 1:
                return song
            if col == 2:
                return self.tr({"downloading": "st_dl", "done": "st_done",
                                "skipped": "st_skip", "failed": "st_fail",
                                "paused": "st_pause"}.get(status, "") or "")
            if col == 3:
                return f"{pct:.0f}%" if status in ("downloading", "done") else ""
            if col == 4:
                return human_speed(speed) if status == "downloading" else ""
        if role == Qt.ForegroundRole and col == 2:
            c = self.STATUS_COLOR.get(status)
            if c:
                return QColor(c)
        return None


# ---------------------------------------------------------------- 搜尋執行緒
class SearchThread(QThread):
    done = Signal(object)
    fail = Signal(str)

    def __init__(self, keyword, category, has_local):
        super().__init__()
        self.keyword = keyword
        self.category = category
        self.has_local = has_local

    def run(self):
        try:
            d = SongDownloader(db_path=DB_PATH)
            songs = d.search_songs(keyword=self.keyword or None, category=self.category)
            # 日文搜尋：關鍵字含日文 → 從本地庫找對應英文標題，一次 OR 查詢補上
            if self.keyword and self.has_local:
                if any('぀' <= c <= 'ヿ' or '一' <= c <= '鿿' for c in self.keyword):
                    conn = sqlite3.connect(LOCAL_DB_PATH)
                    cur = conn.cursor()
                    cur.execute("SELECT title FROM local_songs WHERE title_ja LIKE ?",
                                (f"%{self.keyword}%",))
                    titles = [r[0] for r in cur.fetchall() if r[0]]
                    conn.close()
                    if titles:
                        extra = d.search_songs(keywords=titles, category=self.category)
                        seen = {(s["song_name"], s["category"]) for s in songs}
                        for s in extra:
                            k = (s["song_name"], s["category"])
                            if k not in seen:
                                seen.add(k)
                                songs.append(s)
            d.close()
            # 過濾 box.def，只留有檔案的歌
            out = []
            for s in songs:
                s["files"] = [f for f in s["files"] if f["filename"].lower() != "box.def"]
                if s["files"]:
                    out.append(s)
            self.done.emit(out)
        except Exception as e:
            self.fail.emit(str(e))


# ---------------------------------------------------------------- 下載執行緒
# 設計：工作執行緒「不」對每個 chunk 發訊號（下載全部 = 數千檔 × 多並行，會
# 用跨執行緒訊號灌爆主執行緒事件佇列導致卡死）。改成把進度寫進共用記憶體，
# 主執行緒用 QTimer 每 ~200ms 拉一次（snapshot）統一刷新 UI。
class DownloadThread(QThread):
    log = Signal(str)
    finished_all = Signal(int, int, int, int)      # downloaded, skipped, failed, total

    def __init__(self, files, download_dir, workers):
        super().__init__()
        self.files = files
        self.download_dir = download_dir
        self.workers = max(1, workers)
        self._stop = False
        self._pause = threading.Event()
        self._pause.set()         # set = 執行中；clear = 暫停
        self.failed = []          # [(song, file_info)]
        self._lock = threading.Lock()
        self._dirty = {}          # file_path -> (status, pct, speed)  自上次拉取後變更
        self.total = len(files)
        self.done = 0
        self.dl = self.skip = self.fail = 0
        self.bytes_total = 0
        self.t0 = time.time()

    def stop(self):
        self._stop = True
        self._pause.set()         # 喚醒被暫停的工作執行緒，讓它們結束

    def pause(self):
        self._pause.clear()

    def resume(self):
        self._pause.set()

    def is_paused(self):
        return not self._pause.is_set()

    def snapshot(self):
        """主執行緒呼叫：原子取出計數與變更列，並清空 dirty。"""
        with self._lock:
            el = time.time() - self.t0
            spd = (self.bytes_total / 1024 / 1024) / el if el > 0 else 0
            eta = (self.total - self.done) / (self.done / el) if self.done > 0 and el > 0 else 0
            dirty = self._dirty
            self._dirty = {}
            return (self.done, self.total, spd, eta, dirty)

    def _mark(self, file_path, status, pct, speed):
        with self._lock:
            self._dirty[file_path] = (status, pct, speed)

    def run(self):
        sess = requests.Session()
        sess.headers["User-Agent"] = "ESEManager"

        def worker(item):
            song, f = item
            self._pause.wait()        # 暫停時在此等待（檔案開始前）
            if self._stop:
                return
            save_path = os.path.join(self.download_dir, f["file_path"])
            disp = f["filename"]
            if os.path.exists(save_path):
                with self._lock:
                    self.done += 1
                    self.skip += 1
                self._mark(f["file_path"], "skipped", 100.0, 0.0)
                return
            try:
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                r = sess.get(f["download_url"], stream=True, timeout=60, verify=False)
                r.raise_for_status()
                clen = int(r.headers.get("content-length", 0)) or 0
                got = 0
                ft0 = time.time()
                last = 0.0
                with open(save_path, "wb") as out:
                    for chunk in r.iter_content(chunk_size=65536):
                        if self._stop:
                            raise Exception("已取消")
                        if not self._pause.is_set():        # 下載中途被暫停
                            self._mark(f["file_path"], "paused", 0.0, 0.0)
                            self._pause.wait()
                            if self._stop:
                                raise Exception("已取消")
                        if not chunk:
                            continue
                        out.write(chunk)
                        got += len(chunk)
                        with self._lock:
                            self.bytes_total += len(chunk)
                        now = time.time()
                        if now - last >= 0.2:          # 每檔最多 5 次/秒寫入狀態
                            last = now
                            fe = now - ft0
                            spd = (got / 1024 / 1024) / fe if fe > 0 else 0
                            pct = (got / clen * 100) if clen else 50.0
                            self._mark(f["file_path"], "downloading", pct, spd)
                with self._lock:
                    self.done += 1
                    self.dl += 1
                self._mark(f["file_path"], "done", 100.0, 0.0)
                self.log.emit(f"✓ {disp} ({got/1024/1024:.2f} MB)")
            except Exception as e:
                if os.path.exists(save_path):
                    try:
                        os.remove(save_path)
                    except OSError:
                        pass
                with self._lock:
                    self.done += 1
                    self.fail += 1
                    self.failed.append((song, f))
                self._mark(f["file_path"], "failed", 0.0, 0.0)
                self.log.emit(f"✗ 失敗: {disp} — {e}")

        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            list(ex.map(worker, self.files))
        self.finished_all.emit(self.dl, self.skip, self.fail, self.total)


# ------------------------------------------------------- 資料庫建立執行緒
class _EmitStream:
    """把寫入導向 Qt 訊號（用來擷取 scraper 的 print 輸出到 GUI log）。"""
    def __init__(self, sig):
        self._sig = sig
        self._buf = ""

    def write(self, text):
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line.strip():
                self._sig.emit(line.rstrip())

    def flush(self):
        if self._buf.strip():
            self._sig.emit(self._buf.rstrip())
        self._buf = ""


class DBBuildThread(QThread):
    """一鍵更新資料庫：blobless 重建 ese_songs.db，再從 ESE 抓 .tja 解析 TITLEJA 建日文標題。"""
    log = Signal(str)
    done = Signal(bool, str)   # ok, info("ok"/"NOGIT"/錯誤訊息)

    def __init__(self, git_exe, download_git=False):
        super().__init__()
        self.git_exe = git_exe
        self.download_git = download_git

    def run(self):
        import contextlib
        stream = _EmitStream(self.log)
        try:
            with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
                from ese_scraper_git_v2 import ESEScraperGitV2, download_portable_git
                import build_local_db

                git_exe = self.git_exe
                if not git_exe and self.download_git:
                    git_exe = download_portable_git()
                if not git_exe:
                    stream.flush()
                    self.done.emit(False, "NOGIT")
                    return

                print("=== 步驟 1/2：更新歌曲清單資料庫（blobless）===")
                s = ESEScraperGitV2(db_path=DB_PATH, clone_dir="ESE_clone", git_exe=git_exe)
                s.scrape(keep_clone=True)
                s.close()

                print("\n=== 步驟 2/2：從 ESE 抓取日文標題 (TITLEJA) ===")
                build_local_db.build_from_remote(song_db=DB_PATH, local_db=LOCAL_DB_PATH,
                                                 workers=12)
                stream.flush()
            self.done.emit(True, "ok")
        except Exception as e:
            try:
                stream.flush()
            except Exception:
                pass
            self.done.emit(False, str(e))


def _hex_to_rgb(h):
    h = (h or "").lstrip("#")
    if len(h) == 6:
        try:
            return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        except ValueError:
            pass
    return 68, 68, 68


def _norm_hex(s):
    """正規化成 6 位 HEX（不含 #）；無效回空字串。"""
    s = (s or "").strip().lstrip("#")
    if len(s) == 6:
        try:
            int(s, 16)
            return s.upper()
        except ValueError:
            pass
    return ""


def _clean_name(folder_name):
    """去掉資料夾名前綴序號，如 '01-J-POP'->'J-POP'、'02-アニメ'->'アニメ'、'01 Pop'->'Pop'。"""
    return re.sub(r"^\s*\d+\s*[-_.]?\s*", "", folder_name or "").strip() or (folder_name or "")


# 常見分類（含日文分類名）對應底色，供範本自動上色
GENRE_COLORS = {
    "J-POP": "1E88E5", "アニメ": "FB8C00", "ボーカロイド": "00B5AD",
    "ゲームミュージック": "7E57C2", "バラエティ": "66BB6A",
    "クラシック": "C9A227", "ナムコオリジナル": "EF5350", "キッズ": "EC407A",
}


def _cat_color(folder_name):
    """取分類底色 HEX6（全名 → 去序號 → 日文分類名），預設 444444。"""
    clean = _clean_name(folder_name)
    c = CATEGORY_COLORS.get(folder_name) or CATEGORY_COLORS.get(clean)
    if c:
        return c.lstrip("#").upper()
    return GENRE_COLORS.get(clean, "444444")


def make_boxdef(folder_name):
    """依資料夾名稱產生 box.def 範本（OpenTaiko 格式，顏色含 #，供 ColorTranslator 解析）。"""
    name = _clean_name(folder_name)
    title = CATEGORY_NAMES.get(folder_name, name)
    hex6 = _cat_color(folder_name)
    return (f"#TITLE:{title}\n"
            f"#GENRE:{name}\n"
            f"#BGCOLOR:#{hex6}\n"
            f"#BOXCOLOR:#{hex6}\n")


def _read_text(path):
    with open(path, "rb") as f:
        data = f.read()
    for enc in ("utf-8-sig", "utf-8", "shift-jis", "cp932", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")


# ------------------------------------------------------------- box.def 編輯器
# OpenTaiko box.def 圖形化編輯器（規格依原始碼 CBoxDef.cs）：
#   #TITLE / #TITLE<LANG>（多語言）/ #GENRE / #BGCOLOR / #BOXCOLOR /
#   #FORECOLOR / #BACKCOLOR（顏色值經 ColorTranslator 解析，需含 #）/
#   #BGTYPE / #BOXTYPE / #BOXCHARA / #SELECTBG / #SCENEPRESET / #BOXEXPLANATION1-3
BOXDEF_LANGS = [("", "#TITLE"), ("EN", "#TITLEEN"), ("JA", "#TITLEJA"),
                ("CN", "#TITLECN"), ("TW", "#TITLETW"), ("KO", "#TITLEKO")]
BOXDEF_LANG_LABEL = {"": "Default", "EN": "English", "JA": "日本語",
                     "CN": "简体中文", "TW": "繁體中文", "KO": "한국어"}
BOXDEF_COLORS = ["BGCOLOR", "BOXCOLOR", "FORECOLOR", "BACKCOLOR"]
BOXDEF_TEXTS = ["BGTYPE", "BOXTYPE", "BOXCHARA", "SELECTBG", "SCENEPRESET"]
BOXDEF_GENRES = ["J-POP", "アニメ", "ボーカロイド", "キッズ", "ゲームミュージック",
                 "バラエティ", "クラシック", "ナムコオリジナル"]


class BoxDefDialog(QDialog):
    """圖形化編輯 box.def：多語言標題 + 顏色選取 + 即時預覽（OpenTaiko 格式）。"""

    def __init__(self, parent, default_dir, tr):
        super().__init__(parent)
        self.tr = tr
        self.setWindowTitle(tr("boxdef_title"))
        self.resize(600, 720)
        self.extra = []   # 保留無法辨識的行，存檔時原樣寫回
        outer = QVBoxLayout(self)

        # 資料夾列
        fr = QHBoxLayout()
        self.dir_edit = QLineEdit(default_dir)
        browse = QPushButton(tr("browse"))
        browse.clicked.connect(self.browse)
        load = QPushButton(tr("boxdef_load"))
        load.clicked.connect(self.load)
        fr.addWidget(QLabel("📁"))
        fr.addWidget(self.dir_edit, 1)
        fr.addWidget(browse)
        fr.addWidget(load)
        outer.addLayout(fr)

        # 即時預覽
        self.preview = QLabel()
        self.preview.setMinimumHeight(64)
        self.preview.setAlignment(Qt.AlignCenter)
        outer.addWidget(self.preview)

        # 可捲動表單
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        form = QFormLayout(body)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        # 多語言標題
        self.title_edits = {}
        for code, key in BOXDEF_LANGS:
            e = QLineEdit()
            e.textChanged.connect(self._update_preview)
            self.title_edits[code] = e
            form.addRow("%s (%s)" % (key, BOXDEF_LANG_LABEL[code]), e)

        # 分類（可編輯下拉）
        self.genre = QComboBox()
        self.genre.setEditable(True)
        self.genre.addItems([""] + BOXDEF_GENRES)
        self.genre.editTextChanged.connect(self._update_preview)
        form.addRow("#GENRE", self.genre)

        # 顏色（HEX + 調色盤 + 色塊）
        self.color_edits = {}
        for ck in BOXDEF_COLORS:
            edit, row = self._color_field()
            self.color_edits[ck] = edit
            form.addRow("#" + ck, row)

        # 其他文字欄位
        self.text_edits = {}
        for tk in BOXDEF_TEXTS:
            e = QLineEdit()
            self.text_edits[tk] = e
            form.addRow("#" + tk, e)

        # 說明（3 行）
        self.exp_edits = []
        for i in range(3):
            e = QLineEdit()
            self.exp_edits.append(e)
            form.addRow("#BOXEXPLANATION%d" % (i + 1), e)

        # 按鈕列
        br = QHBoxLayout()
        gen = QPushButton(tr("boxdef_gen"))
        gen.clicked.connect(self.generate)
        save = QPushButton(tr("boxdef_save"))
        save.clicked.connect(self.save)
        batch = QPushButton(tr("boxdef_batch"))
        batch.clicked.connect(self.batch)
        br.addWidget(gen)
        br.addWidget(save)
        br.addStretch()
        br.addWidget(batch)
        outer.addLayout(br)

        self.load()

    def _color_field(self):
        """一組顏色欄位：HEX 輸入 + 調色盤按鈕 + 色塊。回傳 (edit, row_widget)。"""
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        edit = QLineEdit()
        edit.setMaxLength(7)
        edit.setFixedWidth(90)
        edit.setPlaceholderText("RRGGBB")
        btn = QPushButton("🎨")
        btn.setFixedWidth(40)
        btn.setToolTip(self.tr("boxdef_pick"))
        swatch = QFrame()
        swatch.setFixedSize(28, 24)

        def pick():
            cur = _norm_hex(edit.text())
            init = QColor("#" + cur) if cur else QColor("#444444")
            c = QColorDialog.getColor(init, self, self.tr("boxdef_pick"))
            if c.isValid():
                edit.setText(c.name().lstrip("#").upper())

        def upd():
            hx = _norm_hex(edit.text())
            swatch.setStyleSheet(("background-color:#%s;border:1px solid #888;" % hx) if hx
                                 else "background:transparent;border:1px solid #888;")
            self._update_preview()

        btn.clicked.connect(pick)
        edit.textChanged.connect(upd)
        h.addWidget(edit)
        h.addWidget(btn)
        h.addWidget(swatch)
        h.addStretch()
        return edit, w

    def _update_preview(self):
        hx = _norm_hex(self.color_edits["BGCOLOR"].text()) or "333333"
        r, g, b = _hex_to_rgb("#" + hx)
        fg = "#000000" if (r * 0.299 + g * 0.587 + b * 0.114) > 150 else "#FFFFFF"
        title = self.title_edits[""].text() or "(title)"
        genre = self.genre.currentText().strip()
        self.preview.setText(title + (("\n" + genre) if genre else ""))
        self.preview.setStyleSheet(
            "QLabel{background:#%s;color:%s;border-radius:8px;"
            "font-size:17px;font-weight:bold;}" % (hx, fg))

    def _path(self):
        return os.path.join(self.dir_edit.text(), "box.def")

    def browse(self):
        d = QFileDialog.getExistingDirectory(self, self.tr("browse"), self.dir_edit.text())
        if d:
            self.dir_edit.setText(d)
            self.load()

    def _clear(self):
        for e in self.title_edits.values():
            e.setText("")
        self.genre.setEditText("")
        for e in self.color_edits.values():
            e.setText("")
        for e in self.text_edits.values():
            e.setText("")
        for e in self.exp_edits:
            e.setText("")
        self.extra = []

    def _fill_template(self):
        name = os.path.basename(self.dir_edit.text().rstrip("/\\"))
        clean = _clean_name(name)
        self.title_edits[""].setText(CATEGORY_NAMES.get(name, clean))
        self.genre.setEditText(clean)
        hx = _cat_color(name)
        self.color_edits["BGCOLOR"].setText(hx)
        self.color_edits["BOXCOLOR"].setText(hx)

    def load(self):
        self._clear()
        p = self._path()
        if not os.path.exists(p):
            self._fill_template()
            self._update_preview()
            return
        try:
            text = _read_text(p)
        except Exception as e:
            text = ""
            print("boxdef load:", e)
        for line in text.splitlines():
            s = line.strip()
            if not s:
                continue
            if not (s.startswith("#") and ":" in s):
                self.extra.append(line)
                continue
            key, val = s[1:].split(":", 1)
            key = key.strip().upper()
            val = val.strip()
            if key == "TITLE":
                self.title_edits[""].setText(val)
            elif key.startswith("TITLE") and key[5:] in self.title_edits:
                self.title_edits[key[5:]].setText(val)
            elif key == "GENRE":
                self.genre.setEditText(val)
            elif key in self.color_edits:
                self.color_edits[key].setText(_norm_hex(val))
            elif key in self.text_edits:
                self.text_edits[key].setText(val)
            elif key in ("BOXEXPLANATION1", "BOXEXPLANATION2", "BOXEXPLANATION3"):
                self.exp_edits[int(key[-1]) - 1].setText(val)
            else:
                self.extra.append(line)
        self._update_preview()

    def generate(self):
        self._fill_template()
        self._update_preview()

    def _to_text(self):
        lines = []
        for code, key in BOXDEF_LANGS:
            v = self.title_edits[code].text().strip()
            if v:
                lines.append("%s:%s" % (key, v))
        g = self.genre.currentText().strip()
        if g:
            lines.append("#GENRE:" + g)
        for ck in BOXDEF_COLORS:
            hx = _norm_hex(self.color_edits[ck].text())
            if hx:
                lines.append("#%s:#%s" % (ck, hx))
        for tk in BOXDEF_TEXTS:
            v = self.text_edits[tk].text().strip()
            if v:
                lines.append("#%s:%s" % (tk, v))
        for i, e in enumerate(self.exp_edits):
            v = e.text().strip()
            if v:
                lines.append("#BOXEXPLANATION%d:%s" % (i + 1, v))
        lines += [ln for ln in self.extra if ln.strip()]
        return "\n".join(lines) + "\n"

    def save(self):
        d = self.dir_edit.text()
        if not os.path.isdir(d):
            QMessageBox.warning(self, self.tr("boxdef_title"), self.tr("boxdef_no_dir"))
            return
        try:
            with open(self._path(), "w", encoding="utf-8") as f:
                f.write(self._to_text())
            QMessageBox.information(self, self.tr("boxdef_title"),
                                    self.tr("boxdef_saved", p=self._path()))
        except Exception as e:
            QMessageBox.critical(self, self.tr("boxdef_title"), str(e))

    def batch(self):
        base = self.dir_edit.text()
        if not os.path.isdir(base):
            QMessageBox.warning(self, self.tr("boxdef_title"), self.tr("boxdef_no_dir"))
            return
        subs = sorted(d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d)))
        if not subs:
            QMessageBox.information(self, self.tr("boxdef_title"), self.tr("boxdef_no_sub"))
            return
        if QMessageBox.question(self, self.tr("boxdef_title"),
                                self.tr("boxdef_batch_q", n=len(subs))) != QMessageBox.Yes:
            return
        created = skipped = 0
        for sub in subs:
            p = os.path.join(base, sub, "box.def")
            if os.path.exists(p):
                skipped += 1
                continue
            try:
                with open(p, "w", encoding="utf-8") as f:
                    f.write(make_boxdef(sub))
                created += 1
            except Exception as e:
                print("boxdef batch:", e)
        QMessageBox.information(self, self.tr("boxdef_title"),
                               self.tr("boxdef_batch_done", c=created, s=skipped))


# ---------------------------------------------------------------- 主視窗
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = self.load_config()
        self.download_dir = self.config.get("download", {}).get("directory", "Downloads")
        # ui_language 偏好可為 "auto"（依系統語言）或固定的 zh_TW/en/ja；新安裝預設 auto
        self.lang_pref = self.config.get("display", {}).get("ui_language", "auto")
        self.lang = detect_system_lang() if self.lang_pref == "auto" else self.lang_pref
        self.has_local = os.path.exists(LOCAL_DB_PATH)
        self.jp_map = self.load_jp_map()
        self.dl_thread = None

        self.song_model = SongModel(self.tr, self.jp_map)
        self.dl_model = DownloadModel(self.tr)

        self.build_ui()
        self.load_categories()
        QTimer.singleShot(1200, self.check_db_update)

    # ---- i18n / config
    def tr(self, key, **kw):
        s = TR.get(self.lang, TR["zh_TW"]).get(key, TR["zh_TW"].get(key, key))
        return s.format(**kw) if kw else s

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "rb") as f:
                    return tomllib.load(f)
            except Exception:
                pass
        return {"download": {"directory": "Downloads", "workers": 5},
                "display": {"page_size": 20, "ui_language": "auto"}}

    def save_config(self):
        cfg = {
            "download": {"directory": self.dir_edit.text(),
                         "workers": self.workers_spin.value()},
            "display": {"page_size": 20, "ui_language": self.lang_pref},
        }
        try:
            with open(CONFIG_FILE, "wb") as f:
                tomli_w.dump(cfg, f)
        except Exception as e:
            print("save_config:", e)

    def load_jp_map(self):
        # song_name 其實是 .tja 檔名去副檔名，所以用 file_name 對應命中率最高(~93%)，
        # 再用 title 當備援補上剩餘的（單用 title 只有 ~72%）。
        m = {}
        if self.has_local:
            try:
                conn = sqlite3.connect(LOCAL_DB_PATH)
                rows = conn.execute(
                    "SELECT title, file_name, title_ja FROM local_songs "
                    "WHERE title_ja IS NOT NULL AND title_ja != ''").fetchall()
                conn.close()
                for title, file_name, ja in rows:      # 先放檔名（主鍵）
                    if file_name and ja:
                        m.setdefault(os.path.splitext(file_name)[0], ja)
                for title, file_name, ja in rows:      # 再用 title 補洞（不覆蓋）
                    if title and ja:
                        m.setdefault(title, ja)
            except Exception as e:
                print("load_jp_map:", e)
        return m

    # ---- UI
    def build_ui(self):
        self.setWindowTitle(self.tr("title"))
        self.resize(1280, 860)
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        # top bar
        top = QHBoxLayout()
        title = QLabel(self.tr("title"))
        tf = QFont(); tf.setPointSize(18); tf.setBold(True)
        title.setFont(tf)
        top.addWidget(title)
        top.addStretch()
        self.db_update_btn = QPushButton(self.tr("db_update"))
        self.db_update_btn.setToolTip(self.tr("db_confirm"))
        self.db_update_btn.clicked.connect(self.update_database)
        self.boxdef_btn = QPushButton(self.tr("boxdef_btn"))
        self.boxdef_btn.clicked.connect(self.open_boxdef)
        self.missing_btn = QPushButton(self.tr("check_missing"))
        self.missing_btn.clicked.connect(self.check_missing)
        self.official_btn = QPushButton(self.tr("official"))
        self.official_btn.clicked.connect(lambda: webbrowser.open("https://taiko.ac"))
        top.addWidget(self.db_update_btn)
        top.addWidget(self.boxdef_btn)
        top.addWidget(self.missing_btn)
        top.addWidget(self.official_btn)
        root.addLayout(top)

        # search row
        sr = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(self.tr("ph"))
        self.search_edit.returnPressed.connect(self.do_search)
        self.cat_combo = QComboBox()
        self.cat_combo.setMinimumWidth(220)
        self.cat_combo.currentIndexChanged.connect(lambda _: self.do_search())
        self.search_btn = QPushButton(self.tr("search"))
        self.search_btn.clicked.connect(self.do_search)
        self.showall_btn = QPushButton(self.tr("show_all"))
        self.showall_btn.clicked.connect(self.show_all)
        self.clear_btn = QPushButton(self.tr("clear"))
        self.clear_btn.clicked.connect(self.clear_search)
        sr.addWidget(QLabel("🔍"))
        sr.addWidget(self.search_edit, 1)
        sr.addWidget(QLabel("📁"))
        sr.addWidget(self.cat_combo)
        sr.addWidget(self.search_btn)
        sr.addWidget(self.showall_btn)
        sr.addWidget(self.clear_btn)
        root.addLayout(sr)

        # splitter: song table (top) + monitor (bottom)
        splitter = QSplitter(Qt.Vertical)

        # song table
        song_box = QWidget()
        sb = QVBoxLayout(song_box)
        sb.setContentsMargins(0, 0, 0, 0)
        self.count_label = QLabel(self.tr("total", n=0))
        sb.addWidget(self.count_label)
        self.table = QTableView()
        self.table.setModel(self.song_model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.doubleClicked.connect(self.toggle_check)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        sb.addWidget(self.table)

        # selection row
        selr = QHBoxLayout()
        self.download_btn = QPushButton(self.tr("download"))
        self.download_btn.setStyleSheet(
            "QPushButton{background:#43A047;color:white;font-weight:bold;padding:8px 16px;border-radius:8px;}"
            "QPushButton:hover{background:#388E3C;} QPushButton:disabled{background:#7c7c7c;}")
        self.download_btn.clicked.connect(self.start_download_selected)
        self.selall_btn = QPushButton(self.tr("sel_all"))
        self.selall_btn.clicked.connect(lambda: self.song_model.set_all(True))
        self.deselall_btn = QPushButton(self.tr("desel_all"))
        self.deselall_btn.clicked.connect(lambda: self.song_model.set_all(False))
        self.sel_label = QLabel(self.tr("selected", n=0))
        selr.addWidget(self.download_btn)
        selr.addWidget(self.selall_btn)
        selr.addWidget(self.deselall_btn)
        selr.addStretch()
        selr.addWidget(self.sel_label)
        sb.addLayout(selr)
        splitter.addWidget(song_box)

        # monitor
        splitter.addWidget(self.build_monitor())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, 1)

        # settings row
        st = QHBoxLayout()
        st.addWidget(QLabel("💾 " + self.tr("dir")))
        self.dir_edit = QLineEdit(os.path.abspath(self.download_dir))
        self.browse_btn = QPushButton(self.tr("browse"))
        self.browse_btn.clicked.connect(self.browse_dir)
        self.opendir_btn = QPushButton(self.tr("open_dir"))
        self.opendir_btn.clicked.connect(self.open_dir)
        st.addWidget(self.dir_edit, 1)
        st.addWidget(self.browse_btn)
        st.addWidget(self.opendir_btn)
        st.addSpacing(20)
        st.addWidget(QLabel("⚡ " + self.tr("workers")))
        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, 16)
        self.workers_spin.setValue(self.config.get("download", {}).get("workers", 5))
        self.workers_spin.valueChanged.connect(lambda _: self.save_config())
        st.addWidget(self.workers_spin)
        st.addSpacing(20)
        st.addWidget(QLabel("🌐 " + self.tr("lang")))
        self.lang_combo = QComboBox()
        for label, code in (("自動 Auto", "auto"), ("繁體中文", "zh_TW"),
                            ("English", "en"), ("日本語", "ja")):
            self.lang_combo.addItem(label, code)
        idx = self.lang_combo.findData(self.lang_pref)
        self.lang_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.lang_combo.currentIndexChanged.connect(self.change_lang)
        st.addWidget(self.lang_combo)
        root.addLayout(st)

        # connect selection count
        self.song_model.dataChanged.connect(self.update_sel_count)

    def build_monitor(self):
        box = QGroupBox(self.tr("monitor"))
        v = QVBoxLayout(box)
        # overall progress + speed/eta
        pr = QHBoxLayout()
        self.overall_bar = QProgressBar()
        self.overall_bar.setFormat("%v / %m")
        self.overall_label = QLabel(self.tr("ready"))
        self.overall_label.setMinimumWidth(260)
        self.pause_btn = QPushButton(self.tr("pause"))
        self.pause_btn.clicked.connect(self.toggle_pause)
        self.pause_btn.setEnabled(False)
        self.stop_btn = QPushButton(self.tr("stop"))
        self.stop_btn.clicked.connect(self.stop_download)
        self.stop_btn.setEnabled(False)
        pr.addWidget(QLabel(self.tr("overall")))
        pr.addWidget(self.overall_bar, 1)
        pr.addWidget(self.overall_label)
        pr.addWidget(self.pause_btn)
        pr.addWidget(self.stop_btn)
        v.addLayout(pr)

        self.tabs = QTabWidget()
        # progress tab (per-file table)
        self.dl_table = QTableView()
        self.dl_table.setModel(self.dl_model)
        self.dl_table.verticalHeader().setVisible(False)
        self.dl_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        dh = self.dl_table.horizontalHeader()
        dh.setSectionResizeMode(0, QHeaderView.Stretch)
        dh.setSectionResizeMode(1, QHeaderView.Stretch)
        dh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        dh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        dh.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.tabs.addTab(self.dl_table, self.tr("tab_prog"))
        # log tab
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(5000)
        self.tabs.addTab(self.log_view, self.tr("tab_log"))
        # failed tab
        fail_w = QWidget()
        fv = QVBoxLayout(fail_w)
        self.fail_list = QListWidget()
        self.retry_btn = QPushButton(self.tr("retry"))
        self.retry_btn.clicked.connect(self.retry_failed)
        self.retry_btn.setEnabled(False)
        fv.addWidget(self.fail_list)
        fv.addWidget(self.retry_btn)
        self.tabs.addTab(fail_w, self.tr("tab_fail"))
        v.addWidget(self.tabs)
        return box

    # ---- categories
    def load_categories(self):
        self.cat_combo.blockSignals(True)
        self.cat_combo.clear()
        self.cat_combo.addItem(self.tr("all_cat"), None)
        try:
            conn = sqlite3.connect(DB_PATH)
            for (name,) in conn.execute("SELECT DISTINCT name FROM categories ORDER BY name"):
                self.cat_combo.addItem(CATEGORY_NAMES.get(name, name), name)
            conn.close()
        except Exception as e:
            print("load_categories:", e)
        self.cat_combo.blockSignals(False)

    # ---- search
    def do_search(self):
        kw = self.search_edit.text().strip()
        cat = self.cat_combo.currentData()
        self._run_search(kw, cat)

    def show_all(self):
        self.search_edit.clear()
        self.cat_combo.setCurrentIndex(0)
        self._run_search("", None)

    def clear_search(self):
        self.search_edit.clear()
        self.cat_combo.setCurrentIndex(0)
        self.song_model.set_songs([])
        self.count_label.setText(self.tr("total", n=0))
        self.update_sel_count()

    def _run_search(self, kw, cat):
        self.search_btn.setEnabled(False)
        self.count_label.setText("🔍 ...")
        self._search = SearchThread(kw, cat, self.has_local)
        self._search.done.connect(self.on_search_done)
        self._search.fail.connect(lambda e: (self.count_label.setText("✗ " + e),
                                             self.search_btn.setEnabled(True)))
        self._search.start()

    def on_search_done(self, songs):
        self.song_model.set_songs(songs)
        self.count_label.setText(self.tr("total", n=len(songs)))
        self.search_btn.setEnabled(True)
        self.update_sel_count()

    def toggle_check(self, index):
        if index.column() == 0:
            return
        row = index.row()
        cur = row in self.song_model.checked
        self.song_model.setData(self.song_model.index(row, 0),
                                Qt.Unchecked if cur else Qt.Checked, Qt.CheckStateRole)

    def update_sel_count(self, *args):
        self.sel_label.setText(self.tr("selected", n=len(self.song_model.checked)))

    # ---- download
    def start_download_selected(self):
        songs = self.song_model.selected_songs()
        if not songs:
            QMessageBox.warning(self, "", self.tr("desel_all"))
            return
        files = [(s, f) for s in songs for f in s["files"]]
        self.start_download(files)

    def start_download(self, files):
        if self.dl_thread and self.dl_thread.isRunning():
            QMessageBox.warning(self, "", "下載進行中…")
            return
        if not files:
            return
        self.save_config()
        self.download_btn.setEnabled(False)
        self.fail_list.clear()
        self.retry_btn.setEnabled(False)
        self.dl_model.load(files)
        self.overall_bar.setMaximum(len(files))
        self.overall_bar.setValue(0)
        self.tabs.setCurrentIndex(0)
        self.pause_btn.setText(self.tr("pause"))
        self.pause_btn.setEnabled(True)
        self.stop_btn.setEnabled(True)
        self.log_view.appendPlainText(f"——— 開始下載 {len(files)} 個檔案 ———")

        self.dl_thread = DownloadThread(files, self.dir_edit.text(),
                                        self.workers_spin.value())
        self.dl_thread.log.connect(self.log_view.appendPlainText)
        self.dl_thread.finished_all.connect(self.on_download_done)
        self.dl_thread.start()

        # 主執行緒以 QTimer 定時拉取進度（取代每 chunk 發訊號，避免卡死）
        if not hasattr(self, "dl_timer"):
            self.dl_timer = QTimer(self)
            self.dl_timer.setInterval(200)
            self.dl_timer.timeout.connect(self.refresh_progress)
        self.dl_timer.start()

    def refresh_progress(self):
        if not self.dl_thread:
            return
        done, total, spd, eta, dirty = self.dl_thread.snapshot()
        self.overall_bar.setValue(done)
        if self.dl_thread.is_paused():
            self.overall_label.setText(f"{done}/{total}  ·  {self.tr('paused_label')}")
        else:
            self.overall_label.setText(
                f"{done}/{total}  ·  {human_speed(spd)}  ·  ETA {human_eta(eta)}")
        for fp, (status, pct, speed) in dirty.items():
            self.dl_model.update(fp, status, pct, speed)

    def toggle_pause(self):
        if not (self.dl_thread and self.dl_thread.isRunning()):
            return
        if self.dl_thread.is_paused():
            self.dl_thread.resume()
            self.pause_btn.setText(self.tr("pause"))
        else:
            self.dl_thread.pause()
            self.pause_btn.setText(self.tr("resume"))

    def stop_download(self):
        if self.dl_thread and self.dl_thread.isRunning():
            self.dl_thread.stop()
            self.stop_btn.setEnabled(False)
            self.pause_btn.setEnabled(False)
            self.log_view.appendPlainText("——— 已要求停止，等待收尾… ———")

    def on_download_done(self, dl, skip, fail, total):
        if hasattr(self, "dl_timer"):
            self.dl_timer.stop()
        self.refresh_progress()   # 最後一次刷新，確保畫面到位
        self.download_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.pause_btn.setText(self.tr("pause"))
        self.overall_label.setText(self.tr("ready"))
        self.log_view.appendPlainText(
            f"——— 完成：成功 {dl}．跳過 {skip}．失敗 {fail} ———")
        # 填入失敗清單
        self.fail_list.clear()
        for song, f in self.dl_thread.failed:
            it = QListWidgetItem(f"{f['filename']}  ({song['song_name']})")
            it.setData(Qt.UserRole, (song, f))
            self.fail_list.addItem(it)
        self.retry_btn.setEnabled(fail > 0)
        if fail > 0:
            self.tabs.setCurrentIndex(2)
        QMessageBox.information(self, self.tr("monitor"),
                                self.tr("done_msg", d=dl, s=skip, f=fail, t=total))

    def retry_failed(self):
        files = [self.fail_list.item(i).data(Qt.UserRole)
                 for i in range(self.fail_list.count())]
        if files:
            self.start_download(files)

    # ---- check missing
    def check_missing(self):
        self.missing_btn.setEnabled(False)
        self._miss = SearchThread("", None, self.has_local)
        self._miss.done.connect(self.on_missing_loaded)
        self._miss.fail.connect(lambda e: (QMessageBox.critical(self, "", e),
                                           self.missing_btn.setEnabled(True)))
        self._miss.start()

    def on_missing_loaded(self, songs):
        self.missing_btn.setEnabled(True)
        ddir = self.dir_edit.text()
        missing = []
        for s in songs:
            for f in s["files"]:
                if not os.path.exists(os.path.join(ddir, f["file_path"])):
                    missing.append(s)
                    break
        if not missing:
            QMessageBox.information(self, self.tr("check_missing"), "✓ 沒有缺漏")
            return
        files = [(s, f) for s in missing for f in s["files"]]
        if QMessageBox.question(
                self, self.tr("check_missing"),
                f"發現 {len(missing)} 首缺漏（{len(files)} 檔），是否下載？") \
                == QMessageBox.Yes:
            self.song_model.set_songs(missing)
            self.song_model.set_all(True)
            self.count_label.setText(self.tr("total", n=len(missing)))
            self.start_download(files)

    # ---- misc
    def browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, self.tr("browse"), self.dir_edit.text())
        if d:
            self.dir_edit.setText(d)
            self.save_config()

    def open_dir(self):
        d = self.dir_edit.text()
        if os.path.isdir(d):
            os.startfile(d)  # Windows

    # ---- box.def 編輯器
    def open_boxdef(self):
        start = self.dir_edit.text() if os.path.isdir(self.dir_edit.text()) else os.getcwd()
        BoxDefDialog(self, start, self.tr).exec()

    # ---- 一鍵更新資料庫（歌曲清單 + 日文標題；整合自 update_databases.bat）
    def update_database(self):
        if getattr(self, "_db_thread", None) and self._db_thread.isRunning():
            QMessageBox.warning(self, "", self.tr("db_building"))
            return
        if QMessageBox.question(self, self.tr("db_update"),
                                self.tr("db_confirm")) != QMessageBox.Yes:
            return

        # 解析 git；沒有就詢問是否下載可攜版
        from ese_scraper_git_v2 import find_git
        git_exe = find_git()
        download_git = False
        if not git_exe:
            if QMessageBox.question(self, "Git", self.tr("db_no_git_q")) == QMessageBox.Yes:
                download_git = True
            else:
                QMessageBox.information(self, "Git", self.tr("db_no_git_fail"))
                return

        self.db_update_btn.setEnabled(False)
        self.tabs.setCurrentIndex(1)   # 切到 Log 分頁
        self.overall_label.setText(self.tr("db_building"))
        self.log_view.appendPlainText("——— " + self.tr("db_building") + " ———")
        self._db_thread = DBBuildThread(git_exe, download_git=download_git)
        self._db_thread.log.connect(self.log_view.appendPlainText)
        self._db_thread.done.connect(self.on_db_build_done)
        self._db_thread.start()

    def on_db_build_done(self, ok, info):
        self.db_update_btn.setEnabled(True)
        self.overall_label.setText(self.tr("ready"))
        if not ok:
            if info == "NOGIT":
                QMessageBox.critical(self, "Git", self.tr("db_no_git_fail"))
            else:
                QMessageBox.critical(self, self.tr("db_update"), self.tr("db_fail", e=info))
            return
        # 重載分類 + 日文對照，並刷新目前清單
        self.load_categories()
        self.has_local = os.path.exists(LOCAL_DB_PATH)
        self.jp_map = self.load_jp_map()
        self.song_model.jp_map = self.jp_map
        if self.song_model.songs:
            self.song_model.dataChanged.emit(
                self.song_model.index(0, 2),
                self.song_model.index(self.song_model.rowCount() - 1, 2),
                [Qt.DisplayRole])
        QMessageBox.information(self, self.tr("db_update"), self.tr("db_done"))

    def change_lang(self, *_):
        pref = self.lang_combo.currentData() or "auto"
        if pref == self.lang_pref:
            return
        self.lang_pref = pref
        self.lang = detect_system_lang() if pref == "auto" else pref
        self.save_config()
        # 有下載/資料庫工作進行中就別重啟，避免中斷；下次啟動再套用
        busy = ((self.dl_thread and self.dl_thread.isRunning()) or
                (getattr(self, "_db_thread", None) and self._db_thread.isRunning()))
        if busy:
            QMessageBox.information(self, "", self.tr("lang_busy"))
            return
        self._restart()

    def _restart(self):
        """重新啟動程式以完整套用語言（frozen exe 與原始碼執行皆支援）。"""
        self.save_config()
        if getattr(sys, "frozen", False):
            program, args = sys.executable, sys.argv[1:]
        else:
            program, args = sys.executable, sys.argv
        QProcess.startDetached(program, args, os.getcwd())
        QApplication.quit()

    # ---- db update
    def check_db_update(self):
        self._ver = VersionThread()
        self._ver.result.connect(self.on_version)
        self._ver.start()

    def on_version(self, remote, local):
        if remote and remote != local:
            if QMessageBox.question(
                    self, "資料庫更新",
                    f"發現新版本資料庫\n目前: {local or '無'}\n最新: {remote}\n是否更新？") \
                    == QMessageBox.Yes:
                self._dbu = DBUpdateThread(remote)
                self._dbu.log.connect(self.log_view.appendPlainText)
                self._dbu.done.connect(self.on_db_updated)
                self.tabs.setCurrentIndex(1)
                self._dbu.start()

    def on_db_updated(self, ok, msg):
        if ok:
            self.has_local = os.path.exists(LOCAL_DB_PATH)
            self.jp_map = self.load_jp_map()
            self.song_model.jp_map = self.jp_map
            self.load_categories()
            QMessageBox.information(self, "資料庫更新", "✓ 更新成功")
        else:
            QMessageBox.critical(self, "資料庫更新", msg)


class VersionThread(QThread):
    result = Signal(str, str)  # remote, local

    def run(self):
        remote = ""
        local = ""
        try:
            r = requests.get("https://taikozhong.me/tjamanager/version.txt",
                             timeout=10, verify=False)
            r.raise_for_status()
            remote = r.text.strip()
        except Exception as e:
            print("version:", e)
        if os.path.exists("version.txt"):
            try:
                with open("version.txt", encoding="utf-8") as f:
                    local = f.read().strip()
            except Exception:
                pass
        self.result.emit(remote, local)


class DBUpdateThread(QThread):
    log = Signal(str)
    done = Signal(bool, str)

    def __init__(self, version):
        super().__init__()
        self.version = version

    def run(self):
        base = "https://taikozhong.me/tjamanager/"
        try:
            for name in ("ese_songs.db", "ese_local.db"):
                self.log.emit(f"下載資料庫 {name} …")
                r = requests.get(base + name, stream=True, timeout=120, verify=False)
                r.raise_for_status()
                with open(name, "wb") as f:
                    for chunk in r.iter_content(8192):
                        if chunk:
                            f.write(chunk)
            with open("version.txt", "w", encoding="utf-8") as f:
                f.write(self.version)
            self.done.emit(True, "ok")
        except Exception as e:
            self.done.emit(False, str(e))


def main():
    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create("Fusion"))
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
