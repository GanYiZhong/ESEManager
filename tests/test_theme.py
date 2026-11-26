import pytest
from PySide6.QtGui import QColor, QPalette

import theme  # src/ is on sys.path via conftest.py


def _lum(c):
    def ch(v):
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(c.redF()) + 0.7152 * ch(c.greenF()) + 0.0722 * ch(c.blueF())


def _contrast(a, b):
    la, lb = _lum(QColor(a)), _lum(QColor(b))
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


@pytest.fixture(autouse=True)
def _restore_theme(qapp):
    yield
    # Re-applying the app-wide style sheet restyles every live widget, which is
    # slow; only do it when a test actually left a non-light theme behind.
    if theme._state["mode"] != "light" or theme.is_dark():
        theme.apply_theme(qapp, "light")
    theme._listeners.clear()


def _active(qapp, role):
    return qapp.palette().color(QPalette.Active, role)


@pytest.mark.parametrize("mode", ["light", "dark", "auto"])
def test_apply_each_mode(qapp, mode, monkeypatch):
    monkeypatch.setattr(theme, "os_is_dark", lambda: False)
    dark = theme.apply_theme(qapp, mode)
    assert dark is (mode == "dark")
    # With the app style sheet installed style().name() is empty; the theme
    # module records that Fusion was selected.
    assert theme._state["fusion"] is True
    assert qapp.palette().color(QPalette.Window).isValid()


def test_unknown_mode_falls_back_to_auto(qapp, monkeypatch):
    monkeypatch.setattr(theme, "os_is_dark", lambda: True)
    assert theme.apply_theme(qapp, "bogus") is True
    assert theme.current_mode() == "auto"


def test_light_and_dark_palettes_differ(qapp):
    light = theme.build_palette(False)
    dark = theme.build_palette(True)
    assert light.color(QPalette.Window) != dark.color(QPalette.Window)
    assert light.color(QPalette.Text) != dark.color(QPalette.Text)
    assert light.color(QPalette.Base) != dark.color(QPalette.Base)
    assert QColor(light.color(QPalette.Window)).lightness() > 128
    assert QColor(dark.color(QPalette.Window)).lightness() < 128


@pytest.mark.parametrize("dark", [False, True])
@pytest.mark.parametrize("fg,bg,minimum", [
    ("text", "base", 4.5),
    ("alt_text", "alt_base", 4.5),
    ("window_text", "window", 4.5),
    ("button_text", "button", 4.5),
    ("highlight_text", "highlight", 4.5),
    ("tooltip_text", "tooltip_base", 4.5),
    ("link", "base", 4.5),
    ("disabled_text", "window", 3.0),
])
def test_text_contrast(qapp, dark, fg, bg, minimum):
    p = theme.build_palette(dark)
    roles = {"text": QPalette.Text, "alt_text": QPalette.Text,
             "window_text": QPalette.WindowText, "button_text": QPalette.ButtonText,
             "highlight_text": QPalette.HighlightedText,
             "tooltip_text": QPalette.ToolTipText, "link": QPalette.Link,
             "disabled_text": QPalette.Text}
    bgroles = {"base": QPalette.Base, "alt_base": QPalette.AlternateBase,
               "window": QPalette.Window, "button": QPalette.Button,
               "highlight": QPalette.Highlight, "tooltip_base": QPalette.ToolTipBase}
    if fg == "disabled_text":
        fgc = p.color(QPalette.Disabled, QPalette.Text)
    elif fg == "alt_text":
        fgc = p.color(QPalette.Text)
    else:
        fgc = p.color(roles[fg])
    bgc = p.color(bgroles[bg])
    ratio = _contrast(fgc, bgc)
    assert ratio >= minimum, f"{fg} on {bg} ({'dark' if dark else 'light'}): {ratio:.2f}"


