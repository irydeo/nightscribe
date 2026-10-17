############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - GUI translation catalogue build (lupdate + atomic lrelease)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Rebuild the GUI translation catalogues, safely.

The two steps the CONTRIBUTING file documents, with one guarantee added:
the `.qm` files are replaced ATOMICALLY.

Why that matters, measured: QTranslator MEMORY-MAPS a `.qm` loaded by
filename. If `lrelease` rewrites that file in place while a NightScribe is
open, the running app's mapping is invalidated and the next `tr()` walks off
it and crashes. That is exactly what produced a GUI core dump on 2026-10-10
(the app died inside `QTranslator::translate`, reached from the sky-event
chips). Writing the new `.qm` to a sibling temp file and renaming it over
the target keeps every open app pointing at the OLD inode, whose pages stay
valid, so a rebuild can never crash a running session again.

Usage:
    .venv/bin/python tools/i18n.py                 # lupdate + atomic lrelease
    .venv/bin/python tools/i18n.py --release-only   # only recompile the .qm
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
I18N = ROOT / "nightscribe" / "gui" / "i18n"

# The sources lupdate must see, exactly as CONTRIBUTING lists them: the GUI
# modules, the widgets (their strings would go "vanished" otherwise), the core
# modules that carry runtime strings (NSKinds, NSMigrations, NSNight) and every
# Designer file. Globs, not a directory scan: lupdate silently skips .py files
# when handed a folder.
#
# The core modules are listed ONE BY ONE on purpose: they are the few that
# translate their own strings at runtime (QCoreApplication.translate) instead
# of going through a widget's tr(), and a module that is left out is not just
# untranslated, it is INVISIBLE: lupdate never extracts its strings, they are
# missing from both catalogues, and the completeness test cannot see what is
# not there. That is how the whole sky strip (the Moon, the darkness window,
# the planets, the phase names and the compass letters) shipped in English on
# a Spanish interface (reported 2026-10-17). tests/unit/test_i18n.py walks the
# core package and fails when a module with its own tr() is not listed here.
SOURCES = (
    "nightscribe/gui/*.py",
    "nightscribe/gui/widgets/*.py",
    "nightscribe/core/kinds.py",
    "nightscribe/core/db.py",
    "nightscribe/core/night_brief.py",
    "nightscribe/gui/ui/*.ui",
)

CATALOGUES = ("nightscribe_es.ts", "nightscribe_en.ts")


def _tool(name):
    # @args: name - "lupdate" | "lrelease"
    # @return: the path to the pyside6-<name> tool
    # The tool ships next to the interpreter running this script (the venv);
    # PATH is the fallback for a system install.
    beside = Path(sys.executable).parent / f"pyside6-{name}"
    if beside.exists():
        return str(beside)
    found = shutil.which(f"pyside6-{name}")
    if not found:
        raise SystemExit(f"pyside6-{name} was not found (install PySide6)")
    return found


def lupdate():
    # @return: None. Refreshes the .ts from the sources, keeping the existing
    #          translations; new strings arrive marked unfinished.
    # NOTE: `-no-obsolete` is deliberately NOT passed. Some strings are built
    # at runtime (the sky-quality scale, the planet names), so lupdate cannot
    # see them in the sources and would drop their translations as obsolete,
    # which the coverage test catches. The dead entries it keeps are the price.
    sources = []
    for pattern in SOURCES:
        sources.extend(sorted(str(p) for p in ROOT.glob(pattern)))
    cmd = [_tool("lupdate"), *sources,
           "-ts", str(I18N / CATALOGUES[0]), str(I18N / CATALOGUES[1])]
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)


def lrelease():
    # @return: None. Compiles every .ts into its .qm ATOMICALLY: build to a
    #          sibling temp file and rename it over the target, so a running
    #          app's memory map of the old file stays valid.
    for name in CATALOGUES:
        ts = I18N / name
        if not ts.exists():
            continue
        target = ts.with_suffix(".qm")
        tmp = target.with_name(target.name + ".tmp")
        subprocess.run([_tool("lrelease"), str(ts), "-qm", str(tmp)],
                       check=True, cwd=ROOT)
        os.replace(tmp, target)          # same directory: an atomic rename
        print(f"{target.name}: rebuilt atomically")


def main():
    # @return: the process exit code
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-only", action="store_true",
                        help="skip lupdate and only recompile the .qm files")
    args = parser.parse_args()
    if not args.release_only:
        lupdate()
    lrelease()
    return 0


if __name__ == "__main__":
    sys.exit(main())
