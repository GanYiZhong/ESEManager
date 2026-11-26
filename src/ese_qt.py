"""
ESEManager main window (PySide6).

- Song list: QTableView with a custom model, so thousands of songs scroll instantly.
- Download monitor: overall progress with speed/ETA, per-file status, live log,
  and a failed list with one-click retry.

Other pieces live in sibling modules: appconfig (paths/URLs), i18n (strings),
models (table models), workers (background threads) and theme/notify.
"""

import os
import re
import sys

try:
    import tomllib
except ImportError:
    import tomli as tomllib
import tomli_w

from PySide6.QtCore import Qt, QTimer, QProcess, QEvent
from PySide6.QtGui import (QAction, QKeySequence, QShortcut, QGuiApplication, QFont,
                           QFontDatabase)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QTableView, QHeaderView, QSpinBox,
    QFileDialog, QPlainTextEdit, QProgressBar, QTabWidget, QListWidget,
    QListWidgetItem, QMessageBox, QSplitter, QAbstractItemView, QStyleFactory,
    QDialog, QFrame, QFormLayout, QMenu, QToolButton, QWidgetAction
)

from appconfig import (APP_DIR, APP_VERSION, RELEASES_URL, CONFIG_FILE,
                       DEFAULT_DOWNLOAD_DIR, resolve_dir)
from i18n import TR, CATEGORY_NAMES, detect_system_lang
import theme  # light/dark palette and style-sheet helpers
import icons  # themed SVG icons
import core
from core import load_jp_map, load_meta_map, read_local_version, human_speed, human_eta
from models import SongModel, DownloadModel
from workers import (SearchThread, CheckUpdatesThread, DownloadThread,
                     VersionThread, DBUpdateThread, MetaLoadThread, AppUpdateThread,
                     VersionSortingThread, AppSelfUpdateThread)
from notify import Notifier, set_app_icon


