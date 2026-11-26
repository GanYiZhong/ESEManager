"""Robust settings storage: schema validation, broken-file recovery, atomic
writes, a save debouncer, and export/import bundles. No Qt here, so the GUI,
the CLI and the tests all share it."""

import io
import json
import logging
import os
import time
import zipfile

try:
    import tomllib
except ImportError:          # Python < 3.11
    import tomli as tomllib
import tomli_w

import core

log = logging.getLogger("ese")

DEFAULT_DOWNLOAD_DIR = "Downloads"
LANGS = ("auto", "zh_TW", "en", "ja")
THEMES = ("auto", "light", "dark", "high_contrast")
FONT_SCALES = (90, 100, 115, 130)
DENSITIES = ("comfortable", "compact")
SOURCES = ("auto", "ese", "taiko.ac")
MAX_WORKERS = 16
BUNDLE_FORMAT = "ese-settings"
MAX_BUNDLE_BYTES = 5 * 1024 * 1024


class BundleError(ValueError):
    pass


# ---------------------------------------------------------------- schema
# (section, key) -> (kind, param, default)
SCHEMA = {
    ("download", "directory"): ("str", None, DEFAULT_DOWNLOAD_DIR),
    ("download", "workers"): ("int", (1, MAX_WORKERS), 3),
    ("download", "keep_awake"): ("bool", None, True),
    ("download", "auto_check_updates"): ("bool", None, True),
    ("download", "auto_app_update"): ("bool", None, True),
    ("download", "last_full_check"): ("float", 0.0, 0.0),
    ("download", "source"): ("source", None, "auto"),
    ("display", "page_size"): ("int", (1, 1000), 20),
    ("display", "categories"): ("strlist", None, []),
    ("display", "ui_language"): ("enum", LANGS, "auto"),
    ("display", "last_seen_version"): ("strany", None, ""),
    ("display", "theme"): ("enum", THEMES, "auto"),
    ("display", "font_scale"): ("enum", FONT_SCALES, 100),
    ("display", "density"): ("enum", DENSITIES, "comfortable"),
    ("display", "window_w"): ("int", (1, 100000), 1280),
    ("display", "window_h"): ("int", (1, 100000), 860),
    ("display", "monitor_open"): ("bool", None, False),
    ("display", "columns_order"): ("strlist", None, []),
    ("display", "columns_hidden"): ("strlist", None, []),
    ("display", "columns_widths"): ("intdict", None, {}),
    ("display", "detail_open"): ("bool", None, False),
    ("display", "detail_w"): ("int", (1, 100000), 320),
    ("display", "splitter"): ("pair", None, []),
    ("display", "category"): ("strany", None, ""),     # legacy single category
}


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _check(kind, param, v):
    """(ok, normalised value)."""
    if kind == "bool":
        return isinstance(v, bool), v
    if kind == "int":
        lo, hi = param
        return _is_int(v) and lo <= v <= hi, v
    if kind == "float":
        ok = isinstance(v, (int, float)) and not isinstance(v, bool) and v >= param \
            and v == v and v != float("inf")
        return ok, (float(v) if ok else v)
    if kind == "enum":
        return (not isinstance(v, bool) and v in param), v
    if kind == "str":
        return isinstance(v, str) and v.strip() != "", v
    if kind == "strany":
        return isinstance(v, str), v
    if kind == "source":
        ok = isinstance(v, str) and (v in SOURCES or v.lower().startswith(("http://", "https://")))
        return ok, v
    if kind == "strlist":
        # lenient per element: bad entries are dropped, the rest kept
        return isinstance(v, list), ([x for x in v if isinstance(x, str)]
                                     if isinstance(v, list) else v)
    if kind == "intdict":
        return isinstance(v, dict), ({k: x for k, x in v.items()
                                      if isinstance(k, str) and _is_int(x) and x > 0}
                                     if isinstance(v, dict) else v)
    if kind == "pair":
        return (isinstance(v, list) and len(v) == 2
                and all(_is_int(x) and x > 0 for x in v)), v
    return False, v


def sections():
    return sorted({s for s, _ in SCHEMA})


def default_of(section, key):
    d = SCHEMA[(section, key)][2]
    return list(d) if isinstance(d, list) else dict(d) if isinstance(d, dict) else d


