# -*- mode: python ; coding: utf-8 -*-
block_cipher = None

a = Analysis(
    ['../src/ese_qt.py'],
    pathex=['../src'],
    binaries=[],
    datas=[
        ('../src/download_songs.py', '.'),
    ],
    hiddenimports=[
        'requests',
        'sqlite3',
        'tomllib',
        'tomli',
        'tomli_w',
        'concurrent.futures',
        'download_songs',
        'ese_scraper_git_v2',
        'build_local_db',
        'tja_parser',
        'dan_tools',
        'lxml',
        'lxml.html',
        'lxml.etree',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'customtkinter', 'PyQt5', 'matplotlib', 'numpy',
        'PIL', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
        'PySide6.Qt3DCore', 'PySide6.QtMultimedia', 'PySide6.QtQuick',
        'PySide6.QtQml', 'PySide6.QtCharts', 'PySide6.QtDataVisualization',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# onedir（資料夾）而非 onefile：onefile 每次啟動都要把整包 ~73MB 解壓到 %TEMP%，
# 再讓 Defender 逐一掃描解出的 DLL，實測冷啟動要 ~10 秒。onedir 直接從 _internal/
# 載入 DLL、啟動時不解壓，冷啟動降到約 1 秒。發布時把整個 dist/ESEManager/ 資料夾
# 打包進 .7z 即可（DB/version.txt/config.toml 仍放 exe 同層、相對路徑不變）。
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,     # onedir 關鍵：binaries 交給 COLLECT 放進資料夾
    name='ESEManager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='ESEManager',
)
