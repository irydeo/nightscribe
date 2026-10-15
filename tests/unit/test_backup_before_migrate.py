############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the entry point must not migrate on import
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Importing the CLI entry point must not touch the database.

ADR-042: the GUI snapshots the database before the update wizard runs, and
core/db.py migrates the schema the moment it is imported. The snapshot is
therefore only worth something if the entry point has NOT imported core.db
yet. nightscribe.__main__ used to do `from .core.db import db` at module
level (and launcher.py imports this entry point), so by the time the GUI
asked for the backup the schema was already migrated: there was no rollback
and the Welcome report always said "everything is up to date".

The check runs in a subprocess so it sees a fresh interpreter, independent
of whatever the rest of the suite has already imported.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

_PROBE = ("import sys, nightscribe.__main__;"
          "print('nightscribe.core.db' in sys.modules)")


def test_importing_the_entry_point_does_not_import_the_database():
    out = subprocess.run([sys.executable, "-c", _PROBE],
                         capture_output=True, text=True, cwd=str(ROOT))
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "False", out.stdout + out.stderr


def test_the_database_is_reached_lazily():
    # The other half of the contract: the connection is still reachable when
    # a command actually needs it (the lazy import must not have broken the
    # CLI). Run `project list` against a throwaway data dir so nothing of the
    # observer's is touched.
    import os
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ)
        env["XDG_DATA_HOME"] = tmp
        env["LOCALAPPDATA"] = tmp              # Windows
        env["XDG_CONFIG_HOME"] = tmp
        env["APPDATA"] = tmp                   # Windows
        out = subprocess.run(
            [sys.executable, "-c",
             "import nightscribe.__main__ as m;"
             "print(m.main(['project', 'list']))"],
            env=env, capture_output=True, text=True, cwd=str(ROOT))
    assert out.returncode == 0, out.stderr
    assert "nightscribe.core.db" not in out.stderr
