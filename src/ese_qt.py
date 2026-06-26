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
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

# ESE 檔案下載/取得來源（live host；舊 host git.vanillaaaa.org 已停用）
ESE_RAW_BASE = "https://ese.tjadataba.se/ESE/ESE/raw/branch/master/"


def _live_url(url):
    """把舊 host 換成 live host，讓舊版資料庫的連結仍可用。"""
    if not url:
        return url
    return url.replace("git.vanillaaaa.org", "ese.tjadataba.se")

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
    QGroupBox, QDialog, QFormLayout, QColorDialog, QFrame, QScrollArea,
    QTableWidget, QTableWidgetItem
)
import re

# 確保能 import 同目錄的 download_songs
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from download_songs import SongDownloader  # noqa: E402
import dan_tools  # noqa: E402  段位生成/變換（移植自 bluetaiko/SongConvertor）

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
        "boxdef_fetch": "⬇ 取得 ESE 官方", "boxdef_fetch_tip": "從 ESE 倉庫下載此分類的官方 box.def",
        "boxdef_fetch_none": "ESE 找不到對應此資料夾的 box.def（依名稱/序號比對）",
        "boxdef_fetch_fail": "取得失敗：{e}", "boxdef_fetch_ok": "已載入 ESE 官方 box.def（{c}）",
        "c_bpm": "BPM", "c_easy": "簡單", "c_normal": "普通", "c_hard": "困難",
        "c_oni": "魔王", "c_ura": "裏",
        "f_filter": "篩選", "f_bpm": "BPM 區間", "f_diff": "難度", "f_level": "等級",
        "diff_all": "全部難度", "f_reset": "重設篩選", "f_any": "不限",
        "dan_btn": "🥋 段位工具", "dan_title": "段位工具（Dan）",
        "dan_tab_gen": "段位生成（Wiki）", "dan_tab_conv": "段位變換（tja）",
        "dan_gen_url": "太鼓 Wiki 段位頁面 URL", "dan_out": "輸出資料夾",
        "dan_songs": "Songs 資料夾", "dan_songs_opt": "Songs 資料夾（可省略）",
        "dan_gen_run": "段位生成", "dan_conv_tja": "要變換的 tja",
        "dan_conv_run": "變換執行", "dan_browse": "瀏覽",
        "dan_gen_hint": "輸入太鼓 Wiki 的段位道場頁面網址，依段位名稱與合格條件\n生成 TaikøNauts 等可用的段位檔（dan.def + 各段位 Dan.json）。",
        "dan_conv_hint": "把 OpenTaiko 等的 tja 段位（以 #NEXTSONG 分隔多曲）\n變換成 TaikøNauts 等可用的段位檔。",
        "dan_need_url": "請輸入段位頁面 URL", "dan_need_out": "請選擇輸出資料夾",
        "dan_need_tja": "請選擇要變換的 tja 檔", "dan_running": "處理中…",
        "dan_done": "完成！", "dan_fail": "失敗：{e}",
        "credits_btn": "💗 致謝", "credits_title": "致謝 / Credits",
        "credits_body": "段位生成（DanGenerator）與段位變換（DanConvertor）功能\n移植自 bluetaiko 的 SongConvertor 專案，特此感謝原作者。\n\n原專案（MIT License）：\nhttps://github.com/bluetaiko/SongConvertor",
        "yatai_btn": "🎮 YataiDON", "yatai_title": "YataiDON box.def 生成工具",
        "yatai_folder": "Songs 資料夾", "yatai_scan": "掃描",
        "yatai_col_folder": "資料夾", "yatai_col_title": "標題",
        "yatai_col_genre": "GENRE", "yatai_col_collection": "COLLECTION",
        "yatai_col_back": "背景色", "yatai_col_fore": "文字色",
        "yatai_gen_all": "全部生成 box.def",
        "yatai_done": "完成：已生成 {c} 個 box.def",
        "yatai_pick": "選擇顏色",
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
        "boxdef_fetch": "⬇ Fetch from ESE", "boxdef_fetch_tip": "Download the official box.def for this category from the ESE repo",
        "boxdef_fetch_none": "No matching ESE box.def for this folder (by name/index)",
        "boxdef_fetch_fail": "Fetch failed: {e}", "boxdef_fetch_ok": "Loaded official ESE box.def ({c})",
        "c_bpm": "BPM", "c_easy": "Easy", "c_normal": "Normal", "c_hard": "Hard",
        "c_oni": "Oni", "c_ura": "Ura",
        "f_filter": "Filter", "f_bpm": "BPM range", "f_diff": "Difficulty", "f_level": "Level",
        "diff_all": "All difficulties", "f_reset": "Reset filters", "f_any": "Any",
        "dan_btn": "🥋 Dan Tools", "dan_title": "Dan Tools",
        "dan_tab_gen": "Generate (Wiki)", "dan_tab_conv": "Convert (tja)",
        "dan_gen_url": "Taiko Wiki Dan page URL", "dan_out": "Output folder",
        "dan_songs": "Songs folder", "dan_songs_opt": "Songs folder (optional)",
        "dan_gen_run": "Generate", "dan_conv_tja": "tja to convert",
        "dan_conv_run": "Convert", "dan_browse": "Browse",
        "dan_gen_hint": "Enter a Taiko Wiki Dan-dojo page URL to generate Dan files\nfor TaikøNauts etc. (dan.def + per-rank Dan.json) from the\nrank names and clear conditions.",
        "dan_conv_hint": "Convert an OpenTaiko-style Dan tja (multiple songs split by\n#NEXTSONG) into TaikøNauts-compatible Dan files.",
        "dan_need_url": "Please enter the Dan page URL", "dan_need_out": "Please choose an output folder",
        "dan_need_tja": "Please choose a tja file", "dan_running": "Working…",
        "dan_done": "Done!", "dan_fail": "Failed: {e}",
        "credits_btn": "💗 Credits", "credits_title": "Credits",
        "credits_body": "The Dan Generator and Dan Convertor features are ported from\nbluetaiko's SongConvertor project. Many thanks to the author.\n\nOriginal project (MIT License):\nhttps://github.com/bluetaiko/SongConvertor",
        "yatai_btn": "🎮 YataiDON", "yatai_title": "YataiDON box.def Generator",
        "yatai_folder": "Songs folder", "yatai_scan": "Scan",
        "yatai_col_folder": "Folder", "yatai_col_title": "Title",
        "yatai_col_genre": "GENRE", "yatai_col_collection": "COLLECTION",
        "yatai_col_back": "Back color", "yatai_col_fore": "Fore color",
        "yatai_gen_all": "Generate All box.def",
        "yatai_done": "Done: generated {c} box.def files",
        "yatai_pick": "Pick color",
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
        "boxdef_fetch": "⬇ ESE から取得", "boxdef_fetch_tip": "ESE リポジトリからこの分類の公式 box.def を取得",
        "boxdef_fetch_none": "このフォルダに対応する ESE の box.def が見つかりません（名前/番号で照合）",
        "boxdef_fetch_fail": "取得に失敗: {e}", "boxdef_fetch_ok": "ESE 公式 box.def を読み込みました（{c}）",
        "c_bpm": "BPM", "c_easy": "かんたん", "c_normal": "ふつう", "c_hard": "むずかしい",
        "c_oni": "おに", "c_ura": "裏",
        "f_filter": "絞り込み", "f_bpm": "BPM 範囲", "f_diff": "難易度", "f_level": "レベル",
        "diff_all": "すべて", "f_reset": "リセット", "f_any": "指定なし",
        "dan_btn": "🥋 段位ツール", "dan_title": "段位ツール（Dan）",
        "dan_tab_gen": "段位生成（Wiki）", "dan_tab_conv": "段位変換（tja）",
        "dan_gen_url": "太鼓 Wiki 段位ページの URL", "dan_out": "出力フォルダ",
        "dan_songs": "Songs フォルダ", "dan_songs_opt": "Songs フォルダ（省略可）",
        "dan_gen_run": "段位生成", "dan_conv_tja": "変換する tja",
        "dan_conv_run": "変換実行", "dan_browse": "参照",
        "dan_gen_hint": "太鼓 Wiki の段位道場ページの URL を入力し、段位の名前と\n合格条件から TaikøNauts 等で使える段位ファイル（dan.def +\n各段位の Dan.json）を生成します。",
        "dan_conv_hint": "OpenTaiko 等の tja 段位（#NEXTSONG で複数曲に分割）を\nTaikøNauts 等で使える段位ファイルに変換します。",
        "dan_need_url": "段位ページの URL を入力してください", "dan_need_out": "出力フォルダを選択してください",
        "dan_need_tja": "変換する tja を選択してください", "dan_running": "処理中…",
        "dan_done": "完了！", "dan_fail": "失敗: {e}",
        "credits_btn": "💗 クレジット", "credits_title": "クレジット / Credits",
        "credits_body": "段位生成（DanGenerator）と段位変換（DanConvertor）機能は\nbluetaiko 氏の SongConvertor を移植したものです。作者に感謝します。\n\n元プロジェクト（MIT License）:\nhttps://github.com/bluetaiko/SongConvertor",
        "yatai_btn": "🎮 YataiDON", "yatai_title": "YataiDON box.def 生成ツール",
        "yatai_folder": "Songs フォルダ", "yatai_scan": "スキャン",
        "yatai_col_folder": "フォルダ", "yatai_col_title": "タイトル",
        "yatai_col_genre": "GENRE", "yatai_col_collection": "COLLECTION",
        "yatai_col_back": "背景色", "yatai_col_fore": "文字色",
        "yatai_gen_all": "すべて box.def を生成",
        "yatai_done": "完了：{c} 個の box.def を生成しました",
        "yatai_pick": "色を選択",
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
    COLS = ["c_sel", "c_song", "c_jp", "c_cat", "c_bpm",
            "c_easy", "c_normal", "c_hard", "c_oni", "c_ura", "c_files"]
    LEVEL_COLS = {5: "level_easy", 6: "level_normal", 7: "level_hard",
                  8: "level_oni", 9: "level_ura"}

    def __init__(self, tr, jp_map, meta_map=None):
        super().__init__()
        self.tr = tr
        self.jp_map = jp_map
        self.meta_map = meta_map or {}
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
                meta = self.meta_map.get(song["song_name"])
                return (meta or {}).get("bpm", "") or ""
            if col in self.LEVEL_COLS:
                meta = self.meta_map.get(song["song_name"])
                lv = (meta or {}).get(self.LEVEL_COLS[col])
                return str(lv) if lv is not None else "−"
            if col == 10:
                return str(len(song["files"]))
        if role == Qt.ForegroundRole and col == 3:
            c = CATEGORY_COLORS.get(song["category"])
            if c:
                return QColor(c)
        if role == Qt.TextAlignmentRole and (col == 4 or col in self.LEVEL_COLS or col == 10):
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
                r = sess.get(_live_url(f["download_url"]), stream=True, timeout=60, verify=False)
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

        # 第一次建立分類資料夾時，順便從 ESE 抓官方 box.def（已存在則略過）
        self._fetch_boxdefs(sess)

        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            list(ex.map(worker, self.files))
        self.finished_all.emit(self.dl, self.skip, self.fail, self.total)

    def _fetch_boxdefs(self, sess):
        """為本次下載涉及的每個分類資料夾建立 box.def（缺少時才從 ESE 取）。"""
        try:
            conn = sqlite3.connect(DB_PATH)
            boxmap = {fp.split("/")[0]: fp for (fp,) in conn.execute(
                "SELECT file_path FROM song_files WHERE lower(filename)='box.def'")}
            conn.close()
        except Exception:
            return
        cats = {f["file_path"].split("/")[0] for _, f in self.files if "/" in f["file_path"]}
        for cat in sorted(cats):
            if self._stop:
                break
            fp = boxmap.get(cat)
            if not fp:
                continue
            dest = os.path.join(self.download_dir, cat, "box.def")
            if os.path.exists(dest):
                continue
            try:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                r = sess.get(ESE_RAW_BASE + urllib.parse.quote(fp), timeout=30, verify=False)
                if r.ok:
                    with open(dest, "wb") as out:
                        out.write(r.content)
                    self.log.emit(f"📦 box.def: {cat}")
            except Exception as e:
                self.log.emit(f"box.def {cat}: {e}")


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


