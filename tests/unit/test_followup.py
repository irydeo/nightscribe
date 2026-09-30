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
    assert db.execute("PRAGMA user_version").fetchone()[0] == 14
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
    assert db.execute("PRAGMA user_version").fetchone()[0] == 14
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
    assert db.execute("PRAGMA user_version").fetchone()[0] == 14


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


def test_migration_v10_adds_the_pin_column(tmp_path):
    # ADR-045 review: a pre-pin database gains project_sessions.pinned
    # with default 0, and existing visits survive unpinned.
    import sqlite3
    import time
    from nightscribe.core import db as dbmod
    from nightscribe.core.db import Database

    file = tmp_path / "v9.db"
    conn = sqlite3.connect(str(file))
    conn.executescript(dbmod._SCHEMA)
    conn.executescript(dbmod._V1)
    conn.execute("ALTER TABLE observations ADD COLUMN project_id INTEGER")
    conn.execute("ALTER TABLE project_files ADD COLUMN session_id INTEGER")
    conn.execute("ALTER TABLE project_files ADD COLUMN meta TEXT DEFAULT '{}'")
    now = time.time()
    conn.execute(
        "INSERT INTO projects (kind, object_name, status, created, updated,"
        " context) VALUES ('sn', 'SN2026p', 'active', ?, ?, '{}')",
        (now, now))
    conn.executescript("""
    CREATE TABLE project_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL,
        obs_date TEXT, notes TEXT DEFAULT '', created REAL NOT NULL);
    CREATE TABLE photometry_points (
        id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL,
        session_id INTEGER, mjd REAL, filter TEXT, mag REAL, err REAL,
        source TEXT);
    """)
    conn.execute("INSERT INTO project_sessions (project_id, obs_date,"
                 " created) VALUES (1, '2026-09-20', ?)", (now,))
    conn.execute("PRAGMA user_version = 9")
    conn.commit()
    conn.close()

    db = Database(str(file))
    assert db.execute("PRAGMA user_version").fetchone()[0] == 14
    cols = {r[1] for r in db.execute(
        "PRAGMA table_info(project_sessions)").fetchall()}
    assert "pinned" in cols
    from nightscribe.core import followup as fu
    s = fu.list_sessions(db, 1)
    assert len(s) == 1 and s[0]["pinned"] is False


def test_migration_v10_gains_the_plate_link(tmp_path):
    # A v10 database with a point keeps the row on reopen and gains the
    # plate link (NULL today) plus its index (ADR-047).
    import sqlite3
    import time
    from nightscribe.core.db import Database

    f = tmp_path / "v10.db"
    db = Database(str(f))
    pid = db.execute(
        "INSERT INTO projects (kind, object_name, status, created, updated,"
        " context, root_dir) VALUES ('sn', 'SNx', 'active', 1.0, 1.0, '{}',"
        " '/tmp/p')").lastrowid
    fid = db.execute(
        "INSERT INTO project_files (project_id, path, kind, created, meta)"
        " VALUES (?, '/tmp/old.fits', 'fits', 1.0, '{}')", (pid,)).lastrowid
    db.execute(
        "INSERT INTO photometry_points (project_id, mjd, filter, mag, source)"
        " VALUES (?, 60600.5, 'Clear', 17.1, 'manual')", (pid,))
    db.execute("PRAGMA user_version = 10")
    db.commit()
    db.close()

    db = Database(str(f))           # replays the v11 migration
    assert db.execute("PRAGMA user_version").fetchone()[0] == 14
    cols = {r[1] for r in db.execute(
        "PRAGMA table_info(photometry_points)").fetchall()}
    assert "file_id" in cols
    idx = {r[1] for r in db.execute(
        "PRAGMA index_list(photometry_points)").fetchall()}
    assert "idx_photo_points_file" in idx
    row = db.execute("SELECT file_id FROM photometry_points").fetchone()
    assert row[0] is None
    # the link is a real FK with the detach-on-plate-delete rule: the
    # point survives, its file_id simply goes NULL
    db.execute("DELETE FROM project_files WHERE id=?", (fid,))
    db.commit()
    row = db.execute("SELECT COUNT(*) FROM photometry_points").fetchone()
    assert row[0] == 1
    row = db.execute("SELECT file_id FROM photometry_points").fetchone()
    assert row[0] is None
    db.close()


