"""Ctrl+K command palette: a small frameless popup with a search field and a
list. Type to fuzzy-filter commands (matched on the localized label and an
English alias), Up/Down to move, Enter to run, Esc to close. Text that matches
no command well also lists the top song matches; Enter jumps to that song.

The registry is built from the main window's QActions and buttons so it stays
in sync with the menus; a few entries without a QAction are listed explicitly.
"""

from dataclasses import dataclass
from typing import Callable, Optional

from PySide6.QtCore import Qt, QTimer, QRect
from PySide6.QtGui import QColor, QKeySequence
from PySide6.QtWidgets import (QApplication, QDialog, QLineEdit, QListWidget,
                               QListWidgetItem, QStyle, QStyledItemDelegate,
                               QVBoxLayout)

import core
import theme

MAX_SONGS = 5
GOOD_SCORE = 60          # a command scoring below this does not hide song results
_ROLE_ENTRY = Qt.UserRole
_ROLE_SHORT = Qt.UserRole + 1


@dataclass
class Command:
    key: str                       # stable id (recent-use tracking)
    label: str                     # localized text
    alias: str = ""                # English words, also matched
    shortcut: str = ""
    run: Optional[Callable] = None


def _clean(text):
    return (text or "").replace("&", "").strip()


def _score_one(query, hay):
    """Score `query` (lower-case, no spaces) against one haystack; None = no match."""
    hay = hay.lower()
    if not hay:
        return None
    if hay == query:
        return 120
    if hay.startswith(query):
        return 100
    words = hay.replace("/", " ").replace("-", " ").split()
    if any(w.startswith(query) for w in words):
        return 80
    if query in hay:
        return 60
    # subsequence over the text ("dl" -> "download")
    pos = -1
    first = None
    for ch in query:
        pos = hay.find(ch, pos + 1)
        if pos < 0:
            break
        if first is None:
            first = pos
    else:
        return max(10, 40 - (pos - first - len(query)))
    if query in "".join(w[0] for w in words):     # word initials
        return 35
    return None


def score(query, cmd):
    """Best score of the query against the label and the alias (None = no match)."""
    q = "".join(query.lower().split())
    if not q:
        return 0
    best = None
    for hay in (cmd.label, cmd.alias):
        s = _score_one(q, hay)
        if s is not None and (best is None or s > best):
            best = s
    return best


def build_commands(win):
    """Registry from the window's QActions plus buttons that have no QAction."""
    cmds = []

    def add_action(attr, alias):
        act = getattr(win, attr, None)
        if act is None or not act.isEnabled():
            return
        cmds.append(Command(attr, _clean(act.text()), alias,
                            act.shortcut().toString(QKeySequence.NativeText),
                            act.trigger))

    def add_button(attr, alias, shortcut=""):
        b = getattr(win, attr, None)
        if b is None or not b.isEnabled():
            return
        cmds.append(Command(attr, _clean(b.text()), alias, shortcut, b.click))

    add_button("download_btn", "download dl start", "Ctrl+D")
    add_button("pause_btn", "pause resume")
    add_button("stop_btn", "stop cancel")
    add_button("selall_btn", "select all check all")
    add_button("deselall_btn", "select none uncheck all clear selection")
    for attr, alias in (("act_sel_invert", "invert selection"),
                        ("act_sel_notdl", "select not downloaded missing"),
                        ("act_sel_partial", "select partial incomplete"),
                        ("act_sel_cat", "select category"),
                        ("act_sel_visible", "select visible only"),
                        ("act_sel_fav", "select favourites favorites")):
        add_action(attr, alias)
    add_action("act_update_db", "update database db refresh")
    add_action("act_missing", "check missing files")
    add_action("act_updates", "check updates upstream")
    add_action("act_vsort", "version sorting download")
    add_action("act_open_dir", "open folder directory")
    add_action("act_detail", "detail panel details song info")
    add_button("monitor_btn", "monitor download log")
    add_button("reset_filter_btn", "reset filters clear filter")
    add_action("act_settings", "settings preferences options theme language font")
    add_action("act_shortcuts", "keyboard shortcuts help keys")
    add_action("act_official", "official website taiko.ac")
    add_action("act_about", "about version update app")
    return cmds


class _Delegate(QStyledItemDelegate):
    """Label on the left, shortcut (muted) on the right."""

    def paint(self, painter, option, index):
        opt = option
        self.initStyleOption(opt, index)
        text, opt.text = opt.text, ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)
        pal = opt.palette
        selected = bool(opt.state & QStyle.State_Selected)
        painter.save()
        painter.setPen(pal.highlightedText().color() if selected else pal.text().color())
        r = opt.rect.adjusted(10, 0, -10, 0)
        short = index.data(_ROLE_SHORT) or ""
        fm = painter.fontMetrics()
        sw = fm.horizontalAdvance(short) + 12 if short else 0
        painter.drawText(QRect(r.left(), r.top(), r.width() - sw, r.height()),
                         Qt.AlignVCenter | Qt.AlignLeft,
                         fm.elidedText(text, Qt.ElideRight, max(10, r.width() - sw)))
        if short:
            painter.setPen(pal.highlightedText().color() if selected
                           else QColor(theme.colours()["placeholder"]))
            painter.drawText(r, Qt.AlignVCenter | Qt.AlignRight, short)
        painter.restore()

    def sizeHint(self, option, index):
        sh = super().sizeHint(option, index)
        sh.setHeight(max(sh.height(), 30))
        return sh