# --------------------------------------------------------- YataiDON box.def 生成工具
# YataiDON parse_box_def supports: #TITLE / #TITLE<LANG> / #GENRE / #COLLECTION /
# #BACKCOLOR:#RRGGBB / #FORECOLOR:#RRGGBB
# Valid GENRE strings (from GENRE_MAP in enums.h): J-POP ANIME VOCALOID CHILDREN
# VARIETY CLASSICAL GAME NAMCO TUTORIAL
# COLLECTION strings: DAN DIFFICULTY RECOMMENDED FAVORITE RECENT

YATAI_VALID_GENRES = [
    "", "J-POP", "ANIME", "VOCALOID", "CHILDREN", "VARIETY",
    "CLASSICAL", "GAME", "NAMCO", "TUTORIAL",
]


def _detect_yatai_def(folder_name):
    """Auto-detect (genre, collection) from folder name for YataiDON."""
    low = folder_name.lower()
    if "dan" in low or "dojo" in low:
        return "", "DAN"
    if "recommend" in low:
        return "", "RECOMMENDED"
    if "recent" in low:
        return "", "RECENT"
    if "favorite" in low or "favour" in low:
        return "", "FAVORITE"
    if "difficulty" in low:
        return "", "DIFFICULTY"
    if "j-pop" in low or "jpop" in low:
        return "J-POP", ""
    if "pop" in low:
        return "J-POP", ""
    if "anime" in low:
        return "ANIME", ""
    if "vocaloid" in low:
        return "VOCALOID", ""
    if any(k in low for k in ("children", "kids", "folk")):
        return "CHILDREN", ""
    if "variety" in low:
        return "VARIETY", ""
    if "classical" in low or "classic" in low:
        return "CLASSICAL", ""
    if "game" in low:
        return "GAME", ""
    if "namco" in low:
        return "NAMCO", ""
    return "J-POP", ""


