"""Qt table models for the song list and the download monitor."""

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
