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

MODES = ("auto", "light", "dark", "high_contrast")

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
        "border": "#C4C4C4", "button_hover": "#DEDEDE", "button_pressed": "#D0D0D0",
        "header_bg": "#ECEEF1", "progress_track": "#DADDE1", "progress_chunk": "#90CAF9",
        "scroll_handle": "#B4B4B4", "check_border": "#8A8A8A",
        # status glyph / text colours (contrast >= 3:1 on white rows)
        # Colour-blind-safe (Okabe-Ito derived): blue / amber / red, never a
        # red-green pair; glyphs and text labels back every colour up anyway.
        "st_done": "#0072B2", "st_partial": "#B8860B", "st_none": "#767676",
        "st_active": "#5E35B1", "st_fail": "#B3261E", "st_paused": "#B8860B",
        "st_skipped": "#6B6B6B",
        # difficulty level bars: easy, normal, hard, oni, ura (Okabe-Ito derived)
        "lv_easy": "#D55E00", "lv_normal": "#00896A", "lv_hard": "#0072B2",
        "lv_oni": "#B34D86", "lv_ura": "#6B5B00",
        "lv_default": "#888888",
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
        "hint_bg": "#302B1C", "hint_fg": "#F0DFA6", "hint_border": "#5C5024",
        "muted": "#9E9E9E", "success": "#81C784",
        "border": "#4A4A4A", "button_hover": "#464646", "button_pressed": "#525252",
        "header_bg": "#323232", "progress_track": "#3A3A3A", "progress_chunk": "#1F6AB5",
        "scroll_handle": "#5E5E5E", "check_border": "#A0A0A0",
        "st_done": "#56B4E9", "st_partial": "#F0E442", "st_none": "#9A9A9A",
        "st_active": "#B39DDB", "st_fail": "#FF8A50", "st_paused": "#F0E442",
        "st_skipped": "#9E9E9E",
        "lv_easy": "#E69F00", "lv_normal": "#009E73", "lv_hard": "#56B4E9",
        "lv_oni": "#CC79A7", "lv_ura": "#F0E442",
        "lv_default": "#888888",
    },
    # High contrast: white on black, yellow selection/focus, text pairs >= 7:1
    "hc": {
        "window": "#000000", "window_text": "#FFFFFF",
        "base": "#000000", "alt_base": "#141414", "text": "#FFFFFF",
        "button": "#000000", "button_text": "#FFFFFF", "bright_text": "#FF9090",
        "highlight": "#FFFF00", "highlight_text": "#000000",
        "tooltip_base": "#000000", "tooltip_text": "#FFFFFF",
        "link": "#6FD8FF", "placeholder": "#D0D0D0",
        "mid": "#FFFFFF", "dark": "#FFFFFF", "light": "#FFFFFF",
        "disabled_text": "#B8B8B8",
        "accent": "#00FF7F", "accent_hover": "#FFFFFF", "accent_text": "#000000",
        "disabled_bg": "#000000", "disabled_fg": "#B8B8B8",
        "hint_bg": "#000000", "hint_fg": "#FFFF00", "hint_border": "#FFFF00",
        "muted": "#D8D8D8", "success": "#00FF7F",
        "border": "#FFFFFF", "button_hover": "#333333", "button_pressed": "#4D4D4D",
        "header_bg": "#000000", "progress_track": "#000000", "progress_chunk": "#0040A0",
        "scroll_handle": "#FFFFFF", "check_border": "#FFFFFF",
        "st_done": "#5CC8FF", "st_partial": "#FFFF4D", "st_none": "#BFBFBF",
        "st_active": "#D0B0FF", "st_fail": "#FF9A66", "st_paused": "#FFFF4D",
        "st_skipped": "#C8C8C8",
        "lv_easy": "#FFB000", "lv_normal": "#00E0A0", "lv_hard": "#5CC8FF",
        "lv_oni": "#FF7AC8", "lv_ura": "#FFFF4D",
        "lv_default": "#BFBFBF",
        # layout tokens: 2px borders and focus rings in a bright colour
        "hc": "1", "border_px": "2", "focus": "#FFFF00",
    },
}
for _k in (False, True):
    _TOKENS[_k].update(hc="", border_px="1", focus=_TOKENS[_k]["highlight"])

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

_state = {"app": None, "mode": "auto", "dark": False, "hc": False,
          "hooked": False, "fusion": False}
_listeners = []


