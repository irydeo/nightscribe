############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: SN follow-up model (Track B, B0)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

from nightscribe.core import project, followup


# ---------------- B0: migration + tables exist ----------------

def test_fresh_db_has_followup_tables(tmp_db):
    tables = {r[0] for r in tmp_db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    # ADR-045: session_images is gone; visit images live in the single
    # registry (project_files with the visit link and the meta JSON)
    assert {"project_sessions", "photometry_points"} <= tables
    assert "session_images" not in tables
    cols = {r[1] for r in tmp_db.execute(
        "PRAGMA table_info(project_files)").fetchall()}
    assert {"session_id", "meta"} <= cols


def test_migration_v3_to_current_preserves_projects(tmp_path):
    # A pre-Track-B database (user_version 3) with a project must keep
    # every row and gain the follow-up tables on reopen; ADR-045 walks it
    # further: the process step is renamed analysis (v8) and the visit
    # images move into the single registry (v9).
    import sqlite3
    import time
    from nightscribe.core import db as dbmod
    from nightscribe.core.db import Database

    file = tmp_path / "v3.db"
    conn = sqlite3.connect(str(file))
    conn.executescript(dbmod._SCHEMA)
    conn.executescript(dbmod._V1)
    conn.execute("ALTER TABLE observations ADD COLUMN project_id INTEGER")
    now = time.time()
    conn.execute(
        "INSERT INTO projects (kind, object_name, status, created, updated,"
        " context) VALUES ('sn', 'SN2026b', 'active', ?, ?, '{}')", (now, now))
    conn.execute(
        "INSERT INTO project_steps (project_id, step, status, data, updated)"
        " VALUES (1, 'process', 'current', '{}', ?)", (now,))
    conn.execute("PRAGMA user_version = 3")
    conn.commit()
    conn.close()

    db = Database(str(file))
    assert db.execute("PRAGMA user_version").fetchone()[0] == 9
    # project survived
    row = db.execute(
        "SELECT kind, object_name FROM projects WHERE id=1").fetchone()
    assert row[0] == "sn" and row[1] == "SN2026b"
    # the step kept its status through the rename
    row = db.execute(
        "SELECT step, status FROM project_steps WHERE project_id=1").fetchone()
    assert row == ("analysis", "current")
    # tables exist; the old per-visit image table is gone
    tables = {r[0] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "project_sessions" in tables
    assert "session_images" not in tables


def test_migration_v9_moves_session_images_into_the_registry(tmp_path):
    # A v8 database with a visit and a registered image: on reopen the
    # image lands in project_files with kind "fits", the visit link and
    # the header facts in meta (ADR-045).
    import sqlite3
    import time
    from nightscribe.core import db as dbmod
    from nightscribe.core.db import Database

    file = tmp_path / "v8.db"
    conn = sqlite3.connect(str(file))
    conn.executescript(dbmod._SCHEMA)
    conn.executescript(dbmod._V1)
    conn.execute("ALTER TABLE observations ADD COLUMN project_id INTEGER")
    now = time.time()
    conn.execute(
        "INSERT INTO projects (kind, object_name, status, created, updated,"
        " context) VALUES ('sn', 'SN2026b', 'active', ?, ?, '{}')", (now, now))
    conn.executescript("""
    CREATE TABLE project_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL,
        obs_date TEXT, notes TEXT DEFAULT '', created REAL NOT NULL);
    CREATE TABLE session_images (
        id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER NOT NULL,
        filter TEXT, fits_path TEXT, date_obs TEXT, exptime_s REAL);
    CREATE TABLE photometry_points (
        id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL,
        session_id INTEGER, mjd REAL, filter TEXT, mag REAL, err REAL,
        source TEXT);
    """)
    conn.execute("INSERT INTO project_sessions (project_id, obs_date,"
                 " created) VALUES (1, '2026-09-20', ?)", (now,))
    conn.execute("INSERT INTO session_images (session_id, filter,"
                 " fits_path, date_obs, exptime_s) VALUES (1, 'V',"
                 " '/data/sn_v.fits', '2026-09-20T23:10:00', 120.0)")
    conn.execute("PRAGMA user_version = 8")
    conn.commit()
    conn.close()

    db = Database(str(file))
    assert db.execute("PRAGMA user_version").fetchone()[0] == 9
    row = db.execute(
        "SELECT path, kind, session_id, meta FROM project_files"
        " WHERE project_id=1").fetchone()
    assert row[0] == "/data/sn_v.fits" and row[1] == "fits"
    assert row[2] == 1
    import json
    meta = json.loads(row[3])
    assert meta["filter"] == "V" and meta["exptime_s"] == 120.0
    tables = {r[0] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "session_images" not in tables


def test_migration_v5_is_idempotent(tmp_path):
    import sqlite3
    import time
    from nightscribe.core import db as dbmod
    from nightscribe.core.db import Database

    file = tmp_path / "v3.db"
    conn = sqlite3.connect(str(file))
    conn.executescript(dbmod._SCHEMA)
    conn.executescript(dbmod._V1)
    conn.execute("ALTER TABLE observations ADD COLUMN project_id INTEGER")
    now = time.time()
    conn.execute(
        "INSERT INTO projects (kind, object_name, status, created, updated,"
        " context) VALUES ('sn', 'SNx', 'active', ?, ?, '{}')", (now, now))
    conn.execute("PRAGMA user_version = 3")
    conn.commit()
    conn.close()

    Database(str(file))  # 3 -> current
    db = Database(str(file))  # re-open: no-op
    assert db.execute("PRAGMA user_version").fetchone()[0] == 9


# ---------------- sessions CRUD ----------------

def test_create_and_list_sessions(tmp_db):
    p = project.create(tmp_db, "sn", "SN2026s")
    sid = followup.create_session(tmp_db, p["id"], "2026-09-09")
    sessions = followup.list_sessions(tmp_db, p["id"])
    assert len(sessions) == 1
    assert sessions[0]["obs_date"] == "2026-09-09"


def test_session_defaults_to_today(tmp_db):
    p = project.create(tmp_db, "sn", "SN2026d")
    sid = followup.create_session(tmp_db, p["id"])
    s = followup.get_session(tmp_db, sid)
    assert s is not None
    assert len(s["obs_date"]) == 10  # YYYY-MM-DD


def test_update_session_notes(tmp_db):
    p = project.create(tmp_db, "sn", "SN2026n")
    sid = followup.create_session(tmp_db, p["id"], "2026-09-09")
    assert followup.update_session_notes(tmp_db, sid, "cloudy night")
    s = followup.get_session(tmp_db, sid)
    assert s["notes"] == "cloudy night"


def test_delete_session_cascades(tmp_db):
    p = project.create(tmp_db, "sn", "SN2026del")
    sid = followup.create_session(tmp_db, p["id"], "2026-09-09")
    followup.add_image(tmp_db, sid, "Clear", "/tmp/stack.fits")
    assert followup.delete_session(tmp_db, sid)
    assert followup.get_session(tmp_db, sid) is None
    assert followup.list_images(tmp_db, sid) == []


def test_delete_session_with_project(tmp_db):
    # deleting the project cascades to sessions (PRAGMA foreign_keys = ON)
    p = project.create(tmp_db, "sn", "SN2026casc")
    sid = followup.create_session(tmp_db, p["id"], "2026-09-09")
    project.delete(tmp_db, p["id"])
    assert followup.list_sessions(tmp_db, p["id"]) == []


def test_days_since_last_session(tmp_db):
    import datetime
    p = project.create(tmp_db, "sn", "SN2026cad")
    assert followup.days_since_last_session(tmp_db, p["id"]) is None
    followup.create_session(tmp_db, p["id"])
    days = followup.days_since_last_session(tmp_db, p["id"])
    assert days is not None
    assert days >= 0


# ---------------- images ----------------

def test_add_and_list_images(tmp_db):
    p = project.create(tmp_db, "sn", "SN2026img")
    sid = followup.create_session(tmp_db, p["id"], "2026-09-09")
    followup.add_image(tmp_db, sid, "Clear", "/tmp/a.fits",
                       date_obs="2026-09-09T22:30:00", exptime_s=300.0)
    followup.add_image(tmp_db, sid, "NIR", "/tmp/b.fits")
    imgs = followup.list_images(tmp_db, sid)
    assert len(imgs) == 2
    assert imgs[0]["filter"] == "Clear"
    assert imgs[1]["filter"] == "NIR"


# ---------------- photometry points ----------------

def test_add_and_list_points(tmp_db):
    p = project.create(tmp_db, "sn", "SN2026pt")
    sid = followup.create_session(tmp_db, p["id"], "2026-09-09")
    followup.add_point(tmp_db, p["id"], 60602.5, "Clear", 16.55,
                       err=0.02, source="manual", session_id=sid)
    followup.add_point(tmp_db, p["id"], 60603.5, "Clear", 16.60,
                       source="paste")
    pts = followup.list_points(tmp_db, p["id"])
    assert len(pts) == 2
    assert pts[0]["mag"] == 16.55
    assert pts[0]["err"] == 0.02
    assert pts[0]["source"] == "manual"


def test_list_points_by_filter(tmp_db):
    p = project.create(tmp_db, "sn", "SN2026fil")
    followup.add_point(tmp_db, p["id"], 60602.5, "Clear", 16.5)
    followup.add_point(tmp_db, p["id"], 60602.5, "NIR", 15.8)
    clear = followup.list_points(tmp_db, p["id"], filter_name="Clear")
    assert len(clear) == 1
    assert clear[0]["filter"] == "Clear"


def test_point_without_session(tmp_db):
    # B-d: a measure can exist without a FITS/session link
    p = project.create(tmp_db, "sn", "SN2026nos")
    followup.add_point(tmp_db, p["id"], 60602.5, "Clear", 16.5,
                       source="manual")
    pts = followup.list_points(tmp_db, p["id"])
    assert pts[0]["session_id"] is None


def test_delete_point(tmp_db):
    p = project.create(tmp_db, "sn", "SN2026dp")
    pid = followup.add_point(tmp_db, p["id"], 60602.5, "Clear", 16.5)
    assert followup.delete_point(tmp_db, pid)
    assert len(followup.list_points(tmp_db, p["id"])) == 0


def test_points_cascade_with_project(tmp_db):
    p = project.create(tmp_db, "sn", "SN2026pc")
    followup.add_point(tmp_db, p["id"], 60602.5, "Clear", 16.5)
    project.delete(tmp_db, p["id"])
    assert len(followup.list_points(tmp_db, p["id"])) == 0
