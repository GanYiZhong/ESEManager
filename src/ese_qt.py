"""
ESEManager main window (PySide6).

- Song list: QTableView with a custom model, so thousands of songs scroll instantly.
- Download monitor: overall progress with speed/ETA, per-file status, live log,
  and a failed list with one-click retry.

Other pieces live in sibling modules: appconfig (paths/URLs), i18n (strings),
models (table models), workers (background threads), boxdef (box.def generators)
and dialogs (box.def editor, YataiDON generator, Dan tools).
"""

import os
import re
import sys
import sqlite3
import subprocess
import webbrowser

try:
    import tomllib
except ImportError:
    import tomli as tomllib
import tomli_w

from PySide6.QtCore import Qt, QTimer, QProcess
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QTableView, QHeaderView, QSpinBox,
    QFileDialog, QPlainTextEdit, QProgressBar, QTabWidget, QListWidget,
    QListWidgetItem, QMessageBox, QSplitter, QAbstractItemView, QStyleFactory,
    QGroupBox
)

import dan_tools  # Dan generator/convertor (ported from bluetaiko/SongConvertor)
from appconfig import (APP_DIR, CONFIG_FILE, DB_PATH, LOCAL_DB_PATH,
                       DEFAULT_DOWNLOAD_DIR, resolve_dir, safe_join, UnsafePathError)
from i18n import TR, CATEGORY_NAMES, detect_system_lang
from models import SongModel, DownloadModel, human_speed, human_eta
from workers import (SearchThread, CheckUpdatesThread, DownloadThread, DBBuildThread,
                     VersionThread, DBUpdateThread, MetaLoadThread, load_jp_map,
                     load_meta_map)
from dialogs import BoxDefDialog, DanToolsDialog, YataiBoxDefDialog
from notify import Notifier, set_app_icon


