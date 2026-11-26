"""Shareable song lists: format, matching, GUI import/export, CLI."""

import json

import pytest
from PySide6.QtWidgets import QFileDialog, QMessageBox
from PySide6.QtGui import QGuiApplication

import core
import songlist
from test_cli import app, make_db              # noqa: F401  (fixture re-export)
from test_gui import window                    # noqa: F401  (fixture re-export)


def song(name, cat="01 Pop"):
    return {"song_name": name, "category": cat,
            "files": [{"file_path": f"{cat}/{name}/{name}.tja", "filename": "x.tja"}]}


DB = [song("Alpha"), song("Ｂeta Song", "02 Anime"), song("Gamma", "02 Anime"),
      song("Gamma", "01 Pop"), song("千本桜", "03 Vocaloid")]


def test_json_roundtrip():
    entries = [("01 Pop", "Alpha"), ("03 Vocaloid", "千本桜")]
    doc = json.loads(songlist.to_json(entries, "my set"))
    assert doc["format"] == "esemanager-songlist" and doc["version"] == 1
    assert doc["name"] == "my set" and doc["created"]
    assert songlist.parse(songlist.to_json(entries, "my set")) == (entries, "my set")


def test_text_format_and_comments():
    entries = [("01 Pop", "Alpha"), ("02 Anime", "A/B")]
    assert songlist.to_text(entries) == "01 Pop/Alpha\n02 Anime/A/B\n"
    got, name = songlist.parse("# my list\n\n01 Pop/Alpha\r\n  Gamma \n02 Anime/A/B\n")
    assert got == [("01 Pop", "Alpha"), ("", "Gamma"), ("02 Anime", "A/B")] and name == ""


def test_parse_rejects_foreign_json():
    with pytest.raises(ValueError):
        songlist.parse('{"hello": 1}')
    with pytest.raises(ValueError):
        songlist.parse('{broken')
    assert songlist.parse("") == ([], "")


def test_match_exact_normalised_fuzzy_missing():
    sug = {"Alhpa": ["Alpha"], "zzz": []}
    res = songlist.match(
        [("01 Pop", "Alpha"),               # exact
         ("Anime", "Beta Song"),            # normalised (full-width B), category w/o number
         ("02 Anime", "Gamma"),             # right category wins among duplicates
         ("", "Alhpa"),                     # fuzzy
         ("", "zzz")],                      # missing
        DB, suggest=lambda k, n=3: sug.get(k, []))
    assert [(s["song_name"], s["category"]) for s in res.matched] == [
        ("Alpha", "01 Pop"), ("Ｂeta Song", "02 Anime"), ("Gamma", "02 Anime")]
    assert [(lab, s["song_name"]) for lab, s in res.fuzzy] == [("Alhpa", "Alpha")]
    assert res.missing == ["zzz"]
    assert len(res.songs) == 3          # fuzzy Alpha duplicates the exact one
    text = songlist.report(res, lambda k, **kw: f"{k}{kw}")
    assert "Alhpa" in text and "zzz" in text


def test_gui_import_checks_rows_and_reports(window, tmp_path, monkeypatch):
    window.all_songs = DB
    window.apply_filters()
    p = tmp_path / "l.json"
    p.write_text(songlist.to_json([("02 Anime", "Gamma"), ("01 Pop", "Alpha"),
                                   ("", "nothing at all xyz")]), encoding="utf-8")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(p), ""))
    shown = []
    monkeypatch.setattr(window, "toast", lambda text, kind="info", **k: shown.append(text))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: 1 / 0)
    window.act_sl_import.trigger()
    assert window.song_model.checked == {("Gamma", "02 Anime"), ("Alpha", "01 Pop")}
    assert "nothing at all xyz" in shown[0]


def test_gui_paste_and_copy_export(window, tmp_path, monkeypatch):
    window.all_songs = DB
    window.apply_filters()
    QGuiApplication.clipboard().setText("01 Pop/Alpha\n")
    window.act_sl_paste.trigger()
    assert window.song_model.checked == {("Alpha", "01 Pop")}
    window.act_sl_copy.trigger()
    assert QGuiApplication.clipboard().text() == "01 Pop/Alpha\n"
    for name, check in (("o.json", lambda t: json.loads(t)["songs"] ==
                         [{"category": "01 Pop", "song": "Alpha"}]),
                        ("o.txt", lambda t: t == "01 Pop/Alpha\n")):
        out = tmp_path / name
        monkeypatch.setattr(QFileDialog, "getSaveFileName",
                            lambda *a, _o=out, **k: (str(_o), ""))
        window.act_sl_export.trigger()
        assert check(out.read_text(encoding="utf-8"))


def test_gui_export_nothing_and_favourites(window, tmp_path, monkeypatch):
    window.all_songs = DB
    window.apply_filters()
    msgs = []
    monkeypatch.setattr(window, "toast", lambda text, kind="info", **k: msgs.append(text))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: 1 / 0)
    window.act_sl_copy.trigger()
    assert msgs == [window.tr("sl_nothing")]
    monkeypatch.setattr(core, "FAVOURITES_FILE", str(tmp_path / "f.json"))
    window.toggle_favourite(DB[2])
    window.act_sl_copy.trigger()
    assert QGuiApplication.clipboard().text() == "02 Anime/Gamma\n"


def test_gui_import_bad_text(window, monkeypatch):
    msgs = []
    monkeypatch.setattr(window, "toast", lambda text, kind="info", **k: msgs.append(text))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: 1 / 0)
    QGuiApplication.clipboard().setText('{"x": 1}')
    window.act_sl_paste.trigger()
    assert msgs == [window.tr("sl_bad")]


def test_cli_export_and_from_list(app):
    tmp, run = app
    make_db(tmp / "ese_songs.db")
    rc, out = run("export")
    assert rc == 2 and "--favourites" in out
    rc, out = run("export", "-c", "Pop")
    assert rc == 0
    assert json.loads(out)["songs"] == [{"category": "01 Pop", "song": "Song"}]
    f = tmp / "l.txt"
    rc, out = run("export", "Song", "-o", str(f))
    assert rc == 0 and f.read_text(encoding="utf-8") == "01 Pop/Song\n"
    rc, out = run("export", "Song", "--text")
    assert rc == 0 and out.strip() == "01 Pop/Song"
    g = tmp / "bad.txt"
    g.write_text("Nope Nope Nope\n", encoding="utf-8")
    rc, out = run("download", "--from-list", str(g))
    assert rc == 2 and "1 not found" in out
    rc, out = run("download", "--from-list", str(tmp / "missing.json"))
    assert rc == 2
