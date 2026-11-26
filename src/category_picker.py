"""Multi-select category picker: a tool button whose popup menu holds one
checkable entry per category (coloured dot, song count) plus "All"."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QToolButton

import theme
from i18n import CATEGORY_COLORS, CATEGORY_NAMES


def short_name(name):
    """'Anime' for '02 Anime' (first word of the display name)."""
    disp = CATEGORY_NAMES.get(name, name)
    return disp.split()[0] if disp.split() else disp


def _dot(colour, size=12):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(colour))
    p.drawEllipse(1, 1, size - 2, size - 2)
    p.end()
    return QIcon(pm)


class _CheckMenu(QMenu):
    """Toggling a checkable entry (mouse, Space, Enter) keeps the menu open."""

    def _toggle_active(self):
        act = self.activeAction()
        if act is not None and act.isCheckable():
            act.toggle()
            return True
        return False

    def mouseReleaseEvent(self, ev):
        act = self.actionAt(ev.position().toPoint())
        if act is not None and act.isCheckable() and act.isEnabled():
            act.toggle()
            return
        super().mouseReleaseEvent(ev)

    def keyPressEvent(self, ev):
        if ev.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter) and self._toggle_active():
            return
        super().keyPressEvent(ev)


class CategoryPicker(QToolButton):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPopupMode(QToolButton.InstantPopup)
        self.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.setFocusPolicy(Qt.StrongFocus)
        self._menu = _CheckMenu(self)
        self.setMenu(self._menu)
        self._tr = lambda key, **kw: key
        self._all_text = "All"
        self._items = []          # [(name, QAction)]
        self._all_act = None
        self._updating = False

    def set_translator(self, tr):
        self._tr = tr
        self._all_text = tr("all_cat")
        self._refresh_text()

    def set_categories(self, counts_by_name, selected=()):
        """counts_by_name: ordered {category: song count}. Keeps `selected`
        (names that still exist)."""
        self._updating = True
        self._menu.clear()
        self._items = []
        self._all_act = QAction(self._tr("cat_all_menu"), self._menu)
        self._all_act.triggered.connect(lambda: self.set_selected([]))
        self._menu.addAction(self._all_act)
        self._menu.addSeparator()
        wanted = set(selected)
        for name, n in counts_by_name.items():
            act = QAction(f"{CATEGORY_NAMES.get(name, name)} ({n})", self._menu)
            act.setCheckable(True)
            act.setChecked(name in wanted)
            act.setData(name)
            act.toggled.connect(self._on_toggled)
            self._menu.addAction(act)
            self._items.append((name, act))
        self._updating = False
        self.refresh_icons()
        self._refresh_text()

    def refresh_icons(self, dark=None):
        for name, act in self._items:
            hexc = CATEGORY_COLORS.get(name)
            act.setIcon(_dot(theme.category_colour(hexc, dark) if hexc
                             else QColor(Qt.gray)))

    def selected(self):
        """Checked category names in menu order; [] means all categories."""
        return [n for n, a in self._items if a.isChecked()]

    def set_selected(self, names):
        names = set(names)
        self._updating = True
        for n, a in self._items:
            a.setChecked(n in names)
        self._updating = False
        self._refresh_text()
        self.changed.emit()

    def _on_toggled(self, _checked=False):
        if self._updating:
            return
        self._refresh_text()
        self.changed.emit()

    def summary(self):
        sel = self.selected()
        if not sel or len(sel) == len(self._items):
            return self._all_text
        if len(sel) <= 2:
            return " + ".join(short_name(n) for n in sel)
        return self._tr("cat_n", n=len(sel))

    def _refresh_text(self):
        self.setText(self.summary())
