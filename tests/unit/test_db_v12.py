############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: v12 migration (photometric series)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""v12 acceptance: mag_raw/flags/run_id on photometry_points plus the
measurement_runs table, idempotent, with the batch writers and the
per-run undo. Legacy points keep their visit link untouched (ADR-048).
"""

import sqlite3

from nightscribe.core import followup as fu
from nightscribe.core.db import Database

_V11_POINTS = """
CREATE TABLE photometry_points (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL REFERENCES projects(id)
                ON DELETE CASCADE,
    session_id  INTEGER REFERENCES project_sessions(id)
                ON DELETE SET NULL,
    mjd        REAL,
    filter     TEXT,
    mag        REAL,
    err        REAL,
    source     TEXT,
    file_id    INTEGER
);
"""


def _v11_database(path):
    # A hand-built pre-v12 database: the v5 photometry_points (plus the
    # v11 file_id), a legacy point tied to a visit, user_version 11.
    conn = sqlite3.connect(str(path))
    conn.executescript("""
    CREATE TABLE projects (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        kind        TEXT, object_name TEXT, status TEXT,
        created     REAL, updated   REAL, context TEXT DEFAULT '{}'
    );
    CREATE TABLE project_sessions (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id  INTEGER NOT NULL REFERENCES projects(id)
                    ON DELETE CASCADE,
        obs_date    TEXT, notes TEXT DEFAULT '', created REAL NOT NULL,
        pinned      INTEGER DEFAULT 0
    );
    """ + _V11_POINTS)
    conn.execute("INSERT INTO projects (kind, object_name, status, created,"
                 " updated) VALUES ('transit', 'HAT-P-32 b', 'active',"
                 " 1.0, 1.0)")
    conn.execute("INSERT INTO project_sessions (project_id, obs_date,"
                 " created) VALUES (1, '2026-09-20', 1.0)")
    conn.execute("INSERT INTO photometry_points (project_id, session_id,"
                 " mjd, filter, mag, err, source) VALUES (1, 1, 60000.1,"
                 " 'V', 12.3, 0.05, 'measure')")
    conn.execute("PRAGMA user_version = 11")
    conn.commit()
    conn.close()
    return path


def _columns(db, table):
    return {r[1] for r in db.execute(f"PRAGMA table_info({table})")}


def test_upgrade_from_v11_adds_the_series_schema(tmp_path):
    f = _v11_database(tmp_path / "v11.db")
    db = Database(str(f))
    assert db.execute("PRAGMA user_version").fetchone()[0] == 17
    cols = _columns(db, "photometry_points")
    assert {"mag_raw", "flags", "run_id"} <= cols
    tables = {r[0] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "measurement_runs" in tables
    # the legacy point survived, its visit link intact and the new
    # columns NULL (never rewritten)
    row = db.execute("SELECT session_id, mag, mag_raw, flags, run_id"
                     " FROM photometry_points WHERE id=1").fetchone()
    assert row[0] == 1 and row[1] == 12.3
    assert row[2] is None and row[3] is None and row[4] is None
    db.close()


def test_fresh_database_has_v13(tmp_path):
    db = Database(str(tmp_path / "fresh.db"))
    assert db.execute("PRAGMA user_version").fetchone()[0] == 17
    assert {"mag_raw", "flags", "run_id", "err_internal"} <= _columns(
        db, "photometry_points")
    db.close()


def test_reopen_is_idempotent(tmp_path):
    f = tmp_path / "t.db"
    Database(str(f)).close()
    db = Database(str(f))
    assert db.execute("PRAGMA user_version").fetchone()[0] == 17
    assert {"mag_raw", "flags", "run_id"} <= _columns(db,
                                                      "photometry_points")
    db.close()


def _seed_project(db):
    db.execute("INSERT INTO projects (kind, object_name, status, created,"
               " updated) VALUES ('transit', 'HAT-P-32 b', 'active',"
               " 1.0, 1.0)")
    db.execute("INSERT INTO project_sessions (project_id, obs_date,"
               " created) VALUES (1, '2026-09-20', 1.0)")
    db.commit()


def test_batch_writer_and_per_run_undo(tmp_path):
    db = Database(str(tmp_path / "s.db"))
    _seed_project(db)
    run_a = fu.create_run(db, session_id=1, cfg={"band": "V", "group_n": 1})
    run_b = fu.create_run(db, session_id=1, cfg={"band": "V"})
    assert run_a and run_b and run_a != run_b
    ids_a = fu.add_points(db, [
        {"project_id": 1, "session_id": 1, "mjd": 60000.1, "filter": "V",
         "mag": 12.30, "err": 0.01, "source": "measure", "mag_raw": -9.5,
         "flags": [], "run_id": run_a},
        {"project_id": 1, "session_id": 1, "mjd": 60000.2, "filter": "V",
         "mag": None, "err": None, "source": "measure", "mag_raw": None,
         "flags": ["saturated", "cloud"], "run_id": run_a}])
    ids_b = fu.add_points(db, [
        {"project_id": 1, "session_id": 1, "mjd": 60001.1, "filter": "V",
         "mag": 12.31, "err": 0.01, "source": "measure", "mag_raw": -9.4,
         "flags": [], "run_id": run_b}])
    assert len(ids_a) == 2 and len(ids_b) == 1
    # flags round-trip as a list, mag_raw as a number
    pts = fu.list_points_for_run(db, run_a)
    assert [p["flags"] for p in pts] == [[], ["saturated", "cloud"]]
    assert pts[0]["mag_raw"] == -9.5
    # undo run A: only its points go, B is untouched
    assert fu.delete_points_for_run(db, run_a) == 2
    fu.set_run_status(db, run_a, "undone")
    assert fu.list_points_for_run(db, run_a) == []
    assert len(fu.list_points_for_run(db, run_b)) == 1
    assert len(fu.list_points(db, 1)) == 1
    db.close()


def test_delete_points_by_ids(tmp_path):
    db = Database(str(tmp_path / "d.db"))
    _seed_project(db)
    ids = fu.add_points(db, [
        {"project_id": 1, "session_id": 1, "mjd": 60000.0 + i,
         "filter": "V", "mag": 12.0, "source": "measure", "run_id": None}
        for i in range(3)])
    assert fu.delete_points(db, ids[:2]) == 2
    assert [p["id"] for p in fu.list_points(db, 1)] == [ids[2]]
    db.close()


def test_legacy_add_point_contract_is_unchanged(tmp_path):
    # D18: the single-point path still writes flags/mag_raw/run_id NULL
    # and keeps the visit link.
    db = Database(str(tmp_path / "l.db"))
    _seed_project(db)
    pid = fu.add_point(db, 1, 60000.0, "V", 12.0, err=0.02,
                       source="measure", session_id=1)
    p = fu.point_by_id(db, pid)
    assert p["session_id"] == 1
    assert p["mag_raw"] is None and p["run_id"] is None
    assert p["flags"] == []
    db.close()
