"""Drag and drop, command-line open-with and the .esesongs extension."""

import pytest
from PySide6.QtCore import Qt, QMimeData, QUrl, QPoint, QPointF
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QMessageBox

import ese_qt
import songlist
from test_gui import window  # noqa: F401  (fixture)


def _mime(urls=None, text=None):
    m = QMimeData()
    if urls is not None:
        m.setUrls([QUrl.fromLocalFile(str(u)) for u in urls])
    if text is not None:
        m.setText(text)
    return m


def _enter(w, mime):
    ev = QDragEnterEvent(QPoint(5, 5), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    w.dragEnterEvent(ev)
    return ev


def _drop(w, mime):
    w.dropEvent(QDropEvent(QPointF(5, 5), Qt.CopyAction, mime,
                           Qt.LeftButton, Qt.NoModifier))


def test_drop_files_and_text_import(window, tmp_path, monkeypatch):
    applied = []
    monkeypatch.setattr(window, "_apply_song_list", applied.append)
    window.all_songs = [{"song_name": "x"}]
    for name in ("a.json", "b.txt", "c.esesongs"):
        f = tmp_path / name
        f.write_text("C/X\n", encoding="utf-8")
        assert _enter(window, _mime([f])).isAccepted()
        assert not window._drop_overlay.isHidden()
        _drop(window, _mime([f]))
        assert window._drop_overlay.isHidden()
    assert len(applied) == 3
    assert _enter(window, _mime(text="C/X\nC/Y\n")).isAccepted()
    _drop(window, _mime(text="C/X\nC/Y\n"))
    assert len(applied) == 4


def test_unacceptable_drags_are_ignored(window, tmp_path):
    other = tmp_path / "pic.png"
    other.write_bytes(b"x")
    assert not _enter(window, _mime([other])).isAccepted()
    assert not _enter(window, _mime(text="hello")).isAccepted()
    assert getattr(window, "_drop_overlay", None) is None


def test_drop_folder_asks_then_sets_download_dir(window, tmp_path, monkeypatch):
    d = tmp_path / "songs"
    d.mkdir()
    asked = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: asked.append(a) or QMessageBox.No)
    _drop(window, _mime([d]))
    assert asked and window.dir_edit.text() != str(d)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    _drop(window, _mime([d]))
    assert window.dir_edit.text() == str(d)


def test_drop_folder_on_dir_field_sets_directly(window, tmp_path, monkeypatch):
    d = tmp_path / "direct"
    d.mkdir()
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: pytest.fail("must not ask"))
    mime = _mime([d])            # keep alive: the event does not own it
    window.dir_edit.dropEvent(QDropEvent(QPointF(1, 1), Qt.CopyAction, mime,
                                         Qt.LeftButton, Qt.NoModifier))
    assert window.dir_edit.text() == str(d)


def test_file_import_waits_for_songs(window, tmp_path, monkeypatch):
    f = tmp_path / "l.json"
    f.write_text("C/X\n", encoding="utf-8")
    applied = []
    monkeypatch.setattr(window, "_apply_song_list", applied.append)
    monkeypatch.setattr(ese_qt.MainWindow, "has_song_db", staticmethod(lambda: True))
    window.all_songs = []
    window.import_song_list_file(str(f))
    assert not applied and window._pending_import
    monkeypatch.setattr(window, "apply_filters", lambda: None)
    monkeypatch.setattr(window, "refresh_download_status", lambda: None)
    window._search_seq = 3
    window.on_search_done(3, [{"song_name": "X"}])
    assert applied == ["C/X\n"] and window._pending_import is None


def test_file_import_runs_at_once_when_songs_loaded(window, tmp_path, monkeypatch):
    f = tmp_path / "l.esesongs"
    f.write_text(songlist.to_json([("C", "X")]), encoding="utf-8")
    applied = []
    monkeypatch.setattr(window, "_apply_song_list", applied.append)
    window.all_songs = [{"song_name": "X"}]
    window.import_song_list_file(str(f))
    assert len(applied) == 1


def test_esesongs_round_trip(tmp_path):
    p = tmp_path / "l.esesongs"
    p.write_text(songlist.to_json([("Cat", "Song")]), encoding="utf-8")
    entries, _ = songlist.parse(p.read_text(encoding="utf-8-sig"))
    assert entries == [("Cat", "Song")]
    assert "*.esesongs" in ese_qt.TR["en"]["sl_filter"]


def test_command_line_path(tmp_path, monkeypatch):
    f = tmp_path / "l.esesongs"
    f.write_text("C/X\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert ese_qt.list_path_from_argv(["--selftest"]) is None
    assert ese_qt.list_path_from_argv(["missing.json"]) is None
    assert ese_qt.list_path_from_argv(["l.esesongs"]) == str(f)
