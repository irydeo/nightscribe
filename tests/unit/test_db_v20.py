############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: v20 migration (the point's error and provenance)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""v20 acceptance (ADR-085/086): astrometry_points gains mag_err and
centroid_source, and the project-level combined table appears; all additive
and idempotent, and a database whose astrometry table is gone still walks to
the top instead of failing to open (QA-06)."""

from nightscribe.core.db import Database


def _columns(db, table):
    return {r[1] for r in db.execute(f"PRAGMA table_info({table})")}


def _tables(db):
    return {r[0] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}


def test_v20_adds_the_error_and_the_combined_table(tmp_path):
    db = Database(str(tmp_path / "m.db"))
    assert {"mag_err", "centroid_source"} <= _columns(db, "astrometry_points")
    assert "astrometry_combined" in _tables(db)
    assert db.execute("PRAGMA user_version").fetchone()[0] >= 20


def test_v20_is_idempotent(tmp_path):
    path = str(tmp_path / "m.db")
    Database(path).close()
    db = Database(path)
    assert {"mag_err", "centroid_source"} <= _columns(db, "astrometry_points")
    assert "astrometry_combined" in _tables(db)


def test_a_v19_database_without_astrometry_points_still_walks(tmp_path):
    # Same guard as v18: the ALTER must not run on a table that is not there
    # (QA-06). The combined table is created either way.
    path = str(tmp_path / "m.db")
    db = Database(path)
    db.execute("DROP TABLE astrometry_points")
    db.execute("PRAGMA user_version = 19")
    db.commit()
    db.close()
    db = Database(path)          # must not raise
    assert db.execute("PRAGMA user_version").fetchone()[0] == 21
    assert "astrometry_combined" in _tables(db)
