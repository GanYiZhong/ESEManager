"""Song detail side panel: titles, category, BPM, per-difficulty level bars,
file list and per-song actions. Pure view; the main window feeds it a song and
handles the action signals."""

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QWidget, QListWidget, QAbstractItemView, QSizePolicy)

from i18n import CATEGORY_NAMES, CATEGORY_COLORS
import theme

DIFFS = (("c_easy", "level_easy", "#E53935"), ("c_normal", "level_normal", "#43A047"),
         ("c_hard", "level_hard", "#1E88E5"), ("c_oni", "level_oni", "#D81B60"),
         ("c_ura", "level_ura", "#8E24AA"))
MAX_LEVEL = 10


def format_size(n):
    if not isinstance(n, (int, float)) or isinstance(n, bool) or n <= 0:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


class LevelBar(QWidget):
    """Row of MAX_LEVEL small segments, the first `level` filled in `colour`."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.level = None
        self.colour = "#888888"
        self.empty = "#B8B8B8"
        self.setFixedHeight(12)
        self.setMinimumWidth(MAX_LEVEL * 8)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_level(self, level, colour, empty):
        self.level, self.colour, self.empty = level, colour, empty
        self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        gap = 3
        w = (self.width() - gap * (MAX_LEVEL - 1)) / MAX_LEVEL
        n = int(self.level) if isinstance(self.level, (int, float)) else 0
        for i in range(MAX_LEVEL):
            p.setBrush(QColor(self.colour if i < n else self.empty))
            p.drawRoundedRect(i * (w + gap), 1, w, self.height() - 2, 2, 2)
        p.end()


class DetailPanel(QFrame):
    download_requested = Signal()
    open_folder_requested = Signal()
    copy_requested = Signal()

    def __init__(self, tr, parent=None):
        super().__init__(parent)
        self.tr = tr
        self.setObjectName("detailPanel")
        self.setMinimumWidth(220)
        self.setFocusPolicy(Qt.NoFocus)
        self._song = None
        self._jp = ""
        self._meta = {}
        self._downloaded = False
        self._cat_hex = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        self.head = QLabel()
        self.head.setObjectName("detailHead")
        self.title = QLabel()
        self.title.setObjectName("detailTitle")
        self.title.setWordWrap(True)
        self.jp = QLabel()
        self.jp.setWordWrap(True)
        self.cat = QLabel()
        self.bpm = QLabel()
        self.bpm.setObjectName("detailMuted")
        self.empty = QLabel()
        self.empty.setObjectName("detailMuted")
        self.empty.setWordWrap(True)
        self.empty.setAlignment(Qt.AlignCenter)
        for w in (self.head, self.title, self.jp, self.cat, self.bpm):
            lay.addWidget(w)

        self.levels_box = QWidget()
        grid = QVBoxLayout(self.levels_box)
        grid.setContentsMargins(0, 4, 0, 4)
        grid.setSpacing(4)
        self.level_names, self.level_bars, self.level_nums = [], [], []
        for _ in DIFFS:
            row = QHBoxLayout()
            row.setSpacing(6)
            name, bar, num = QLabel(), LevelBar(), QLabel()
            name.setMinimumWidth(48)
            num.setMinimumWidth(18)
            num.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row.addWidget(name)
            row.addWidget(bar, 1)
            row.addWidget(num)
            grid.addLayout(row)
            self.level_names.append(name)
            self.level_bars.append(bar)
            self.level_nums.append(num)
        lay.addWidget(self.levels_box)

        self.files_head = QLabel()
        self.files_head.setObjectName("detailHead")
        lay.addWidget(self.files_head)
        self.files = QListWidget()
        self.files.setFocusPolicy(Qt.NoFocus)
        self.files.setSelectionMode(QAbstractItemView.NoSelection)
        self.files.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.files.setTextElideMode(Qt.ElideMiddle)
        lay.addWidget(self.files, 1)

        self.dl_btn = QPushButton()
        self.dl_btn.clicked.connect(self.download_requested)
        self.open_btn = QPushButton()
        self.open_btn.clicked.connect(self.open_folder_requested)
        self.copy_btn = QPushButton()
        self.copy_btn.clicked.connect(self.copy_requested)
        for b in (self.dl_btn, self.open_btn, self.copy_btn):
            b.setFocusPolicy(Qt.NoFocus)       # never take focus from the song table
            lay.addWidget(b)
        lay.addWidget(self.empty, 1)
        self.retranslate()
        self.restyle()
        self.set_song(None)

    def sizeHint(self):
        return QSize(280, 400)

    # ---- content
    def retranslate(self):
        t = self.tr
        self.head.setText(t("dp_title"))
        self.dl_btn.setText(t("dp_download"))
        self.open_btn.setText(t("ctx_open_folder"))
        self.copy_btn.setText(t("dp_copy"))
        self.empty.setText(t("dp_empty"))
        for name, (key, _c, _col) in zip(self.level_names, DIFFS):
            name.setText(t(key))
        self.setAccessibleName(t("dp_title"))
        if self._song is not None:
            self._fill()
        else:
            self.files_head.setText(t("dp_files"))

    def set_song(self, song, jp="", meta=None, downloaded=False):
        self._song, self._jp = song, jp or ""
        self._meta, self._downloaded = meta or {}, bool(downloaded)
        has = song is not None
        for w in (self.head, self.title, self.jp, self.cat, self.bpm, self.levels_box,
                  self.files_head, self.files, self.dl_btn, self.open_btn, self.copy_btn):
            w.setVisible(has)
        self.empty.setVisible(not has)
        if has:
            self._fill()

    def _fill(self):
        s, meta = self._song, self._meta
        self.title.setText(s["song_name"])
        self.jp.setText(self._jp)
        self.jp.setVisible(bool(self._jp))
        self._cat_hex = CATEGORY_COLORS.get(s["category"])
        self.cat.setText(str(CATEGORY_NAMES.get(s["category"], s["category"])))
        self.bpm.setText(f"BPM  {meta.get('bpm') or '−'}")
        self.files.clear()
        for f in s["files"]:
            sz = format_size(f.get("size"))
            ft = f.get("file_type") or f["filename"].rsplit(".", 1)[-1]
            self.files.addItem(f"{f['filename']}   [{ft}{', ' + sz if sz else ''}]")
        self.files_head.setText(f"{self.tr('dp_files')} ({len(s['files'])})")
        self.open_btn.setEnabled(self._downloaded)
        self.restyle()

    def _paint_levels(self, dark=None):
        t = theme.colours(dark)
        for num, bar, (_k, col, colour) in zip(self.level_nums, self.level_bars, DIFFS):
            lv = self._meta.get(col) if self._song is not None else None
            num.setText(str(lv) if lv is not None else "−")
            bar.set_level(lv, theme.ensure_contrast(colour, (t["window"], t["base"]), 3.0, dark),
                          t["progress_track"])

    # ---- theme
    def restyle(self, dark=None):
        t = theme.colours(dark)
        self.setStyleSheet(
            f"#detailPanel{{background:{t['window']};border-left:1px solid {t['border']};}}"
            f"#detailHead{{color:{t['muted']};font-size:11px;font-weight:600;}}"
            f"#detailTitle{{font-weight:700;font-size:15px;}}"
            f"#detailMuted{{color:{t['muted']};}}"
            f"QListWidget{{background:{t['base']};border:1px solid {t['border']};}}")
        if self._cat_hex:
            self.cat.setStyleSheet(
                f"color:{theme.category_colour(self._cat_hex, dark)};font-weight:600;")
        self._paint_levels(dark)
