"""Song-table column management: show/hide menu, order, widths, density.

Everything is stored by column *key* (e.g. "c_bpm"), never by index, so a future
version that adds, removes or reorders columns still reads old config files.
"""
from PySide6.QtCore import QObject, QPoint, Qt, Signal
from PySide6.QtWidgets import QHeaderView, QMenu

ALWAYS_VISIBLE = frozenset(["c_song"])
STRETCH = frozenset(["c_song", "c_jp"])
FIXED = frozenset(["c_sel", "c_dl", "c_new", "c_fav"])   # narrow icon columns
DENSITIES = ("comfortable", "compact")
# density -> (min row height, padding added to font height, cell padding px)
DENSITY_METRICS = {"comfortable": (28, 14, 6), "compact": (22, 6, 3)}


def valid_density(v):
    return v if v in DENSITIES else "comfortable"


def _str_list(v):
    return [x for x in v if isinstance(x, str)] if isinstance(v, list) else []


class ColumnManager(QObject):
    changed = Signal()    # visibility, order or widths changed by the user

    def __init__(self, table, keys, label, tr):
        """keys: column keys in logical order; label(key) -> header text;
        tr(key) -> UI string."""
        super().__init__(table)
        self.table, self.keys, self.label, self.tr = table, list(keys), label, tr
        self.user_widths = {}        # key -> px, only columns the user resized
        self._fitted = False         # content widths measured once
        self._busy = False           # ignore sectionResized caused by us
        hh = self.header = table.horizontalHeader()
        hh.setSectionsMovable(True)
        hh.setStretchLastSection(False)
        hh.setContextMenuPolicy(Qt.CustomContextMenu)
        hh.customContextMenuRequested.connect(self.show_menu)
        hh.sectionResized.connect(self._on_resized)
        hh.sectionMoved.connect(lambda *_: self.changed.emit())
        for c, k in enumerate(self.keys):
            if k in STRETCH:
                hh.setSectionResizeMode(c, QHeaderView.Stretch)
            elif k in FIXED:
                hh.setSectionResizeMode(c, QHeaderView.Fixed)
            else:
                hh.setSectionResizeMode(c, QHeaderView.Interactive)

    # ---- state <-> config
    def state(self):
        hh = self.header
        order = [self.keys[hh.logicalIndex(v)] for v in range(hh.count())]
        return {"columns_order": order,
                "columns_hidden": [k for c, k in enumerate(self.keys)
                                   if hh.isSectionHidden(c)],
                "columns_widths": dict(self.user_widths)}

    def restore(self, disp):
        """Apply display-section values; anything unknown or malformed is ignored."""
        hidden = set(_str_list(disp.get("columns_hidden"))) - ALWAYS_VISIBLE
        saved = _str_list(disp.get("columns_order"))
        order = [k for k in dict.fromkeys(saved) if k in self.keys]
        order += [k for k in self.keys if k not in order]
        hh = self.header
        for v, k in enumerate(order):
            hh.moveSection(hh.visualIndex(self.keys.index(k)), v)
        for c, k in enumerate(self.keys):
            hh.setSectionHidden(c, k in hidden)
        w = disp.get("columns_widths")
        self.user_widths = {
            k: v for k, v in (w.items() if isinstance(w, dict) else ())
            if k in self.keys and k not in STRETCH and k not in FIXED
            and isinstance(v, int) and not isinstance(v, bool) and 20 <= v <= 2000}
        self.apply_widths()

    def reset(self):
        hh = self.header
        for v in range(hh.count()):
            hh.moveSection(hh.visualIndex(v), v)    # logical order
        for c in range(hh.count()):
            hh.setSectionHidden(c, False)
        self.user_widths = {}
        self.apply_widths()

    # ---- widths
    def _on_resized(self, c, _old, new):
        if self._busy or c >= len(self.keys) or self.header.isSectionHidden(c):
            return
        k = self.keys[c]
        if k not in STRETCH and k not in FIXED:
            self.user_widths[k] = int(new)
            self.changed.emit()

    def apply_widths(self):
        """Icon columns and default widths follow the font; content-based widths
        are measured once, when rows first appear (see fit_once)."""
        hh, fm = self.header, self.table.fontMetrics()
        self._busy = True
        try:
            for c, k in enumerate(self.keys):
                if hh.isSectionHidden(c) or k in STRETCH:
                    continue
                head = fm.horizontalAdvance(self.label(k)) + 28
                if k in FIXED:
                    hh.resizeSection(c, max(fm.horizontalAdvance("M") * 3, head - 8))
                elif k in self.user_widths:
                    hh.resizeSection(c, self.user_widths[k])
                else:
                    body = self.table.sizeHintForColumn(c) + 4 if self._fitted else 0
                    hh.resizeSection(c, max(head, body))
        finally:
            self._busy = False

    def fit_once(self):
        """Measure content widths a single time, when the model first has rows."""
        if not self._fitted and self.table.model().rowCount() > 0:
            self._fitted = True
            self.apply_widths()

    def refit(self):
        """Font or density changed: measure again (user-set widths are kept)."""
        self._fitted = False
        self.apply_widths()
        self.fit_once()

    # ---- header context menu
    @staticmethod
    def _popup(menu, global_pos):
        """The one place that runs the menu modally (tests replace it)."""
        return menu.exec(global_pos)

    def show_menu(self, pos=None):
        hh = self.header
        menu = QMenu(self.table)
        for c, k in enumerate(self.keys):
            act = menu.addAction(self.label(k) or k)
            act.setCheckable(True)
            act.setChecked(not hh.isSectionHidden(c))
            act.setEnabled(k not in ALWAYS_VISIBLE)
            act.setData(k)
        menu.addSeparator()
        reset = menu.addAction(self.tr("col_reset"))
        glob = hh.mapToGlobal(pos if isinstance(pos, QPoint) else QPoint(0, 0))
        chosen = self._popup(menu, glob)
        if chosen is None:
            return
        if chosen is reset:
            self.reset()
        elif chosen.data() in self.keys and chosen.data() not in ALWAYS_VISIBLE:
            hh.setSectionHidden(self.keys.index(chosen.data()), not chosen.isChecked())
            self.apply_widths()
        self.changed.emit()
