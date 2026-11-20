"""
Light / dark theme for ESEManager (Qt 6, Fusion style).

apply_theme(app, mode) installs an application-wide QPalette for mode
"light", "dark" or "auto" (follow the OS colour scheme). In "auto" mode the
palette is re-applied live when the OS scheme changes.

Widgets that need custom colours should use the *_qss() helpers (or colours()
from the active mode) instead of hard-coded hex values, so they stay readable
in both modes. Widgets can also register a callback with add_listener() to
restyle themselves when the mode changes.
"""

import inspect
import weakref

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette

MODES = ("auto", "light", "dark")

# Colour tokens per mode. Palette keys feed QPalette; the rest feed the helpers.
_TOKENS = {
    False: {  # light
        "window": "#F4F4F4", "window_text": "#1E1E1E",
        "base": "#FFFFFF", "alt_base": "#F0F4F8", "text": "#1E1E1E",
        "button": "#E9E9E9", "button_text": "#1E1E1E", "bright_text": "#C62828",
        "highlight": "#1565C0", "highlight_text": "#FFFFFF",
        "tooltip_base": "#FFFFFF", "tooltip_text": "#1E1E1E",
        "link": "#1565C0", "placeholder": "#6B6B6B",
        "mid": "#B8B8B8", "dark": "#8A8A8A", "light": "#FFFFFF",
        "disabled_text": "#7A7A7A",
        # helper tokens
        "accent": "#2E7D32", "accent_hover": "#1B5E20", "accent_text": "#FFFFFF",
        "disabled_bg": "#BDBDBD", "disabled_fg": "#616161",
        "hint_bg": "#FFF3CD", "hint_fg": "#5C4400", "hint_border": "#E0C36C",
        "muted": "#6B6B6B", "success": "#2E7D32",
    },
    True: {  # dark
        "window": "#2B2B2B", "window_text": "#E8E8E8",
        "base": "#1E1E1E", "alt_base": "#262626", "text": "#E8E8E8",
        "button": "#3A3A3A", "button_text": "#E8E8E8", "bright_text": "#FF8A80",
        "highlight": "#42A5F5", "highlight_text": "#0D0D0D",
        "tooltip_base": "#3A3A3A", "tooltip_text": "#EEEEEE",
        "link": "#64B5F6", "placeholder": "#9A9A9A",
        # Fusion draws check-box and frame borders from Dark/Mid; keep them
        # clearly lighter than Base so unchecked boxes stay visible.
        "mid": "#5A5A5A", "dark": "#7A7A7A", "light": "#505050",
        "disabled_text": "#7A7A7A",
        "accent": "#2E7D32", "accent_hover": "#388E3C", "accent_text": "#FFFFFF",
        "disabled_bg": "#4A4A4A", "disabled_fg": "#9A9A9A",
        "hint_bg": "#3D3314", "hint_fg": "#FFE08A", "hint_border": "#7A6320",
        "muted": "#9E9E9E", "success": "#81C784",
    },
}

# Palette role -> colour token.
_ROLES = {
    QPalette.Window: "window", QPalette.WindowText: "window_text",
    QPalette.Base: "base", QPalette.AlternateBase: "alt_base",
    QPalette.Text: "text", QPalette.Button: "button",
    QPalette.ButtonText: "button_text", QPalette.BrightText: "bright_text",
    QPalette.Highlight: "highlight", QPalette.HighlightedText: "highlight_text",
    QPalette.ToolTipBase: "tooltip_base", QPalette.ToolTipText: "tooltip_text",
    QPalette.Link: "link", QPalette.PlaceholderText: "placeholder",
    QPalette.Mid: "mid", QPalette.Dark: "dark", QPalette.Light: "light",
}
_DISABLED_ROLES = (QPalette.WindowText, QPalette.Text, QPalette.ButtonText,
                   QPalette.HighlightedText)

_state = {"app": None, "mode": "auto", "dark": False, "hooked": False}
_listeners = []


# ---------------------------------------------------------------- detection
def os_is_dark():
    """True when the OS asks for a dark colour scheme (Qt 6.5+)."""
    try:
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:  # Qt older than 6.5 has no colorScheme()
        return False


def is_dark():
    """Whether the theme last applied by apply_theme() is dark."""
    return _state["dark"]


def current_mode():
    return _state["mode"]


def colours(dark=None):
    """Colour tokens for the given mode (default: the active mode)."""
    if dark is None:
        dark = _state["dark"]
    return _TOKENS[bool(dark)]


