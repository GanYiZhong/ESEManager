# -*- mode: python ; coding: utf-8 -*-
block_cipher = None

_common = dict(
    pathex=['../src'],
    binaries=[],
    datas=[
        ('../assets', 'assets'),
        ('../src/icons', 'icons'),     # themed SVG icons (src/icons.py)
    ],
    hiddenimports=[
        'requests',
        'webbrowser',          # loaded lazily (core.LazyModule)
        'sqlite3',
        'tomllib',
        'tomli',
        'tomli_w',
        'concurrent.futures',
        'appconfig',
        'core',
        'theme',
        'icons',
        'responsive',
        'detail_panel',
        'command_palette',
        'PySide6.QtSvg',
        'app_version',
        'i18n',
        'models',
        'workers',
        'dialogs',
        'category_picker',
        'columns',
        'songlist',
        'notify',
        'power',
        'cli',
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

# Two programs share one folder: the GUI (ESEManager) and the console
# command-line mode (ESEManager-cli, see src/cli.py).
a = Analysis(['../src/ese_qt.py'], **_common)
a_cli = Analysis(['../src/cli.py'], **_common)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
pyz_cli = PYZ(a_cli.pure, a_cli.zipped_data, cipher=block_cipher)

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
    icon='../assets/icon.ico',
)

exe_cli = EXE(
    pyz_cli,
    a_cli.scripts,
    [],
    exclude_binaries=True,
    name='ESEManager-cli',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,              # command-line mode prints to the terminal
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='../assets/icon.ico',
)

coll = COLLECT(
    exe,
    exe_cli,
    a.binaries + a_cli.binaries,
    a.zipfiles + a_cli.zipfiles,
    a.datas + a_cli.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='ESEManager',
)