def validate(cfg):
    """Return (clean, problems). Known keys with a bad type/range are dropped (so
    the caller's default applies) and listed in `problems`; unknown keys and
    sections are kept untouched."""
    clean, problems = {}, []
    if not isinstance(cfg, dict):
        return clean, ["<root>"]
    for sec, body in cfg.items():
        if sec in sections():
            if not isinstance(body, dict):
                problems.append(sec)
                continue
            out = {}
            for k, v in body.items():
                spec = SCHEMA.get((sec, k))
                if spec is None:
                    out[k] = v
                    continue
                ok, nv = _check(spec[0], spec[1], v)
                if ok:
                    out[k] = nv
                else:
                    problems.append(f"{sec}.{k}")
            clean[sec] = out
        else:
            clean[sec] = body
    return clean, problems


def merge_unknown(old, new):
    """`new` (the full known state) over `old`, keeping every key of `old` that
    `new` does not mention, so unknown settings survive a save."""
    res = {k: (dict(v) if isinstance(v, dict) else v) for k, v in (old or {}).items()}
    for sec, body in new.items():
        if isinstance(body, dict) and isinstance(res.get(sec), dict):
            res[sec].update(body)
        else:
            res[sec] = body
    return res


# ---------------------------------------------------------------- load / save
def _broken_name(path):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest, n = f"{path}.broken-{stamp}", 1
    while os.path.exists(dest):
        n += 1
        dest = f"{path}.broken-{stamp}-{n}"
    return dest


def read_config(path):
    """Parse without side effects: (cfg or None when missing, error or None)."""
    try:
        with open(path, "rb") as f:
            return tomllib.load(f), None
    except FileNotFoundError:
        return None, None
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        return None, e
    except OSError as e:
        log.warning("cannot read %s: %s", path, e)
        return None, None


def load_config(path):
    """Load and validate. Returns (cfg, broken_path). A file that is not valid
    TOML is renamed to <path>.broken-<timestamp> (never overwritten) and
    defaults ({}) are used; broken_path says where it went."""
    raw, err = read_config(path)
    if err is not None:
        dest = _broken_name(path)
        try:
            os.replace(path, dest)
        except OSError:
            log.warning("could not move broken config %s", path, exc_info=True)
            dest = None
        log.warning("config %s is damaged (%s); moved to %s, using defaults", path, err, dest)
        return {}, dest or path
    if raw is None:
        return {}, None
    cfg, problems = validate(raw)
    if problems:
        log.warning("config: ignoring invalid values: %s", ", ".join(problems))
    return cfg, None


def write_config(path, cfg):
    core.write_atomic(path, tomli_w.dumps(cfg).encode("utf-8"))


def save_known(path, known, existing=None):
    """Write `known` over the current file's content, preserving unknown keys."""
    if existing is None:
        existing, _ = read_config(path)
    cfg = merge_unknown(existing or {}, known)
    write_config(path, cfg)
    return cfg


def reset_config(cfg, keep_directory=True):
    """cfg without any known setting (defaults apply); unknown keys stay."""
    out = {}
    for sec, body in (cfg or {}).items():
        if isinstance(body, dict) and sec in sections():
            keep = {k: v for k, v in body.items() if (sec, k) not in SCHEMA
                    or (keep_directory and (sec, k) == ("download", "directory"))}
            if keep:
                out[sec] = keep
        else:
            out[sec] = body
    return out


# ---------------------------------------------------------------- dotted keys (CLI)
def split_key(key):
    sec, _, k = (key or "").partition(".")
    if (sec, k) not in SCHEMA:
        raise KeyError(key)
    return sec, k


def all_keys():
    return [f"{s}.{k}" for s, k in SCHEMA]