# ---------------- ADR-047: point plate link (file_id) ----------------

def test_point_carries_its_plate_link(tmp_db):
    p = project.create(tmp_db, "sn", "SN2026plt")
    fid = project.add_file(tmp_db, p["id"], "/tmp/plate.fits", "fits",
                           meta={"filter": "Clear"})
    pid = followup.add_point(tmp_db, p["id"], 60602.5, "Clear", 16.5,
                             err=0.01, source="measure", file_id=fid)
    assert followup.point_by_id(tmp_db, pid)["file_id"] == fid
    pts = followup.list_points(tmp_db, p["id"])
    assert len(pts) == 1 and pts[0]["file_id"] == fid


def test_point_without_plate_stays_null(tmp_db):
    # Paste, survey and ad-hoc UFE rows never get a plate link (ADR-047).
    p = project.create(tmp_db, "sn", "SN2026noplt")
    pid = followup.add_point(tmp_db, p["id"], 60602.5, "Clear", 16.5,
                             source="paste")
    assert followup.point_by_id(tmp_db, pid)["file_id"] is None
    assert followup.list_points(tmp_db, p["id"])[0]["file_id"] is None


def test_delete_points_only_for_its_plate(tmp_db):
    # The UFE reset "delete this plate's measurements" must never touch
    # points that belong to another plate or to no plate.
    p = project.create(tmp_db, "sn", "SN2026dplt")
    fid = project.add_file(tmp_db, p["id"], "/tmp/plate.fits", "fits")
    other = project.add_file(tmp_db, p["id"], "/tmp/other.fits", "fits")
    followup.add_point(tmp_db, p["id"], 60602.5, "Clear", 16.5, file_id=fid)
    followup.add_point(tmp_db, p["id"], 60603.5, "Clear", 16.6, file_id=fid)
    followup.add_point(tmp_db, p["id"], 60604.5, "Clear", 16.7,
                       file_id=other)       # different plate
    pid = followup.add_point(tmp_db, p["id"], 60605.5, "Clear", 16.8,
                             source="paste")  # no plate
    assert followup.delete_points_for_file(tmp_db, fid) == 2
    pts = followup.list_points(tmp_db, p["id"])
    assert [q["file_id"] for q in pts] == [other, None]
    assert followup.point_by_id(tmp_db, pid) is not None
    assert followup.delete_point(tmp_db, pid) is True
    assert followup.point_by_id(tmp_db, pid) is None


# ---------------- the curve a visit holds (D) -------------------------

def test_the_visit_knows_the_curve_it_holds(tmp_path):
    # The curve of a visit is what the SERIES wrote there: a hand-entered
    # or survey point in the same visit is context, not the measurement.
    from nightscribe.core.db import Database
    from nightscribe.core import followup as fu, project as proj
    db = Database(str(tmp_path / "t.db"))
    pid = proj.create(db, "variable", "V0526 Per")["id"]
    sid = fu.create_session(db, pid, obs_date="2026-09-20")
    run = fu.create_run(db, session_id=sid, cfg={"series": {"band": "V"}})
    fu.add_points(db, [
        {"project_id": pid, "session_id": sid, "mjd": 60000.10,
         "filter": "V", "mag": 12.34, "err": 0.01, "err_internal": 0.005,
         "mag_raw": -9.5, "source": "measure", "flags": [], "run_id": run},
        {"project_id": pid, "session_id": sid, "mjd": 60000.11,
         "filter": "V", "mag": 12.35, "err": 0.01, "err_internal": 0.005,
         "mag_raw": -9.4, "source": "measure", "flags": [], "run_id": run},
        {"project_id": pid, "session_id": sid, "mjd": 60000.12,
         "filter": "V", "mag": 15.0, "err": 0.2, "source": "manual"}])
    got = fu.points_for_session(db, sid)
    assert [round(p["mag"], 2) for p in got] == [12.34, 12.35]     # mjd order
    assert all(p["run_id"] == run for p in got)
    # everything is still there for whoever asks for it
    assert len(fu.points_for_session(db, sid, series_only=False)) == 3
    assert len(fu.runs_for_session(db, sid)) == 1