webbrowser = core.LazyModule("webbrowser")   # ~60 ms we do not need at startup


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
        # display.theme: "auto" (follow OS) | "light" | "dark"
        self.theme_pref = self.config.get("display", {}).get("theme", "auto")
        # display.font_scale: UI font size in percent (90/100/115/130), app-wide
        self.font_scale = self._valid_font_scale(
            self.config.get("display", {}).get("font_scale", 100))
        self.apply_font_scale(self.font_scale)
        self.jp_map = load_jp_map()
        self.meta_map = load_meta_map()
        self.all_songs = []          # 最近一次搜尋的完整結果（篩選前）
        self.dl_thread = None
        self._search = None
        self._search_seq = 0         # newest search wins; stale results are ignored
        self._threads = []           # every worker started, so closeEvent can stop them
        self._db_version = read_local_version()
        self._total_songs = None     # song count, shown in the status bar after a search
        self._unfiltered_seq = None  # seq of the search that was not filtered by keyword/category

        # Live search: restart this single-shot timer on every keystroke.
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(self.SEARCH_DELAY_MS)
        self._search_timer.timeout.connect(self.do_search)

        self.song_model = SongModel(self.tr, self.jp_map, self.meta_map)
        self.dl_model = DownloadModel(self.tr)

        self.build_menus()          # created once; texts refreshed in retranslate_chrome
        self.build_status_bar()
        self.build_shortcuts()
        self.build_ui()
        self.notifier = Notifier(self)
        self.load_categories()
        QTimer.singleShot(1200, self.check_db_update)
        QTimer.singleShot(3000, self.check_app_update)
        QTimer.singleShot(500, self._report_failed_update)

    SEARCH_DELAY_MS = 300
    FONT_SCALES = (90, 100, 115, 130)

    @classmethod
    def _valid_font_scale(cls, v):
        return v if isinstance(v, int) and not isinstance(v, bool) and v in cls.FONT_SCALES else 100

    def apply_font_scale(self, pct):
        """Scale the application font (relative to the font at first launch)
        and re-derive the pixel metrics that depend on it."""
        app = QApplication.instance()
        if app is None:
            return
        base = app.property("ese_base_font")
        if base is None:
            base = app.font()
            app.setProperty("ese_base_font", base)
        f = QFont(base)
        if base.pointSizeF() > 0:
            f.setPointSizeF(base.pointSizeF() * pct / 100)
        elif base.pixelSize() > 0:
            f.setPixelSize(max(1, round(base.pixelSize() * pct / 100)))
        app.setFont(f)
        # Item views, headers and menus carry their own platform font, so setFont()
        # on the app alone leaves them behind: push the font to every widget.
        self.setFont(f)
        for child in self.findChildren(QWidget):
            child.setFont(f)
        self.update_font_metrics()

    def update_font_metrics(self):
        """Row heights, minimum widths and bar height follow the font, not fixed
        pixels, so text stays readable at 125%/150% OS scaling and larger fonts."""
        if not hasattr(self, "dir_row"):
            return
        fm = self.table.fontMetrics()
        row = max(28, fm.height() + 14)
        self.table.verticalHeader().setDefaultSectionSize(row)
        self.dl_table.verticalHeader().setDefaultSectionSize(row)
        em = fm.horizontalAdvance("M")
        self.cat_combo.setMinimumWidth(em * 9)
        self.overall_bar.setMaximumWidth(em * 14)
        self.overall_bar.setMaximumHeight(max(18, fm.height() + 4))
        # Size the path field, not the whole row: the row also holds two
        # buttons, and the dialog grows to fit its layout.
        self.dir_edit.setMinimumWidth(em * 22)
    DEFAULT_WINDOW = (1280, 860)

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
        return {"download": {"directory": DEFAULT_DOWNLOAD_DIR, "workers": 3},
                "display": {"page_size": 20, "ui_language": "auto", "theme": "auto"}}

    @staticmethod
    def _cfg_int(d, key, default, lo):
        """Read an int from a config section; anything missing or invalid -> default."""
        v = d.get(key)
        return v if isinstance(v, int) and not isinstance(v, bool) and v >= lo else default

    def save_config(self):
        self.refresh_welcome_dir()
        prev = self.config.get("display", {})
        # Keep the last normal (not maximized) size; a maximized window would store the screen size.
        if self.isMaximized() or self.isMinimized():
            win_w = self._cfg_int(prev, "window_w", self.DEFAULT_WINDOW[0], 1)
            win_h = self._cfg_int(prev, "window_h", self.DEFAULT_WINDOW[1], 1)
        else:
            win_w, win_h = self.width(), self.height()
        cat = self.cat_combo.currentData() if hasattr(self, "cat_combo") else None
        display = {"page_size": 20, "category": cat or "", "ui_language": self.lang_pref,
                   "theme": self.theme_pref, "font_scale": self.font_scale,
                   "window_w": win_w, "window_h": win_h,
                   "monitor_open": bool(getattr(self, "monitor_btn", None)
                                        and self.monitor_btn.isChecked())}
        sizes = self.splitter.sizes() if hasattr(self, "splitter") else []
        if len(sizes) == 2 and all(s > 0 for s in sizes):
            display["splitter"] = [int(s) for s in sizes]
        elif isinstance(prev.get("splitter"), list):
            display["splitter"] = prev["splitter"]
        cfg = {
            "download": {"directory": self.dir_edit.text(),
                         "workers": self.workers_spin.value(),
                         "source": (self.source_combo.currentData()
                                    if hasattr(self, "source_combo") else "ese")},
            "display": display,
        }
        self.config = {**self.config, "display": display}
        try:
            with open(CONFIG_FILE, "wb") as f:
                tomli_w.dump(cfg, f)
        except Exception:
            core.log.warning("save_config failed", exc_info=True)

    # ---- menus, status bar, shortcuts (created once; texts via retranslate_chrome)
    def _action(self, slot):
        act = QAction(self)
        act.triggered.connect(slot)
        return act

    def build_menus(self):
        mb = self.menuBar()
        # File: maintenance actions (also on the top bar), folder, quit
        self.menu_file = mb.addMenu("")
        self.act_update_db = self._action(self.update_database)
        self.act_missing = self._action(self.check_missing)
        self.act_updates = self._action(self.check_updates)
        self.act_open_dir = self._action(self.open_dir)
        self.act_vsort = self._action(self.download_version_sorting)
        self.act_settings = self._action(self.open_settings)
        self.act_settings.setShortcut(QKeySequence("Ctrl+,"))
        self.act_quit = self._action(self.close)
        for a in (self.act_update_db, self.act_missing, self.act_updates, self.act_vsort):
            self.menu_file.addAction(a)
        self.menu_file.addSeparator()
        self.menu_file.addAction(self.act_open_dir)
        self.menu_file.addAction(self.act_settings)
        self.menu_file.addSeparator()
        self.menu_file.addAction(self.act_quit)

        # Help: contact page
        self.menu_help = mb.addMenu("")
        self.act_shortcuts = self._action(
            lambda: QMessageBox.information(self, self.tr("shortcuts"),
                                            self.tr("shortcuts_text")))
        self.menu_help.addAction(self.act_shortcuts)
        self.act_official = self._action(lambda: webbrowser.open("https://taiko.ac"))
        self.menu_help.addAction(self.act_official)

    def build_status_bar(self):
        sb = self.statusBar()
        self.count_label = QLabel(self.tr("total", n=0))   # current list / progress text
        self.db_ver_label = QLabel()
        # Shown only when GitHub has a newer release; opens the release page.
        self.app_update_btn = QPushButton()
        self.app_update_btn.setFlat(True)
        self.app_update_btn.setCursor(Qt.PointingHandCursor)
        self.app_update_btn.setStyleSheet(theme.success_text_qss())
        self.app_update_btn.hide()
        self.app_update_btn.clicked.connect(self.install_app_update)
        sb.addWidget(self.count_label)
        sb.addPermanentWidget(self.app_update_btn)
        sb.addPermanentWidget(self.db_ver_label)

    def build_shortcuts(self):
        for seq, slot in (("Ctrl+F", self._focus_search), ("Ctrl+D", self._shortcut_download),
                          ("F5", self._refresh_current)):
            sc = QShortcut(QKeySequence(seq), self)
            sc.activated.connect(slot)

    def _focus_search(self):
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    def _refresh_current(self):
        """F5: re-run the current search (also leaves a check-result view)."""
        self._search_now()

    def _check_all_visible(self):
        """Ctrl+A in the table: check every song currently listed."""
        self.table.selectAll()
        self.song_model.set_all(True)

    def _search_down(self):
        """Down in the search box: move into the table."""
        self.table.setFocus()
        if self.song_model.rowCount() and not self.table.currentIndex().isValid():
            self.table.selectRow(0)
            self.table.setCurrentIndex(self.song_model.index(0, 1))

    def _shortcut_download(self):
        # Same guard as the button: nothing to do while a download is running.
        if self.download_btn.isEnabled():
            self.start_download_selected()

    def _refresh_status(self):
        self.db_ver_label.setText(
            self.tr("mw_status_db", v=self._db_version or self.tr("dbv_none")))

    def retranslate_chrome(self):
        """Apply the current language to menus, actions and status bar."""
        self.menu_file.setTitle(self.tr("mw_menu_file"))
        self.menu_help.setTitle(self.tr("mw_menu_help"))
        self.act_update_db.setText(self.tr("db_update"))
        self.act_missing.setText(self.tr("check_missing"))
        self.act_updates.setText(self.tr("check_updates"))
        self.act_open_dir.setText(self.tr("mw_act_open_dir"))
        self.act_vsort.setText(self.tr("vsort_action"))
        self.act_vsort.setToolTip(self.tr("vsort_tip"))
        self.act_settings.setText(self.tr("mw_settings"))
        self.act_quit.setText(self.tr("mw_act_quit"))
        self.act_official.setText(self.tr("official"))
        self.act_shortcuts.setText(self.tr("shortcuts"))
        self._refresh_status()

    # ---- UI
    # Layout (compact): one top row (search, category, filter, maintenance
    # buttons), the song table filling the window, one bottom row (download
    # actions + a slim progress bar), and a download monitor that only opens
    # while downloading or when toggled. Rarely-changed settings live in a
    # Settings dialog (File > Settings).
    def build_ui(self):
        self.setWindowTitle(f"{self.tr('title')} {APP_VERSION}")
        w, h = self.DEFAULT_WINDOW
        disp = self.config.get("display", {})
        self.resize(*self._fit_to_screen(self._cfg_int(disp, "window_w", w, 640),
                                         self._cfg_int(disp, "window_h", h, 480)))
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 10, 14, 8)
        root.setSpacing(8)

        # ---- top row: search + category + filter + maintenance actions
        top = QHBoxLayout()
        top.setSpacing(8)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(self.tr("ph"))
        self._search_icon_action = None
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.returnPressed.connect(self._search_now)
        self.search_edit.textChanged.connect(lambda _=None: self._search_timer.start())
        # Esc clears the box; the debounced search then shows everything again.
        esc = QShortcut(QKeySequence(Qt.Key_Escape), self.search_edit)
        esc.setContext(Qt.WidgetShortcut)
        esc.activated.connect(self.search_edit.clear)
        down = QShortcut(QKeySequence(Qt.Key_Down), self.search_edit)
        down.setContext(Qt.WidgetShortcut)
        down.activated.connect(self._search_down)
        self.cat_combo = QComboBox()
        self.cat_combo.currentIndexChanged.connect(self._on_category_changed)
        self.filter_btn = QToolButton()
        self.filter_btn.setPopupMode(QToolButton.InstantPopup)
        self.filter_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        filter_menu = QMenu(self.filter_btn)
        fa = QWidgetAction(filter_menu)
        fa.setDefaultWidget(self.build_filter_panel())
        filter_menu.addAction(fa)
        self.filter_btn.setMenu(filter_menu)
        top.addWidget(self.search_edit, 1)
        top.addWidget(self.cat_combo)
        top.addWidget(self.filter_btn)
        top.addSpacing(12)
        # Most-used maintenance actions; everything else is in the menu bar.
        self.db_update_btn = QPushButton(self.tr("db_update"))
        self.db_update_btn.setToolTip(self.tr("db_update_tip"))
        self.db_update_btn.clicked.connect(self.update_database)
        self.missing_btn = QPushButton(self.tr("check_missing"))
        self.missing_btn.clicked.connect(self.check_missing)
        self.updates_btn = QPushButton(self.tr("check_updates"))
        self.updates_btn.clicked.connect(self.check_updates)
        for b in (self.db_update_btn, self.missing_btn, self.updates_btn):
            top.addWidget(b)
        root.addLayout(top)

        # First-run / empty-database hint, hidden once a song database exists.
        self.build_welcome_panel(root)
        self.refresh_empty_hint()

        # Shown while the table holds a check result instead of a search.
        self.view_bar = QWidget()
        vb = QHBoxLayout(self.view_bar)
        vb.setContentsMargins(0, 0, 0, 0)
        self.view_label = QLabel()
        self.view_label.setStyleSheet(theme.hint_qss())
        self.view_back_btn = QPushButton(self.tr("view_back"))
        self.view_back_btn.clicked.connect(self.show_all)
        vb.addWidget(self.view_label, 1)
        vb.addWidget(self.view_back_btn)
        self.view_bar.hide()
        root.addWidget(self.view_bar)

        # ---- splitter: song table (top) + download monitor (bottom, collapsible)
        splitter = self.splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)
        self.table = QTableView()
        self.table.setModel(self.song_model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)  # no initial sort
        self.table.doubleClicked.connect(self.on_row_double_clicked)
        # Space toggles the check of the current row (all selected rows if several).
        space = QShortcut(QKeySequence(Qt.Key_Space), self.table)
        space.setContext(Qt.WidgetShortcut)
        space.activated.connect(self.toggle_current_rows)
        sel = QShortcut(QKeySequence("Ctrl+A"), self.table)
        sel.setContext(Qt.WidgetShortcut)
        sel.activated.connect(self._check_all_visible)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_row_menu)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)   # ✓
        hh.setSectionResizeMode(1, QHeaderView.Stretch)            # 歌名
        hh.setSectionResizeMode(2, QHeaderView.Stretch)            # 日文
        for c in range(3, len(SongModel.COLS)):                    # 分類/BPM/難度×5/檔案
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.empty_label = QLabel(self.table.viewport())  # empty-state message over the table
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.empty_label.setStyleSheet(theme.hint_qss())
        self.empty_label.hide()
        self.table.viewport().installEventFilter(self)
        splitter.addWidget(self.table)
        splitter.addWidget(self.build_monitor())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        saved = disp.get("splitter")
        if (isinstance(saved, list) and len(saved) == 2
                and all(isinstance(s, int) and not isinstance(s, bool) and s > 0
                        for s in saved)):
            splitter.setSizes(saved)
        root.addWidget(splitter, 1)

        # ---- bottom row: download actions + slim progress
        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        self.download_btn = QPushButton(self.tr("download"))
        self.download_btn.setStyleSheet(theme.primary_button_qss(padding="5px 18px"))
        self.table.setStyleSheet(theme.check_indicator_qss())
        theme.add_listener(self._restyle_theme)  # re-colour these on theme change
        self.download_btn.setToolTip(self.tr("download_tip"))
        self.download_btn.clicked.connect(self.start_download_selected)
        self.selall_btn = QPushButton(self.tr("sel_all"))
        self.selall_btn.clicked.connect(lambda: self.song_model.set_all(True))
        self.deselall_btn = QPushButton(self.tr("desel_all"))
        self.deselall_btn.clicked.connect(lambda: self.song_model.set_all(False))
        self.sel_label = QLabel(self.tr("selected", n=0))
        self.overall_bar = QProgressBar()
        self.overall_bar.setFormat("%v / %m")
        self.overall_label = QLabel(self.tr("ready"))
        self.pause_btn = QToolButton()
        self.pause_btn.setText(self.tr("pause"))
        self._set_pause_icon(False)
        self.pause_btn.clicked.connect(self.toggle_pause)
        self.pause_btn.setEnabled(False)
        self.stop_btn = QToolButton()
        self.stop_btn.setText(self.tr("stop"))
        self.stop_btn.clicked.connect(self.stop_download)
        self.stop_btn.setEnabled(False)
        self.monitor_btn = QToolButton()
        self.monitor_btn.setCheckable(True)
        self.monitor_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.monitor_btn.toggled.connect(self.set_monitor_open)
        for wdg in (self.download_btn, self.selall_btn, self.deselall_btn, self.sel_label):
            bottom.addWidget(wdg)
        bottom.addStretch()
        for wdg in (self.overall_label, self.overall_bar, self.pause_btn, self.stop_btn,
                    self.monitor_btn):
            bottom.addWidget(wdg)
        root.addLayout(bottom)

        self.build_settings_dialog()
        self.update_font_metrics()
        self.set_monitor_open(bool(disp.get("monitor_open", False)))
        self.update_filter_button()

        # connect selection count
        self.song_model.dataChanged.connect(self.update_sel_count)
        self.retranslate_chrome()
        self._apply_icons()
        self._setup_accessibility()

    def _setup_accessibility(self):
        """Logical Tab order, accessible names and shortcut-bearing tooltips."""
        order = (self.search_edit, self.cat_combo, self.filter_btn, self.db_update_btn,
                 self.missing_btn, self.updates_btn, self.table, self.download_btn,
                 self.selall_btn, self.deselall_btn, self.pause_btn, self.stop_btn,
                 self.monitor_btn)
        for a, b in zip(order, order[1:]):
            QWidget.setTabOrder(a, b)
        t = self.tr
        for wdg, name, tip in (
                (self.search_edit, t("ph"), t("search_tip")),
                (self.cat_combo, t("acc_category"), t("acc_category_tip")),
                (self.filter_btn, t("f_filter"), t("acc_filter_tip")),
                (self.table, t("acc_table"), t("acc_table_tip")),
                (self.selall_btn, t("sel_all"), t("selall_tip")),
                (self.deselall_btn, t("desel_all"), t("deselall_tip")),
                (self.pause_btn, t("pause"), t("pause")),
                (self.stop_btn, t("stop"), t("stop")),
                (self.monitor_btn, t("monitor"), t("monitor")),
                (self.download_btn, t("download"), t("download_tip")),
                (self.db_update_btn, t("db_update"), t("db_update_tip")),
                (self.missing_btn, t("check_missing"), t("check_missing")),
                (self.updates_btn, t("check_updates"), t("check_updates")),
                (self.dl_table, t("tab_prog"), t("tab_prog")),
                (self.fail_list, t("tab_fail"), t("tab_fail"))):
            wdg.setAccessibleName(name)
            wdg.setAccessibleDescription(tip)
            wdg.setToolTip(tip)

    # (button/action attribute, icon name); re-tinted by _apply_icons() on theme change
    _ICON_MAP = (
        ("db_update_btn", "refresh"), ("missing_btn", "check-list"),
        ("updates_btn", "update"), ("filter_btn", "filter"),
        ("pause_btn", "pause"), ("stop_btn", "stop"),
        ("retry_btn", "retry"), ("opendir_btn", "folder"),
        ("act_update_db", "refresh"), ("act_missing", "check-list"),
        ("act_updates", "update"), ("act_open_dir", "folder"),
        ("act_official", "mail"), ("act_shortcuts", "keyboard"),
        ("download_btn", "download"),
    )

    def _apply_icons(self, dark=None):
        """(Re)set every themed icon; called after build and on theme change."""
        if dark is None:
            dark = theme.is_dark()
        for attr, name in self._ICON_MAP:
            w = getattr(self, attr, None)
            if w is not None and name:
                # the green download button keeps white text/icon in both themes
                colour = theme.colours(dark)["accent_text"] if attr == "download_btn" else None
                w.setIcon(icons.icon(name, dark, colour))
        if getattr(self, "pause_btn", None):
            self._set_pause_icon(self._paused_icon_play)
        for b in (self.pause_btn, self.stop_btn, self.monitor_btn, self.filter_btn):
            b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.monitor_btn.setIcon(icons.icon(
            "chevron-down" if self.monitor_btn.isChecked() else "chevron-up", dark))
        self.app_update_btn.setIcon(icons.icon(
            "update", dark, theme.colours(dark)["success"]))
        if not getattr(self, "_search_icon_action", None):
            self._search_icon_action = self.search_edit.addAction(
                icons.icon("search", dark), QLineEdit.LeadingPosition)
        else:
            self._search_icon_action.setIcon(icons.icon("search", dark))

    _paused_icon_play = False

    def _set_pause_icon(self, show_play):
        self._paused_icon_play = bool(show_play)
        self.pause_btn.setIcon(icons.icon("play" if show_play else "pause"))

    @staticmethod
    def _fit_to_screen(w, h):
        """Clamp a window size to the primary screen's work area (small laptops,
        high display scaling), leaving a margin for the title bar."""
        scr = QApplication.primaryScreen()
        if scr is None:
            return w, h
        area = scr.availableGeometry()
        return (max(640, min(w, area.width() - 40)),
                max(480, min(h, area.height() - 60)))

    def build_filter_panel(self):
        """BPM range + difficulty/level filter, shown in the filter button's popup."""
        panel = QWidget()
        form = QFormLayout(panel)
        form.setContentsMargins(14, 12, 14, 12)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.bpm_min = QSpinBox(); self.bpm_min.setRange(0, 999)
        self.bpm_min.setSpecialValueText(self.tr("f_any"))   # 0 顯示為「不限」
        self.bpm_max = QSpinBox(); self.bpm_max.setRange(0, 999)
        self.bpm_max.setSpecialValueText(self.tr("f_any"))
        form.addRow(self.tr("f_bpm"), self._range_row(self.bpm_min, self.bpm_max))
        self.diff_combo = QComboBox()
        self.diff_combo.addItem(self.tr("diff_all"), None)
        for key, col in (("c_easy", "level_easy"), ("c_normal", "level_normal"),
                         ("c_hard", "level_hard"), ("c_oni", "level_oni"),
                         ("c_ura", "level_ura")):
            self.diff_combo.addItem(self.tr(key), col)
        form.addRow(self.tr("f_diff"), self.diff_combo)
        self.lv_min = QSpinBox(); self.lv_min.setRange(0, 20)
        self.lv_min.setSpecialValueText(self.tr("f_any"))
        self.lv_max = QSpinBox(); self.lv_max.setRange(0, 20)
        self.lv_max.setSpecialValueText(self.tr("f_any"))
        form.addRow(self.tr("f_level"), self._range_row(self.lv_min, self.lv_max))
        self.reset_filter_btn = QPushButton(self.tr("f_reset"))
        self.reset_filter_btn.clicked.connect(self.reset_filters)
        for sp in (self.bpm_min, self.bpm_max, self.lv_min, self.lv_max):
            sp.setFixedWidth(84)
        self.diff_combo.setMinimumWidth(184)
        form.addRow(self.reset_filter_btn)
        for w in (self.bpm_min, self.bpm_max, self.lv_min, self.lv_max):
            w.valueChanged.connect(lambda _=None: self.apply_filters())
        self.diff_combo.currentIndexChanged.connect(lambda _=None: self.apply_filters())
        return panel

    @staticmethod
    def _range_row(lo, hi):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        h.addWidget(lo)
        dash = QLabel("–")
        dash.setAlignment(Qt.AlignCenter)
        h.addWidget(dash)
        h.addWidget(hi)
        h.addStretch()
        return w

    def active_filter_count(self):
        n = 0
        if self.bpm_min.value() or self.bpm_max.value():
            n += 1
        if self.diff_combo.currentData() is not None:
            n += 1
        if self.lv_min.value() or self.lv_max.value():
            n += 1
        return n

    def update_filter_button(self):
        n = self.active_filter_count()
        self.filter_btn.setText((self.tr("f_filter"))
                                + (f" ({n})" if n else "") + "  ")

    def _settings_section(self, layout, title_key):
        """Section header (bold caption + hairline) for the settings dialog."""
        head = QLabel(self.tr(title_key))
        head.setObjectName("sectionHeader")
        layout.addWidget(head)
        rule = QFrame()
        rule.setObjectName("sectionRule")
        rule.setFixedHeight(1)
        layout.addWidget(rule)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignTop)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)
        form.setContentsMargins(0, 6, 0, 0)
        layout.addLayout(form)
        return form

    def _settings_row(self, form, label, control, help_key):
        """One form row: label, control and a small muted explanation below it."""
        if isinstance(label, str):
            label = QLabel(label)
        label.setMinimumWidth(110)
        label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        label.setContentsMargins(0, 6, 0, 0)   # line up with the control's text
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        v.addWidget(control)
        helper = QLabel(self.tr(help_key))
        helper.setObjectName("helperText")
        helper.setWordWrap(True)
        v.addWidget(helper)
        form.addRow(label, box)

    def build_settings_dialog(self):
        """Download folder, parallel downloads, language and theme. The widgets
        belong to the main window (other code reads them), shown in a dialog."""
        dlg = self.settings_dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("mw_settings_title"))
        root = QVBoxLayout(dlg)
        root.setContentsMargins(20, 16, 20, 14)
        root.setSpacing(6)

        # ---- downloads
        form = self._settings_section(root, "set_sec_download")
        self.dir_edit = QLineEdit(os.path.abspath(self.download_dir))
        self.dir_edit.editingFinished.connect(self.save_config)
        self.browse_btn = QPushButton(self.tr("browse"))
        self.browse_btn.clicked.connect(self.browse_dir)
        self.opendir_btn = QPushButton(self.tr("open_dir"))
        self.opendir_btn.clicked.connect(self.open_dir)
        dir_row = QWidget()
        dh = QHBoxLayout(dir_row)
        dh.setContentsMargins(0, 0, 0, 0)
        dh.setSpacing(8)
        dh.addWidget(self.dir_edit, 1)
        dh.addWidget(self.browse_btn)
        dh.addWidget(self.opendir_btn)
        self.dir_row = dir_row
        self._settings_row(form, self.tr("dir"), dir_row, "dir_help")
        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, 8)       # be gentle with the ESE server
        self.workers_spin.setFixedWidth(90)
        self.workers_spin.setValue(self._cfg_int(self.config.get("download", {}), "workers", 3, 1))
        self.workers_spin.valueChanged.connect(lambda _: self.save_config())
        wbox = QWidget()
        wh = QHBoxLayout(wbox)
        wh.setContentsMargins(0, 0, 0, 0)
        wh.addWidget(self.workers_spin)
        wh.addStretch()
        self._settings_row(form, self.tr("workers"), wbox, "workers_help")
        self.source_combo = QComboBox()
        self.source_combo.setToolTip(self.tr("src_tip"))
        self.source_combo.addItem(self.tr("src_ese"), "ese")
        self.source_combo.addItem(self.tr("src_mirror"), "taiko.ac")
        src = self.config.get("download", {}).get("source", "ese")
        if isinstance(src, str) and src.lower().startswith(("http://", "https://")):
            self.source_combo.addItem(self.tr("src_custom", u=src), src)
        idx = self.source_combo.findData(src)
        self.source_combo.setCurrentIndex(idx if idx >= 0 else 0)
        core.set_download_source(self.source_combo.currentData())
        self.source_combo.currentIndexChanged.connect(self.change_source)
        lbl = QLabel(self.tr("src_label"))
        lbl.setToolTip(self.tr("src_tip"))
        self._settings_row(form, lbl, self.source_combo, "src_help")

        root.addSpacing(14)

        # ---- appearance and language
        form = self._settings_section(root, "set_sec_appearance")
        self.lang_combo = QComboBox()
        for label, code in (("自動 Auto", "auto"), ("繁體中文", "zh_TW"),
                            ("English", "en"), ("日本語", "ja")):
            self.lang_combo.addItem(label, code)
        idx = self.lang_combo.findData(self.lang_pref)
        self.lang_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.lang_combo.currentIndexChanged.connect(self.change_lang)
        self._settings_row(form, self.tr("lang"), self.lang_combo, "lang_help")
        self.theme_combo = QComboBox()
        self.theme_combo.setToolTip(self.tr("th_tip"))
        for label_key, code in (("th_auto", "auto"), ("th_light", "light"),
                                ("th_dark", "dark")):
            self.theme_combo.addItem(self.tr(label_key), code)
        idx = self.theme_combo.findData(self.theme_pref)
        self.theme_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.theme_combo.currentIndexChanged.connect(self.change_theme)
        self._settings_row(form, self.tr("th_label"), self.theme_combo, "th_help")
        self.font_combo = QComboBox()
        self.font_combo.setToolTip(self.tr("font_tip"))
        for pct in self.FONT_SCALES:
            self.font_combo.addItem(f"{pct}%", pct)
        self.font_combo.setCurrentIndex(self.font_combo.findData(self.font_scale))
        self.font_combo.currentIndexChanged.connect(self.change_font_scale)
        self._settings_row(form, self.tr("font_label"), self.font_combo, "font_tip")

        root.addSpacing(10)
        buttons = QHBoxLayout()
        buttons.addStretch()
        close = QPushButton(self.tr("mw_close"))
        close.setMinimumWidth(96)
        close.setDefault(True)
        close.clicked.connect(dlg.accept)
        buttons.addWidget(close)
        root.addLayout(buttons)
        dlg.finished.connect(lambda _=None: self.save_config())

    def change_source(self, _=None):
        core.set_download_source(self.source_combo.currentData())
        self.save_config()

    def open_settings(self):
        self.settings_dlg.show()
        self.settings_dlg.raise_()
        self.settings_dlg.activateWindow()

    def build_monitor(self):
        """Per-file progress, log and failed list (the collapsible part)."""
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
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
        # ResizeToContents re-measures rows on every dataChanged; with thousands
        # of rows only a sample is needed to size these narrow columns.
        dh.setResizeContentsPrecision(40)
        self.tabs.addTab(self.dl_table, self.tr("tab_prog"))
        # log tab
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(5000)
        self.log_view.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.tabs.addTab(self.log_view, self.tr("tab_log"))
        # failed tab
        fail_w = QWidget()
        fv = QVBoxLayout(fail_w)
        fv.setContentsMargins(0, 6, 0, 0)
        fv.setSpacing(8)
        self.fail_list = QListWidget()
        self.retry_btn = QPushButton(self.tr("retry"))
        self.retry_btn.clicked.connect(self.retry_failed)
        self.retry_btn.setEnabled(False)
        fv.addWidget(self.fail_list)
        row = QHBoxLayout()
        row.addStretch()
        self.retry_btn.setMinimumWidth(140)
        row.addWidget(self.retry_btn)
        fv.addLayout(row)
        self.tabs.addTab(fail_w, self.tr("tab_fail"))
        return self.tabs

    def set_monitor_open(self, on):
        """Show or hide the download monitor below the song table."""
        on = bool(on)
        self.tabs.setVisible(on)
        if self.monitor_btn.isChecked() != on:
            self.monitor_btn.blockSignals(True)
            self.monitor_btn.setChecked(on)
            self.monitor_btn.blockSignals(False)
        self.monitor_btn.setText(self.tr("monitor"))
        self.monitor_btn.setIcon(icons.icon("chevron-down" if on else "chevron-up"))

    def show_monitor(self, tab=None):
        """Open the monitor (e.g. when a download starts) and pick a tab."""
        self.set_monitor_open(True)
        if tab is not None:
            self.tabs.setCurrentIndex(tab)

    # ---- categories
    def load_categories(self):
        self.cat_combo.blockSignals(True)
        self.cat_combo.clear()
        self.cat_combo.addItem(self.tr("all_cat"), None)
        try:
            for name in core.list_categories():
                self.cat_combo.addItem(CATEGORY_NAMES.get(name, name), name)
        except Exception:
            core.log.warning("load_categories failed", exc_info=True)
        # Restore the category used last time (if it still exists).
        last = self.config.get("display", {}).get("category")
        i = self.cat_combo.findData(last) if isinstance(last, str) and last else -1
        if i > 0:
            self.cat_combo.setCurrentIndex(i)
        self.cat_combo.blockSignals(False)

    @staticmethod
    def has_song_db():
        return core.has_song_db()

    def build_welcome_panel(self, root):
        """In-window first-run panel: one primary button to fetch the song
        database, plus the download folder with a way to change it."""
        self.welcome_panel = self.empty_hint = QFrame()
        self.welcome_panel.setObjectName("welcome")
        self.welcome_panel.setStyleSheet(self._welcome_qss(None))
        v = QVBoxLayout(self.welcome_panel)
        v.setContentsMargins(18, 14, 18, 14)
        v.setSpacing(8)
        self.welcome_title = QLabel(self.tr("welcome_title"))
        f = self.welcome_title.font()
        f.setBold(True)
        f.setPointSize(f.pointSize() + 3)
        self.welcome_title.setFont(f)
        self.welcome_body = QLabel(self.tr("empty_hint"))
        self.welcome_body.setWordWrap(True)
        self.welcome_btn = QPushButton(self.tr("welcome_download"))
        self.welcome_btn.setMinimumHeight(36)
        self.welcome_btn.setStyleSheet(theme.primary_button_qss())
        self.welcome_btn.clicked.connect(self.update_database)
        self.welcome_dir = QLabel()
        self.welcome_dir.setWordWrap(True)
        self.welcome_dir.setTextInteractionFlags(Qt.TextSelectableByMouse)
        change = self.welcome_change_btn = QPushButton(self.tr("welcome_change_dir"))
        change.clicked.connect(self.browse_dir)
        dir_row = QHBoxLayout()
        dir_row.addWidget(self.welcome_dir, 1)
        dir_row.addWidget(change)
        for wdg in (self.welcome_title, self.welcome_body):
            v.addWidget(wdg)
        v.addWidget(self.welcome_btn, 0, Qt.AlignLeft)
        v.addLayout(dir_row)
        root.addWidget(self.welcome_panel)
        self.refresh_welcome_dir()

    @staticmethod
    def _welcome_qss(dark):
        return (theme.hint_qss(dark).replace("QLabel", "QFrame#welcome")
                + "QFrame#welcome QLabel{background:transparent;border:none;padding:0;}")

    def refresh_welcome_dir(self):
        if hasattr(self, "welcome_dir"):
            d = self.dir_edit.text() if hasattr(self, "dir_edit") else self.download_dir
            self.welcome_dir.setText(self.tr("welcome_dir", d=os.path.abspath(d)))

    def refresh_empty_hint(self):
        has = self.has_song_db()
        self.welcome_panel.setVisible(not has)
        for b in (self.missing_btn, self.updates_btn):
            b.setEnabled(has)
        if not has:
            self.count_label.setText("")      # no "Total 0" before a database exists
        self.refresh_welcome_dir()

    def _db_btns_enabled(self, on):
        self.db_update_btn.setEnabled(on)
        self.welcome_btn.setEnabled(on)

    def _track(self, thread):
        """Remember a worker so closeEvent can stop it; forget it when it ends."""
        self._threads.append(thread)
        thread.finished.connect(lambda t=thread: self._threads.remove(t)
                                if t in self._threads else None)
        return thread

    # ---- search
    def _search_now(self):
        """Enter in the search box: search immediately, skipping the debounce."""
        self._search_timer.stop()
        self.do_search()

    def do_search(self):
        kw = self.search_edit.text().strip()
        cat = self.cat_combo.currentData()
        self._run_search(kw, cat)

    def show_all(self):
        self.search_edit.clear()
        self._search_timer.stop()      # clearing the box must not queue a second search
        self.cat_combo.blockSignals(True)
        self.cat_combo.setCurrentIndex(0)
        self.cat_combo.blockSignals(False)
        self._run_search("", None)

    def clear_search(self):
        self.search_edit.clear()
        self._search_timer.stop()
        self.cat_combo.blockSignals(True)
        self.cat_combo.setCurrentIndex(0)
        self.cat_combo.blockSignals(False)
        self._search_seq += 1          # drop any search still in flight
        self.all_songs = []
        self.song_model.set_songs([])
        self.count_label.setText(self.tr("total", n=0))
        self.update_sel_count()

    def _show_view(self, key, songs):
        """Replace the table with a check result and say so above it."""
        self._search_seq += 1          # a late search must not overwrite the result
        self.song_model.set_songs(songs)
        self.song_model.set_all(True)
        self.count_label.setText(self.tr("total", n=len(songs)))
        self.view_label.setText(self.tr(key, n=len(songs)))
        self.view_bar.show()
        self.update_sel_count()

    def _run_search(self, kw, cat):
        self.view_bar.hide()
        self.empty_label.hide()
        if not self.has_song_db():
            self.refresh_empty_hint()
            return
        # Each search gets a sequence number; results from an older search that
        # finishes late are ignored, so typing quickly never shows stale rows.
        self._search_seq += 1
        if not kw and cat is None:
            self._unfiltered_seq = self._search_seq   # full list: its size is the song total
        self.count_label.setText("...")
        t = self._track(SearchThread(kw, cat, seq=self._search_seq, tr=self.tr))
        t.done.connect(self.on_search_done)
        t.fail.connect(self.on_search_fail)
        self._search = t
        t.start()

    def on_search_done(self, seq, songs):
        if seq != self._search_seq:
            return
        self.all_songs = songs
        # Status bar total: set by the first search, then refreshed by unfiltered searches.
        if self._total_songs is None or seq == self._unfiltered_seq:
            self._total_songs = len(songs)
            self._refresh_status()
        self.apply_filters()

    DB_DAMAGED = ("malformed", "not a database", "no such table", "unable to open")

    def on_search_fail(self, seq, err):
        if seq != self._search_seq:
            return
        self.count_label.setText(err)
        if any(m in err for m in self.DB_DAMAGED) and not self._db_warned:
            self._db_warned = True     # once per session
            QMessageBox.warning(self, self.tr("dbv_title"), self.tr("db_corrupt", e=err))

    _db_warned = False

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
        self.update_filter_button()
        self.update_empty_state()

    def _on_category_changed(self, _=None):
        self.do_search()
        self.save_config()

    def eventFilter(self, obj, ev):
        if obj is self.table.viewport() and ev.type() == QEvent.Resize:
            self.empty_label.setGeometry(self.table.viewport().rect().adjusted(20, 20, -20, -20))
        return super().eventFilter(obj, ev)

    def update_empty_state(self):
        """Tell the user why the table is blank instead of leaving it empty."""
        if self.song_model.rowCount() or not self.has_song_db() or self.view_bar.isVisible():
            self.empty_label.hide()
            return
        searching = (bool(self.search_edit.text().strip())
                     or self.cat_combo.currentData() is not None
                     or self.active_filter_count() > 0)
        self.empty_label.setText(self.tr("no_results" if searching else "no_songs"))
        self.empty_label.setGeometry(self.table.viewport().rect().adjusted(20, 20, -20, -20))
        self.empty_label.show()

    def _song_dir(self, song):
        """Folder of a song inside the download directory, or None if not downloaded."""
        try:
            fp = song["files"][0]["file_path"]
            d = core.safe_join(resolve_dir(self.dir_edit.text()), os.path.dirname(fp))
        except Exception:
            return None
        return d if d and os.path.isdir(d) else None

    @staticmethod
    def _open_path(d):
        if sys.platform == "win32":
            os.startfile(d)
        else:
            import subprocess
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", d])

    def _row_song(self, row):
        return self.song_model._view[row] if 0 <= row < self.song_model.rowCount() else None

    def on_row_double_clicked(self, index):
        """Double-click: open the song's folder if it is downloaded, else check/uncheck."""
        song = self._row_song(index.row())
        d = self._song_dir(song) if song else None
        if d:
            self._open_path(d)
        else:
            self.toggle_check(index)

    def toggle_current_rows(self):
        rows = sorted({i.row() for i in self.table.selectionModel().selectedRows()})
        if not rows and self.table.currentIndex().isValid():
            rows = [self.table.currentIndex().row()]
        if not rows:
            return
        on = not all(self.song_model.is_checked(r) for r in rows)
        for r in rows:
            self.song_model.setData(self.song_model.index(r, 0),
                                    Qt.Checked if on else Qt.Unchecked, Qt.CheckStateRole)

    def show_row_menu(self, pos):
        idx = self.table.indexAt(pos)
        song = self._row_song(idx.row()) if idx.isValid() else None
        if not song:
            return
        menu = QMenu(self.table)
        menu.addAction(self.tr("ctx_toggle"), self.toggle_current_rows)
        menu.addAction(self.tr("ctx_download"), lambda: self.start_download(
            [(song, f) for f in song["files"]]))
        d = self._song_dir(song)
        a = menu.addAction(self.tr("ctx_open_folder"), lambda: self._open_path(d))
        a.setEnabled(bool(d))
        menu.addAction(self.tr("ctx_copy_title"),
                       lambda: QGuiApplication.clipboard().setText(song["song_name"]))
        menu.exec(self.table.viewport().mapToGlobal(pos))

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
            QMessageBox.warning(self, self.tr("download"), self.tr("no_selection"))
            return
        files = [(s, f) for s in songs for f in s["files"]]
        if len(files) > self.LARGE_DOWNLOAD and QMessageBox.question(
                self, self.tr("download"),
                self.tr("dl_confirm_many", n=len(songs), f=len(files))) != QMessageBox.Yes:
            return
        self.start_download(files)

    def start_download(self, files, overwrite=False):
        if self.dl_thread and self.dl_thread.isRunning():
            QMessageBox.warning(self, self.tr("download"), self.tr("dl_busy"))
            return
        if not files:
            return
        self.save_config()
        self.download_btn.setEnabled(False)
        self.fail_list.clear()
        self.retry_btn.setEnabled(False)
        self.dl_model.load(files)
        self.overall_bar.setRange(0, len(files))
        self.overall_bar.setValue(0)
        self.show_monitor(0)
        self.pause_btn.setText(self.tr("pause"))
        self._set_pause_icon(False)
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

    def _set_busy(self, on):
        """Indeterminate bottom bar while a check or DB update runs (not while
        downloading: the bar then shows file progress)."""
        self._busy = max(0, self._busy + (1 if on else -1))
        if self.dl_thread and self.dl_thread.isRunning():
            return
        if self._busy:
            self.overall_bar.setRange(0, 0)
        else:
            self.overall_bar.setRange(0, 1)
            self.overall_bar.setValue(0)

    _busy = 0

    def refresh_progress(self):
        if not self.dl_thread:
            return
        flush = getattr(self.dl_thread, "flush_log", None)
        if flush:
            flush()         # batched log lines, one signal per tick
        done, total, spd, eta, dirty = self.dl_thread.snapshot()
        self.overall_bar.setValue(done)
        if self.dl_thread.is_paused():
            self.overall_label.setText(f"{done}/{total}  ·  {self.tr('paused_label')}")
        else:
            self.overall_label.setText(
                f"{done}/{total}  ·  {human_speed(spd)}  ·  ETA {human_eta(eta)}")
        if dirty:
            self.dl_model.update_many(dirty)
        if total:
            self.setWindowTitle(f"{done * 100 // total}% – {self.tr('title')}")

    def _reset_window_title(self):
        self.setWindowTitle(f"{self.tr('title')} {APP_VERSION}")

    def toggle_pause(self):
        if not (self.dl_thread and self.dl_thread.isRunning()) or self.dl_thread.stopped:
            return
        if self.dl_thread.is_paused():
            self.dl_thread.resume()
            self.pause_btn.setText(self.tr("pause"))
            self._set_pause_icon(False)
        else:
            self.dl_thread.pause()
            self.pause_btn.setText(self.tr("resume"))
            self._set_pause_icon(True)

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
        self._reset_window_title()
        self.download_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.pause_btn.setText(self.tr("pause"))
        self._set_pause_icon(False)
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
            self.show_monitor(2)
        if self._closing:
            return
        key = "stopped_msg" if stopped else "done_msg"
        text = self.tr(key, d=dl, s=skip, f=fail, t=total)
        self.notifier.notify(self.tr("title"), text)
        self._show_summary(text, fail)

    def _show_summary(self, text, fail):
        """Completion dialog with shortcuts: open the download folder / retry failures."""
        box = QMessageBox(QMessageBox.Information, self.tr("download"), text,
                          QMessageBox.Ok, self)
        open_btn = box.addButton(self.tr("dl_open_folder"), QMessageBox.ActionRole)
        retry_btn = box.addButton(self.tr("dl_retry_failed"), QMessageBox.ActionRole)             if fail > 0 else None
        box.exec()
        clicked = box.clickedButton()
        if clicked is open_btn:
            d = resolve_dir(self.dir_edit.text())
            if os.path.isdir(d):
                self._open_path(d)
        elif retry_btn is not None and clicked is retry_btn:
            self.dl_thread.wait(3000)   # finished_all fires just before the thread ends
            self.retry_failed()

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
        self.overall_label.setText(self.tr("missing_checking"))
        self._set_busy(True)
        t = self._track(SearchThread("", None, tr=self.tr))
        t.done.connect(lambda _seq, songs: self.on_missing_loaded(songs))
        t.fail.connect(self._on_missing_fail)
        self._miss = t
        t.start()

    def _on_missing_fail(self, _seq, e):
        self.missing_btn.setEnabled(True)
        self._set_busy(False)
        self.overall_label.setText(self.tr("ready"))
        QMessageBox.critical(self, self.tr("check_missing"), e)

    def on_missing_loaded(self, songs):
        self.missing_btn.setEnabled(True)
        self._set_busy(False)
        self.overall_label.setText(self.tr("ready"))
        missing = core.find_missing(songs, resolve_dir(self.dir_edit.text()))
        if not missing:
            QMessageBox.information(self, self.tr("check_missing"), self.tr("missing_none"))
            return
        files = [(s, f) for s in missing for f in s["files"]]
        if QMessageBox.question(
                self, self.tr("check_missing"),
                self.tr("missing_found", n=len(missing), f=len(files))) == QMessageBox.Yes:
            self._show_view("view_missing", missing)
            self.start_download(files)

    # ---- check updates（比對 git blob sha，找出上游已更新的已下載檔案）
    def check_updates(self):
        ddir = resolve_dir(self.dir_edit.text())
        if not os.path.isdir(ddir):
            QMessageBox.warning(self, self.tr("check_updates"), self.tr("dir_missing", d=ddir))
            return
        self.updates_btn.setEnabled(False)
        self._set_busy(True)
        self.log_view.appendPlainText(self.tr("upd_checking"))
        t = self._track(CheckUpdatesThread(ddir, None, tr=self.tr))
        t.progress.connect(
            lambda d, n: self.count_label.setText(self.tr("upd_progress", d=d, t=n)))
        t.done.connect(self.on_updates_loaded)
        t.fail.connect(self._on_updates_fail)
        self._upd = t
        t.start()

    def _on_updates_fail(self, e):
        self.updates_btn.setEnabled(True)
        self._set_busy(False)
        if e == "__NO_SHA__":
            QMessageBox.information(self, self.tr("check_updates"), self.tr("upd_no_sha"))
        else:
            QMessageBox.critical(self, self.tr("check_updates"), e)

    def on_updates_loaded(self, songs):
        self.updates_btn.setEnabled(True)
        self._set_busy(False)
        self.count_label.setText(self.tr("total", n=self.song_model.rowCount()))
        if not songs:
            QMessageBox.information(self, self.tr("check_updates"), self.tr("upd_none"))
            return
        files = [(s, f) for s in songs for f in s["files"]]
        if QMessageBox.question(
                self, self.tr("check_updates"),
                self.tr("upd_found", n=len(songs), f=len(files))) == QMessageBox.Yes:
            self._show_view("view_updates", songs)
            self.start_download(files, overwrite=True)   # 覆寫既有檔案

    # ---- misc
    def browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, self.tr("browse"),
                                             resolve_dir(self.dir_edit.text()))
        if d:
            self.dir_edit.setText(d)
            self.save_config()
            self.refresh_welcome_dir()

    def open_dir(self):
        d = resolve_dir(self.dir_edit.text())
        if os.path.isdir(d):
            self._open_path(d)

    # ---- ESE-Version-Sorting (YataiDON version folders)
    def download_version_sorting(self):
        t = getattr(self, "_vsort", None)
        if t and t.isRunning():
            return
        ddir = resolve_dir(self.dir_edit.text())
        self.act_vsort.setEnabled(False)
        self.show_monitor(1)
        self.log_view.appendPlainText("——— " + self.tr("vsort_action") + " ———")
        t = self._vsort = self._track(VersionSortingThread(ddir, tr=self.tr))
        t.log.connect(self.log_view.appendPlainText)
        t.done.connect(self.on_version_sorting_done)
        t.start()

    def on_version_sorting_done(self, ok, info, commit):
        self.act_vsort.setEnabled(True)
        if self._closing:
            return
        if not ok:
            QMessageBox.critical(self, self.tr("vsort_action"), self.tr("vsort_fail", e=info))
            return
        key = "vsort_latest" if info == "latest" else "vsort_done"
        text = self.tr(key, c=commit[:7])
        self.notifier.notify(self.tr("vsort_action"), text)
        QMessageBox.information(self, self.tr("vsort_action"), text)

    # ---- database update (prebuilt databases from GitHub Pages)
    def _db_busy(self):
        t = getattr(self, "_dbu", None)
        return bool(t and t.isRunning())

    def update_database(self):
        """Manual "Update DB": check the published version and download it if
        it differs. The databases are rebuilt from ESE every 6 hours by CI."""
        if self._db_busy():
            QMessageBox.warning(self, self.tr("db_update"), self.tr("db_building"))
            return
        self._db_btns_enabled(False)
        self.overall_label.setText(self.tr("db_checking"))
        self._set_busy(True)
        t = self._track(VersionThread())
        t.result.connect(lambda remote, local: self.on_version(remote, local, manual=True))
        self._ver = t
        t.start()

    def start_db_download(self, remote):
        self._db_btns_enabled(False)
        self.overall_label.setText(self.tr("db_building"))
        self._set_busy(True)
        self._dbu = self._track(DBUpdateThread(remote, tr=self.tr))
        self._dbu.log.connect(self.log_view.appendPlainText)
        self._dbu.done.connect(self.on_db_updated)
        self._dbu.start()

    def reload_databases(self, done_msg=None):
        """Reload categories and the Japanese-title/level maps after a DB change.
        The maps load on a worker thread so the window stays responsive."""
        self.load_categories()
        self.refresh_empty_hint()
        self._db_version = read_local_version()
        self._refresh_status()
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
        if QMessageBox.question(self, self.tr("lang"), self.tr("lang_restart")) == QMessageBox.Yes:
            self._restart()

    def change_font_scale(self, *_):
        pct = self._valid_font_scale(self.font_combo.currentData())
        if pct == self.font_scale:
            return
        self.font_scale = pct
        self.apply_font_scale(pct)     # applies immediately
        self.save_config()

    def change_theme(self, *_):
        mode = self.theme_combo.currentData() or "auto"
        if mode == self.theme_pref:
            return
        self.theme_pref = mode
        theme.apply_theme(QApplication.instance(), mode)  # applies immediately
        self.save_config()

    def _restyle_theme(self, dark):
        try:
            self.download_btn.setStyleSheet(theme.primary_button_qss(dark))
            self.welcome_panel.setStyleSheet(self._welcome_qss(dark))
            self.welcome_btn.setStyleSheet(theme.primary_button_qss(dark))
            self.view_label.setStyleSheet(theme.hint_qss(dark))
            self.table.setStyleSheet(theme.check_indicator_qss(dark))
            self.app_update_btn.setStyleSheet(theme.success_text_qss(dark))
            self._apply_icons(dark)
            self.song_model.layoutChanged.emit()          # category colours
        except RuntimeError:  # widgets already deleted by Qt
            pass

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

    def check_app_update(self):
        """Rolling releases: tell the user when GitHub has a newer build."""
        t = self._track(AppUpdateThread())
        t.found.connect(self.on_app_update)
        self._app_upd = t
        t.start()

    def _report_failed_update(self):
        err = core.update_failed()
        if err and not self._closing:
            core.discard_update_work()
            QMessageBox.warning(self, self.tr("upd_app_title"),
                                self.tr("upd_app_failed_restart", e=err))

    def on_app_update(self, tag, url):
        self.app_update_btn.setText(self.tr("mw_app_update", v=tag))
        tip = "mw_app_update_tip2" if core.can_self_update() else "mw_app_update_tip"
        self.app_update_btn.setToolTip(self.tr(tip, cur=APP_VERSION, v=tag))
        self._app_update_url = url
        self._app_update_tag = tag
        self.app_update_btn.show()

    def install_app_update(self):
        """Download the new release over this folder and restart (release
        builds); from source, just open the release page."""
        url = getattr(self, "_app_update_url", RELEASES_URL)
        if not core.can_self_update():
            webbrowser.open(url)
            return
        t = getattr(self, "_selfupd", None)
        if t and t.isRunning():
            return
        if (self.dl_thread and self.dl_thread.isRunning()) or self._db_busy():
            QMessageBox.information(self, self.tr("upd_app_title"), self.tr("upd_app_busy"))
            return
        tag = getattr(self, "_app_update_tag", "")
        if QMessageBox.question(self, self.tr("upd_app_title"),
                                self.tr("upd_app_confirm", cur=APP_VERSION, v=tag)) \
                != QMessageBox.Yes:
            return
        self.app_update_btn.setEnabled(False)
        self.overall_label.setText(self.tr("upd_app_downloading", p=0))
        self._set_busy(True)
        t = self._selfupd = self._track(AppSelfUpdateThread(tr=self.tr))
        t.restart_exe = sys.executable          # the frozen ESEManager executable
        t.progress.connect(self._on_self_update_progress)
        t.done.connect(self._on_self_update_done)
        t.start()

    def _on_self_update_progress(self, got, total):
        if total:
            self.overall_label.setText(
                self.tr("upd_app_downloading", p=int(got * 100 / total)))

    def _on_self_update_done(self, ok, info):
        self._set_busy(False)
        self.app_update_btn.setEnabled(True)
        self.overall_label.setText(self.tr("ready"))
        if self._closing:
            return
        if not ok:
            if QMessageBox.question(self, self.tr("upd_app_title"),
                                    self.tr("upd_app_fail", e=info)) == QMessageBox.Yes:
                webbrowser.open(getattr(self, "_app_update_url", RELEASES_URL))
            return
        how, _, tag = info.partition(":")
        QMessageBox.information(self, self.tr("upd_app_title"),
                                self.tr("upd_app_done", v=tag))
        if how == "applied":
            self._restart()
        else:                  # Windows helper waits for us to exit, then restarts
            self.close()

    def on_version(self, remote, local, manual=False):
        if self._closing:
            return
        if manual:
            self._db_btns_enabled(True)
            self.overall_label.setText(self.tr("ready"))
            self._set_busy(False)
            if not remote:
                QMessageBox.warning(self, self.tr("dbv_title"), self.tr("db_offline"))
                return
            if remote == local and self.has_song_db():
                QMessageBox.information(self, self.tr("dbv_title"),
                                        self.tr("db_latest", v=local))
                return
            self.start_db_download(remote)      # the user asked for it: no extra prompt
            return
        # Startup check: offer the update.
        if not remote or remote == local or self._db_busy():
            return
        if not self.has_song_db():
            return      # the welcome panel already offers the download
        else:
            msg = self.tr("dbv_found", cur=local or self.tr("dbv_none"), new=remote)
        if QMessageBox.question(self, self.tr("dbv_title"), msg) == QMessageBox.Yes:
            self.start_db_download(remote)

    def on_db_updated(self, ok, msg):
        first_run = not self.welcome_panel.isHidden()
        self._db_btns_enabled(True)
        self.overall_label.setText(self.tr("ready"))
        self._set_busy(False)
        self._db_warned = False
        self.notifier.notify(self.tr("dbv_title"),
                             self.tr("dbv_ok") if ok else self.tr("db_fail", e=msg))
        if ok:
            self._db_version = read_local_version()
            self._refresh_status()
            # First database: no modal, just show the list and let them type.
            self.reload_databases(None if first_run else self.tr("dbv_ok"))
            if first_run:
                self.show_all()
                self.search_edit.setFocus()
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
                    core.log.warning("closeEvent: %s still running; exiting anyway",
                                     type(t).__name__)
        event.accept()