def parse_value(section, key, text):
    """Text from the command line -> a validated value (ValueError if bad)."""
    kind, param, _ = SCHEMA[(section, key)]
    t = text.strip()
    try:
        if kind == "bool":
            v = {"true": True, "yes": True, "on": True, "1": True,
                 "false": False, "no": False, "off": False, "0": False}[t.lower()]
        elif kind in ("int", "float"):
            v = int(t) if kind == "int" else float(t)
        elif kind == "enum":
            v = next(e for e in param if str(e) == t)
        elif kind in ("str", "strany", "source"):
            v = t
        else:
            try:
                v = json.loads(t)
            except ValueError:
                v = [x.strip() for x in t.split(",") if x.strip()] if t else []
                if kind == "pair":
                    v = [int(x) for x in v]
    except (KeyError, ValueError, StopIteration):
        raise ValueError(f"invalid value {text!r} for {section}.{key}") from None
    ok, nv = _check(kind, param, v)
    if not ok:
        raise ValueError(f"invalid value {text!r} for {section}.{key}")
    return nv


# ---------------------------------------------------------------- debounce
class Debouncer:
    """Coalesce many request() calls into one fn() within `delay_ms`.
    timer_factory(callback) must return an object with start(ms), stop() and
    isActive() (a QTimer wrapper in the GUI, a fake in tests)."""

    def __init__(self, fn, timer_factory, delay_ms=300):
        self.fn = fn
        self.delay_ms = delay_ms
        self.pending = False
        self._timer = timer_factory(self._fire)

    def request(self):
        self.pending = True
        if not self._timer.isActive():
            self._timer.start(self.delay_ms)

    def _fire(self):
        if self.pending:
            self.pending = False
            self.fn()

    def flush(self):
        self._timer.stop()
        self._fire()

    def cancel(self):
        self._timer.stop()
        self.pending = False


# ---------------------------------------------------------------- export / import
def _fav_ids(data):
    items = data.get("songs") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    return sorted({i for i in items if isinstance(i, str) and "/" in i
                   and i.split("/", 1)[0] and i.split("/", 1)[1]})


def export_bundle(path, cfg, fav_ids):
    """.json -> one JSON document; anything else -> zip with config.toml and
    favourites.json."""
    fav_ids = sorted(fav_ids)
    fav_doc = {"version": 1, "songs": fav_ids}
    if str(path).lower().endswith(".json"):
        doc = {"format": BUNDLE_FORMAT, "version": 1, "config": cfg, "favourites": fav_ids}
        core.write_atomic(path, json.dumps(doc, ensure_ascii=False, indent=1).encode("utf-8"))
        return
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("config.toml", tomli_w.dumps(cfg))
        z.writestr("favourites.json", json.dumps(fav_doc, ensure_ascii=False, indent=1))
    core.write_atomic(path, buf.getvalue())


def read_bundle(path):
    """(validated cfg, favourite ids or None, problems). BundleError if the
    file is not a settings bundle."""
    try:
        if os.path.getsize(path) > MAX_BUNDLE_BYTES:
            raise BundleError("too large")
        with open(path, "rb") as f:
            raw = f.read()
        favs = None
        if raw[:2] == b"PK":
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                names = set(z.namelist())
                if "config.toml" not in names:
                    raise BundleError("config.toml missing")
                for n in ("config.toml", "favourites.json"):
                    if n in names and z.getinfo(n).file_size > MAX_BUNDLE_BYTES:
                        raise BundleError("too large")
                cfg = tomllib.loads(z.read("config.toml").decode("utf-8"))
                if "favourites.json" in names:
                    favs = _fav_ids(json.loads(z.read("favourites.json").decode("utf-8")))
        else:
            doc = json.loads(raw.decode("utf-8"))
            if not isinstance(doc, dict) or doc.get("format") != BUNDLE_FORMAT:
                raise BundleError("not an ESEManager settings file")
            cfg = doc.get("config")
            if not isinstance(cfg, dict):
                raise BundleError("config missing")
            if "favourites" in doc:
                favs = _fav_ids(doc["favourites"])
    except BundleError:
        raise
    except (OSError, ValueError, zipfile.BadZipFile, UnicodeDecodeError, KeyError) as e:
        raise BundleError(str(e)) from e
    clean, problems = validate(cfg)
    return clean, favs, problems


def diff_config(old, new):
    """[(dotted key, old effective value, new effective value)] for known keys
    whose effective value changes when `new` replaces `old`."""
    rows = []
    for (sec, k) in SCHEMA:
        o = (old or {}).get(sec, {}).get(k, default_of(sec, k))
        n = (new or {}).get(sec, {}).get(k, default_of(sec, k))
        if o != n:
            rows.append((f"{sec}.{k}", o, n))
    return rows