def make_yatai_boxdef(folder_name, title="", genre="", collection="",
                      back_color="", fore_color=""):
    """Generate box.def in YataiDON format."""
    lines = [f"#TITLE:{title or folder_name}"]
    if genre:
        lines.append(f"#GENRE:{genre}")
    if collection:
        lines.append(f"#COLLECTION:{collection}")
    if back_color:
        hx = _norm_hex(back_color)
        if hx:
            lines.append(f"#BACKCOLOR:#{hx}")
    if fore_color:
        hx = _norm_hex(fore_color)
        if hx:
            lines.append(f"#FORECOLOR:#{hx}")
    return "\n".join(lines) + "\n"


class YataiBoxDefDialog(QDialog):
    """YataiDON box.def 批量生成工具。
    為 Songs 資料夾內每個子資料夾產生正確格式的 box.def（GENRE/COLLECTION/顏色）。
    """

    COL_FOLDER = 0
    COL_TITLE  = 1
    COL_GENRE  = 2
    COL_COLL   = 3
    COL_BACK   = 4
    COL_FORE   = 5

    def __init__(self, parent, tr, start_dir=""):
        super().__init__(parent)
        self.tr = tr
        self.setWindowTitle(tr("yatai_title"))
        self.resize(980, 580)
        self._color_edits = {}   # (row, col) -> QLineEdit
        self._build_ui(start_dir)
        if start_dir and os.path.isdir(start_dir):
            self.scan()

    def _build_ui(self, start_dir):
        root = QVBoxLayout(self)

        # Folder row
        fr = QHBoxLayout()
        fr.addWidget(QLabel(self.tr("yatai_folder") + ":"))
        self.folder_edit = QLineEdit(start_dir)
        fr.addWidget(self.folder_edit, 1)
        browse_btn = QPushButton(self.tr("browse"))
        browse_btn.clicked.connect(self._browse)
        scan_btn = QPushButton(self.tr("yatai_scan"))
        scan_btn.clicked.connect(self.scan)
        fr.addWidget(browse_btn)
        fr.addWidget(scan_btn)
        root.addLayout(fr)

        # Table
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            self.tr("yatai_col_folder"),
            self.tr("yatai_col_title"),
            self.tr("yatai_col_genre"),
            self.tr("yatai_col_collection"),
            self.tr("yatai_col_back"),
            self.tr("yatai_col_fore"),
        ])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(self.COL_FOLDER, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(self.COL_TITLE,  QHeaderView.Stretch)
        hh.setSectionResizeMode(self.COL_GENRE,  QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(self.COL_COLL,   QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(self.COL_BACK,   QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(self.COL_FORE,   QHeaderView.ResizeToContents)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        root.addWidget(self.table, 1)

        # Info
        info = QLabel(
            "YataiDON: #TITLE / #GENRE (J-POP ANIME VOCALOID CHILDREN VARIETY CLASSICAL GAME NAMCO) "
            "/ #COLLECTION (DAN DIFFICULTY RECOMMENDED FAVORITE RECENT). "
            "顏色留空＝使用 GENRE 內建背景圖（建議）；填色會覆蓋成純色背景 / "
            "Leave colors blank to use the built-in genre texture (recommended); "
            "setting a color overrides it with a flat background."
        )
        info.setStyleSheet("color:#888;font-size:10px;")
        info.setWordWrap(True)
        root.addWidget(info)

        # Buttons
        br = QHBoxLayout()
        gen_btn = QPushButton(self.tr("yatai_gen_all"))
        gen_btn.setStyleSheet(
            "QPushButton{background:#1976D2;color:white;font-weight:bold;"
            "padding:8px 16px;border-radius:8px;}"
            "QPushButton:hover{background:#1565C0;}"
        )
        gen_btn.clicked.connect(self.generate_all)
        br.addStretch()
        br.addWidget(gen_btn)
        root.addLayout(br)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, self.tr("browse"), self.folder_edit.text())
        if d:
            self.folder_edit.setText(d)
            self.scan()

    def _color_widget(self, row, col, initial=""):
        """Color cell: hex QLineEdit + live swatch + picker button."""
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(2, 1, 2, 1)
        edit = QLineEdit(initial.upper().lstrip("#"))
        edit.setMaxLength(6)
        edit.setPlaceholderText("RRGGBB")
        edit.setFixedWidth(66)
        swatch = QFrame()
        swatch.setFixedSize(18, 18)
        btn = QPushButton("🎨")
        btn.setFixedWidth(28)
        btn.setFlat(True)

        def upd():
            hx = edit.text().strip().upper()
            ok = len(hx) == 6 and all(c in "0123456789ABCDEF" for c in hx)
            swatch.setStyleSheet(
                (f"background:#{hx};border:1px solid #555;border-radius:2px;") if ok
                else "border:1px solid #555;border-radius:2px;"
            )

        def pick():
            cur = edit.text().strip()
            init = QColor("#" + cur) if len(cur) == 6 else QColor("#444444")
            c = QColorDialog.getColor(init, self, self.tr("yatai_pick"))
            if c.isValid():
                edit.setText(c.name().lstrip("#").upper())

        edit.textChanged.connect(upd)
        btn.clicked.connect(pick)
        h.addWidget(edit)
        h.addWidget(swatch)
        h.addWidget(btn)
        upd()
        self._color_edits[(row, col)] = edit
        return w

    def scan(self):
        base = self.folder_edit.text().strip()
        if not os.path.isdir(base):
            return
        self._color_edits.clear()
        subs = sorted(d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d)))
        self.table.setRowCount(0)

        for row_idx, sub in enumerate(subs):
            self.table.insertRow(row_idx)

            # Try to read existing box.def
            bpath = os.path.join(base, sub, "box.def")
            ex_title = sub
            ex_genre = ""
            ex_coll  = ""
            ex_back  = ""
            ex_fore  = ""
            if os.path.exists(bpath):
                try:
                    for line in _read_text(bpath).splitlines():
                        s = line.strip()
                        if s.startswith("#TITLE:") and ex_title == sub:
                            ex_title = s[7:]
                        elif s.startswith("#GENRE:"):
                            ex_genre = s[7:].upper()
                        elif s.startswith("#COLLECTION:"):
                            ex_coll = s[12:].upper()
                except Exception:
                    pass

            # Auto-detect when existing file has wrong/missing genre/collection
            if not ex_genre and not ex_coll:
                ex_genre, ex_coll = _detect_yatai_def(sub)
            # NOTE: colors are deliberately NOT pre-loaded and stay blank.
            # YataiDON renders the genre background from a texture keyed by
            # #GENRE/#COLLECTION. Setting #BACKCOLOR forces texture_index=NONE,
            # replacing the proper genre texture with a flat colour. Leaving the
            # color fields blank means "Generate All" writes clean files with no
            # color lines, so the correct genre textures show. Fill a colour in
            # only for a deliberate custom override.

            # Col 0: folder (read-only)
            fi = QTableWidgetItem(sub)
            fi.setFlags(fi.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row_idx, self.COL_FOLDER, fi)

            # Col 1: title
            self.table.setItem(row_idx, self.COL_TITLE, QTableWidgetItem(ex_title))

            # Col 2: genre combo
            combo = QComboBox()
            combo.addItems(YATAI_VALID_GENRES)
            if ex_genre in YATAI_VALID_GENRES:
                combo.setCurrentText(ex_genre)
            self.table.setCellWidget(row_idx, self.COL_GENRE, combo)

            # Col 3: collection (free text)
            self.table.setItem(row_idx, self.COL_COLL, QTableWidgetItem(ex_coll))

            # Col 4/5: colors
            self.table.setCellWidget(row_idx, self.COL_BACK, self._color_widget(row_idx, self.COL_BACK, ex_back))
            self.table.setCellWidget(row_idx, self.COL_FORE, self._color_widget(row_idx, self.COL_FORE, ex_fore))

        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(self.COL_TITLE, QHeaderView.Stretch)

    def generate_all(self):
        base = self.folder_edit.text().strip()
        if not os.path.isdir(base):
            QMessageBox.warning(self, self.tr("yatai_title"), self.tr("boxdef_no_dir"))
            return
        created = 0
        errors = []
        for row in range(self.table.rowCount()):
            sub_item = self.table.item(row, self.COL_FOLDER)
            if not sub_item:
                continue
            sub = sub_item.text()
            title_item = self.table.item(row, self.COL_TITLE)
            title = title_item.text().strip() if title_item else sub
            genre_w = self.table.cellWidget(row, self.COL_GENRE)
            genre = genre_w.currentText() if genre_w else ""
            coll_item = self.table.item(row, self.COL_COLL)
            coll = coll_item.text().strip().upper() if coll_item else ""
            back_e = self._color_edits.get((row, self.COL_BACK))
            fore_e = self._color_edits.get((row, self.COL_FORE))
            back = back_e.text().strip() if back_e else ""
            fore = fore_e.text().strip() if fore_e else ""

            content = make_yatai_boxdef(sub, title=title, genre=genre, collection=coll,
                                        back_color=back, fore_color=fore)
            path = os.path.join(base, sub, "box.def")
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                created += 1
            except Exception as e:
                errors.append(f"{sub}: {e}")

        msg = self.tr("yatai_done", c=created)
        if errors:
            msg += "\n" + "\n".join(errors[:5])
        QMessageBox.information(self, self.tr("yatai_title"), msg)


# ------------------------------------------------------------- box.def 編輯器
# OpenTaiko box.def 圖形化編輯器（規格依原始碼 CBoxDef.cs）：
#   #TITLE / #TITLE<LANG>（多語言）/ #GENRE / #BGCOLOR / #BOXCOLOR /
#   #FORECOLOR / #BACKCOLOR（顏色值經 ColorTranslator 解析，需含 #）/
#   #BGTYPE / #BOXTYPE / #BOXCHARA / #SELECTBG / #SCENEPRESET / #BOXEXPLANATION1-3
BOXDEF_LANGS = [("", "#TITLE"), ("EN", "#TITLEEN"), ("JA", "#TITLEJA"),
                ("ZH", "#TITLEZH"), ("CN", "#TITLECN"), ("TW", "#TITLETW"),
                ("KO", "#TITLEKO")]
BOXDEF_LANG_LABEL = {"": "Default", "EN": "English", "JA": "日本語",
                     "ZH": "中文", "CN": "简体中文", "TW": "繁體中文", "KO": "한국어"}
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
        fetch = QPushButton(tr("boxdef_fetch"))
        fetch.setToolTip(tr("boxdef_fetch_tip"))
        fetch.clicked.connect(self.fetch_ese)
        gen = QPushButton(tr("boxdef_gen"))
        gen.clicked.connect(self.generate)
        save = QPushButton(tr("boxdef_save"))
        save.clicked.connect(self.save)
        batch = QPushButton(tr("boxdef_batch"))
        batch.clicked.connect(self.batch)
        br.addWidget(fetch)
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
        # 盒子外觀以 BACKCOLOR 為底、FORECOLOR 為字（ESE box.def 多半只設這兩個）；
        # 沒設才退回 BGCOLOR / 自動對比色。
        bg = (_norm_hex(self.color_edits["BACKCOLOR"].text())
              or _norm_hex(self.color_edits["BGCOLOR"].text()) or "333333")
        fore = _norm_hex(self.color_edits["FORECOLOR"].text())
        if fore:
            fg = "#" + fore
        else:
            r, g, b = _hex_to_rgb("#" + bg)
            fg = "#000000" if (r * 0.299 + g * 0.587 + b * 0.114) > 150 else "#FFFFFF"
        title = self.title_edits[""].text() or "(title)"
        genre = self.genre.currentText().strip()
        self.preview.setText(title + (("\n" + genre) if genre else ""))
        self.preview.setStyleSheet(
            "QLabel{background:#%s;color:%s;border-radius:8px;"
            "font-size:17px;font-weight:bold;}" % (bg, fg))

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

    def _apply_text(self, text):
        """把 box.def 文字內容填入各欄位（未知行存入 self.extra）。"""
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

    def load(self):
        self._clear()
        p = self._path()
        if not os.path.exists(p):
            self._fill_template()
            self._update_preview()
            return
        try:
            self._apply_text(_read_text(p))
        except Exception as e:
            print("boxdef load:", e)
        self._update_preview()

    def fetch_ese(self):
        """從 ESE 官方倉庫抓取對應分類的 box.def 填入表單（依資料夾名或序號比對）。"""
        name = os.path.basename(self.dir_edit.text().rstrip("/\\"))
        m = re.match(r"\s*(\d+)", name)
        num = m.group(1).zfill(2) if m else None
        try:
            conn = sqlite3.connect(DB_PATH)
            paths = [r[0] for r in conn.execute(
                "SELECT file_path FROM song_files WHERE lower(filename)='box.def'")]
            conn.close()
        except Exception as e:
            QMessageBox.critical(self, self.tr("boxdef_title"), str(e))
            return
        target = None
        for fp in paths:
            cat = fp.split("/")[0]
            cm = re.match(r"\s*(\d+)", cat)
            if (cat == name
                    or _clean_name(cat).lower() == _clean_name(name).lower()
                    or (num and cm and cm.group(1).zfill(2) == num)):
                target = fp
                break
        if not target:
            QMessageBox.information(self, self.tr("boxdef_title"), self.tr("boxdef_fetch_none"))
            return
        url = ESE_RAW_BASE + urllib.parse.quote(target)
        try:
            r = requests.get(url, timeout=30, verify=False)
            r.raise_for_status()
            text = None
            for enc in ("utf-8-sig", "utf-8", "shift-jis", "cp932", "latin-1"):
                try:
                    text = r.content.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
        except Exception as e:
            QMessageBox.critical(self, self.tr("boxdef_title"), self.tr("boxdef_fetch_fail", e=str(e)))
            return
        self._clear()
        self._apply_text(text or "")
        self._update_preview()
        QMessageBox.information(self, self.tr("boxdef_title"),
                               self.tr("boxdef_fetch_ok", c=target.split("/")[0]))

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


# ---------------------------------------------------------- 段位工具執行緒/對話框
class DanGenThread(QThread):
    log = Signal(str)
    done = Signal(bool, str)         # ok, info

    def __init__(self, url, out_dir, songs_folder, local_db=""):
        super().__init__()
        self.url, self.out_dir, self.songs_folder = url, out_dir, songs_folder
        self.local_db = local_db

    def run(self):
        try:
            n = dan_tools.generate_dan_from_wiki(
                self.url, self.out_dir, songs_folder=self.songs_folder,
                log=self.log.emit, local_db=self.local_db)
            self.done.emit(True, str(n))
        except Exception as e:
            self.done.emit(False, str(e))


class DanConvThread(QThread):
    log = Signal(str)
    done = Signal(bool, str)

    def __init__(self, tja, out_dir, songs_folder):
        super().__init__()
        self.tja, self.out_dir, self.songs_folder = tja, out_dir, songs_folder

    def run(self):
        try:
            dan_tools.convert_dan_tja(
                self.tja, self.out_dir, simu_folder=self.songs_folder,
                log=self.log.emit)
            self.done.emit(True, "")
        except Exception as e:
            self.done.emit(False, str(e))


class DanToolsDialog(QDialog):
    """段位生成（Wiki）+ 段位變換（tja）。移植自 bluetaiko/SongConvertor。"""

    def __init__(self, parent, tr, start_dir):
        super().__init__(parent)
        self.tr = tr
        self.start_dir = start_dir
        self._thread = None
        self.setWindowTitle(tr("dan_title"))
        self.resize(720, 560)

        root = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._build_gen_tab(), tr("dan_tab_gen"))
        tabs.addTab(self._build_conv_tab(), tr("dan_tab_conv"))
        root.addWidget(tabs)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(5000)
        root.addWidget(self.log_view, 1)

        credit = QLabel(
            'Dan tools ported from '
            '<a href="https://github.com/bluetaiko/SongConvertor">bluetaiko/SongConvertor</a>'
            ' (MIT) — thanks!')
        credit.setOpenExternalLinks(True)
        credit.setStyleSheet("color:#888;")
        root.addWidget(credit)

    def _pick_dir(self, edit):
        d = QFileDialog.getExistingDirectory(self, self.tr("dan_browse"),
                                             edit.text() or self.start_dir)
        if d:
            edit.setText(d)

    def _pick_file(self, edit, flt):
        f, _ = QFileDialog.getOpenFileName(self, self.tr("dan_browse"),
                                           edit.text() or self.start_dir, flt)
        if f:
            edit.setText(f)

    def _build_gen_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        hint = QLabel(self.tr("dan_gen_hint"))
        hint.setStyleSheet("color:#aaa;")
        v.addWidget(hint)
        form = QFormLayout()
        self.gen_url = QLineEdit()
        self.gen_url.setPlaceholderText(
            "https://wikiwiki.jp/taiko-fumen/%E6%AE%B5%E4%BD%8D%E9%81%93%E5%A0%B4")
        form.addRow(self.tr("dan_gen_url"), self.gen_url)
        self.gen_out = QLineEdit()
        form.addRow(self.tr("dan_out"), self._with_browse(self.gen_out, lambda: self._pick_dir(self.gen_out)))
        self.gen_songs = QLineEdit()
        form.addRow(self.tr("dan_songs"), self._with_browse(self.gen_songs, lambda: self._pick_dir(self.gen_songs)))
        v.addLayout(form)
        self.gen_btn = QPushButton(self.tr("dan_gen_run"))
        self.gen_btn.setStyleSheet(
            "QPushButton{background:#43A047;color:white;font-weight:bold;padding:8px;border-radius:8px;}"
            "QPushButton:hover{background:#388E3C;} QPushButton:disabled{background:#7c7c7c;}")
        self.gen_btn.clicked.connect(self.run_gen)
        v.addWidget(self.gen_btn)
        v.addStretch()
        return w

    def _build_conv_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        hint = QLabel(self.tr("dan_conv_hint"))
        hint.setStyleSheet("color:#aaa;")
        v.addWidget(hint)
        form = QFormLayout()
        self.conv_tja = QLineEdit()
        form.addRow(self.tr("dan_conv_tja"),
                    self._with_browse(self.conv_tja,
                                      lambda: self._pick_file(self.conv_tja, "TJA (*.tja)")))
        self.conv_out = QLineEdit()
        form.addRow(self.tr("dan_out"), self._with_browse(self.conv_out, lambda: self._pick_dir(self.conv_out)))
        self.conv_songs = QLineEdit()
        form.addRow(self.tr("dan_songs_opt"), self._with_browse(self.conv_songs, lambda: self._pick_dir(self.conv_songs)))
        v.addLayout(form)
        self.conv_btn = QPushButton(self.tr("dan_conv_run"))
        self.conv_btn.setStyleSheet(
            "QPushButton{background:#43A047;color:white;font-weight:bold;padding:8px;border-radius:8px;}"
            "QPushButton:hover{background:#388E3C;} QPushButton:disabled{background:#7c7c7c;}")
        self.conv_btn.clicked.connect(self.run_conv)
        v.addWidget(self.conv_btn)
        v.addStretch()
        return w

    def _with_browse(self, edit, cb):
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(edit, 1)
        b = QPushButton(self.tr("dan_browse"))
        b.clicked.connect(cb)
        h.addWidget(b)
        return box

    def _busy(self, on):
        self.gen_btn.setEnabled(not on)
        self.conv_btn.setEnabled(not on)

    def run_gen(self):
        url = self.gen_url.text().strip()
        out = self.gen_out.text().strip()
        if not url:
            QMessageBox.warning(self, self.tr("dan_title"), self.tr("dan_need_url"))
            return
        if not out:
            QMessageBox.warning(self, self.tr("dan_title"), self.tr("dan_need_out"))
            return
        self._busy(True)
        self.log_view.appendPlainText("▶ " + self.tr("dan_running"))
        local_db = os.path.abspath(LOCAL_DB_PATH) if os.path.isfile(LOCAL_DB_PATH) else ""
        self._thread = DanGenThread(url, out, self.gen_songs.text().strip(), local_db)
        self._thread.log.connect(self.log_view.appendPlainText)
        self._thread.done.connect(self._on_done)
        self._thread.start()

    def run_conv(self):
        tja = self.conv_tja.text().strip()
        out = self.conv_out.text().strip()
        if not tja:
            QMessageBox.warning(self, self.tr("dan_title"), self.tr("dan_need_tja"))
            return
        if not out:
            QMessageBox.warning(self, self.tr("dan_title"), self.tr("dan_need_out"))
            return
        self._busy(True)
        self.log_view.appendPlainText("▶ " + self.tr("dan_running"))
        self._thread = DanConvThread(tja, out, self.conv_songs.text().strip())
        self._thread.log.connect(self.log_view.appendPlainText)
        self._thread.done.connect(self._on_done)
        self._thread.start()

    def _on_done(self, ok, info):
        self._busy(False)
        if ok:
            self.log_view.appendPlainText("✓ " + self.tr("dan_done"))
            QMessageBox.information(self, self.tr("dan_title"), self.tr("dan_done"))
        else:
            self.log_view.appendPlainText("✗ " + info)
            QMessageBox.critical(self, self.tr("dan_title"), self.tr("dan_fail", e=info))


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
        self.meta_map = self.load_meta_map()
        self.all_songs = []          # 最近一次搜尋的完整結果（篩選前）
        self.dl_thread = None

        self.song_model = SongModel(self.tr, self.jp_map, self.meta_map)
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

    def load_meta_map(self):
        """讀取 BPM / 五大難度等級，鍵同 jp_map（檔名 stem 優先、title 備援）。
        舊版 ese_local.db 可能沒有難度欄位，故先檢查欄位存在與否再查詢。"""
        m = {}
        if not self.has_local:
            return m
        try:
            conn = sqlite3.connect(LOCAL_DB_PATH)
            cols = {r[1] for r in conn.execute("PRAGMA table_info(local_songs)")}
            lvl_cols = [c for c in ("level_easy", "level_normal", "level_hard",
                                    "level_oni", "level_ura") if c in cols]
            sel = ["title", "file_name", "bpm"] + lvl_cols
            rows = conn.execute(f"SELECT {', '.join(sel)} FROM local_songs").fetchall()
            conn.close()

            def to_meta(row):
                d = {"bpm": (row[2] or "").strip()}
                for i, c in enumerate(lvl_cols):
                    d[c] = row[3 + i]
                return d

            def has_levels(row):
                return any(row[3 + i] is not None for i in range(len(lvl_cols)))

            # 同一檔名可能有多筆（例：舊的本機掃描列 + 遠端列），其中只有一筆帶
            # 難度。把「有難度」的排前面，setdefault 才會選到正確那筆而非空的。
            rows = sorted(rows, key=lambda r: not has_levels(r))

            for row in rows:                       # 先放檔名（主鍵）
                fn = row[1]
                if fn:
                    m.setdefault(os.path.splitext(fn)[0], to_meta(row))
            for row in rows:                       # 再用 title 補洞（不覆蓋）
                t = row[0]
                if t:
                    m.setdefault(t, to_meta(row))
        except Exception as e:
            print("load_meta_map:", e)
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
        self.dan_btn = QPushButton(self.tr("dan_btn"))
        self.dan_btn.clicked.connect(self.open_dan_tools)
        self.yatai_btn = QPushButton(self.tr("yatai_btn"))
        self.yatai_btn.clicked.connect(self.open_yatai_boxdef)
        self.missing_btn = QPushButton(self.tr("check_missing"))
        self.missing_btn.clicked.connect(self.check_missing)
        self.official_btn = QPushButton(self.tr("official"))
        self.official_btn.clicked.connect(lambda: webbrowser.open("https://taiko.ac"))
        self.credits_btn = QPushButton(self.tr("credits_btn"))
        self.credits_btn.clicked.connect(self.open_credits)
        top.addWidget(self.db_update_btn)
        top.addWidget(self.boxdef_btn)
        top.addWidget(self.dan_btn)
        top.addWidget(self.yatai_btn)
        top.addWidget(self.missing_btn)
        top.addWidget(self.official_btn)
        top.addWidget(self.credits_btn)
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

        # filter row：BPM 區間 + 難度等級篩選（依本地資料庫的 BPM/難度）
        fr = QHBoxLayout()
        fr.addWidget(QLabel("🎚 " + self.tr("f_filter") + ":"))
        fr.addWidget(QLabel(self.tr("f_bpm")))
        self.bpm_min = QSpinBox(); self.bpm_min.setRange(0, 999)
        self.bpm_min.setSpecialValueText(self.tr("f_any"))   # 0 顯示為「不限」
        self.bpm_max = QSpinBox(); self.bpm_max.setRange(0, 999)
        self.bpm_max.setSpecialValueText(self.tr("f_any"))
        fr.addWidget(self.bpm_min); fr.addWidget(QLabel("–")); fr.addWidget(self.bpm_max)
        fr.addSpacing(16)
        fr.addWidget(QLabel(self.tr("f_diff")))
        self.diff_combo = QComboBox()
        self.diff_combo.addItem(self.tr("diff_all"), None)
        for key, col in (("c_easy", "level_easy"), ("c_normal", "level_normal"),
                         ("c_hard", "level_hard"), ("c_oni", "level_oni"),
                         ("c_ura", "level_ura")):
            self.diff_combo.addItem(self.tr(key), col)
        fr.addWidget(self.diff_combo)
        fr.addWidget(QLabel(self.tr("f_level")))
        self.lv_min = QSpinBox(); self.lv_min.setRange(0, 20)
        self.lv_min.setSpecialValueText(self.tr("f_any"))
        self.lv_max = QSpinBox(); self.lv_max.setRange(0, 20)
        self.lv_max.setSpecialValueText(self.tr("f_any"))
        fr.addWidget(self.lv_min); fr.addWidget(QLabel("–")); fr.addWidget(self.lv_max)
        self.reset_filter_btn = QPushButton(self.tr("f_reset"))
        self.reset_filter_btn.clicked.connect(self.reset_filters)
        fr.addWidget(self.reset_filter_btn)
        fr.addStretch()
        for w in (self.bpm_min, self.bpm_max, self.lv_min, self.lv_max):
            w.valueChanged.connect(lambda _=None: self.apply_filters())
        self.diff_combo.currentIndexChanged.connect(lambda _=None: self.apply_filters())
        root.addLayout(fr)

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
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)   # ✓
        hh.setSectionResizeMode(1, QHeaderView.Stretch)            # 歌名
        hh.setSectionResizeMode(2, QHeaderView.Stretch)            # 日文
        for c in range(3, len(SongModel.COLS)):                    # 分類/BPM/難度×5/檔案
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
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
        self.all_songs = []
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
        self.all_songs = songs
        self.search_btn.setEnabled(True)
        self.apply_filters()

    @staticmethod
    def _bpm_val(s):
        """從 BPM 字串取出數值（取第一個數字；無則 None）。"""
        if not s:
            return None
        m = re.search(r"\d+(?:\.\d+)?", str(s))
        return float(m.group()) if m else None

    def reset_filters(self):
        for w in (self.bpm_min, self.bpm_max, self.lv_min, self.lv_max):
            w.blockSignals(True); w.setValue(0); w.blockSignals(False)
        self.diff_combo.blockSignals(True)
        self.diff_combo.setCurrentIndex(0)
        self.diff_combo.blockSignals(False)
        self.apply_filters()

    def apply_filters(self):
        bmin, bmax = self.bpm_min.value(), self.bpm_max.value()
        lmin, lmax = self.lv_min.value(), self.lv_max.value()
        diff_col = self.diff_combo.currentData()
        bpm_active = bmin > 0 or bmax > 0
        lvl_active = lmin > 0 or lmax > 0 or diff_col is not None

        if not bpm_active and not lvl_active:
            songs = self.all_songs                       # 無篩選：全部顯示（含無中繼資料者）
        else:
            diff_cols = [diff_col] if diff_col else list(SongModel.LEVEL_COLS.values())
            songs = []
            for s in self.all_songs:
                meta = self.meta_map.get(s["song_name"])
                if not meta:
                    continue                             # 篩選啟用但無資料 → 排除
                if bpm_active:
                    bpm = self._bpm_val(meta.get("bpm"))
                    if bpm is None:
                        continue
                    if bmin and bpm < bmin:
                        continue
                    if bmax and bpm > bmax:
                        continue
                if lvl_active and (lmin or lmax):
                    lvls = [meta.get(c) for c in diff_cols]
                    lvls = [v for v in lvls if v is not None]
                    if not any((not lmin or v >= lmin) and (not lmax or v <= lmax)
                               for v in lvls):
                        continue
                elif diff_col is not None:
                    # 只選了難度、沒設等級 → 要求該難度存在
                    if meta.get(diff_col) is None:
                        continue
                songs.append(s)

        self.song_model.set_songs(songs)
        self.count_label.setText(self.tr("total", n=len(songs)))
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

    def open_dan_tools(self):
        start = self.dir_edit.text() if os.path.isdir(self.dir_edit.text()) else os.getcwd()
        DanToolsDialog(self, self.tr, start).exec()

    def open_yatai_boxdef(self):
        YataiBoxDefDialog(self, self.tr).exec()

    def open_credits(self):
        box = QMessageBox(self)
        box.setWindowTitle(self.tr("credits_title"))
        box.setText(self.tr("credits_body"))
        box.setIcon(QMessageBox.Information)
        box.exec()

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
        self.meta_map = self.load_meta_map()
        self.song_model.jp_map = self.jp_map
        self.song_model.meta_map = self.meta_map
        if self.song_model.songs:
            self.song_model.dataChanged.emit(
                self.song_model.index(0, 2),
                self.song_model.index(self.song_model.rowCount() - 1,
                                      self.song_model.columnCount() - 1),
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
            self.meta_map = self.load_meta_map()
            self.song_model.jp_map = self.jp_map
            self.song_model.meta_map = self.meta_map
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
    # 打包後自我檢測：確認 lxml/dan_tools 等相依在 frozen exe 內可用（不開視窗）
    if "--selftest-dan" in sys.argv:
        from lxml import html as _h
        doc = _h.fromstring("<table><tr><td>魂ゲージ</td></tr></table>")
        ok = bool(doc.xpath("//td")) and hasattr(dan_tools, "generate_dan_from_wiki")
        print("DAN_SELFTEST_OK" if ok else "DAN_SELFTEST_FAIL")
        sys.exit(0 if ok else 1)

    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create("Fusion"))
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
