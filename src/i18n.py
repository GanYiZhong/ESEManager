"""UI strings, category names/colours and system language detection."""

import sys

CATEGORY_NAMES = {
    "01 Pop": "Pop 流行音樂",
    "02 Anime": "Anime 動漫音樂",
    "03 Vocaloid": "Vocaloid 音樂",
    "04 Children and Folk": "Children 兒童音樂",
    "05 Variety": "Variety 綜合音樂",
    "06 Classical": "Classical 古典音樂",
    "07 Game Music": "Game Music 遊戲音樂",
    "09 Namco Original": "Namco 原創音樂",
    "08 Live Festival Mode": "Live Festival 模式",
    "10 Taiko Towers": "Taiko Towers",
    "11 Dan Dojo": "Dan Dojo 段位道場",
}
CATEGORY_COLORS = {
    "01 Pop": "#1E88E5", "02 Anime": "#FB8C00", "03 Vocaloid": "#AB47BC",
    "04 Children and Folk": "#EC407A", "05 Variety": "#66BB6A",
    "06 Classical": "#C9A227", "07 Game Music": "#7E57C2",
    "09 Namco Original": "#EF5350", "08 Live Festival Mode": "#26A69A",
    "10 Taiko Towers": "#8D6E63", "11 Dan Dojo": "#78909C",
}

