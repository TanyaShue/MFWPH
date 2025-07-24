# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('D:\\DeveEnvironment\\Program\\Anaconda3\\envs\\MFWPH\\Lib\\site-packages\\maa/bin', 'maa/bin'), ('D:\\DeveEnvironment\\Program\\Anaconda3\\envs\\MFWPH\\Lib\\site-packages\\MaaAgentBinary', 'MaaAgentBinary'), ('C:\\Users\\black\\AppData\\Local\\Temp\\versioninfo_MFWPH.txt', '.')],
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
    name='MFWPH',
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
    version='C:\\Users\\black\\AppData\\Local\\Temp\\tmp2_df3__1.txt',
    uac_admin=True,
)
