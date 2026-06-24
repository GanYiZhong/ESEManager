"""
段位（Dan）工具 — 移植自 bluetaiko/SongConvertor（C#，MIT）

提供兩個功能：
- DanGenerator：輸入太鼓 wiki 段位道場頁面 URL，依段位名稱與合格條件，產出
  TaikøNauts 等可用的段位檔（dan.def + 各段位資料夾的 Dan.json）。
- DanConvertor：把 OpenTaiko 等的多曲 tja 段位檔（以 #NEXTSONG 分隔）轉成
  TaikøNauts 可用的段位檔（拆成各曲 tja + Dan.json）。

原作：bluetaiko — https://github.com/bluetaiko/SongConvertor
"""

import json
import os
import re
import shutil
import unicodedata

import requests
import urllib3
from lxml import html as lxml_html

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ============================================================ 共用：標準化工具
# 對應 C# 的 NormalizationUtils
_INVALID_FS = set('<>:"/\\|?*') | {chr(c) for c in range(0, 32)}

_ROMAN = {"Ⅰ": "I", "Ⅱ": "II", "Ⅲ": "III", "Ⅳ": "IV", "Ⅴ": "V", "Ⅵ": "VI",
          "Ⅶ": "VII", "Ⅷ": "VIII", "Ⅸ": "IX", "Ⅹ": "X", "Ⅺ": "XI", "Ⅻ": "XII"}

_TITLE_PREFIXES = ["双打"]
_TITLE_SUFFIXES = ["NEWAUDIO", "OLDAUDIO", "BEENAVERSION", "SHORTVERSION",
                   "LONGVERSION", "COVERVERSION", "TVXQVERSION", "初代"]

# 別名對照（雙向）
_ALIAS_PAIRS = [("自力本願レボリューション", "THE REVO"),
                ("スパート！", "スパートシンドローマー"),
                ("天使と悪魔", "カーマイン")]

_IGNORABLE_CATS = {"Pc", "Pd", "Ps", "Pe", "Pi", "Pf", "Po",
                   "Sm", "Sc", "Sk", "So"}


def _is_ignorable_symbol(c):
    if c in ("︎", "️", "‍"):
        return True
    return unicodedata.category(c) in _IGNORABLE_CATS


def normalize_title(s):
    """全形→半形、統一記號、去空白/標點，轉大寫。對應 NormalizeTitle。"""
    if not s or not s.strip():
        return ""
    out = []
    for c in unicodedata.normalize("NFKC", s):
        if c in _ROMAN:
            out.append(_ROMAN[c])
            continue
        w = c
        if 0xFF01 <= ord(w) <= 0xFF5E:
            w = chr(ord(w) - 0xFEE0)
        if w in "'’‘′‵ʼ＇":
            w = "'"
        if w in ("”", "“"):
            w = '"'
        if w.isspace() or unicodedata.category(w) == "Cc":
            continue
        if _is_ignorable_symbol(w):
            continue
        out.append(w)
    return "".join(out).upper()


def _fold_latin(value):
    out = []
    for c in value:
        if "A" <= c <= "Z" or "a" <= c <= "z" or "À" <= c <= "ɏ" or "Ḁ" <= c <= "ỿ":
            d = unicodedata.normalize("NFD", c)
            appended = False
            for ch in d:
                if unicodedata.category(ch) == "Mn":
                    continue
                out.append(ch)
                appended = True
            if not appended:
                out.append(c)
        else:
            out.append(c)
    return "".join(out)


def _strip_prefixes(value):
    work, changed = value, True
    while changed:
        changed = False
        for p in _TITLE_PREFIXES:
            if work.startswith(p) and len(work) > len(p) + 1:
                work = work[len(p):]
                changed = True
                break
    return work


def _strip_suffixes(value):
    work, changed = value, True
    while changed:
        changed = False
        for s in _TITLE_SUFFIXES:
            if work.endswith(s) and len(work) > len(s) + 1:
                work = work[:-len(s)]
                changed = True
                break
    return work


def _strip_after(value, keyword):
    idx = value.find(keyword)
    if idx <= 0:
        return value
    trimmed = value[:idx]
    return trimmed if len(trimmed) >= 3 else value


def _heuristic_variants(norm):
    folded = _fold_latin(norm)
    if folded != norm:
        yield folded
    no_prefix = _strip_prefixes(norm)
    if no_prefix != norm:
        yield no_prefix
    no_suffix = _strip_suffixes(norm)
    if no_suffix != norm:
        yield no_suffix
    no_both = _strip_prefixes(no_suffix)
    if no_both != norm and no_both != no_suffix:
        yield no_both
    no_feat = _strip_after(norm, "FEAT")
    if no_feat != norm:
        yield no_feat
    if folded != norm:
        folded_no_suffix = _strip_suffixes(folded)
        if folded_no_suffix != folded:
            yield folded_no_suffix


