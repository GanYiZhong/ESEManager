"""Responsive button rows.

A ResponsiveRow is a plain QHBoxLayout inside a widget that can collapse in
ordered *steps* when it gets narrow (icon-only buttons, hidden buttons moved
into an overflow menu, ...). Mode k means "the first k steps are applied".
The width each mode needs is measured from the real size hints; resizing
picks the least-collapsed mode that fits, with hysteresis so dragging the
window edge does not flicker. minimumSizeHint() reports the fully collapsed
width, so the window's minimum width is no longer set by the full-width row.
"""

from PySide6.QtCore import QEvent, QSize
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

HYSTERESIS = 24  # extra px needed before *expanding* back to a wider mode


class ElasticLabel(QLabel):
    """A label that may shrink below its text (clipped) instead of forcing width."""

    def minimumSizeHint(self):
        s = super().minimumSizeHint()
        return QSize(0, s.height())


class ResponsiveRow(QWidget):
    def __init__(self, parent=None, spacing=8):
        super().__init__(parent)
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(spacing)
        self._steps = []        # callables: step(collapsed: bool)
        self._mode = 0
        self._need = None       # cached width needed per mode (len = steps + 1)
        self._busy = False

    # -- configuration
    def row_layout(self):
        return self._lay

    def add_step(self, step):
        """Append a collapse step: step(True) collapses, step(False) restores."""
        self._steps.append(step)
        self._need = None

    @property
    def mode(self):
        return self._mode

    @property
    def mode_count(self):
        return len(self._steps) + 1

    # -- measuring / switching
    def _apply_mode(self, mode):
        for i, step in enumerate(self._steps):
            step(i < mode)
        self._mode = mode
        for i in range(self._lay.count()):   # drop cached per-item size hints
            self._lay.itemAt(i).invalidate()
        # invalidate() only: activate() asks this widget for minimumSizeHint(),
        # which would start another measurement while one is running.
        self._lay.invalidate()

    def reapply(self):
        """Re-run every step for the current mode (after something reset a widget)."""
        self._apply_mode(self._mode)

    def _measure(self):
        cur = self._mode
        self.ensurePolished()
        for child in self.findChildren(QWidget):   # style-sheet padding counts
            child.ensurePolished()
        need = []
        for k in range(len(self._steps) + 1):
            self._apply_mode(k)
            last = k == len(self._steps)
            sz = self._lay.minimumSize() if last else self._lay.sizeHint()
            need.append(sz.width())
        # a more collapsed mode never needs more room than a wider one
        for k in range(1, len(need)):
            need[k] = min(need[k], need[k - 1])
        self._need = need
        self._apply_mode(cur)
        self.updateGeometry()

    def needed_widths(self):
        """Width each mode needs, or None while a measurement is running (a
        size query from inside it must not start another one)."""
        if self._need is None:
            if self._busy:
                return None
            self._busy = True
            try:
                self._measure()
            finally:
                self._busy = False
        return list(self._need)

    def invalidate_widths(self):
        """Re-measure (call after text/font/theme changes)."""
        self._need = None
        self.updateGeometry()
        self.update_mode()

    def update_mode(self, width=None):
        if self._busy or not self._steps:
            return
        need = self.needed_widths()
        if not need:
            return
        w = self.width() if width is None else width
        target = len(need) - 1
        for k, n in enumerate(need):
            if w >= n:
                target = k
                break
        if target < self._mode and w < need[target] + HYSTERESIS:
            target = self._mode  # not enough slack to expand yet
        if target != self._mode:
            self._busy = True
            try:
                self._apply_mode(target)
            finally:
                self._busy = False

    # -- Qt hooks
    def minimumSizeHint(self):
        base = super().minimumSizeHint()
        need = self.needed_widths() if self._steps else None
        if not need:
            return base
        return QSize(need[-1], base.height())

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self.update_mode(ev.size().width())

    def showEvent(self, ev):
        super().showEvent(ev)
        self._need = None   # first real polish may change the hints
        self.updateGeometry()
        self.update_mode()

    def changeEvent(self, ev):
        super().changeEvent(ev)
        if not self._busy and ev.type() in (QEvent.FontChange, QEvent.LanguageChange,
                                              QEvent.StyleChange):
            self._need = None
            self.updateGeometry()
