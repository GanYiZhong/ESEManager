"""Dialogs: OpenTaiko box.def editor, YataiDON box.def generator and Dan tools."""

import json
import os
import re
import sqlite3

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox,
    QHeaderView, QFileDialog, QPlainTextEdit, QTabWidget, QMessageBox, QDialog,
    QFormLayout, QColorDialog, QFrame, QScrollArea, QTableWidget, QTableWidgetItem,
    QProgressBar
)

import dan_tools
from appconfig import DB_PATH, LOCAL_DB_PATH, app_path
from i18n import CATEGORY_NAMES
from tja_parser import read_text_file
from boxdef import (_hex_to_rgb, _norm_hex, _clean_name, _cat_color, make_boxdef,
                    YATAI_GENRE_PRESETS, YATAI_VALID_GENRES, _normalize_yatai_genre,
                    _detect_yatai_def, make_yatai_boxdef)
from workers import BoxDefFetchThread


# ------------------------------------------------------------ shared helpers
_HEX6_RE = re.compile(r"#?[0-9A-Fa-f]{6}")
_BAD_COLOR_STYLE = "QLineEdit{border:2px solid #E53935;}"


def _color_ok(text):
    """True when the text is empty or a 6-digit hex colour, with or without '#'."""
    s = (text or "").strip()
    return not s or _HEX6_RE.fullmatch(s) is not None


def _mark_color_edit(edit, tip):
    """Red border + tooltip while the colour text is invalid."""
    bad = not _color_ok(edit.text())
    edit.setStyleSheet(_BAD_COLOR_STYLE if bad else "")
    edit.setToolTip(tip if bad else "")


