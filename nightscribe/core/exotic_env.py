############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - EXOTIC environment module (exotic orchestration, phase A)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Prepare and probe the external EXOTIC environment (plan phase A).

EXOTIC needs Python >= 3.10 and its own heavy stack (astropy, scipy,
pylightcurve, ultranest, astroalign, LDTk...), which is why it runs as an
EXTERNAL tool and never inside the app (ADR-004). This module finds a
suitable interpreter, checks whether EXOTIC imports, and builds a private
virtual environment with it.

It is written around a real quirk: on some distributions `python3.10 -m
venv` fails because `ensurepip` is missing, so the venv is created with
`--without-pip` and pip is bootstrapped through the base interpreter with
`pip --python <venv>/bin/python`. Windows layouts (Scripts/python.exe) are
handled too.
"""

import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# WHICH PYTHONS EXOTIC CAN LIVE IN. The rule used to be "3.10 or older", from
# EXOTIC 3.x, and it had two problems: it refused interpreters that work, and
# it offered ones EXOTIC 4.x does not support.
#
# What is true today (EXOTIC 4.3.1, measured 2026-10-20):
# * its metadata says `requires_python >= 3.10`, and every pin of its own stack
#   (numpy 1.26.4, astropy 6.1, numba 0.59.1, scipy 1.14.1, matplotlib 3.9.2,
#   photutils 2.0) has wheels for 3.10, 3.11 and 3.12;
# * a full `pip install exotic` on **3.11.2** leaves EXOTIC 4.3.1 importable
#   with every pinned version, so 3.11 is VERIFIED, and 3.10 was already
#   verified by the author's own environment;
# * 3.12 is allowed by the metadata and has wheels for the whole stack, but it
#   has not been installed here (no 3.12 on this machine);
# * 3.13 is OUT: numpy 1.26 has no wheels for it, so EXOTIC's own pins cannot
#   be satisfied there;
# * and 3.10 reached end of life in October 2026, which is why it is LAST: it
#   works, but nothing should be started on it any more.
#
# Newest first, so a machine that has several uses the best one it has.
_CANDIDATES = ("python3.11", "python3.12", "python3.10")
_PY_VERSIONS = ("3.11", "3.12", "3.10")
_MIN_VERSION = (3, 10)
_MAX_VERSION = (3, 12)
_TIMEOUT_S = 1800.0


class _Cancelled(Exception):
    pass


def bin_dir(install_dir):
    # @return: the venv's executable folder (Scripts on Windows, bin else)
    return Path(install_dir) / ("Scripts" if os.name == "nt" else "bin")


def venv_python(install_dir):
    # @return: the venv interpreter path (may not exist yet)
    exe = "python.exe" if os.name == "nt" else "python"
    return bin_dir(install_dir) / exe


def _version_of(python):
    # @args: python - an interpreter path
    # @return: (major, minor) or None when it cannot be run
    try:
        out = subprocess.run(
            [str(python), "-c",
             "import sys; print('%d.%d' % sys.version_info[:2])"],
            capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    try:
        major, minor = out.stdout.strip().split(".")[:2]
        return int(major), int(minor)
    except ValueError:
        return None


def version_ok(python):
    # @return: True when the interpreter is one EXOTIC can live in (3.10 to
    #          3.12: see the note at the top for why those and not others)
    v = _version_of(python)
    return v is not None and _MIN_VERSION <= v <= _MAX_VERSION


def _py_launcher(version):
    # The Windows launcher (`py -3.10`) resolves to a real interpreter;
    # a plain `python.exe` on PATH may be the wrong version or the
    # Microsoft Store stub.
    # @return: the interpreter path it points at, or None
    launcher = shutil.which("py")
    if not launcher:
        return None
    try:
        out = subprocess.run(
            [launcher, f"-{version}", "-c",
             "import sys; print(sys.executable)"],
            capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    exe = out.stdout.strip()
    if exe and Path(exe).is_file() and version_ok(exe):
        return exe
    return None


def configured_problem(preferred):
    # @args: preferred - the interpreter path from Settings (may be empty)
    # @return: None when nothing is configured or it is fine, else "missing"
    #          (the file is gone) or "version" (it is not one EXOTIC can use).
    #
    # This exists because "the interpreter you pointed at is gone" and "there
    # is no Python on this machine" are different sentences, and the app used
    # to say the second one while a working 3.11 sat on the PATH: a venv the
    # observer had built was deleted, the configured path stayed, and the
    # panel announced that no Python existed. It looked like a lost
    # configuration (reported 2026-10-20).
    if not preferred:
        return None
    if not Path(preferred).is_file():
        return "missing"
    if not version_ok(preferred):
        return "version"
    return None


def detect_python(preferred=None):
    # @args: preferred - a configured interpreter path or None
    # @return: the path of a Python EXOTIC can live in, or None
    if preferred:
        p = Path(preferred)
        # a venv python the app prepared, or the user's own with EXOTIC
        if p.is_file() and version_ok(p):
            return str(p)
        # A configured interpreter that is gone or of the wrong version does
        # NOT mean there is no Python: fall through and look for one (the
        # caller can ask configured_problem to say what happened to the old
        # one). Refusing to look is what turned a deleted venv into "no Python
        # 3.10 interpreter found" with 3.10 installed.
    if os.name == "nt":       # the py launcher first (Windows)
        for v in _PY_VERSIONS:
            exe = _py_launcher(v)
            if exe:
                return exe
    for name in _CANDIDATES:
        found = shutil.which(name)
        if found and version_ok(found):
            return found
    # a generic python/python3, validated; skip the Store stub
    for name in ("python", "python3"):
        found = shutil.which(name)
        if found and "WindowsApps" not in found and version_ok(found):
            return found
    return None


def probe(python_path):
    # @args: python_path - the interpreter that should host EXOTIC
    # @return: {"ok", "version", "message"}
    if not python_path:
        return {"ok": False, "version": None,
                "message": "no Python 3.10 to 3.12 found"}
    try:
        out = subprocess.run(
            [str(python_path), "-c",
             "import exotic, sys; print(exotic.__version__)"],
            capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as err:
        return {"ok": False, "version": None, "message": str(err)}
    if out.returncode != 0:
        msg = (out.stderr or out.stdout or "").strip().splitlines()
        return {"ok": False, "version": None,
                "message": msg[-1] if msg else "EXOTIC not importable"}
    version = out.stdout.strip()
    return {"ok": True, "version": version, "message": f"EXOTIC {version}"}


def _run(cmd, log, cancel):
    log.append("$ " + " ".join(str(c) for c in cmd))
    if cancel is not None and cancel():
        raise _Cancelled()
    proc = subprocess.run([str(c) for c in cmd], capture_output=True,
                          text=True, timeout=_TIMEOUT_S)
    tail = (proc.stdout or "")[-2000:] + (proc.stderr or "")[-2000:]
    if tail.strip():
        log.append(tail.strip())
    return proc.returncode


def _inside(path, folder):
    # @args: path - a file, folder - a directory
    # @return: True when path lives inside folder
    try:
        Path(path).resolve().relative_to(Path(folder).resolve())
        return True
    except (ValueError, OSError):
        return False


def _swap_in(staging, install_dir, log):
    # @args: staging - the freshly built environment, install_dir - where it
    #        has to end up, log - the build log (the swap is written there)
    # @return: None. The old environment is renamed out of the way, the new
    #          one takes its place and the old one is removed.
    #
    # The rename is atomic on one filesystem, so there is no window where the
    # configured path points at nothing; and if the second rename fails (on
    # Windows a file of the old environment may still be open), the old one
    # goes BACK instead of leaving the observer with neither.
    backup = install_dir.with_name(install_dir.name + ".old")
    shutil.rmtree(backup, ignore_errors=True)
    try:
        if install_dir.exists():
            install_dir.rename(backup)
        staging.rename(install_dir)
    except OSError:
        if backup.exists() and not install_dir.exists():
            backup.rename(install_dir)
        raise
    shutil.rmtree(backup, ignore_errors=True)
    log.append(f"environment installed at {install_dir}")


def prepare(install_dir, base_python, progress=None, cancel=None):
    # Creates the venv (without pip, then bootstrapped) and installs EXOTIC.
    #
    # IT BUILDS ASIDE AND SWAPS AT THE END, and that is not a detail: the
    # environment the observer already has is only replaced once the new one
    # works. The first version wiped the target FIRST, so any failure after
    # that (no network, no disk, a cancel) left nothing behind, and one case
    # destroyed a working environment every single time: the app offers the
    # venv it already built as the base interpreter, and the wipe took that
    # interpreter away halfway through the build, so the next command could
    # not even run. Reported 2026-10-20.
    # @args: install_dir - where the venv lives, base_python - the suitable
    #        interpreter, progress - callable(stage_key),
    #        cancel - callable() -> bool
    # @return: (ok, log_text)
    log = []
    install_dir = Path(install_dir)
    staging = install_dir.with_name(install_dir.name + ".new")
    ok = False
    # a base interpreter INSIDE the folder we are about to replace would be
    # deleted halfway through the build: refuse it, with the reason
    if _inside(base_python, install_dir):
        log.append(
            f"the base interpreter ({base_python}) lives inside the folder "
            f"being built ({install_dir}): point at a Python outside it")
        return False, "\n".join(log)
    try:
        shutil.rmtree(staging, ignore_errors=True)
        if progress:
            progress("venv")
        # a normal venv first (Windows ships pip with it); only if pip is
        # missing (the Linux ensurepip quirk) redo without pip and
        # bootstrap it through the base interpreter
        rc = _run([base_python, "-m", "venv", str(staging)], log, cancel)
        py = venv_python(staging)
        pip = bin_dir(staging) / ("pip.exe" if os.name == "nt" else "pip")
        if rc != 0 or not pip.is_file():
            shutil.rmtree(staging, ignore_errors=True)
            if progress:
                progress("venv")
            rc = _run([base_python, "-m", "venv", "--without-pip",
                       str(staging)], log, cancel)
            if rc != 0:
                return False, "\n".join(log)
            if progress:
                progress("pip")
            rc = _run([base_python, "-m", "pip", "--python", str(py),
                       "install", "--upgrade", "pip", "wheel"], log, cancel)
            if rc != 0:
                return False, "\n".join(log)
        if progress:
            progress("exotic")
        rc = _run([str(py), "-m", "pip", "install", "exotic"], log, cancel)
        if rc != 0:
            return False, "\n".join(log)
        # the new environment works: only now does the old one go
        _swap_in(staging, install_dir, log)
        ok = True
        if progress:
            progress("done")
        return True, "\n".join(log)
    except _Cancelled:
        log.append("cancelled")
        return False, "\n".join(log)
    except (OSError, subprocess.SubprocessError) as err:
        log.append(str(err))
        return False, "\n".join(log)
    finally:
        # A build that did not deliver leaves no half-built folder behind, and
        # the environment that was already there is untouched: the swap is the
        # only thing in here that writes to it.
        if not ok:
            shutil.rmtree(staging, ignore_errors=True)
