"""Search-box filter syntax: bpm:>180 oni:>=8 cat:vocaloid fav new dl:no ..."""

import pytest

import core
from i18n import TR
from test_cli import app, make_db              # noqa: F401  (fixture re-export)
from test_gui import window                    # noqa: F401  (fixture re-export)


def song(name, cat, nfiles=1):
    return {"song_name": name, "category": cat,
            "files": [{"file_path": f"{cat}/{name}/{i}", "filename": str(i)}
                      for i in range(nfiles)]}


SONGS = [
    song("Senbonzakura", "03 Vocaloid", 3),
    song("Love Story", "01 Pop"),
    song("Tell Your World", "03 Vocaloid"),
    song("Gurenge", "02 Anime", 2),
    song("New World", "07 Game Music"),
    song("No Meta", "01 Pop"),
]
META = {
    "Senbonzakura": {"bpm": "154", "level_easy": 2, "level_normal": 4, "level_hard": 6,
                     "level_oni": 8, "level_ura": 10},
    "Love Story": {"bpm": "120-130", "level_easy": 1, "level_normal": 3, "level_hard": 5,
                   "level_oni": 7, "level_ura": None},
    "Tell Your World": {"bpm": "200", "level_easy": 3, "level_normal": 5,
                        "level_hard": 7, "level_oni": 9, "level_ura": None},
    "Gurenge": {"bpm": "", "level_easy": 3, "level_normal": 5, "level_hard": 7,
                "level_oni": 10, "level_ura": None},
    "New World": {"bpm": "180.5", "level_oni": 8},
}
JP = {"Senbonzakura": "千本桜"}
FAVS = {core.song_key(SONGS[0]), core.song_key(SONGS[3])}
MARKS = {core.song_key(SONGS[1]): "new", core.song_key(SONGS[3]): "updated"}
DL = {core.song_key(SONGS[0]): core.DL_COMPLETE, core.song_key(SONGS[1]): core.DL_PARTIAL,
      core.song_key(SONGS[2]): core.DL_NONE}


def run(text, songs=SONGS):
    q = core.parse_query(text)
    res = core.apply_query(q, songs, META, JP, DL, FAVS, MARKS, set())
    return [s["song_name"] for s in res]


# ---- parser
@pytest.mark.parametrize("text", [
    "", "miku", "  miku  ", "re:zero", "Re:Start", "http://x", "a-b", "100%", "ミク　ルカ",
    "new", "fav", "new world", "fav new", "love story", "key:", ":x", "-", "- x", "x:y:z",
    "bpm", "oni", "unknown:>5", "ＬＯＶＥ",
])
def test_plain_queries_are_untouched(text):
    q = core.parse_query(text)
    assert not q.structured and not q.active and not q.invalid
    assert q.text == text.strip()


def test_grammar_example():
    q = core.parse_query('miku bpm:>180 oni:>=8 cat:vocaloid fav new dl:no ura:any')
    assert q.text == "miku" and not q.invalid
    assert q.conds == [
        (False, "num", "bpm", ("cmp", ">", 180.0)),
        (False, "num", "level_oni", ("cmp", ">=", 8.0)),
        (False, "cat", "vocaloid", None),
        (False, "flag", "fav", None), (False, "flag", "new", None),
        (False, "dl", core.DL_NONE, None),
        (False, "num", "level_ura", ("any",))]


def test_fullwidth_and_case_and_aliases():
    q = core.parse_query("ＢＰＭ：＞１８０ ONI:>=８ Category:Pop Favourite")
    assert q.text == "Favourite" and not q.invalid
    assert [c[1:3] for c in q.conds] == [("num", "bpm"), ("num", "level_oni"),
                                         ("cat", "pop")]


@pytest.mark.parametrize("val,spec", [
    (">180", ("cmp", ">", 180.0)), (">=8", ("cmp", ">=", 8.0)), ("<5", ("cmp", "<", 5.0)),
    ("<=5", ("cmp", "<=", 5.0)), ("=7", ("cmp", "=", 7.0)), ("7", ("cmp", "=", 7.0)),
    ("==7", ("cmp", "=", 7.0)), ("=>7", ("cmp", ">=", 7.0)), ("120.5", ("cmp", "=", 120.5)),
    ("5..8", ("range", 5.0, 8.0)), ("8..5", ("range", 5.0, 8.0)),
    ("..8", ("range", None, 8.0)), ("5..", ("range", 5.0, None)),
    ("any", ("any",)), ("NONE", ("none",)),
])
def test_numeric_values(val, spec):
    q = core.parse_query("oni:" + val)
    assert q.conds == [(False, "num", "level_oni", spec)] and not q.invalid


