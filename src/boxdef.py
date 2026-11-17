"""box.def generators for OpenTaiko and YataiDON (pure functions, no Qt)."""

import re

from i18n import CATEGORY_NAMES, CATEGORY_COLORS


def _hex_to_rgb(h):
    h = (h or "").lstrip("#")
    if len(h) == 6:
        try:
            return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        except ValueError:
            pass
    return 68, 68, 68


def _norm_hex(s):
    """正規化成 6 位 HEX（不含 #）；無效回空字串。"""
    s = (s or "").strip().lstrip("#")
    if len(s) == 6:
        try:
            int(s, 16)
            return s.upper()
        except ValueError:
            pass
    return ""


def _clean_name(folder_name):
    """去掉資料夾名前綴序號，如 '01-J-POP'->'J-POP'、'02-アニメ'->'アニメ'、'01 Pop'->'Pop'。"""
    return re.sub(r"^\s*\d+\s*[-_.]?\s*", "", folder_name or "").strip() or (folder_name or "")


# 常見分類（含日文分類名）對應底色，供範本自動上色
GENRE_COLORS = {
    "J-POP": "1E88E5", "アニメ": "FB8C00", "ボーカロイド": "00B5AD",
    "ゲームミュージック": "7E57C2", "バラエティ": "66BB6A",
    "クラシック": "C9A227", "ナムコオリジナル": "EF5350", "キッズ": "EC407A",
}


def _cat_color(folder_name):
    """取分類底色 HEX6（全名 → 去序號 → 日文分類名），預設 444444。"""
    clean = _clean_name(folder_name)
    c = CATEGORY_COLORS.get(folder_name) or CATEGORY_COLORS.get(clean)
    if c:
        return c.lstrip("#").upper()
    return GENRE_COLORS.get(clean, "444444")


def make_boxdef(folder_name):
    """依資料夾名稱產生 box.def 範本（OpenTaiko 格式，顏色含 #，供 ColorTranslator 解析）。"""
    name = _clean_name(folder_name)
    title = CATEGORY_NAMES.get(folder_name, name)
    hex6 = _cat_color(folder_name)
    return (f"#TITLE:{title}\n"
            f"#GENRE:{name}\n"
            f"#BGCOLOR:#{hex6}\n"
            f"#BOXCOLOR:#{hex6}\n")


# --------------------------------------------------------- YataiDON box.def 生成工具
# YataiDON parse_box_def supports: #TITLE / #TITLE<LANG> / #GENRE / #COLLECTION /
# #BACKCOLOR:#RRGGBB / #FORECOLOR:#RRGGBB
#   #BACKCOLOR = the box (folder) colour, #FORECOLOR = the title text outline.
# #GENRE accepts English or Japanese names (GENRE_MAP in enums.h has both).
# COLLECTION strings: DAN DIFFICULTY RECOMMENDED FAVORITE RECENT (+ shipped NEW/SEARCH).

# Canonical genre presets — colours taken from ESE's own official box.def files
# (the #BACKCOLOR/#FORECOLOR format is identical to YataiDON's). Genre folders are
# rendered as a flat coloured box, matching how ESE / 太鼓 ships them.
# key = genre label written to #GENRE -> (title_ja, back_color, fore_color)
YATAI_GENRE_PRESETS = {
    "J-POP":            ("J-POP",            "20A0BA", "004D68"),
    "アニメ":            ("アニメ",            "FF9800", "9C4002"),
    "VOCALOID":         ("ボーカロイド曲",     "29C2C9", "54657E"),
    "どうよう":          ("どうよう",          "FF5286", "99042E"),
    "バラエティー":       ("バラエティー",       "8ED41E", "3C6800"),
    "クラシック":         ("クラシック",        "D1A213", "865800"),
    "ゲームミュージック":  ("ゲームミュージック", "9C75BD", "4F2886"),
    "ナムコオリジナル":    ("ナムコオリジナル",   "FF5A13", "941800"),
}

# Genre combo choices (canonical labels above; combo is editable so any value works)
YATAI_VALID_GENRES = [""] + list(YATAI_GENRE_PRESETS.keys())

# Normalise any English/Japanese genre alias to the canonical preset key.
YATAI_GENRE_ALIAS = {
    "J-POP": "J-POP", "JPOP": "J-POP", "POP": "J-POP", "ポップス": "J-POP",
    "ANIME": "アニメ", "アニメ": "アニメ",
    "VOCALOID": "VOCALOID", "ボーカロイド": "VOCALOID", "ボーカロイド曲": "VOCALOID",
    "CHILDREN": "どうよう", "KIDS": "どうよう", "FOLK": "どうよう",
    "キッズ": "どうよう", "どうよう": "どうよう", "童謡": "どうよう", "童謡・民謡": "どうよう",
    "VARIETY": "バラエティー", "バラエティ": "バラエティー", "バラエティー": "バラエティー",
    "CLASSICAL": "クラシック", "CLASSIC": "クラシック", "クラシック": "クラシック",
    "GAME": "ゲームミュージック", "ゲームミュージック": "ゲームミュージック",
    "NAMCO": "ナムコオリジナル", "ナムコオリジナル": "ナムコオリジナル",
}


def _normalize_yatai_genre(genre):
    """Map an English/Japanese genre alias to its canonical preset key."""
    g = (genre or "").strip()
    return YATAI_GENRE_ALIAS.get(g.upper()) or YATAI_GENRE_ALIAS.get(g) or g


def _detect_yatai_def(folder_name):
    """Auto-detect (genre, collection) from folder name for YataiDON.
    genre is returned as a canonical preset key (Japanese, except J-POP/VOCALOID)."""
    low = folder_name.lower()
    if "dan" in low or "dojo" in low:
        return "", "DAN"
    if "recommend" in low:
        return "", "RECOMMENDED"
    if "recent" in low:
        return "", "RECENT"
    if "favorite" in low or "favour" in low:
        return "", "FAVORITE"
    if "difficulty" in low:
        return "", "DIFFICULTY"
    if "j-pop" in low or "jpop" in low or "pop" in low:
        return "J-POP", ""
    if "anime" in low:
        return "アニメ", ""
    if "vocaloid" in low:
        return "VOCALOID", ""
    if any(k in low for k in ("children", "kids", "folk")):
        return "どうよう", ""
    if "variety" in low:
        return "バラエティー", ""
    if "classical" in low or "classic" in low:
        return "クラシック", ""
    if "game" in low:
        return "ゲームミュージック", ""
    if "namco" in low:
        return "ナムコオリジナル", ""
    return "J-POP", ""


def make_yatai_boxdef(folder_name, title="", title_ja="", genre="", collection="",
                      back_color="", fore_color=""):
    """Generate box.def in YataiDON format.
    Order matches ESE / the reference example: TITLE, TITLEJA, GENRE, BACKCOLOR, FORECOLOR.
    #BACKCOLOR = box colour, #FORECOLOR = title outline colour."""
    lines = [f"#TITLE:{title or folder_name}"]
    if title_ja:
        lines.append(f"#TITLEJA:{title_ja}")
    if genre:
        lines.append(f"#GENRE:{genre}")
    if collection:
        lines.append(f"#COLLECTION:{collection}")
    if back_color:
        hx = _norm_hex(back_color)
        if hx:
            lines.append(f"#BACKCOLOR:#{hx}")
    if fore_color:
        hx = _norm_hex(fore_color)
        if hx:
            lines.append(f"#FORECOLOR:#{hx}")
    return "\n".join(lines) + "\n"