def _build_aliases():
    m = {}
    for a, b in _ALIAS_PAIRS:
        na, nb = normalize_title(a), normalize_title(b)
        if not na or not nb or na == nb:
            continue
        m.setdefault(na, set()).add(nb)
        m.setdefault(nb, set()).add(na)
    return m


_TITLE_ALIASES = _build_aliases()


def expand_title_match_keys(norm):
    """產生標題的所有比對鍵（別名 + 啟發式變體）。對應 ExpandTitleMatchKeys。"""
    if not norm or not norm.strip():
        return
    visited, queue = set(), [norm]
    while queue:
        cur = queue.pop(0)
        if cur in visited:
            continue
        visited.add(cur)
        yield cur
        for alias in _TITLE_ALIASES.get(cur, ()):
            if alias and alias not in visited:
                queue.append(alias)
        for v in _heuristic_variants(cur):
            if v and v not in visited:
                queue.append(v)


def sanitize_folder_name(name):
    if not name:
        return "Unnamed"
    return "".join("_" if c in _INVALID_FS else c for c in name).strip()


def sanitize_file_name(name):
    if not name:
        return "Unnamed"
    return "".join(c for c in name if c not in _INVALID_FS).strip()


def find_directory_fuzzy(dirs, target_name):
    """以標準化標題做模糊比對找曲目資料夾。對應 FindDirectoryFuzzy。"""
    nt = normalize_title(target_name)
    if not nt:
        return None
    target_variants = list(expand_title_match_keys(nt))
    best, best_score = None, -(2 ** 31)
    for d in dirs:
        dn = os.path.basename(d)
        dvs = list(expand_title_match_keys(normalize_title(dn)))
        score = -(2 ** 31)
        if any(tv == dv for tv in target_variants for dv in dvs):
            score = 1000
        elif any(dv.startswith(tv) for tv in target_variants for dv in dvs):
            score = 500
        elif any(dv.endswith(tv) for tv in target_variants for dv in dvs):
            score = 250
        elif any(tv in dv for tv in target_variants for dv in dvs):
            score = 100
        if score > best_score or (score == best_score and best is not None
                                  and len(dn) < len(os.path.basename(best))):
            best_score, best = score, d
    return best if best_score > -(2 ** 31) else None


