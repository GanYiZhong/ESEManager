"""In-app update: download the release archive, verify it, install it over the
app folder (renaming files in use to .old) and clean up on the next start."""

import hashlib
import io
import os
import tarfile
import zipfile

import pytest

import core


NEW_FILES = {
    "ESEManager/ESEManager.exe": b"new exe",
    "ESEManager/_internal/lib.dll": b"new lib",
    "ESEManager/ese_songs.db": b"bundled db",
    "ESEManager/version.txt": b"bundled",
    "ESEManager/README.md": b"readme",
}


def make_zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


def make_tgz(files):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o755
            t.addfile(info, io.BytesIO(data))
    return buf.getvalue()


@pytest.fixture
def release(http_dir, monkeypatch):
    www, base = http_dir

    def publish(data, ext=".zip", plat="windows-x86_64", sha=None, tag="v2099.1.1"):
        monkeypatch.setattr(core, "update_platform", lambda: (plat, ext))
        name = f"ESEManager_{tag}_{plat}{ext}"
        (www / name).write_bytes(data)
        (www / (name + ".sha256")).write_text(
            f"{sha or hashlib.sha256(data).hexdigest()}  {name}\n")
        return {"tag_name": tag, "assets": [
            {"name": name, "size": len(data), "browser_download_url": base + name},
            {"name": name + ".sha256", "browser_download_url": base + name + ".sha256"}]}
    return publish


@pytest.fixture
def app(tmp_path):
    d = tmp_path / "app"
    (d / "_internal").mkdir(parents=True)
    (d / "Downloads").mkdir()
    (d / "ESEManager.exe").write_bytes(b"old exe")
    (d / "_internal" / "old.dll").write_bytes(b"old only")
    (d / "config.toml").write_text("mine")
    (d / "ese_songs.db").write_bytes(b"my newer db")
    (d / "Downloads" / "song.tja").write_bytes(b"chart")
    return d


@pytest.mark.parametrize("kind", ["zip", "tgz"])
def test_download_install_and_cleanup(release, app, kind):
    data = make_zip(NEW_FILES) if kind == "zip" else make_tgz(NEW_FILES)
    rel = release(data, ".zip" if kind == "zip" else ".tar.gz")
    seen = []
    root = core.download_app_update(rel, app_dir=str(app), log=lambda m: None,
                                    progress=lambda g, t: seen.append((g, t)))
    assert seen and seen[-1][0] == len(data)
    assert (app / "ESEManager.exe").read_bytes() == b"old exe"      # nothing changed yet

    n = core.apply_app_update(root, app_dir=str(app))
    assert n == 4                                     # exe, lib, version.txt, README
    assert (app / "ESEManager.exe").read_bytes() == b"new exe"
    assert (app / "ESEManager.exe.old").read_bytes() == b"old exe"
    assert (app / "_internal" / "lib.dll").read_bytes() == b"new lib"
    assert (app / "_internal" / "old.dll").exists()           # unrelated files stay
    assert (app / "ese_songs.db").read_bytes() == b"my newer db"  # user data kept
    assert (app / "config.toml").read_text() == "mine"
    assert (app / "version.txt").read_bytes() == b"bundled"   # installed: there was none
    assert (app / "Downloads" / "song.tja").exists()
    assert not (app / ".update").exists()

    assert core.cleanup_app_update(str(app)) == 1
    assert not (app / "ESEManager.exe.old").exists()
    assert not (app / core.UPDATE_OLD_LIST).exists()


def test_checksum_mismatch_changes_nothing(release, app):
    rel = release(make_zip(NEW_FILES), sha="0" * 64)
    with pytest.raises(RuntimeError, match="SHA-256"):
        core.download_app_update(rel, app_dir=str(app), log=lambda m: None)
    assert (app / "ESEManager.exe").read_bytes() == b"old exe"


def test_archive_cannot_escape_the_app_folder(release, app, tmp_path):
    rel = release(make_zip({"ESEManager/../../evil.txt": b"x"}))
    with pytest.raises(core.UnsafePathError):
        core.download_app_update(rel, app_dir=str(app), log=lambda m: None)
    assert not (tmp_path / "evil.txt").exists()


def test_failed_install_rolls_back(release, app, monkeypatch):
    root = core.download_app_update(release(make_zip(NEW_FILES)), app_dir=str(app),
                                    log=lambda m: None)
    real = os.replace
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] == 4:                       # fail part-way through
            raise PermissionError("locked")
        return real(src, dst)
    monkeypatch.setattr(core.os, "replace", flaky)
    with pytest.raises(PermissionError):
        core.apply_app_update(root, app_dir=str(app))
    monkeypatch.setattr(core.os, "replace", real)
    assert (app / "ESEManager.exe").read_bytes() == b"old exe"
    assert not (app / "ESEManager.exe.old").exists()
    assert not (app / "_internal" / "lib.dll").exists()


def test_missing_platform_asset_is_reported(release, monkeypatch):
    rel = release(make_zip(NEW_FILES))
    monkeypatch.setattr(core, "update_platform", lambda: ("linux-x86_64", ".tar.gz"))
    with pytest.raises(RuntimeError, match="not found"):
        core.pick_update_asset(rel)


def test_source_checkout_never_self_updates():
    assert not core.can_self_update()            # tests run from source


def test_cmd_paths_with_percent_are_refused():
    assert core._cmd_quote(r"C:\太鼓 遊戲\app") == r'"C:\太鼓 遊戲\app"'
    with pytest.raises(RuntimeError):
        core._cmd_quote(r"C:\100%\app")


def test_failed_windows_update_is_reported_once(app):
    (app / ".update").mkdir()
    (app / ".update" / core.UPDATE_FAILED).write_text("robocopy exit 8")
    core.cleanup_app_update(str(app))              # keeps the report
    assert core.update_failed(str(app)) == "robocopy exit 8"
    core.discard_update_work(str(app))
    assert core.update_failed(str(app)) == ""


def test_install_applies_in_place_off_windows(release, app, monkeypatch):
    root = core.download_app_update(release(make_zip(NEW_FILES)), app_dir=str(app),
                                    log=lambda m: None)
    monkeypatch.setattr(core.sys, "platform", "linux")
    assert core.install_app_update(root, app_dir=str(app)) == "applied"
    assert (app / "ESEManager.exe").read_bytes() == b"new exe"
