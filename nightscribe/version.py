############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Version reporting
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

# Single place to answer "which NightScribe am I running on?":
# the semver of the installed distribution (or the packaged one when
# running from a tree / frozen), plus the short git commit when the
# repo is around so dev builds are easy to tell apart.

from importlib.metadata import PackageNotFoundError
from pathlib import Path


def base_version():
    # @args: none
    # @return: e.g. "0.1.0" — the installed distribution version when
    #         available, else the __version__ from the package.
    try:
        from importlib.metadata import version
        return version("nightscribe")
    except PackageNotFoundError:
        from . import __version__
        return __version__


def git_sha():
    # @args: none
    # @return: the short commit of the repo this tree lives in (e.g.
    #         "5c295cb"), or "" when there is no git (frozen builds,
    #         sdist) — silent by design.
    import subprocess
    here = Path(__file__).resolve().parent
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(here), capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def git_dirty():
    # @args: none
    # @return: True if the working tree has uncommitted changes.
    import subprocess
    here = Path(__file__).resolve().parent
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(here), capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.SubprocessError):
        return False
    return bool(out.stdout.strip()) if out.returncode == 0 else False


def full_version():
    # @args: none
    # @return: e.g. "0.1.0 (5c295cb)" or "0.2.0.dev3+g5c295cb (5c295cb)*"
    v = base_version()
    sha = git_sha()
    parts = [v]
    if sha:
        parts.append(f"({sha})")
    if git_dirty():
        parts.append("*")
    return " ".join(parts)
