"""High-contrast theme, colour-blind-safe palettes and runtime theme switching."""
import itertools
import math

import pytest
from PySide6.QtGui import QColor, QPalette

import theme  # src/ is on sys.path via conftest.py
from i18n import CATEGORY_COLORS

HC = "hc"


@pytest.fixture(autouse=True)
def _restore_theme(qapp):
    yield
    if theme._state["mode"] != "light" or theme.is_dark() or theme.is_high_contrast():
        theme.apply_theme(qapp, "light")
    theme._listeners.clear()


# ---------------------------------------------------------------- contrast
# every (foreground token, background token) pair that carries text in the HC theme
TEXT_PAIRS = [
    ("text", "base"), ("text", "alt_base"), ("window_text", "window"),
    ("button_text", "button"), ("button_text", "button_hover"),
    ("button_text", "button_pressed"), ("highlight_text", "highlight"),
    ("tooltip_text", "tooltip_base"), ("link", "base"), ("link", "window"),
    ("placeholder", "base"), ("disabled_text", "window"), ("disabled_text", "base"),
    ("disabled_fg", "disabled_bg"), ("accent_text", "accent"),
    ("accent_text", "accent_hover"), ("hint_fg", "hint_bg"),
    ("muted", "window"), ("muted", "base"), ("muted", "alt_base"),
    ("muted", "header_bg"), ("success", "window"), ("success", "base"),
    ("bright_text", "base"), ("bright_text", "window"),
    ("text", "progress_chunk"), ("text", "progress_track"),
] + [(f"st_{k}", bg) for k in ("done", "partial", "none", "active", "fail",
                               "paused", "skipped") for bg in ("base", "alt_base")]


@pytest.mark.parametrize("fg,bg", TEXT_PAIRS)
def test_high_contrast_text_pairs_reach_7_to_1(fg, bg):
    t = theme._TOKENS[HC]
    ratio = theme.contrast_ratio(t[fg], t[bg])
    assert ratio >= 7.0, f"{fg} on {bg}: {ratio:.2f}"


def test_high_contrast_palette_roles_reach_7_to_1():
    p = theme.build_palette(HC)
    pairs = [(QPalette.Text, QPalette.Base), (QPalette.WindowText, QPalette.Window),
             (QPalette.ButtonText, QPalette.Button),
             (QPalette.HighlightedText, QPalette.Highlight),
             (QPalette.ToolTipText, QPalette.ToolTipBase),
             (QPalette.Link, QPalette.Base), (QPalette.PlaceholderText, QPalette.Base)]
    for fg, bg in pairs:
        assert theme.contrast_ratio(p.color(fg), p.color(bg)) >= 7.0, (fg, bg)
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        assert theme.contrast_ratio(p.color(QPalette.Disabled, role),
                                    p.color(QPalette.Window)) >= 7.0


def test_high_contrast_difficulty_bars_and_borders_visible():
    t = theme._TOKENS[HC]
    for k in ("lv_easy", "lv_normal", "lv_hard", "lv_oni", "lv_ura"):
        assert theme.contrast_ratio(t[k], t["window"]) >= 7.0
        assert theme.contrast_ratio(t[k], t["base"]) >= 7.0
    assert theme.contrast_ratio(t["border"], t["window"]) >= 7.0
    assert theme.contrast_ratio(t["focus"], t["window"]) >= 7.0
    assert theme.contrast_ratio(t["check_border"], t["base"]) >= 7.0


def test_high_contrast_category_colours_when_active(qapp):
    theme.apply_theme(qapp, "high_contrast")
    t = theme.colours()
    vals = CATEGORY_COLORS.values() if isinstance(CATEGORY_COLORS, dict) else CATEGORY_COLORS
    for hex_colour in vals:
        c = theme.category_colour(hex_colour)
        assert theme.contrast_ratio(c, t["base"]) >= 7.0
        assert theme.contrast_ratio(c, t["alt_base"]) >= 7.0


def test_high_contrast_focus_ring_is_two_pixels():
    qss = theme.app_qss(HC)
    assert "QPushButton:focus, QToolButton:focus { border:2px solid #FFFF00; }" in qss
    assert "QTableView:focus" in qss and "border:2px solid #FFFF00" in qss
    assert "border:2px solid #FFFFFF" in qss            # control borders
    assert "2px solid #FFFF00" not in theme.app_qss(False)
    assert "border:2px solid" in theme.primary_button_qss(HC)


