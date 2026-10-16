############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: v16 migration (image calibration)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""v16 acceptance: the calib_masters table and its index, idempotent, and
usable through the calibration module (ADR-061). A hand-built v15 database
walks to v16 without touching anything else."""

import sqlite3

import numpy as np
from astropy.io import fits

from nightscribe.core import calibration as cal
from nightscribe.core.db import Database


def _v15_database(path):
    # A hand-built pre-v16 database: only the version marker is needed, as
    # _migrate lays down the base schema before walking the steps.
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA user_version = 15")
    conn.commit()
    conn.close()


def _columns(db):
    return {r[1] for r in db.execute("PRAGMA table_info(calib_masters)")}


def test_v15_walks_to_v16(tmp_path):
    db_file = tmp_path / "old.db"
    _v15_database(db_file)
    db = Database(db_file)
    assert db.execute("PRAGMA user_version").fetchone()[0] == 24
    assert {"kind", "path", "camera", "gain", "temp_c", "exptime_s",
            "filter", "created", "meta"} <= _columns(db)
    # The index the matching leans on.
    names = {r[0] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='index'")}
    assert "idx_calib_key" in names


def test_v16_is_idempotent(tmp_path):
    db_file = tmp_path / "fresh.db"
    Database(db_file).close()
    Database(db_file).close()          # reopening must be a no-op
    db = Database(db_file)
    assert db.execute("PRAGMA user_version").fetchone()[0] == 24


def test_v21_merges_the_dark_of_the_flats_into_the_darks(tmp_path):
    # ADR-061 rev: a "dark of the flats" is a dark at the flat's exposure,
    # so the rows move over instead of asking the observer to keep two
    # entries for one frame.
    db_file = tmp_path / "with_darkflat.db"
    db = Database(db_file)          # current version, base schema laid down
    db.execute("INSERT INTO calib_masters (kind, path) VALUES (?, ?)",
               ("dark_flat", "/m/df.fits"))
    db.execute("INSERT INTO calib_masters (kind, path) VALUES (?, ?)",
               ("dark", "/m/d.fits"))
    # walk BACK to v20 (a restored backup), so reopening runs the step
    db.execute("PRAGMA user_version = 20")
    db.commit()
    db.close()
    db = Database(db_file)
    kinds = [r[0] for r in db.execute(
        "SELECT kind FROM calib_masters ORDER BY id")]
    assert kinds == ["dark", "dark"]


def test_calibration_module_uses_the_new_table(tmp_db, tmp_path):
    master = tmp_path / "dark.fits"
    fits.PrimaryHDU(np.full((4, 4), 7.0, dtype=np.float32)).writeto(str(master))
    master_id = cal.add_master(tmp_db, str(master),
                               {"kind": "dark", "camera": "TestCam",
                                "gain": 1.0, "temp_c": -10.0,
                                "exptime_s": 30.0, "filter": "R"})
    assert master_id
    refs = cal.list_masters(tmp_db, kind="dark")
    assert len(refs) == 1 and refs[0].path == str(master)
