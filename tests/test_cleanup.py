"""Download-folder cleanup: analyze_library, safety rules, GUI dialog, CLI."""
import os
import sys
import time

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

import core
import dialogs
from test_columns import make_window  # noqa: F401  (fixture)
from test_workers import make_song_db

DAY = 86400


@pytest.fixture
def lib(tmp_path):
    """Download tree + DB listing 01 Pop/Song/{Song.tja,Song.ogg}."""
    db = tmp_path / "ese_songs.db"
    make_song_db(str(db), [("01 Pop/Song/Song.tja", "a" * 40),
                           ("01 Pop/Song/Song.ogg", "b" * 40)])
    dl = tmp_path / "dl"

    def put(rel, data=b"x", age=0):
        p = dl / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        if age:
            t = time.time() - age
            os.utime(p, (t, t))
        return p

    put("01 Pop/Song/Song.tja", b"1234")
    put("01 Pop/Song/Song.ogg", b"12345678")
    put("01 Pop/box.def", b"box")                       # expected
    put("01 Pop/Song/Song.tja.part", b"pp", age=2 * DAY)    # stale part
    put("01 Pop/Song/Song.ogg.part", b"p", age=60)          # fresh part
    put("01 Pop/Song/notes.txt", b"hello")                  # stray
    put("01 Pop/Gone/Gone.tja", b"gonegone")                # orphan folder
    (dl / "01 Pop" / "Empty").mkdir()
    (dl / "01 Pop" / "Song" / "Sub" / "Deeper").mkdir(parents=True)  # empty chain
    # never listed: outside known categories / protected
    put("Random Folder/a.txt")
    put("ESE-Version-Sorting/list.txt")
    put("config/x.json")
    put("ese_songs.db", b"db")
    put(".ese_sha_cache.json", b"{}")
    return dl, db, put


def rels(items):
    return sorted(i["rel"].replace("\\", "/").lower() for i in items)


def test_analyze_finds_each_group(lib):
    dl, db, _ = lib
    r = core.analyze_library(str(dl), db_path=str(db))
    assert rels(r["orphans"]) == ["01 pop/gone"]
    assert r["orphans"][0]["size"] == 8
    assert rels(r["strays"]) == ["01 pop/song/notes.txt"]
    assert rels(r["parts"]) == ["01 pop/song/song.ogg.part", "01 pop/song/song.tja.part"]
    assert rels(r["empty"]) == ["01 pop/empty", "01 pop/song/sub"]   # topmost only
    ages = {os.path.basename(p["path"]): p["age"] for p in r["parts"]}
    assert ages["Song.tja.part"] > DAY and ages["Song.ogg.part"] < DAY
    assert set(r["categories"]) == {"01 Pop"}
    assert r["categories"]["01 Pop"]["size"] > 0


def test_nothing_outside_categories_and_box_def_expected(lib):
    dl, db, _ = lib
    r = core.analyze_library(str(dl), db_path=str(db))
    everything = r["orphans"] + r["strays"] + r["parts"] + r["empty"]
    for it in everything:
        assert it["rel"].replace("\\", "/").lower().startswith("01 pop/")
    assert not any("box.def" in i["rel"].lower() for i in everything)


def test_protected_name_never_scanned_even_if_db_category(tmp_path):
    db = tmp_path / "ese_songs.db"
    make_song_db(str(db), [("ESE-Version-Sorting/Song/a.tja", "a" * 40)])
    dl = tmp_path / "dl"
    (dl / "ESE-Version-Sorting" / "Junk").mkdir(parents=True)
    (dl / "ESE-Version-Sorting" / "Junk" / "j.txt").write_text("x")
    r = core.analyze_library(str(dl), db_path=str(db))
    assert r["orphans"] == [] and r["categories"] == {}
    assert not core.cleanup_safe(str(dl), str(dl / "ESE-Version-Sorting" / "Junk"), str(db))


def test_no_db_returns_none(tmp_path):
    assert core.analyze_library(str(tmp_path), db_path=str(tmp_path / "nope.db")) is None


def test_default_selection_only_stale_parts(lib):
    dl, db, _ = lib
    r = core.analyze_library(str(dl), db_path=str(db))
    sel = [i for k in ("orphans", "strays", "parts", "empty") for i in r[k]
           if core.cleanup_default_selection(i)]
    assert [os.path.basename(i["path"]) for i in sel] == ["Song.tja.part"]


