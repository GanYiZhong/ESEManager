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
        "title": "ESEManager", "search": "搜尋", "show_all": "顯示全部",
        "clear": "清除", "ph": "搜尋歌曲名稱，支援日文（Ctrl+F）", "category": "分類",
        "all_cat": "全部分類", "official": "聯絡我們", "check_missing": "檢查缺漏",
        "download": "下載選中的歌曲", "sel_all": "全選", "desel_all": "全不選",
        "selected": "已選擇 {n} 首", "dir": "下載目錄", "browse": "瀏覽", "workers": "並行數",
        "lang": "語言", "c_sel": "✓", "c_song": "歌曲名稱", "c_jp": "日文標題",
        "c_cat": "分類", "c_files": "檔案數", "monitor": "下載監控", "tab_prog": "進度",
        "tab_log": "Log", "tab_fail": "失敗清單", "overall": "整體進度", "retry": "重試失敗項目",
        "ready": "就緒", "total": "共 {n} 首歌曲", "f_file": "檔案", "f_song": "歌曲",
        "f_status": "狀態", "f_pct": "進度", "f_speed": "速度", "open_dir": "開啟下載資料夾",
        "st_dl": "下載中", "st_done": "完成", "st_skip": "已存在", "st_fail": "失敗",
        "st_pause": "暫停", "pause": "暫停", "resume": "繼續", "stop": "停止",
        "paused_label": "已暫停",
        "done_msg": "下載完成！\n成功 {d}．跳過 {s}．失敗 {f}（共 {t} 檔）",
        "db_update": "更新資料庫", "db_building": "資料庫更新中…",
        "db_fail": "資料庫更新失敗：{e}",
        
        "lang_busy": "工作進行中，語言將於下次啟動時套用。",
        
        
        "c_bpm": "BPM", "c_easy": "簡單", "c_normal": "普通", "c_hard": "困難",
        "c_oni": "魔王", "c_ura": "裏",
        "f_filter": "篩選", "f_bpm": "BPM 區間", "f_diff": "難度", "f_level": "等級",
        "c_dl": "已下載", "dl_complete": "已下載（檔案齊全）", "dl_partial": "部分下載（缺少檔案）", "dl_none": "未下載", "f_dl": "下載狀態", "dl_all": "全部", "dl_missing": "未下載／不完整", "dl_have": "已下載",
        "diff_all": "全部難度", "f_reset": "重設篩選", "f_any": "不限",
        "check_updates": "檢查更新",
        "upd_checking": "檢查更新中（比對本地檔案雜湊）…",
        "upd_progress": "檢查更新 {d}/{t}",
        "upd_none": "所有已下載的歌曲都是最新的",
        "upd_found": "發現 {n} 首歌有更新（{f} 個檔案），是否重新下載覆蓋？",
        "upd_no_sha": "此資料庫沒有內容雜湊，請先按「更新資料庫」再檢查更新。",
        
        
        
        
        
        
    },
    "en": {
        "title": "ESEManager", "search": "Search", "show_all": "Show All",
        "clear": "Clear", "ph": "Search songs, Japanese supported (Ctrl+F)", "category": "Category",
        "all_cat": "All Categories", "official": "Contact us", "check_missing": "Check Missing",
        "download": "Download Selected", "sel_all": "Select All", "desel_all": "Select None",
        "selected": "{n} selected", "dir": "Download Dir", "browse": "Browse", "workers": "Workers",
        "lang": "Language", "c_sel": "✓", "c_song": "Song", "c_jp": "Japanese",
        "c_cat": "Category", "c_files": "Files", "monitor": "Download Monitor", "tab_prog": "Progress",
        "tab_log": "Log", "tab_fail": "Failed", "overall": "Overall", "retry": "Retry Failed",
        "ready": "Ready", "total": "{n} songs", "f_file": "File", "f_song": "Song",
        "f_status": "Status", "f_pct": "Progress", "f_speed": "Speed", "open_dir": "Open Folder",
        "st_dl": "downloading", "st_done": "done", "st_skip": "skipped", "st_fail": "failed",
        "done_msg": "Done!\nOK {d} · skipped {s} · failed {f} (of {t})",
        "st_pause": "paused", "pause": "Pause", "resume": "Resume", "stop": "Stop",
        "paused_label": "Paused",
        "db_update": "Update DB", "db_building": "Updating database…",
        "db_fail": "Database update failed: {e}",
        
        "lang_busy": "A task is running; the language will apply on next launch.",
        
        
        "c_bpm": "BPM", "c_easy": "Easy", "c_normal": "Normal", "c_hard": "Hard",
        "c_oni": "Oni", "c_ura": "Ura",
        "f_filter": "Filter", "f_bpm": "BPM range", "f_diff": "Difficulty", "f_level": "Level",
        "c_dl": "Have", "dl_complete": "Downloaded (all files present)", "dl_partial": "Partly downloaded (files missing)", "dl_none": "Not downloaded", "f_dl": "Downloaded", "dl_all": "All", "dl_missing": "Not downloaded / incomplete", "dl_have": "Downloaded",
        "diff_all": "All difficulties", "f_reset": "Reset filters", "f_any": "Any",
        "check_updates": "Check Updates",
        "upd_checking": "Checking for updates (hashing local files)…",
        "upd_progress": "Checking updates {d}/{t}",
        "upd_none": "All downloaded songs are up to date",
        "upd_found": "{n} songs have updates ({f} files). Re-download and overwrite?",
        "upd_no_sha": "This database has no content hashes. Click Update DB first, then check updates.",
        
        
        
        
        
        
    },
    "ja": {
        "title": "ESEManager", "search": "検索", "show_all": "すべて表示",
        "clear": "クリア", "ph": "楽曲名を検索・日本語対応（Ctrl+F）", "category": "カテゴリー",
        "all_cat": "すべて", "official": "お問い合わせ", "check_missing": "不足チェック",
        "download": "選択をダウンロード", "sel_all": "全選択", "desel_all": "選択解除",
        "selected": "{n} 曲選択", "dir": "保存先", "browse": "参照", "workers": "並列数",
        "lang": "言語", "c_sel": "✓", "c_song": "楽曲名", "c_jp": "日本語",
        "c_cat": "カテゴリー", "c_files": "ファイル", "monitor": "ダウンロード状況", "tab_prog": "進捗",
        "tab_log": "ログ", "tab_fail": "失敗", "overall": "全体", "retry": "失敗を再試行",
        "ready": "準備完了", "total": "{n} 曲", "f_file": "ファイル", "f_song": "楽曲",
        "f_status": "状態", "f_pct": "進捗", "f_speed": "速度", "open_dir": "フォルダを開く",
        "st_dl": "DL中", "st_done": "完了", "st_skip": "既存", "st_fail": "失敗",
        "done_msg": "完了！\n成功 {d}・スキップ {s}・失敗 {f}（計 {t}）",
        "st_pause": "一時停止", "pause": "一時停止", "resume": "再開", "stop": "停止",
        "paused_label": "一時停止中",
        "db_update": "データベース更新", "db_building": "データベース更新中…",
        "db_fail": "データベース更新に失敗: {e}",
        
        "lang_busy": "処理の実行中です。言語は次回起動時に適用されます。",
        
        
        "c_bpm": "BPM", "c_easy": "かんたん", "c_normal": "ふつう", "c_hard": "むずかしい",
        "c_oni": "おに", "c_ura": "裏",
        "f_filter": "絞り込み", "f_bpm": "BPM 範囲", "f_diff": "難易度", "f_level": "レベル",
        "c_dl": "取得", "dl_complete": "ダウンロード済み（全ファイルあり）", "dl_partial": "一部のみ（ファイル不足）", "dl_none": "未ダウンロード", "f_dl": "ダウンロード状況", "dl_all": "すべて", "dl_missing": "未取得／不完全", "dl_have": "取得済み",
        "diff_all": "すべて", "f_reset": "リセット", "f_any": "指定なし",
        "check_updates": "更新チェック",
        "upd_checking": "更新をチェック中（ローカルファイルのハッシュ照合）…",
        "upd_progress": "更新チェック {d}/{t}",
        "upd_none": "ダウンロード済みの曲はすべて最新です",
        "upd_found": "{n} 曲に更新があります（{f} ファイル）。再ダウンロードして上書きしますか？",
        "upd_no_sha": "このデータベースにはハッシュがありません。先に「データベース更新」を実行してください。",
        
        
        
        
        
        
    },
}


