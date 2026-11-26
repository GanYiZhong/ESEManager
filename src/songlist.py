"""Shareable song lists (Qt-free).

JSON file:  {"format": "esemanager-songlist", "version": 1, "name": ..,
             "created": .., "songs": [{"category": .., "song": ..}, ...]}
Text:       one "Category/Song" per line (a bare "Song" line also works;
            blank lines and lines starting with # are ignored).
"""

import datetime
import json
import re

import core

FORMAT = "esemanager-songlist"
VERSION = 1


def entries_from_songs(songs):
    return [(s["category"] or "", s["song_name"]) for s in songs]


def to_json(entries, name=""):
    return json.dumps({
        "format": FORMAT, "version": VERSION, "name": name,
        "created": datetime.datetime.now().replace(microsecond=0).isoformat(),
        "songs": [{"category": c, "song": n} for c, n in entries]},
        ensure_ascii=False, indent=2) + "\n"


def to_text(entries):
    return "".join(f"{c}/{n}\n" if c else f"{n}\n" for c, n in entries)


def parse(text):
    """-> (entries, name). entries are (category or "", song) pairs. Accepts
    the JSON file or text lines; raises ValueError for JSON of another kind."""
    text = (text or "").lstrip("﻿")
    if text.lstrip().startswith("{"):
        try:
            doc = json.loads(text)
        except ValueError as e:
            raise ValueError("not a song list") from e
        if not isinstance(doc, dict) or doc.get("format") != FORMAT \
                or not isinstance(doc.get("songs"), list):
            raise ValueError("not a song list")
        out = []
        for it in doc["songs"]:
            if isinstance(it, dict) and isinstance(it.get("song"), str) and it["song"].strip():
                out.append((str(it.get("category") or "").strip(), it["song"].strip()))
        name = doc.get("name")
        return out, name if isinstance(name, str) else ""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "/" in line:
            c, n = line.split("/", 1)
            out.append((c.strip(), n.strip()))
        else:
            out.append(("", line))
    return [e for e in out if e[1]], ""


def _ckey(category):
    """Category compare key: normalised, without a leading '01 ' number."""
    return re.sub(r"^\d+\s*[._-]?\s*", "", core.norm_text(category)).strip()


class Result:
    def __init__(self):
        self.matched = []      # songs found by exact/normalised title
        self.fuzzy = []        # (entry text, song) found through suggestions
        self.missing = []      # entry texts nothing matched

    @property
    def songs(self):
        out, seen = [], set()
        for s in self.matched + [s for _, s in self.fuzzy]:
            k = (s["song_name"], s["category"])
            if k not in seen:
                seen.add(k)
                out.append(s)
        return out


def _label(cat, name):
    return f"{cat}/{name}" if cat else name


def match(entries, songs, suggest=None):
    """Match entries to database songs: exact (category + title), then by
    normalised text, then through core.suggest for near misses. Without a
    category (or when the category is unknown) the title alone decides."""
    suggest = core.suggest if suggest is None else suggest
    exact, by_name, by_norm = {}, {}, {}
    for s in songs:
        cat = s["category"] or ""
        exact.setdefault((cat, s["song_name"]), s)
        by_name.setdefault(s["song_name"], []).append(s)
        by_norm.setdefault(core.norm_text(s["song_name"]), []).append(s)

    def pick(cands, cat):
        if not cands:
            return None
        if cat:
            ck = _ckey(cat)
            for s in cands:
                if _ckey(s["category"] or "") == ck:
                    return s
        return cands[0]

    res = Result()
    for cat, name in entries:
        s = exact.get((cat, name)) or pick(by_name.get(name), cat) \
            or pick(by_norm.get(core.norm_text(name)), cat)
        if s:
            res.matched.append(s)
            continue
        found = None
        try:
            tips = suggest(name, 3) if name else []
        except Exception:
            tips = []
        for t in tips:
            found = pick(by_name.get(t) or by_norm.get(core.norm_text(t)), cat)
            if found:
                break
        if found:
            res.fuzzy.append((_label(cat, name), found))
        else:
            res.missing.append(_label(cat, name))
    return res


def report(res, tr, limit=8):
    """Short multi-line summary for a dialog or the console."""
    lines = [tr("sl_report", m=len(res.matched), f=len(res.fuzzy), x=len(res.missing))]
    for label, s in res.fuzzy[:limit]:
        lines.append(f"  ~ {label}  ->  {s['song_name']}")
    if len(res.fuzzy) > limit:
        lines.append(f"  ... (+{len(res.fuzzy) - limit})")
    for label in res.missing[:limit]:
        lines.append(f"  x {label}")
    if len(res.missing) > limit:
        lines.append(f"  ... (+{len(res.missing) - limit})")
    return "\n".join(lines)
