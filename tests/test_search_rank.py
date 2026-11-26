"""search_songs relevance ranking and tolerant matching."""

import sqlite3

import pytest

import core
from test_workers import make_song_db

NAMES = ["Zzz Love Story", "Love Story wa Totsuzen ni", "Love", "Lovely Day",
         "365 Nichi no Love Story", "Hatsune Miku no Gekishou",
         "Senbonzakura Sachiko Version", "Senbonzakura", "Sweet-Heart Beat"]
STORY = {"Zzz Love Story", "Love Story wa Totsuzen ni", "365 Nichi no Love Story"}


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "DB_PATH", str(tmp_path / "ese_songs.db"))
    monkeypatch.setattr(core, "LOCAL_DB_PATH", str(tmp_path / "ese_local.db"))
    make_song_db(core.DB_PATH, [("01 Pop/Song/Song.tja", "a" * 40)])
    conn = sqlite3.connect(core.DB_PATH)
    conn.execute("DELETE FROM song_files")
    conn.execute("DELETE FROM songs")
    for i, n in enumerate(NAMES, 1):
        conn.execute("INSERT INTO songs(id, category_id, song_name, base_path) "
                     "VALUES (?, 1, ?, ?)", (i, n, f"01 Pop/{n}"))
        conn.execute("INSERT INTO song_files(song_id, filename, file_path, file_type, size, "
                     "download_url, blob_sha) VALUES (?, ?, ?, '.tja', 0, '', ?)",
                     (i, n + ".tja", f"01 Pop/{n}/{n}.tja", "a" * 40))
    conn.commit()
    conn.close()
    core.clear_search_cache()
    return tmp_path


def names(q, cat=None):
    return [s["song_name"] for s in core.search_songs(q, cat)]


def test_exact_prefix_boundary_substring_order(db):
    r = names("love")
    assert r[0] == "Love"                                   # exact
    assert r.index("Love Story wa Totsuzen ni") < r.index("Zzz Love Story")  # prefix first
    assert r.index("Lovely Day") < r.index("Zzz Love Story")
    assert set(r) == STORY | {"Love", "Lovely Day"}


def test_word_boundary_beats_substring(db):
    assert names("ove")[0:1] != []                          # substring still matches
    assert set(names("story")) == STORY
    assert names("sen")[0].startswith("Senbonzakura")


def test_ties_keep_database_order(db):
    r = names("story")
    assert r == [n for n in NAMES if n in r]


def test_empty_keyword_keeps_order(db):
    assert names("") == NAMES


def test_multiword_any_order(db):
    assert set(names("story love")) == STORY
    assert names("miku gekishou") == ["Hatsune Miku no Gekishou"]
    assert names("miku nothing") == []


def test_punctuation_and_space_insensitive(db):
    assert names("365nichi") == ["365 Nichi no Love Story"]
    assert names("sweetheart") == ["Sweet-Heart Beat"]
    assert names("sweet heart") == ["Sweet-Heart Beat"]
    assert set(names("lovestory")) == STORY


def test_repeated_word_and_category(db):
    assert names("love  love")[0] == "Love"
    assert names("love", "rock") == []
    assert names("love", "pop")[0] == "Love"


def test_japanese_title_ranks(db):
    conn = sqlite3.connect(core.LOCAL_DB_PATH)
    conn.execute("CREATE TABLE local_songs (title TEXT, file_name TEXT, title_ja TEXT)")
    conn.executemany("INSERT INTO local_songs VALUES (?, ?, ?)", [
        ("Senbonzakura", "", "千本桜"),
        ("Senbonzakura Sachiko Version", "", "千本桜 幸子ver"),
        ("Hatsune Miku no Gekishou", "", "初音ミクの激唱"),
    ])
    conn.commit()
    conn.close()
    core.clear_search_cache()
    assert names("千本桜")[0] == "Senbonzakura"      # exact ja title
    assert "Senbonzakura Sachiko Version" in names("千本桜")
    assert names("ミク") == ["Hatsune Miku no Gekishou"]
    assert names("みくの") == ["Hatsune Miku no Gekishou"]