def build_palette(dark):
    """Fusion QPalette for light (dark=False) or dark (dark=True) mode."""
    t = _TOKENS[bool(dark)]
    p = QPalette()
    for role, key in _ROLES.items():
        p.setColor(role, QColor(t[key]))
    for role in _DISABLED_ROLES:
        p.setColor(QPalette.Disabled, role, QColor(t["disabled_text"]))
    p.setColor(QPalette.Disabled, QPalette.Highlight, QColor(t["mid"]))
    return p


# ---------------------------------------------------------------- apply
def _resolve(mode):
    if mode == "dark":
        return True
    if mode == "light":
        return False
    return os_is_dark()


def _set_dark(dark):
    app = _state["app"]
    if app is None:
        return
    if app.style().name().lower() != "fusion":
        app.setStyle("Fusion")  # palettes are only honoured reliably in Fusion
    app.setPalette(build_palette(dark))
    _state["dark"] = bool(dark)
    for ref in list(_listeners):
        fn = ref()
        if fn is None:          # owner was garbage-collected
            _listeners.remove(ref)
            continue
        fn(bool(dark))


def _on_os_scheme_changed(*_):
    # Re-resolve the current mode: "auto" follows the OS, explicit modes are
    # re-applied because Qt may reset the app palette on a system theme change.
    if _state["app"] is not None:
        _set_dark(_resolve(_state["mode"]))


def apply_theme(app, mode="auto"):
    """Apply the light, dark or auto (OS-following) theme to app.

    Returns True when the dark palette is now active. Unknown modes act as "auto".
    """
    if mode not in MODES:
        mode = "auto"
    _state["app"] = app
    _state["mode"] = mode
    if not _state["hooked"]:
        try:
            QGuiApplication.styleHints().colorSchemeChanged.connect(_on_os_scheme_changed)
            _state["hooked"] = True
        except AttributeError:  # Qt older than 6.5
            pass
    _set_dark(_resolve(mode))
    return _state["dark"]


def add_listener(fn):
    """Call fn(dark: bool) after every theme change (used to restyle widgets).

    Bound methods are held weakly, so a listener never keeps its owner alive."""
    ref = weakref.WeakMethod(fn) if inspect.ismethod(fn) else weakref.ref(fn)
    if not any(r() is not None and r() == fn for r in _listeners):
        _listeners.append(ref)


# ---------------------------------------------------------------- style sheets
def primary_button_qss(dark=None, padding="8px 16px"):
    """Green call-to-action button (download / convert)."""
    t = colours(dark)
    return (f"QPushButton{{background:{t['accent']};color:{t['accent_text']};"
            f"font-weight:bold;padding:{padding};border-radius:8px;}}"
            f"QPushButton:hover{{background:{t['accent_hover']};}}"
            f"QPushButton:disabled{{background:{t['disabled_bg']};color:{t['disabled_fg']};}}")


def hint_qss(dark=None):
    """Yellow hint banner (first run / empty database)."""
    t = colours(dark)
    return (f"QLabel{{background:{t['hint_bg']};color:{t['hint_fg']};"
            f"border:1px solid {t['hint_border']};border-radius:6px;padding:8px;}}")


def success_text_qss(dark=None):
    """Bold "good news" text (e.g. the app-update notice in the status bar)."""
    return f"QPushButton{{color:{colours(dark)['success']};font-weight:bold;}}"


def category_colour(hex_colour, dark=None):
    """Category colours are mid-tones; darken them on light backgrounds and
    lighten them on dark ones so the text stays readable."""
    from PySide6.QtGui import QColor
    c = QColor(hex_colour)
    dark = is_dark() if dark is None else dark
    return c.lighter(125) if dark else c.darker(135)


def muted_label_qss(dark=None, font_px=None):
    """Secondary / info text colour (replaces hard-coded grey)."""
    t = colours(dark)
    size = f"font-size:{font_px}px;" if font_px else ""
    return f"color:{t['muted']};{size}"


def check_indicator_qss(dark=None):
    """Item-view check boxes. Fusion outlines them with a darker shade of the
    window colour, which disappears on a dark background; draw them explicitly."""
    t = colours(dark)
    border = "#A0A0A0" if t is _TOKENS[True] else "#8A8A8A"
    return (f"QTableView::indicator{{width:14px;height:14px;border-radius:3px;"
            f"border:1px solid {border};background:{t['base']};}}"
            f"QTableView::indicator:checked{{background:{t['highlight']};"
            f"border:1px solid {t['highlight']};}}")
