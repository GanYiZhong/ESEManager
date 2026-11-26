"""Simulator song-folder detection: fake trees only, read-only, bounded."""

import json
import os
import subprocess
import sys
import time

import core
import ese_qt
from test_gui import window  # noqa: F401  (fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def touch(p):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")


def snapshot(root):
    return sorted((str(p), p.stat().st_mtime_ns) for p in root.rglob("*"))


def make_tree(tmp_path):
    game = tmp_path / "games" / "OpenTaiko"
    touch(game / "OpenTaiko.exe")
    for i in range(3):
        touch(game / "Songs" / "Cat" / f"s{i}" / "a.tja")
    touch(tmp_path / "games" / "Other" / "Songs" / "x" / "b.tja")
    touch(tmp_path / "games" / "Empty" / "Songs" / "readme.txt")
    return game


def test_finds_known_simulator_first(tmp_path):
    game = make_tree(tmp_path)
    found = core.find_song_folders(roots=[str(tmp_path)])
    assert [c["path"] for c in found] == [str(game / "Songs"),
                                          str(tmp_path / "games" / "Other" / "Songs")]
    assert found[0]["simulator"] == "OpenTaiko" and found[0]["tja_count"] == 3
    assert found[1]["simulator"] == "" and found[1]["tja_count"] == 1


def test_read_only(tmp_path):
    make_tree(tmp_path)
    before = snapshot(tmp_path)
    core.find_song_folders(roots=[str(tmp_path)])
    assert snapshot(tmp_path) == before


def test_depth_limit(tmp_path):
    touch(tmp_path / "a" / "b" / "c" / "d" / "Songs" / "x.tja")
    assert core.find_song_folders(roots=[str(tmp_path)]) == []


def test_entry_limit(tmp_path):
    touch(tmp_path / "Songs" / "x.tja")
    for i in range(50):
        touch(tmp_path / f"d{i:02d}" / "f.txt")
    found = core.find_song_folders(roots=[str(tmp_path)], max_entries=5)
    assert len(found) <= 1


def test_time_limit(tmp_path):
    make_tree(tmp_path)
    t = time.monotonic()
    assert core.find_song_folders(roots=[str(tmp_path)], max_seconds=0) == []
    assert time.monotonic() - t < 1


def test_symlinks_not_followed(tmp_path):
    real = tmp_path / "real"
    touch(real / "Songs" / "x.tja")
    scan = tmp_path / "scan"
    scan.mkdir()
    try:
        os.symlink(real, scan / "link", target_is_directory=True)
    except (OSError, NotImplementedError):
        return
    assert core.find_song_folders(roots=[str(scan)]) == []


def test_steam_library_roots(tmp_path, monkeypatch):
    lib = tmp_path / "SteamLib"
    touch(lib / "steamapps" / "common" / "TJAPlayer3" / "TJAPlayer3.exe")
    touch(lib / "steamapps" / "common" / "TJAPlayer3" / "Songs" / "a.tja")
    vdf = tmp_path / "home" / ".steam" / "steam" / "steamapps" / "libraryfolders.vdf"
    vdf.parent.mkdir(parents=True)
    vdf.write_text('"libraryfolders"\n{\n "1"\n {\n  "path"  "%s"\n }\n}\n'
                   % str(lib).replace("\\", "\\\\"), encoding="utf-8")
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path / "home"))
    for v in ("ProgramFiles", "ProgramFiles(x86)"):
        monkeypatch.delenv(v, raising=False)
    roots = core._steam_library_roots()
    assert str(lib / "steamapps" / "common") in roots
    found = core.find_song_folders(roots=roots)
    assert found and found[0]["simulator"] == "TJAPlayer3"


def test_default_roots_use_patched_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    touch(home / "Documents" / "YataiDON" / "YataiDON.exe")
    touch(home / "Documents" / "YataiDON" / "Songs" / "a.tja")
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(home))
    monkeypatch.setattr(core, "APP_DIR", str(tmp_path / "app" / "ese"))
    for v in ("LOCALAPPDATA", "ProgramFiles", "ProgramFiles(x86)"):
        monkeypatch.delenv(v, raising=False)
    found = core.find_song_folders()
    assert [c["simulator"] for c in found] == ["YataiDON"]


def test_cli_detect_folders(tmp_path, monkeypatch):
    import cli
    game = make_tree(tmp_path)
    monkeypatch.setattr(core, "_song_search_roots", lambda: [str(tmp_path)])
    lines = []
    monkeypatch.setattr(cli.out, "msg", lines.append)
    monkeypatch.setattr(cli.out, "json", False)
    assert cli.cmd_detect_folders(None, lambda k, **kw: core_tr(k, **kw)) == 0
    assert str(game / "Songs") in lines[0] and "OpenTaiko" in lines[0]


def core_tr(k, **kw):
    from i18n import TR
    return TR["en"][k].format(**kw)


def test_cli_subcommand_registered():
    r = subprocess.run([sys.executable, os.path.join(ROOT, "src", "cli.py"),
                        "detect-folders", "--help"], capture_output=True, text=True,
                       env=dict(os.environ, PYTHONUTF8="1"), timeout=60)
    assert r.returncode == 0 and "detect-folders" in r.stdout


def test_welcome_offers_found_folder(window, monkeypatch, tmp_path):  # noqa: F811
    c = {"path": str(tmp_path / "Songs"), "simulator": "OpenTaiko",
         "tja_count": 1234, "truncated": False}
    before = window.dir_edit.text()
    window._on_folders_found([c])
    assert not window.welcome_found_row.isHidden()
    assert "OpenTaiko" in window.welcome_found.text() and "1234" in window.welcome_found.text()
    assert window.dir_edit.text() == before          # never switched on its own
    window.welcome_use_btn.click()
    assert window.dir_edit.text() == c["path"]
    assert c["path"] in window.welcome_dir.text()


def test_settings_detect_button(window, monkeypatch, tmp_path):  # noqa: F811
    c = {"path": str(tmp_path / "Songs"), "simulator": "", "tja_count": 2, "truncated": False}
    monkeypatch.setattr(core, "find_song_folders", lambda: [c])
    monkeypatch.setattr(ese_qt.QInputDialog, "getItem",
                        staticmethod(lambda parent, t, lbl, items, *a, **k: (items[0], True)))
    window.detect_btn.click()
    assert window.dir_edit.text() == c["path"]


def test_settings_detect_none_shows_info(window, monkeypatch):  # noqa: F811
    shown = []
    monkeypatch.setattr(core, "find_song_folders", lambda: [])
    monkeypatch.setattr(window, "toast", lambda text, kind="info", **k: shown.append(text))
    monkeypatch.setattr(ese_qt.QMessageBox, "information",
                        staticmethod(lambda *a, **k: 1 / 0))
    window.detect_btn.click()
    assert shown == [window.tr("detect_none")]
