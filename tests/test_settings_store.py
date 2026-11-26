"""Settings you can trust: recovery, validation, unknown keys, bundles,
reset, debounce and the CLI config commands."""

import json
import os
import tomllib
import zipfile

import pytest
from PySide6.QtWidgets import QFileDialog, QMessageBox

import appconfig
import core
import ese_qt
import settings_store as ss
import workers
from test_cli import app  # noqa: F401  (fixture: throwaway app copy + runner)


# ---------------------------------------------------------------- pure store
def test_broken_file_is_moved_aside_not_overwritten(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("[download\nworkers = ", encoding="utf-8")
    cfg, broken = ss.load_config(str(p))
    assert cfg == {} and broken and ".broken-" in broken
    assert not p.exists()
    assert open(broken, encoding="utf-8").read().startswith("[download")
    # a second breakage the same second must not clobber the first copy
    p.write_text("x = [", encoding="utf-8")
    _, broken2 = ss.load_config(str(p))
    assert broken2 != broken and os.path.exists(broken) and os.path.exists(broken2)


def test_missing_file_is_just_defaults(tmp_path):
    assert ss.load_config(str(tmp_path / "nope.toml")) == ({}, None)


def test_invalid_values_fall_back_individually():
    cfg, problems = ss.validate({
        "download": {"workers": 99, "keep_awake": "yes", "directory": "D:/songs",
                     "source": "ftp://x", "last_full_check": -1},
        "display": {"theme": "neon", "font_scale": 100, "density": 3,
                    "window_w": True, "splitter": [1], "ui_language": "ja"}})
    assert cfg["download"] == {"directory": "D:/songs"}
    assert cfg["display"] == {"font_scale": 100, "ui_language": "ja"}
    assert set(problems) == {"download.workers", "download.keep_awake", "download.source",
                             "download.last_full_check", "display.theme", "display.density",
                             "display.window_w", "display.splitter"}


def test_non_table_section_is_dropped():
    cfg, problems = ss.validate({"download": 5, "display": {"theme": "dark"}})
    assert "download" not in cfg and problems == ["download"]


def test_unknown_keys_survive_save(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('top = 1\n[download]\nworkers = 2\nfuture = "x"\n[extra]\na = 1\n',
                 encoding="utf-8")
    ss.save_known(str(p), {"download": {"workers": 5}, "display": {"theme": "dark"}})
    got = tomllib.loads(p.read_text(encoding="utf-8"))
    assert got["top"] == 1 and got["extra"] == {"a": 1}
    assert got["download"] == {"workers": 5, "future": "x"}
    assert got["display"] == {"theme": "dark"}
    assert not os.path.exists(str(p) + ".part")             # atomic temp file gone


def test_reset_config_keeps_unknown_and_optionally_directory():
    cur = {"download": {"workers": 5, "directory": "D:/s", "future": 1},
           "display": {"theme": "dark"}, "x": {"y": 1}}
    kept = ss.reset_config(cur)
    assert kept == {"download": {"directory": "D:/s", "future": 1}, "x": {"y": 1}}
    assert "directory" not in ss.reset_config(cur, keep_directory=False)["download"]


def test_parse_value():
    assert ss.parse_value("download", "workers", "4") == 4
    assert ss.parse_value("download", "keep_awake", "off") is False
    assert ss.parse_value("display", "font_scale", "115") == 115
    assert ss.parse_value("display", "categories", "a, b") == ["a", "b"]
    assert ss.parse_value("display", "splitter", "300,500") == [300, 500]
    for sec, k, v in (("download", "workers", "0"), ("display", "theme", "x"),
                      ("download", "keep_awake", "maybe"), ("display", "font_scale", "101")):
        with pytest.raises(ValueError):
            ss.parse_value(sec, k, v)


class FakeTimer:
    def __init__(self, cb):
        self.cb, self.active, self.started = cb, False, []

    def start(self, ms):
        self.active = True
        self.started.append(ms)

    def stop(self):
        self.active = False

    def isActive(self):
        return self.active

    def fire(self):
        if self.active:
            self.active = False
            self.cb()


def test_debouncer_coalesces_and_flushes():
    calls, timers = [], []

    def factory(cb):
        timers.append(FakeTimer(cb))
        return timers[-1]
    d = ss.Debouncer(lambda: calls.append(1), factory, 300)
    for _ in range(10):
        d.request()
    assert calls == [] and timers[0].started == [300]       # one timer for 10 requests
    timers[0].fire()
    assert calls == [1]
    d.request()
    d.flush()                                               # flush on close
    assert calls == [1, 1]
    d.flush()                                               # nothing pending
    assert calls == [1, 1]
    d.request()
    d.cancel()
    timers[0].fire()
    assert calls == [1, 1]


def test_bundle_roundtrip_zip_and_json(tmp_path):
    cfg = {"download": {"workers": 6}, "display": {"theme": "dark", "categories": ["01 Pop"]},
           "future": {"k": 1}}
    favs = ["01 Pop/Song", "02 Anime/Other"]
    for name in ("b.zip", "b.json"):
        path = str(tmp_path / name)
        ss.export_bundle(path, cfg, favs)
        got_cfg, got_favs, problems = ss.read_bundle(path)
        assert got_cfg == cfg and got_favs == favs and problems == []
    assert set(zipfile.ZipFile(tmp_path / "b.zip").namelist()) == {"config.toml",
                                                                    "favourites.json"}


def test_bundle_validates_and_rejects_garbage(tmp_path):
    p = tmp_path / "b.json"
    p.write_text(json.dumps({"format": ss.BUNDLE_FORMAT, "config": {
        "download": {"workers": 500}}, "favourites": ["bad", "a/b"]}), encoding="utf-8")
    cfg, favs, problems = ss.read_bundle(str(p))
    assert cfg == {"download": {}} and favs == ["a/b"] and problems == ["download.workers"]
    for text in ("not json", json.dumps({"hello": 1}), "[1]"):
        p.write_text(text, encoding="utf-8")
        with pytest.raises(ss.BundleError):
            ss.read_bundle(str(p))
    z = tmp_path / "bad.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("other.txt", "x")
    with pytest.raises(ss.BundleError):
        ss.read_bundle(str(z))


def test_diff_config():
    rows = ss.diff_config({"download": {"workers": 3}},
                          {"download": {"workers": 5}, "display": {"theme": "dark"}})
    assert {(k, o, n) for k, o, n in rows} == {("download.workers", 3, 5),
                                              ("display.theme", "auto", "dark")}


# ---------------------------------------------------------------- window
@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    for mod in (appconfig, ese_qt, workers, core):
        for name, val in (("DB_PATH", tmp_path / "ese_songs.db"),
                          ("LOCAL_DB_PATH", tmp_path / "ese_local.db"),
                          ("CONFIG_FILE", tmp_path / "config.toml"),
                          ("VERSION_FILE", tmp_path / "version.txt"),
                          ("NEW_SONGS_FILE", tmp_path / "new_songs.json"),
                          ("FAVOURITES_FILE", tmp_path / "favourites.json")):
            if hasattr(mod, name):
                monkeypatch.setattr(mod, name, str(val))
    monkeypatch.setattr(ese_qt, "APP_DIR", str(tmp_path))
    monkeypatch.setattr(appconfig, "APP_DIR", str(tmp_path))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    made = []

    def make(text=None):
        if text is not None:
            (tmp_path / "config.toml").write_text(text, encoding="utf-8")
        w = ese_qt.MainWindow()
        made.append(w)
        return w
    make.tmp = tmp_path
    yield make
    from conftest import dispose_window
    for w in made:
        dispose_window(w)


def _cfg(tmp):
    return tomllib.loads((tmp / "config.toml").read_text(encoding="utf-8"))


def test_window_recovers_from_broken_config(window, monkeypatch):
    tmp = window.tmp
    w = window("[download\nbroken")
    assert w._config_broken and ".broken-" in w._config_broken
    assert os.path.exists(w._config_broken) and not (tmp / "config.toml").exists()
    assert w.workers_spin.value() == 3                       # defaults
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: shown.append(a[-1]))
    w._notify_broken_config()
    w._notify_broken_config()                                # one-time
    assert len(shown) == 1 and ".broken-" in shown[0]


def test_window_bad_values_default_and_unknown_keys_kept(window):
    tmp = window.tmp
    w = window('[download]\nworkers = 99\nmystery = "keep"\n[display]\ntheme = "neon"\n'
               '[newsection]\nv = 1\n')
    assert w.workers_spin.value() == 3 and w.theme_pref == "auto"
    w.workers_spin.setValue(4)
    got = _cfg(tmp)
    assert got["download"]["workers"] == 4 and got["download"]["mystery"] == "keep"
    assert got["newsection"] == {"v": 1}


@pytest.mark.real_debounce
def test_window_save_is_debounced(window, monkeypatch):
    tmp = window.tmp
    w = window()
    writes = []
    real = ss.save_known
    monkeypatch.setattr(ss, "save_known", lambda *a, **k: (writes.append(1), real(*a, **k))[1])
    w.flush_config()
    writes.clear()
    for v in (2, 3, 4, 5):
        w.workers_spin.setValue(v)
    assert writes == []                                      # coalesced, not yet written
    w.flush_config()
    assert writes == [1] and _cfg(tmp)["download"]["workers"] == 5
    w.workers_spin.setValue(6)
    w.close()                                                # flushed on close
    assert _cfg(tmp)["download"]["workers"] == 6


def test_reset_keeps_favourites_and_directory(window):
    tmp = window.tmp
    w = window('[download]\ndirectory = "D:/my songs"\nworkers = 7\nfuture = 1\n'
               '[display]\ntheme = "dark"\n')
    core.save_favourites({("Song", "01 Pop")})
    w.song_model.set_favourites(core.load_favourites())
    w.reset_settings()
    got = _cfg(tmp)
    assert got["download"] == {"directory": w.dir_edit.text(), "future": 1}
    assert "display" not in got
    assert core.load_favourites() == {("Song", "01 Pop")}
    w.reset_settings(reset_favs=True, reset_dir=True)
    assert "directory" not in _cfg(tmp).get("download", {})
    assert core.load_favourites() == set()


def test_reset_ui_confirm_cancel_and_no_overwrite_after(window, monkeypatch):
    tmp = window.tmp
    w = window('[download]\nworkers = 7\n')
    monkeypatch.setattr(w, "_ask_reset", lambda: None)
    w.reset_settings_ui()
    assert _cfg(tmp)["download"]["workers"] == 7
    monkeypatch.setattr(w, "_ask_reset", lambda: (False, False))
    w.reset_settings_ui()
    assert "workers" not in _cfg(tmp).get("download", {})
    w.save_config()                                          # must not resurrect old values
    w.close()
    assert "workers" not in _cfg(tmp).get("download", {})


def test_export_import_roundtrip(window, monkeypatch):
    tmp = window.tmp
    w = window('[download]\nworkers = 6\n[display]\ntheme = "dark"\n')
    core.save_favourites({("Song", "01 Pop")})
    bundle = str(tmp / "out.zip")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (bundle, ""))
    w.export_settings()
    assert zipfile.is_zipfile(bundle)

    w.reset_settings(reset_favs=True)
    w2 = window()
    assert w2.workers_spin.value() == 3
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (bundle, ""))
    asked = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: (asked.append(a[2]), QMessageBox.Yes)[1])
    w2.import_settings()
    assert asked and "download.workers" in asked[0] and "display.theme" in asked[0]
    got = _cfg(tmp)
    assert got["download"]["workers"] == 6 and got["display"]["theme"] == "dark"
    assert core.load_favourites() == {("Song", "01 Pop")}


