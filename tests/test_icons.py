"""Icons load, tint per theme, and no button/action text starts with an emoji."""

import os
import re

import pytest
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QAbstractButton

import icons
import theme
from test_gui import window  # noqa: F401  (fixture: offscreen MainWindow)

# Emoji and pictographic symbols (also arrows/geometric shapes some fonts lack).
EMOJI = re.compile(r"^[\s←-⯿✀-➿\U0001F000-\U0001FFFF️]")


def test_every_icon_file_exists_and_loads(qapp):
    svgs = {f[:-4] for f in os.listdir(icons.icon_dir()) if f.endswith(".svg")}
    assert svgs == set(icons.NAMES)
    for name in icons.NAMES:
        for dark in (False, True):
            ic = icons.icon(name, dark)
            assert not ic.isNull()
            img = ic.pixmap(24, 24).toImage()
            assert any(img.pixelColor(x, y).alpha() > 0
                       for x in range(img.width()) for y in range(img.height())), name


def test_icon_tint_follows_theme(qapp):
    def centre(dark):
        img = icons.icon("stop", dark).pixmap(24, 24).toImage()
        return img.pixelColor(12, 12).name().upper()
    assert centre(False) == theme.colours(False)["button_text"].upper()
    assert centre(True) == theme.colours(True)["button_text"].upper()


def test_no_emoji_in_translations():
    from i18n import TR
    bad = re.compile(r"[⬇✉⌨⏩-⏿▶\U0001F000-\U0001FFFF]")
    for lang, d in TR.items():
        for key, val in d.items():
            if isinstance(val, str):
                assert not bad.search(val), (lang, key)


@pytest.mark.parametrize("lang", ["zh_TW", "en", "ja"])
def test_no_button_or_action_text_starts_with_emoji(window, lang):  # noqa: F811
    window.lang = lang
    window.build_ui()
    window.update_filter_button()
    window.set_monitor_open(True)
    for b in window.findChildren(QAbstractButton):
        assert not EMOJI.match(b.text() or "x"), (lang, b.text())
    for a in window.findChildren(QAction):
        assert not EMOJI.match(a.text() or "x"), (lang, a.text())
    assert not window.download_btn.icon().isNull()
    assert not window.pause_btn.icon().isNull()