class CommandPalette(QDialog):
    """`win` is the MainWindow (tr, table, song_model, ...)."""

    def __init__(self, win):
        super().__init__(win, Qt.Popup | Qt.FramelessWindowHint)
        self.win = win
        self.recent = []                 # command keys, most recent first
        self._cmds = []
        self.setObjectName("CommandPalette")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        self.edit = QLineEdit()
        self.edit.textChanged.connect(self._refilter)
        self.edit.installEventFilter(self)
        self.list = QListWidget()
        self.list.setItemDelegate(_Delegate(self.list))
        self.list.setFocusPolicy(Qt.NoFocus)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.itemClicked.connect(lambda _it: self.run_current())
        lay.addWidget(self.edit)
        lay.addWidget(self.list)
        self.setFixedWidth(540)
        self.restyle()

    def restyle(self):
        c = theme.colours()
        self.setStyleSheet(
            f"#CommandPalette {{ background: {c['base']}; border: 1px solid {c['mid']};"
            f" border-radius: 8px; }}"
            f"QListWidget {{ border: none; background: transparent; outline: 0; }}"
            f"QListWidget::item:selected {{ background: {c['highlight']}; border-radius: 4px; }}")

    # ---- showing
    def open_palette(self):
        self.restyle()
        self._cmds = build_commands(self.win)
        self.edit.setPlaceholderText(self.win.tr("palette_ph"))
        self.edit.clear()
        self._refilter()
        w = self.win
        origin = w.mapToGlobal(w.rect().topLeft())
        self.setFixedHeight(380)
        self.move(origin.x() + (w.width() - self.width()) // 2,
                  origin.y() + max(40, w.height() // 6))
        self.show()
        self.edit.setFocus()

    # ---- filtering
    def _recency(self, key):
        return self.recent.index(key) if key in self.recent else len(self.recent) + 1

    def matches(self, text):
        """(score, command) pairs, best first (empty text: recent first)."""
        text = text.strip()
        scored = []
        for order, cmd in enumerate(self._cmds):
            s = score(text, cmd)
            if s is not None:
                scored.append((s, cmd, order))
        if text:
            scored.sort(key=lambda t: (-t[0], self._recency(t[1].key), t[2]))
        else:
            scored.sort(key=lambda t: (self._recency(t[1].key), t[2]))
        return [(s, c) for s, c, _ in scored]

    def _song_matches(self, text):
        try:
            return list(core.search_songs(text) or [])[:MAX_SONGS]
        except Exception:
            core.log.warning("palette song search failed", exc_info=True)
            return []

    def _refilter(self, *_):
        text = self.edit.text()
        self.list.clear()
        found = self.matches(text)
        for _s, cmd in found:
            it = QListWidgetItem(cmd.label)
            it.setData(_ROLE_ENTRY, cmd)
            it.setData(_ROLE_SHORT, cmd.shortcut)
            self.list.addItem(it)
        best = found[0][0] if found else -1
        if text.strip() and best < GOOD_SCORE:
            for song in self._song_matches(text.strip()):
                it = QListWidgetItem(song.get("song_name", ""))
                it.setData(_ROLE_ENTRY, song)
                it.setData(_ROLE_SHORT, self.win.tr("palette_song"))
                self.list.addItem(it)
        if self.list.count():
            self.list.setCurrentRow(0)

    # ---- keys
    def eventFilter(self, obj, ev):
        if obj is self.edit and ev.type() == ev.Type.KeyPress:
            k = ev.key()
            if k in (Qt.Key_Down, Qt.Key_Up):
                n = self.list.count()
                if n:
                    self.list.setCurrentRow(
                        (self.list.currentRow() + (1 if k == Qt.Key_Down else -1)) % n)
                return True
            if k in (Qt.Key_Return, Qt.Key_Enter):
                self.run_current()
                return True
        return super().eventFilter(obj, ev)

    def run_current(self):
        it = self.list.currentItem()
        if it is None:
            return
        entry = it.data(_ROLE_ENTRY)
        self.hide()
        if isinstance(entry, Command):
            if entry.key in self.recent:
                self.recent.remove(entry.key)
            self.recent.insert(0, entry.key)
            del self.recent[20:]
            if entry.run:
                entry.run()
        else:
            self.jump_to_song(entry)

    # ---- song jump
    def jump_to_song(self, song, _tries=0):
        """Select the song's row and open the detail panel. If the current
        list/filter hides it, search for its exact name first and wait."""
        w = self.win
        name = song.get("song_name", "")
        for row, s in enumerate(w.song_model._view):
            if s.get("song_name") == name:
                idx = w.song_model.index(row, 0)
                w.table.setCurrentIndex(idx)
                w.table.selectRow(row)
                w.table.scrollTo(idx)
                w.set_detail_open(True)
                return True
        if _tries == 0:
            w.search_edit.setText(name)
            w._search_now()
        if _tries < 40:
            QTimer.singleShot(100, lambda: self.jump_to_song(song, _tries + 1))
        return False
