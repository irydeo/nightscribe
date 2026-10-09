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
# Bundles: Qt Designer .ui files, compiled .qm translations, the moon
#          surface asset, matplotlib style
#          and the docs/ folder (Help > Documentation).

import glob
import os

from PyInstaller.utils.hooks import (collect_data_files, copy_metadata)

block_cipher = None
ROOT = os.path.abspath(os.path.join(os.path.dirname(SPEC), ".."))

datas = []
# astropy ships data files it reads at runtime (IERS tables, its bundled
# constants, etc.). The hooks usually catch the Python modules but not every
# data file, and a missing one shows up as a runtime error in a frozen build
# only. It is pulled in by the astrometry/calibration modules (ADR-060).
try:
    datas += collect_data_files("astropy")
except Exception:
    pass  # bare environment without astropy: the app still runs without it
# Bundle the installed dist-info so the frozen app reports the real
# package version instead of the "not installed" fallback.
try:
    datas += copy_metadata("nightscribe")
except Exception:
    pass  # no installed metadata (bare source tree): keep the fallback
for pattern in ("nightscribe/gui/ui/*.ui", "nightscribe/gui/i18n/*.qm",
                "nightscribe/assets/*"):
    for f in glob.glob(os.path.join(ROOT, pattern)):
        sub = os.path.dirname(os.path.relpath(f, ROOT))
        datas.append((f, sub))
# Whole docs/ tree, including adr/ (the in-app docs browser the UFE's series
# "?" opens; the Help menu no longer has a general door to it)
for f in glob.glob(os.path.join(ROOT, "docs/**/*.md"), recursive=True):
    sub = os.path.dirname(os.path.relpath(f, ROOT))
    datas.append((f, sub))

a = Analysis(
    [os.path.join(ROOT, "launcher.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    # QtSvg renders the Welcome hero's sky (gui/widgets/welcome_sky.py).
    # It is imported inside a function, so it is named here rather than
    # trusted to the import graph: a missing QtSvg would not crash the app
    # (the hero falls back to a painted gradient) but it would quietly
    # downgrade the first screen of every frozen build.
    hiddenimports=["lxml._elementpath", "Pillow", "platformdirs",
                   "PySide6.QtSvg",
                   # astropy/scipy/photutils are imported lazily by the
                   # astrometry modules, so the import graph does not reach
                   # them; naming the pieces we actually use keeps the bundle
                   # from swallowing all of astropy (ADR-060).
                   "astropy", "astropy.io.fits", "astropy.wcs",
                   "astropy.units", "astropy.time", "astropy.utils.iers",
                   "scipy.ndimage", "scipy.optimize", "scipy.stats",
                   "photutils.centroids", "photutils.detection",
                   "photutils.aperture"],
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
    icon=os.path.join(ROOT, "nightscribe", "assets", "appicon.ico"),
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