# Strings for first-run guidance, download/DB status and worker logs.
TR["zh_TW"].update({
    "palette_ph": "輸入命令或歌曲名稱…", "palette_song": "歌曲",
    "palette_none": "沒有符合的項目",
})
TR["zh_TW"].update({
    "empty_hint": "按下方按鈕下載預先建好的歌曲資料庫，完成後就能搜尋與下載。",
    "welcome_title": "歡迎使用 ESEManager",
    "welcome_download": "下載歌曲資料庫",
    "welcome_change_dir": "變更…",
    "welcome_dir": "歌曲會下載到：{d}",
    "no_selection": "請先勾選要下載的歌曲。",
    "dl_busy": "下載進行中，請等目前的下載完成或先停止。",
    "dl_queued": "已加入佇列：{n} 首歌曲（{f} 個檔案）",
    "dl_queued_none": "所選檔案都已在佇列中",
    "dl_confirm_many": "即將下載 {n} 首歌曲（{f} 個檔案），可能需要很長時間與大量磁碟空間。\n是否繼續？",
    "log_dl_start": "——— 開始下載 {n} 個檔案 ———",
    "log_dl_stopping": "——— 已要求停止，等待收尾… ———",
    "log_dl_done": "——— 完成：成功 {d}．跳過 {s}．失敗 {f} ———",
    "dl_open_folder": "開啟下載資料夾",
    "dl_retry_failed": "重試失敗項目",
    "stopped_msg": "下載已停止。\n成功 {d}．跳過 {s}．失敗或取消 {f}（共 {t} 檔）\n"
                   "未完成的檔案已列在「失敗清單」，可一鍵重試。",
    "missing_none": "沒有缺漏",
    "missing_found": "發現 {n} 首缺漏（{f} 檔），是否下載？",
    "db_reloading": "正在載入資料庫…",
    "dbv_title": "資料庫更新",
    "dbv_found": "發現新版本資料庫\n目前：{cur}\n最新：{new}\n是否更新？",
    "dbv_first": "尚未有歌曲資料庫。\n要下載最新的預先建好資料庫（{v}）嗎？",
    "dbv_none": "無",
    "dbv_ok": "資料庫更新成功",
    "quit_busy": "下載或資料庫更新仍在進行中。\n確定要結束嗎？未完成的檔案不會被保留。",
    "log_cancelled": "已取消",
    "log_short": "檔案不完整（{got}/{want} bytes）",
    "log_sha_mismatch": "校驗碼不符（檔案內容與資料庫記錄不同）",
    "log_mirror": "改用 {host} 下載",
    "src_label": "下載來源",
    "src_tip": "歌曲檔從哪裡下載。選的來源失敗時，會自動改用另一個。",
    "src_auto": "自動（最快）",
    "src_ese": "ESE 官方（ese.tjadataba.se）",
    "src_mirror": "鏡像（git.taiko.ac）",
    "src_custom": "自訂：{u}",
    "log_fail": "失敗：{f} — {e}",
    "log_db_dl": "下載資料庫 {n} …",
    "log_db_bad": "{n} 不是有效的資料庫",
    "log_db_sha": "{n} 校驗碼不符，請稍後再試",
})

