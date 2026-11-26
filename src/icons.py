"""Monochrome SVG icons (src/icons/*.svg), tinted to the active theme.

The SVG files draw with ``currentColor``; icon() substitutes a concrete colour
and renders them with QtSvg, so an icon always matches the theme's text colour
(call it again after a theme change). Works from source and when frozen by
PyInstaller (data folder ``icons`` under sys._MEIPASS).
"""

import os
import sys

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

import theme

NAMES = ("search", "filter", "download", "refresh", "check-list", "update",
         "mail", "retry", "folder", "pause", "play", "stop", "chevron-up",
         "chevron-down", "keyboard", "music")

_RENDER_PX = 64          # rendered large; Qt scales it down crisply
_cache = {}


def icon_dir():
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "icons")


def icon_path(name):
    return os.path.join(icon_dir(), name + ".svg")


def _pixmap(name, colour, px=_RENDER_PX):
    with open(icon_path(name), "rb") as f:
        svg = f.read().replace(b"currentColor", colour.encode("ascii"))
    renderer = QSvgRenderer(QByteArray(svg))
    img = QImage(px, px, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    renderer.render(p)
    p.end()
    return QPixmap.fromImage(img)


def icon(name, dark=None, colour=None):
    """QIcon for `name` in the theme's button-text colour (or `colour`);
    its Disabled mode uses the theme's disabled-text colour."""
    t = theme.colours(dark)
    colour = colour or t["button_text"]
    key = (name, colour, t["disabled_text"])
    ic = _cache.get(key)
    if ic is None:
        ic = QIcon()
        ic.addPixmap(_pixmap(name, colour), QIcon.Normal)
        ic.addPixmap(_pixmap(name, t["disabled_text"]), QIcon.Disabled)
        _cache[key] = ic
    return ic