@pytest.mark.parametrize("tok", ["bpm:", "bpm:abc", "bpm:>", "oni:..", "oni:5..x",
                                 "files:any", "dl:maybe", "fav:sometimes", "cat:", "oni:>>5"])
def test_invalid_tokens_are_reported_and_ignored(tok):
    q = core.parse_query("miku " + tok)
    assert q.invalid == [tok] and q.text == "miku" and not q.conds
    assert run(tok) == [s["song_name"] for s in SONGS]


def test_unknown_key_stays_a_word():
    q = core.parse_query("foo:bar oni:>=9")
    assert q.text == "foo:bar" and len(q.conds) == 1 and not q.invalid


def test_quotes_and_negation_parse():
    q = core.parse_query('"love story" -"new world" -miku cat:"game music"')
    assert q.phrases == ["love story"] and q.text == "love story"
    assert q.neg_words == ["new world", "miku"]
    assert q.conds == [(False, "cat", "game music", None)]
    q = core.parse_query('"unterminated phrase')
    assert q.phrases == ["unterminated phrase"]
    q = core.parse_query('""')
    assert not q.phrases


def test_bare_flags_need_company():
    assert core.parse_query("new world").conds == []
    assert core.parse_query("fav").text == "fav"
    assert core.parse_query("new oni:>5").conds[0] == (False, "flag", "new", None)
    assert core.parse_query("+fav").conds == [(False, "flag", "fav", None)]
    assert core.parse_query("-fav").conds == [(True, "flag", "fav", None)]
    assert core.parse_query("fav:no").conds == [(True, "flag", "fav", None)]
    assert core.parse_query("-fav:no").conds == [(False, "flag", "fav", None)]


# ---- evaluator
def test_numeric_filters():
    assert run("bpm:>150") == ["Senbonzakura", "Tell Your World", "New World"]
    assert run("bpm:120") == ["Love Story"]                    # first number of a range
    assert run("bpm:100..160") == ["Senbonzakura", "Love Story"]
    assert run("oni:>=8") == ["Senbonzakura", "Tell Your World", "Gurenge", "New World"]
    assert run("oni:>=8 bpm:>150") == ["Senbonzakura", "Tell Your World", "New World"]
    assert run("hard:5..6") == ["Senbonzakura", "Love Story"]
    assert run("ura:any") == ["Senbonzakura"]
    assert run("ura:none") == [s["song_name"] for s in SONGS[1:]]   # incl. no metadata
    assert run("files:>1") == ["Senbonzakura", "Gurenge"]
    assert run("files:=3") == ["Senbonzakura"]
    assert run("bpm:any") == ["Senbonzakura", "Love Story", "Tell Your World", "New World"]
    assert run("-oni:>=8") == ["Love Story", "No Meta"]


def test_category_filters():
    assert run("cat:vocaloid") == ["Senbonzakura", "Tell Your World"]
    assert run("cat:03") == ["Senbonzakura", "Tell Your World"]
    assert run("cat:VOCA") == ["Senbonzakura", "Tell Your World"]
    assert run("cat:game") == ["New World"]
    assert run("cat:流行") == ["Love Story", "No Meta"]           # localized display name
    assert run("cat:ocal") == []                                 # prefix, not substring
    assert run("cat:anime cat:pop") == ["Love Story", "Gurenge", "No Meta"]   # OR
    assert run("-cat:vocaloid") == ["Love Story", "Gurenge", "New World", "No Meta"]
    assert run("cat:pop -cat:anime") == ["Love Story", "No Meta"]
    assert run('cat:"game music"') == ["New World"]
    assert run("category:Game Music") == ["New World"]         # key:value then word


def test_flags():
    assert run("+fav") == ["Senbonzakura", "Gurenge"]
    assert run("-fav") == ["Love Story", "Tell Your World", "New World", "No Meta"]
    assert run("fav oni:>0") == ["Senbonzakura", "Gurenge"]
    assert run("+new") == ["Love Story", "Gurenge"]
    assert run("+upd") == ["Gurenge"]
    assert run("fav -new oni:>0") == ["Senbonzakura"]
    assert run("fav:no oni:>0") == ["Love Story", "Tell Your World", "New World"]
    q = core.parse_query("+upd")
    keys = {core.song_key(SONGS[0])}
    res = core.apply_query(q, SONGS, update_keys=keys)
    assert [s["song_name"] for s in res] == ["Senbonzakura"]       # outdated download