def test_auto_follows_os_scheme_changes(qapp, monkeypatch):
    state = {"dark": False}
    monkeypatch.setattr(theme, "os_is_dark", lambda: state["dark"])
    theme.apply_theme(qapp, "auto")
    assert theme.is_dark() is False
    state["dark"] = True
    theme._on_os_scheme_changed()          # what colorSchemeChanged triggers
    assert theme.is_dark() is True
    assert qapp.palette().color(QPalette.Window) == theme.build_palette(True).color(QPalette.Window)
    state["dark"] = False
    theme._on_os_scheme_changed()
    assert theme.is_dark() is False


def test_explicit_mode_ignores_os(qapp, monkeypatch):
    monkeypatch.setattr(theme, "os_is_dark", lambda: True)
    assert theme.apply_theme(qapp, "light") is False
    monkeypatch.setattr(theme, "os_is_dark", lambda: False)
    theme._on_os_scheme_changed()          # explicit mode must not follow the OS
    assert theme.is_dark() is False


def test_listeners_receive_mode_and_are_weak(qapp):
    seen = []

    class Owner:
        def on_theme(self, dark):
            seen.append(dark)

    owner = Owner()
    theme.add_listener(owner.on_theme)
    theme.apply_theme(qapp, "dark")
    assert seen[-1] is True
    theme.apply_theme(qapp, "light")
    assert seen[-1] is False
    del owner
    import gc
    gc.collect()
    n = len(seen)
    theme.apply_theme(qapp, "dark")
    assert len(seen) == n  # dead owner is not called


def test_theme_combo_applies_immediately_and_saves(qapp, tmp_path, monkeypatch):
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
    w = ese_qt.MainWindow()
    try:
        assert w.theme_pref == "auto"
        w.theme_combo.setCurrentIndex(w.theme_combo.findData("dark"))
        assert theme.is_dark() is True
        assert qapp.palette().color(QPalette.Window) == theme.build_palette(True).color(QPalette.Window)
        assert w.download_btn.styleSheet() == theme.primary_button_qss(True)
        assert 'theme = "dark"' in cfg.read_text(encoding="utf-8")
    finally:
        from conftest import dispose_window
        dispose_window(w)


def test_helpers_differ_per_mode_and_are_readable():
    assert theme.primary_button_qss(False) != theme.primary_button_qss(True)
    assert theme.hint_qss(False) != theme.hint_qss(True)
    assert theme.muted_label_qss(False) != theme.muted_label_qss(True)
    for dark in (False, True):
        t = theme.colours(dark)
        assert _contrast(t["accent_text"], t["accent"]) >= 4.5
        assert _contrast(t["hint_fg"], t["hint_bg"]) >= 4.5
        assert _contrast(t["muted"], t["window"]) >= 4.5
        assert "font-size:11px" in theme.muted_label_qss(dark, font_px=11)
    assert "#43A047" not in theme.primary_button_qss(False)  # old hard-coded green is gone


@pytest.mark.parametrize("dark", [False, True])
def test_category_colours_meet_wcag_aa(dark):
    from i18n import CATEGORY_COLORS
    t = theme.colours(dark)
    for hex_colour in CATEGORY_COLORS.values():
        c = theme.category_colour(hex_colour, dark)
        for bg in (t["base"], t["alt_base"]):
            assert theme.contrast_ratio(c, bg) >= 4.5, (hex_colour, dark, bg)


@pytest.mark.parametrize("dark", [False, True])
def test_app_qss_and_selection_contrast(dark):
    t = theme.colours(dark)
    assert "QProgressBar" in theme.app_qss(dark)
    assert theme.contrast_ratio(t["highlight_text"], t["highlight"]) >= 4.5
    assert theme.contrast_ratio(t["text"], t["progress_chunk"]) >= 4.5
    assert theme.contrast_ratio(t["text"], t["progress_track"]) >= 4.5


def test_apply_theme_installs_stylesheet(qapp):
    theme.apply_theme(qapp, "dark")
    assert "QHeaderView::section" in qapp.styleSheet()


def test_no_hardcoded_hex_colours_outside_theme():
    import re
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "src"
    for name in ("ese_qt.py", "detail_panel.py", "models.py"):
        text = (src / name).read_text(encoding="utf-8")
        assert not re.search(r"#[0-9A-Fa-f]{6}\b|#[0-9A-Fa-f]{3}\b", text), name