TR = {
    "zh_TW": {
        "title": "🎵 ESEManager", "search": "搜尋", "show_all": "顯示全部",
        "clear": "清除", "ph": "搜尋歌曲名稱 (支援日文)...", "category": "分類",
        "all_cat": "全部分類", "official": "🌐 盅鼓官方網站", "check_missing": "🔍 檢查缺漏",
        "download": "⬇ 下載選中的歌曲", "sel_all": "全選", "desel_all": "取消",
        "selected": "已選擇 {n} 首", "dir": "下載目錄", "browse": "瀏覽", "workers": "並行數",
        "lang": "語言", "c_sel": "✓", "c_song": "歌曲名稱", "c_jp": "日文標題",
        "c_cat": "分類", "c_files": "檔案數", "monitor": "下載監控", "tab_prog": "進度",
        "tab_log": "Log", "tab_fail": "失敗清單", "overall": "整體進度", "retry": "🔁 重試失敗項目",
        "ready": "就緒", "total": "共 {n} 首歌曲", "f_file": "檔案", "f_song": "歌曲",
        "f_status": "狀態", "f_pct": "進度", "f_speed": "速度", "open_dir": "📂 開啟下載資料夾",
        "st_dl": "下載中", "st_done": "完成", "st_skip": "已存在", "st_fail": "失敗",
        "st_pause": "暫停", "pause": "⏸ 暫停", "resume": "▶ 繼續", "stop": "⏹ 停止",
        "paused_label": "已暫停",
        "done_msg": "下載完成！\n成功 {d}．跳過 {s}．失敗 {f}（共 {t} 檔）",
        "db_update": "🔄 更新資料庫", "db_building": "資料庫更新中…",
        "db_done": "資料庫已更新（歌曲清單 + 日文標題）！", "db_fail": "資料庫更新失敗：{e}",
        "db_confirm": "將從 ESE 更新資料庫：\n1. 歌曲清單（blobless，只抓檔名、不下載音檔）\n2. 日文標題（抓各 .tja 解析 TITLEJA，約 10MB）\n\n是否繼續？",
        "db_no_git_q": "未偵測到 git（更新歌曲清單需要）。\n是否自動下載可攜版 git（約 50MB，免安裝、免管理員）？\n\n選「否」則需自行安裝 git：https://git-scm.com/downloads",
        "db_no_git_fail": "沒有可用的 git，已取消更新。請安裝 git 後再試。",
        "lang_busy": "工作進行中，語言將於下次啟動時套用。",
        "boxdef_btn": "📦 box.def", "boxdef_title": "box.def 編輯器",
        "boxdef_load": "讀取", "boxdef_gen": "自動生成", "boxdef_save": "儲存",
        "boxdef_batch": "為所有子資料夾生成",
        "boxdef_saved": "已儲存：{p}", "boxdef_no_dir": "資料夾不存在",
        "boxdef_no_sub": "此資料夾沒有子資料夾",
        "boxdef_batch_q": "將為 {n} 個子資料夾建立 box.def（已存在的會略過），是否繼續？",
        "boxdef_batch_done": "完成：新建 {c} 個、略過 {s} 個（已存在）",
        "boxdef_pick": "選擇顏色",
        "boxdef_fetch": "⬇ 取得 ESE 官方", "boxdef_fetch_tip": "從 ESE 倉庫下載此分類的官方 box.def",
        "boxdef_fetch_none": "ESE 找不到對應此資料夾的 box.def（依名稱/序號比對）",
        "boxdef_fetch_fail": "取得失敗：{e}", "boxdef_fetch_ok": "已載入 ESE 官方 box.def（{c}）",
        "c_bpm": "BPM", "c_easy": "簡單", "c_normal": "普通", "c_hard": "困難",
        "c_oni": "魔王", "c_ura": "裏",
        "f_filter": "篩選", "f_bpm": "BPM 區間", "f_diff": "難度", "f_level": "等級",
        "diff_all": "全部難度", "f_reset": "重設篩選", "f_any": "不限",
        "check_updates": "🆕 檢查更新",
        "upd_checking": "檢查更新中（比對本地檔案雜湊）…",
        "upd_progress": "檢查更新 {d}/{t}",
        "upd_none": "✓ 所有已下載的歌曲都是最新的",
        "upd_found": "發現 {n} 首歌有更新（{f} 個檔案），是否重新下載覆蓋？",
        "upd_no_sha": "此資料庫沒有內容雜湊，請先按「🔄 更新資料庫」再檢查更新。",
        "dan_btn": "🥋 段位工具", "dan_title": "段位工具（Dan）",
        "dan_tab_gen": "段位生成（Wiki）", "dan_tab_conv": "段位變換（tja）",
        "dan_gen_url": "太鼓 Wiki 段位頁面 URL", "dan_out": "輸出資料夾",
        "dan_songs": "Songs 資料夾", "dan_songs_opt": "Songs 資料夾（可省略）",
        "dan_gen_run": "段位生成", "dan_conv_tja": "要變換的 tja",
        "dan_conv_run": "變換執行", "dan_browse": "瀏覽",
        "dan_gen_hint": "輸入太鼓 Wiki 的段位道場頁面網址，依段位名稱與合格條件\n生成 TaikøNauts 等可用的段位檔（dan.def + 各段位 Dan.json）。",
        "dan_conv_hint": "把 OpenTaiko 等的 tja 段位（以 #NEXTSONG 分隔多曲）\n變換成 TaikøNauts 等可用的段位檔。",
        "dan_need_url": "請輸入段位頁面 URL", "dan_need_out": "請選擇輸出資料夾",
        "dan_need_tja": "請選擇要變換的 tja 檔", "dan_running": "處理中…",
        "dan_done": "完成！", "dan_fail": "失敗：{e}",
        "ydan_tab": "YataiDON 段位", "ydan_root": "YataiDON Songs 根資料夾",
        "ydan_src": "曲源 Songs 資料夾", "ydan_run": "生成 YataiDON 段位",
        "ydan_hint": "輸入太鼓 Wiki 段位道場頁面網址，生成 YataiDON 格式段位\n（各段 dan.json 寫入 <根>/11 Dan Dojo/，並把對應 tja/ogg\n自動複製到對應曲種資料夾）。",
        "ydan_need_root": "請選擇 YataiDON Songs 根資料夾",
        "credits_btn": "💗 致謝", "credits_title": "致謝 / Credits",
        "credits_body": "段位生成（DanGenerator）與段位變換（DanConvertor）功能\n移植自 bluetaiko 的 SongConvertor 專案，特此感謝原作者。\n\n原專案（MIT License）：\nhttps://github.com/bluetaiko/SongConvertor",
        "yatai_btn": "🎮 YataiDON", "yatai_title": "YataiDON box.def 生成工具",
        "yatai_folder": "Songs 資料夾", "yatai_scan": "掃描",
        "yatai_col_folder": "資料夾", "yatai_col_title": "標題",
        "yatai_col_titleja": "日文標題", "yatai_col_genre": "GENRE", "yatai_col_collection": "COLLECTION",
        "yatai_col_back": "背景色", "yatai_col_fore": "文字色",
        "yatai_gen_all": "全部生成 box.def",
        "yatai_done": "完成：已生成 {c} 個 box.def",
        "yatai_pick": "選擇顏色",
    },
    "en": {
        "title": "🎵 ESEManager", "search": "Search", "show_all": "Show All",
        "clear": "Clear", "ph": "Search songs (Japanese supported)...", "category": "Category",
        "all_cat": "All Categories", "official": "🌐 Official Site", "check_missing": "🔍 Check Missing",
        "download": "⬇ Download Selected", "sel_all": "Select All", "desel_all": "Deselect",
        "selected": "{n} selected", "dir": "Download Dir", "browse": "Browse", "workers": "Workers",
        "lang": "Language", "c_sel": "✓", "c_song": "Song", "c_jp": "Japanese",
        "c_cat": "Category", "c_files": "Files", "monitor": "Download Monitor", "tab_prog": "Progress",
        "tab_log": "Log", "tab_fail": "Failed", "overall": "Overall", "retry": "🔁 Retry Failed",
        "ready": "Ready", "total": "{n} songs", "f_file": "File", "f_song": "Song",
        "f_status": "Status", "f_pct": "Progress", "f_speed": "Speed", "open_dir": "📂 Open Folder",
        "st_dl": "downloading", "st_done": "done", "st_skip": "skipped", "st_fail": "failed",
        "done_msg": "Done!\nOK {d} · skipped {s} · failed {f} (of {t})",
        "st_pause": "paused", "pause": "⏸ Pause", "resume": "▶ Resume", "stop": "⏹ Stop",
        "paused_label": "Paused",
        "db_update": "🔄 Update DB", "db_building": "Updating database…",
        "db_done": "Database updated (song list + Japanese titles)!",
        "db_fail": "Database update failed: {e}",
        "db_confirm": "Update databases from ESE:\n1. Song list (blobless — file list only, no audio)\n2. Japanese titles (parse TITLEJA from each .tja, ~10MB)\n\nContinue?",
        "db_no_git_q": "Git not found (needed to fetch the song list).\nDownload a portable Git automatically (~50MB, no install, no admin)?\n\nChoose No to install Git yourself: https://git-scm.com/downloads",
        "db_no_git_fail": "No Git available; update cancelled. Install Git and try again.",
        "lang_busy": "A task is running; the language will apply on next launch.",
        "boxdef_btn": "📦 box.def", "boxdef_title": "box.def editor",
        "boxdef_load": "Load", "boxdef_gen": "Generate", "boxdef_save": "Save",
        "boxdef_batch": "Generate for all subfolders",
        "boxdef_saved": "Saved: {p}", "boxdef_no_dir": "Folder does not exist",
        "boxdef_no_sub": "No subfolders in this folder",
        "boxdef_batch_q": "Create box.def for {n} subfolders (existing ones are skipped). Continue?",
        "boxdef_batch_done": "Done: created {c}, skipped {s} (existing)",
        "boxdef_pick": "Pick color",
        "boxdef_fetch": "⬇ Fetch from ESE", "boxdef_fetch_tip": "Download the official box.def for this category from the ESE repo",
        "boxdef_fetch_none": "No matching ESE box.def for this folder (by name/index)",
        "boxdef_fetch_fail": "Fetch failed: {e}", "boxdef_fetch_ok": "Loaded official ESE box.def ({c})",
        "c_bpm": "BPM", "c_easy": "Easy", "c_normal": "Normal", "c_hard": "Hard",
        "c_oni": "Oni", "c_ura": "Ura",
        "f_filter": "Filter", "f_bpm": "BPM range", "f_diff": "Difficulty", "f_level": "Level",
        "diff_all": "All difficulties", "f_reset": "Reset filters", "f_any": "Any",
        "check_updates": "🆕 Check Updates",
        "upd_checking": "Checking for updates (hashing local files)…",
        "upd_progress": "Checking updates {d}/{t}",
        "upd_none": "✓ All downloaded songs are up to date",
        "upd_found": "{n} songs have updates ({f} files). Re-download and overwrite?",
        "upd_no_sha": "This database has no content hashes. Click 🔄 Update DB first, then check updates.",
        "dan_btn": "🥋 Dan Tools", "dan_title": "Dan Tools",
        "dan_tab_gen": "Generate (Wiki)", "dan_tab_conv": "Convert (tja)",
        "dan_gen_url": "Taiko Wiki Dan page URL", "dan_out": "Output folder",
        "dan_songs": "Songs folder", "dan_songs_opt": "Songs folder (optional)",
        "dan_gen_run": "Generate", "dan_conv_tja": "tja to convert",
        "dan_conv_run": "Convert", "dan_browse": "Browse",
        "dan_gen_hint": "Enter a Taiko Wiki Dan-dojo page URL to generate Dan files\nfor TaikøNauts etc. (dan.def + per-rank Dan.json) from the\nrank names and clear conditions.",
        "dan_conv_hint": "Convert an OpenTaiko-style Dan tja (multiple songs split by\n#NEXTSONG) into TaikøNauts-compatible Dan files.",
        "dan_need_url": "Please enter the Dan page URL", "dan_need_out": "Please choose an output folder",
        "dan_need_tja": "Please choose a tja file", "dan_running": "Working…",
        "dan_done": "Done!", "dan_fail": "Failed: {e}",
        "ydan_tab": "YataiDON Dan", "ydan_root": "YataiDON Songs root",
        "ydan_src": "Source Songs folder", "ydan_run": "Generate YataiDON Dan",
        "ydan_hint": "Enter a Taiko Wiki Dan-dojo page URL to generate YataiDON-format\nDan (dan.json into <root>/11 Dan Dojo/), and auto-copy the matched\ntja/ogg into the matching genre folders.",
        "ydan_need_root": "Please choose the YataiDON Songs root folder",
        "credits_btn": "💗 Credits", "credits_title": "Credits",
        "credits_body": "The Dan Generator and Dan Convertor features are ported from\nbluetaiko's SongConvertor project. Many thanks to the author.\n\nOriginal project (MIT License):\nhttps://github.com/bluetaiko/SongConvertor",
        "yatai_btn": "🎮 YataiDON", "yatai_title": "YataiDON box.def Generator",
        "yatai_folder": "Songs folder", "yatai_scan": "Scan",
        "yatai_col_folder": "Folder", "yatai_col_title": "Title",
        "yatai_col_titleja": "Title (JA)", "yatai_col_genre": "GENRE", "yatai_col_collection": "COLLECTION",
        "yatai_col_back": "Back color", "yatai_col_fore": "Fore color",
        "yatai_gen_all": "Generate All box.def",
        "yatai_done": "Done: generated {c} box.def files",
        "yatai_pick": "Pick color",
    },
    "ja": {
        "title": "🎵 ESEManager", "search": "検索", "show_all": "すべて表示",
        "clear": "クリア", "ph": "楽曲名を検索（日本語対応）...", "category": "カテゴリー",
        "all_cat": "すべて", "official": "🌐 公式サイト", "check_missing": "🔍 不足チェック",
        "download": "⬇ 選択をダウンロード", "sel_all": "全選択", "desel_all": "解除",
        "selected": "{n} 曲選択", "dir": "保存先", "browse": "参照", "workers": "並列数",
        "lang": "言語", "c_sel": "✓", "c_song": "楽曲名", "c_jp": "日本語",
        "c_cat": "カテゴリー", "c_files": "ファイル", "monitor": "ダウンロード状況", "tab_prog": "進捗",
        "tab_log": "ログ", "tab_fail": "失敗", "overall": "全体", "retry": "🔁 失敗を再試行",
        "ready": "準備完了", "total": "{n} 曲", "f_file": "ファイル", "f_song": "楽曲",
        "f_status": "状態", "f_pct": "進捗", "f_speed": "速度", "open_dir": "📂 フォルダを開く",
        "st_dl": "DL中", "st_done": "完了", "st_skip": "既存", "st_fail": "失敗",
        "done_msg": "完了！\n成功 {d}・スキップ {s}・失敗 {f}（計 {t}）",
        "st_pause": "一時停止", "pause": "⏸ 一時停止", "resume": "▶ 再開", "stop": "⏹ 停止",
        "paused_label": "一時停止中",
        "db_update": "🔄 データベース更新", "db_building": "データベース更新中…",
        "db_done": "データベースを更新しました（曲リスト＋日本語タイトル）！",
        "db_fail": "データベース更新に失敗: {e}",
        "db_confirm": "ESE からデータベースを更新します：\n1. 曲リスト（blobless・一覧のみ／音声なし）\n2. 日本語タイトル（各 .tja の TITLEJA を解析、約10MB）\n\n続行しますか？",
        "db_no_git_q": "Git が見つかりません（曲リスト取得に必要）。\nポータブル版 Git を自動ダウンロードしますか（約50MB、インストール不要・管理者不要）？\n\n「いいえ」で手動インストール：https://git-scm.com/downloads",
        "db_no_git_fail": "利用可能な Git がありません。更新を中止しました。",
        "lang_busy": "処理の実行中です。言語は次回起動時に適用されます。",
        "boxdef_btn": "📦 box.def", "boxdef_title": "box.def エディター",
        "boxdef_load": "読み込み", "boxdef_gen": "自動生成", "boxdef_save": "保存",
        "boxdef_batch": "全サブフォルダに生成",
        "boxdef_saved": "保存しました：{p}", "boxdef_no_dir": "フォルダが存在しません",
        "boxdef_no_sub": "サブフォルダがありません",
        "boxdef_batch_q": "{n} 個のサブフォルダに box.def を作成します（既存はスキップ）。続行しますか？",
        "boxdef_batch_done": "完了：作成 {c}、スキップ {s}（既存）",
        "boxdef_pick": "色を選択",
        "boxdef_fetch": "⬇ ESE から取得", "boxdef_fetch_tip": "ESE リポジトリからこの分類の公式 box.def を取得",
        "boxdef_fetch_none": "このフォルダに対応する ESE の box.def が見つかりません（名前/番号で照合）",
        "boxdef_fetch_fail": "取得に失敗: {e}", "boxdef_fetch_ok": "ESE 公式 box.def を読み込みました（{c}）",
        "c_bpm": "BPM", "c_easy": "かんたん", "c_normal": "ふつう", "c_hard": "むずかしい",
        "c_oni": "おに", "c_ura": "裏",
        "f_filter": "絞り込み", "f_bpm": "BPM 範囲", "f_diff": "難易度", "f_level": "レベル",
        "diff_all": "すべて", "f_reset": "リセット", "f_any": "指定なし",
        "check_updates": "🆕 更新チェック",
        "upd_checking": "更新をチェック中（ローカルファイルのハッシュ照合）…",
        "upd_progress": "更新チェック {d}/{t}",
        "upd_none": "✓ ダウンロード済みの曲はすべて最新です",
        "upd_found": "{n} 曲に更新があります（{f} ファイル）。再ダウンロードして上書きしますか？",
        "upd_no_sha": "このデータベースにはハッシュがありません。先に「🔄 データベース更新」を実行してください。",
        "dan_btn": "🥋 段位ツール", "dan_title": "段位ツール（Dan）",
        "dan_tab_gen": "段位生成（Wiki）", "dan_tab_conv": "段位変換（tja）",
        "dan_gen_url": "太鼓 Wiki 段位ページの URL", "dan_out": "出力フォルダ",
        "dan_songs": "Songs フォルダ", "dan_songs_opt": "Songs フォルダ（省略可）",
        "dan_gen_run": "段位生成", "dan_conv_tja": "変換する tja",
        "dan_conv_run": "変換実行", "dan_browse": "参照",
        "dan_gen_hint": "太鼓 Wiki の段位道場ページの URL を入力し、段位の名前と\n合格条件から TaikøNauts 等で使える段位ファイル（dan.def +\n各段位の Dan.json）を生成します。",
        "dan_conv_hint": "OpenTaiko 等の tja 段位（#NEXTSONG で複数曲に分割）を\nTaikøNauts 等で使える段位ファイルに変換します。",
        "dan_need_url": "段位ページの URL を入力してください", "dan_need_out": "出力フォルダを選択してください",
        "dan_need_tja": "変換する tja を選択してください", "dan_running": "処理中…",
        "dan_done": "完了！", "dan_fail": "失敗: {e}",
        "ydan_tab": "YataiDON 段位", "ydan_root": "YataiDON Songs ルート",
        "ydan_src": "曲ソース Songs フォルダ", "ydan_run": "YataiDON 段位を生成",
        "ydan_hint": "太鼓 Wiki 段位道場ページの URL を入力し、YataiDON 形式の段位を\n生成します（各段の dan.json を <ルート>/11 Dan Dojo/ に書き出し、\n対応する tja/ogg を曲種フォルダへ自動コピー）。",
        "ydan_need_root": "YataiDON Songs ルートフォルダを選択してください",
        "credits_btn": "💗 クレジット", "credits_title": "クレジット / Credits",
        "credits_body": "段位生成（DanGenerator）と段位変換（DanConvertor）機能は\nbluetaiko 氏の SongConvertor を移植したものです。作者に感謝します。\n\n元プロジェクト（MIT License）:\nhttps://github.com/bluetaiko/SongConvertor",
        "yatai_btn": "🎮 YataiDON", "yatai_title": "YataiDON box.def 生成ツール",
        "yatai_folder": "Songs フォルダ", "yatai_scan": "スキャン",
        "yatai_col_folder": "フォルダ", "yatai_col_title": "タイトル",
        "yatai_col_titleja": "日本語タイトル", "yatai_col_genre": "GENRE", "yatai_col_collection": "COLLECTION",
        "yatai_col_back": "背景色", "yatai_col_fore": "文字色",
        "yatai_gen_all": "すべて box.def を生成",
        "yatai_done": "完了：{c} 個の box.def を生成しました",
        "yatai_pick": "色を選択",
    },
}


