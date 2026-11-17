"""Qt table models for the song list and the download monitor."""

import re

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex
from PySide6.QtGui import QColor

from i18n import CATEGORY_NAMES, CATEGORY_COLORS


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
        self.songs = []          # source order, as given to set_songs()
        self._view = []          # same songs in display (sorted) order
        self._sort_col = -1      # -1 = original order
        self._sort_desc = False
        # checked state is keyed by song identity so it follows the song when sorted
        self.checked = set()     # {(song_name, category), ...}

    @staticmethod
    def _key(song):
        return (song["song_name"], song["category"])

    def is_checked(self, row):
        return self._key(self._view[row]) in self.checked

    def set_songs(self, songs):
        self.beginResetModel()
        self.songs = list(songs)
        self.checked = set()
        self._view = self._sorted(self.songs, self._sort_col, self._sort_desc)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self._view)

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
        song = self._view[row]
        if col == 0:
            if role == Qt.CheckStateRole:
                return Qt.Checked if self.is_checked(row) else Qt.Unchecked
            return None
        if role == Qt.ToolTipRole:
            if col in (1, 2):
                jp = self.jp_map.get(song["song_name"]) or ""
                cat = CATEGORY_NAMES.get(song["category"], song["category"])
                return "\n".join(x for x in (song["song_name"], jp, str(cat)) if x)
            if col in self.LEVEL_COLS:
                meta = self.meta_map.get(song["song_name"]) or {}
                lv = meta.get(self.LEVEL_COLS[col])
                return f"{self.tr(self.COLS[col])}: {lv if lv is not None else '−'}"
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
            key = self._key(self._view[index.row()])
            if Qt.CheckState(value) == Qt.Checked:
                self.checked.add(key)
            else:
                self.checked.discard(key)
            self.dataChanged.emit(index, index, [Qt.CheckStateRole])
            return True
        return False

    def set_all(self, checked):
        self.checked = {self._key(s) for s in self.songs} if checked else set()
        if self._view:
            self.dataChanged.emit(self.index(0, 0),
                                  self.index(len(self._view) - 1, 0),
                                  [Qt.CheckStateRole])

    def selected_songs(self):
        """Checked songs, in the current display order."""
        return [s for s in self._view if self._key(s) in self.checked]

    # ---- sorting
    def sort(self, column, order=Qt.AscendingOrder):
        self._sort_col = column if 0 <= column < len(self.COLS) else -1
        self._sort_desc = order == Qt.DescendingOrder
        self.beginResetModel()
        self._view = self._sorted(self.songs, self._sort_col, self._sort_desc)
        self.endResetModel()

    def _sorted(self, songs, column, desc):
        if column == 0:
            # checked songs first (ascending); stable within each group
            return sorted(songs, key=lambda s: 0 if self._key(s) in self.checked else 1,
                           reverse=desc)
        if column < 0:
            return list(songs)
        pairs = [(self._sort_value(column, s), s) for s in songs]
        present = [p for p in pairs if p[0] is not None]
        missing = [s for v, s in pairs if v is None]
        present.sort(key=lambda p: p[0], reverse=desc)   # stable, also when desc
        return [s for _, s in present] + missing          # missing values always last

    def _sort_value(self, col, song):
        name = song["song_name"]
        if col == 1:
            return name.casefold()
        if col == 2:
            return (self.jp_map.get(name) or "").casefold() or None   # untitled last
        if col == 3:
            return str(CATEGORY_NAMES.get(song["category"], song["category"])).casefold()
        if col == 10:
            return len(song["files"])
        meta = self.meta_map.get(name) or {}
        if col == 4:
            m = re.search(r"\d+(?:\.\d+)?", str(meta.get("bpm") or ""))
            return float(m.group()) if m else None
        if col in self.LEVEL_COLS:
            return meta.get(self.LEVEL_COLS[col])
        return None


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