# ---------------------------------------------------------------- 主視窗
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = self.load_config()
        self.download_dir = resolve_dir(
            self.config.get("download", {}).get("directory", DEFAULT_DOWNLOAD_DIR))
        # ui_language 偏好可為 "auto"（依系統語言）或固定的 zh_TW/en/ja；新安裝預設 auto
        self.lang_pref = self.config.get("display", {}).get("ui_language", "auto")
        self.lang = detect_system_lang() if self.lang_pref == "auto" else self.lang_pref
        self.has_local = os.path.exists(LOCAL_DB_PATH)
        self.jp_map = load_jp_map()
        self.meta_map = load_meta_map()
        self.all_songs = []          # 最近一次搜尋的完整結果（篩選前）
        self.dl_thread = None
        self._search = None
        self._search_seq = 0         # newest search wins; stale results are ignored
        self._threads = []           # every worker started, so closeEvent can stop them

        self.song_model = SongModel(self.tr, self.jp_map, self.meta_map)
        self.dl_model = DownloadModel(self.tr)

        self.build_ui()
        self.notifier = Notifier(self)
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
        return {"download": {"directory": DEFAULT_DOWNLOAD_DIR, "workers": 5},
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
        self.updates_btn = QPushButton(self.tr("check_updates"))
        self.updates_btn.clicked.connect(self.check_updates)
        self.official_btn = QPushButton(self.tr("official"))
        self.official_btn.clicked.connect(lambda: webbrowser.open("https://taiko.ac"))
        self.credits_btn = QPushButton(self.tr("credits_btn"))
        self.credits_btn.clicked.connect(self.open_credits)
        top.addWidget(self.db_update_btn)
        top.addWidget(self.boxdef_btn)
        top.addWidget(self.dan_btn)
        top.addWidget(self.yatai_btn)
        top.addWidget(self.missing_btn)
        top.addWidget(self.updates_btn)
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
        # First-run / empty-database hint, hidden once a song database exists.
        self.empty_hint = QLabel(self.tr("empty_hint"))
        self.empty_hint.setWordWrap(True)
        self.empty_hint.setStyleSheet(
            "QLabel{background:#FFF3CD;color:#5c4400;border:1px solid #E0C36C;"
            "border-radius:6px;padding:8px;}")
        sb.addWidget(self.empty_hint)
        self.refresh_empty_hint()
        self.table = QTableView()
        self.table.setModel(self.song_model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)  # no initial sort
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
        if os.path.exists(DB_PATH):      # connect() would create an empty file
            try:
                conn = sqlite3.connect(DB_PATH)
                try:
                    for (name,) in conn.execute(
                            "SELECT DISTINCT name FROM categories ORDER BY name"):
                        self.cat_combo.addItem(CATEGORY_NAMES.get(name, name), name)
                finally:
                    conn.close()
            except Exception as e:
                print("load_categories:", e)
        self.cat_combo.blockSignals(False)

    def has_song_db(self):
        return os.path.exists(DB_PATH) and os.path.getsize(DB_PATH) > 0

    def refresh_empty_hint(self):
        self.empty_hint.setVisible(not self.has_song_db())

    def _track(self, thread):
        """Remember a worker so closeEvent can stop it; forget it when it ends."""
        self._threads.append(thread)
        thread.finished.connect(lambda t=thread: self._threads.remove(t)
                                if t in self._threads else None)
        return thread

    # ---- search
    def do_search(self):
        kw = self.search_edit.text().strip()
        cat = self.cat_combo.currentData()
        self._run_search(kw, cat)

    def show_all(self):
        self.search_edit.clear()
        self.cat_combo.blockSignals(True)
        self.cat_combo.setCurrentIndex(0)
        self.cat_combo.blockSignals(False)
        self._run_search("", None)

    def clear_search(self):
        self.search_edit.clear()
        self.cat_combo.blockSignals(True)
        self.cat_combo.setCurrentIndex(0)
        self.cat_combo.blockSignals(False)
        self._search_seq += 1          # drop any search still in flight
        self.all_songs = []
        self.song_model.set_songs([])
        self.count_label.setText(self.tr("total", n=0))
        self.update_sel_count()

    def _run_search(self, kw, cat):
        if not self.has_song_db():
            self.refresh_empty_hint()
            self.count_label.setText(self.tr("total", n=0))
            return
        # Each search gets a sequence number; results from an older search that
        # finishes late are ignored, so typing quickly never shows stale rows.
        self._search_seq += 1
        self.count_label.setText("🔍 ...")
        t = self._track(SearchThread(kw, cat, self.has_local, seq=self._search_seq))
        t.done.connect(self.on_search_done)
        t.fail.connect(self.on_search_fail)
        self._search = t
        t.start()

    def on_search_done(self, seq, songs):
        if seq != self._search_seq:
            return
        self.all_songs = songs
        self.apply_filters()

    def on_search_fail(self, seq, err):
        if seq == self._search_seq:
            self.count_label.setText("✗ " + err)

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
        cur = self.song_model.is_checked(row)
        self.song_model.setData(self.song_model.index(row, 0),
                                Qt.Unchecked if cur else Qt.Checked, Qt.CheckStateRole)

    def update_sel_count(self, *args):
        self.sel_label.setText(self.tr("selected", n=len(self.song_model.checked)))

    # ---- download
    LARGE_DOWNLOAD = 300     # ask before starting more files than this

    def start_download_selected(self):
        songs = self.song_model.selected_songs()
        if not songs:
            QMessageBox.warning(self, self.tr("monitor"), self.tr("no_selection"))
            return
        files = [(s, f) for s in songs for f in s["files"]]
        if len(files) > self.LARGE_DOWNLOAD and QMessageBox.question(
                self, self.tr("monitor"),
                self.tr("dl_confirm_many", n=len(songs), f=len(files))) != QMessageBox.Yes:
            return
        self.start_download(files)

    def start_download(self, files, overwrite=False):
        if self.dl_thread and self.dl_thread.isRunning():
            QMessageBox.warning(self, self.tr("monitor"), self.tr("dl_busy"))
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
        self.log_view.appendPlainText(self.tr("log_dl_start", n=len(files)))

        self.dl_thread = self._track(DownloadThread(
            files, resolve_dir(self.dir_edit.text()), self.workers_spin.value(),
            overwrite=overwrite, tr=self.tr))
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
            self.log_view.appendPlainText(self.tr("log_dl_stopping"))

    def on_download_done(self, dl, skip, fail, total):
        if hasattr(self, "dl_timer"):
            self.dl_timer.stop()
        self.refresh_progress()   # 最後一次刷新，確保畫面到位
        self.download_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.pause_btn.setText(self.tr("pause"))
        self.overall_label.setText(self.tr("ready"))
        stopped = self.dl_thread.stopped
        self.log_view.appendPlainText(self.tr("log_dl_done", d=dl, s=skip, f=fail))
        # 填入失敗清單（停止時被取消的檔案也列入，可一鍵重試）
        self.fail_list.clear()
        for song, f in self.dl_thread.failed:
            it = QListWidgetItem(f"{f['filename']}  ({song['song_name']})")
            it.setData(Qt.UserRole, (song, f))
            self.fail_list.addItem(it)
        self.retry_btn.setEnabled(fail > 0)
        if fail > 0:
            self.tabs.setCurrentIndex(2)
        if self._closing:
            return
        key = "stopped_msg" if stopped else "done_msg"
        text = self.tr(key, d=dl, s=skip, f=fail, t=total)
        self.notifier.notify(self.tr("title"), text)
        QMessageBox.information(self, self.tr("monitor"), text)

    def retry_failed(self):
        files = [self.fail_list.item(i).data(Qt.UserRole)
                 for i in range(self.fail_list.count())]
        if files:
            self.start_download(files)

    # ---- check missing
    def check_missing(self):
        if not self.has_song_db():
            QMessageBox.information(self, self.tr("check_missing"), self.tr("empty_hint"))
            return
        self.missing_btn.setEnabled(False)
        t = self._track(SearchThread("", None, self.has_local))
        t.done.connect(lambda _seq, songs: self.on_missing_loaded(songs))
        t.fail.connect(lambda _seq, e: (QMessageBox.critical(self, self.tr("check_missing"), e),
                                        self.missing_btn.setEnabled(True)))
        self._miss = t
        t.start()

    def on_missing_loaded(self, songs):
        self.missing_btn.setEnabled(True)
        ddir = resolve_dir(self.dir_edit.text())
        missing = []
        for s in songs:
            for f in s["files"]:
                try:
                    path = safe_join(ddir, f["file_path"])
                except UnsafePathError:
                    continue
                if not os.path.exists(path):
                    missing.append(s)
                    break
        if not missing:
            QMessageBox.information(self, self.tr("check_missing"), self.tr("missing_none"))
            return
        files = [(s, f) for s in missing for f in s["files"]]
        if QMessageBox.question(
                self, self.tr("check_missing"),
                self.tr("missing_found", n=len(missing), f=len(files))) == QMessageBox.Yes:
            self.song_model.set_songs(missing)
            self.song_model.set_all(True)
            self.count_label.setText(self.tr("total", n=len(missing)))
            self.start_download(files)

    # ---- check updates（比對 git blob sha，找出上游已更新的已下載檔案）
    def check_updates(self):
        ddir = resolve_dir(self.dir_edit.text())
        if not os.path.isdir(ddir):
            QMessageBox.warning(self, self.tr("check_updates"), self.tr("boxdef_no_dir"))
            return
        self.updates_btn.setEnabled(False)
        self.log_view.appendPlainText("▶ " + self.tr("upd_checking"))
        t = self._track(CheckUpdatesThread(ddir, None))
        t.progress.connect(
            lambda d, n: self.count_label.setText(self.tr("upd_progress", d=d, t=n)))
        t.done.connect(self.on_updates_loaded)
        t.fail.connect(self._on_updates_fail)
        self._upd = t
        t.start()

    def _on_updates_fail(self, e):
        self.updates_btn.setEnabled(True)
        if e == "__NO_SHA__":
            QMessageBox.information(self, self.tr("check_updates"), self.tr("upd_no_sha"))
        else:
            QMessageBox.critical(self, self.tr("check_updates"), e)

    def on_updates_loaded(self, songs):
        self.updates_btn.setEnabled(True)
        if not songs:
            QMessageBox.information(self, self.tr("check_updates"), self.tr("upd_none"))
            return
        files = [(s, f) for s in songs for f in s["files"]]
        if QMessageBox.question(
                self, self.tr("check_updates"),
                self.tr("upd_found", n=len(songs), f=len(files))) == QMessageBox.Yes:
            self.song_model.set_songs(songs)
            self.song_model.set_all(True)
            self.count_label.setText(self.tr("total", n=len(songs)))
            self.start_download(files, overwrite=True)   # 覆寫既有檔案

    # ---- misc
    def browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, self.tr("browse"),
                                             resolve_dir(self.dir_edit.text()))
        if d:
            self.dir_edit.setText(d)
            self.save_config()

    def open_dir(self):
        d = resolve_dir(self.dir_edit.text())
        if os.path.isdir(d):
            if sys.platform == "win32":
                os.startfile(d)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", d])
            else:
                subprocess.Popen(["xdg-open", d])

    def _tool_start_dir(self):
        d = resolve_dir(self.dir_edit.text())
        return d if os.path.isdir(d) else APP_DIR

    # ---- box.def 編輯器
    def open_boxdef(self):
        BoxDefDialog(self, self._tool_start_dir(), self.tr).exec()

    def open_dan_tools(self):
        DanToolsDialog(self, self.tr, self._tool_start_dir()).exec()

    def open_yatai_boxdef(self):
        YataiBoxDefDialog(self, self.tr).exec()

    def open_credits(self):
        box = QMessageBox(self)
        box.setWindowTitle(self.tr("credits_title"))
        box.setText(self.tr("credits_body"))
        box.setIcon(QMessageBox.Information)
        box.exec()

    # ---- 一鍵更新資料庫（歌曲清單 + 日文標題；整合自 update_databases.bat）
    def _db_busy(self):
        return any(t.isRunning() for t in (getattr(self, "_db_thread", None),
                                           getattr(self, "_dbu", None)) if t)

    def update_database(self):
        if self._db_busy():
            QMessageBox.warning(self, self.tr("db_update"), self.tr("db_building"))
            return
        if QMessageBox.question(self, self.tr("db_update"),
                                self.tr("db_confirm")) != QMessageBox.Yes:
            return

        # 解析 git；Windows 沒有就詢問是否下載可攜版；其他平台直接提示手動安裝
        from ese_scraper_git_v2 import find_git
        git_exe = find_git()
        download_git = False
        if not git_exe:
            if sys.platform == "win32":
                if QMessageBox.question(self, "Git", self.tr("db_no_git_q")) == QMessageBox.Yes:
                    download_git = True
                else:
                    QMessageBox.information(self, "Git", self.tr("db_no_git_fail"))
                    return
            else:
                QMessageBox.information(self, "Git", self.tr("db_no_git_fail"))
                return

        self.db_update_btn.setEnabled(False)
        self.tabs.setCurrentIndex(1)   # 切到 Log 分頁
        self.overall_label.setText(self.tr("db_building"))
        self.log_view.appendPlainText("——— " + self.tr("db_building") + " ———")
        self._db_thread = self._track(DBBuildThread(git_exe, download_git=download_git))
        self._db_thread.log.connect(self.log_view.appendPlainText)
        self._db_thread.done.connect(self.on_db_build_done)
        self._db_thread.start()

    def on_db_build_done(self, ok, info):
        self.db_update_btn.setEnabled(True)
        self.overall_label.setText(self.tr("ready"))
        if ok:
            text = self.tr("db_done")
        elif info == "NOGIT":
            text = self.tr("db_no_git_fail")
        else:
            text = self.tr("db_fail", e=info)
        self.notifier.notify(self.tr("db_update"), text)
        if not ok:
            if info == "NOGIT":
                QMessageBox.critical(self, "Git", self.tr("db_no_git_fail"))
            else:
                QMessageBox.critical(self, self.tr("db_update"), self.tr("db_fail", e=info))
            return
        self.reload_databases(self.tr("db_done"))

    def reload_databases(self, done_msg=None):
        """Reload categories and the Japanese-title/level maps after a DB change.
        The maps load on a worker thread so the window stays responsive."""
        self.load_categories()
        self.refresh_empty_hint()
        self.has_local = os.path.exists(LOCAL_DB_PATH)
        self.count_label.setText(self.tr("db_reloading"))

        def apply(jp_map, meta_map):
            self.jp_map, self.meta_map = jp_map, meta_map
            self.song_model.jp_map = jp_map
            self.song_model.meta_map = meta_map
            if self.song_model.songs:
                self.song_model.dataChanged.emit(
                    self.song_model.index(0, 2),
                    self.song_model.index(self.song_model.rowCount() - 1,
                                          self.song_model.columnCount() - 1),
                    [Qt.DisplayRole])
            self.count_label.setText(self.tr("total", n=self.song_model.rowCount()))
            if done_msg and not self._closing:
                QMessageBox.information(self, self.tr("db_update"), done_msg)

        t = self._track(MetaLoadThread())
        t.done.connect(apply)
        self._meta = t
        t.start()

    def change_lang(self, *_):
        pref = self.lang_combo.currentData() or "auto"
        if pref == self.lang_pref:
            return
        self.lang_pref = pref
        self.lang = detect_system_lang() if pref == "auto" else pref
        self.save_config()
        # 有下載/資料庫工作進行中就別重啟，避免中斷；下次啟動再套用
        busy = (self.dl_thread and self.dl_thread.isRunning()) or self._db_busy()
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
        QProcess.startDetached(program, args, APP_DIR)
        self.close()

    # ---- prebuilt database update (GitHub Pages)
    def check_db_update(self):
        self._ver = self._track(VersionThread())
        self._ver.result.connect(self.on_version)
        self._ver.start()

    def on_version(self, remote, local):
        if not remote or remote == local or self._db_busy() or self._closing:
            return
        if not self.has_song_db():
            msg = self.tr("dbv_first", v=remote)
        else:
            msg = self.tr("dbv_found", cur=local or self.tr("dbv_none"), new=remote)
        if QMessageBox.question(self, self.tr("dbv_title"), msg) == QMessageBox.Yes:
            self.db_update_btn.setEnabled(False)
            self.overall_label.setText(self.tr("db_building"))
            self._dbu = self._track(DBUpdateThread(remote, tr=self.tr))
            self._dbu.log.connect(self.log_view.appendPlainText)
            self._dbu.done.connect(self.on_db_updated)
            self.tabs.setCurrentIndex(1)
            self._dbu.start()

    def on_db_updated(self, ok, msg):
        self.db_update_btn.setEnabled(True)
        self.overall_label.setText(self.tr("ready"))
        self.notifier.notify(self.tr("dbv_title"),
                             self.tr("dbv_ok") if ok else self.tr("db_fail", e=msg))
        if ok:
            self.reload_databases(self.tr("dbv_ok"))
        elif not self._closing:
            QMessageBox.critical(self, self.tr("dbv_title"), self.tr("db_fail", e=msg))

    # ---- shutdown
    _closing = False

    def closeEvent(self, event):
        """Stop background work before the window goes away, so no QThread is
        destroyed while running and no half-written file is left behind."""
        busy = [t for t in self._threads if t.isRunning()]
        if busy and not self._closing:
            if self.dl_thread in busy or self._db_busy():
                if QMessageBox.question(self, self.tr("title"),
                                        self.tr("quit_busy")) != QMessageBox.Yes:
                    event.ignore()
                    return
        self._closing = True
        if self.dl_thread and self.dl_thread.isRunning():
            self.dl_thread.stop()
        if hasattr(self, "dl_timer"):
            self.dl_timer.stop()
        self.save_config()
        for t in list(self._threads):
            if t.isRunning():
                # Downloads stop within one chunk; a git/DB build cannot be
                # interrupted mid-step, so give it a bounded wait, then leave it.
                if not t.wait(8000):
                    print(f"closeEvent: {type(t).__name__} still running; exiting anyway")
        event.accept()


def main():
    # 打包後自我檢測：確認 lxml/dan_tools 等相依在 frozen exe 內可用（不開視窗）
    if "--selftest-dan" in sys.argv:
        from lxml import html as _h
        doc = _h.fromstring("<table><tr><td>魂ゲージ</td></tr></table>")
        ok = bool(doc.xpath("//td")) and hasattr(dan_tools, "generate_dan_from_wiki")
        print("DAN_SELFTEST_OK" if ok else "DAN_SELFTEST_FAIL")
        sys.exit(0 if ok else 1)

    # Relative paths (git clone, portable git, user-entered folders) resolve
    # next to the app no matter where it was launched from.
    os.chdir(APP_DIR)
    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create("Fusion"))
    set_app_icon(app)
    w = MainWindow()
    w.show()
    rc = app.exec()
    if any(t.isRunning() for t in w._threads):
        # A git/DB step that ignored the shutdown wait: exit without running
        # QThread destructors (which would abort on a running thread).
        sys.stdout.flush() if sys.stdout else None
        os._exit(rc)
    sys.exit(rc)


if __name__ == "__main__":
    main()
