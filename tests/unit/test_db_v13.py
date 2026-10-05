############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: v13 migration (the point's own error)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""v13 acceptance (quality plan, phase A): a point carries its own photon
error (`err_internal`) apart from the calibration systematic that `err`
(the total) keeps. Idempotent, legacy rows survive with NULL, and the
batch writer round-trips it. The total stays what AAVSO and the CSV see.
"""

import sqlite3

from nightscribe.core import followup as fu
from nightscribe.core.db import Database

_V12_POINTS = """
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
    file_id    INTEGER,
    mag_raw    REAL,
    flags      TEXT,
    run_id     INTEGER
);
CREATE TABLE measurement_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER,
    created     REAL NOT NULL,
    cfg_json    TEXT DEFAULT '{}',
    status      TEXT NOT NULL DEFAULT 'complete'
);
"""


def _v12_database(path):
    # A hand-built v12 database with one series point and one legacy
    # point, user_version 12.
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
    """ + _V12_POINTS)
    conn.execute("INSERT INTO projects (kind, object_name, status, created,"
                 " updated) VALUES ('variable', 'V0526 Per', 'active',"
                 " 1.0, 1.0)")
    conn.execute("INSERT INTO project_sessions (project_id, obs_date,"
                 " created) VALUES (1, '2023-12-19', 1.0)")
    conn.execute("INSERT INTO photometry_points (project_id, session_id,"
                 " mjd, filter, mag, err, source, mag_raw, flags)"
                 " VALUES (1, 1, 60297.77, 'V', 12.58, 0.17, 'measure',"
                 " -13.40, '[]')")
    conn.execute("PRAGMA user_version = 12")
    conn.commit()
    conn.close()
    return path


def _columns(db, table):
    return {r[1] for r in db.execute(f"PRAGMA table_info({table})")}


def test_upgrade_from_v12_adds_err_internal(tmp_path):
    f = _v12_database(tmp_path / "v12.db")
    db = Database(str(f))
    assert db.execute("PRAGMA user_version").fetchone()[0] == 18
    assert "err_internal" in _columns(db, "photometry_points")
    row = db.execute("SELECT mag, err, err_internal, mag_raw FROM"
                     " photometry_points WHERE id=1").fetchone()
    # the legacy point survived untouched; the total is still the total
    assert row[0] == 12.58 and row[1] == 0.17
    assert row[2] is None and row[3] == -13.40
    db.close()


def test_reopen_is_idempotent(tmp_path):
    f = tmp_path / "t.db"
    Database(str(f)).close()
    db = Database(str(f))
    assert db.execute("PRAGMA user_version").fetchone()[0] == 18
    assert "err_internal" in _columns(db, "photometry_points")
    db.close()


def test_err_internal_round_trips_and_err_stays_the_total(tmp_path):
    db = Database(str(tmp_path / "r.db"))
    db.execute("INSERT INTO projects (kind, object_name, status, created,"
               " updated) VALUES ('variable', 'X', 'active', 1.0, 1.0)")
    db.execute("INSERT INTO project_sessions (project_id, obs_date, created)"
               " VALUES (1, '2026-09-20', 1.0)")
    db.commit()
    run = fu.create_run(db, session_id=1, cfg={"band": "V"})
    ids = fu.add_points(db, [
        {"project_id": 1, "session_id": 1, "mjd": 60000.1, "filter": "V",
         "mag": 12.58, "err": 0.176, "err_internal": 0.0052,
         "mag_raw": -13.40, "flags": [], "run_id": run, "source": "measure"},
        {"project_id": 1, "session_id": 1, "mjd": 60000.2, "filter": "V",
         "mag": None, "err": None, "mag_raw": None, "flags": ["seeing"],
         "run_id": run, "source": "measure"}])
    assert len(ids) == 2
    pts = fu.list_points_for_run(db, run)
    assert pts[0]["err"] == 0.176
    assert pts[0]["err_internal"] == 0.0052
    assert pts[1]["err_internal"] is None
    # the single-point reader carries it too (the export and the panel use it)
    assert fu.point_by_id(db, ids[0])["err_internal"] == 0.0052
    db.close()


def test_legacy_single_point_has_no_internal_error(tmp_path):
    db = Database(str(tmp_path / "l.db"))
    db.execute("INSERT INTO projects (kind, object_name, status, created,"
               " updated) VALUES ('sn', 'X', 'active', 1.0, 1.0)")
    db.commit()
    pid = fu.add_point(db, 1, 60000.0, "V", 12.0, err=0.02)
    p = fu.point_by_id(db, pid)
    assert p["err"] == 0.02 and p["err_internal"] is None
    db.close()
