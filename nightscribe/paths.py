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
    # @return: Path to the documentation folder, or None when there is none.
    # The three places a running copy looks, in order: the PyInstaller
    # bundle (Windows installer and portable build), a checkout run from
    # source, and a system install (the .deb, the .rpm, the PKGBUILD and a
    # `pip install`, which drop the guide in share/nightscribe/docs). Until
    # 2026-10-15 the Linux packages and the wheel shipped WITHOUT it, so
    # Help > Documentation, the UFE's "?" and the offline assistant index
    # came up empty everywhere except Windows.
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "docs"
    candidates = [
        Path(__file__).resolve().parent.parent / "docs",
        Path(sys.prefix) / "share" / "nightscribe" / "docs",
        Path("/usr/share/nightscribe/docs"),
    ]
    for cand in candidates:
        if cand.is_dir():
            return cand
    return candidates[0]


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


# The prefix every scratch entry the app writes to the SYSTEM temp folder
# carries, so a sweep can tell the app's own leftovers from everyone else's
# (a run's `fo` folder, the phase chart's scratch, a captured frame).
TEMP_PREFIX = "nightscribe-"


def sweep_temp(max_age_s=24 * 3600):
    # Removes the app's OWN leftovers in the system temp folder. The app
    # writes there for work that has to exist as a PATH (Find_Orb's folders,
    # the phase chart's scratch PNG, a captured frame the editor reads by
    # path) and removes each one when it is done; a crash or a kill leaves
    # it behind, so the OLD ones go at startup. Only entries older than
    # `max_age_s` are touched, which is what keeps a second instance working
    # RIGHT NOW out of it.
    # @args: max_age_s - how old a leftover must be (seconds)
    # @return: how many entries were removed
    import shutil
    import tempfile
    import time
    root = Path(tempfile.gettempdir())
    now = time.time()
    removed = 0
    for entry in root.glob(TEMP_PREFIX + "*"):
        try:
            if now - entry.stat().st_mtime < max_age_s:
                continue
            if entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink(missing_ok=True)
            removed += 1
        except OSError:
            continue
    return removed