# Strings for first-run guidance, download/DB status and worker logs.
TR["zh_TW"].update({
    "empty_hint": "尚未下載歌曲資料庫。程式啟動時會詢問是否下載預先建好的資料庫；"
                  "也可以按上方「🔄 更新資料庫」自行從 ESE 建立。",
    "no_selection": "請先勾選要下載的歌曲。",
    "dl_busy": "下載進行中，請等目前的下載完成或先停止。",
    "dl_confirm_many": "即將下載 {n} 首歌曲（{f} 個檔案），可能需要很長時間與大量磁碟空間。\n是否繼續？",
    "log_dl_start": "——— 開始下載 {n} 個檔案 ———",
    "log_dl_stopping": "——— 已要求停止，等待收尾… ———",
    "log_dl_done": "——— 完成：成功 {d}．跳過 {s}．失敗 {f} ———",
    "stopped_msg": "下載已停止。\n成功 {d}．跳過 {s}．失敗或取消 {f}（共 {t} 檔）\n"
                   "未完成的檔案已列在「失敗清單」，可一鍵重試。",
    "missing_none": "✓ 沒有缺漏",
    "missing_found": "發現 {n} 首缺漏（{f} 檔），是否下載？",
    "db_reloading": "正在載入資料庫…",
    "dbv_title": "資料庫更新",
    "dbv_found": "發現新版本資料庫\n目前：{cur}\n最新：{new}\n是否更新？",
    "dbv_first": "尚未有歌曲資料庫。\n要下載最新的預先建好資料庫（{v}，約 5 MB）嗎？",
    "dbv_none": "無",
    "dbv_ok": "✓ 資料庫更新成功",
    "quit_busy": "下載或資料庫更新仍在進行中。\n確定要結束嗎？未完成的檔案不會被保留。",
    "log_cancelled": "已取消",
    "log_short": "檔案不完整（{got}/{want} bytes）",
    "log_sha_mismatch": "校驗碼不符（檔案內容與資料庫記錄不同）",
    "log_fail": "✗ 失敗：{f} — {e}",
    "log_db_dl": "下載資料庫 {n} …",
    "log_db_bad": "{n} 不是有效的資料庫",
    "log_db_sha": "{n} 校驗碼不符，請稍後再試",
    "boxdef_fetching": "⏳ 取得中…",
    "yatai_info": "YataiDON 支援：#TITLE / #TITLEJA / #GENRE / #COLLECTION（DAN DIFFICULTY "
                  "RECOMMENDED FAVORITE RECENT）/ #BACKCOLOR / #FORECOLOR。"
                  "#BACKCOLOR＝盒子顏色，#FORECOLOR＝文字外框色。曲種顏色取自 ESE 官方配色；"
                  "特殊資料夾（COLLECTION）顏色留空＝使用內建圖示。",
    "official": "🌐 太鼓官方網站",
})

