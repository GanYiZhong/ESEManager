"""UI font stacks: Latin face first, CJK face of the UI language next; Japanese
titles get a Japanese font."""

from PySide6.QtCore import Qt

import fonts
from models import SongModel


def test_stacks_only_list_installed_fonts(qapp, monkeypatch):
    monkeypatch.setattr(fonts.QFontDatabase, "families",
                        staticmethod(lambda *a: ["Segoe UI", "Microsoft JhengHei UI",
                                                 "Yu Gothic UI", "Arial"]))
    assert fonts.ui_families("zh_TW") == ["Segoe UI", "Arial", "Microsoft JhengHei UI",
                                          "Yu Gothic UI"]
    assert fonts.ui_families("ja")[2] == "Yu Gothic UI"
    assert fonts.japanese_families()[2] == "Yu Gothic UI"


def test_no_known_fonts_keeps_qt_default(qapp, monkeypatch):
    monkeypatch.setattr(fonts.QFontDatabase, "families", staticmethod(lambda *a: []))
    f = fonts.ui_font("en", 9)
    assert f.pointSizeF() == 9


def test_japanese_column_uses_japanese_font(qapp):
    m = SongModel(lambda k, **kw: k, {})
    m.set_songs([{"song_name": "a", "category": "01 Pop", "files": []}])
    m.jp_font = fonts.japanese_font(qapp.font())
    assert m.data(m.index(0, 2), Qt.FontRole) is m.jp_font
    assert m.data(m.index(0, 1), Qt.FontRole) is None