TR["en"].update({
    "palette_ph": "Type a command or song name...", "palette_song": "Song",
    "palette_none": "No matches",
})
TR["en"].update({
    "empty_hint": "Download the prebuilt song database with the button below, then search and download charts.",
    "welcome_title": "Welcome to ESEManager",
    "welcome_download": "Download song database",
    "welcome_change_dir": "Change...",
    "welcome_dir": "Songs will be saved to: {d}",
    "no_selection": "Select the songs to download first.",
    "dl_busy": "A download is already running. Wait for it to finish or stop it first.",
    "dl_queued": "Added {n} songs ({f} files) to the queue",
    "dl_queued_none": "Those files are already in the queue",
    "dl_confirm_many": "About to download {n} songs ({f} files). This can take a long time "
                       "and a lot of disk space.\nContinue?",
    "log_dl_start": "——— Downloading {n} files ———",
    "log_dl_stopping": "——— Stop requested, finishing current files… ———",
    "log_dl_done": "——— Done: {d} downloaded · {s} skipped · {f} failed ———",
    "dl_open_folder": "Open download folder",
    "dl_retry_failed": "Retry failed",
    "stopped_msg": "Download stopped.\n{d} downloaded · {s} skipped · {f} failed or cancelled "
                   "({t} files)\nUnfinished files are in the Failed tab for a one-click retry.",
    "missing_none": "Nothing missing",
    "missing_found": "{n} songs are missing ({f} files). Download them?",
    "db_reloading": "Loading database…",
    "dbv_title": "Database update",
    "dbv_found": "A newer database is available.\nCurrent: {cur}\nLatest: {new}\nUpdate now?",
    "dbv_first": "There is no song database yet.\nDownload the latest prebuilt database "
                 "({v})?",
    "dbv_none": "none",
    "dbv_ok": "Database updated",
    "quit_busy": "A download or database update is still running.\nQuit anyway? "
                 "Unfinished files will not be kept.",
    "log_cancelled": "cancelled",
    "log_short": "incomplete file ({got}/{want} bytes)",
    "log_sha_mismatch": "checksum mismatch (content differs from the database record)",
    "log_mirror": "Switched to {host} for downloads",
    "src_label": "Download source",
    "src_tip": "Where song files are downloaded from. If it fails, the other one is used automatically.",
    "src_auto": "Auto (fastest)",
    "src_ese": "ESE official (ese.tjadataba.se)",
    "src_mirror": "Mirror (git.taiko.ac)",
    "src_custom": "Custom: {u}",
    "log_fail": "Failed: {f} — {e}",
    "log_db_dl": "Downloading database {n} …",
    "log_db_bad": "{n} is not a valid database",
    "log_db_sha": "{n} checksum mismatch; please try again later",
})

TR["ja"].update({
    "palette_ph": "コマンドまたは曲名を入力…", "palette_song": "曲",
    "palette_none": "一致する項目がありません",
})
TR["ja"].update({
    "empty_hint": "下のボタンでビルド済みの曲データベースをダウンロードすると、検索とダウンロードができます。",
    "welcome_title": "ESEManager へようこそ",
    "welcome_download": "曲データベースをダウンロード",
    "welcome_change_dir": "変更…",
    "welcome_dir": "保存先：{d}",
    "no_selection": "先にダウンロードする曲を選択してください。",
    "dl_busy": "ダウンロード中です。完了するか停止してから実行してください。",
    "dl_queued": "{n} 曲（{f} ファイル）をキューに追加しました",
    "dl_queued_none": "選択したファイルはすべてキューに入っています",
    "dl_confirm_many": "{n} 曲（{f} ファイル）をダウンロードします。時間とディスク容量が"
                       "多く必要になる場合があります。\n続行しますか？",
    "log_dl_start": "——— {n} ファイルのダウンロードを開始 ———",
    "log_dl_stopping": "——— 停止を要求しました。処理中のファイルを終了しています… ———",
    "log_dl_done": "——— 完了：成功 {d}・スキップ {s}・失敗 {f} ———",
    "dl_open_folder": "ダウンロードフォルダを開く",
    "dl_retry_failed": "失敗を再試行",
    "stopped_msg": "ダウンロードを停止しました。\n成功 {d}・スキップ {s}・失敗/取消 {f}"
                   "（全 {t} ファイル）\n未完了のファイルは「失敗リスト」から再試行できます。",
    "missing_none": "不足はありません",
    "missing_found": "{n} 曲（{f} ファイル）が不足しています。ダウンロードしますか？",
    "db_reloading": "データベースを読み込み中…",
    "dbv_title": "データベース更新",
    "dbv_found": "新しいデータベースがあります。\n現在：{cur}\n最新：{new}\n更新しますか？",
    "dbv_first": "曲データベースがまだありません。\n最新のビルド済みデータベース（{v}）を"
                 "ダウンロードしますか？",
    "dbv_none": "なし",
    "dbv_ok": "データベースを更新しました",
    "quit_busy": "ダウンロードまたはデータベース更新が実行中です。\n終了しますか？"
                 "未完了のファイルは保存されません。",
    "log_cancelled": "キャンセルしました",
    "log_short": "ファイルが不完全です（{got}/{want} bytes）",
    "log_sha_mismatch": "チェックサムが一致しません（内容がデータベースの記録と異なります）",
    "log_mirror": "{host} からのダウンロードに切り替えました",
    "src_label": "ダウンロード元",
    "src_tip": "曲ファイルのダウンロード元。失敗した場合は自動的にもう一方を使います。",
    "src_auto": "自動（最速）",
    "src_ese": "ESE 公式（ese.tjadataba.se）",
    "src_mirror": "ミラー（git.taiko.ac）",
    "src_custom": "カスタム：{u}",
    "log_fail": "失敗：{f} — {e}",
    "log_db_dl": "データベース {n} をダウンロード中 …",
    "log_db_bad": "{n} は有効なデータベースではありません",
    "log_db_sha": "{n} のチェックサムが一致しません。しばらくしてから再試行してください",
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
    "dir_missing": "下載資料夾不存在：\n{d}\n\n請到「檔案 → 設定」選擇資料夾。",
    "mw_menu_file": "檔案(&F)",
    "mw_menu_tools": "工具(&T)",
    "mw_menu_help": "說明(&H)",
    "mw_act_open_dir": "開啟下載資料夾",
    "mw_act_quit": "結束",
    "mw_status_db": "資料庫版本：{v}",
    "mw_status_songs": "歌曲總數：{n}",
})

TR["en"].update({
    "dir_missing": "The download folder does not exist:\n{d}\n\nChoose one in File → Settings.",
    "mw_menu_file": "&File",
    "mw_menu_tools": "&Tools",
    "mw_menu_help": "&Help",
    "mw_act_open_dir": "Open Download Folder",
    "mw_act_quit": "Quit",
    "mw_status_db": "Database version: {v}",
    "mw_status_songs": "Songs: {n}",
})