TR["en"].update({
    "empty_hint": "No song database yet. At startup the app offers to download the prebuilt "
                  "database; you can also build it from ESE with \"🔄 Update DB\" above.",
    "no_selection": "Select the songs to download first.",
    "dl_busy": "A download is already running. Wait for it to finish or stop it first.",
    "dl_confirm_many": "About to download {n} songs ({f} files). This can take a long time "
                       "and a lot of disk space.\nContinue?",
    "log_dl_start": "——— Downloading {n} files ———",
    "log_dl_stopping": "——— Stop requested, finishing current files… ———",
    "log_dl_done": "——— Done: {d} downloaded · {s} skipped · {f} failed ———",
    "stopped_msg": "Download stopped.\n{d} downloaded · {s} skipped · {f} failed or cancelled "
                   "({t} files)\nUnfinished files are in the Failed tab for a one-click retry.",
    "missing_none": "✓ Nothing missing",
    "missing_found": "{n} songs are missing ({f} files). Download them?",
    "db_reloading": "Loading database…",
    "dbv_title": "Database update",
    "dbv_found": "A newer database is available.\nCurrent: {cur}\nLatest: {new}\nUpdate now?",
    "dbv_first": "There is no song database yet.\nDownload the latest prebuilt database "
                 "({v}, about 5 MB)?",
    "dbv_none": "none",
    "dbv_ok": "✓ Database updated",
    "quit_busy": "A download or database update is still running.\nQuit anyway? "
                 "Unfinished files will not be kept.",
    "log_cancelled": "cancelled",
    "log_short": "incomplete file ({got}/{want} bytes)",
    "log_sha_mismatch": "checksum mismatch (content differs from the database record)",
    "log_fail": "✗ Failed: {f} — {e}",
    "log_db_dl": "Downloading database {n} …",
    "log_db_bad": "{n} is not a valid database",
    "log_db_sha": "{n} checksum mismatch; please try again later",
    "boxdef_fetching": "⏳ Fetching…",
    "yatai_info": "YataiDON supports #TITLE / #TITLEJA / #GENRE / #COLLECTION (DAN DIFFICULTY "
                  "RECOMMENDED FAVORITE RECENT) / #BACKCOLOR / #FORECOLOR. #BACKCOLOR = box "
                  "color, #FORECOLOR = title outline. Genre colors come from ESE's official "
                  "palette; COLLECTION folders are left blank to use built-in art.",
})