# ---------------------------------------------------------------- suggest()
def test_suggest_typos(db):
    assert core.suggest("senbonzakra")[0] == "Senbonzakura"
    assert core.suggest("hatune miku")[0] == "Hatsune Miku"
    assert core.suggest("lvoe story")[:1] == ["Love Story"]


def test_suggest_romaji_variants_and_run_together(db):
    assert core.suggest("hatsunee miku")[0] == "Hatsune Miku"
    assert core.suggest("sweetheartbeat")[0] == "Sweet-Heart Beat"


def test_suggest_edge_cases(db):
    assert core.suggest("") == [] and core.suggest("   ") == []
    assert core.suggest("qqqqqqqq") == []
    assert core.suggest("senbonzakra", limit=0) == []
    assert len(core.suggest("senbonzakra", limit=1)) == 1


def test_suggest_japanese(db):
    conn = sqlite3.connect(core.LOCAL_DB_PATH)
    conn.execute("CREATE TABLE local_songs (title TEXT, title_ja TEXT)")
    conn.execute("INSERT INTO local_songs VALUES ('Senbonzakura', '千本桜')")
    conn.execute("INSERT INTO local_songs VALUES ('Love Story', 'ラブストーリー')")
    conn.commit()
    conn.close()
    core.clear_search_cache()
    assert core.suggest("ラブストリー")[0] == "ラブストーリー"
    assert core.suggest("あ") == []


def test_suggest_is_fast_and_does_not_change_search(db):
    before = names("love")
    core.suggest("senbonzakra")
    import time
    t = time.perf_counter()
    core.suggest("hatune miku")
    assert time.perf_counter() - t < 0.05
    assert names("love") == before


# ------------------------------------------------------------ kana -> romaji
@pytest.mark.parametrize("kana, romaji", [
    ("せんぼんざくら", "senbonzakura"), ("きゃりー", "kyarii"), ("しゃ", "sha"),
    ("まっちゃ", "matcha"), ("あっぱれ", "appare"), ("ろーりん", "roorin"),
    ("ハツネミク", "hatsunemiku"), ("ふぁいと", "faito"), ("じゅん", "jun"),
    ("ちぇっく", "chekku"), ("ぱみゅ", "pamyu"),
])
def test_kana_to_romaji(kana, romaji):
    assert core.kana_to_romaji(kana) == romaji


def test_kana_n_apostrophe():
    assert core.kana_to_romaji("しんいち") == "shin'ichi"
    assert core.kana_to_romaji("しんいち", apostrophe=False) == "shinichi"
    assert core.kana_to_romaji("かんや") == "kan'ya"
    assert core.kana_to_romaji("せんぼん") == "senbon"


def test_kana_query_finds_romaji_titles(db):
    assert names("せんぼんざくら") == ["Senbonzakura", "Senbonzakura Sachiko Version"]
    assert names("センボンザクラ")[0] == "Senbonzakura"
    assert names("はつねみく") == ["Hatsune Miku no Gekishou"]


def test_kana_query_with_kanji_not_transliterated(db):
    assert names("千本桜") == []


def test_kana_japanese_title_hits_rank_first(db):
    conn = sqlite3.connect(core.LOCAL_DB_PATH)
    conn.execute("CREATE TABLE local_songs (title TEXT, title_ja TEXT)")
    conn.execute("INSERT INTO local_songs VALUES ('Zzz Love Story', 'せんぼんざくらの歌')")
    conn.commit()
    conn.close()
    core.clear_search_cache()
    got = names("せんぼんざくら")
    assert got[0] == "Zzz Love Story"
    assert "Senbonzakura" in got


def test_kana_suggest(db):
    assert "Senbonzakura" in core.suggest("せんぼんざくる")


def test_non_kana_results_unchanged(db):
    assert names("senbonzakura") == ["Senbonzakura", "Senbonzakura Sachiko Version"]
    assert names("love") == ["Love", "Love Story wa Totsuzen ni", "Lovely Day",
                             "Zzz Love Story", "365 Nichi no Love Story"]
    assert names("miku gekishou") == ["Hatsune Miku no Gekishou"]
    assert names("365nichi") == ["365 Nichi no Love Story"]
    assert names("love story")[0] == "Love Story wa Totsuzen ni"