def test_download_filter():
    assert run("dl:yes") == ["Senbonzakura"]
    assert run("dl:partial") == ["Love Story"]
    assert run("dl:no") == ["Tell Your World", "Gurenge", "New World", "No Meta"]
    assert run("-dl:yes") == ["Love Story", "Tell Your World", "Gurenge", "New World", "No Meta"]
    assert run("dl:no cat:vocaloid") == ["Tell Your World"]


def test_phrases_and_negated_words():
    assert run('"love story"') == ["Love Story"]
    assert run('"story love"') == []
    assert run('"lovestory"') == ["Love Story"]                # punctuation/space-insensitive
    assert run('"千本"') == ["Senbonzakura"]                     # Japanese title
    assert run("-world oni:>0") == ["Senbonzakura", "Love Story", "Gurenge", "No Meta"][:3]
    assert run('-"new world" oni:>5') == ["Senbonzakura", "Love Story", "Tell Your World",
                                           "Gurenge"]
    assert run("-千本 oni:>0") == ["Love Story", "Tell Your World", "Gurenge", "New World"]


def test_empty_results_and_contradictions():
    assert run("bpm:>300") == []
    assert run("oni:>8 oni:<8") == []
    assert run("fav -fav oni:>0") == []


def test_inactive_query_returns_copy():
    q = core.parse_query("miku")
    res = core.apply_query(q, SONGS)
    assert res == SONGS and res is not SONGS


# ---- end to end
def test_search_query_plain_matches_search_songs(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "DB_PATH", str(tmp_path / "ese_songs.db"))
    monkeypatch.setattr(core, "LOCAL_DB_PATH", str(tmp_path / "ese_local.db"))
    make_db(tmp_path / "ese_songs.db")
    for text in ("Song", "song 01", "ＳＯＮＧ", "nothing", "", "new", "re:zero"):
        songs, q = core.search_query(text)
        assert songs == core.search_songs(text) and not q.structured
    songs, q = core.search_query("song files:>1")
    assert [s["song_name"] for s in songs] == ["Song"]
    assert core.search_query("song files:>2")[0] == []
    assert core.search_query("song -cat:pop")[0] == []
    assert core.search_query("song -fav")[0] != []


def test_cli_search_syntax(app):
    tmp, run_cli = app
    make_db(tmp / "ese_songs.db")
    rc, out = run_cli("search", "Song files:>1")
    assert rc == 0 and "Song" in out
    rc, out = run_cli("search", "Song files:>5")
    assert rc == 2
    rc, out = run_cli("search", "Song bpm:wat")
    assert rc == 0 and "bpm:wat" in out
    rc, out = run_cli("search", "Song dl:no")
    assert rc == 0
    (tmp / "Downloads" / "01 Pop" / "Song").mkdir(parents=True)
    for name in ("Song.tja", "Song.ogg"):
        (tmp / "Downloads" / "01 Pop" / "Song" / name).write_text("x")
    rc, out = run_cli("search", "Song dl:no")
    assert rc == 2
    rc, out = run_cli("search", "Song dl:yes")
    assert rc == 0


# ---- GUI
def test_window_applies_query_with_popup_filters(window):
    window.meta_map = META
    window.jp_map = JP
    window.all_songs = list(SONGS)
    window.song_model.set_favourites(FAVS)
    window._query = core.parse_query("oni:>=8 -cat:anime")
    window.apply_filters()
    assert window.song_model.rowCount() == 3                # Senbonzakura, Tell, New World
    window.fav_only.setChecked(True)                        # popup filter coexists
    window.apply_filters()
    assert window.song_model.rowCount() == 1


def test_window_invalid_token_marks_box_and_message(window, monkeypatch):
    monkeypatch.setattr(window, "_run_search", lambda kw, cat: None)
    window.search_edit.setText("miku bpm:abc")
    window.do_search()
    assert window.search_edit.property("badToken") is True
    assert window._query.invalid == ["bpm:abc"] and window._query.text == "miku"
    window.search_edit.setText("miku")
    window.do_search()
    assert window.search_edit.property("badToken") is False
    assert "bpm:" in window.search_edit.toolTip()


def test_i18n_keys_in_all_languages():
    for key in ("q_syntax_help", "q_invalid"):
        for lang in ("zh_TW", "en", "ja"):
            assert key in TR[lang]
    assert "{items}" in TR["en"]["q_invalid"]
