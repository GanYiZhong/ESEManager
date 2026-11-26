"""What's new in the song library: DB diff, persistence, GUI marker/filter, CLI."""

import json
import os
import sqlite3
import sys
import time

import pytest
from PySide6.QtWidgets import QMessageBox

import core
from ese_scraper_git_v2 import ESEScraperGitV2

sys.path.insert(0, os.path.dirname(__file__))
from test_cli import app as cli_app  # noqa: E402,F401  (fixture)
from test_gui import window  # noqa: E402,F401  (fixture)


def make_db(path, songs):
    """songs: {(category, name): {file_path: sha}}"""
    s = ESEScraperGitV2(db_path=str(path), clone_dir="unused", git_exe="git")
    s.init_database()
    s.close()
    conn = sqlite3.connect(str(path))
    cats, sid = {}, 0
    for (cat, name), files in songs.items():
        if cat not in cats:
            cats[cat] = len(cats) + 1
            conn.execute("INSERT INTO categories(id, name, path) VALUES (?, ?, ?)",
                         (cats[cat], cat, cat))
        sid += 1
        conn.execute("INSERT INTO songs(id, category_id, song_name, base_path) VALUES (?,?,?,?)",
                     (sid, cats[cat], name, f"{cat}/{name}"))
        for fp, sha in files.items():
            conn.execute("INSERT INTO song_files(song_id, filename, file_path, file_type, size, "
                         "download_url, blob_sha) VALUES (?,?,?,?,0,'',?)",
                         (sid, fp.split("/")[-1], fp, os.path.splitext(fp)[1], sha))
    conn.commit()
    conn.close()


def song(cat, name, sha="a", extra=None):
    f = {f"{cat}/{name}/{name}.tja": sha * 40}
    f.update(extra or {})
    return (cat, name), f


OLD = dict([song("01 Pop", "Keep"), song("01 Pop", "Edit"), song("02 Anime", "Same")])
NEW = dict([song("01 Pop", "Keep"),
            song("01 Pop", "Edit", sha="b"),                 # sha changed
            song("02 Anime", "Same", extra={"02 Anime/Same/x.ogg": "c" * 40}),  # file added
            song("02 Anime", "Fresh"),                       # new song
            song("01 Pop", "Same")])                         # same name, other category -> new


def test_diff_song_sets(tmp_path):
    make_db(tmp_path / "old.db", OLD)
    make_db(tmp_path / "new.db", NEW)
    d = core.diff_song_sets(str(tmp_path / "old.db"), str(tmp_path / "new.db"))
    assert d["added"] == [["01 Pop", "Same"], ["02 Anime", "Fresh"]]
    assert d["changed"] == [["01 Pop", "Edit"], ["02 Anime", "Same"]]
    d = core.diff_song_sets(str(tmp_path / "old.db"), str(tmp_path / "old.db"))
    assert d == {"added": [], "changed": []}


def test_diff_is_fast_on_realistic_size(tmp_path):
    big_old = dict(song("01 Pop", f"S{i}", extra={f"01 Pop/S{i}/S{i}.ogg": "d" * 40})
                   for i in range(3200))
    big_new = dict(big_old)
    for i in range(0, 3200, 40):
        big_new[("01 Pop", f"S{i}")] = {f"01 Pop/S{i}/S{i}.tja": "e" * 40}
    big_new.update(dict(song("01 Pop", f"N{i}") for i in range(12)))
    make_db(tmp_path / "o.db", big_old)
    make_db(tmp_path / "n.db", big_new)
    t = time.perf_counter()
    d = core.diff_song_sets(str(tmp_path / "o.db"), str(tmp_path / "n.db"))
    dt = time.perf_counter() - t
    print(f"diff of 3200 songs: {dt * 1000:.0f} ms")
    assert len(d["added"]) == 12 and len(d["changed"]) == 80
    assert dt < 2


def test_persistence_roundtrip_and_damage(tmp_path, monkeypatch):
    f = tmp_path / "new_songs.json"
    monkeypatch.setattr(core, "NEW_SONGS_FILE", str(f))
    assert core.load_new_songs()["added"] == [] and core.new_song_marks() == {}
    core.save_new_songs({"added": [["01 Pop", "A"]], "changed": [["02 Anime", "B"]]}, "v9")
    d = core.load_new_songs()
    assert d["version"] == "v9" and d["time"] and d["added"] == [("01 Pop", "A")]
    assert core.new_song_marks() == {("A", "01 Pop"): "new", ("B", "02 Anime"): "updated"}
    assert not os.path.exists(str(f) + ".part")
    f.write_text("{not json")
    assert core.load_new_songs()["changed"] == []
    assert "new_songs.json" in core.UPDATE_KEEP_FILES


