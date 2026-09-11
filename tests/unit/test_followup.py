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
    assert {"project_sessions", "session_images", "photometry_points"} <= tables


def test_migration_v3_to_v5_preserves_projects(tmp_path):
    # A pre-Track-B database (user_version 3) with a project must keep
    # every row and gain the three follow-up tables on reopen.
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
    conn.execute("PRAGMA user_version = 3")
    conn.commit()
    conn.close()

    db = Database(str(file))
    assert db.execute("PRAGMA user_version").fetchone()[0] == 7
    # project survived
    row = db.execute(
        "SELECT kind, object_name FROM projects WHERE id=1").fetchone()
    assert row[0] == "sn" and row[1] == "SN2026b"
    # tables exist
    tables = {r[0] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "project_sessions" in tables


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

    Database(str(file))  # 3 -> 5
    db = Database(str(file))  # re-open: no-op
    assert db.execute("PRAGMA user_version").fetchone()[0] == 7


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
