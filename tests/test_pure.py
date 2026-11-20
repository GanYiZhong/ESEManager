"""Tests for the pure helpers (no Qt, no network)."""

import os

import pytest

from appconfig import UnsafePathError, live_url, resolve_dir, safe_join, APP_DIR
from tja_parser import TJAParser, decode_tja_bytes
from core import human_eta, human_speed


# ---------------------------------------------------------------- safe_join
@pytest.mark.parametrize("rel", [
    "01 Pop/Song/song.tja",
    "01 Pop/Song (Ura)/song.ogg",
    "11 Dan Dojo/box.def",
    "a/./b.tja",
])
def test_safe_join_accepts_normal_paths(tmp_path, rel):
    full = safe_join(str(tmp_path), rel)
    assert full.startswith(str(tmp_path))
    assert full.endswith(os.path.normpath(rel.replace("/./", "/")).split(os.sep)[-1])


@pytest.mark.parametrize("rel", [
    "", "../x", "a/../../x", "a/..", "/etc/passwd", "\\\\server\\share\\x",
    "C:\\Windows\\x", "c:/x", "a/b:c", "..\\..\\x", "a/\0b",
])
def test_safe_join_rejects_escapes(tmp_path, rel):
    with pytest.raises(UnsafePathError):
        safe_join(str(tmp_path), rel)


def test_live_url_rewrites_old_host_and_raw():
    old = "https://git.vanillaaaa.org/ESE/ESE/raw/branch/master/a.ogg"
    assert live_url(old) == "https://ese.tjadataba.se/ESE/ESE/media/branch/master/a.ogg"
    assert live_url("") == ""


def test_resolve_dir_relative_to_app(tmp_path):
    assert resolve_dir("Downloads") == os.path.join(APP_DIR, "Downloads")
    assert resolve_dir(str(tmp_path)) == str(tmp_path)


# ---------------------------------------------------------------- TJA decoding
TJA = "TITLE:千本桜\nTITLEJA:千本桜\nBPM:154\nCOURSE:Oni\nLEVEL:10\n#START\n#END\n"


@pytest.mark.parametrize("data", [
    TJA.encode("utf-8"),
    b"\xef\xbb\xbf" + TJA.encode("utf-8"),
    TJA.encode("cp932"),
    TJA.encode("utf-16"),            # with BOM
])
def test_decode_tja_bytes_encodings(data):
    assert decode_tja_bytes(data).lstrip("\ufeff") == TJA


def test_decode_tja_bytes_never_fails():
    out = decode_tja_bytes(b"\xff\xff\x81\x00TITLE:x")
    assert isinstance(out, str) and "TITLE:x" in out


def test_parser_metadata_and_courses():
    p = TJAParser()
    text = ("TITLE:Foo\nTITLEJA:フー\nBPM:150\nCOURSE:Oni\nLEVEL:9\n#START\n#END\n"
            "COURSE:Edit\nLEVEL:10\n")
    assert p.parse_text(text) == {"title": "Foo", "titleja": "フー", "bpm": "150"}
    assert p.parse_courses(text) == {"easy": None, "normal": None, "hard": None,
                                     "oni": 9, "ura": 10}


def test_parse_file_uses_shared_decoder(tmp_path):
    f = tmp_path / "a.tja"
    f.write_bytes(TJA.encode("cp932"))
    meta = TJAParser().parse_file(str(f))
    assert meta["titleja"] == "千本桜"
    assert meta["level_oni"] == 10


# ---------------------------------------------------------------- formatting
def test_human_formatting():
    assert human_speed(0) == "—"
    assert human_speed(0.5) == "512 KB/s"
    assert human_speed(2) == "2.00 MB/s"
    assert human_eta(None) == "—"
    assert human_eta(59) == "59s"
    assert human_eta(61) == "1m01s"
    assert human_eta(3700) == "1h01m"
