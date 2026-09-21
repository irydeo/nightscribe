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


def docs_dir():
    # @return: Path to the documentation folder (docs/ bundled by the
    # PyInstaller spec, or the repository one when running from source)
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "docs"
    return Path(__file__).resolve().parent.parent / "docs"


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