# =========================================================== 共用：tja 讀檔/解碼
def _read_tja_text(path):
    with open(path, "rb") as f:
        data = f.read()
    for enc in ("cp932", "shift_jis", "utf-8-sig", "utf-8"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def _genre_from_color(color):
    color = (color or "").lower()
    table = [("#ff7028", "ナムコオリジナル"), ("#fe90d2", "アニメ"),
             ("#fe9800", "アニメ"), ("#cbcfde", "ボーカロイド™曲"),
             ("#cc8aeb", "ゲームミュージック"), ("#0acc2a", "バラエティ"),
             ("#ded523", "クラシック"), ("#ff619d", "クラシック"),
             ("#49d5eb", "ポップス"), ("#fdc000", "キッズ")]
    for key, name in table:
        if key in color:
            return name
    return "ナムコオリジナル"


def _detect_difficulty(text):
    if "裏" in text or "(裏)" in text:
        return 4
    if "おに" in text:
        return 3
    if "むずかしい" in text:
        return 2
    if "ふつう" in text:
        return 1
    if "かんたん" in text:
        return 0
    return 3


# ============================================================ DanConvertor (tja)
_EXAM_TYPE = {"p": "Great", "jp": "Great", "g": "Good", "jg": "Good",
              "b": "Miss", "jb": "Miss", "m": "Miss", "s": "Score",
              "r": "Roll", "h": "HitCount", "c": "Combo"}


def _parse_exam(content, conditions, gauge_holder):
    """解析 EXAM 行。gauge_holder 為 dict（type 'g' 時寫入 conditionGauge）。"""
    parts = content.split(",")
    if len(parts) < 3:
        return
    code = parts[0].strip().lower()
    try:
        red, gold = int(parts[1]), int(parts[2])
    except ValueError:
        return
    if code == "g" and gauge_holder is not None:
        gauge_holder["conditionGauge"] = {"red": red, "gold": gold}
        return
    name = _EXAM_TYPE.get(code)
    if not name:
        return
    for c in conditions:
        if c["type"] == name:
            c["threshold"].append({"red": red, "gold": gold})
            return
    conditions.append({"type": name, "threshold": [{"red": red, "gold": gold}]})


def _split_sections(lines, global_meta):
    """把多曲 tja 依 #NEXTSONG 拆段。對應 SplitIntoSections。"""
    sections = []
    cur = None
    last_bpm = global_meta.get("BPM", "120")
    in_song = False

    def finalize(c):
        while c["content"] and not c["content"][-1].strip():
            c["content"].pop()
        sections.append(c)

    for line in lines:
        t = line.strip()
        up = t.upper()
        if up.startswith("#NEXTSONG"):
            if cur is not None:
                finalize(cur)
            parts = t[9:].split(",")

            def g(i, dflt=""):
                return parts[i].strip() if len(parts) > i else dflt
            cur = {"title": g(0, "Untitled"), "subtitle": g(1), "genre": g(2),
                   "wave": g(3, "song.ogg"), "scoreinit": g(4), "scorediff": g(5),
                   "demostart": g(6, "0"), "bpm": last_bpm, "offset": "0",
                   "course": "Oni", "balloon": "", "content": [], "exam": []}
            in_song = True
        elif up.startswith("COURSE:"):
            val = t[7:].strip()
            if cur is not None:
                cur["course"] = val
                if in_song:
                    cur["content"].append(line)
        elif up.startswith("DEMOSTART:"):
            if cur is not None:
                cur["demostart"] = t[10:].strip()
        elif up.startswith("#BPMCHANGE"):
            last_bpm = t[10:].strip()
            if cur is not None:
                cur["bpm"] = last_bpm
                if in_song:
                    cur["content"].append(line)
        elif up.startswith("#DELAY"):
            if cur is not None and in_song:
                try:
                    delay = float(t[6:].strip())
                    cur["offset"] = f"{-delay:.3f}"
                except ValueError:
                    pass
        elif up.startswith("#BALLOON"):
            if cur is not None and in_song:
                bv = t[8:].strip()
                if bv.startswith(":"):
                    bv = bv[1:].strip()
                if bv:
                    cur["balloon"] = bv
        elif up.startswith("#MEASURE") or up.startswith("#SCROLL") or up.startswith("#BARLINE"):
            if cur is not None and in_song:
                cur["content"].append(line)
        elif cur is not None and in_song:
            if up.startswith("EXAM"):
                mm = re.match(r"^EXAM\d*:\s*(.*)$", t, re.IGNORECASE)
                if mm:
                    cur["exam"].append(mm.group(1))
                continue
            if not t and not cur["content"]:
                continue
            cur["content"].append(line)
            if up == "#END":
                in_song = False

    if cur is not None:
        finalize(cur)
    return sections


def convert_dan_tja(tja_path, output_root, simu_folder="", log=None,
                    dan_index=18, dan_mini_plate_text=None):
    """把 OpenTaiko 風格的多曲段位 tja 轉成 TaikøNauts 段位檔。對應 DanConvertorCore。"""
    def emit(msg):
        if log:
            log(msg)

    if not os.path.isfile(tja_path):
        emit(f"エラー: ファイルが見つかりません ({tja_path})")
        return None

    content = _read_tja_text(tja_path)
    lines = content.splitlines()

    global_meta = {}
    for line in lines:
        up = line.upper()
        if up.startswith("#NEXTSONG") or up.startswith("#START"):
            break
        m = re.match(r"^([A-Z0-9]+):\s*(.*)$", line, re.IGNORECASE)
        if m:
            global_meta[m.group(1).upper()] = m.group(2).strip()

    tja_stem = os.path.splitext(os.path.basename(tja_path))[0]
    safe_title = sanitize_folder_name(tja_stem)
    output_dir = os.path.join(output_root, safe_title)
    os.makedirs(output_dir, exist_ok=True)

    course_title = global_meta.get("TITLE") or tja_stem
    emit(f"変換を開始: {course_title} -> {output_dir}")

    dan = {"title": course_title, "danIndex": dan_index}
    if dan_mini_plate_text:
        dan["danMiniPlateText"] = dan_mini_plate_text
    conditions = []
    gauge_holder = {}

    # 全域 EXAM（#NEXTSONG 之前）
    for line in lines:
        t = line.strip()
        up = t.upper()
        if up.startswith("#NEXTSONG"):
            break
        if up.startswith("EXAM"):
            m = re.match(r"^EXAM\d*:\s*(.*)$", t, re.IGNORECASE)
            if m:
                _parse_exam(m.group(1), conditions, gauge_holder)

    sections = _split_sections(lines, global_meta)
    local_dir = os.path.dirname(os.path.abspath(tja_path))
    simu_files = []
    if simu_folder and os.path.isdir(simu_folder):
        for root, _, files in os.walk(simu_folder):
            for fn in files:
                simu_files.append(os.path.join(root, fn))

    final_songs = []
    for sec in sections:
        target_tja = os.path.splitext(sec["wave"])[0] + ".tja"
        out_tja = os.path.join(output_dir, target_tja)
        sb = [f"TITLE:{sec['title']}", f"SUBTITLE:{sec['subtitle']}",
              f"BPM:{sec['bpm']}", f"WAVE:{sec['wave']}",
              f"OFFSET:{sec['offset']}", f"GENRE:{sec['genre']}",
              f"COURSE:{sec['course']}",
              f"LEVEL:{global_meta.get('LEVEL', '10')}"]
        if sec["balloon"]:
            sb.append(f"BALLOON:{sec['balloon']}")
        elif "BALLOON" in global_meta:
            sb.append(f"BALLOON:{global_meta['BALLOON']}")
        if sec["scoreinit"]:
            sb.append(f"SCOREINIT:{sec['scoreinit']}")
        if sec["scorediff"]:
            sb.append(f"SCOREDIFF:{sec['scorediff']}")
        if "SCOREMODE" in global_meta:
            sb.append(f"SCOREMODE:{global_meta['SCOREMODE']}")
        sb.append("")
        sb.append("#START")
        sb.append("")
        for l in sec["content"]:
            if l.strip().upper().startswith("COURSE:"):
                continue
            sb.append(l)

        with open(out_tja, "w", encoding="utf-8") as f:
            f.write("\n".join(sb) + "\n")

        # 找音源（先 tja 同層，再模擬器 Songs 資料夾）
        wave_src = os.path.join(local_dir, sec["wave"])
        if not os.path.isfile(wave_src):
            wave_src = next((f for f in simu_files
                             if os.path.basename(f).lower() == sec["wave"].lower()), None)
        if wave_src and os.path.isfile(wave_src):
            shutil.copy2(wave_src, os.path.join(output_dir, sec["wave"]))
            emit(f"  分割譜面を生成 + 音源採取: {sec['title']}")
        else:
            emit(f"  警告: 音源が見つかりませんでした: {sec['title']}")

        # 各曲的 EXAM 也併入整體 conditions
        for ex in sec["exam"]:
            _parse_exam(ex, conditions, None)

        # Dan_Plate.png（tja 同層）
        plate_src = os.path.join(local_dir, "Dan_Plate.png")
        if os.path.isfile(plate_src) and "danPlatePath" not in dan:
            shutil.copy2(plate_src, os.path.join(output_dir, "Plate.png"))
            dan["danPlatePath"] = "Plate.png"

        final_songs.append({"path": target_tja, "difficulty": 3,
                            "genre": sec["genre"], "isHidden": False})

    dan["danSongs"] = final_songs
    if "conditionGauge" in gauge_holder:
        dan["conditionGauge"] = gauge_holder["conditionGauge"]
    dan["conditions"] = conditions

    json_path = os.path.join(output_dir, "Dan.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(dan, f, ensure_ascii=False, indent=2)
    emit(f"完了: {json_path}")
    return output_dir


# =========================================================== DanGenerator (wiki)
RANK_NAMES = ["五級", "四級", "三級", "二級", "一級", "初段", "二段", "三段",
              "四段", "五段", "六段", "七段", "八段", "九段", "十段",
              "玄人", "名人", "超人", "達人"]

EXCLUDE_KEYWORDS = ["合格条件", "お題", "お品書き", "魂ゲージ", "たたけた数",
                    "叩けた数", "総音符数", "ノーツ数", "不可", "連打数", "良",
                    "可", "コンボ", "最大コンボ数", "スコア", "動画", "計",
                    "楽曲名", "課題曲", "難易度", "難しさ", "むずかしさ", "強さ",
                    "★", "レベル", "概要", "詳細", "備考", "リンク",
                    "プレイ動画", "参照", "初出", "回数", "解放期間", "解放条件",
                    "QRコード", "QR", "公式サイト", "コメント", "アンケート",
                    "疑問", "解決所", "募集", "募集中", "？", "質問", "お願い"]


def _itext(node):
    return (node.text_content() or "").strip()


def _is_invalid_rank(txt, is_gaiden=False):
    if not txt or not txt.strip():
        return True
    if re.match(r"^\d+[\/\.]\d+", txt) or re.match(r"^[\d\/\.～\-]+$", txt):
        return True
    if re.match(r"^\d+(%|％)?(以上|以下|未満)$", txt) or re.match(r"^\d+(%|％)$", txt):
        return True
    if "以上" in txt or "以下" in txt or "未満" in txt:
        return True
    if re.match(r"^\d+$", txt):
        return True
    if len(txt) > (50 if is_gaiden else 20):
        return True
    return False


def _find_rank_in_row(row, is_gaiden=False):
    nodes = row.xpath(".//strong | .//b | .//span[contains(@style,'font-size')] | .//font")
    best = ""
    for node in nodes:
        txt = _itext(node)
        if not txt:
            continue
        if any(txt == k for k in EXCLUDE_KEYWORDS):
            continue
        if any(k in txt for k in EXCLUDE_KEYWORDS) and not any(rn in txt for rn in RANK_NAMES):
            continue
        if _is_invalid_rank(txt, is_gaiden):
            continue
        rank_like = (is_gaiden or any(rn in txt for rn in RANK_NAMES)
                     or txt.endswith("級") or txt.endswith("段")
                     or txt in ("玄人", "名人", "超人", "達人"))
        if not rank_like:
            continue
        best = txt
        if any(rn in txt for rn in RANK_NAMES):
            return txt
    return best


def _absolute_cells(row, active_row_spans):
    """以 rowspan/colspan 還原每列的「絕對欄位 → cell」對照。對應 GetAbsoluteCells。"""
    cells = row.xpath(".//td")
    result = {}
    if not cells:
        for col in range(len(active_row_spans)):
            if active_row_spans[col] > 0:
                active_row_spans[col] -= 1
        return result
    cell_idx = 0
    col = 0
    n = len(active_row_spans)
    while col < n:
        if active_row_spans[col] > 0:
            active_row_spans[col] -= 1
            col += 1
            continue
        if cell_idx >= len(cells):
            break
        cell = cells[cell_idx]
        cs = int(cell.get("colspan", "1") or "1")
        rs = int(cell.get("rowspan", "1") or "1")
        result[col] = cell
        for k in range(cs):
            if col + k < n:
                active_row_spans[col + k] = rs - 1
        cell_idx += 1
        col += cs
    return result


def _is_song_row(abs_cells):
    has_order = any(_itext(c) in ("1st", "2nd", "3rd") for c in abs_cells.values())
    if has_order:
        return True
    has_link = False
    for c in abs_cells.values():
        a = c.xpath(".//a")
        if a and len(_itext(a[0])) >= 2:
            has_link = True
            break
    has_diff = any("★" in (c.text_content() or "") for c in abs_cells.values())
    return has_link and has_diff


def _style_value(node, prop):
    style = node.get("style", "") or ""
    m = re.search(prop + r":\s*([^;]+)", style)
    return m.group(1).strip() if m else ""


def _extract_number(text):
    if not text:
        return None, False
    m = re.search(r"\d+", text.replace(",", ""))
    if m:
        return int(m.group()), False
    if "?" in text:
        return 1, True
    return None, False


def _extract_red_gold(cell, ctype):
    red = gold = None
    gold_uncertain = False
    red_nodes = cell.xpath(".//span[contains(@style,'#f23b08') or contains(@style,'color:red') or contains(@style,'color:#ff0000')]")
    gold_nodes = cell.xpath(".//span[contains(@style,'#e8d03e') or contains(@style,'color:gold') or contains(@style,'color:#ffff00')]")
    if not gold_nodes:
        gold_nodes = cell.xpath(".//strong")
    if red_nodes:
        red, _ = _extract_number(_itext(red_nodes[0]))
    if gold_nodes:
        gold, gold_uncertain = _extract_number(_itext(gold_nodes[0]))

    if red is None or gold is None:
        text = cell.text_content() or ""
        nums = re.findall(r"\d+", text.replace(",", ""))
        if len(nums) >= 2:
            if red is None:
                red = int(nums[0])
            if gold is None:
                gold = int(nums[1])
        elif len(nums) == 1:
            val = int(nums[0])
            if red is None:
                red = val
            elif gold is None:
                gold = val
        if red is None and "?" in text:
            red = 1
        if gold is None and "?" in text:
            gold, gold_uncertain = 1, True

    if ctype in ("Miss", "MissCount", "Good"):
        if red is not None and gold is not None and red < gold:
            red, gold = gold, red
    else:
        if red is not None and gold is not None and gold < red and not gold_uncertain:
            red, gold = gold, red
    return red, gold


def _parse_conditions(song_rows_info, relative_col_map, dan):
    for abs_cells, _row in song_rows_info:
        cur_song_col, best_len = -1, -1
        for col, cell in abs_cells.items():
            for link in cell.xpath(".//a"):
                t = _itext(link)
                if t and t not in EXCLUDE_KEYWORDS and len(t) > best_len:
                    best_len, cur_song_col = len(t), col
        if cur_song_col == -1:
            continue
        combo_col = diff_col = -1
        for col, cell in abs_cells.items():
            if col <= cur_song_col:
                continue
            txt = cell.text_content() or ""
            if "コンボ" in txt:
                combo_col = col
            if "★" in txt:
                diff_col = col
        if combo_col != -1:
            first_cond = combo_col + 1
        elif diff_col != -1:
            first_cond = diff_col + 1
        else:
            first_cond = cur_song_col + 3

        for col, cell in abs_cells.items():
            rel = col - first_cond
            ctype = relative_col_map.get(rel)
            if not ctype:
                continue
            inner = cell.text_content() or ""
            if not re.search(r"\d", inner) and "?" not in inner:
                continue
            red, gold = _extract_red_gold(cell, ctype)
            if red is None and gold is None:
                continue
            red, gold = red or 0, gold or 0
            if ctype == "Gauge":
                dan["conditionGauge"] = {"red": red, "gold": gold}
            else:
                cond = next((c for c in dan["conditions"] if c["type"] == ctype), None)
                if cond is None:
                    cond = {"type": ctype, "threshold": []}
                    dan["conditions"].append(cond)
                cond["threshold"].append({"red": red, "gold": gold})


def _fetch_html(source, timeout=30):
    if source.startswith("http"):
        sess = requests.Session()
        sess.headers["User-Agent"] = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                      "ESEManager DanGenerator")
        r = sess.get(source, timeout=timeout, verify=False)
        r.raise_for_status()
        r.encoding = r.apparent_encoding or r.encoding
        return r.text
    if not os.path.isfile(source):
        return None
    return _read_tja_text(source)


def generate_dan_from_wiki(input_source, output_dir, songs_folder="", filter_text="",
                           log=None, dan_index=None):
    """從太鼓 wiki 段位道場頁面產出段位檔。對應 DanGeneratorCore.GenerateAsync。"""
    def emit(msg):
        if log:
            log(msg)

    os.makedirs(output_dir, exist_ok=True)
    try:
        emit(f"URLからデータを取得中: {input_source}")
        html = _fetch_html(input_source)
    except Exception as e:
        emit(f"データ取得エラー: {e}")
        return 0
    if html is None:
        emit(f"エラー: ファイルが見つかりません ({input_source})")
        return 0

    doc = lxml_html.fromstring(html)
    nodes = doc.xpath("//h3 | //h4 | //table")
    if not nodes:
        emit("エラー: コンテンツが見つかりません。")
        return 0

    is_gaiden = ("外伝" in input_source) or ("%E5%A4%96%E4%BC%9D" in input_source)
    total_processed = 0
    missing_songs = []
    all_sets = []                       # (version_name, [ (dan, rank, rank_idx) ])
    current_set = []
    seen_idx = set()
    current_version = ""
    current_section = ""

    for node in nodes:
        tag = node.tag
        if tag == "h3":
            new_version = _itext(node)
            if (not is_gaiden and current_version and new_version != current_version
                    and current_set):
                all_sets.append((current_version, current_set))
                current_set = []
                seen_idx = set()
            current_version = new_version
            continue
        if tag == "h4":
            current_section = _itext(node)
            continue
        if tag != "table":
            continue

        table = node
        inner = table.text_content() or ""
        is2020 = "2020" in current_version
        is_candidate = ("課題候補曲リスト" in inner or "候補" in current_version
                        or "候補" in current_section)
        is_extra = (any(k in current_section for k in ("CHINA", "中国", "アジア", "Asia",
                    "海外", "台湾", "韓国", "版の課題曲"))
                    or "中国版" in inner or "アジア版" in inner or "版の課題曲" in inner)
        if is2020:
            is_extra = False
        is_changelog = (any(k in current_section for k in ("変更点", "違い", "差分"))
                        or "変更点" in inner)
        if is_candidate or is_extra or is_changelog:
            continue
        if "1st" not in inner and "魂ゲージ" not in inner and "合格条件" not in inner:
            continue

        rows = table.xpath(".//tr")
        if not rows:
            continue

        last_rank_name = ""
        active_row_spans = [0] * 30

        for i in range(len(rows)):
            row = rows[i]
            abs_cells = _absolute_cells(row, active_row_spans)
            if not abs_cells:
                continue
            cell_texts = [_itext(c) for c in abs_cells.values()]
            if not any(any(k in t for k in ("魂ゲージ", "合格条件", "可", "不可", "叩けた数"))
                       for t in cell_texts):
                continue

            detected = _find_rank_in_row(row, is_gaiden)
            if not detected and i > 0:
                detected = _find_rank_in_row(rows[i - 1], is_gaiden)
            if not detected and abs_cells:
                for cell in abs_cells.values():
                    ct = _itext(cell)
                    if not ct or len(ct) < 2:
                        continue
                    rank_like = (is_gaiden or any(rn in ct for rn in RANK_NAMES)
                                 or ct.endswith("級") or ct.endswith("段")
                                 or ct in ("玄人", "名人", "超人", "達人"))
                    if not rank_like:
                        continue
                    if any(k in ct for k in EXCLUDE_KEYWORDS):
                        continue
                    if _is_invalid_rank(ct, is_gaiden):
                        continue
                    detected = ct
                    break

            if detected:
                detected = (detected.replace("(裏)", "").replace("(おに)", "")
                            .replace("(おに裏)", "").strip())
                detected = re.sub(r"^[（(]裏[）)]$", "", detected).strip()

            if not detected or detected == last_rank_name:
                continue
            if filter_text and filter_text not in detected:
                continue

            try:
                if dan_index is not None:
                    rank_idx = dan_index
                elif is_gaiden:
                    rank_idx = 19
                else:
                    rank_idx = next((k for k, rn in enumerate(RANK_NAMES) if rn in detected), -1)
                dan = {"title": detected, "danIndex": rank_idx if rank_idx >= 0 else 0,
                       "danSongs": [], "conditionGauge": {"red": 0, "gold": 0},
                       "conditions": []}

                last_idx = current_set[-1][2] if current_set else -1
                is_new_set = False
                if not is_gaiden:
                    if rank_idx >= 0:
                        if rank_idx in seen_idx or (last_idx >= 0 and rank_idx < last_idx):
                            is_new_set = True
                    elif any(s[1] == detected for s in current_set):
                        is_new_set = True
                if is_new_set and current_set:
                    all_sets.append((current_version, current_set))
                    current_set = []
                    seen_idx = set()

                emit(f"解析中: {detected}")

                # header → 條件欄位型別
                col_map = {}
                header_song_col = -1
                for col, hc in abs_cells.items():
                    txt = _itext(hc)
                    cs = int(hc.get("colspan", "1") or "1")
                    if header_song_col == -1 and detected and detected in txt and cs >= 3:
                        header_song_col = col
                    if header_song_col == -1 and (txt in ("課題曲", "楽曲名", "曲名")
                                                  or "課題曲" in txt):
                        header_song_col = col
                    ctype = None
                    if "魂ゲージ" in txt:
                        ctype = "Gauge"
                    elif "不可" in txt:
                        ctype = "Miss"
                    elif "良" in txt:
                        ctype = "Great"
                    elif "可" in txt:
                        ctype = "Good"
                    elif "連打数" in txt:
                        ctype = "Roll"
                    elif "たたけた数" in txt or "叩けた数" in txt:
                        ctype = "HitCount"
                    elif "コンボ" in txt or "最大コンボ数" in txt:
                        ctype = "MaxCombo"
                    elif "最低スコア" in txt or "スコア" in txt:
                        ctype = "Score"
                    if ctype:
                        for k in range(cs):
                            col_map[col + k] = ctype

                if header_song_col == -1:
                    for col, cell in abs_cells.items():
                        if cell.xpath(".//a"):
                            header_song_col = col
                            break
                if header_song_col == -1:
                    header_song_col = 0

                first_cond_col = min(col_map.keys()) if col_map else -1
                relative_col_map = {}
                if first_cond_col != -1:
                    for col, v in col_map.items():
                        relative_col_map[col - first_cond_col] = v

                # 收集曲目列（最多 3 首）
                songs_added = 0
                song_rows_info = []
                for s_idx in range(1, 16):
                    if i + s_idx >= len(rows):
                        break
                    temp_spans = list(active_row_spans)
                    for skip in range(1, s_idx):
                        _absolute_cells(rows[i + skip], temp_spans)
                    s_abs = _absolute_cells(rows[i + s_idx], temp_spans)
                    if not s_abs:
                        continue
                    if any(("魂ゲージ" in (c.text_content() or "") or "合格条件" in (c.text_content() or ""))
                           for c in s_abs.values()):
                        break
                    if not _is_song_row(s_abs):
                        continue

                    best_cell, best_title = None, ""
                    for cell in s_abs.values():
                        for link in cell.xpath(".//a"):
                            t = _itext(link)
                            if not t or t in EXCLUDE_KEYWORDS or len(t) < 2:
                                continue
                            if len(t) > len(best_title):
                                best_title, best_cell = t, cell
                    if best_cell is None:
                        continue

                    safe = sanitize_file_name(best_title)
                    genre = "ナムコオリジナル"
                    color_cell = next((c for c in s_abs.values()
                                       if "background-color:#" in (c.get("style", "") or "")), None)
                    if color_cell is not None:
                        genre = _genre_from_color(_style_value(color_cell, "background-color"))

                    diff_text = rows[i + s_idx].text_content() or ""
                    diff_cell = next((c for c in s_abs.values() if "★" in (c.text_content() or "")), None)
                    if diff_cell is not None:
                        diff_text = diff_cell.text_content() or ""
                    is_ura = "(裏)" in best_title or "裏" in diff_text
                    path_title = safe.replace("(裏)", "").replace("(裏譜面)", "").strip()
                    difficulty = 4 if is_ura else _detect_difficulty(diff_text)

                    dan["danSongs"].append({"path": f"{path_title}.tja",
                                            "difficulty": difficulty, "genre": genre,
                                            "isHidden": False})
                    song_rows_info.append((s_abs, rows[i + s_idx]))
                    songs_added += 1
                    if songs_added >= 3:
                        break

                if song_rows_info:
                    _parse_conditions(song_rows_info, relative_col_map, dan)

                if dan["danSongs"]:
                    current_set.append((dan, detected, rank_idx))
                    if rank_idx >= 0:
                        seen_idx.add(rank_idx)
                    last_rank_name = detected
            except Exception as e:
                emit(f"  警告 ({detected}): {e}")

    if current_set:
        all_sets.append((current_version, current_set))

    # 輸出每個 set
    for set_idx, (version_name, dan_set) in enumerate(all_sets):
        sorted_set = dan_set if is_gaiden else sorted(dan_set, key=lambda d: d[2])
        set_base = output_dir
        dan_def_title = "外伝段位" if is_gaiden else "段位道場"

        if len(all_sets) > 1:
            folder_name = str(set_idx)
            if not is_gaiden and version_name:
                m = re.search(r"20\d{2}", version_name)
                if m:
                    folder_name = m.group()
                    dan_def_title = f"{m.group()}段位"
                else:
                    folder_name = sanitize_folder_name(version_name)
                    dan_def_title = f"{folder_name}段位"
            set_base = os.path.join(output_dir, folder_name)
        else:
            if is_gaiden:
                dan_def_title = "外伝段位"
            elif version_name:
                m = re.search(r"20\d{2}", version_name)
                dan_def_title = f"{m.group()}段位" if m else f"{version_name}段位"

        os.makedirs(set_base, exist_ok=True)
        with open(os.path.join(set_base, "dan.def"), "w", encoding="utf-8") as f:
            f.write(f"#TITLE:{dan_def_title}")

        found_order = 0
        for dan, detected, _idx in sorted_set:
            prefix = f"{found_order:02d}"
            rank_folder = os.path.join(set_base, f"{prefix} {sanitize_folder_name(detected)}")
            os.makedirs(rank_folder, exist_ok=True)

            # Dan_Plate.png（來自 Songs 資料夾）
            if songs_folder and os.path.isdir(songs_folder):
                plate_src = os.path.join(songs_folder, "Dan_Plate.png")
                if os.path.isfile(plate_src):
                    shutil.copy2(plate_src, os.path.join(rank_folder, "Plate.png"))
                    dan["danPlatePath"] = "Plate.png"

            # 從 Songs 資料夾模糊比對複製曲目
            if songs_folder and os.path.isdir(songs_folder):
                all_dirs = [songs_folder]
                for root, dirs, _ in os.walk(songs_folder):
                    for d in dirs:
                        all_dirs.append(os.path.join(root, d))
                songs_keep, remove_idx = [], []
                for s_i, s in enumerate(dan["danSongs"]):
                    raw = os.path.splitext(s["path"])[0]
                    search = raw.replace("(裏譜面)", "").replace("(裏)", "").strip()
                    found = find_directory_fuzzy(all_dirs, search)
                    if found:
                        for fn in os.listdir(found):
                            fp = os.path.join(found, fn)
                            if not os.path.isfile(fp):
                                continue
                            ext = os.path.splitext(fn)[1].lower()
                            if ext == ".tja":
                                shutil.copy2(fp, os.path.join(rank_folder, s["path"]))
                            elif ext in (".ogg", ".mp3"):
                                shutil.copy2(fp, os.path.join(rank_folder, fn))
                        songs_keep.append(s)
                    else:
                        missing_songs.append(f"[{detected}] {raw}")
                        remove_idx.append(s_i)

                if remove_idx:
                    orig_count = len(dan["danSongs"])
                    dan["danSongs"] = songs_keep
                    for cond in dan["conditions"]:
                        if len(cond["threshold"]) == orig_count:
                            for r in sorted(remove_idx, reverse=True):
                                if r < len(cond["threshold"]):
                                    cond["threshold"].pop(r)

            with open(os.path.join(rank_folder, "Dan.json"), "w", encoding="utf-8") as f:
                json.dump(dan, f, ensure_ascii=False, indent=2)
            total_processed += 1
            found_order += 1

    emit(f"生成完了: {total_processed} 件の段位を処理しました。")
    if missing_songs:
        emit("")
        emit("=========== 見つからなかった曲一覧 ===========")
        for ms in dict.fromkeys(missing_songs):
            emit(ms)
        emit("==============================================")
    return total_processed


def fetch_rank_names(input_source):
    """只取段位名稱清單（預覽用）。對應 FetchRankNamesAsync。"""
    html = _fetch_html(input_source)
    if not html:
        return []
    doc = lxml_html.fromstring(html)
    nodes = doc.xpath("//h3 | //h4 | //table")
    if not nodes:
        return []
    is_gaiden = ("外伝" in input_source) or ("%E5%A4%96%E4%BC%9D" in input_source)
    ranks = []
    current_version = current_section = ""
    for node in nodes:
        tag = node.tag
        if tag == "h3":
            current_version = _itext(node)
            continue
        if tag == "h4":
            current_section = _itext(node)
            continue
        if tag != "table":
            continue
        inner = node.text_content() or ""
        if "1st" not in inner and "魂ゲージ" not in inner and "合格条件" not in inner:
            continue
        for row in node.xpath(".//tr"):
            cells = row.xpath(".//td")
            if not cells:
                continue
            texts = [_itext(c) for c in cells]
            if not any(any(k in t for k in ("魂ゲージ", "合格条件", "可", "不可", "叩けた数"))
                       for t in texts):
                continue
            rank = _find_rank_in_row(row, is_gaiden)
            if rank:
                rank = (rank.replace("(裏)", "").replace("(おに)", "")
                        .replace("(おに裏)", "").strip())
                if rank and rank not in ranks:
                    ranks.append(rank)
    return ranks
