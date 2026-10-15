############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Debian package builder (.deb)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Build the NightScribe .deb (ADR-087 packaging).

The package uses the SYSTEM Python: it depends on the distro's python3 and
the Qt/scientific packages (PySide6, astropy, scipy, numpy, matplotlib,
photutils, lxml, requests, PyYAML, platformdirs, Pillow). That keeps the
.deb small (a few MB) and avoids shipping a second Python and a second Qt.
The price is the target: Debian 13+ and Ubuntu 25.10+, the distros that
package PySide6. Older ones (Ubuntu 24.04 LTS has no python3-pyside6) are
documented as a manual install, not supported by this package.

Three things are NOT optional for a package the observer installs from a
software centre, and all three were missing until 2026-10-14:

* a *.dist-info with the version, because the app reads its own version with
  importlib.metadata.version("nightscribe"); copying the tree by hand left it
  at the "0.0.0" fallback and the update detection never worked;
* the AppStream metainfo, which is where GNOME Software and the Ubuntu App
  Center read the licence, the developer and the icon from (a .desktop entry
  alone gives none of them);
* usr/share/doc/nightscribe/copyright, the licence file Debian policy asks
  for (it also names the bundled Find_Orb's separate licence).

imageio-ffmpeg is a RECOMMENDATION, not a dependency: it only powers the
MP4 animation export, and Fedora does not package it. Without it the GIF and
the montage keep working. pyopencl IS a dependency (ADR-091): it is the
portable GPU backend and the app ships it, though the acceleration stays off
by default and the CPU path runs unchanged with no OpenCL device.

Find_Orb is shipped INSIDE the package (usr/lib/nightscribe/findorb), so the
orbit check works out of the box. It is GPLv2 with an extra commercial-use
clause from Project Pluto, which is fine for this non-commercial GPLv3 app
and for a package published on GitHub Releases (it would NOT be accepted in
Debian main; see ADR-079).

Usage:
    .venv/bin/python tools/build_deb.py --version 0.1.0 \
        [--findorb /path/to/a/findorb/tree] [--out dist]
"""

import argparse
import gzip
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Hard dependencies, mapped to the Debian/Ubuntu binary package names. The
# PySide6 modules are split, so each Qt module the app imports is listed.
DEPENDS = [
    "python3 (>= 3.11)",
    "python3-pyside6.qtcore",
    "python3-pyside6.qtgui",
    "python3-pyside6.qtwidgets",
    "python3-pyside6.qtsvg",
    "python3-pyside6.qtuitools",
    "python3-astropy",
    "python3-scipy",
    "python3-numpy",
    "python3-matplotlib",
    "python3-photutils",
    "python3-lxml",
    "python3-requests",
    "python3-yaml",
    "python3-platformdirs",
    "python3-pil",
    # The portable GPU backend travels with the app (ADR-091), so OpenCL works
    # out of the box on NVIDIA, AMD and Intel. python3-pyopencl pulls the ICD
    # loader (ocl-icd-libopencl1) with it. The acceleration itself is off by
    # default and the app runs unchanged with no OpenCL device.
    "python3-pyopencl",
]
RECOMMENDS = ["python3-imageio-ffmpeg"]

# The app icons the .desktop entry points at, by size.
ICON_SIZES = (16, 32, 48, 64, 128, 256)

# The reverse-DNS id shared by the desktop entry and the AppStream metainfo.
# AppStream requires the two to match, which is why the file names carry it.
DESKTOP_ID = "io.github.irydeo.nightscribe"


def _write(path, text, mode=None):
    # @args: path - Path, text - contents, mode - chmod (or None)
    # @return: None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if mode is not None:
        path.chmod(mode)


def _dist_info(version):
    # The metadata importlib.metadata.version("nightscribe") reads. Without
    # it the installed app cannot tell its own version and falls back to
    # "0.0.0", which also breaks the update detection (ADR-087 rev).
    # @args: version - the package version
    # @return: the METADATA text of nightscribe-<version>.dist-info
    return "\n".join([
        "Metadata-Version: 2.1",
        "Name: nightscribe",
        f"Version: {version}",
        "Summary: Plan, reduce and report an astronomy night",
        "License: GPL-3.0-only",
        "Home-page: https://irydeo.github.io/nightscribe",
        "",
    ])


def _copyright():
    # The Debian copyright file (DEP-5): the licence the software centre and
    # `dpkg` show. GPL-3 is on every Debian/Ubuntu system, so the text is
    # referenced instead of inlined; the bundled Find_Orb is a SEPARATE
    # program with its own licence and is named as such (ADR-087).
    # @return: the copyright text
    return """Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: NightScribe
Source: https://github.com/irydeo/nightscribe

Files: *
Copyright: 2026 Francisco Jose Calvo Fernandez (Irydeo Observatory, MPC Z41)
License: GPL-3.0-only
 This program is free software: you can redistribute it and/or modify it
 under the terms of the GNU General Public License as published by the Free
 Software Foundation, version 3.
 .
 On Debian systems, the complete text of the GNU General Public License
 version 3 can be found in "/usr/share/common-licenses/GPL-3".

Files: usr/lib/nightscribe/findorb/*
Copyright: Bill Gray / Project Pluto
License: GPL-2.0-or-later with the Project Pluto commercial-use restriction
 Find_Orb is distributed under the GNU General Public License version 2 or
 later, with an additional restriction from Project Pluto: it may not be
 used in or with commercial software without written permission. It travels
 inside this package as a SEPARATE program (mere aggregation, GPLv2 section
 2) by this non-commercial GPLv3 application, which is allowed.
 Source: https://www.projectpluto.com/find_orb.htm
"""


def _control(version, arch, installed_size_kb):
    # @args: version - the package version, arch - the Debian architecture
    #        (amd64: the package ships the native `fo` binary), installed_size_kb
    # @return: the DEBIAN/control text
    return "\n".join([
        "Package: nightscribe",
        f"Version: {version}",
        "Section: science",
        "Priority: optional",
        f"Architecture: {arch}",
        "Maintainer: Francisco Jose Calvo Fernandez "
        "<irydeo@users.noreply.github.com>",
        "Homepage: https://github.com/irydeo/nightscribe",
        "Description: Plan, reduce and report an astronomy night",
        " NightScribe plans the night's best targets, captures and reduces the",
        " images (calibration, track & stack astrometry, photometry) and drafts",
        " the report and the social post.",
        f"Depends: {', '.join(DEPENDS)}",
        f"Recommends: {', '.join(RECOMMENDS)}",
        f"Installed-Size: {installed_size_kb}",
        "",
    ])


def _wrapper():
    # @return: the /usr/bin/nightscribe launcher
    return "\n".join([
        "#!/bin/sh",
        "# NightScribe launcher: runs the installed package with the system",
        "# Python (the .deb depends on it, ADR-087).",
        "exec python3 -m nightscribe \"$@\"",
        "",
    ])


def build(version, findorb_dir, out_dir, arch="amd64"):
    # @args: version - package version, findorb_dir - a prepared Find_Orb tree
    #        (bin/fo + share/findorb/data) or None, out_dir - where the .deb
    #        lands, arch - the Debian architecture (amd64: the shipped `fo` is
    #        a native linux-64 binary, so the package cannot be `all`)
    # @return: the path to the .deb
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stage = _stage(version, findorb_dir, arch)
    try:
        deb = out_dir / f"nightscribe_{version}_{arch}.deb"
        subprocess.run(["dpkg-deb", "--build", "--root-owner-group",
                        str(stage), str(deb)], check=True)
        return deb
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def _stage(version, findorb_dir, arch):
    # @args: version, findorb_dir, arch - as in build()
    # @return: the Path of the staged tree (the caller removes it)
    # Split out of build() so a test can inspect what the package will
    # actually carry without a dpkg-deb run: the documentation shipped empty
    # on every Linux channel until 2026-10-15 and nothing noticed.
    stage = Path(tempfile.mkdtemp(prefix="ns-deb-"))
    # The Python package, importable by the system interpreter.
    dest_pkg = stage / "usr" / "lib" / "python3" / "dist-packages"
    shutil.copytree(ROOT / "nightscribe", dest_pkg / "nightscribe",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    # The version, in the two shapes the app understands: the standard
    # dist-info (importlib.metadata) and a plain file the version module
    # reads as a last resort. Both carry the SAME --version, so a package
    # can never report a version other than the one it was built with.
    _write(dest_pkg / f"nightscribe-{version}.dist-info" / "METADATA",
           _dist_info(version))
    _write(stage / "usr" / "share" / "nightscribe" / "version",
           version + "\n")
    # The documentation, where paths.docs_dir() looks on a system install:
    # without it Help > Documentation, the UFE's "?" and the offline
    # assistant index come up empty.
    shutil.copytree(ROOT / "docs",
                    _mk(stage / "usr" / "share" / "nightscribe" / "docs"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    # Find_Orb's own licence notice, next to the copyright: the package ships
    # Find_Orb (a separate GPLv2 program) and has to say so.
    notice = ROOT / "installer" / "findorb-notice.txt"
    if notice.is_file():
        shutil.copy2(notice, _mk(stage / "usr" / "share" / "doc"
                                 / "nightscribe" / "findorb-notice.txt"))
    # The launcher, the desktop entry and the icons.
    _write(stage / "usr" / "bin" / "nightscribe", _wrapper(),
           mode=0o755)
    shutil.copy2(ROOT / "installer" / f"{DESKTOP_ID}.desktop",
                 _mk(stage / "usr" / "share" / "applications"
                     / f"{DESKTOP_ID}.desktop"))
    # The AppStream metainfo: licence, developer and icon for the
    # software centre (its id must match the .desktop file's name).
    shutil.copy2(ROOT / "installer" / f"{DESKTOP_ID}.metainfo.xml",
                 _mk(stage / "usr" / "share" / "metainfo"
                     / f"{DESKTOP_ID}.metainfo.xml"))
    for size in ICON_SIZES:
        src = ROOT / "nightscribe" / "assets" / f"appicon-{size}.png"
        if src.is_file():
            dst = (stage / "usr" / "share" / "icons" / "hicolor"
                   / f"{size}x{size}" / "apps" / "nightscribe.png")
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    # The Debian documentation: the copyright (the licence Debian policy
    # asks for) and a one-line changelog.
    doc = stage / "usr" / "share" / "doc" / "nightscribe"
    _write(doc / "copyright", _copyright())
    with gzip.open(_mk(doc / "changelog.gz"), "wt", encoding="utf-8") as fh:
        fh.write(
            f"nightscribe ({version}) unstable; urgency=medium\n\n"
            f"  * Package build {version}.\n\n"
            f" -- Francisco Jose Calvo Fernandez "
            f"<irydeo@users.noreply.github.com>  "
            f"{time.strftime('%a, %d %b %Y %H:%M:%S %z')}\n")
    # Find_Orb, when the caller prepared one (bin/fo + share/findorb/data).
    if findorb_dir and Path(findorb_dir).is_dir():
        shutil.copytree(findorb_dir,
                        stage / "usr" / "lib" / "nightscribe" / "findorb")
    # DEBIAN/control (Installed-Size in KiB, as the policy wants).
    size_kb = sum(f.stat().st_size for f in stage.rglob("*")
                  if f.is_file()) // 1024
    _write(stage / "DEBIAN" / "control", _control(version, arch, size_kb))
    return stage


def _mk(path):
    # @args: path - Path
    # @return: the path, with its parent created
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def main():
    # @return: the process exit code
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--findorb", default="",
                        help="a prepared Find_Orb tree to ship (bin/fo + "
                             "share/findorb/data)")
    parser.add_argument("--arch", default="amd64",
                        help="the Debian architecture (default amd64)")
    parser.add_argument("--out", default=str(ROOT / "dist"))
    args = parser.parse_args()
    deb = build(args.version, args.findorb, args.out, arch=args.arch)
    print(f"built {deb}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
