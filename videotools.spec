# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec — VideoTools  (--onedir / 目录模式)
# 生成目录：VideoTools\打包\VideoTools\
#
import os

# ── Project root (directory containing this spec file) ────────────────────────
ROOT = os.path.dirname(os.path.abspath(SPEC))

a = Analysis(
    # Entry point
    [os.path.join(ROOT, 'main', 'main.py')],

    # Add project root so 'from UI.xxx import ...' works in frozen mode
    pathex=[ROOT],

    binaries=[],

    # Data files bundled into the package
    datas=[
        # Window icon
        (os.path.join(ROOT, 'log', 'log.ico'), 'log'),
    ],

    hiddenimports=[
        # PyQt6 multimedia (imported inside try/except — not auto-detected)
        'PyQt6.QtMultimedia',
        'PyQt6.QtMultimediaWidgets',
        'PyQt6.sip',
        # Pillow — used by image_worker for image processing
        'PIL',
        'PIL.Image',
        'PIL.ImageOps',
        'PIL.ImageFilter',
        'PIL.ImageEnhance',
        'PIL.ImageDraw',
        # Our own packages
        'UI.ui',
        'UI.ui_image_merger',
        'UI.ui_image_cropper',
        'UI.ui_multi_segment',
        'UI.ui_youtube_downloader',
        'UI.ui_auto_screenshot',
        'UI.ui_gdrive_downloader',
        'UI.ui_ffmpeg_downloader_mgr',
        'image_worker.image_merge_worker',
        'image_worker.image_worker',
        'image_worker.ffmpeg_worker',
        'image_worker.audio_library',
        'Video.video_manager',
    ],

    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Shrink the package by excluding things we definitely don't use
        'matplotlib', 'numpy', 'pandas', 'scipy', 'tkinter',
        'PySide2', 'PySide6', 'PyQt5',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,   # ← key: do NOT embed – place beside the exe (onedir)
    name='VideoTools',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,               # UPX can cause AV false-positives — keep off
    console=False,           # no black command-window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ROOT, 'log', 'log.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='VideoTools',        # output sub-folder name inside distpath
)
