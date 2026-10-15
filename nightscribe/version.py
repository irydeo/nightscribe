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

import logging
from importlib.metadata import PackageNotFoundError
from pathlib import Path

logger = logging.getLogger(__name__)


def _packaged_version():
    # The version a Linux package writes next to its data
    # (/usr/share/nightscribe/version, see tools/build_deb.py). It is the
    # fallback for a system install that somehow lacks the dist-info the
    # metadata lookup needs; without it the app would report "0.0.0" and the
    # update detection would never fire (the bug fixed on 2026-10-14).
    # @args: none
    # @return: the packaged version string, or None
    try:
        text = Path("/usr/share/nightscribe/version").read_text(
            encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def base_version():
    # @args: none
    # @return: e.g. "0.1.0" — the installed distribution version when
    #         available, else the packaged version file, else the
    #         __version__ from the package.
    try:
        from importlib.metadata import version
        return version("nightscribe")
    except PackageNotFoundError:
        packaged = _packaged_version()
        if packaged:
            return packaged
        from . import __version__
        if __version__ == "0.0.0":
            # Never silent: an unknown version is what broke the update
            # detection, so it deserves a line in the log.
            logger.warning(
                "package version unknown (no dist-info and no packaged "
                "version file): reporting 0.0.0")
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