# ---------------------------------------------------------------- detection
def os_is_dark():
    """True when the OS asks for a dark colour scheme (Qt 6.5+)."""
    try:
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:  # Qt older than 6.5 has no colorScheme()
        return False


def os_high_contrast():
    """True when Windows high-contrast mode is on (SPI_GETHIGHCONTRAST).

    Best effort: always False off Windows or if the call fails (Qt's
    colorScheme() does not report high contrast)."""
    import sys
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        class HIGHCONTRASTW(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("dwFlags", wintypes.DWORD),
                        ("lpszDefaultScheme", wintypes.LPWSTR)]
        hc = HIGHCONTRASTW()
        hc.cbSize = ctypes.sizeof(hc)
        ok = ctypes.windll.user32.SystemParametersInfoW(
            0x0042, hc.cbSize, ctypes.byref(hc), 0)  # SPI_GETHIGHCONTRAST
        return bool(ok and hc.dwFlags & 0x1)  # HCF_HIGHCONTRASTON
    except Exception:
        return False


def is_dark():
    """Whether the theme last applied by apply_theme() is dark (also true for
    high contrast, which is light-on-dark)."""
    return _state["dark"]


def is_high_contrast():
    return _state["hc"]


def _key(dark):
    """Token-set key: "hc" if asked for, or when a dark palette is requested
    while high contrast is active; else the bool."""
    if dark == "hc":
        return "hc"
    return "hc" if dark and _state["hc"] else bool(dark)


def current_mode():
    return _state["mode"]


def colours(dark=None):
    """Colour tokens for the given mode (default: the active mode)."""
    if dark is None:
        dark = _state["dark"]
    return _TOKENS[_key(dark)]


def build_palette(dark):
    """Fusion QPalette for light (False), dark (True) or high contrast ("hc")."""
    t = _TOKENS[_key(dark)]
    p = QPalette()
    for role, key in _ROLES.items():
        p.setColor(role, QColor(t[key]))
    for role in _DISABLED_ROLES:
        p.setColor(QPalette.Disabled, role, QColor(t["disabled_text"]))
    p.setColor(QPalette.Disabled, QPalette.Highlight, QColor(t["mid"]))
    return p


# ---------------------------------------------------------------- apply
def _resolve(mode):
    """Theme key for a mode: False (light), True (dark) or "hc"."""
    if mode == "high_contrast":
        return "hc"
    if mode == "dark":
        return True
    if mode == "light":
        return False
    return "hc" if os_high_contrast() else os_is_dark()


