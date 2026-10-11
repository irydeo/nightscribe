############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Per-OS paths module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import re
import sys
from pathlib import Path

import platformdirs

from . import __app_name__

# Single access point for per-OS directories, so the rest of the code
# never hard-codes paths (Windows and Linux both supported, see ADR-001).


def config_dir():
    # @return: Path to the user config dir (created if missing)
    p = platformdirs.user_config_path(__app_name__)
    p.mkdir(parents=True, exist_ok=True)
    return p


def data_dir():
    # @return: Path to the user data dir (SQLite db, cached images...)
    p = platformdirs.user_data_path(__app_name__)
    p.mkdir(parents=True, exist_ok=True)
    return p


def db_path():
    # @return: Path to the SQLite database file
    return data_dir() / "nightscribe.db"


def backups_dir():
    # @return: the backups folder (SQLite copies the update wizard keeps
    #          before touching the database, ADR-042)
    p = data_dir() / "backups"
    p.mkdir(parents=True, exist_ok=True)
    return p


def image_cache_dir():
    # @return: Path to the cached image dir (SDO, cutouts...)
    p = data_dir() / "images"
    p.mkdir(parents=True, exist_ok=True)
    return p


def astap_dir():
    # @return: the folder of the local ASTAP solver's outputs (the `-o`
    #          base: the solver's .ini/.wcs/.log land here instead of next
    #          to the observer's images, ADR-051)
    p = data_dir() / "astap"
    p.mkdir(parents=True, exist_ok=True)
    return p


def log_path():
    # @return: Path of the application log. It lives in the app's own data
    #          folder (the same place as the database) and it exists because
    #          a GUI launched from a menu has NO console: a report like "a
    #          dialog appears and disappears and I do not know what happens"
    #          left no trace anywhere. Help > Open the log shows this file.
    p = data_dir()
    p.mkdir(parents=True, exist_ok=True)
    return p / "nightscribe.log"


def docs_dir():
    # @return: Path to the documentation folder (docs/ bundled by the
    # PyInstaller spec, or the repository one when running from source)
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "docs"
    return Path(__file__).resolve().parent.parent / "docs"


def findorb_bundle_dir():
    # @return: the folder of the Find_Orb copy NightScribe ships (the `fo`
    #          binary plus its share/findorb data), or None when there is
    #          none (a source tree without it). This is what makes the check
    #          work out of the box: install NightScribe and Find_Orb is
    #          already there, no path to set.
    # The three places a running copy looks, in order: the PyInstaller bundle
    # (Windows installer and portable build), a system install (the .deb and
    # the .rpm drop it in /usr/lib/nightscribe/findorb) and a checkout that
    # has one next to the package.
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys._MEIPASS) / "findorb")
    candidates += [
        Path("/usr/lib/nightscribe/findorb"),
        Path("/usr/share/nightscribe/findorb"),
        Path(__file__).resolve().parent.parent / "findorb",
    ]
    for cand in candidates:
        if cand.is_dir():
            return cand
    return None


def findorb_home_dir():
    # @return: a PRIVATE home for the Find_Orb subprocess.
    # Find_Orb copies its data to `$HOME/.find_orb` on the first run, and it
    # reads the JPL ephemeris from there. Pointing HOME at this folder keeps
    # all of that inside NightScribe's own data dir instead of the observer's
    # real home, and it is what makes the copy we SHIP work: that `fo` was
    # built with its package manager's prefix baked in, so on its own it
    # would try to copy data from a path that no longer exists. We seed
    # `.find_orb` from the shipped data instead (see core/findorb).
    p = data_dir() / "findorb" / "home"
    p.mkdir(parents=True, exist_ok=True)
    return p


def project_dir(project_id, slug="", root=""):
    # @args: project_id - int, slug - object name (sanitised to a safe folder
    #        name; non-alphanumeric chars become _, capped at 50 chars),
    #        root - base folder hosting the project container; empty means the
    #        legacy platformdirs data dir's projects/ folder (ADR-032)
    # @return: Path to the per-project export folder (created if missing).
    #          Exports go here instead of the flat exports/ dir (Track A, A4).
    safe = re.sub(r'[^a-zA-Z0-9_-]', '_', slug or "")[:50]
    base = Path(root) if root else data_dir() / "projects"
    p = base / f"{project_id}-{safe}"
    p.mkdir(parents=True, exist_ok=True)
    return p