def test_discarding_the_curve_undoes_its_runs_and_leaves_the_trail(tmp_path):
    from nightscribe.core.db import Database
    from nightscribe.core import followup as fu, project as proj
    db = Database(str(tmp_path / "t.db"))
    pid = proj.create(db, "variable", "V0526 Per")["id"]
    sid = fu.create_session(db, pid, obs_date="2026-09-20")
    runs = []
    for k in range(2):
        run = fu.create_run(db, session_id=sid, cfg={"series": {"n": k}})
        runs.append(run)
        fu.add_points(db, [
            {"project_id": pid, "session_id": sid, "mjd": 60000.1 + k,
             "filter": "V", "mag": 12.3, "err": 0.01, "source": "measure",
             "flags": [], "run_id": run}])
    fu.add_point(db, pid, 60000.9, "V", 12.0, source="manual",
                 session_id=sid)
    undone, removed = fu.discard_session_curve(db, sid)
    assert (undone, removed) == (2, 2)
    assert fu.points_for_session(db, sid) == []          # the curve is gone
    # the run rows stay, marked: the trail is never silent
    assert [r["status"] for r in fu.runs_for_session(db, sid)] == \
        ["undone", "undone"]
    # and the hand-entered point was never part of the curve
    assert len(fu.points_for_session(db, sid, series_only=False)) == 1


# ---------------- v14: the night travels with the point ---------------

def test_migration_v14_adds_the_night_fields(tmp_path):
    # A database from before v14 has points without airmass or position:
    # the migration adds them, and the guard is idempotent (the v9-v13
    # pattern) because a hand-seeded old database may not have the table.
    import sqlite3
    from nightscribe.core.db import Database
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE photometry_points (
        id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER,
        session_id INTEGER, mjd REAL, filter TEXT, mag REAL, err REAL,
        source TEXT, file_id INTEGER, mag_raw REAL, flags TEXT,
        run_id INTEGER, err_internal REAL)""")
    conn.execute("INSERT INTO photometry_points (mjd, mag)"
                 " VALUES (60000.0, 12.0)")
    conn.execute("PRAGMA user_version = 13")
    conn.commit()
    conn.close()
    db = Database(path)
    cols = {r[1] for r in db.execute("PRAGMA table_info(photometry_points)")}
    assert {"airmass", "x", "y", "fwhm", "sky"} <= cols
    # the old point is still there, with its new fields empty
    row = db.execute(
        "SELECT mjd, airmass, x FROM photometry_points").fetchone()
    assert row[0] == 60000.0 and row[1] is None and row[2] is None
    db.close()


def test_the_night_fields_survive_a_write_and_a_read(tmp_path):
    # The whole point: a curve read back from the database (a visit's own
    # curve) brings the airmass and the measured position, so its night
    # figures can be drawn months later without measuring again.
    import pytest
    from nightscribe.core.db import Database
    from nightscribe.core import followup as fu
    db = Database(tmp_path / "p.db")
    pid = project.create(db, "variable", "V0526 Per")["id"]
    sid = fu.create_session(db, pid, "2026-09-30")
    ids = fu.add_points(db, [{
        "project_id": pid, "session_id": sid, "mjd": 60000.25,
        "filter": "V", "mag": 12.34, "err": 0.05, "source": "measure",
        "airmass": 1.42, "x": 831.5, "y": 620.25, "fwhm": 3.1, "sky": 420.0}])
    assert ids
    back = fu.points_for_session(db, sid)
    assert len(back) == 1
    assert back[0]["airmass"] == pytest.approx(1.42)
    assert back[0]["x"] == pytest.approx(831.5)
    assert back[0]["y"] == pytest.approx(620.25)
    assert back[0]["fwhm"] == pytest.approx(3.1)
    assert back[0]["sky"] == pytest.approx(420.0)
    db.close()
