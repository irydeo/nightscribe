############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the layers' import boundaries
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Two AGENTS.md rules that a future PR could break without anything
failing, so a test holds them instead of discipline:

- every network call goes through `core/sources/` (never `requests`
  elsewhere), so the cache in `core/db.py` cannot be bypassed;
- the GUI does not open SQLite itself: it goes through `core/`.

No network, no Qt: it only reads the source tree.
"""

import re
from pathlib import Path

PKG = Path(__file__).resolve().parents[2] / "nightscribe"


def _py_files():
    # @return: every module of the package
    return sorted(PKG.rglob("*.py"))


def test_requests_is_only_imported_in_core_sources():
    offenders = []
    for p in _py_files():
        text = p.read_text(encoding="utf-8")
        if re.search(r"^\s*(?:import requests\b|from requests\b)", text,
                     re.M):
            rel = p.relative_to(PKG).as_posix()
            if not rel.startswith("core/sources/"):
                offenders.append(rel)
    assert not offenders, (
        "requests must live in core/sources/ only (all network goes through "
        "core/db.py): " + ", ".join(offenders))


def test_the_gui_does_not_open_sqlite_itself():
    offenders = []
    for p in _py_files():
        rel = p.relative_to(PKG).as_posix()
        if not rel.startswith("gui/"):
            continue
        text = p.read_text(encoding="utf-8")
        if re.search(r"^\s*(?:import sqlite3\b|from sqlite3\b)", text, re.M):
            offenders.append(rel)
    assert not offenders, (
        "the GUI must not touch SQLite directly: " + ", ".join(offenders))
