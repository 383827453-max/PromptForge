# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置。

llmclient 是独立项目、作为普通依赖装在 site-packages 里，PyInstaller
能自动找到，不再需要 pathex 或 hiddenimports 手工兜底。
"""

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('promptforge\\strategies', 'promptforge\\strategies'),
        ('promptforge\\templates_builtin', 'promptforge\\templates_builtin'),
        ('assets', 'assets'),
    ],
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
