"""core.friendly_error: short localized messages instead of raw exception text."""

import argparse
import errno
import ssl

import pytest
import requests

import core
from i18n import TR


def tr_en(key, **kw):
    s = TR["en"].get(key, key)
    return s.format(**kw) if kw else s


def _http(code):
    r = requests.Response()
    r.status_code = code
    return requests.HTTPError(f"HTTP {code}", response=r)


RAW = ("HTTPSConnectionPool(host='x', port=443): Max retries exceeded with url: /a "
       "(Caused by NewConnectionError('Failed to resolve'))")

CASES = [
    (requests.ConnectionError(RAW), "err_offline"),
    (requests.ConnectTimeout("t"), "err_timeout"),
    (requests.ReadTimeout("t"), "err_timeout"),
    (requests.ConnectionError("Read timed out."), "err_timeout"),
    (requests.exceptions.SSLError("CERTIFICATE_VERIFY_FAILED"), "err_tls"),
    (ssl.SSLError("bad"), "err_tls"),
    (_http(404), "err_not_found"),
    (_http(403), "err_rate_limit"),
    (_http(429), "err_rate_limit"),
    (_http(500), "err_server"),
    (_http(503), "err_server"),
    (OSError(errno.ENOSPC, "No space left on device"), "err_disk_full"),
    (PermissionError(errno.EACCES, "denied"), "err_permission"),
    (core.ChecksumError("SHA-256 mismatch"), "err_checksum"),
]


@pytest.mark.parametrize("exc,key", CASES)
def test_mapping(exc, key):
    msg = core.friendly_error(exc, tr_en)
    assert msg == TR["en"][key]
    assert "Max retries" not in msg and "Pool" not in msg


def test_unknown_falls_back_to_text():
    assert core.friendly_error(ValueError("boom"), tr_en) == "boom"
    assert core.friendly_error(KeyError(), tr_en) == "KeyError"


def test_default_translator_is_english():
    assert core.friendly_error(requests.ConnectionError(RAW)) == TR["en"]["err_offline"]


def test_all_hosts_failed_lists_hosts():
    exc = core.AllHostsFailed(["a.example", "b.example"], _http(404))
    msg = core.friendly_error(exc, tr_en)
    assert msg.startswith(TR["en"]["err_not_found"])
    assert "a.example, b.example" in msg


def test_keys_in_every_language():
    keys = [k for k in TR["en"] if k.startswith("err_")]
    assert len(keys) >= 10
    for lang in TR:
        assert all(k in TR[lang] for k in keys), lang


def test_downloader_log_is_friendly_and_names_hosts(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError(RAW)
    monkeypatch.setattr(core, "get_with_retry", boom)
    monkeypatch.setattr(core, "load_sha_map", lambda: {})
    logs = []

    def tr(key, **kw):
        if key == "log_fail":
            return "FAIL {f}: {e}".format(**kw)
        return tr_en(key, **kw)
    files = [({"song_name": "S"}, {"filename": "X.tja", "file_path": "01 Pop/S/X.tja",
                                   "download_url": ""})]
    job = core.Downloader(files, str(tmp_path / "dl"), 1, log=logs.append, tr=tr,
                          bases=["http://one.test/", "http://two.test/"])
    assert job.run()[2] == 1
    line = next(m for m in logs if m.startswith("FAIL"))
    assert "Max retries" not in line and "NewConnectionError" not in line
    assert "one.test" in line and "two.test" in line
    assert TR["en"]["err_offline"] in line


def test_update_databases_failure_maps_to_offline(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "DB_PATH", str(tmp_path / "ese_songs.db"))

    def boom(*a, **k):
        raise requests.ConnectionError(RAW)
    monkeypatch.setattr(core, "get_with_retry", boom)
    with pytest.raises(requests.ConnectionError) as ei:
        core.update_databases("1", log=lambda m: None, tr=tr_en)
    assert core.friendly_error(ei.value, tr_en) == TR["en"]["err_offline"]


def test_cli_db_update_prints_friendly(monkeypatch, capsys):
    import cli

    def boom(*a, **k):
        raise requests.ConnectionError(RAW)
    monkeypatch.setattr(core, "fetch_remote_version", lambda timeout=10: "2")
    monkeypatch.setattr(core, "read_local_version", lambda: "1")
    monkeypatch.setattr(core, "update_databases", boom)
    rc = cli.cmd_update_db(argparse.Namespace(force=True), cli.make_tr("en"))
    cap = capsys.readouterr()
    assert rc == 1
    assert "Max retries" not in cap.out + cap.err
    assert TR["en"]["err_offline"] in cap.out + cap.err