TR["ja"].update({
    "dir_missing": "ダウンロードフォルダーが存在しません：\n{d}\n\n「ファイル → 設定」で選択してください。",
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



# --- compact layout
TR["zh_TW"].update({
    "mw_settings": "設定…",
    "mw_settings_title": "設定",
    "mw_close": "關閉",
})
TR["en"].update({
    "mw_settings": "Settings…",
    "mw_settings_title": "Settings",
    "mw_close": "Close",
})
TR["ja"].update({
    "mw_settings": "設定…",
    "mw_settings_title": "設定",
    "mw_close": "閉じる",
})


# --- rolling release: in-app update notice
TR["zh_TW"].update({
    "mw_app_update": "有新版本 {v}，按此下載",
    "mw_app_update_tip": "目前版本：{cur}\n最新版本：{v}\n開啟 GitHub 下載頁",
})
TR["en"].update({
    "mw_app_update": "New version {v} available",
    "mw_app_update_tip": "Current: {cur}\nLatest: {v}\nOpens the GitHub download page",
})
TR["ja"].update({
    "mw_app_update": "新しいバージョン {v} があります",
    "mw_app_update_tip": "現在：{cur}\n最新：{v}\nGitHub のダウンロードページを開きます",
})


# --- database update from GitHub Pages
TR["zh_TW"].update({
    "db_update_tip": "從 GitHub 下載最新的歌曲資料庫（每 6 小時自動從 ESE 重建）",
    "db_checking": "檢查資料庫版本…",
    "db_latest": "資料庫已是最新版本（{v}）。",
    "db_offline": "無法連線到資料庫伺服器，請檢查網路後再試。",
})
TR["en"].update({
    "db_update_tip": "Download the latest song database from GitHub (rebuilt from ESE every 6 hours)",
    "db_checking": "Checking database version…",
    "db_latest": "The database is already up to date ({v}).",
    "db_offline": "Could not reach the database server. Check your connection and try again.",
})
TR["ja"].update({
    "db_update_tip": "GitHub から最新の曲データベースをダウンロード（ESE から 6 時間ごとに自動再構築）",
    "db_checking": "データベースのバージョンを確認中…",
    "db_latest": "データベースは最新です（{v}）。",
    "db_offline": "データベースサーバーに接続できません。ネットワークを確認して再試行してください。",
})


# --- ESE-Version-Sorting download
TR["zh_TW"].update({
    "vsort_action": "下載版本分類（ESE-Version-Sorting）",
    "vsort_tip": "下載 YataiDON 用的版本分類資料夾到下載目錄（約 21 MB，整包一次下載）",
    "vsort_done": "已下載到下載目錄的 ESE-Version-Sorting 資料夾（{c}）。",
    "vsort_latest": "ESE-Version-Sorting 已是最新版本（{c}）。",
    "vsort_fail": "下載 ESE-Version-Sorting 失敗：{e}",
})
TR["en"].update({
    "vsort_action": "Download version sorting (ESE-Version-Sorting)",
    "vsort_tip": "Download the YataiDON version-sorting folders into the download folder (about 21 MB, one archive)",
    "vsort_done": "Installed ESE-Version-Sorting into the download folder ({c}).",
    "vsort_latest": "ESE-Version-Sorting is already up to date ({c}).",
    "vsort_fail": "Downloading ESE-Version-Sorting failed: {e}",
})
TR["ja"].update({
    "vsort_action": "バージョン別フォルダをダウンロード（ESE-Version-Sorting）",
    "vsort_tip": "YataiDON 用のバージョン別フォルダをダウンロード先に取得します（約 21 MB、アーカイブ 1 回）",
    "vsort_done": "ダウンロード先に ESE-Version-Sorting をインストールしました（{c}）。",
    "vsort_latest": "ESE-Version-Sorting は最新です（{c}）。",
    "vsort_fail": "ESE-Version-Sorting のダウンロードに失敗しました：{e}",
})


# --- command-line mode
TR["zh_TW"].update({
    "cli_found": "將下載 {n} 首（{f} 個檔案）",
    "cli_missing": "缺少 {n} 首（{f} 個檔案）",
    "cli_updated": "{n} 首有更新（{f} 個檔案）",
    "cli_no_db": "尚未有歌曲資料庫，請先執行：ESEManager-cli update-db",
    "cli_app_dir": "程式資料夾",
    "cli_db_local": "本機資料庫版本",
    "cli_db_remote": "最新資料庫版本",
    "cli_download_what": "請指定關鍵字、--category，或用 --all 下載全部。",
    "cli_continue": "要繼續嗎？",
    "cli_next": "下一步：{cmd}",
})
TR["en"].update({
    "cli_found": "{n} songs ({f} files) to download",
    "cli_missing": "{n} songs ({f} files) missing",
    "cli_updated": "{n} songs ({f} files) changed upstream",
    "cli_no_db": "No song database yet. Run: ESEManager-cli update-db",
    "cli_app_dir": "App folder",
    "cli_db_local": "Local database",
    "cli_db_remote": "Latest database",
    "cli_download_what": "Give a keyword, --category, or --all to download everything.",
    "cli_continue": "Continue?",
    "cli_next": "Next: {cmd}",
})
TR["ja"].update({
    "cli_found": "{n} 曲（{f} ファイル）をダウンロードします",
    "cli_missing": "{n} 曲（{f} ファイル）が不足しています",
    "cli_updated": "{n} 曲（{f} ファイル）に更新があります",
    "cli_no_db": "曲データベースがありません。先に実行してください：ESEManager-cli update-db",
    "cli_app_dir": "アプリのフォルダー",
    "cli_db_local": "ローカルのデータベース",
    "cli_db_remote": "最新のデータベース",
    "cli_download_what": "キーワード、--category、またはすべてなら --all を指定してください。",
    "cli_continue": "続行しますか？",
    "cli_next": "次のコマンド：{cmd}",
})


# --- usability: shortcuts, result views, language restart, damaged database
TR["zh_TW"].update({
    "download_tip": "下載勾選的歌曲（Ctrl+D）",
    "shortcuts": "快捷鍵",
    "shortcuts_text": "Ctrl+K　命令面板\nCtrl+F　搜尋\nEsc　清除搜尋\nCtrl+D　下載勾選的歌曲\nF5　重新搜尋／重新整理\nCtrl+A　（表格中）勾選全部列出的歌曲\n↓　（搜尋框中）移到表格\n"
                      "Ctrl+,　設定\nSpace　勾選／取消勾選目前的列\n雙擊列　已下載則開啟資料夾，否則勾選\n右鍵　歌曲選單",
    "view_missing": "目前只顯示缺漏的 {n} 首歌曲。",
    "view_updates": "目前只顯示有更新的 {n} 首歌曲。",
    "view_back": "顯示全部",
    "missing_checking": "正在檢查缺漏…",
    "lang_restart": "需要重新啟動程式才能套用新語言。\n現在重新啟動嗎？（選「否」則下次啟動時套用）",
    "db_corrupt": "歌曲資料庫無法讀取，可能已損毀。\n請按「更新資料庫」重新下載。\n\n{e}",
})
TR["en"].update({
    "download_tip": "Download the checked songs (Ctrl+D)",
    "shortcuts": "Keyboard Shortcuts",
    "shortcuts_text": "Ctrl+K  Command palette\nCtrl+F  Search\nEsc  Clear search\nCtrl+D  Download checked songs\nF5  Re-run the search / refresh\nCtrl+A  (in the table) Check all listed songs\nDown arrow  (in the search box) Move into the table\n"
                      "Ctrl+,  Settings\nSpace  Check / uncheck the current row\nDouble-click a row  Open its folder if downloaded, else check\nRight-click  Song menu",
    "view_missing": "Showing only the {n} songs with missing files.",
    "view_updates": "Showing only the {n} songs with upstream changes.",
    "view_back": "Show All",
    "missing_checking": "Checking for missing files…",
    "lang_restart": "The app must restart to use the new language.\nRestart now? "
                    "(No = apply on next launch)",
    "db_corrupt": "The song database cannot be read and may be damaged.\n"
                  "Click \"Update DB\" to download it again.\n\n{e}",
})
TR["ja"].update({
    "download_tip": "チェックした曲をダウンロード（Ctrl+D）",
    "shortcuts": "キーボードショートカット",
    "shortcuts_text": "Ctrl+K　コマンドパレット\nCtrl+F　検索\nEsc　検索をクリア\nCtrl+D　チェックした曲をダウンロード\nF5　再検索／更新\nCtrl+A　（表内）表示中の曲をすべてチェック\n↓　（検索ボックス内）表へ移動\n"
                      "Ctrl+,　設定\nSpace　現在の行のチェック切り替え\n行をダブルクリック　ダウンロード済みならフォルダを開く、未ならチェック\n右クリック　曲メニュー",
    "view_missing": "不足している {n} 曲のみ表示しています。",
    "view_updates": "更新のある {n} 曲のみ表示しています。",
    "view_back": "すべて表示",
    "missing_checking": "不足ファイルを確認中…",
    "lang_restart": "新しい言語を適用するには再起動が必要です。\n今すぐ再起動しますか？"
                    "（「いいえ」で次回起動時に適用）",
    "db_corrupt": "曲データベースを読み込めません。破損している可能性があります。\n"
                  "「データベース更新」で再ダウンロードしてください。\n\n{e}",
})


# --- in-app update (download and overwrite)
TR["zh_TW"].update({
    "mw_app_update_tip2": "目前版本：{cur}\n最新版本：{v}\n按此自動下載並更新",
    "upd_app_title": "更新 ESEManager",
    "upd_app_confirm": "要從 {cur} 更新到 {v} 嗎？\n\n會從 GitHub 下載新版並直接覆蓋程式，完成後自動重新啟動。"
                       "\n設定、資料庫和下載的歌曲都會保留。",
    "upd_app_downloading": "下載更新中… {p}%",
    "upd_app_busy": "請先等目前的下載或資料庫更新完成。",
    "upd_app_done": "已更新到 {v}，程式即將重新啟動。",
    "upd_app_fail": "自動更新失敗，程式沒有被更改：\n{e}\n\n要開啟下載頁手動更新嗎？",
})
TR["en"].update({
    "mw_app_update_tip2": "Current: {cur}\nLatest: {v}\nClick to download and install it",
    "upd_app_title": "Update ESEManager",
    "upd_app_confirm": "Update from {cur} to {v}?\n\nThe new version is downloaded from GitHub and "
                       "installed over this one, then the app restarts.\nSettings, databases and "
                       "downloaded songs are kept.",
    "upd_app_downloading": "Downloading update… {p}%",
    "upd_app_busy": "Wait for the current download or database update to finish first.",
    "upd_app_done": "Updated to {v}. The app will now restart.",
    "upd_app_fail": "The update failed and nothing was changed:\n{e}\n\n"
                    "Open the download page to update manually?",
})
TR["ja"].update({
    "mw_app_update_tip2": "現在：{cur}\n最新：{v}\nクリックで自動ダウンロード・更新",
    "upd_app_title": "ESEManager の更新",
    "upd_app_confirm": "{cur} から {v} に更新しますか？\n\nGitHub から新しいバージョンをダウンロードして"
                       "上書きし、完了後に再起動します。\n設定・データベース・ダウンロードした曲はそのまま残ります。",
    "upd_app_downloading": "更新をダウンロード中… {p}%",
    "upd_app_busy": "現在のダウンロードまたはデータベース更新が終わるまでお待ちください。",
    "upd_app_done": "{v} に更新しました。アプリを再起動します。",
    "upd_app_fail": "更新に失敗しました。アプリは変更されていません：\n{e}\n\n"
                    "ダウンロードページを開いて手動で更新しますか？",
})
TR["zh_TW"]["mw_app_update"] = "有新版本 {v}，按此更新"
TR["en"]["mw_app_update"] = "New version {v}: click to update"
TR["ja"]["mw_app_update"] = "新しいバージョン {v}：クリックで更新"
TR["zh_TW"].update({
    "upd_app_latest": "已是最新版本（{v}）",
    "upd_app_available": "有新版本：{cur} → {v}",
    "upd_app_manual": "從原始碼執行時無法自動更新，請到 {url} 下載。",
    "upd_app_fail_cli": "更新失敗，程式沒有被更改：{e}",
    "upd_app_done_cli": "已更新到 {v}，請重新啟動 ESEManager。",
    "upd_app_scheduled_cli": "已下載 {v}；這個指令結束後幾秒內會自動換上新版。",
    "upd_app_failed_restart": "上次的自動更新沒有完成，目前仍是舊版：\n{e}\n\n可以再按一次更新，或到 GitHub 手動下載。",
})
TR["en"].update({
    "upd_app_latest": "Already up to date ({v})",
    "upd_app_available": "New version: {cur} → {v}",
    "upd_app_manual": "Running from source cannot update itself; download it from {url}",
    "upd_app_fail_cli": "Update failed; nothing was changed: {e}",
    "upd_app_done_cli": "Updated to {v}. Restart ESEManager.",
    "upd_app_scheduled_cli": "Downloaded {v}; it is installed a few seconds after this command exits.",
    "upd_app_failed_restart": "The last update did not finish; this is still the old version:\n{e}\n\n"
                              "Try the update again, or download it from GitHub.",
})
TR["ja"].update({
    "upd_app_latest": "最新バージョンです（{v}）",
    "upd_app_available": "新しいバージョン：{cur} → {v}",
    "upd_app_manual": "ソースから実行している場合は自動更新できません。{url} からダウンロードしてください。",
    "upd_app_fail_cli": "更新に失敗しました。変更はありません：{e}",
    "upd_app_done_cli": "{v} に更新しました。ESEManager を再起動してください。",
    "upd_app_scheduled_cli": "{v} をダウンロードしました。このコマンドの終了後、数秒で新しいバージョンに置き換わります。",
    "upd_app_failed_restart": "前回の更新が完了しませんでした。現在も古いバージョンです：\n{e}\n\n"
                              "もう一度更新するか、GitHub から手動でダウンロードしてください。",
})


# --- usability: context menu, empty states
TR["zh_TW"].update({
    "ctx_toggle": "勾選／取消勾選", "ctx_download": "下載這首歌曲",
    "ctx_open_folder": "開啟歌曲資料夾", "ctx_copy_title": "複製歌名",
    "no_results": "找不到符合的歌曲。\n請調整關鍵字、分類或篩選條件。",
    "no_songs": "目前沒有歌曲可顯示。",
})
TR["en"].update({
    "ctx_toggle": "Check / uncheck", "ctx_download": "Download this song",
    "ctx_open_folder": "Open song folder", "ctx_copy_title": "Copy title",
    "no_results": "No songs match.\nTry a different keyword, category or filter.",
    "no_songs": "There are no songs to show.",
})
TR["ja"].update({
    "ctx_toggle": "チェックの切り替え", "ctx_download": "この曲をダウンロード",
    "ctx_open_folder": "曲のフォルダを開く", "ctx_copy_title": "曲名をコピー",
    "no_results": "一致する曲がありません。\nキーワード、カテゴリ、フィルターを変えてください。",
    "no_songs": "表示する曲がありません。",
})


# --- friendly network / disk error messages (core.friendly_error)
TR["zh_TW"].update({
    "err_offline": "無法連線，請檢查網路連線（或 DNS）後再試一次。",
    "err_timeout": "連線逾時，伺服器沒有回應，請稍後再試。",
    "err_tls": "安全連線（TLS／憑證）失敗，請檢查系統時間、代理或防火牆設定。",
    "err_not_found": "伺服器上找不到這個檔案（404）。",
    "err_rate_limit": "伺服器暫時拒絕請求（請求過於頻繁），請稍後再試。",
    "err_server": "伺服器發生問題，請稍後再試。",
    "err_disk_full": "磁碟空間不足，請釋出空間後再試。",
    "err_permission": "沒有權限寫入這個資料夾，請換一個下載位置。",
    "err_checksum": "檔案校驗碼不符，下載內容可能已損毀，請稍後再試。",
    "err_tried": "（已嘗試：{hosts}）",
})
TR["en"].update({
    "err_offline": "Can't connect. Check your internet connection (or DNS) and try again.",
    "err_timeout": "The connection timed out; the server did not respond. Try again later.",
    "err_tls": "Secure connection (TLS/certificate) failed. Check the system clock, proxy or firewall.",
    "err_not_found": "The file was not found on the server (404).",
    "err_rate_limit": "The server is refusing requests for now (rate limited). Try again later.",
    "err_server": "The server is having problems. Try again later.",
    "err_disk_full": "Not enough disk space. Free some space and try again.",
    "err_permission": "No permission to write to this folder. Choose another download location.",
    "err_checksum": "Checksum mismatch; the download may be damaged. Try again later.",
    "err_tried": " (tried: {hosts})",
})
TR["ja"].update({
    "err_offline": "接続できません。インターネット接続（または DNS）を確認して再試行してください。",
    "err_timeout": "接続がタイムアウトしました。サーバーが応答しません。後でもう一度お試しください。",
    "err_tls": "安全な接続（TLS／証明書）に失敗しました。システム時刻、プロキシ、ファイアウォールを確認してください。",
    "err_not_found": "サーバー上にファイルが見つかりません（404）。",
    "err_rate_limit": "サーバーが一時的にリクエストを拒否しています（制限中）。後でもう一度お試しください。",
    "err_server": "サーバーに問題が発生しています。後でもう一度お試しください。",
    "err_disk_full": "ディスクの空き容量が足りません。空きを作って再試行してください。",
    "err_permission": "このフォルダーに書き込む権限がありません。別の保存先を選んでください。",
    "err_checksum": "チェックサムが一致しません。ダウンロードが破損している可能性があります。後でもう一度お試しください。",
    "err_tried": "（試行：{hosts}）",
})


# --- settings dialog sections and helper text
TR["zh_TW"].update({
    "set_sec_download": "下載",
    "set_sec_appearance": "外觀與語言",
    "dir_help": "歌曲會儲存在這個資料夾，每首歌一個子資料夾。",
    "workers_help": "同時下載的檔案數（1–8）。數字越大越快，但對伺服器負擔也越大，建議 3。",
    "src_help": "選擇歌曲檔的下載來源；失敗時會自動改用另一個。",
    "keep_awake": "下載時保持電腦喚醒",
    "keep_awake_help": "下載進行中防止電腦進入睡眠；下載結束後恢復正常。",
    "bg_ask": "下載仍在進行中。\n要停止並結束，還是改在背景（系統匣）繼續下載？",
    "bg_keep": "背景繼續下載",
    "bg_quit": "停止並結束",
    "bg_ask_notray": "下載仍在進行中。\n要停止並結束嗎？",
    "tray_show": "顯示視窗",
    "tray_pause": "暫停",
    "tray_resume": "繼續",
    "tray_quit": "停止並結束",
    "lang_help": "介面語言。「自動」會依系統語言決定。",
    "th_help": "淺色或深色外觀；「跟隨系統」會隨作業系統設定切換。",
})
TR["en"].update({
    "set_sec_download": "Downloads",
    "set_sec_appearance": "Appearance and language",
    "dir_help": "Songs are saved in this folder, one sub-folder per song.",
    "workers_help": "Files downloaded at the same time (1-8). More is faster but harder on the server; 3 is a good default.",
    "src_help": "Where song files come from. If it fails, the other source is tried automatically.",
    "keep_awake": "Keep computer awake while downloading",
    "keep_awake_help": "Prevents the computer from sleeping during a download; normal behaviour resumes afterwards.",
    "bg_ask": "Downloads are running.\nStop and quit, or keep downloading in the background (tray)?",
    "bg_keep": "Keep in background",
    "bg_quit": "Stop and quit",
    "bg_ask_notray": "Downloads are running.\nStop and quit?",
    "tray_show": "Show",
    "tray_pause": "Pause",
    "tray_resume": "Resume",
    "tray_quit": "Stop and quit",
    "lang_help": "Interface language. Auto follows your system language.",
    "th_help": "Light or dark look. Auto follows the OS setting and switches with it.",
})
TR["ja"].update({
    "set_sec_download": "ダウンロード",
    "set_sec_appearance": "外観と言語",
    "dir_help": "曲はこのフォルダに、1曲につき1つのサブフォルダで保存されます。",
    "workers_help": "同時にダウンロードするファイル数（1～8）。多いほど速いですがサーバーへの負荷も増えます。標準は 3 です。",
    "src_help": "曲ファイルのダウンロード元。失敗した場合は自動的にもう一方を使います。",
    "keep_awake": "ダウンロード中はスリープさせない",
    "keep_awake_help": "ダウンロード中にPCがスリープしないようにします。終了後は通常に戻ります。",
    "bg_ask": "ダウンロード実行中です。\n停止して終了しますか？それともバックグラウンド（トレイ）で続けますか？",
    "bg_keep": "バックグラウンドで続行",
    "bg_quit": "停止して終了",
    "bg_ask_notray": "ダウンロード実行中です。\n停止して終了しますか？",
    "tray_show": "表示",
    "tray_pause": "一時停止",
    "tray_resume": "再開",
    "tray_quit": "停止して終了",
    "lang_help": "表示言語。「自動」はシステムの言語に合わせます。",
    "th_help": "ライトまたはダーク。「自動」は OS の設定に合わせて切り替わります。",
})


# --- keyboard, accessibility and UI font size
TR["zh_TW"].update({
    "sel_menu": "選取 ▾", "sel_invert": "反向選取", "sel_notdl": "選取未下載的",
    "sel_partial": "選取部分下載的（補齊）", "sel_cat": "選取目前分類的歌曲",
    "sel_visible_only": "清除隱藏列的勾選（只留可見的）",
    "sel_menu_tip": "更多選取方式", "sel_detail": "已選擇 {n} 首 · {f} 個檔案",
    "sel_detail_size": "已選擇 {n} 首 · {f} 個檔案 · {size}",
    "sel_label_tip": "點擊跳到已勾選的歌曲（再點跳下一首）",
    "search_tip": "搜尋歌曲（Ctrl+F；↓ 移到表格；Esc 清除；F5 重新搜尋）",
    "acc_category": "分類", "acc_category_tip": "依分類篩選歌曲（可複選）",
    "cat_n": "{n} 個分類", "cat_all_menu": "全部分類",
    "acc_filter_tip": "依 BPM、難度與等級篩選",
    "acc_table": "歌曲列表", "acc_table_tip": "歌曲列表（Space 勾選、Ctrl+A 全部勾選、Ctrl+D 下載）",
    "selall_tip": "勾選目前列出的所有歌曲（Ctrl+A）",
    "deselall_tip": "取消勾選所有歌曲",
    "font_label": "字體大小", "font_tip": "整個程式的文字大小，立即套用",
})
TR["en"].update({
    "sel_menu": "Select ▾", "sel_invert": "Invert selection", "sel_notdl": "Select not downloaded",
    "sel_partial": "Select partially downloaded (to complete)", "sel_cat": "Select songs in current category",
    "sel_visible_only": "Clear checks in hidden rows (keep visible only)",
    "sel_menu_tip": "More ways to select", "sel_detail": "{n} selected · {f} files",
    "sel_detail_size": "{n} selected · {f} files · {size}",
    "sel_label_tip": "Click to jump to checked songs (click again for the next)",
    "search_tip": "Search songs (Ctrl+F; Down arrow moves to the table; Esc clears; F5 re-runs)",
    "acc_category": "Category", "acc_category_tip": "Filter songs by category (multi-select)",
    "cat_n": "{n} categories", "cat_all_menu": "All categories",
    "acc_filter_tip": "Filter by BPM, difficulty and level",
    "acc_table": "Song list", "acc_table_tip": "Song list (Space checks, Ctrl+A checks all, Ctrl+D downloads)",
    "selall_tip": "Check all listed songs (Ctrl+A)",
    "deselall_tip": "Uncheck all songs",
    "font_label": "Font size", "font_tip": "Text size for the whole app, applied immediately",
})
TR["ja"].update({
    "sel_menu": "選択 ▾", "sel_invert": "選択を反転", "sel_notdl": "未ダウンロードを選択",
    "sel_partial": "一部ダウンロード済みを選択（補完）", "sel_cat": "現在のカテゴリの曲を選択",
    "sel_visible_only": "非表示行のチェックを解除（表示中のみ残す）",
    "sel_menu_tip": "その他の選択方法", "sel_detail": "{n} 曲選択 · {f} ファイル",
    "sel_detail_size": "{n} 曲選択 · {f} ファイル · {size}",
    "sel_label_tip": "クリックでチェック済みの曲へ移動（もう一度で次へ）",
    "search_tip": "曲を検索（Ctrl+F、↓ で表へ移動、Esc でクリア、F5 で再検索）",
    "acc_category": "カテゴリ", "acc_category_tip": "カテゴリで曲を絞り込み（複数選択可）",
    "cat_n": "{n} カテゴリ", "cat_all_menu": "すべてのカテゴリ",
    "acc_filter_tip": "BPM・難易度・レベルで絞り込み",
    "acc_table": "曲リスト", "acc_table_tip": "曲リスト（Space でチェック、Ctrl+A で全チェック、Ctrl+D でダウンロード）",
    "selall_tip": "表示中の曲をすべてチェック（Ctrl+A）",
    "deselall_tip": "すべてのチェックを外す",
    "font_label": "文字サイズ", "font_tip": "アプリ全体の文字サイズ（すぐに反映）",
})

# --- song detail panel
TR["zh_TW"].update({
    "dp_title": "歌曲詳細資料", "dp_files": "檔案", "dp_download": "下載此歌曲",
    "dp_copy": "複製歌名", "dp_empty": "選擇一首歌曲以查看詳細資料",
    "mw_menu_view": "檢視(&V)", "dp_toggle": "歌曲詳細資料面板",
    "dp_toggle_tip": "顯示或隱藏歌曲詳細資料面板",
})
TR["en"].update({
    "dp_title": "Song details", "dp_files": "Files", "dp_download": "Download this song",
    "dp_copy": "Copy title", "dp_empty": "Select a song to see its details",
    "mw_menu_view": "&View", "dp_toggle": "Song Details Panel",
    "dp_toggle_tip": "Show or hide the song details panel",
})
TR["ja"].update({
    "dp_title": "曲の詳細", "dp_files": "ファイル", "dp_download": "この曲をダウンロード",
    "dp_copy": "曲名をコピー", "dp_empty": "曲を選ぶと詳細が表示されます",
    "mw_menu_view": "表示(&V)", "dp_toggle": "曲の詳細パネル",
    "dp_toggle_tip": "曲の詳細パネルを表示/非表示",
})


# --- download monitor: log toolbar and failed list
TR["zh_TW"].update({
    "tab_log_n": "Log（{n} 個錯誤）", "tab_fail_n": "失敗清單（{n}）",
    "log_filter_ph": "篩選記錄…", "log_errors_only": "只看錯誤",
    "log_copy": "全部複製", "log_save": "儲存…", "log_clear": "清除",
    "log_save_title": "儲存記錄", "log_save_fail": "無法儲存記錄：{e}",
    "fail_retry_sel": "重試選取項目", "fail_open_page": "開啟歌曲頁面",
    "fail_copy_path": "複製路徑",
})
TR["en"].update({
    "tab_log_n": "Log ({n} errors)", "tab_fail_n": "Failed ({n})",
    "log_filter_ph": "Filter log…", "log_errors_only": "Errors only",
    "log_copy": "Copy all", "log_save": "Save…", "log_clear": "Clear",
    "log_save_title": "Save log", "log_save_fail": "Could not save the log: {e}",
    "fail_retry_sel": "Retry selected", "fail_open_page": "Open song page",
    "fail_copy_path": "Copy path",
})
TR["ja"].update({
    "tab_log_n": "ログ（エラー {n} 件）", "tab_fail_n": "失敗（{n}）",
    "log_filter_ph": "ログを絞り込み…", "log_errors_only": "エラーのみ",
    "log_copy": "すべてコピー", "log_save": "保存…", "log_clear": "クリア",
    "log_save_title": "ログを保存", "log_save_fail": "ログを保存できませんでした：{e}",
    "fail_retry_sel": "選択を再試行", "fail_open_page": "曲のページを開く",
    "fail_copy_path": "パスをコピー",
})

# --- search typo suggestions
TR["zh_TW"].update({"did_you_mean": "你是不是要找：{items}？"})
TR["en"].update({"did_you_mean": "Did you mean: {items}?"})
TR["ja"].update({"did_you_mean": "もしかして：{items}？"})

# --- About / release notes
TR["zh_TW"].update({
    "about_title": "關於 ESEManager", "about_version": "版本", "about_data_dir": "資料夾",
    "about_log": "記錄檔", "about_open": "開啟", "about_copy_diag": "複製診斷資訊",
    "about_copied": "已複製", "about_close": "關閉",
    "whatsnew_title": "{v} 的新功能", "whatsnew_none": "（此版本沒有更新說明）",
})
TR["en"].update({
    "about_title": "About ESEManager", "about_version": "Version", "about_data_dir": "Data folder",
    "about_log": "Log file", "about_open": "Open", "about_copy_diag": "Copy diagnostics",
    "about_copied": "Copied", "about_close": "Close",
    "whatsnew_title": "What's new in {v}", "whatsnew_none": "(No release notes for this version.)",
})
TR["ja"].update({
    "about_title": "ESEManager について", "about_version": "バージョン", "about_data_dir": "データフォルダ",
    "about_log": "ログファイル", "about_open": "開く", "about_copy_diag": "診断情報をコピー",
    "about_copied": "コピーしました", "about_close": "閉じる",
    "whatsnew_title": "{v} の新機能", "whatsnew_none": "（このバージョンのリリースノートはありません）",
})


TR["zh_TW"].update({"sn_summary": "{new} 首新歌、{upd} 首更新", "sn_show": "查看",
                    "sn_none": "沒有新增或更新的歌曲", "c_new": "新", "f_new": "新增／更新",
                    "sn_filter_new": "新增／更新", "sn_badge_new": "NEW", "sn_badge_upd": "UPD",
                    "sn_tip_new": "上次資料庫更新新增的歌曲", "sn_tip_upd": "上次資料庫更新有檔案變更"})
TR["en"].update({"sn_summary": "{new} new songs, {upd} updated", "sn_show": "Show them",
                 "sn_none": "No new or updated songs", "c_new": "New", "f_new": "What's new",
                 "sn_filter_new": "New / updated", "sn_badge_new": "NEW", "sn_badge_upd": "UPD",
                 "sn_tip_new": "Added by the last database update",
                 "sn_tip_upd": "Files changed in the last database update"})
TR["ja"].update({"sn_summary": "新曲 {new} 件、更新 {upd} 件", "sn_show": "表示する",
                 "sn_none": "新曲・更新はありません", "c_new": "新着", "f_new": "新着・更新",
                 "sn_filter_new": "新着／更新", "sn_badge_new": "NEW", "sn_badge_upd": "UPD",
                 "sn_tip_new": "前回のデータベース更新で追加", "sn_tip_upd": "前回のデータベース更新でファイル変更"})


# --- favourites
TR["zh_TW"].update({
    "c_fav": "★", "fav_add": "加入最愛", "fav_remove": "移出最愛",
    "f_fav_only": "只顯示最愛", "sel_fav": "選取最愛的歌曲",
})
TR["en"].update({
    "c_fav": "★", "fav_add": "Add to favourites", "fav_remove": "Remove from favourites",
    "f_fav_only": "Favourites only", "sel_fav": "Select favourites",
})
TR["ja"].update({
    "c_fav": "★", "fav_add": "お気に入りに追加", "fav_remove": "お気に入りから削除",
    "f_fav_only": "お気に入りのみ", "sel_fav": "お気に入りを選択",
})
