############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: v19 migration (the remembered gain)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""v19 acceptance (ADR-072 rev): the gains table appears additively and
idempotently, and a hand-built v18 database walks to v19 without losing
anything. No network."""

from nightscribe.core.db import Database

_COLS = {"camera", "gain_setting", "binning", "gain_e_per_adu", "ron_e",
         "source", "measured_at", "n_boxes", "n_kept"}


def _columns(db, table):
    return {r[1] for r in db.execute(f"PRAGMA table_info({table})")}


def test_v19_adds_the_gains_table(tmp_path):
    db = Database(str(tmp_path / "g.db"))
    assert _COLS <= _columns(db, "gains")
    assert db.execute("PRAGMA user_version").fetchone()[0] >= 19


def test_v19_is_idempotent(tmp_path):
    path = str(tmp_path / "g.db")
    Database(path).close()
    db = Database(path)          # reopening must not fail or duplicate
    assert db.execute("PRAGMA user_version").fetchone()[0] >= 19
    assert db.execute("SELECT COUNT(*) FROM gains").fetchone()[0] == 0


def test_a_v18_database_walks_to_v19_untouched(tmp_path):
    path = str(tmp_path / "g.db")
    db = Database(path)
    db.execute("INSERT INTO projects (kind, object_name, status, created,"
               " updated, context) VALUES ('sn', 'SN 2026x', 'active',"
               " 1.0, 1.0, '{}')")
    db.execute("DROP TABLE gains")
    db.execute("PRAGMA user_version = 18")
    db.commit()
    db.close()
    db = Database(path)          # the migration runs again
    assert db.execute("PRAGMA user_version").fetchone()[0] == 19
    assert _COLS <= _columns(db, "gains")
    assert db.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 1