TR["ja"].update({
    "empty_hint": "曲データベースがまだありません。起動時にビルド済みデータベースのダウンロードを"
                  "確認します。上の「🔄 データベース更新」で ESE から作成することもできます。",
    "no_selection": "先にダウンロードする曲を選択してください。",
    "dl_busy": "ダウンロード中です。完了するか停止してから実行してください。",
    "dl_confirm_many": "{n} 曲（{f} ファイル）をダウンロードします。時間とディスク容量が"
                       "多く必要になる場合があります。\n続行しますか？",
    "log_dl_start": "——— {n} ファイルのダウンロードを開始 ———",
    "log_dl_stopping": "——— 停止を要求しました。処理中のファイルを終了しています… ———",
    "log_dl_done": "——— 完了：成功 {d}・スキップ {s}・失敗 {f} ———",
    "stopped_msg": "ダウンロードを停止しました。\n成功 {d}・スキップ {s}・失敗/取消 {f}"
                   "（全 {t} ファイル）\n未完了のファイルは「失敗リスト」から再試行できます。",
    "missing_none": "✓ 不足はありません",
    "missing_found": "{n} 曲（{f} ファイル）が不足しています。ダウンロードしますか？",
    "db_reloading": "データベースを読み込み中…",
    "dbv_title": "データベース更新",
    "dbv_found": "新しいデータベースがあります。\n現在：{cur}\n最新：{new}\n更新しますか？",
    "dbv_first": "曲データベースがまだありません。\n最新のビルド済みデータベース（{v}、約 5 MB）を"
                 "ダウンロードしますか？",
    "dbv_none": "なし",
    "dbv_ok": "✓ データベースを更新しました",
    "quit_busy": "ダウンロードまたはデータベース更新が実行中です。\n終了しますか？"
                 "未完了のファイルは保存されません。",
    "log_cancelled": "キャンセルしました",
    "log_short": "ファイルが不完全です（{got}/{want} bytes）",
    "log_sha_mismatch": "チェックサムが一致しません（内容がデータベースの記録と異なります）",
    "log_fail": "✗ 失敗：{f} — {e}",
    "log_db_dl": "データベース {n} をダウンロード中 …",
    "log_db_bad": "{n} は有効なデータベースではありません",
    "log_db_sha": "{n} のチェックサムが一致しません。しばらくしてから再試行してください",
    "boxdef_fetching": "⏳ 取得中…",
    "yatai_info": "YataiDON 対応：#TITLE / #TITLEJA / #GENRE / #COLLECTION（DAN DIFFICULTY "
                  "RECOMMENDED FAVORITE RECENT）/ #BACKCOLOR / #FORECOLOR。#BACKCOLOR＝ボックスの色、"
                  "#FORECOLOR＝タイトルの縁取り色。ジャンル色は ESE 公式の配色です。"
                  "COLLECTION フォルダは色を空欄にすると内蔵の画像を使います。",
})


