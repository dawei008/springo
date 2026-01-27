# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('mcp_tools', 'mcp_tools'), ('api', 'api'), ('auth', 'auth'), ('skills', 'skills')]
binaries = []
hiddenimports = ['flask', 'flask.json', 'werkzeug', 'werkzeug.serving', 'boto3', 'botocore', 'tiktoken', 'tiktoken_ext', 'tiktoken_ext.openai_public', 'mcp.client', 'mcp.client.stdio', 'mcp.types', 'concurrent.futures']
tmp_ret = collect_all('tiktoken')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['full_proxy_server.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    name='springo-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
