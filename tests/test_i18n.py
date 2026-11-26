"""Consistency checks for the UI strings in src/i18n.py."""
import re

import pytest

from i18n import TR

LANGS = ("zh_TW", "en", "ja")
PLACEHOLDER = re.compile(r"\{(\w+)\}")

# Characters that exist ONLY in Simplified Chinese (each has a distinct
# Traditional form, noted alongside).  Deliberately excludes ambiguous ones such
# as 后 (also 皇后) and 复 (also a surname / 複 variant).
SIMPLIFIED_ONLY = (
    "这们个设显载档数选择时间网络错误关闭开应资库"  # 這們個設顯載檔數選擇時間網絡錯誤關閉開應資庫
    "级页单录项过为无与请获还将览态线连测试经储压缩发现删当动体码验证务点击双键栏隐总难区标题称简状进"
    # 級頁單錄項過為無與請獲還將覽態線連測試經儲壓縮發現刪當動體碼驗證務點擊雙鍵欄隱總難區標題稱簡狀進
)
MAINLAND_TERMS = ("默認", "信息", "設置", "軟件", "服務器", "鼠標", "視頻", "用戶", "登錄",
                  "程序員", "激活", "缺省", "下載目錄", "文件夾", "代理服務")


def test_all_languages_have_same_keys():
    base = set(TR["zh_TW"])
    for lang in LANGS:
        assert set(TR[lang]) == base, (lang, base ^ set(TR[lang]))


def test_placeholders_match_across_languages():
    bad = []
    for key, zh in TR["zh_TW"].items():
        sets = {lang: frozenset(PLACEHOLDER.findall(TR[lang][key])) for lang in LANGS}
        if len(set(sets.values())) != 1:
            bad.append((key, {k: sorted(v) for k, v in sets.items()}))
    assert not bad, bad


def test_no_empty_values():
    for lang in LANGS:
        for key, val in TR[lang].items():
            assert isinstance(val, str) and val.strip(), (lang, key)


def test_simplified_denylist_is_sane():
    # every denylisted char must not be a CJK char also used in Traditional text
    assert len(set(SIMPLIFIED_ONLY)) == len(SIMPLIFIED_ONLY)
    for ch in "後間數選擇網絡錯誤":
        assert ch not in SIMPLIFIED_ONLY


def test_zh_tw_has_no_simplified_characters():
    bad = [(k, ch) for k, v in TR["zh_TW"].items() for ch in v if ch in SIMPLIFIED_ONLY]
    assert not bad, bad


def test_zh_tw_has_no_mainland_terms():
    bad = [(k, t) for k, v in TR["zh_TW"].items() for t in MAINLAND_TERMS if t in v]
    assert not bad, bad


@pytest.mark.parametrize("lang", ("en",))
def test_en_has_no_fullwidth_punctuation(lang):
    bad = [k for k, v in TR[lang].items() if re.search(r"[，。：；！？（）、]", v)]
    assert not bad, bad


def test_terminology_is_consistent():
    zh, en, ja = TR["zh_TW"], TR["en"], TR["ja"]
    assert all("下載目錄" not in v for v in zh.values())
    assert all("favorite" not in v.lower() for v in en.values())  # we use "favourites"
    assert all("Update DB" not in v for v in en.values())
    assert all("カテゴリ" not in v.replace("カテゴリー", "") for v in ja.values())
    assert all("フォルダ" not in v.replace("フォルダー", "") for v in ja.values())
    assert all("楽曲" not in v for v in ja.values())
