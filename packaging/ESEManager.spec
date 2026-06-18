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

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ESEManager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