def _set_dark(key):
    app = _state["app"]
    if app is None:
        return
    hc = key == "hc"
    dark = hc or bool(key)
    _state["hc"] = hc
    # Palettes are only honoured reliably in Fusion. Once an application style
    # sheet is installed style().name() is empty, so remember that we did this.
    if not _state["fusion"] and app.style().name().lower() != "fusion":
        app.setStyle("Fusion")
    _state["fusion"] = True
    app.setPalette(build_palette("hc" if hc else dark))
    app.setStyleSheet(app_qss("hc" if hc else dark))
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

    Modes: auto (OS dark scheme, or Windows high contrast), light, dark,
    high_contrast. Returns True when a dark-based palette (dark or high
    contrast) is now active. Unknown modes act as "auto".
    """
    if mode not in MODES:
        mode = "auto"
    if _state["app"] is not app:
        _state["fusion"] = False
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
            f"font-weight:bold;padding:{padding};border-radius:8px;"
            f"border:1px solid {t['accent']};}}"
            f"QPushButton:hover{{background:{t['accent_hover']};border-color:{t['accent_hover']};}}"
            f"QPushButton:focus{{border:{t['border_px']}px solid {t['focus']};}}"
            f"QPushButton:disabled{{background:{t['disabled_bg']};color:{t['disabled_fg']};"
            f"border-color:{t['disabled_bg']};}}")


def hint_qss(dark=None):
    """Yellow hint banner (first run / empty database)."""
    t = colours(dark)
    return (f"QLabel{{background:{t['hint_bg']};color:{t['hint_fg']};"
            f"border:1px solid {t['hint_border']};border-radius:6px;padding:8px;}}")


def empty_state_qss(dark=None):
    """Quiet message over an empty table ("no songs match"): no box, muted text."""
    t = colours(dark)
    return (f"QLabel{{background:transparent;color:{t['muted']};border:none;"
            f"font-size:14px;padding:8px;}}")


def bad_input_qss(dark=None):
    """Red outline for a line edit holding a token we could not parse."""
    return f"QLineEdit{{border:1px solid {colours(dark)['st_fail']};}}"


def success_text_qss(dark=None):
    """Bold "good news" text (e.g. the app-update notice in the status bar)."""
    return (f"QPushButton{{color:{colours(dark)['success']};font-weight:bold;"
            f"background:transparent;border:none;min-height:0;padding:0 6px;}}")


def _luminance(c):
    def ch(v):
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(c.redF()) + 0.7152 * ch(c.greenF()) + 0.0722 * ch(c.blueF())


def contrast_ratio(a, b):
    """WCAG 2.x contrast ratio (1..21) between two colours (QColor or hex)."""
    la, lb = _luminance(QColor(a)), _luminance(QColor(b))
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def ensure_contrast(fg, backgrounds, target=4.5, dark=None):
    """Nudge fg (lighter on dark themes, darker on light ones) until it reaches
    the WCAG contrast `target` against every colour in backgrounds."""
    c = QColor(fg)
    dark = is_dark() if dark is None else dark
    for _ in range(40):
        if all(contrast_ratio(c, bg) >= target for bg in backgrounds):
            break
        c = c.lighter(108) if dark else c.darker(108)
    return c


def category_colour(hex_colour, dark=None):
    """Category colours are mid-tones; shift them until they meet WCAG AA (4.5:1)
    against both row backgrounds of the active theme."""
    dark = is_dark() if dark is None else dark
    t = colours(dark)
    target = 7.0 if t["hc"] else 4.5
    return ensure_contrast(hex_colour, (t["base"], t["alt_base"]), target, dark)


def status_colour(key, dark=None):
    """Theme-aware colour for a status glyph / label ("done", "fail", ...)."""
    return QColor(colours(dark)["st_" + key])


def muted_label_qss(dark=None, font_px=None):
    """Secondary / info text colour (replaces hard-coded grey)."""
    t = colours(dark)
    size = f"font-size:{font_px}px;" if font_px else ""
    return f"color:{t['muted']};{size}"


def _icon(name, colour, points, width=3.4):
    """PNG of a polyline glyph in `colour` (cached in the temp dir); QSS needs a file."""
    import os
    import tempfile
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QImage, QPainter, QPen
    d = os.path.join(tempfile.gettempdir(), "ESEManager-theme")
    path = os.path.join(d, f"{name}_{colour.lstrip('#')}.png")
    if not os.path.exists(path):
        os.makedirs(d, exist_ok=True)
        img = QImage(28, 28, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(colour), width)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.drawPolyline([QPointF(x, y) for x, y in points])
        p.end()
        img.save(path)
    return path.replace(chr(92), "/")


def _tick_icon(colour):
    return _icon("tick", colour, [(6.5, 14.5), (11.8, 19.8), (21.5, 8.5)])


def _chevron_icon(colour):
    return _icon("chev", colour, [(7, 10), (14, 17.5), (21, 10)], 3.0)


def check_indicator_qss(dark=None):
    """Item-view check boxes. Fusion outlines them with a darker shade of the
    window colour, which disappears on a dark background; draw them explicitly
    (with a tick, also visible on the selected row)."""
    t = colours(dark)
    border = t["check_border"]
    tick = _tick_icon(t["highlight_text"])
    tick_sel = _tick_icon(t["highlight"])
    return (f"QTableView::indicator{{width:16px;height:16px;border-radius:4px;"
            f"border:1px solid {border};background:{t['base']};}}"
            f"QTableView::indicator:checked{{background:{t['highlight']};"
            f"border:1px solid {t['highlight']};image:url({tick});}}"
            f"QTableView::indicator:checked:selected{{background:{t['highlight_text']};"
            f"border:1px solid {t['highlight_text']};image:url({tick_sel});}}"
            f"QTableView::indicator:unchecked:selected{{border:1px solid {t['highlight_text']};}}")


def app_qss(dark=None):
    """Application-wide polish on top of the palette: consistent buttons and
    inputs, visible focus rings, flat table with a quiet header, slim progress
    bar, underlined tabs and thin scroll bars."""
    t = colours(dark)
    bw, fc = t["border_px"], t["focus"]
    extra = f"""
QTableView:focus, QListWidget:focus, QPlainTextEdit:focus {{ border:2px solid {fc}; }}
QTabBar::tab:focus {{ border:2px solid {fc}; }}
QHeaderView::section {{ border-right:1px solid {t['border']}; }}
QProgressBar {{ border:2px solid {t['border']}; }}
QToolTip {{ background:{t['tooltip_base']}; color:{t['tooltip_text']}; border:2px solid {t['border']}; }}
""" if t["hc"] else ""
    return f"""
