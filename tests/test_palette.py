"""Offscreen tests for the Ctrl+K command palette."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtTest import QTest

import command_palette as cp
import core
from test_gui import window  # noqa: F401  (fixture)

SONGS = [{"song_name": "Alpha Song", "category": "pop", "files": []},
         {"song_name": "Beta Tune", "category": "pop", "files": []}]


@pytest.fixture
def pal(window, monkeypatch):  # noqa: F811
    monkeypatch.setattr(core, "search_songs", lambda kw, cat=None: [
        s for s in SONGS if kw.lower() in s["song_name"].lower()])
    window.song_model.set_songs(list(SONGS))
    window.open_palette()
    return window._palette


def entry(p, i):
    return p.list.item(i).data(cp._ROLE_ENTRY)


def labels(p):
    return [p.list.item(i).text() for i in range(p.list.count())]


def test_registry_has_labels_and_shortcuts(pal, window):
    assert window.tr("db_update") in labels(pal)
    assert window.tr("shortcuts") in labels(pal)
    shorts = {pal.list.item(i).text(): pal.list.item(i).data(cp._ROLE_SHORT)
              for i in range(pal.list.count())}
    assert shorts[window.tr("mw_settings")] == window.act_settings.shortcut().toString(
        QKeySequence.NativeText)


@pytest.mark.parametrize("lang", ["zh_TW", "en", "ja"])
def test_alias_dl_finds_download_in_any_language(window, lang, monkeypatch):
    monkeypatch.setattr(core, "search_songs", lambda *a, **k: [])
    window.lang = lang
    window.retranslate_chrome()
    window.download_btn.setText(window.tr("download"))
    window.download_btn.setEnabled(True)
    window.open_palette()
    p = window._palette
    p.edit.setText("dl")
    assert entry(p, 0).key == "download_btn"


def test_filter_narrows_and_nonmatch_has_no_commands(pal):
    n = pal.list.count()
    pal.edit.setText("settings")
    assert 0 < pal.list.count() < n
    assert entry(pal, 0).key == "act_settings"
    pal.edit.setText("zzzqq")
    assert not any(isinstance(entry(pal, i), cp.Command) for i in range(pal.list.count()))


def test_enter_runs_command_and_tracks_recent(pal, window, monkeypatch):
    called = []
    monkeypatch.setattr(window.act_settings, "trigger", lambda: called.append(1))
    pal._cmds = cp.build_commands(window)
    pal.edit.setText("settings")
    QTest.keyClick(pal.edit, Qt.Key_Return)
    assert called == [1]
    assert not pal.isVisible()
    assert pal.recent[0] == "act_settings"
    pal.open_palette()
    assert entry(pal, 0).key == "act_settings"


def test_up_down_moves_selection(pal):
    assert pal.list.currentRow() == 0
    QTest.keyClick(pal.edit, Qt.Key_Down)
    assert pal.list.currentRow() == 1
    QTest.keyClick(pal.edit, Qt.Key_Up)
    assert pal.list.currentRow() == 0


def test_song_jump_selects_row_and_opens_detail(pal, window):
    pal.edit.setText("beta")
    rows = [i for i in range(pal.list.count()) if isinstance(entry(pal, i), dict)]
    assert [entry(pal, i)["song_name"] for i in rows] == ["Beta Tune"]
    pal.list.setCurrentRow(rows[0])
    QTest.keyClick(pal.edit, Qt.Key_Return)
    assert window.table.currentIndex().row() == 1
    assert window.detail_panel.isVisible() or window.detail_btn.isChecked()


def test_escape_closes(pal):
    pal.show()
    assert pal.isVisible()
    QTest.keyClick(pal.edit, Qt.Key_Escape)
    assert not pal.isVisible()
