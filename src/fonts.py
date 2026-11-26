"""UI fonts: a clean Latin face first, then the right CJK face per language.

Qt falls back per character through QFont.families(), so listing a Latin font
before a CJK one gives Segoe UI for "Miku Miku" and 正黑體 for 中文. Japanese
text (titles from ese_local.db) gets a Japanese font, otherwise its kanji are
drawn with Chinese glyph shapes. Only installed families are used.
"""

from PySide6.QtGui import QFont, QFontDatabase

LATIN = ["Segoe UI Variable Text", "Segoe UI", "Inter", "Noto Sans", "Cantarell",
         "Ubuntu", "DejaVu Sans", "Helvetica Neue", "Arial"]
CJK = {
    "zh_TW": ["Microsoft JhengHei UI", "Microsoft JhengHei", "PingFang TC",
              "Noto Sans CJK TC", "Noto Sans TC", "Source Han Sans TC"],
    "ja": ["Yu Gothic UI", "Meiryo UI", "Meiryo", "Hiragino Sans",
           "Noto Sans CJK JP", "Noto Sans JP", "Source Han Sans JP"],
}
CJK["en"] = CJK["zh_TW"] + CJK["ja"]


def _installed(names):
    have = {f.lower() for f in QFontDatabase.families()}
    return [n for n in names if n.lower() in have]


def ui_families(lang):
    """Font stack for the whole UI in `lang` (zh_TW / en / ja)."""
    primary = CJK.get(lang, CJK["en"])
    rest = [n for n in CJK["zh_TW"] + CJK["ja"] if n not in primary]
    return _installed(LATIN) + _installed(primary + rest)


def japanese_families():
    """Stack for Japanese strings (titles), whatever the UI language."""
    return _installed(LATIN) + _installed(CJK["ja"] + CJK["zh_TW"])


def ui_font(lang, point_size=None):
    f = QFont()
    fams = ui_families(lang)
    if fams:
        f.setFamilies(fams)
    if point_size:
        f.setPointSizeF(point_size)
    f.setHintingPreference(QFont.PreferNoHinting)
    return f


def japanese_font(base):
    """`base` (size, weight) with a Japanese font stack."""
    f = QFont(base)
    fams = japanese_families()
    if fams:
        f.setFamilies(fams)
    return f
