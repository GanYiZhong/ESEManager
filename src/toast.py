"""In-window toast notifications.

ToastManager(window) shows small rounded cards stacked at the bottom-right of
the window instead of modal pop-ups for messages that need no decision.

* info toasts fade after ~4 s, warnings after ~8 s, errors stay until closed
* the timer pauses while the pointer is over a card
* at most MAX_VISIBLE cards are shown; the oldest is dropped first
* optional action buttons run a callback and dismiss the card
* each card has an accessible name/description and raises a QAccessible alert
"""

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

import theme

MAX_VISIBLE = 3
INFO_MS = 4000
WARNING_MS = 8000
MARGIN = 12
GAP = 8
CARD_WIDTH = 340
_KINDS = ("info", "warning", "error")


def _announce(widget):
    """Tell assistive technology that a new message appeared (best effort)."""
    try:
        from PySide6.QtGui import QAccessible, QAccessibleEvent
        if QAccessible.isActive():
            QAccessible.updateAccessibility(
                QAccessibleEvent(widget, QAccessible.Event.Alert))
    except Exception:
        pass


class Toast(QFrame):
    def __init__(self, parent, text, kind="info", title="", actions=(),
                 timeout=None, close_label="x", on_close=None):
        super().__init__(parent)
        self.kind = kind if kind in _KINDS else "info"
        self.text = text
        self._on_close = on_close
        self._closed = False
        if timeout is None:
            timeout = {"info": INFO_MS, "warning": WARNING_MS, "error": 0}[self.kind]
        self.timeout = int(timeout)          # 0 = sticky
        self.setObjectName("toast")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedWidth(CARD_WIDTH)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAccessibleName(title or (text.splitlines()[0] if text else ""))
        self.setAccessibleDescription(text)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 8, 8)
        lay.setSpacing(6)
        top = QHBoxLayout()
        top.setSpacing(8)
        body = QVBoxLayout()
        body.setSpacing(2)
        if title:
            self.title_label = QLabel(title)
            self.title_label.setObjectName("toastTitle")
            self.title_label.setWordWrap(True)
            body.addWidget(self.title_label)
        self.label = QLabel(text)
        self.label.setObjectName("toastText")
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body.addWidget(self.label)
        top.addLayout(body, 1)
        self.close_btn = QPushButton("×")
        self.close_btn.setObjectName("toastClose")
        self.close_btn.setFlat(True)
        self.close_btn.setFixedSize(22, 22)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setAccessibleName(close_label)
        self.close_btn.setToolTip(close_label)
        self.close_btn.clicked.connect(self.dismiss)
        top.addWidget(self.close_btn, 0, Qt.AlignTop)
        lay.addLayout(top)

        self.action_buttons = []
        if actions:
            row = QHBoxLayout()
            row.addStretch()
            for label, callback in actions:
                b = QPushButton(label)
                b.setObjectName("toastAction")
                b.setCursor(Qt.PointingHandCursor)
                b.clicked.connect(lambda _=False, cb=callback: self._run(cb))
                row.addWidget(b)
                self.action_buttons.append(b)
            lay.addLayout(row)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)
        self._remaining = self.timeout
        self.restyle()
        theme.add_listener(self.restyle)

    # ---- lifecycle
    def start(self):
        if self.timeout > 0:
            self._timer.start(self._remaining)

    def restart_timer(self):
        self._remaining = self.timeout
        if self.timeout > 0 and not self.underMouse():
            self._timer.start(self._remaining)

    def pause(self):
        """Stop the countdown (pointer over the card)."""
        if self._timer.isActive():
            self._remaining = max(self._timer.remainingTime(), 0)
            self._timer.stop()

    def resume(self):
        if self.timeout > 0 and not self._closed and not self._timer.isActive():
            self._timer.start(max(self._remaining, 1000))

    def enterEvent(self, e):
        self.pause()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.resume()
        super().leaveEvent(e)

    def _run(self, callback):
        self.dismiss()
        callback()

    def dismiss(self):
        if self._closed:
            return
        self._closed = True
        self._timer.stop()
        self.hide()
        if self._on_close:
            self._on_close(self)
        self.deleteLater()

    # ---- style
    def restyle(self, *_):
        try:
            self.objectName()           # raises once the C++ widget is gone
        except RuntimeError:
            return
        t = theme.colours()
        if self.kind == "warning":
            bg, fg, edge = t["hint_bg"], t["hint_fg"], t["hint_border"]
        elif self.kind == "error":
            bg, fg, edge = t["tooltip_base"], t["tooltip_text"], t["bright_text"]
        else:
            bg, fg, edge = t["tooltip_base"], t["tooltip_text"], t["border"]
        self.setStyleSheet(
            f"#toast {{ background: {bg}; border: 1px solid {edge}; border-radius: 10px; }}"
            f"#toast QLabel {{ color: {fg}; background: transparent; }}"
            f"#toastTitle {{ font-weight: bold; }}"
            f"#toastClose {{ color: {fg}; border: none; background: transparent; "
            f"font-size: 16px; }}"
            f"#toastClose:hover {{ background: {t['button_hover']}; border-radius: 11px; }}"
            f"#toastAction {{ color: {t['accent_text']}; background: {t['accent']}; "
            f"border: none; border-radius: 6px; padding: 4px 12px; }}"
            f"#toastAction:hover {{ background: {t['accent_hover']}; }}")


class ToastManager(QObject):
    """Owns the visible toasts of one window and keeps them anchored."""

    def __init__(self, window, tr=None, anchor_bottom=None):
        super().__init__(window)
        self.window = window
        self._tr = tr
        self._anchor_bottom = anchor_bottom     # () -> y (window coords) toasts sit above
        self.toasts = []
        window.installEventFilter(self)

    def _close_label(self):
        return self._tr("toast_close") if self._tr else "Close"

    def show(self, text, kind="info", title="", actions=(), timeout=None):
        """Show a toast; returns it. Identical text refreshes the existing card."""
        for t in self.toasts:
            if t.text == text and t.kind == kind and not t._closed:
                t.restart_timer()
                return t
        toast = Toast(self.window, text, kind, title, actions, timeout,
                      self._close_label(), self._removed)
        self.toasts.append(toast)
        while len(self.toasts) > MAX_VISIBLE:
            self.toasts[0].dismiss()
        toast.show()
        toast.raise_()
        self.reposition()
        toast.start()
        _announce(toast)
        return toast

    def info(self, text, **kw):
        return self.show(text, "info", **kw)

    def warning(self, text, **kw):
        return self.show(text, "warning", **kw)

    def error(self, text, **kw):
        return self.show(text, "error", **kw)

    def clear(self):
        for t in list(self.toasts):
            t.dismiss()

    def _removed(self, toast):
        if toast in self.toasts:
            self.toasts.remove(toast)
        self.reposition()

    def reposition(self):
        w = self.window
        bottom = self._anchor_bottom() if self._anchor_bottom else w.height()
        y = min(bottom, w.height()) - MARGIN
        for t in reversed(self.toasts):          # newest at the bottom
            t.adjustSize()
            y -= t.height()
            t.move(max(w.width() - t.width() - MARGIN, 0), max(y, 0))
            t.raise_()
            y -= GAP

    def eventFilter(self, obj, ev):
        if obj is self.window and ev.type() in (QEvent.Resize, QEvent.Show):
            self.reposition()
        return False
