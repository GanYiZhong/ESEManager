"""ESE-Version-Sorting download: one archive, skipped when unchanged, safe extraction."""

import json
import zipfile

import pytest

import workers


def make_archive(path, files, extra=()):
    with zipfile.ZipFile(path, "w") as z:
        for rel, data in files.items():
            z.writestr("ese-version-sorting/" + rel, data)
        for name, data in extra:
            z.writestr(name, data)


@pytest.fixture
def server(http_dir, monkeypatch):
    www, base = http_dir
    monkeypatch.setattr(workers, "VSORT_BRANCH_API", base + "branch.json")
    monkeypatch.setattr(workers, "VSORT_ARCHIVE_URL", base + "{ref}.zip")

    def publish(commit, files, extra=()):
        (www / "branch.json").write_text(json.dumps({"commit": {"id": commit}}))
        make_archive(www / f"{commit}.zip", files, extra)
    return publish


def test_install_and_skip_when_unchanged(server, tmp_path):
    server("c1", {"box.def": "#TITLE:Version Sort\n",
                  "Arcade/01 AC1/01 Pop/song_list.txt": "abc|Song|\n"})
    dl = tmp_path / "Downloads"
    assert workers.download_version_sorting(str(dl), log=lambda m: None) == ("updated", "c1")
    root = dl / "ESE-Version-Sorting"
    assert (root / "box.def").read_text() == "#TITLE:Version Sort\n"
    assert (root / "Arcade/01 AC1/01 Pop/song_list.txt").exists()
    assert workers.download_version_sorting(str(dl), log=lambda m: None) == ("latest", "c1")
    assert not [p for p in dl.iterdir() if p.name.startswith(".vsort-")]   # temp cleaned


def test_update_replaces_folder(server, tmp_path):
    dl = tmp_path / "Downloads"
    server("c1", {"box.def": "v1", "old.txt": "gone soon"})
    workers.download_version_sorting(str(dl), log=lambda m: None)
    server("c2", {"box.def": "v2"})
    assert workers.download_version_sorting(str(dl), log=lambda m: None)[0] == "updated"
    root = dl / "ESE-Version-Sorting"
    assert (root / "box.def").read_text() == "v2"
    assert not (root / "old.txt").exists()


def test_rejects_path_traversal(server, tmp_path):
    dl = tmp_path / "Downloads"
    server("c1", {"box.def": "x"}, extra=[("ese-version-sorting/../../evil.txt", "evil")])
    with pytest.raises(workers.UnsafePathError):
        workers.download_version_sorting(str(dl), log=lambda m: None)
    assert not (tmp_path / "evil.txt").exists()
    assert not (dl / "ESE-Version-Sorting").exists()       # nothing half-installed
