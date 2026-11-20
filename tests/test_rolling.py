"""Rolling-release support: version parsing, the in-app update check and the
manual "Update DB" button (which now downloads from GitHub Pages)."""

import json

import pytest
from PySide6.QtWidgets import QMessageBox

import appconfig
import core
import workers
from appconfig import is_newer, parse_version


@pytest.mark.parametrize("tag,expected", [
    ("v2026.11.18", (2026, 11, 18)),
    ("v2026.11.18.2", (2026, 11, 18, 2)),
    ("v1.2.1", (1, 2, 1)),
    ("dev", None),
    ("ci-abc1234", None),
    ("", None),
])
def test_parse_version(tag, expected):
    assert parse_version(tag) == expected


def test_is_newer():
    assert is_newer("v2026.11.18", "v1.2.1")            # date versions follow semver ones
    assert is_newer("v2026.11.18.2", "v2026.11.18")
    assert is_newer("v2026.11.19", "v2026.11.18.5")
    assert not is_newer("v2026.11.18", "v2026.11.18")
    assert not is_newer("v2026.11.17", "v2026.11.18")
    assert not is_newer("v2026.11.18", "dev")           # source runs never prompt
    assert not is_newer("garbage", "v1.0")


def run_app_update(monkeypatch, base, current):
    monkeypatch.setattr(core, "LATEST_RELEASE_API", base + "latest.json")
    t = workers.AppUpdateThread(current)
    out = []
    t.found.connect(lambda tag, url: out.append((tag, url)))
    t.run()
    return out


def test_app_update_found(http_dir, monkeypatch, qapp):
    www, base = http_dir
    url = "https://github.com/GanYiZhong/ESEManager/releases/tag/v2026.11.18"
    (www / "latest.json").write_text(json.dumps({"tag_name": "v2026.11.18", "html_url": url}))
    assert run_app_update(monkeypatch, base, "v1.2.1") == [("v2026.11.18", url)]
    assert run_app_update(monkeypatch, base, "v2026.11.18") == []
    assert run_app_update(monkeypatch, base, "dev") == []


def test_app_update_ignores_bad_data(http_dir, monkeypatch, qapp):
    www, base = http_dir
    (www / "latest.json").write_text(json.dumps(
        {"tag_name": "v2099.1.1", "html_url": "https://evil.example/x"}))
    assert run_app_update(monkeypatch, base, "v1.2.1") == []      # not a GitHub page
    (www / "latest.json").write_text("not json")
    assert run_app_update(monkeypatch, base, "v1.2.1") == []      # silent on errors


# ---------------------------------------------------------------- manual DB update
@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    import ese_qt
    for mod in (appconfig, ese_qt, workers, core):
        for name, val in (("DB_PATH", tmp_path / "ese_songs.db"),
                          ("LOCAL_DB_PATH", tmp_path / "ese_local.db"),
                          ("CONFIG_FILE", tmp_path / "config.toml"),
                          ("VERSION_FILE", tmp_path / "version.txt")):
            if hasattr(mod, name):
                monkeypatch.setattr(mod, name, str(val))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)
    w = ese_qt.MainWindow()
    started = []
    monkeypatch.setattr(w, "start_db_download", lambda remote: started.append(remote))
    yield w, started, tmp_path
    w._closing = True
    w.close()


def test_manual_update_downloads_without_asking(window, monkeypatch):
    w, started, tmp = window
    asked = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: asked.append(a) or QMessageBox.No)
    w.on_version("v2", "v1", manual=True)
    assert started == ["v2"] and asked == []


def test_manual_update_reports_up_to_date(window, monkeypatch):
    w, started, tmp = window
    (tmp / "ese_songs.db").write_bytes(b"x")
    info = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: info.append(a[2]))
    w.on_version("v1", "v1", manual=True)
    assert started == [] and info == [w.tr("db_latest", v="v1")]


def test_manual_update_offline(window, monkeypatch):
    w, started, tmp = window
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(a[2]))
    w.on_version("", "v1", manual=True)
    assert started == [] and warned == [w.tr("db_offline")]
    assert w.db_update_btn.isEnabled()


def test_startup_check_asks_first(window):
    w, started, tmp = window
    w.on_version("v2", "v1")          # QMessageBox.question -> No
    assert started == []
