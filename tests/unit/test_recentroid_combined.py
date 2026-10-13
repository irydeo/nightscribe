############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: re-centroid and combined report store
# (ADR-085 / ADR-086)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The data layer of the two features that share the observations: the manual
re-centroid of one point (ADR-085) and the project-level combined check/report
(ADR-086). No GUI, no network.
"""

from nightscribe.core import astrometry_store as store
from nightscribe.core import project


def _run(db, pid, sid, *, mjd, rate=12.0):
    run_id = store.create_run(
        db, pid, sid, cfg={"result": {}}, status="complete",
        object_name="2026 TQ8", n_obs=1, rate_arcsec_min=rate)
    store.add_points(db, [{
        "run_id": run_id, "project_id": pid, "session_id": sid,
        "group_index": 0, "mjd": mjd, "ra": 33.0, "dec": 35.0,
        "rms_ra": 0.2, "rms_dec": 0.2, "mag": 19.0, "band": "G",
        "mag_err": 0.05, "x": 10.0, "y": 12.0, "snr": 8.0,
        "source": "stack", "flags": []}])
    return run_id


def _seed(db):
    pid = project.create(db, "neo", "2026 TQ8", {})["id"]
    sid = db.execute(
        "INSERT INTO project_sessions (project_id, obs_date, notes, created)"
        " VALUES (?, '2026-10-13', '', 1.0)", (pid,)).lastrowid
    db.commit()
    return pid, sid


def test_set_manual_centroid_moves_and_signs_the_stack_point(tmp_db):
    pid, sid = _seed(tmp_db)
    run_id = _run(tmp_db, pid, sid, mjd=61300.1)
    assert store.set_manual_centroid(
        tmp_db, run_id, 0, 34.0, 36.0, 0.11, 0.12, 14.0, 15.0, 9.5) == 1
    pt = next(p for p in store.points_for_run(tmp_db, run_id)
              if p["source"] == "stack")
    assert (pt["ra"], pt["dec"]) == (34.0, 36.0)
    assert (pt["x"], pt["y"]) == (14.0, 15.0)
    assert pt["centroid_source"] == "manual"
    # a fresh point is "auto"
    run2 = _run(tmp_db, pid, sid, mjd=61300.2)
    pt2 = next(p for p in store.points_for_run(tmp_db, run2)
               if p["source"] == "stack")
    assert pt2["centroid_source"] == "auto"


def test_mag_err_round_trips(tmp_db):
    pid, sid = _seed(tmp_db)
    run_id = _run(tmp_db, pid, sid, mjd=61300.1)
    pt = next(p for p in store.points_for_run(tmp_db, run_id)
              if p["source"] == "stack")
    assert pt["mag_err"] == 0.05


def test_project_observations_gathers_runs_in_time_order(tmp_db):
    pid, sid = _seed(tmp_db)
    _run(tmp_db, pid, sid, mjd=61300.9)      # measured last, saved first
    _run(tmp_db, pid, sid, mjd=61300.1)
    obs = store.project_observations(tmp_db, pid)
    assert [o["mjd"] for o in obs] == [61300.1, 61300.9]
    assert all(o["source"] == "stack" for o in obs)
    assert all(o["run_created"] for o in obs)


def test_project_observations_skips_undone_runs(tmp_db):
    pid, sid = _seed(tmp_db)
    keep = _run(tmp_db, pid, sid, mjd=61300.1)
    gone = _run(tmp_db, pid, sid, mjd=61300.2)
    store.delete_run(tmp_db, gone)
    obs = store.project_observations(tmp_db, pid)
    assert [o["run_id"] for o in obs] == [keep]


def test_dedupe_keeps_one_point_per_observation():
    obs = [
        {"id": 1, "run_id": 10, "mjd": 61300.5, "group_index": 0},
        {"id": 2, "run_id": 11, "mjd": 61300.5, "group_index": 0},
        {"id": 3, "run_id": 12, "mjd": 61300.5, "group_index": 0},
        {"id": 4, "run_id": 10, "mjd": 61301.5, "group_index": 0},
    ]
    kept, merged = store.dedupe_observations(obs)
    assert merged == 2
    assert [o["id"] for o in kept] == [3, 4]     # the newest run per instant


def test_runs_for_session_lists_the_visits_runs(tmp_db):
    pid, sid = _seed(tmp_db)
    a = _run(tmp_db, pid, sid, mjd=61300.1)
    _run(tmp_db, pid, sid, mjd=61300.2)
    # a run with no visit is not listed under it
    other = db_run_without_session(tmp_db, pid)
    runs = store.runs_for_session(tmp_db, sid)
    assert [r["id"] for r in runs] == [a, a + 1]
    assert all(r["points"] >= 1 for r in runs)
    assert store.runs_for_session(tmp_db, None) == []
    assert other


def db_run_without_session(db, pid):
    return store.create_run(db, pid, None, cfg={}, status="complete",
                            object_name="2026 TQ8", n_obs=0)


def test_combined_check_round_trips(tmp_db):
    pid, sid = _seed(tmp_db)
    run_id = _run(tmp_db, pid, sid, mjd=61300.1)
    pt = store.project_observations(tmp_db, pid)[0]
    store.save_combined(tmp_db, pid, [pt["id"]],
                        {"ok": True, "our_residual": (0.1, -0.2)})
    got = store.get_combined(tmp_db, pid)
    assert got["included"] == [pt["id"]]
    assert got["check"]["ok"] is True
    # saving again replaces (one row per project)
    store.save_combined(tmp_db, pid, [], {"ok": False})
    got = store.get_combined(tmp_db, pid)
    assert got["included"] == [] and got["check"]["ok"] is False
    assert run_id