def test_import_nothing_and_bad_file(window, monkeypatch):
    tmp = window.tmp
    w = window('[download]\nworkers = 6\n')
    bundle = str(tmp / "same.json")
    w.flush_config()
    cfg, _ = ss.read_config(str(tmp / "config.toml"))
    ss.export_bundle(bundle, cfg, w._fav_ids())
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (bundle, ""))
    msgs = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: msgs.append(a[-1]))
    w.import_settings()
    assert msgs == [w.tr("import_nothing")]
    bad = tmp / "bad.json"
    bad.write_text("nope", encoding="utf-8")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(bad), ""))
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(1))
    w.import_settings()
    assert warned == [1] and _cfg(tmp)["download"]["workers"] == 6


def test_footer_buttons_exist_and_strings_in_all_languages(window):
    w = window()
    for b in (w.set_reset_btn, w.set_export_btn, w.set_import_btn, w.set_folder_btn):
        assert b.text()
    from i18n import TR
    keys = [k for k in TR["en"] if k.startswith(("set_reset", "reset_", "import_", "export_",
                                                  "set_export", "set_import", "set_open_folder",
                                                  "cfg_broken", "settings_filter"))]
    assert keys
    for lang in ("zh_TW", "ja"):
        assert all(k in TR[lang] for k in keys), lang


