# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['launcher_v2.py'],
    pathex=['D:/Users/Administrator/Desktop/mtkclient', 'D:/Users/Administrator/Desktop/mtkclient/app'],
    binaries=[],
    datas=[('D:/Users/Administrator/Desktop/mtkclient/mtkclient/Loader/OPLUS_DA_mt6991.bin', 'mtkclient/Loader'), ('D:/Users/Administrator/Desktop/mtkclient/mtkclient/Loader/OPLUS_mt6991.auth', 'mtkclient/Loader'), ('D:/Users/Administrator/Desktop/mtkclient/mtkclient/payloads', 'mtkclient/payloads'), ('D:/Users/Administrator/Desktop/mtkclient/mtkclient/Windows', 'mtkclient/Windows'), ('D:/Users/Administrator/Desktop/mtkclient/mtkclient/Library/Filesystem/bin', 'mtkclient/Library/Filesystem/bin'), ('D:/Users/Administrator/Desktop/mtkclient/app/icon.ico', '.'), ('D:/Users/Administrator/Desktop/mtkclient/app/platform-tools', 'platform-tools'), ('D:/Users/Administrator/Desktop/mtkclient/app/tools', 'tools'), ('D:/Users/Administrator/Desktop/mtkclient/app/THIRD_PARTY_NOTICES.md', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='MTK9400Pro',
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
    icon=['D:/Users/Administrator/Desktop/mtkclient/app/icon.ico'],
)