def _load_dialog_prefs():
    """Contents of dialogs.json as a dict; a missing or corrupt file gives {}."""
    try:
        with open(app_path("dialogs.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


class YataiBoxDefDialog(QDialog):
    """YataiDON box.def 批量生成工具。
    為 Songs 資料夾內每個子資料夾產生正確格式的 box.def（GENRE/COLLECTION/顏色）。
    """

    COL_FOLDER  = 0
    COL_TITLE   = 1
    COL_TITLEJA = 2
    COL_GENRE   = 3
    COL_COLL    = 4
    COL_BACK    = 5
    COL_FORE    = 6

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
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            self.tr("yatai_col_folder"),
            self.tr("yatai_col_title"),
            self.tr("yatai_col_titleja"),
            self.tr("yatai_col_genre"),
            self.tr("yatai_col_collection"),
            self.tr("yatai_col_back"),
            self.tr("yatai_col_fore"),
        ])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(self.COL_FOLDER,  QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(self.COL_TITLE,   QHeaderView.Stretch)
        hh.setSectionResizeMode(self.COL_TITLEJA, QHeaderView.Stretch)
        hh.setSectionResizeMode(self.COL_GENRE,   QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(self.COL_COLL,    QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(self.COL_BACK,    QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(self.COL_FORE,    QHeaderView.ResizeToContents)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        root.addWidget(self.table, 1)

        # Info
        info = QLabel(self.tr("yatai_info"))
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
        edit.setMaxLength(7)   # room for a leading '#'
        edit.setPlaceholderText("RRGGBB")
        edit.setFixedWidth(72)
        swatch = QFrame()
        swatch.setFixedSize(18, 18)
        btn = QPushButton("🎨")
        btn.setFixedWidth(28)
        btn.setFlat(True)

        def upd():
            hx = _norm_hex(edit.text())
            swatch.setStyleSheet(
                (f"background:#{hx};border:1px solid #555;border-radius:2px;") if hx
                else "border:1px solid #555;border-radius:2px;"
            )
            _mark_color_edit(edit, self.tr("dlg_color_invalid"))

        def pick():
            cur = _norm_hex(edit.text())
            init = QColor("#" + cur) if cur else QColor("#444444")
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
            ex_title  = sub
            ex_titleja = ""
            ex_genre  = ""
            ex_coll   = ""
            ex_back   = ""
            ex_fore   = ""
            if os.path.exists(bpath):
                try:
                    for line in read_text_file(bpath).splitlines():
                        s = line.strip()
                        if s.startswith("#TITLEJA:"):
                            ex_titleja = s[9:]
                        elif s.startswith("#TITLE:") and ex_title == sub:
                            ex_title = s[7:]
                        elif s.startswith("#GENRE:"):
                            ex_genre = s[7:]
                        elif s.startswith("#COLLECTION:"):
                            ex_coll = s[12:].upper()
                        elif s.startswith("#BACKCOLOR:"):
                            ex_back = s[11:].lstrip("#").upper()
                        elif s.startswith("#FORECOLOR:"):
                            ex_fore = s[11:].lstrip("#").upper()
                except Exception:
                    pass

            # Auto-detect when existing file has no genre/collection
            if not ex_genre and not ex_coll:
                ex_genre, ex_coll = _detect_yatai_def(sub)
            # Normalise any English/JP genre alias to a canonical preset key
            ex_genre = _normalize_yatai_genre(ex_genre)

            # Fill TITLEJA + colours from the genre preset (ESE palette) when
            # missing. #BACKCOLOR = box colour, #FORECOLOR = text outline. For
            # COLLECTION folders we leave colours blank so the built-in art shows.
            preset = YATAI_GENRE_PRESETS.get(ex_genre)
            if preset:
                if not ex_titleja:
                    ex_titleja = preset[0]
                if not ex_back:
                    ex_back = preset[1]
                if not ex_fore:
                    ex_fore = preset[2]

            # Col 0: folder (read-only)
            fi = QTableWidgetItem(sub)
            fi.setFlags(fi.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row_idx, self.COL_FOLDER, fi)

            # Col 1/2: titles
            self.table.setItem(row_idx, self.COL_TITLE, QTableWidgetItem(ex_title))
            self.table.setItem(row_idx, self.COL_TITLEJA, QTableWidgetItem(ex_titleja))

            # Col 3: genre combo (editable so any English/JP name is allowed)
            combo = QComboBox()
            combo.setEditable(True)
            combo.addItems(YATAI_VALID_GENRES)
            combo.setCurrentText(ex_genre)
            self.table.setCellWidget(row_idx, self.COL_GENRE, combo)

            # Col 4: collection (free text)
            self.table.setItem(row_idx, self.COL_COLL, QTableWidgetItem(ex_coll))

            # Col 5/6: colors
            self.table.setCellWidget(row_idx, self.COL_BACK, self._color_widget(row_idx, self.COL_BACK, ex_back))
            self.table.setCellWidget(row_idx, self.COL_FORE, self._color_widget(row_idx, self.COL_FORE, ex_fore))

        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(self.COL_TITLE, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(self.COL_TITLEJA, QHeaderView.Stretch)

    def _folder_names(self):
        return [self.table.item(r, self.COL_FOLDER).text()
                for r in range(self.table.rowCount()) if self.table.item(r, self.COL_FOLDER)]

    def generate_all(self):
        base = self.folder_edit.text().strip()
        if not os.path.isdir(base):
            QMessageBox.warning(self, self.tr("yatai_title"), self.tr("boxdef_no_dir"))
            return
        # Refuse to write anything while a colour is invalid.
        bad = []
        for row in range(self.table.rowCount()):
            if any(not _color_ok(self._color_edits[(row, c)].text())
                   for c in (self.COL_BACK, self.COL_FORE) if (row, c) in self._color_edits):
                item = self.table.item(row, self.COL_FOLDER)
                bad.append(item.text() if item else str(row + 1))
        if bad:
            QMessageBox.warning(self, self.tr("yatai_title"),
                                self.tr("dlg_yatai_bad_color", rows=", ".join(bad)))
            return
        # Ask before overwriting existing box.def files.
        existing = [s for s in self._folder_names()
                    if os.path.exists(os.path.join(base, s, "box.def"))]
        if existing and QMessageBox.question(
                self, self.tr("yatai_title"),
                self.tr("dlg_yatai_overwrite_q", n=len(existing)),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
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
            titleja_item = self.table.item(row, self.COL_TITLEJA)
            titleja = titleja_item.text().strip() if titleja_item else ""
            genre_w = self.table.cellWidget(row, self.COL_GENRE)
            genre = genre_w.currentText().strip() if genre_w else ""
            coll_item = self.table.item(row, self.COL_COLL)
            coll = coll_item.text().strip().upper() if coll_item else ""
            back_e = self._color_edits.get((row, self.COL_BACK))
            fore_e = self._color_edits.get((row, self.COL_FORE))
            back = _norm_hex(back_e.text()) if back_e else ""
            fore = _norm_hex(fore_e.text()) if fore_e else ""

            content = make_yatai_boxdef(sub, title=title, title_ja=titleja,
                                        genre=genre, collection=coll,
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
        self._base_title = tr("boxdef_title")
        self.setWindowTitle(self._base_title)
        self.resize(600, 720)
        self.extra = []   # 保留無法辨識的行，存檔時原樣寫回
        self._dirty = False   # unsaved edits in the form
        self._quiet = 0       # >0 while load/fill code sets fields programmatically
        outer = QVBoxLayout(self)

        # 資料夾列
        fr = QHBoxLayout()
        self.dir_edit = QLineEdit(default_dir)
        browse = QPushButton(tr("browse"))
        browse.clicked.connect(self.browse)
        load = QPushButton(tr("boxdef_load"))
        load.clicked.connect(lambda: self.load())
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
            e.textChanged.connect(self._touch)
            self.title_edits[code] = e
            form.addRow("%s (%s)" % (key, BOXDEF_LANG_LABEL[code]), e)

        # 分類（可編輯下拉）
        self.genre = QComboBox()
        self.genre.setEditable(True)
        self.genre.addItems([""] + BOXDEF_GENRES)
        self.genre.editTextChanged.connect(self._update_preview)
        self.genre.editTextChanged.connect(self._touch)
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
            e.textChanged.connect(self._touch)
            self.text_edits[tk] = e
            form.addRow("#" + tk, e)

        # 說明（3 行）
        self.exp_edits = []
        for i in range(3):
            e = QLineEdit()
            e.textChanged.connect(self._touch)
            self.exp_edits.append(e)
            form.addRow("#BOXEXPLANATION%d" % (i + 1), e)

        # 按鈕列
        br = QHBoxLayout()
        fetch = self.fetch_btn = QPushButton(tr("boxdef_fetch"))
        fetch.setToolTip(tr("boxdef_fetch_tip"))
        fetch.clicked.connect(self.fetch_ese)
        gen = QPushButton(tr("boxdef_gen"))
        gen.clicked.connect(self.generate)
        save = QPushButton(tr("boxdef_save"))
        save.clicked.connect(lambda: self.save())
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self.save)
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
            _mark_color_edit(edit, self.tr("dlg_color_invalid"))
            self._update_preview()

        btn.clicked.connect(pick)
        edit.textChanged.connect(upd)
        edit.textChanged.connect(self._touch)
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

    def _touch(self, *_):
        """Any user edit marks the form dirty (ignored while loading)."""
        if not self._quiet:
            self._set_dirty(True)

    def _set_dirty(self, dirty):
        self._dirty = dirty
        self.setWindowTitle(self._base_title + (" *" if dirty else ""))

    def _confirm_discard(self):
        """Ask before throwing away unsaved edits. True means it is safe to go on."""
        if not self._dirty:
            return True
        return QMessageBox.question(
            self, self.tr("boxdef_title"), self.tr("dlg_boxdef_unsaved"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes

    def browse(self):
        d = QFileDialog.getExistingDirectory(self, self.tr("browse"), self.dir_edit.text())
        if d and self._confirm_discard():
            self.dir_edit.setText(d)
            self.load(confirm=False)

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

    def load(self, confirm=True):
        if confirm and not self._confirm_discard():
            return
        self._quiet += 1
        try:
            self._clear()
            p = self._path()
            if not os.path.exists(p):
                self._fill_template()
            else:
                try:
                    self._apply_text(read_text_file(p))
                except Exception as e:
                    print("boxdef load:", e)
        finally:
            self._quiet -= 1
        self._set_dirty(False)
        self._update_preview()

    def fetch_ese(self):
        """Fetch ESE's official box.def for this category (matched by folder name
        or number) on a worker thread, then fill the form."""
        name = os.path.basename(self.dir_edit.text().rstrip("/\\"))
        m = re.match(r"\s*(\d+)", name)
        num = m.group(1).zfill(2) if m else None
        if not os.path.exists(DB_PATH):
            QMessageBox.information(self, self.tr("boxdef_title"), self.tr("empty_hint"))
            return
        try:
            conn = sqlite3.connect(DB_PATH)
            try:
                paths = [r[0] for r in conn.execute(
                    "SELECT file_path FROM song_files WHERE lower(filename)='box.def'")]
            finally:
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
        if not self._confirm_discard():
            return
        self.fetch_btn.setEnabled(False)
        self.fetch_btn.setText(self.tr("boxdef_fetching"))
        self._fetch = BoxDefFetchThread(target)
        self._fetch.done.connect(self._on_fetched)
        self._fetch.start()

    def _on_fetched(self, ok, text, target):
        self.fetch_btn.setEnabled(True)
        self.fetch_btn.setText(self.tr("boxdef_fetch"))
        if not ok:
            QMessageBox.critical(self, self.tr("boxdef_title"),
                                 self.tr("boxdef_fetch_fail", e=text))
            return
        self._quiet += 1
        try:
            self._clear()
            self._apply_text(text)
        finally:
            self._quiet -= 1
        self._set_dirty(True)   # fetched content is not saved yet
        self._update_preview()
        QMessageBox.information(self, self.tr("boxdef_title"),
                                self.tr("boxdef_fetch_ok", c=target.split("/")[0]))

    def done(self, r):
        if not self._confirm_discard():
            return
        # Do not destroy the dialog while its fetch thread is still running.
        if getattr(self, "_fetch", None) and self._fetch.isRunning():
            self._fetch.wait(35000)
        super().done(r)

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
        bad = [ck for ck in BOXDEF_COLORS if not _color_ok(self.color_edits[ck].text())]
        if bad:
            QMessageBox.warning(self, self.tr("boxdef_title"),
                                self.tr("dlg_boxdef_bad_color", fields=", ".join("#" + b for b in bad)))
            return
        try:
            with open(self._path(), "w", encoding="utf-8") as f:
                f.write(self._to_text())
            self._set_dirty(False)
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


class YataiDanThread(QThread):
    log = Signal(str)
    done = Signal(bool, str)

    def __init__(self, url, yatai_root, source_songs, local_db=""):
        super().__init__()
        self.url, self.yatai_root = url, yatai_root
        self.source_songs, self.local_db = source_songs, local_db

    def run(self):
        try:
            n = dan_tools.generate_yatai_dan_from_wiki(
                self.url, self.yatai_root, source_songs_folder=self.source_songs,
                log=self.log.emit, local_db=self.local_db)
            self.done.emit(True, str(n))
        except Exception as e:
            self.done.emit(False, str(e))


class DanToolsDialog(QDialog):
    """段位生成（Wiki）+ 段位變換（tja）+ YataiDON 段位。移植自 bluetaiko/SongConvertor。"""

    def __init__(self, parent, tr, start_dir):
        super().__init__(parent)
        self.tr = tr
        self.start_dir = start_dir
        self._thread = None
        self._close_after = False   # user chose to close once the running task ends
        self.setWindowTitle(tr("dan_title"))
        self.resize(720, 560)

        root = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_gen_tab(), tr("dan_tab_gen"))
        self.tabs.addTab(self._build_conv_tab(), tr("dan_tab_conv"))
        self.tabs.addTab(self._build_yatai_tab(), tr("ydan_tab"))
        root.addWidget(self.tabs)

        # Indeterminate busy bar, shown only while a worker thread runs.
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        root.addWidget(self.progress)

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

        self._restore_prefs()

    # ------------------------------------------------ remembered folders
    def _folder_fields(self):
        return {"gen_out": self.gen_out, "gen_songs": self.gen_songs,
                "conv_tja": self.conv_tja, "conv_out": self.conv_out,
                "conv_songs": self.conv_songs, "ydan_root": self.ydan_root,
                "ydan_src": self.ydan_src}

    def _restore_prefs(self):
        saved = _load_dialog_prefs().get("dan_tools")
        if not isinstance(saved, dict):
            return
        for key, edit in self._folder_fields().items():
            if isinstance(saved.get(key), str):
                edit.setText(saved[key])

    def _save_prefs(self):
        data = _load_dialog_prefs()
        data["dan_tools"] = {k: e.text().strip() for k, e in self._folder_fields().items()}
        try:
            with open(app_path("dialogs.json"), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except (OSError, TypeError, ValueError):
            pass

    # ------------------------------------------------ busy / close handling
    def _running(self):
        return self._thread is not None and self._thread.isRunning()

    def done(self, r):
        if self._running():
            if not self._close_after:
                if QMessageBox.question(self, self.tr("dan_title"), self.tr("dlg_dan_busy_q"),
                                        QMessageBox.Yes | QMessageBox.No,
                                        QMessageBox.No) == QMessageBox.Yes:
                    self._close_after = True
                    self.log_view.appendPlainText("… " + self.tr("dlg_dan_closing"))
            return   # keep the dialog open until the thread has finished
        self._save_prefs()
        super().done(r)

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

    def _build_yatai_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        hint = QLabel(self.tr("ydan_hint"))
        hint.setStyleSheet("color:#aaa;")
        v.addWidget(hint)
        form = QFormLayout()
        self.ydan_url = QLineEdit()
        self.ydan_url.setPlaceholderText(
            "https://wikiwiki.jp/taiko-fumen/%E6%AE%B5%E4%BD%8D%E9%81%93%E5%A0%B4")
        form.addRow(self.tr("dan_gen_url"), self.ydan_url)
        self.ydan_root = QLineEdit()
        form.addRow(self.tr("ydan_root"), self._with_browse(self.ydan_root, lambda: self._pick_dir(self.ydan_root)))
        self.ydan_src = QLineEdit()
        form.addRow(self.tr("ydan_src"), self._with_browse(self.ydan_src, lambda: self._pick_dir(self.ydan_src)))
        v.addLayout(form)
        self.ydan_btn = QPushButton(self.tr("ydan_run"))
        self.ydan_btn.setStyleSheet(
            "QPushButton{background:#1976D2;color:white;font-weight:bold;padding:8px;border-radius:8px;}"
            "QPushButton:hover{background:#1565C0;} QPushButton:disabled{background:#7c7c7c;}")
        self.ydan_btn.clicked.connect(self.run_yatai)
        v.addWidget(self.ydan_btn)
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
        # Lock every tab page (inputs, browse buttons and run buttons).
        for i in range(self.tabs.count()):
            self.tabs.widget(i).setEnabled(not on)
        self.progress.setVisible(on)

    def _path_problem(self, checks):
        """checks: [(label_key, path, must_be_file)]. Warn and return True on the first
        non-empty path that does not exist. Empty paths are skipped (optional fields)."""
        for key, path, is_file in checks:
            if not path:
                continue
            ok = os.path.isfile(path) if is_file else os.path.isdir(path)
            if not ok:
                QMessageBox.warning(self, self.tr("dan_title"),
                                    self.tr("dlg_dan_missing", name=self.tr(key), path=path))
                return True
        return False

    def run_gen(self):
        url = self.gen_url.text().strip()
        out = self.gen_out.text().strip()
        if not url:
            QMessageBox.warning(self, self.tr("dan_title"), self.tr("dan_need_url"))
            return
        if not out:
            QMessageBox.warning(self, self.tr("dan_title"), self.tr("dan_need_out"))
            return
        if self._path_problem([("dan_songs", self.gen_songs.text().strip(), False)]):
            return
        self._save_prefs()
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
        if self._path_problem([("dan_conv_tja", tja, True),
                               ("dan_songs_opt", self.conv_songs.text().strip(), False)]):
            return
        self._save_prefs()
        self._busy(True)
        self.log_view.appendPlainText("▶ " + self.tr("dan_running"))
        self._thread = DanConvThread(tja, out, self.conv_songs.text().strip())
        self._thread.log.connect(self.log_view.appendPlainText)
        self._thread.done.connect(self._on_done)
        self._thread.start()

    def run_yatai(self):
        url = self.ydan_url.text().strip()
        root = self.ydan_root.text().strip()
        if not url:
            QMessageBox.warning(self, self.tr("dan_title"), self.tr("dan_need_url"))
            return
        if not root:
            QMessageBox.warning(self, self.tr("dan_title"), self.tr("ydan_need_root"))
            return
        if self._path_problem([("ydan_root", root, False),
                               ("ydan_src", self.ydan_src.text().strip(), False)]):
            return
        self._save_prefs()
        self._busy(True)
        self.log_view.appendPlainText("▶ " + self.tr("dan_running"))
        local_db = os.path.abspath(LOCAL_DB_PATH) if os.path.isfile(LOCAL_DB_PATH) else ""
        self._thread = YataiDanThread(url, root, self.ydan_src.text().strip(), local_db)
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
        if self._close_after:
            self._close_after = False
            self._thread.wait()   # the worker has emitted done; let it exit before closing
            self._save_prefs()
            QDialog.done(self, QDialog.Rejected)
