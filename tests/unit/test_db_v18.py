############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: v18 migration (the measured magnitude)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""v18 acceptance (ADR-085): astrometry_points gains mag_auto and
mag_source additively and idempotently, and a database whose astrometry
table is gone still walks to the top instead of failing to open (QA-06)."""

from nightscribe.core.db import Database


def _columns(db, table):
    return {r[1] for r in db.execute(f"PRAGMA table_info({table})")}


def test_v18_adds_the_magnitude_provenance(tmp_path):
    db = Database(str(tmp_path / "m.db"))
    assert {"mag_auto", "mag_source"} <= _columns(db, "astrometry_points")
    assert db.execute("PRAGMA user_version").fetchone()[0] >= 18


def test_v18_is_idempotent(tmp_path):
    path = str(tmp_path / "m.db")
    Database(path).close()
    db = Database(path)
    assert {"mag_auto", "mag_source"} <= _columns(db, "astrometry_points")


def test_a_v17_database_without_astrometry_points_still_walks(tmp_path):
    # A restored or hand-edited database can sit at v17 with the astrometry
    # table missing. The ALTER used to die with "no such table: 
    # astrometry_points" and Database() raised, so the app would not open at
    # all (QA-06). The migration now guards the table.
    path = str(tmp_path / "m.db")
    db = Database(path)
    db.execute("DROP TABLE astrometry_points")
    db.execute("PRAGMA user_version = 17")
    db.commit()
    db.close()
    db = Database(path)          # must not raise
    assert db.execute("PRAGMA user_version").fetchone()[0] == 21