def test_high_contrast_does_not_rely_on_colour_alone():
    """Selected tab and focus are marked by a thick border / underline, selected
    rows invert text colour, and disabled controls differ in colour *and* style."""
    qss = theme.app_qss(HC)
    assert "QTabBar::tab:selected" in qss and "border-bottom:2px solid" in qss
    t = theme._TOKENS[HC]
    assert t["highlight"] != t["base"] and t["highlight_text"] != t["text"]


# ---------------------------------------------------------------- colour vision
_LIN2LMS = {
    "protan": ((0.152286, 1.052583, -0.204868), (0.114503, 0.786281, 0.099216),
               (-0.003882, -0.048116, 1.051998)),
    "deutan": ((0.367322, 0.860646, -0.227968), (0.280085, 0.672501, 0.047413),
               (-0.011820, 0.042940, 0.968881)),
    "tritan": ((1.255528, -0.076749, -0.178779), (-0.078411, 0.930809, 0.147602),
               (0.004733, 0.691367, 0.303900)),
}


def _lin(v):
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def _lab(rgb):
    x, y, z = (sum(m * c for m, c in zip(row, rgb)) for row in
               ((0.4124, 0.3576, 0.1805), (0.2126, 0.7152, 0.0722), (0.0193, 0.1192, 0.9505)))

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    fx, fy, fz = f(x / 0.95047), f(y), f(z / 1.08883)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def simulate(hex_colour, kind):
    """CIELAB of a colour as seen with protanopia/deuteranopia/tritanopia
    (Machado et al. 2009, severity 1.0, linear RGB); kind "normal" = unchanged."""
    c = QColor(hex_colour)
    rgb = [_lin(c.redF()), _lin(c.greenF()), _lin(c.blueF())]
    if kind != "normal":
        rgb = [min(1.0, max(0.0, sum(m * v for m, v in zip(row, rgb))))
               for row in _LIN2LMS[kind]]
    return _lab(rgb)


def min_distance(colours, kind):
    return min(math.dist(simulate(a, kind), simulate(b, kind))
               for a, b in itertools.combinations(colours, 2))


KINDS = ("normal", "protan", "deutan", "tritan")
MIN_DELTA_E = 10.0


def test_simulation_collapses_red_green():
    """Sanity check of the matrices: a red/green pair gets far closer for a
    deuteranope than for normal vision."""
    normal = math.dist(simulate("#E53935", "normal"), simulate("#43A047", "normal"))
    deut = math.dist(simulate("#E53935", "deutan"), simulate("#43A047", "deutan"))
    assert deut < normal * 0.6
    assert simulate("#808080", "deutan") == pytest.approx(simulate("#808080", "normal"), abs=2.0)


@pytest.mark.parametrize("key", [False, True, HC])
@pytest.mark.parametrize("kind", KINDS)
def test_difficulty_colours_distinguishable_under_cvd(key, kind):
    t = theme._TOKENS[key]
    cols = [t[k] for k in ("lv_easy", "lv_normal", "lv_hard", "lv_oni", "lv_ura")]
    assert min_distance(cols, kind) >= MIN_DELTA_E


@pytest.mark.parametrize("key", [False, True, HC])
@pytest.mark.parametrize("kind", KINDS)
def test_status_colours_distinguishable_under_cvd(key, kind):
    t = theme._TOKENS[key]
    cols = [t[f"st_{k}"] for k in ("done", "partial", "fail", "none")]
    assert min_distance(cols, kind) >= MIN_DELTA_E


def test_difficulty_bars_carry_text_labels():
    """Colour is never the only cue: each bar has a name label and a number."""
    import detail_panel
    assert len(detail_panel.DIFFS) == 5
    for name_key, _col, _token in detail_panel.DIFFS:
        assert name_key.startswith("c_")


