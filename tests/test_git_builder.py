"""The Pages database builder reads charts through git in batches.

Uses a throwaway local repository served over file:// as a partial-clone
server, so the test never contacts ESE.
"""

import shutil
import sqlite3
import subprocess

import pytest

import build_local_db
from ese_scraper_git_v2 import ESEScraperGitV2

GIT = shutil.which("git")
pytestmark = pytest.mark.skipif(not GIT, reason="git not installed")


def git(*args, cwd=None):
    return subprocess.run([GIT, *args], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout


def tja(title, title_ja, oni):
    return (f"TITLE:{title}\nTITLEJA:{title_ja}\nBPM:150\nWAVE:{title}.ogg\n"
            f"COURSE:Oni\nLEVEL:{oni}\n#START\n1,\n#END\n").encode("utf-8")


@pytest.fixture
def upstream(tmp_path):
    """A small ESE-like repository plus a bare copy that allows partial clones."""
    work = tmp_path / "work"
    work.mkdir()
    git("init", "-q", "-b", "master", cwd=work)
    git("config", "user.email", "t@example.com", cwd=work)
    git("config", "user.name", "t", cwd=work)

    def write(rel, data):
        p = work / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    write("01 Pop/Alpha/Alpha.tja", tja("Alpha", "アルファ", 7))
    write("01 Pop/Alpha/Alpha.ogg", b"OggS audio")
    write("02 Anime/Beta/Beta.tja", tja("Beta", "ベータ", 8).decode().encode("cp932"))
    write("02 Anime/Beta/Beta.ogg", b"OggS audio 2")
    write("02 Anime/box.def", b"#TITLE:Anime\n")
    git("add", "-A", cwd=work)
    git("commit", "-q", "-m", "init", cwd=work)

    bare = tmp_path / "ese.git"
    git("clone", "-q", "--bare", str(work), str(bare))
    git("config", "uploadpack.allowFilter", "true", cwd=bare)
    git("config", "uploadpack.allowAnySHA1InWant", "true", cwd=bare)

    def commit(rel, data):
        write(rel, data)
        git("add", "-A", cwd=work)
        git("commit", "-q", "-m", "update", cwd=work)
        git("push", "-q", str(bare), "master", cwd=work)

    return bare.as_uri(), commit


def build(tmp_path, url):
    clone = str(tmp_path / "clone")
    songs = str(tmp_path / "ese_songs.db")
    local = str(tmp_path / "ese_local.db")
    s = ESEScraperGitV2(db_path=songs, clone_dir=clone, git_exe=GIT)
    s.git_url = url
    try:
        s.scrape(keep_clone=True)
    finally:
        s.close()
    n = build_local_db.build_from_git(songs, local, clone, git_exe=GIT)
    return n, local, clone


def rows(local):
    conn = sqlite3.connect(local)
    try:
        return {fp: (ja, oni) for fp, ja, oni in conn.execute(
            "SELECT file_path, title_ja, level_oni FROM local_songs")}
    finally:
        conn.close()


def test_builds_from_batched_fetch(tmp_path, upstream, monkeypatch):
    url, commit = upstream
    calls = []
    real = build_local_db._fetch_blobs
    monkeypatch.setattr(build_local_db, "_fetch_blobs",
                        lambda g, c, oids: (calls.append(list(oids)), real(g, c, oids)))
    n, local, clone = build(tmp_path, url)
    assert n == 2
    assert rows(local) == {"01 Pop/Alpha/Alpha.tja": ("アルファ", 7),
                           "02 Anime/Beta/Beta.tja": ("ベータ", 8)}
    # One batched request for exactly the two chart blobs; audio never fetched.
    assert len(calls) == 1 and len(calls[0]) == 2
    missing = subprocess.run([GIT, "-C", clone, "rev-list", "--objects", "--missing=print",
                              "--no-object-names", "master"],
                             capture_output=True, text=True).stdout
    assert sum(1 for line in missing.splitlines() if line.startswith("?")) == 3  # 2 ogg + box.def


def test_incremental_only_changed_charts(tmp_path, upstream, monkeypatch):
    url, commit = upstream
    build(tmp_path, url)
    commit("01 Pop/Alpha/Alpha.tja", tja("Alpha", "アルファ改", 9))

    calls = []
    real = build_local_db._fetch_blobs
    monkeypatch.setattr(build_local_db, "_fetch_blobs",
                        lambda g, c, oids: (calls.append(list(oids)), real(g, c, oids)))
    n, local, _ = build(tmp_path, url)
    assert n == 1                                    # only the edited chart
    assert calls == [calls[0]] and len(calls[0]) == 1
    assert rows(local)["01 Pop/Alpha/Alpha.tja"] == ("アルファ改", 9)

    # Nothing changed: no fetch at all.
    calls.clear()
    n, _, _ = build(tmp_path, url)
    assert n == 0 and calls == []


def test_removed_charts_are_pruned(tmp_path, upstream):
    url, commit = upstream
    build(tmp_path, url)
    # Delete Beta upstream.
    tmp = tmp_path / "w2"
    git("clone", "-q", url, str(tmp))
    git("config", "user.email", "t@example.com", cwd=tmp)
    git("config", "user.name", "t", cwd=tmp)
    git("rm", "-q", "-r", "02 Anime/Beta", cwd=tmp)
    git("commit", "-q", "-m", "rm", cwd=tmp)
    git("push", "-q", "origin", "master", cwd=tmp)
    n, local, _ = build(tmp_path, url)
    assert list(rows(local)) == ["01 Pop/Alpha/Alpha.tja"]
