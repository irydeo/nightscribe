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

EXOTIC needs Python <= 3.10 and its own heavy stack (astropy, scipy,
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

# EXOTIC only supports Python <= 3.10.
_CANDIDATES = ("python3.10", "python3.9", "python3.8")
_PY_VERSIONS = ("3.10", "3.9", "3.8")
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
    # @return: True when the interpreter is Python <= 3.10
    v = _version_of(python)
    return v is not None and v <= (3, 10)


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


def detect_python(preferred=None):
    # @args: preferred - a configured interpreter path or None
    # @return: the path of a Python <= 3.10 interpreter, or None
    if preferred:
        p = Path(preferred)
        # a venv python the app prepared, or the user's own with EXOTIC
        if p.is_file() and version_ok(p):
            return str(p)
        return None
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
                "message": "no Python <=3.10 found"}
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


def prepare(install_dir, base_python, progress=None, cancel=None):
    # Creates the venv (without pip, then bootstrapped) and installs EXOTIC.
    # @args: install_dir - where the venv lives, base_python - the <=3.10
    #        interpreter, progress - callable(stage_key),
    #        cancel - callable() -> bool
    # @return: (ok, log_text)
    log = []
    install_dir = Path(install_dir)
    try:
        if progress:
            progress("venv")
        # a normal venv first (Windows ships pip with it); only if pip is
        # missing (the Linux ensurepip quirk) redo without pip and
        # bootstrap it through the base interpreter
        rc = _run([base_python, "-m", "venv", str(install_dir)], log, cancel)
        py = venv_python(install_dir)
        pip = bin_dir(install_dir) / ("pip.exe" if os.name == "nt" else "pip")
        if rc != 0 or not pip.is_file():
            shutil.rmtree(install_dir, ignore_errors=True)
            if progress:
                progress("venv")
            rc = _run([base_python, "-m", "venv", "--without-pip",
                       str(install_dir)], log, cancel)
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
        if progress:
            progress("done")
        return True, "\n".join(log)
    except _Cancelled:
        log.append("cancelled")
        return False, "\n".join(log)
    except (OSError, subprocess.SubprocessError) as err:
        log.append(str(err))
        return False, "\n".join(log)
