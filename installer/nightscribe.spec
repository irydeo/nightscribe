############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - PyInstaller spec (standalone builds)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

# Build with:  .venv/bin/pyinstaller installer/nightscribe.spec
# Output:      dist/nightscribe/   (Linux binary; on Windows: nightscribe.exe)
# Bundles: Qt Designer .ui files, compiled .qm translations, matplotlib style
#          and the docs/ folder (Help > Documentation).

import glob
import os

block_cipher = None
ROOT = os.path.abspath(os.path.join(os.path.dirname(SPEC), ".."))

datas = []
for pattern in ("nightscribe/gui/ui/*.ui", "nightscribe/gui/i18n/*.qm"):
    for f in glob.glob(os.path.join(ROOT, pattern)):
        sub = os.path.dirname(os.path.relpath(f, ROOT))
        datas.append((f, sub))
# Whole docs/ tree, including adr/ (Help > Documentation viewer)
for f in glob.glob(os.path.join(ROOT, "docs/**/*.md"), recursive=True):
    sub = os.path.dirname(os.path.relpath(f, ROOT))
    datas.append((f, sub))

a = Analysis(
    [os.path.join(ROOT, "launcher.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=["lxml._elementpath", "Pillow", "platformdirs"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter"],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="nightscribe",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,   # CLI works from the same binary; GUI starts with "gui"
    argv_emulation=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="nightscribe",
)