# ---------------------------------------------------------------- CLI
def test_cli_config_get_set_reset(app):
    tmp, run = app
    rc, out = run("config", "get", "download.workers")
    assert rc == 0 and out.strip().splitlines()[0] == "3"
    (tmp / "config.toml").write_text('[download]\nfuture = "x"\n', encoding="utf-8")
    rc, out = run("config", "set", "download.workers", "5")
    assert rc == 0
    rc, out = run("config", "get", "download.workers")
    assert out.strip().splitlines()[0] == "5"
    got = tomllib.loads((tmp / "config.toml").read_text(encoding="utf-8"))
    assert got["download"] == {"future": "x", "workers": 5}          # unknown key kept
    rc, out = run("config", "set", "download.workers", "99")
    assert rc == 2 and "invalid" in out
    rc, out = run("config", "set", "nope.key", "1")
    assert rc == 2 and "unknown setting" in out
    rc, out = run("config", "set", "display.theme", "dark")
    assert rc == 0
    rc, out = run("config", "reset", "display.theme")
    assert rc == 0
    rc, out = run("config", "get", "display.theme")
    assert out.strip().splitlines()[0] == "auto"
    run("config", "set", "download.directory", "D:/x")
    rc, out = run("config", "reset")
    got = tomllib.loads((tmp / "config.toml").read_text(encoding="utf-8"))
    assert got["download"] == {"future": "x", "directory": "D:/x"}   # directory kept
    rc, out = run("config", "reset", "--all")
    got = tomllib.loads((tmp / "config.toml").read_text(encoding="utf-8"))
    assert got["download"] == {"future": "x"}


def test_cli_config_get_all_json_and_broken_file(app):
    tmp, run = app
    (tmp / "config.toml").write_text("[oops", encoding="utf-8")
    rc, out = run("config", "get", "--json")
    assert rc == 0 and "damaged" in out
    assert any(p.name.startswith("config.toml.broken-") for p in tmp.iterdir())
    line = [x for x in out.splitlines() if x.startswith("{")][0]
    assert json.loads(line)["download.workers"] == 3