def test_apply_refuses_unsafe_paths_and_uses_mover(lib):
    dl, db, _ = lib
    moved = []
    items = [{"path": str(dl / "Random Folder" / "a.txt")},
             {"path": str(dl / "config" / "x.json")},
             {"path": str(dl / "01 Pop")},                       # category folder itself
             {"path": str(dl.parent / "ese_songs.db")},          # outside the tree
             {"path": str(dl / "01 Pop" / "Song" / "notes.txt")}]
    done, failed = core.cleanup_apply(str(dl), items, lambda p: moved.append(p) or True,
                                      db_path=str(db))
    assert [os.path.basename(i["path"]) for i in done] == ["notes.txt"]
    assert len(failed) == 4 and len(moved) == 1
    assert (dl / "Random Folder" / "a.txt").exists()


def test_apply_reports_mover_failure(lib):
    dl, db, _ = lib
    it = {"path": str(dl / "01 Pop" / "Song" / "notes.txt")}
    done, failed = core.cleanup_apply(str(dl), [it], lambda p: False, db_path=str(db))
    assert failed == [it] and not done
    assert os.path.exists(it["path"])


# ------------------------------------------------------------------ GUI
@pytest.fixture
def gui(make_window, lib, tmp_path, monkeypatch):
    dl, db, _ = lib
    monkeypatch.setattr(core, "DB_PATH", str(db))
    w = make_window()
    w.dir_edit.setText(str(dl))
    return w, dl


def test_menu_dialog_defaults_and_trash(gui, monkeypatch):
    w, dl = gui
    seen = {}

    def fake_exec(self):
        seen["checked"] = [i["path"] for i in self.selected_items()]
        return 1
    monkeypatch.setattr(dialogs.CleanupDialog, "exec", fake_exec)
    trashed = []
    monkeypatch.setattr("ese_qt.QFile.moveToTrash", staticmethod(lambda p: trashed.append(p) or True))
    w.act_cleanup.trigger()
    assert [os.path.basename(p) for p in seen["checked"]] == ["Song.tja.part"]
    assert [os.path.basename(p) for p in trashed] == ["Song.tja.part"]


def test_trash_failure_asks_before_permanent_delete(gui, monkeypatch):
    w, dl = gui
    monkeypatch.setattr(dialogs.CleanupDialog, "exec", lambda self: 1)
    monkeypatch.setattr("ese_qt.QFile.moveToTrash", staticmethod(lambda p: False))
    asked = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: asked.append(1) or QMessageBox.No)
    w.act_cleanup.trigger()
    part = dl / "01 Pop" / "Song" / "Song.tja.part"
    assert asked and part.exists()                     # declined: still there
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    w.act_cleanup.trigger()
    assert not part.exists()


def test_dialog_groups_checkboxes(gui):
    w, dl = gui
    r = core.analyze_library(str(dl))
    d = dialogs.CleanupDialog(w, w.tr, r)
    assert d.tree.topLevelItemCount() == 4
    assert len(d.selected_items()) == 1
    top = d.tree.topLevelItem(0)
    top.setCheckState(0, Qt.Checked)                    # tick a whole group
    assert len(d.selected_items()) > 1


# ------------------------------------------------------------------ CLI
def test_cli_dry_run_main_in_process(lib, tmp_path, monkeypatch, capsys):
    import cli
    dl, db, _ = lib
    monkeypatch.setattr(core, "DB_PATH", str(db))
    cli.out.json = False
    cli.out.quiet = False
    tr = cli.make_tr("en")
    args = cli.build_parser().parse_args(["cleanup", "--dry-run"])
    args.dir = str(dl)
    assert cli.cmd_cleanup(args, tr) == 0
    text = capsys.readouterr().out
    assert "Gone" in text and "notes.txt" in text and "Song.tja.part" in text
    assert (dl / "01 Pop" / "Gone").exists()

    # --yes without a kind refuses
    args = cli.build_parser().parse_args(["cleanup", "--yes"])
    args.dir = str(dl)
    assert cli.cmd_cleanup(args, tr) == 2

    # --yes --part-files-only: only the stale part goes to the (mocked) trash
    trashed = []
    monkeypatch.setattr(core, "move_to_trash", lambda p: trashed.append(p) or True)
    args = cli.build_parser().parse_args(["cleanup", "--yes", "--part-files-only"])
    args.dir = str(dl)
    assert cli.cmd_cleanup(args, tr) == 0
    assert [os.path.basename(p) for p in trashed] == ["Song.tja.part"]

    # --permanent really deletes
    args = cli.build_parser().parse_args(["cleanup", "--yes", "--strays", "--permanent"])
    args.dir = str(dl)
    assert cli.cmd_cleanup(args, tr) == 0
    assert not (dl / "01 Pop" / "Song" / "notes.txt").exists()
    assert (dl / "01 Pop" / "Gone").exists()
