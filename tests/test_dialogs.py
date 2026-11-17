"""Offscreen checks for the polished tool dialogs (box.def editor, Yatai, Dan tools)."""

import json

import pytest
from PySide6.QtWidgets import QMessageBox

import appconfig
import dialogs
from dialogs import BoxDefDialog, DanToolsDialog, YataiBoxDefDialog


def tr(k, **kw):
    return k


@pytest.fixture
def app_dir(tmp_path, monkeypatch):
    # Keep dialogs.json and any box.def writes inside a temp folder.
    monkeypatch.setattr(appconfig, "APP_DIR", str(tmp_path))
    return tmp_path


def test_all_dialogs_construct(qapp, app_dir):
    BoxDefDialog(None, str(app_dir), tr).close()
    YataiBoxDefDialog(None, tr).close()
    DanToolsDialog(None, tr, str(app_dir)).close()


@pytest.mark.parametrize("text, ok", [
    ("", True),
    ("AABBCC", True),
    ("aabbcc", True),
    ("#AABBCC", True),
    ("#aabbcc", True),
    ("GG0000", False),
    ("#12345", False),
    ("#", False),
    ("1234567", False),
])
def test_colour_validation_accepts_hex_with_or_without_hash(text, ok):
    assert dialogs._color_ok(text) is ok


def test_colour_edit_gets_red_border_when_invalid(qapp, app_dir):
    dlg = BoxDefDialog(None, str(app_dir), tr)
    edit = dlg.color_edits["BACKCOLOR"]
    edit.setText("ZZZZZZ")
    assert "#E53935" in edit.styleSheet()
    edit.setText("#33AA11")
    assert edit.styleSheet() == ""
    dlg.close()


def test_boxdef_dirty_flag_follows_edits_load_and_save(qapp, app_dir, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    dlg = BoxDefDialog(None, str(app_dir), tr)
    assert not dlg._dirty
    dlg.title_edits[""].setText("Hello")
    assert dlg._dirty and dlg.windowTitle().endswith("*")
    # Saving clears the flag and writes the file.
    dlg.save()
    assert not dlg._dirty
    assert "#TITLE:Hello" in (app_dir / "box.def").read_text(encoding="utf-8")
    # Loading again while clean does not ask anything.
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: pytest.fail("unexpected prompt"))
    dlg.load()
    assert not dlg._dirty
    dlg.close()


def test_boxdef_load_asks_before_discarding_edits(qapp, app_dir, monkeypatch):
    asked = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: asked.append(a[2]) or QMessageBox.No)
    dlg = BoxDefDialog(None, str(app_dir), tr)
    dlg.title_edits[""].setText("Edited")
    dlg.load()
    assert asked == ["dlg_boxdef_unsaved"]
    assert dlg.title_edits[""].text() == "Edited"   # user said No, nothing reloaded
    dlg.close()


def test_yatai_overwrite_needs_confirmation_and_no_keeps_files(qapp, app_dir, monkeypatch):
    sub = app_dir / "01_pop"
    sub.mkdir()
    (sub / "box.def").write_text("#TITLE:orig\n", encoding="utf-8")
    asked = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: asked.append(a[2]) or QMessageBox.No)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    dlg = YataiBoxDefDialog(None, tr, str(app_dir))
    dlg.generate_all()
    assert asked == ["dlg_yatai_overwrite_q"]
    assert (sub / "box.def").read_text(encoding="utf-8") == "#TITLE:orig\n"
    dlg.close()


def test_dan_prefs_round_trip_and_corrupt_file_ignored(qapp, app_dir):
    (app_dir / "dialogs.json").write_text("{not json", encoding="utf-8")
    dlg = DanToolsDialog(None, tr, str(app_dir))   # corrupt file must not break startup
    dlg.gen_out.setText(str(app_dir / "out"))
    dlg._save_prefs()
    data = json.loads((app_dir / "dialogs.json").read_text(encoding="utf-8"))
    assert data["dan_tools"]["gen_out"] == str(app_dir / "out")
    dlg.close()

    again = DanToolsDialog(None, tr, str(app_dir))
    assert again.gen_out.text() == str(app_dir / "out")
    again.close()


def test_dan_busy_locks_inputs_and_shows_progress(qapp, app_dir):
    dlg = DanToolsDialog(None, tr, str(app_dir))
    dlg._busy(True)
    assert not dlg.tabs.widget(0).isEnabled()
    assert not dlg.progress.isHidden()
    assert dlg.progress.maximum() == 0 and dlg.progress.minimum() == 0   # indeterminate
    dlg._busy(False)
    assert dlg.tabs.widget(0).isEnabled()
    dlg.close()


def test_dan_missing_folder_is_reported_before_start(qapp, app_dir, monkeypatch):
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warnings.append(a[2]))
    dlg = DanToolsDialog(None, tr, str(app_dir))
    dlg.gen_url.setText("https://example.invalid/dan")
    dlg.gen_out.setText(str(app_dir / "out"))
    dlg.gen_songs.setText(str(app_dir / "no_such_songs"))
    dlg.run_gen()
    assert warnings == ["dlg_dan_missing"]
    assert dlg._thread is None   # nothing was started
    dlg.close()