# ---------------------------------------------------------------- switching
def test_runtime_switching_to_and_from_high_contrast(qapp, monkeypatch):
    monkeypatch.setattr(theme, "os_is_dark", lambda: False)
    monkeypatch.setattr(theme, "os_high_contrast", lambda: False)
    seen = []
    def listener(dark):
        seen.append((dark, theme.is_high_contrast(), theme.colours(dark)["window"]))
    theme._listeners.clear()
    theme.add_listener(listener)

    assert theme.apply_theme(qapp, "light") is False
    assert not theme.is_high_contrast()
    light_window = qapp.palette().color(QPalette.Window)

    assert theme.apply_theme(qapp, "high_contrast") is True       # dark-based
    assert theme.is_high_contrast() and theme.is_dark()
    assert qapp.palette().color(QPalette.Window) == QColor("#000000")
    assert qapp.palette().color(QPalette.WindowText) == QColor("#FFFFFF")
    assert theme.colours()["highlight"] == "#FFFF00"
    assert "border:2px solid #FFFF00" in qapp.styleSheet()

    assert theme.apply_theme(qapp, "dark") is True
    assert not theme.is_high_contrast() and theme.is_dark()
    assert qapp.palette().color(QPalette.Window) == QColor(theme._TOKENS[True]["window"])
    assert theme.colours()["highlight"] != "#FFFF00"
    assert "2px solid #FFFF00" not in qapp.styleSheet()

    theme.apply_theme(qapp, "high_contrast")
    theme.apply_theme(qapp, "light")
    assert not theme.is_high_contrast() and not theme.is_dark()
    assert qapp.palette().color(QPalette.Window) == light_window
    assert seen[0] == (False, False, theme._TOKENS[False]["window"])
    assert (True, True, "#000000") in seen
    assert seen[-1] == (False, False, theme._TOKENS[False]["window"])


def test_auto_picks_high_contrast_when_os_reports_it(qapp, monkeypatch):
    monkeypatch.setattr(theme, "os_is_dark", lambda: False)
    monkeypatch.setattr(theme, "os_high_contrast", lambda: True)
    assert theme.apply_theme(qapp, "auto") is True
    assert theme.is_high_contrast()
    monkeypatch.setattr(theme, "os_high_contrast", lambda: False)
    theme._on_os_scheme_changed()                       # OS leaves high contrast
    assert not theme.is_high_contrast() and not theme.is_dark()
    # an explicit light/dark choice ignores the OS high-contrast flag
    monkeypatch.setattr(theme, "os_high_contrast", lambda: True)
    theme.apply_theme(qapp, "light")
    assert not theme.is_high_contrast()


def test_os_high_contrast_never_raises(monkeypatch):
    assert theme.os_high_contrast() in (True, False)
    import sys
    monkeypatch.setattr(sys, "platform", "linux")
    assert theme.os_high_contrast() is False


def test_theme_combo_offers_high_contrast_and_saves(qapp, tmp_path, monkeypatch):
    import appconfig
    import ese_qt
    import core
    import workers

    cfg = tmp_path / "config.toml"
    for mod in (appconfig, ese_qt, workers, core):
        for name, val in (("DB_PATH", tmp_path / "ese_songs.db"),
                          ("LOCAL_DB_PATH", tmp_path / "ese_local.db"),
                          ("CONFIG_FILE", cfg)):
            if hasattr(mod, name):
                monkeypatch.setattr(mod, name, str(val))
    monkeypatch.setattr(theme, "os_is_dark", lambda: False)
    monkeypatch.setattr(theme, "os_high_contrast", lambda: False)
    w = ese_qt.MainWindow()
    try:
        codes = [w.theme_combo.itemData(i) for i in range(w.theme_combo.count())]
        assert codes == ["auto", "light", "dark", "high_contrast"]
        w.theme_combo.setCurrentIndex(w.theme_combo.findData("high_contrast"))
        assert theme.is_high_contrast()
        assert w.download_btn.styleSheet() == theme.primary_button_qss(True)
        assert 'theme = "high_contrast"' in cfg.read_text(encoding="utf-8")
        w.theme_combo.setCurrentIndex(w.theme_combo.findData("light"))
        assert not theme.is_high_contrast() and not theme.is_dark()
        assert w.download_btn.styleSheet() == theme.primary_button_qss(False)
    finally:
        from conftest import dispose_window
        dispose_window(w)


def test_theme_label_translated_in_all_languages():
    import i18n
    for lang in ("zh_TW", "en", "ja"):
        assert i18n.TR[lang]["th_hc"]
