# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置。

注意 pathex 里显式加入 llmclient/src：PromptForge 依赖同仓库的 llmclient
子包，打包机未必把它 pip install 到 site-packages（CI 里装了，本地可能没装），
把源码路径直接告诉分析器最稳。
"""

a = Analysis(
    ['run.py'],
    pathex=['llmclient\\src'],
    binaries=[],
    datas=[
        ('promptforge\\strategies', 'promptforge\\strategies'),
        ('promptforge\\templates_builtin', 'promptforge\\templates_builtin'),
        ('assets', 'assets'),
    ],
    hiddenimports=['llmclient', 'llmclient.client', 'llmclient.endpoints', 'llmclient.errors'],
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
    name='PromptForge',
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
    icon=['assets\\icon.ico'],
)