def selftest():
    """Packaged self-test (release workflow): start the real window offscreen,
    close it, and report. Any startup error exits non-zero instead of leaving
    an error dialog open."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        app = QApplication(sys.argv)
        app.setStyle(QStyleFactory.create("Fusion"))
        set_app_icon(app)
        QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
        w = MainWindow()
        theme.apply_theme(app, w.theme_pref)
        w.show()
        app.processEvents()
        w._closing = True
        w.close()
    except Exception:
        import traceback
        traceback.print_exc()
        print("SELFTEST_FAIL")
        os._exit(1)
    print("SELFTEST_OK", APP_VERSION)
    sys.stdout.flush()
    os._exit(0)


def main():
    if "--selftest" in sys.argv:
        selftest()

    # Relative paths (git clone, portable git, user-entered folders) resolve
    # next to the app no matter where it was launched from.
    os.chdir(APP_DIR)
    core.setup_logging()
    try:
        core.cleanup_app_update()      # .old files left by the last self-update
    except Exception:
        core.log.warning("update cleanup failed", exc_info=True)
    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create("Fusion"))
    set_app_icon(app)
    w = MainWindow()
    theme.apply_theme(app, w.theme_pref)  # display.theme from config.toml
    w.show()
    rc = app.exec()
    if any(t.isRunning() for t in w._threads):
        # A worker that ignored the shutdown wait: exit without running
        # QThread destructors (which would abort on a running thread).
        if sys.stdout:
            sys.stdout.flush()
        os._exit(rc)
    sys.exit(rc)


if __name__ == "__main__":
    main()
