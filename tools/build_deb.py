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

"""Build the NightScribe .deb (ADR-079 packaging).

The package uses the SYSTEM Python: it depends on the distro's python3 and
the Qt/scientific packages (PySide6, astropy, scipy, numpy, matplotlib,
photutils, lxml, requests, PyYAML, platformdirs, Pillow). That keeps the
.deb small (a few MB) and avoids shipping a second Python and a second Qt.
The price is the target: Debian 13+ and Ubuntu 25.10+, the distros that
package PySide6. Older ones (Ubuntu 24.04 LTS has no python3-pyside6) are
documented as a manual install, not supported by this package.

imageio-ffmpeg is a RECOMMENDATION, not a dependency: it only powers the
MP4 animation export, and Fedora does not package it. Without it the GIF and
the montage keep working.

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
import os
import shutil
import stat
import subprocess
import sys
import tempfile
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
]
RECOMMENDS = ["python3-imageio-ffmpeg"]

# The app icons the .desktop entry points at, by size.
ICON_SIZES = (16, 32, 48, 64, 128, 256)


def _write(path, text, mode=None):
    # @args: path - Path, text - contents, mode - chmod (or None)
    # @return: None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if mode is not None:
        path.chmod(mode)


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
        "# Python (the .deb depends on it, ADR-079).",
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
    stage = Path(tempfile.mkdtemp(prefix="ns-deb-"))
    try:
        # The Python package, importable by the system interpreter.
        dest_pkg = stage / "usr" / "lib" / "python3" / "dist-packages"
        shutil.copytree(ROOT / "nightscribe", dest_pkg / "nightscribe",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        # The launcher, the desktop entry and the icons.
        _write(stage / "usr" / "bin" / "nightscribe", _wrapper(),
               mode=0o755)
        shutil.copy2(ROOT / "installer" / "nightscribe.desktop",
                     _mk(stage / "usr" / "share" / "applications"
                         / "nightscribe.desktop"))
        for size in ICON_SIZES:
            src = ROOT / "nightscribe" / "assets" / f"appicon-{size}.png"
            if src.is_file():
                dst = (stage / "usr" / "share" / "icons" / "hicolor"
                       / f"{size}x{size}" / "apps" / "nightscribe.png")
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        # Find_Orb, when the caller prepared one (bin/fo + share/findorb/data).
        if findorb_dir and Path(findorb_dir).is_dir():
            shutil.copytree(findorb_dir,
                            stage / "usr" / "lib" / "nightscribe" / "findorb")
        # DEBIAN/control (Installed-Size in KiB, as the policy wants).
        size_kb = sum(f.stat().st_size for f in stage.rglob("*")
                      if f.is_file()) // 1024
        _write(stage / "DEBIAN" / "control", _control(version, arch, size_kb))
        deb = out_dir / f"nightscribe_{version}_{arch}.deb"
        subprocess.run(["dpkg-deb", "--build", "--root-owner-group",
                        str(stage), str(deb)], check=True)
        return deb
    finally:
        shutil.rmtree(stage, ignore_errors=True)


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
