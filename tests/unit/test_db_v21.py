############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: v21 migration (a dark of the flats is a dark)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""v21 acceptance (ADR-061 rev): the "dark_flat" rows move to "dark", the
exposure being what tells them apart; the step is idempotent and a database
whose calib_masters table is gone still walks to the top (QA-06, QA-17)."""

from nightscribe.core.db import Database


def test_v21_folds_the_flat_dark_into_dark(tmp_path):
    path = str(tmp_path / "c.db")
    db = Database(path)
    db.execute("INSERT INTO calib_masters (kind, path, exptime_s)"
               " VALUES ('dark_flat', '/tmp/x.fit', 2.5)")
    db.execute("PRAGMA user_version = 20")
    db.commit()
    db.close()
    db = Database(path)          # the migration runs again
    rows = db.execute("SELECT kind, exptime_s FROM calib_masters").fetchall()
    assert rows == [("dark", 2.5)]
    assert db.execute("PRAGMA user_version").fetchone()[0] >= 21


def test_v21_is_idempotent(tmp_path):
    path = str(tmp_path / "c.db")
    db = Database(path)
    db.execute("INSERT INTO calib_masters (kind, path)"
               " VALUES ('dark', '/tmp/y.fit')")
    db.execute("PRAGMA user_version = 20")
    db.commit()
    db.close()
    db = Database(path)
    assert db.execute("SELECT COUNT(*) FROM calib_masters").fetchone()[0] == 1


def test_a_v20_database_without_calib_masters_still_walks(tmp_path):
    # A restored database can be at v20 with the calibration library gone: the
    # UPDATE used to die with "no such table" and the app would not open. v22
    # (main's, 2026-10-15) had the same hole in its ALTER and is guarded too,
    # which this test also covers.
    path = str(tmp_path / "c.db")
    db = Database(path)
    db.execute("DROP TABLE calib_masters")
    db.execute("PRAGMA user_version = 20")
    db.commit()
    db.close()
    db = Database(path)          # must not raise
    assert db.execute("PRAGMA user_version").fetchone()[0] >= 21
