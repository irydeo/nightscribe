############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Portable stand-ins for external executables (tests)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Portable stand-ins for the external binaries the tests fake.

The production code runs them AS executables: ASTAP gets its command line
(`[astap_path, "-f", file, ...]`) and EXOTIC is started as the interpreter
(`[python, "-c", ..., "-red", inits, "-ov"]`). So the stand-in has to be a
file the operating system can execute.

On POSIX that is a shebang script with the executable bit. On Windows a .py
file cannot be run directly: the CI measured `[WinError 193] %1 is not a
valid Win32 application` and eighteen tests went red. Windows runs a .cmd
(or .bat) through the command processor, so a two-line .cmd hands the body
to this very interpreter, which is also what the real thing looks like from
the outside: one executable that prints and writes files.
"""

import os
import sys
from pathlib import Path


def make_fake_binary(folder, name, body):
    # Writes the stand-in and returns the path to hand the production code.
    # @args: folder - where to write it, name - the file name (ends in .py),
    #        body - the Python source, without shebang
    # @return: the executable path (the script on POSIX, the .cmd on Windows)
    folder = Path(folder)
    script = folder / name
    script.write_text("#!/usr/bin/env python3\n" + body)
    os.chmod(script, 0o755)
    if os.name != "nt":
        return script
    shim = folder / (Path(name).stem + ".cmd")
    # %~dp0 is the shim's own folder (with its trailing separator) and %*
    # passes the original arguments through untouched; %* keeps the quoting
    # the caller used, so a path with spaces survives.
    shim.write_text('@echo off\r\n"{}" "%~dp0{}" %*\r\n'.format(
        sys.executable, name))
    return shim