QPushButton, QToolButton {{
    background:{t['button']}; color:{t['button_text']};
    border:{bw}px solid {t['border']}; border-radius:6px;
    padding:4px 12px; min-height:20px;
}}
QPushButton:hover, QToolButton:hover {{ background:{t['button_hover']}; }}
QPushButton:pressed, QToolButton:pressed, QToolButton:checked {{
    background:{t['button_pressed']};
}}
QPushButton:focus, QToolButton:focus {{ border:{bw}px solid {fc}; }}
QPushButton:disabled, QToolButton:disabled {{
    color:{t['disabled_text']}; background:{t['window']};
}}
QToolButton::menu-indicator {{ subcontrol-position:right center; right:6px; }}
QLineEdit, QComboBox {{
    background:{t['base']}; color:{t['text']};
    border:{bw}px solid {t['border']}; border-radius:6px;
    padding:4px 8px; min-height:20px;
    selection-background-color:{t['highlight']}; selection-color:{t['highlight_text']};
}}
QLineEdit:focus, QComboBox:focus, QComboBox:on {{
    border:{bw}px solid {fc};
}}
QLabel#sectionHeader {{ font-weight:700; font-size:14px; color:{t['text']}; padding-top:2px; }}
QFrame#sectionRule {{ background:{t['border']}; border:none; }}
QLabel#helperText {{ color:{t['muted']}; font-size:12px; }}
QComboBox::drop-down {{ border:none; width:24px; }}
QComboBox::down-arrow {{ image:url({_chevron_icon(t['muted'])}); width:14px; height:14px; }}
QComboBox QAbstractItemView {{ background:{t['base']}; border:1px solid {t['border']};
    selection-background-color:{t['highlight']}; selection-color:{t['highlight_text']}; outline:0; }}
QLineEdit:disabled, QComboBox:disabled {{ background:{t['window']}; color:{t['disabled_text']}; }}
QPlainTextEdit, QListWidget {{
    background:{t['base']}; color:{t['text']};
    border:1px solid {t['border']}; border-radius:6px; outline:0; padding:4px;
    selection-background-color:{t['highlight']}; selection-color:{t['highlight_text']};
}}
QTabWidget::pane {{ border:none; border-top:1px solid {t['border']}; top:-1px; }}
QTableView {{
    background:{t['base']}; alternate-background-color:{t['alt_base']};
    border:1px solid {t['border']}; border-radius:6px; outline:0;
    gridline-color:transparent;
    selection-background-color:{t['highlight']}; selection-color:{t['highlight_text']};
}}
QTableView::item {{ padding:0 6px; }}
QTableView::item:selected {{ background:{t['highlight']}; color:{t['highlight_text']}; }}
QHeaderView::section {{
    background:{t['header_bg']}; color:{t['muted']}; font-weight:600;
    padding:5px 8px; border:none; border-bottom:1px solid {t['border']};
}}
QProgressBar {{
    background:{t['progress_track']}; color:{t['text']}; border:none;
    border-radius:8px; text-align:center; min-height:16px;
}}
QProgressBar::chunk {{ background:{t['progress_chunk']}; border-radius:8px; }}
QTabBar::tab {{
    padding:6px 16px; border:none; border-bottom:2px solid transparent; color:{t['muted']};
}}
QTabBar::tab:hover {{ color:{t['text']}; }}
QTabBar::tab:selected {{ color:{t['text']}; border-bottom:2px solid {t['highlight']}; }}
QStatusBar {{ color:{t['muted']}; }}
QStatusBar::item {{ border:none; }}
QScrollBar:vertical {{ background:transparent; width:12px; margin:0; }}
QScrollBar:horizontal {{ background:transparent; height:12px; margin:0; }}
QScrollBar::handle:vertical {{ background:{t['scroll_handle']}; border-radius:4px; min-height:28px; margin:2px; }}
QScrollBar::handle:horizontal {{ background:{t['scroll_handle']}; border-radius:4px; min-width:28px; margin:2px; }}
QScrollBar::handle:hover {{ background:{t['dark']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width:0; height:0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background:transparent; }}
{extra}"""


def cell_padding_qss(px):
    """Horizontal padding of song-table cells (density setting)."""
    return f"QTableView::item{{padding:0 {int(px)}px;}}"
