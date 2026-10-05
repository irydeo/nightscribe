############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: v17 migration (minor-planet astrometry)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""v17 acceptance (phase 8, D14): the astrometry_runs, astrometry_points and
astrometry_frames tables appear additively, idempotently and without losing
anything, and the store writes and undoes one execution without touching the
others. A hand-built v16 database walks to v17 untouched."""

import pytest

from nightscribe.core import astrometry_store as ast
from nightscribe.core.db import Database

_RUN_COLS = {
    "id", "project_id", "session_id", "created", "cfg_json", "status",
    "object_name", "method", "n_frames", "n_obs", "rate_arcsec_min",
    "pa_deg", "sweep_json", "dither", "snr_gate", "submit_snr", "detected",
}
_POINT_COLS = {
    "id", "run_id", "project_id", "session_id", "group_index", "mjd", "ra",
    "dec", "rms_ra", "rms_dec", "mag", "band", "x", "y", "n_frames", "snr",
    "mag_limit", "source", "method", "flags", "check_residual_ra",
    "check_residual_dec", "check_scatter", "check_ok", "check_note",
    "mag_auto", "mag_source",
}
_FRAME_COLS = {
    "id", "run_id", "path", "size", "filter", "exptime_s", "date_obs",
    "archived", "moved_to",
}


def _columns(db, table):
    return {r[1] for r in db.execute(f"PRAGMA table_info({table})")}


def _v16_database(path):
    # A real database walked to v17 and then rewound to v16: below v17 its
    # schema is exactly what an installed v16 has. The three astrometry
    # tables are dropped and a legacy project + photometry point are left
    # behind, so the migration has to create the tables again and prove it
    # does not disturb what was already there.
    db = Database(str(path))
    pid = db.execute(
        "INSERT INTO projects (kind, object_name, status, created, updated,"
        " context) VALUES ('pccp', 'PCCP 2026A', 'active', 1.0, 1.0, '{}')"
    ).lastrowid
    db.execute("INSERT INTO photometry_points (project_id, mjd, filter, mag,"
               " source) VALUES (?, 60600.5, 'Clear', 17.1, 'manual')",
               (pid,))
    db.execute("DROP TABLE astrometry_points")
    db.execute("DROP TABLE astrometry_frames")
    db.execute("DROP TABLE astrometry_runs")
    db.execute("PRAGMA user_version = 16")
    db.commit()
    db.close()
    return pid


def _seed(db):
    # A project and its VISIT (project_sessions), the two ids every run and
    # point must carry.
    pid = db.execute(
        "INSERT INTO projects (kind, object_name, status, created, updated,"
        " context) VALUES ('pccp', 'PCCP 2026A', 'active', 1.0, 1.0, '{}')"
    ).lastrowid
    sid = db.execute(
        "INSERT INTO project_sessions (project_id, obs_date, notes, created)"
        " VALUES (?, '2026-10-04', '', 1.0)", (pid,)).lastrowid
    db.commit()
    return pid, sid


# ---------------- migration ----------------

def test_v16_walks_to_v17_without_loss(tmp_path):
    pid = _v16_database(tmp_path / "v16.db")
    db = Database(str(tmp_path / "v16.db"))
    assert db.execute("PRAGMA user_version").fetchone()[0] == 18
    assert _columns(db, "astrometry_runs") == _RUN_COLS
    assert _columns(db, "astrometry_points") == _POINT_COLS
    assert _columns(db, "astrometry_frames") == _FRAME_COLS
    # the legacy photometry point survived the migration untouched
    row = db.execute("SELECT mag, source FROM photometry_points"
                     " WHERE project_id=?", (pid,)).fetchone()
    assert row == (17.1, "manual")
    db.close()


def test_fresh_db_is_v17(tmp_path):
    db = Database(str(tmp_path / "fresh.db"))
    assert db.execute("PRAGMA user_version").fetchone()[0] == 18
    tables = {r[0] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"astrometry_runs", "astrometry_points",
            "astrometry_frames"} <= tables
    db.close()


def test_reopen_is_idempotent(tmp_path):
    f = tmp_path / "t.db"
    Database(str(f)).close()
    db = Database(str(f))               # reopening must be a no-op
    assert db.execute("PRAGMA user_version").fetchone()[0] == 18
    assert _columns(db, "astrometry_runs") == _RUN_COLS
    db.close()


# ---------------- store: batch write ----------------

def test_batch_write_round_trips_points_and_frames(tmp_db):
    pid, sid = _seed(tmp_db)
    run = ast.create_run(
        tmp_db, pid, sid, {"report_source": "MPC", "sweep": {"pct": 5.0}},
        status="complete", object_name="2026 AB", method="sigma",
        n_frames=40, n_obs=2, rate_arcsec_min=1.23, pa_deg=245.0,
        sweep={"pct": 5.0, "steps": 25}, dither=True, snr_gate=3.5,
        submit_snr=41.0, detected=True)
    ids = ast.add_points(tmp_db, [
        {"run_id": run, "project_id": pid, "session_id": sid,
         "group_index": 0, "mjd": 60600.10, "ra": 12.5, "dec": -3.2,
         "rms_ra": 0.1, "rms_dec": 0.12, "mag": 18.2, "band": "G",
         "x": 512.0, "y": 400.0, "n_frames": 20, "snr": 12.0,
         "mag_limit": 20.1, "source": "stack", "method": "sigma",
         "flags": ["ok"], "check_residual_ra": 0.05,
         "check_residual_dec": -0.02, "check_scatter": 0.3,
         "check_ok": True, "check_note": ""},
        {"run_id": run, "project_id": pid, "session_id": sid,
         "group_index": 0, "mjd": 60600.10, "ra": 12.6, "dec": -3.1,
         "source": "frames", "method": "sigma", "n_frames": 20}])
    frame_ids = ast.add_frames(tmp_db, run, [
        {"path": "/data/f1.fits", "size": 100, "filter": "G",
         "exptime_s": 30.0, "date_obs": "2026-10-04T22:00:00"},
        {"path": "/data/f2.fits", "size": 100, "filter": "G",
         "exptime_s": 30.0, "date_obs": "2026-10-04T22:00:30",
         "archived": True, "moved_to": "/archive/f2.fits"}])
    assert len(ids) == 2 and len(frame_ids) == 2

    # the VISIT lives in session_id, the execution in run_id
    pts = ast.points_for_run(tmp_db, run)
    assert all(p["session_id"] == sid and p["run_id"] == run for p in pts)
    assert pts[0]["source"] == "stack" and pts[1]["source"] == "frames"
    assert pts[0]["flags"] == ["ok"] and pts[1]["flags"] == []
    assert pts[0]["check_ok"] is True

    runs = ast.list_runs(tmp_db, pid)
    assert len(runs) == 1
    assert runs[0]["cfg"]["report_source"] == "MPC"
    assert runs[0]["sweep"] == {"pct": 5.0, "steps": 25}
    assert runs[0]["detected"] is True and runs[0]["dither"] is True
    assert runs[0]["points"] == 2
    assert runs[0]["rate_arcsec_min"] == 1.23


def test_not_detected_run_keeps_its_limit(tmp_db):
    pid, sid = _seed(tmp_db)
    run = ast.create_run(tmp_db, pid, sid, {}, status="not_detected",
                         n_frames=10, snr_gate=3.5, detected=False)
    assert ast.points_for_run(tmp_db, run) == []
    row = ast.list_runs(tmp_db, pid)[0]
    assert row["status"] == "not_detected" and row["detected"] is False


# ---------------- store: undo by execution ----------------

def test_delete_run_only_touches_its_own(tmp_db):
    pid, sid = _seed(tmp_db)
    # a legacy photometry point that the undo must never see
    tmp_db.execute("INSERT INTO photometry_points (project_id, session_id,"
                   " mjd, filter, mag, source) VALUES (?, ?, 60600.0, 'V',"
                   " 12.0, 'manual')", (pid, sid))
    tmp_db.commit()
    run_a = ast.create_run(tmp_db, pid, sid, {}, n_frames=2, n_obs=1)
    run_b = ast.create_run(tmp_db, pid, sid, {}, n_frames=2, n_obs=1)
    for run in (run_a, run_b):
        ast.add_points(tmp_db, [{"run_id": run, "project_id": pid,
                                 "session_id": sid, "group_index": 0,
                                 "mjd": 60600.1, "source": "stack"}])
        ast.add_frames(tmp_db, run, [{"path": f"/data/{run}.fits"}])

    out = ast.delete_run(tmp_db, run_a)
    assert out == {"points": 1, "frames": 1, "undone": True}

    # run A is gone but audited: no points, no frames, status "undone"
    assert ast.points_for_run(tmp_db, run_a) == []
    frames_a = tmp_db.execute(
        "SELECT COUNT(*) FROM astrometry_frames WHERE run_id=?",
        (run_a,)).fetchone()[0]
    assert frames_a == 0
    assert tmp_db.execute("SELECT status FROM astrometry_runs WHERE id=?",
                          (run_a,)).fetchone()[0] == "undone"

    # run B and the legacy point are exactly as they were
    assert len(ast.points_for_run(tmp_db, run_b)) == 1
    assert tmp_db.execute(
        "SELECT COUNT(*) FROM astrometry_frames WHERE run_id=?",
        (run_b,)).fetchone()[0] == 1
    assert tmp_db.execute("SELECT COUNT(*) FROM photometry_points"
                          " WHERE project_id=?", (pid,)).fetchone()[0] == 1


def test_a_manual_magnitude_replaces_the_effective_one(tmp_path):
    # D: the observer measured the brightness by hand in the Photometry tab
    # and says the report should use it. The EFFECTIVE magnitude moves, the
    # automatic one stays in mag_auto, and mag_source records who wrote
    # what: nothing reaches the MPC without its trace.
    store = ast
    db = Database(str(tmp_path / "t.db"))
    pid = db.execute(
        "INSERT INTO projects (kind, object_name, status, created, updated,"
        " context) VALUES ('neo', '2025 UR', 'active', 1.0, 1.0, '{}')"
    ).lastrowid
    run = ast.create_run(db, pid, None, {}, status="complete")
    ast.add_points(db, [{"run_id": run, "project_id": pid, "session_id":
                           None, "group_index": 0, "mag": 18.05, "band": "G",
                           "source": "stack"}])
    # the run's own value is the automatic one, and it says so
    p = ast.points_for_run(db, run)[0]
    assert p["mag"] == pytest.approx(18.05)
    assert p["mag_auto"] == pytest.approx(18.05)
    assert p["mag_source"] == "auto"
    # the observer's measurement takes over the effective magnitude
    assert ast.set_manual_magnitude(db, run, 0, 17.98, "G") == 1
    p = ast.points_for_run(db, run)[0]
    assert p["mag"] == pytest.approx(17.98)
    assert p["mag_auto"] == pytest.approx(18.05)   # what the machine said
    assert p["mag_source"] == "manual"
