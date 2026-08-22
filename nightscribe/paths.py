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


def image_cache_dir():
    # @return: Path to the cached image dir (SDO, cutouts...)
    p = data_dir() / "images"
    p.mkdir(parents=True, exist_ok=True)
    return p