def detect_system_lang():
    """偵測系統語言 → 'zh_TW' / 'ja' / 'en'（預設 en）。"""
    code = ""
    try:
        if sys.platform == "win32":
            import ctypes
            buf = ctypes.create_unicode_buffer(85)
            if ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, 85):
                code = buf.value          # 例如 "zh-TW" / "ja-JP" / "en-US"
    except Exception:
        pass
    if not code:
        try:
            import locale
            code = locale.getdefaultlocale()[0] or ""
        except Exception:
            code = ""
    code = code.replace("_", "-").lower()
    if code.startswith("ja"):
        return "ja"
    if code.startswith("zh"):
        return "zh_TW"
    return "en"


# --- main window layout
TR["zh_TW"].update({
    "mw_menu_file": "檔案(&F)",
    "mw_menu_tools": "工具(&T)",
    "mw_menu_help": "說明(&H)",
    "mw_act_open_dir": "開啟下載資料夾",
    "mw_act_quit": "結束",
    "mw_status_db": "資料庫版本：{v}",
    "mw_status_songs": "歌曲總數：{n}",
})

TR["en"].update({
    "mw_menu_file": "&File",
    "mw_menu_tools": "&Tools",
    "mw_menu_help": "&Help",
    "mw_act_open_dir": "Open Download Folder",
    "mw_act_quit": "Quit",
    "mw_status_db": "Database version: {v}",
    "mw_status_songs": "Songs: {n}",
})

TR["ja"].update({
    "mw_menu_file": "ファイル(&F)",
    "mw_menu_tools": "ツール(&T)",
    "mw_menu_help": "ヘルプ(&H)",
    "mw_act_open_dir": "ダウンロードフォルダーを開く",
    "mw_act_quit": "終了",
    "mw_status_db": "データベース版：{v}",
    "mw_status_songs": "楽曲数：{n}",
})

# --- theme
TR["zh_TW"].update({
    "th_label": "主題",
    "th_auto": "跟隨系統",
    "th_light": "淺色",
    "th_dark": "深色",
    "th_tip": "外觀：淺色／深色；跟隨系統會依作業系統設定自動切換",
})
TR["en"].update({
    "th_label": "Theme",
    "th_auto": "Auto (system)",
    "th_light": "Light",
    "th_dark": "Dark",
    "th_tip": "Appearance: light or dark; Auto follows the OS setting and switches with it",
})
TR["ja"].update({
    "th_label": "テーマ",
    "th_auto": "自動（システム）",
    "th_light": "ライト",
    "th_dark": "ダーク",
    "th_tip": "外観：ライト／ダーク。自動は OS の設定に合わせて切り替わります",
})
