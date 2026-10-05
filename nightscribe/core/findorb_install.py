############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Find_Orb guided installation module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Installing Find_Orb, with the app's hand on the wheel (ADR-062, D31).

Find_Orb is Bill Gray's orbit fitter (Project Pluto) and NightScribe never
bundles it: it detects the user's copy and runs it, the way it does with
ASTAP for the plate solve. But "go and install Find_Orb" is a wall for an
observer who does not live in a terminal, so this module walks them through
it.

The easy road on Linux and macOS is the conda-forge package `findorb`: it
ships PRECOMPILED binaries for both `fo` (the non-interactive one NightScribe
runs) and `find_orb`, and it pulls `findorb-data-de430t`, the JPL DE430t
ephemerides the perturbations need. So the whole install is one command of a
package manager the user already has, and the environment is PRIVATE (a `-p`
prefix inside a folder of their choosing) so it never touches a base install.

What this module will NOT do is download a package manager behind the user's
back: fetching and running a binary from the internet is a decision an
astronomy app does not get to make for its user. With no manager found, the
guide says where to get one and what to type, and stops there.

The binary is searched by NAME, never by a guessed path: conda puts it in
`bin/` on posix and in `Library/bin` on Windows, and the Windows zips unpack
it next to `find_orb` itself.
"""

import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# The managers we can drive, in the order we prefer them. micromamba comes
# first because it is one static binary and needs no base environment; conda
# comes last because it is the heaviest of the three.
MANAGERS = ("micromamba", "mamba", "conda")

# The conda-forge package: the two binaries plus the DE430t ephemerides.
PACKAGE = "findorb"
CHANNEL = "conda-forge"

# Where a manager may live without being on PATH. This is the common case,
# not the exception: micromamba is usually dropped in ~/.local/bin or
# ~/micromamba/bin and the shell's PATH is never touched.
_EXTRA_DIRS = ("~/.local/bin", "~/micromamba/bin", "~/bin",
               "~/miniconda3/bin", "~/anaconda3/bin", "~/miniforge3/bin",
               "~/mambaforge/bin")

# The names the binary goes by, most specific first. `fo` is the
# NON-interactive program, which is the only one NightScribe can drive; the
# interactive `find_orb` is refused on purpose (a probe that opened a
# console UI would hang the app).
_BIN_NAMES = ("fo", "fo.exe", "fo64.exe", "fo64")


def find_manager():
    # @return: (name, path) of the first package manager found, or
    #          (None, None). PATH first (the honest answer), then the usual
    #          install folders that a GUI app never inherits.
    for name in MANAGERS:
        found = shutil.which(name)
        if found:
            return name, found
    for folder in _EXTRA_DIRS:
        base = Path(folder).expanduser()
        for name in MANAGERS:
            candidate = base / name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return name, str(candidate)
    return None, None


def install_plan(manager, manager_path, target_dir):
    # @args: manager - the manager's name, manager_path - its executable,
    #        target_dir - where the private environment goes
    # @return: {"argv", "cwd", "what"}: the exact command to run. micromamba,
    #          mamba and conda share this CLI; the `-p` prefix is what keeps
    #          the environment PRIVATE, so nothing of the user's existing
    #          Python setup is touched.
    target = str(Path(target_dir).expanduser())
    argv = [str(manager_path), "create", "-y", "-p", target,
            "-c", CHANNEL, PACKAGE]
    return {"argv": argv, "cwd": str(Path(target).parent),
            "what": f"{manager} create -p {target} -c {CHANNEL} {PACKAGE}"}


def find_fo(root):
    # @args: root - a folder to search (an environment, or a plain folder
    #        where the Windows zips were unpacked)
    # @return: the path to the non-interactive binary, or None
    root = Path(root).expanduser()
    if not root.exists():
        return None
    for name in _BIN_NAMES:
        direct = root / name
        if direct.is_file():
            return str(direct)
    for name in _BIN_NAMES:
        for hit in sorted(root.rglob(name)):
            if hit.is_file():
                return str(hit)
    return None


def find_on_path():
    # @return: the `fo` already installed and on PATH, or None. The easy
    #          case: the observer installed it and never told the app.
    for name in _BIN_NAMES:
        found = shutil.which(name)
        if found:
            return found
    return None


def install(manager_path, target_dir, on_log=None, cancel=None):
    # @args: manager_path - the manager's executable, target_dir - the
    #        private environment, on_log - callable(line) for the live log,
    #        cancel - callable() -> True to stop the run
    # @return: {"ok", "path", "log"}: ok is False when the manager failed or
    #          the run was cancelled; path is the `fo` found afterwards, or
    #          None; log is the tail of the manager's own words, which is
    #          what the observer needs when it fails.
    plan = install_plan(Path(manager_path).name, manager_path, target_dir)
    try:
        Path(target_dir).expanduser().mkdir(parents=True, exist_ok=True)
    except OSError as err:
        return {"ok": False, "path": None, "log": [str(err)]}
    log = []
    try:
        proc = subprocess.Popen(
            plan["argv"], cwd=plan["cwd"], stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8",
            errors="replace")
    except OSError as err:
        # the manager vanished between the search and the run: say it
        return {"ok": False, "path": None, "log": [f"{manager_path}: {err}"]}
    try:
        for line in proc.stdout:
            line = line.rstrip()
            log.append(line)
            if on_log is not None:
                on_log(line)
            if cancel is not None and cancel():
                proc.terminate()
                break
        proc.wait(timeout=30)
    except Exception as err:            # a broken pipe, a killed process
        logger.warning("find_orb install stream failed: %s", err)
        try:
            proc.kill()
        except Exception:
            pass
    ok = proc.returncode == 0
    return {"ok": ok, "path": find_fo(target_dir) if ok else None,
            "log": log[-40:]}