def test_update_databases_records_diff(tmp_path, monkeypatch):
    """update_databases diffs the old DB against the downloaded one before the swap."""
    import hashlib
    app = tmp_path / "app"
    www = tmp_path / "www"
    app.mkdir()
    www.mkdir()
    make_db(app / "ese_songs.db", OLD)
    make_db(www / "ese_songs.db", NEW)
    make_db(www / "ese_local.db", {})
    monkeypatch.setattr(core, "DB_PATH", str(app / "ese_songs.db"))
    monkeypatch.setattr(core, "VERSION_FILE", str(app / "version.txt"))
    monkeypatch.setattr(core, "NEW_SONGS_FILE", str(app / "new_songs.json"))
    manifest = {"version": "v2", "files": {
        n: {"sha256": hashlib.sha256((www / n).read_bytes()).hexdigest()}
        for n in core.DB_NAMES}}

    class R:
        def json(self):
            return manifest

    def fake_dl(sess, name, want, part, tr):
        with open(part, "wb") as f:
            f.write((www / name).read_bytes())

    monkeypatch.setattr(core, "get_with_retry", lambda *a, **k: R())
    monkeypatch.setattr(core, "_download_db_plain", fake_dl)
    assert core.update_databases("v2") == "v2"
    d = core.load_new_songs()
    assert len(d["added"]) == 2 and len(d["changed"]) == 2 and d["version"] == "v2"


def test_gui_marker_filter_and_show_button(window, monkeypatch):
    songs = [{"song_name": n, "category": "01 Pop", "files": []} for n in ("a", "b", "c")]
    window.all_songs = songs
    window.song_model.set_new_marks({("a", "01 Pop"): "new", ("b", "01 Pop"): "updated"})
    window.song_model.set_songs(songs)
    m = window.song_model
    col = m.NEW_COL
    assert [m.data(m.index(r, col)) for r in range(3)] == ["NEW", "UPD", ""]
    assert m.data(m.index(2, col), 3) is None                      # tooltip role (Qt.ToolTipRole)
    window.new_combo.setCurrentIndex(window.new_combo.findData("new"))
    assert [s["song_name"] for s in m.songs] == ["a", "b"]
    assert window.active_filter_count() == 1
    window.reset_filters()
    assert len(m.songs) == 3
    # "Show them" selects the filter and reloads the list
    ran = []
    monkeypatch.setattr(window, "show_all", lambda: ran.append(1))
    window.show_new_songs()
    assert window.new_combo.currentData() == "new" and ran


def test_gui_db_updated_message_has_summary(window, monkeypatch, tmp_path):
    core.save_new_songs({"added": [["01 Pop", "a"]] * 1, "changed": [["01 Pop", "b"]]}, "v2")
    got = []
    monkeypatch.setattr(window, "reload_databases",
                        lambda msg=None, show_btn=False: got.append((msg, show_btn)))
    window.welcome_panel.hide()
    window.on_db_updated(True, "")
    msg, show = got[0]
    assert window.tr("sn_summary", new=1, upd=1) in msg and show
    assert window.song_model.new_marks[("a", "01 Pop")] == "new"
    # the message itself: a toast with a "Show them" action, no modal
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 1 / 0)
    ran = []
    monkeypatch.setattr(window, "show_new_songs", lambda: ran.append(1))
    window._db_done_box(msg, True)
    t = window.toasts.toasts[-1]
    assert [b.text() for b in t.action_buttons] == [window.tr("sn_show")]
    t.action_buttons[0].click()
    assert ran == [1] and t._closed


def test_cli_search_new(cli_app):
    tmp, run = cli_app
    make_db(tmp / "ese_songs.db", NEW)
    (tmp / "new_songs.json").write_text(json.dumps(
        {"time": "t", "version": "v", "added": [["02 Anime", "Fresh"]],
         "changed": [["01 Pop", "Edit"]]}), encoding="utf-8")
    rc, out = run("search", "--new")
    assert rc == 0 and "Fresh" in out and "Edit" in out and "Keep" not in out
    rc, out = run("search", "Fresh", "--new")
    assert rc == 0 and "Fresh" in out and "Edit" not in out
    rc, out = run("search", "Keep", "--new")
    assert rc == 2


def test_cli_update_db_prints_counts(monkeypatch, capsys, tmp_path):
    import cli
    monkeypatch.setattr(core, "NEW_SONGS_FILE", str(tmp_path / "n.json"))
    monkeypatch.setattr(core, "fetch_remote_version", lambda *a, **k: "v2")
    monkeypatch.setattr(core, "read_local_version", lambda: "v1")
    monkeypatch.setattr(core, "update_databases", lambda *a, **k: (
        core.save_new_songs({"added": [["c", "a"]] * 12, "changed": [["c", "b"]] * 3}), "v2")[1])
    monkeypatch.setattr(cli, "out", cli.Output())
    args = type("A", (), {"force": False})()
    assert cli.cmd_update_db(args, cli.make_tr("en")) == 0
    assert "12 new songs, 3 updated" in capsys.readouterr().out
