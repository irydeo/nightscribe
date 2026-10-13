############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Minor-planet astrometry persistence module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Persistence for the minor-planet astrometry flow (phase 8, D14).

One execution of the track & stack engine is a RUN; a run measures one or
more OBSERVATIONS (points) and consumes a manifest of FRAMES. All of it is
tied to the VISIT the observer was working in, never to the run itself.

Why the split matters (the rule this module exists to protect): db.py runs
with PRAGMA foreign_keys = ON and session_id is a FK to project_sessions.
Storing the run id there would break the link point -> visit that the
multinight view needs. So session_id is the visit and run_id is the
execution, exactly the split measurement_runs made for photometry (ADR-048).

All SQL goes through db.execute (ADR-002). Short functions, no ORM, no
magic, in the pragmatic style of core/followup.py.
"""

import json
import time


def create_run(db, project_id, session_id, cfg, status="complete",
               object_name="", method="", n_frames=0, n_obs=0,
               rate_arcsec_min=None, pa_deg=None, sweep=None, dither=None,
               snr_gate=None, submit_snr=None, detected=None):
    # One execution of the engine. The RESULT (rate, PA, whether it was
    # detected) is written next to the configuration so the analysis view
    # can list a run without re-reducing it.
    #
    # status is the honest verdict: complete | not_detected | incomplete |
    # undone. A not_detected run still has a row and a magnitude limit: "we
    # looked and there was nothing" is data too, and the next night needs to
    # know it was tried.
    # @args: db - Database, project_id / session_id - the project and the
    #        VISIT it belongs to, cfg - JSON-safe configuration echo,
    #        status - complete|not_detected|incomplete|undone, object_name -
    #        the target as reported, method - sum|mean|median|sigma,
    #        n_frames / n_obs - how many frames and observations the run
    #        holds, rate_arcsec_min / pa_deg - the resolved motion, sweep -
    #        the velocity sweep grid (JSON) or None, dither - did the
    #        sequence dither (bool) or None, snr_gate / submit_snr - the
    #        thresholds used, detected - the detection verdict (bool) or None
    # @return: the new run id
    cur = db.execute(
        "INSERT INTO astrometry_runs (project_id, session_id, created,"
        " cfg_json, status, object_name, method, n_frames, n_obs,"
        " rate_arcsec_min, pa_deg, sweep_json, dither, snr_gate,"
        " submit_snr, detected)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (project_id, session_id, time.time(),
         json.dumps(cfg or {}, ensure_ascii=False), status, object_name,
         method, n_frames, n_obs, rate_arcsec_min, pa_deg,
         _json_or_none(sweep), _int_or_none(dither), snr_gate, submit_snr,
         _int_or_none(detected)))
    db.commit()
    return cur.lastrowid


def add_points(db, rows):
    # Batch write of the run's observations (D22: one row per observation).
    #
    # A point can be measured by two routes (source "stack" and "frames")
    # with the same mjd and group_index: the contrast of D16 is then one
    # query, and neither route is ever silently preferred.
    #
    # Each row is a dict with the astrometry_points columns; missing keys
    # become NULL. `flags` accepts a list (stored as JSON) or an already
    # encoded string.
    # @args: db - Database, rows - [dicts with run_id, project_id,
    #        session_id (the VISIT), group_index, mjd, ra, dec, rms_ra,
    #        rms_dec, mag, band, x, y, n_frames, snr, mag_limit, source,
    #        method, flags, check_residual_ra, check_residual_dec,
    #        check_scatter, check_ok, check_note, mag_auto, mag_source]
    # @return: the list of new point ids
    ids = []
    for r in rows:
        flags = r.get("flags")
        if isinstance(flags, (list, tuple, dict)):
            flags = json.dumps(flags, ensure_ascii=False)
        cur = db.execute(
            "INSERT INTO astrometry_points (run_id, project_id, session_id,"
            " group_index, mjd, ra, dec, rms_ra, rms_dec, mag, band, x, y,"
            " n_frames, snr, mag_limit, source, method, flags,"
            " check_residual_ra, check_residual_dec, check_scatter,"
            " check_ok, check_note, mag_auto, mag_source, mag_err,"
            " centroid_source)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,"
            " ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (r.get("run_id"), r.get("project_id"), r.get("session_id"),
             r.get("group_index"), r.get("mjd"), r.get("ra"), r.get("dec"),
             r.get("rms_ra"), r.get("rms_dec"), r.get("mag"), r.get("band"),
             r.get("x"), r.get("y"), r.get("n_frames"), r.get("snr"),
             r.get("mag_limit"), r.get("source"), r.get("method"), flags,
             r.get("check_residual_ra"), r.get("check_residual_dec"),
             r.get("check_scatter"), r.get("check_ok"), r.get("check_note"),
             r.get("mag_auto", r.get("mag")), r.get("mag_source", "auto"),
             r.get("mag_err"), r.get("centroid_source", "auto")))
        ids.append(cur.lastrowid)
    db.commit()
    return ids


def set_manual_magnitude(db, run_id, group_index, mag, band=None):
    # The observer measured the brightness by hand and says the report should
    # use it (D). The EFFECTIVE magnitude moves; the automatic one stays in
    # mag_auto and mag_source records who wrote what, so nothing reaches the
    # MPC without its trace. Only the point of the STACK is touched: the
    # per-frame one is the other half of the double measurement.
    # @args: db - Database, run_id - the execution, group_index - which
    #        observation, mag - the magnitude to use, band - its band
    # @return: how many points were updated (0 or 1)
    cur = db.execute(
        "UPDATE astrometry_points SET mag=?, band=COALESCE(?, band),"
        " mag_source='manual' WHERE run_id=? AND group_index=?"
        " AND source='stack'",
        (float(mag), band, int(run_id), int(group_index)))
    db.commit()
    return cur.rowcount


def set_point_excluded(db, run_id, group_index, excluded):
    # The observer excluded an observation from the report and the check (or
    # put it back, 2026-10-10). The point is NEVER deleted: the flag
    # `user_excluded` is added to (or taken out of) the flags of the STACK
    # point, which is the one the report and the check use. So a reopened run
    # keeps the observer's decision and the audit keeps the measurement.
    # @args: db - Database, run_id - the execution, group_index - which
    #        observation, excluded - True to leave it out, False to put it back
    # @return: how many points were updated (0 or 1)
    row = db.execute(
        "SELECT flags FROM astrometry_points WHERE run_id=? AND group_index=?"
        " AND source='stack'",
        (int(run_id), int(group_index))).fetchone()
    if row is None:
        return 0
    flags = [f for f in _flags_in(row[0]) if f != "user_excluded"]
    if excluded:
        flags.append("user_excluded")
    cur = db.execute(
        "UPDATE astrometry_points SET flags=? WHERE run_id=? AND"
        " group_index=? AND source='stack'",
        (json.dumps(flags, ensure_ascii=False), int(run_id),
         int(group_index)))
    db.commit()
    return cur.rowcount


def set_manual_centroid(db, run_id, group_index, ra, dec, rms_ra, rms_dec,
                        x, y, snr=None, source="manual"):
    # ADR-085: the observer re-selected the centroid of an observation on the
    # saved stack (a bad residual, a centroid dragged by a neighbour), or asked
    # the app to pick it again AUTOMATICALLY (source="auto"): the STACK point's
    # position and its error bar move and the point is SIGNED with where the
    # centroid came from; the per-frame point is left alone (it is the other
    # half of the double measurement). Nothing is re-stacked.
    # @args: db, run_id, group_index, ra/dec - the new position, rms_ra/dec -
    #        its error bar, x/y - the pixel centroid, snr - optional,
    #        source - "manual" | "auto"
    # @return: how many points were updated (0 or 1)
    src = "manual" if str(source) == "manual" else "auto"
    cur = db.execute(
        "UPDATE astrometry_points SET ra=?, dec=?, rms_ra=?, rms_dec=?,"
        " x=?, y=?, snr=COALESCE(?, snr), centroid_source=?"
        " WHERE run_id=? AND group_index=? AND source='stack'",
        (float(ra), float(dec), float(rms_ra), float(rms_dec), float(x),
         float(y), (float(snr) if snr is not None else None), src,
         int(run_id), int(group_index)))
    db.commit()
    return cur.rowcount


def project_observations(db, project_id):
    # ADR-086: every measurement the project has, across its runs, in time
    # order: the STACK points of the complete runs (the object's own
    # measurement, the one the report carries). It is what the combined
    # check/report lists, so the observer can see the whole set at once.
    # @args: db, project_id
    # @return: [point dicts, each carrying its run's created time and motion]
    runs = [r for r in list_runs(db, project_id)
            if r.get("status") == "complete"]
    out = []
    for run in runs:
        for pt in points_for_run(db, run["id"]):
            if pt.get("source") != "stack":
                continue
            pt = dict(pt)
            pt["run_created"] = run.get("created")
            pt["rate_arcsec_min"] = run.get("rate_arcsec_min")
            out.append(pt)
    out.sort(key=lambda q: (q.get("mjd") or 0.0, q.get("id") or 0))
    return out


def dedupe_observations(obs):
    # ADR-086 rev: a project accumulates RE-MEASURES of the same observation
    # (the same night's frames stacked again, with another method or another
    # observation count). Feeding all of them to Find_Orb hands it several
    # identical points at the same instant, a degenerate set that produces
    # absurd residuals (measured 2026-10-13: four runs at mjd 61322.915954).
    # The combined view keeps ONE point per (mjd, group_index), the one from
    # the NEWEST run, and says how many were merged.
    # @args: obs - [point dicts] from project_observations
    # @return: (kept, merged): the deduped list (time order) and how many were
    #          folded away
    best = {}
    for o in obs:
        try:
            key = (round(float(o.get("mjd") or 0.0), 6),
                   int(o.get("group_index") or 0))
        except (TypeError, ValueError):
            key = (o.get("mjd"), o.get("group_index"))
        cur = best.get(key)
        if cur is None or (o.get("run_id") or 0) > (cur.get("run_id") or 0):
            best[key] = o
    kept = sorted(best.values(),
                  key=lambda q: (q.get("mjd") or 0.0, q.get("id") or 0))
    return kept, len(obs) - len(kept)


def runs_for_session(db, session_id):
    # ADR-086 rev: the astrometry runs of ONE visit, oldest first, with the
    # numbers the visit window shows. The counterpart of the series'
    # `followup.runs_for_session`, for the track & stack.
    # @args: db, session_id - the visit
    # @return: [run dicts, with their point count]
    if session_id is None:
        return []
    rows = db.execute(
        "SELECT r.id, r.created, r.status, r.object_name, r.n_obs,"
        " r.n_frames, r.rate_arcsec_min, COUNT(p.id)"
        " FROM astrometry_runs r"
        " LEFT JOIN astrometry_points p ON p.run_id = r.id"
        " WHERE r.session_id=? GROUP BY r.id ORDER BY r.id",
        (session_id,)).fetchall()
    return [{"id": r[0], "created": r[1], "status": r[2],
             "object_name": r[3], "n_obs": r[4], "n_frames": r[5],
             "rate_arcsec_min": r[6], "points": r[7] or 0} for r in rows]


def save_combined(db, project_id, included, check):
    # ADR-086: the project's combined check/report is SAVED (one row per
    # project): the point ids the observer ticked and the combined
    # CheckReport summary. A reopen shows the same set and the same verdict.
    # @args: db, project_id, included - [point ids], check - the summary dict
    # @return: None
    db.execute(
        "INSERT INTO astrometry_combined (project_id, included_json,"
        " check_json, updated) VALUES (?, ?, ?, ?)"
        " ON CONFLICT(project_id) DO UPDATE SET"
        " included_json=excluded.included_json,"
        " check_json=excluded.check_json, updated=excluded.updated",
        (int(project_id), _json_or_none(list(included or [])),
         _json_or_none(check), time.time()))
    db.commit()


def get_combined(db, project_id):
    # @args: db, project_id
    # @return: {"included": [ids], "check": {...}, "updated": epoch} or None
    row = db.execute(
        "SELECT included_json, check_json, updated FROM astrometry_combined"
        " WHERE project_id=?", (int(project_id),)).fetchone()
    if row is None:
        return None
    return {"included": _json_in(row[0]) or [],
            "check": _json_in(row[1]) or {},
            "updated": row[2]}


def add_frames(db, run_id, rows):
    # The manifest of the frames a run consumed (phase 9). It is written
    # once per run: the run already says how many frames it used, and this
    # is WHICH ones, so the archive step can find them later and the user
    # can see what was really measured.
    # @args: db - Database, run_id - the execution, rows - [dicts with path,
    #        size, filter, exptime_s, date_obs, archived, moved_to]
    # @return: the list of new frame ids
    ids = []
    for r in rows:
        cur = db.execute(
            "INSERT INTO astrometry_frames (run_id, path, size, filter,"
            " exptime_s, date_obs, archived, moved_to)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, r.get("path"), r.get("size"), r.get("filter"),
             r.get("exptime_s"), r.get("date_obs"),
             _int_or_none(r.get("archived")) or 0, r.get("moved_to")))
        ids.append(cur.lastrowid)
    db.commit()
    return ids


def set_run_status(db, run_id, status):
    # The run's verdict can change (a cancelled run is "incomplete", an
    # undone one is "undone"); the row always stays for the audit trail.
    # @return: True if the run was found and updated
    cur = db.execute("UPDATE astrometry_runs SET status=? WHERE id=?",
                     (status, run_id))
    db.commit()
    return cur.rowcount > 0


def delete_run(db, run_id):
    # "Undo this execution" (D14): the run's points and its frame manifest
    # go, the run row stays marked "undone" so the trail is never silent.
    #
    # It touches ONLY this run: another run in the same visit, the visit
    # itself and the legacy photometry_points of the project are all left
    # exactly as they were.
    # @args: db - Database, run_id - the execution to undo
    # @return: {"points": removed, "frames": removed, "undone": bool}
    points = db.execute("DELETE FROM astrometry_points WHERE run_id=?",
                        (run_id,)).rowcount
    frames = db.execute("DELETE FROM astrometry_frames WHERE run_id=?",
                        (run_id,)).rowcount
    undone = set_run_status(db, run_id, "undone")
    db.commit()
    return {"points": points, "frames": frames, "undone": undone}


def list_runs(db, project_id):
    # The executions of a project, oldest first (the analysis view lists
    # them in order). cfg and sweep come back decoded so the caller does
    # not repeat the JSON dance; `points` is how many observations the run
    # actually holds.
    # @return: [{"id", "project_id", "session_id", "created", "cfg",
    #           "status", "object_name", "method", "n_frames", "n_obs",
    #           "rate_arcsec_min", "pa_deg", "sweep", "dither", "snr_gate",
    #           "submit_snr", "detected", "points"}, ...]
    rows = db.execute(
        "SELECT r.id, r.project_id, r.session_id, r.created, r.cfg_json,"
        " r.status, r.object_name, r.method, r.n_frames, r.n_obs,"
        " r.rate_arcsec_min, r.pa_deg, r.sweep_json, r.dither, r.snr_gate,"
        " r.submit_snr, r.detected,"
        " (SELECT COUNT(*) FROM astrometry_points p WHERE p.run_id = r.id)"
        " FROM astrometry_runs r WHERE r.project_id=? ORDER BY r.id",
        (project_id,)).fetchall()
    return [{"id": r[0], "project_id": r[1], "session_id": r[2],
             "created": r[3], "cfg": _json_in(r[4]), "status": r[5],
             "object_name": r[6], "method": r[7], "n_frames": r[8],
             "n_obs": r[9], "rate_arcsec_min": r[10], "pa_deg": r[11],
             "sweep": _json_in(r[12]), "dither": _bool_in(r[13]),
             "snr_gate": r[14], "submit_snr": r[15],
             "detected": _bool_in(r[16]), "points": r[17] or 0}
            for r in rows]


def points_for_run(db, run_id):
    # The observations of one execution, in the order they were measured
    # (group_index first: a sequence is numbered, and the stack/frames pair
    # of a group lands together). flags comes back decoded.
    # @return: [point dicts, all astrometry_points columns]
    rows = db.execute(
        "SELECT id, run_id, project_id, session_id, group_index, mjd, ra,"
        " dec, rms_ra, rms_dec, mag, band, x, y, n_frames, snr, mag_limit,"
        " source, method, flags, check_residual_ra, check_residual_dec,"
        " check_scatter, check_ok, check_note, mag_auto, mag_source,"
        " mag_err, centroid_source"
        " FROM astrometry_points WHERE run_id=?"
        " ORDER BY group_index, id",
        (run_id,)).fetchall()
    return [{"id": r[0], "run_id": r[1], "project_id": r[2],
             "session_id": r[3], "group_index": r[4], "mjd": r[5],
             "ra": r[6], "dec": r[7], "rms_ra": r[8], "rms_dec": r[9],
             "mag": r[10], "band": r[11], "x": r[12], "y": r[13],
             "n_frames": r[14], "snr": r[15], "mag_limit": r[16],
             "source": r[17], "method": r[18], "flags": _flags_in(r[19]),
             "check_residual_ra": r[20], "check_residual_dec": r[21],
             "check_scatter": r[22], "check_ok": _bool_in(r[23]),
             "check_note": r[24], "mag_auto": r[25], "mag_source": r[26],
             "mag_err": r[27], "centroid_source": r[28]}
            for r in rows]


def _json_or_none(value):
    # @return: value encoded as JSON, or None when there is nothing to store
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _json_in(raw):
    # @args: raw - a stored TEXT column (JSON) or None
    # @return: the decoded value, tolerating legacy/blank values
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


def _int_or_none(value):
    # SQLite has no bool type: keep the three states (None / 0 / 1) that
    # let "we did not record it" be different from "it was no".
    # @return: 1, 0 or None
    if value is None:
        return None
    return 1 if value else 0


def _bool_in(value):
    # @return: True/False when the column has a value, else None
    if value is None:
        return None
    return bool(value)


def _flags_in(raw):
    # @args: raw - the stored flags TEXT (JSON list) or None
    # @return: a list of flags, tolerating legacy/blank values
    if not raw:
        return []
    try:
        val = json.loads(raw)
    except (ValueError, TypeError):
        return []
    return val if isinstance(val, list) else []
