"""Qt table models for the song list and the download monitor."""

import re
import unicodedata

from PySide6.QtCore import (Qt, QAbstractTableModel,
                            QModelIndex)

from i18n import CATEGORY_NAMES, CATEGORY_COLORS
import theme
from core import human_speed

# ------------------------------------------------------------ sort keys
_DIGITS = re.compile(r"(\d+)")


def natural_key(text):
    """Case/width-insensitive key where digit runs compare as numbers and
    katakana compares like hiragana ("Song 2" < "Song 10", ア == あ)."""
    t = unicodedata.normalize("NFKC", text or "").casefold()
    t = "".join(chr(ord(ch) - 0x60) if "ァ" <= ch <= "ヶ" else ch for ch in t)
    parts = _DIGITS.split(t)
    # even slots are str, odd slots int: tuples always compare like with like
    return tuple(int(p) if i & 1 else p for i, p in enumerate(parts))


def human_size(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


# ---------------------------------------------------------------- 歌曲清單 model
_CHECK_ROLE = [Qt.CheckStateRole]


class SongModel(QAbstractTableModel):
    COLS = ["c_sel", "c_song", "c_jp", "c_cat", "c_bpm",
            "c_easy", "c_normal", "c_hard", "c_oni", "c_ura", "c_files", "c_dl", "c_new", "c_fav"]
    LEVEL_COLS = {5: "level_easy", 6: "level_normal", 7: "level_hard",
                  8: "level_oni", 9: "level_ura"}
    _CENTER_COLS = frozenset([4, 5, 6, 7, 8, 9, 10, 11, 12, 13])
    DL_COL = 11
    NEW_COL = 12
    _NEW_TEXT = {"new": "sn_badge_new", "updated": "sn_badge_upd"}
    _NEW_TIP = {"new": "sn_tip_new", "updated": "sn_tip_upd"}
    FAV_COL = 13
    _DL_TEXT = {2: "●", 1: "◐", 0: "○"}
    _DL_TIP = {2: "dl_complete", 1: "dl_partial", 0: "dl_none"}

    def __init__(self, tr, jp_map, meta_map=None):
        super().__init__()
        self.tr = tr
        self._jp_map = jp_map
        self._meta_map = meta_map or {}
        self.songs = []          # source order, as given to set_songs()
        self._view = []          # same songs in display (sorted) order
        self._sort_col = -1      # -1 = original order
        self._sort_desc = False
        # checked state is keyed by song identity so it follows the song when sorted
        self.checked = set()     # {(song_name, category), ...}
        self._cells = {}         # id(song) -> cached display strings
        self._skeys = {}         # column -> {id(song): sort value}
        self.update_keys = set()  # downloaded songs with upstream changes
        self.dl_status = {}      # (song_name, category) -> 0 none / 1 partial / 2 complete
        self.new_marks = {}      # (song_name, category) -> "new" / "updated" (last DB update)
        self.favourites = set()  # {(song_name, category), ...}

    # jp/meta maps are replaced wholesale after a DB reload: drop derived caches
    @property
    def jp_map(self):
        return self._jp_map

    @jp_map.setter
    def jp_map(self, v):
        self._jp_map = v
        self._invalidate()

    @property
    def meta_map(self):
        return self._meta_map

    @meta_map.setter
    def meta_map(self, v):
        self._meta_map = v or {}
        self._invalidate()

    def set_download_status(self, status):
        """Install a {(name, category): 0|1|2} map from a folder scan."""
        self.dl_status = status or {}
        self._skeys.pop(self.DL_COL, None)
        if self._sort_col == self.DL_COL:
            self.sort(self.DL_COL, Qt.DescendingOrder if self._sort_desc
                      else Qt.AscendingOrder)
        if self._view:
            self.dataChanged.emit(self.index(0, self.DL_COL),
                                  self.index(len(self._view) - 1, self.DL_COL))

    def set_update_keys(self, keys):
        """Songs whose downloaded files are outdated (shown as ⟳ in the status column)."""
        self.update_keys = set(keys or ())
        self._skeys.pop(self.DL_COL, None)
        if self._view:
            self.dataChanged.emit(self.index(0, self.DL_COL),
                                  self.index(len(self._view) - 1, self.DL_COL))

    def set_new_marks(self, marks):
        """Install the {(name, category): "new"|"updated"} map from the last DB update."""
        self.new_marks = marks or {}
        self._skeys.pop(self.NEW_COL, None)
        if self._sort_col == self.NEW_COL:
            self.sort(self.NEW_COL, Qt.DescendingOrder if self._sort_desc
                      else Qt.AscendingOrder)
        if self._view:
            self.dataChanged.emit(self.index(0, self.NEW_COL),
                                  self.index(len(self._view) - 1, self.NEW_COL))

    def set_favourites(self, favs):
        """Install the starred set (sorted column and star cells refresh)."""
        self.favourites = set(favs)
        self._skeys.pop(self.FAV_COL, None)
        if self._sort_col == self.FAV_COL:
            self.sort(self.FAV_COL, Qt.DescendingOrder if self._sort_desc
                      else Qt.AscendingOrder)
        if self._view:
            self.dataChanged.emit(self.index(0, self.FAV_COL),
                                  self.index(len(self._view) - 1, self.FAV_COL))

    def is_favourite(self, song):
        return self._key(song) in self.favourites

    def toggle_favourite(self, song):
        """Flip the star of one song; returns the new state."""
        key = self._key(song)
        new = set(self.favourites)
        on = key not in new
        (new.add if on else new.discard)(key)
        self.set_favourites(new)
        return on

    def check_favourites(self):
        return self.check_where(self.is_favourite)

    def _invalidate(self):
        self._cells.clear()
        self._skeys.clear()

    @staticmethod
    def _key(song):
        return (song["song_name"], song["category"])

    def is_checked(self, row):
        return self._key(self._view[row]) in self.checked

    def set_songs(self, songs):
        """Replace the list. Songs that are still present stay checked."""
        self.beginResetModel()
        self.songs = list(songs)
        self._invalidate()
        if self.checked:
            self.checked &= {self._key(s) for s in self.songs}
        self._view = self._sorted(self.songs, self._sort_col, self._sort_desc)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._view)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.COLS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.tr(self.COLS[section])
        return None

    def flags(self, index):
        f = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if index.column() == 0:
            f |= Qt.ItemIsUserCheckable
        return f

    def _row_cells(self, song):
        """Display strings for columns 1..10 (cached per song)."""
        cells = self._cells.get(id(song))
        if cells is None:
            name = song["song_name"]
            meta = self._meta_map.get(name) or {}
            cells = [name, self._jp_map.get(name, ""),
                     CATEGORY_NAMES.get(song["category"], song["category"]),
                     meta.get("bpm", "") or ""]
            for col in (5, 6, 7, 8, 9):
                lv = meta.get(self.LEVEL_COLS[col])
                cells.append(str(lv) if lv is not None else "−")
            cells.append(str(len(song["files"])))
            self._cells[id(song)] = cells
        return cells

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row, col = index.row(), index.column()
        song = self._view[row]
        if col == self.FAV_COL:
            fav = self._key(song) in self.favourites
            if role == Qt.DisplayRole:
                return "★" if fav else "☆"
            if role == Qt.ToolTipRole:
                return self.tr("fav_remove" if fav else "fav_add")
            if role == Qt.TextAlignmentRole:
                return int(Qt.AlignCenter)
            if role == Qt.ForegroundRole:
                return theme.status_colour("partial") if fav else theme.status_colour("none")
            return None
        if col == self.DL_COL:
            st = self.dl_status.get(self._key(song))
            if st is not None and self._key(song) in self.update_keys:
                if role == Qt.DisplayRole:
                    return "⟳"
                if role == Qt.ToolTipRole:
                    return self.tr("dl_update_avail")
                if role == Qt.TextAlignmentRole:
                    return int(Qt.AlignCenter)
                if role == Qt.ForegroundRole:
                    return theme.status_colour("partial")
                return None
            if role == Qt.DisplayRole:
                return self._DL_TEXT.get(st, "")
            if role == Qt.ToolTipRole and st is not None:
                return self.tr(self._DL_TIP[st])
            if role == Qt.TextAlignmentRole:
                return int(Qt.AlignCenter)
            if role == Qt.ForegroundRole and st is not None:
                return theme.status_colour({2: "done", 1: "partial", 0: "none"}[st])
            return None
        if col == self.NEW_COL:
            mark = self.new_marks.get(self._key(song))
            if role == Qt.DisplayRole:
                return self.tr(self._NEW_TEXT[mark]) if mark else ""
            if role == Qt.ToolTipRole and mark:
                return self.tr(self._NEW_TIP[mark])
            if role == Qt.TextAlignmentRole:
                return int(Qt.AlignCenter)
            if role == Qt.ForegroundRole and mark:
                return theme.status_colour("done" if mark == "new" else "partial")
            return None
        if role == Qt.DisplayRole:
            return self._row_cells(song)[col - 1] if col else None
        if col == 0:
            if role == Qt.CheckStateRole:
                return Qt.Checked if self._key(song) in self.checked else Qt.Unchecked
            return None
        if role == Qt.TextAlignmentRole:
            return int(Qt.AlignCenter) if col in self._CENTER_COLS else None
        if role == Qt.ForegroundRole:
            if col == 3:
                c = CATEGORY_COLORS.get(song["category"])
                if c:
                    return theme.category_colour(c)
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

    def setData(self, index, value, role=Qt.EditRole):
        if index.column() == 0 and role == Qt.CheckStateRole:
            key = self._key(self._view[index.row()])
            if Qt.CheckState(value) == Qt.Checked:
                self.checked.add(key)
            else:
                self.checked.discard(key)
            self.dataChanged.emit(index, index, _CHECK_ROLE)
            return True
        return False

    def set_all(self, checked):
        """Check/uncheck every song in one step (one dataChanged for the column)."""
        new = {self._key(s) for s in self.songs} if checked else set()
        if new == self.checked:
            return
        self.checked = new
        if self._view:
            self.dataChanged.emit(self.index(0, 0),
                                  self.index(len(self._view) - 1, 0), _CHECK_ROLE)

    # ---- bulk selection helpers: each makes one set and one dataChanged
    def _apply_checked(self, new):
        if new == self.checked:
            return False
        self.checked = new
        if self._view:
            self.dataChanged.emit(self.index(0, 0),
                                  self.index(len(self._view) - 1, 0), _CHECK_ROLE)
        return True

    def invert_checked(self):
        """Flip the check of every listed song."""
        return self._apply_checked({self._key(s) for s in self._view} - self.checked)

    def check_where(self, pred):
        """Add every listed song for which pred(song) is true to the checked set."""
        key = self._key
        return self._apply_checked(
            self.checked | {key(s) for s in self._view if pred(s)})

    def check_by_status(self, status):
        """Check listed songs whose download status equals `status` (0/1/2)."""
        key, st = self._key, self.dl_status
        return self._apply_checked(
            self.checked | {key(s) for s in self._view if st.get(key(s)) == status})

    def check_category(self, category):
        return self.check_where(lambda s: s["category"] == category)

    def keep_visible_only(self):
        """Drop checks that belong to songs not in the current list."""
        return self._apply_checked(self.checked & {self._key(s) for s in self._view})

    def selection_stats(self):
        """(songs, files, bytes) of the checked songs; bytes counts only known sizes."""
        ck = self.checked
        if not ck:
            return 0, 0, 0
        n = nf = total = 0
        key = self._key
        for s in self._view:
            if key(s) in ck:
                n += 1
                nf += len(s["files"])
                for f in s["files"]:
                    total += f.get("size") or 0
        return n, nf, total

    def checked_rows(self):
        ck, key = self.checked, self._key
        return [i for i, s in enumerate(self._view) if key(s) in ck]

    def selected_songs(self):
        """Checked songs, in the current display order."""
        return [s for s in self._view if self._key(s) in self.checked]

    # ---- sorting
    def sort(self, column, order=Qt.AscendingOrder):
        self._sort_col = column if 0 <= column < len(self.COLS) else -1
        self._sort_desc = order == Qt.DescendingOrder
        old = self._view
        new = self._sorted(self.songs, self._sort_col, self._sort_desc)
        if new == old:
            return
        # layout change (not reset) keeps the view's selection, current row and scroll
        self.layoutAboutToBeChanged.emit()
        persistent = self.persistentIndexList()
        if persistent:
            pos = {id(s): i for i, s in enumerate(new)}
            self.changePersistentIndexList(
                persistent,
                [self.index(pos[id(old[p.row()])], p.column()) if p.isValid() else QModelIndex()
                 for p in persistent])
        self._view = new
        self.layoutChanged.emit()

    def _sorted(self, songs, column, desc):
        if column == 0:
            # checked songs first (ascending); stable within each group
            ck = self.checked
            return sorted(songs, key=lambda s: 0 if self._key(s) in ck else 1,
                          reverse=desc)
        if column < 0:
            return list(songs)
        cache = self._skeys.get(column)
        if cache is None:
            cache = self._skeys[column] = {id(s): self._sort_value(column, s) for s in songs}
        present = [s for s in songs if cache[id(s)] is not None]
        missing = [s for s in songs if cache[id(s)] is None]
        present.sort(key=lambda s: cache[id(s)], reverse=desc)   # stable, also when desc
        return present + missing                                  # missing values always last

    def _sort_value(self, col, song):
        name = song["song_name"]
        if col == 1:
            return natural_key(name)
        if col == 2:
            jp = self.jp_map.get(name) or ""
            return natural_key(jp) if jp else None                # untitled last
        if col == 3:
            return natural_key(str(CATEGORY_NAMES.get(song["category"], song["category"])))
        if col == 10:
            return len(song["files"])
        if col == self.DL_COL:
            return self.dl_status.get(self._key(song))            # unscanned last
        if col == self.NEW_COL:
            return {"new": 2, "updated": 1}.get(self.new_marks.get(self._key(song)))
        if col == self.FAV_COL:
            return 0 if self._key(song) in self.favourites else 1   # starred first (ascending)
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
    STATUS_COLOR = {"downloading": "active", "done": "done",
                    "skipped": "skipped", "failed": "fail", "paused": "paused"}

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

    def append(self, files):
        """Add rows for (song, file) pairs not shown yet (queueing)."""
        files = [(s, f) for s, f in files if f["file_path"] not in self.index_of]
        if not files:
            return
        first = len(self.rows)
        self.beginInsertRows(QModelIndex(), first, first + len(files) - 1)
        for song, f in files:
            self.index_of[f["file_path"]] = len(self.rows)
            self.rows.append([f["filename"], song["song_name"], "", 0.0, 0.0])
        self.endInsertRows()

    def update(self, file_path, status, pct, speed):
        r = self.index_of.get(file_path)
        if r is None:
            return
        self.rows[r][2] = status
        self.rows[r][3] = pct
        self.rows[r][4] = speed
        self.dataChanged.emit(self.index(r, 2), self.index(r, 4))

    def update_many(self, changes):
        """Apply {file_path: (status, pct, speed)} and emit one dataChanged per
        run of adjacent rows, covering only the status/pct/speed columns."""
        rows = []
        for fp, (status, pct, speed) in changes.items():
            r = self.index_of.get(fp)
            if r is None:
                continue
            row = self.rows[r]
            row[2], row[3], row[4] = status, pct, speed
            rows.append(r)
        if not rows:
            return
        rows.sort()
        start = prev = rows[0]
        for r in rows[1:]:
            if r != prev + 1:
                self.dataChanged.emit(self.index(start, 2), self.index(prev, 4))
                start = r
            prev = r
        self.dataChanged.emit(self.index(start, 2), self.index(prev, 4))

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.COLS)

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
                return theme.status_colour(c)
        return None
