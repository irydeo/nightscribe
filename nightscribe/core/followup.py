############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - SN follow-up model (Track B, project-concept v2)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Multi-night follow-up storage (visits and photometry points).

A follow-up is a tree: project → sessions (one per observing night, any
kind since ADR-045) → resources in the single file registry
(project_files linked by session_id) and photometry points (manual,
pasted, imported, measured in the UFE, or survey context).

All SQL goes through db.execute (ADR-002). The module mirrors the
pragmatic style of core/project.py: short functions, no ORM, no magic.
"""

import json
import logging
import time

logger = logging.getLogger(__name__)


def _now():
    # @return: current epoch seconds
    return time.time()


# ---------------- sessions ----------------

def create_session(db, project_id, obs_date=None, notes=""):
    # @args: db - Database, project_id - int, obs_date - ISO date string or
    #        None (defaults to today), notes - free text
    # @return: session id
    obs_date = obs_date or time.strftime("%Y-%m-%d")
    cur = db.execute(
        "INSERT INTO project_sessions (project_id, obs_date, notes, created)"
        " VALUES (?, ?, ?, ?)",
        (project_id, obs_date, notes, _now()),
    )
    db.commit()
    return cur.lastrowid


def list_sessions(db, project_id):
    # @return: list of session dicts: pinned visits first, then newest
    #          first by observing date (ADR-045)
    rows = db.execute(
        "SELECT id, project_id, obs_date, notes, created, pinned,"
        " curve_run_id"
        " FROM project_sessions WHERE project_id=?"
        " ORDER BY pinned DESC, obs_date DESC",
        (project_id,),
    ).fetchall()
    return [{"id": r[0], "project_id": r[1], "obs_date": r[2],
             "notes": r[3] or "", "created": r[4], "pinned": bool(r[5]),
             "curve_run_id": r[6]}
            for r in rows]


def get_session(db, session_id):
    # @return: session dict or None
    row = db.execute(
        "SELECT id, project_id, obs_date, notes, created, pinned,"
        " curve_run_id"
        " FROM project_sessions WHERE id=?",
        (session_id,),
    ).fetchone()
    if not row:
        return None
    return {"id": row[0], "project_id": row[1], "obs_date": row[2],
            "notes": row[3] or "", "created": row[4],
            "pinned": bool(row[5]), "curve_run_id": row[6]}


def update_session_notes(db, session_id, notes):
    # @return: True if the session was found
    cur = db.execute(
        "UPDATE project_sessions SET notes=? WHERE id=?",
        (notes, session_id),
    )
    db.commit()
    return cur.rowcount > 0


def update_session_date(db, session_id, obs_date):
    # Edits the visit's date (its visible name in the list). Points
    # already saved to the visit keep their own MJD: they were measured
    # then, and that truth is not rewritten here.
    # @args: obs_date - ISO date string
    # @return: True if the session was found
    cur = db.execute(
        "UPDATE project_sessions SET obs_date=? WHERE id=?",
        (obs_date, session_id),
    )
    db.commit()
    return cur.rowcount > 0


def set_session_pinned(db, session_id, pinned):
    # Pins/unpins a visit: pinned ones float to the top of the list.
    # @return: True if the session was found
    cur = db.execute(
        "UPDATE project_sessions SET pinned=? WHERE id=?",
        (1 if pinned else 0, session_id),
    )
    db.commit()
    return cur.rowcount > 0


def delete_session(db, session_id):
    # @return: True if the session was found and deleted (its files and
    #         photometry points keep living in the project, unlinked —
    #         both links are ON DELETE SET NULL)
    cur = db.execute("DELETE FROM project_sessions WHERE id=?", (session_id,))
    db.commit()
    return cur.rowcount > 0


def days_since_last_session(db, project_id):
    # @return: int days since the most recent session, or None if no sessions
    row = db.execute(
        "SELECT created FROM project_sessions WHERE project_id=?"
        " ORDER BY created DESC LIMIT 1",
        (project_id,),
    ).fetchone()
    if not row:
        return None
    return int((_now() - row[0]) / 86400)


# ---------------- images ----------------
#
# ADR-045: a visit's images live in the single file registry
# (project_files, kind="fits", linked by session_id, header facts in
# meta). The session_images table is gone; the functions below keep the
# established contract on top of it.

def add_image(db, session_id, filter_name, fits_path, date_obs=None,
              exptime_s=None):
    # @args: filter_name - "Clear"/"None" for the no-filter path (B-f),
    #        fits_path - registered, never copied (T4), date_obs - from FITS
    #        header (B1) or None, exptime_s - exposure seconds or None
    # @return: the file id, or None when the visit does not exist
    from . import project as _proj
    sess = get_session(db, session_id)
    if sess is None:
        return None
    meta = {"filter": filter_name, "date_obs": date_obs,
            "exptime_s": exptime_s}
    return _proj.add_file(db, sess["project_id"], fits_path, "fits",
                          session_id=session_id, meta=meta)


def list_images(db, session_id):
    # @return: list of image dicts (the established keys, read from the
    #          registry's meta)
    from . import project as _proj
    out = []
    for f in _proj.files_for_session(db, session_id):
        if f["kind"] != "fits":
            continue
        out.append({"id": f["id"], "session_id": session_id,
                    "filter": f["meta"].get("filter"),
                    "fits_path": f["path"],
                    "date_obs": f["meta"].get("date_obs"),
                    "exptime_s": f["meta"].get("exptime_s")})
    return out


def delete_image(db, image_id):
    # Unlinks a visit's image (the file on disk is never touched).
    # @return: True if the row was found and deleted
    from . import project as _proj
    return _proj.delete_file(db, image_id)


# ---------------- photometry points ----------------

def add_point(db, project_id, mjd, filter_name, mag, err=None, source="manual",
              session_id=None, file_id=None):
    # @args: mjd - Modified Julian Date (float), filter_name - band or
    #        "Clear"/"None", mag - magnitude (float), err - uncertainty or
    #        None, source - manual|paste|file|quicklook|measure|survey,
    #        session_id - the visit it belongs to (or None), file_id - the
    #        plate it was measured on (project_files row, ADR-047) or None
    # @return: point id
    cur = db.execute(
        "INSERT INTO photometry_points (project_id, session_id, mjd,"
        " filter, mag, err, source, file_id)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (project_id, session_id, mjd, filter_name, mag, err, source, file_id),
    )
    db.commit()
    return cur.lastrowid


# ---------------- the curve: one night, one run ----------------
#
# A visit can hold SEVERAL series runs: the observer measures again with
# another band, with another sequence, or just to check something, and
# every run keeps its own points ("undo this run" undoes exactly one, and
# the trail is never silent). But the CURVE of the night is ONE of them.
#
# What went wrong without this (reported 2026-09-30, "the chart of a visit
# gets corrupted when you close and reopen the app"): the chart of a visit
# drew EVERY run of the visit at once. Measured on the real one (V0526
# Per): four runs, 976 points at two different levels (11.96-12.07
# calibrated in G and 12.70-12.81 in V) joined by a zigzag, while the live
# chart had drawn only the last run. The live chart is the truth: it is
# what the observer just measured, so the reloaded one has to draw the
# same. What you see is what you get.
#
# The rule, in the code and in the docs: the curve of a night is the run
# the visit CHOSE (the door "Series > Passes of this visit") and, if it
# never chose, the run of its newest series point. Points with no run
# (hand-entered, pasted, survey context) are never a re-measurement: they
# always belong to the curve.

def _curve_group(session_id, mjd):
    # @args: session_id - the visit of the point, or None, mjd - its time
    # @return: what makes two series points share one curve: the VISIT
    #          when they have one (a visit is one night by construction),
    #          else the observing night of their mjd (the points measured
    #          before visits existed: a project holds several of those and
    #          re-measuring the same night must not double the curve)
    if session_id is not None:
        return ("visit", session_id)
    from . import series_measure
    return ("night", series_measure._night_of(mjd))


def _series_point_rows(db, project_id=None, session_id=None):
    # The series points, in INSERTION order: the last row of a group is
    # the last thing that was measured for it, which is the whole point.
    # @return: rows of (id, session_id, run_id, mjd)
    sql = ("SELECT id, session_id, run_id, mjd FROM photometry_points"
           " WHERE source='measure' AND run_id IS NOT NULL")
    params = []
    if project_id is not None:
        sql += " AND project_id=?"
        params.append(project_id)
    if session_id is not None:
        sql += " AND session_id=?"
        params.append(session_id)
    sql += " ORDER BY id"
    return db.execute(sql, tuple(params)).fetchall()


def _chosen_runs(db, project_id=None, session_id=None):
    # @return: {session_id: run_id} of the visits that said which of
    #          their runs the chart shows
    sql = ("SELECT id, curve_run_id FROM project_sessions"
           " WHERE curve_run_id IS NOT NULL")
    params = []
    if project_id is not None:
        sql += " AND project_id=?"
        params.append(project_id)
    if session_id is not None:
        sql += " AND id=?"
        params.append(session_id)
    return {r[0]: r[1] for r in db.execute(sql, tuple(params)).fetchall()}


def curve_run_ids(db, project_id=None, session_id=None):
    # Which run each curve is made of.
    # @args: db - Database, project_id - limit to one project or None,
    #        session_id - limit to one visit or None
    # @return: the set of run ids whose points are the curve (one per
    #          visit, or per night for the points that have no visit)
    rows = _series_point_rows(db, project_id=project_id,
                              session_id=session_id)
    with_points = {r[2] for r in rows}
    newest = {}
    for r in rows:
        # later rows overwrite earlier ones: the newest measurement wins
        newest[_curve_group(r[1], r[3])] = r[2]
    for sid, run_id in _chosen_runs(db, project_id=project_id,
                                    session_id=session_id).items():
        # The visit's choice wins, as long as that run still HAS points: an
        # undone run has none, so the curve falls back to the previous one,
        # which is exactly what "undo this run" should show.
        if run_id in with_points:
            newest[_curve_group(sid, None)] = run_id
    return set(newest.values())


def curve_run_for_session(db, session_id):
    # @return: the run the visit's curve is, or None when it has none
    ids = curve_run_ids(db, session_id=session_id)
    return next(iter(ids)) if len(ids) == 1 else None


def set_session_curve_run(db, session_id, run_id):
    # "Make this pass the curve" (the passes door). Nothing is deleted and
    # nothing is re-measured: the visit remembers which of its runs the
    # chart shows, and every reader follows.
    # @return: True when the visit was found
    cur = db.execute(
        "UPDATE project_sessions SET curve_run_id=? WHERE id=?",
        (run_id, session_id))
    db.commit()
    return cur.rowcount > 0


def list_points(db, project_id, filter_name=None, curve=True):
    # @args: filter_name - filter to select, or None for all, curve - True
    #        (default) for the project's CURVE: one run per night, so a
    #        night measured several times counts once; False for every
    #        point the project holds (the audit path, and the tests that
    #        check the trail)
    # @return: list of point dicts ordered by mjd (file_id: the plate it
    #          was measured on, or None; mag_raw/flags/run_id carry the
    #          series data when the point came from one, ADR-048)
    col = ("id, project_id, session_id, mjd, filter, mag, err, source,"
           " file_id, mag_raw, flags, run_id, err_internal,"
           " airmass, x, y, fwhm, sky")
    if filter_name:
        rows = db.execute(
            f"SELECT {col} FROM photometry_points WHERE project_id=?"
            " AND filter=? ORDER BY mjd",
            (project_id, filter_name),
        ).fetchall()
    else:
        rows = db.execute(
            f"SELECT {col} FROM photometry_points WHERE project_id=?"
            " ORDER BY mjd",
            (project_id,),
        ).fetchall()
    points = [_point_dict(r) for r in rows]
    if not curve:
        return points
    keep = curve_run_ids(db, project_id=project_id)
    return [p for p in points
            if p["run_id"] is None or p["run_id"] in keep]


def _point_dict(row):
    # @args: row - a photometry_points row in the list_points column order
    # @return: the point dict the callers use (flags parsed from JSON)
    def at(i):
        # @return: the column when the query carries it, else None (the
        #          pattern err_internal started: an old query keeps working)
        return row[i] if len(row) > i else None
    return {"id": row[0], "project_id": row[1], "session_id": row[2],
            "mjd": row[3], "filter": row[4], "mag": row[5], "err": row[6],
            "source": row[7], "file_id": row[8], "mag_raw": row[9],
            "flags": _flags_in(row[10]), "run_id": row[11],
            "err_internal": at(12),
            # what the NIGHT figures are made of (the airmass and the
            # measured position): with them stored, a curve read back from
            # the database explains its own night months later instead of
            # demanding a new run
            "airmass": at(13), "x": at(14), "y": at(15),
            "fwhm": at(16), "sky": at(17)}


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


def point_by_id(db, point_id):
    # Looks up a single photometry point by its id (ADR-047: the visit
    # window's click-a-measurement flow needs the full row, with file_id).
    # @return: point dict (as list_points), or None
    row = db.execute(
        "SELECT id, project_id, session_id, mjd, filter, mag, err,"
        " source, file_id, mag_raw, flags, run_id, err_internal,"
        " airmass, x, y, fwhm, sky"
        " FROM photometry_points WHERE id=?", (point_id,)).fetchone()
    return _point_dict(row) if row else None


def create_run(db, session_id=None, cfg=None, status="complete"):
    # ADR-048: one "Measure" is a run (D9). Its config and status are
    # stored so the run survives a restart and "incomplete" is visible.
    # @args: cfg - dict stored as JSON (may be None), status - complete |
    #        incomplete | undone
    # @return: the new run id
    cur = db.execute(
        "INSERT INTO measurement_runs (session_id, created, cfg_json,"
        " status) VALUES (?, ?, ?, ?)",
        (session_id, time.time(),
         json.dumps(cfg or {}, ensure_ascii=False), status))
    db.commit()
    run_id = cur.lastrowid
    # A NEW series run IS the visit's curve: the observer just measured it,
    # and that is what the live chart shows, so the reloaded one must show
    # it too. The door "Series > Passes of this visit" is what goes back to
    # an earlier pass, and that choice survives until the next run.
    if session_id is not None and isinstance(cfg, dict) and "series" in cfg:
        set_session_curve_run(db, session_id, run_id)
    return run_id


def set_run_status(db, run_id, status):
    # @return: True if the run was found and updated
    cur = db.execute("UPDATE measurement_runs SET status=? WHERE id=?",
                     (status, run_id))
    db.commit()
    return cur.rowcount > 0


def save_pass(db, entries, cfg=None):
    # A campaign pass writes ONE run per project (E5c).
    #
    # The frames, the comparison stars and the zero point were measured a
    # single time; each project still receives its own run and its own
    # points, because a project is one object and "undo this run" must
    # undo exactly that object's curve. The shared facts (which pass this
    # was, which other objects were measured with it) ride in the run's
    # cfg echo, so the journal can say so without a schema change.
    # @args: db - Database, entries - [{"project_id", "session_id", "rows",
    #        "label"}], cfg - JSON-safe echo of the shared configuration
    #        (it gets a "pass" block with the labels of the whole pass)
    # @return: [{"project_id", "label", "run_id", "session_id", "points"}]
    labels = [e.get("label") or "" for e in entries]
    out = []
    for entry in entries:
        rows = list(entry.get("rows") or [])
        echo = dict(cfg or {})
        echo["pass"] = {"labels": [l for l in labels if l],
                        "target": entry.get("label") or "",
                        "campaign": echo.get("campaign")}
        run_id = create_run(db, session_id=entry.get("session_id"),
                            cfg=echo, status=entry.get("status")
                            or "complete")
        for r in rows:
            r["project_id"] = entry["project_id"]
            r["session_id"] = entry.get("session_id")
            r["run_id"] = run_id
        ids = add_points(db, rows) if rows else []
        out.append({"project_id": entry["project_id"],
                    "label": entry.get("label") or "",
                    "run_id": run_id,
                    "session_id": entry.get("session_id"),
                    "points": len(ids)})
    return out


def share_frames(db, paths, projects, obs_date=None, notes="", meta=None):
    # The same frames in every project of a pass (E5c).
    #
    # A pass measures one set of files for several objects, and a visit is
    # a night of ONE project: so each of those projects gets its own visit
    # that night, holding those very files. Nothing is copied: the paths
    # are registered, exactly as if the observer had attached them by hand
    # in each project.
    #
    # A project that already has a visit with those frames reuses it (that
    # is the point of a pass: measuring what was already filed).
    # @args: db - Database, paths - the frames of the pass, projects -
    #        [{"project_id"} | {"id"}] of the projects that will hold them,
    #        obs_date - the night (ISO date) for the visits it creates,
    #        notes - the visit's note, meta - plate facts per path or None
    # @return: {project_id: session_id}
    from . import project as project_mod
    out = {}
    for p in projects or []:
        pid = p.get("project_id") or p.get("id")
        if pid is None:
            continue
        have = {}
        for s in list_sessions(db, pid):
            for f in project_mod.files_for_session(db, s["id"]):
                if f.get("kind") == "fits" and f.get("path"):
                    have[str(f["path"])] = s["id"]
        wanted = [str(x) for x in paths or []]
        session_id = next((have[w] for w in wanted if w in have), None)
        if session_id is None:
            session_id = create_session(db, pid, obs_date=obs_date,
                                        notes=notes or "")
        already = set()
        for f in project_mod.files_for_session(db, session_id):
            if f.get("kind") == "fits" and f.get("path"):
                already.add(str(f["path"]))
        facts = meta if isinstance(meta, dict) else {}
        for path in wanted:
            if path in already:
                continue
            project_mod.add_file(db, pid, path, "fits",
                                 session_id=session_id,
                                 meta=facts.get(path))
        out[pid] = session_id
    return out


def add_points(db, rows):
    # Batch write of series points (ADR-048, D9/D18): one transaction for
    # a whole run. Each row is a dict with project_id, session_id, mjd,
    # filter, mag, err, source, file_id, mag_raw, flags, run_id, airmass,
    # x, y, fwhm, sky; missing keys become NULL (the legacy single-point
    # contract is unchanged);
    # err_internal is the point's OWN photon error, apart from the
    # calibration systematic that `err` (the total) carries (quality plan,
    # phase A).
    # @return: the list of new point ids
    ids = []
    for r in rows:
        flags = r.get("flags")
        if isinstance(flags, (list, tuple)):
            flags = json.dumps(list(flags), ensure_ascii=False)
        cur = db.execute(
            "INSERT INTO photometry_points (project_id, session_id, mjd,"
            " filter, mag, err, source, file_id, mag_raw, flags, run_id,"
            " err_internal, airmass, x, y, fwhm, sky)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (r.get("project_id"), r.get("session_id"), r.get("mjd"),
             r.get("filter"), r.get("mag"), r.get("err"),
             r.get("source") or "measure", r.get("file_id"),
             r.get("mag_raw"), flags, r.get("run_id"),
             r.get("err_internal"), r.get("airmass"), r.get("x"),
             r.get("y"), r.get("fwhm"), r.get("sky")))
        ids.append(cur.lastrowid)
    db.commit()
    return ids


def list_points_for_run(db, run_id):
    # @return: the points of one run, mjd-ordered
    rows = db.execute(
        "SELECT id, project_id, session_id, mjd, filter, mag, err, source,"
        " file_id, mag_raw, flags, run_id, err_internal,"
        " airmass, x, y, fwhm, sky"
        " FROM photometry_points WHERE run_id=? ORDER BY mjd",
        (run_id,)).fetchall()
    return [_point_dict(r) for r in rows]


def points_for_session(db, session_id, series_only=True, curve=True):
    # The points a VISIT holds, oldest first.
    #
    # `series_only` keeps the ones the series engine wrote (source
    # "measure"): they are the curve. A hand-entered or survey point in the
    # same visit is context, not the night's measurement, and it is not
    # touched by the visit's curve nor by discarding it.
    #
    # `curve` keeps ONE run (the visit's curve, see curve_run_ids): the
    # visit may hold several passes and drawing all of them at once is the
    # corruption this file's "one night, one run" section explains. False
    # returns every series point of the visit (the trail).
    # @args: db - Database, session_id - the visit, series_only - the
    #        curve's own points only, curve - the visit's curve, not every
    #        pass it holds
    # @return: [{id, project_id, session_id, mjd, filter, mag, err, source,
    #           file_id, mag_raw, flags, run_id, err_internal, airmass, x,
    #           y, fwhm, sky}, ...]
    sql = ("SELECT id, project_id, session_id, mjd, filter, mag, err, source,"
           " file_id, mag_raw, flags, run_id, err_internal,"
           " airmass, x, y, fwhm, sky"
           " FROM photometry_points WHERE session_id=?")
    params = [session_id]
    if series_only:
        sql += " AND source=?"
        params.append("measure")
    sql += " ORDER BY mjd"
    points = [_point_dict(r) for r in db.execute(sql, tuple(params))]
    if not curve:
        return points
    keep = curve_run_ids(db, session_id=session_id)
    return [p for p in points
            if p["run_id"] is None or p["run_id"] in keep]


def get_run(db, run_id):
    # One run by id, in the same shape runs_for_session hands out (the
    # curve's reader needs its band and its detrend choice: they are what
    # the stored points no longer carry).
    # @return: the run dict, or None
    if run_id is None:
        return None
    row = db.execute(
        "SELECT r.id, r.session_id, r.created, r.cfg_json, r.status,"
        " (SELECT COUNT(*) FROM photometry_points p WHERE p.run_id = r.id),"
        " (SELECT MIN(p.mjd) FROM photometry_points p WHERE p.run_id = r.id),"
        " (SELECT MAX(p.mjd) FROM photometry_points p WHERE p.run_id = r.id)"
        " FROM measurement_runs r WHERE r.id=?", (run_id,)).fetchone()
    if not row:
        return None
    cfg = json.loads(row[3] or "{}")
    series = cfg.get("series") or {}
    return {"id": row[0], "session_id": row[1], "created": row[2],
            "cfg": cfg, "status": row[4], "points": row[5] or 0,
            "mjd0": row[6], "mjd1": row[7], "band": series.get("band")}


def reusable_run(db, run_id, session_id=None):
    # A live session writes its batches into ONE run ("the whole live
    # session is undone as one run", ADR-050 P2 #19), so a batch asks
    # whether the run it wants to continue is still usable: it exists, it
    # is not undone and it belongs to the same visit.
    #
    # Measured why it matters for the curve too: one run per batch left a
    # visit with 49 runs for a single night, so the curve reloaded from the
    # project was the LAST BATCH (a few frames) instead of the live curve
    # the observer had just watched grow.
    # @args: db - Database, run_id - the run the batch wants to continue
    #        (or None), session_id - the visit of the batch
    # @return: the run id, or None (a run that is gone is never an error:
    #          the batch opens a new one)
    if run_id is None:
        return None
    row = db.execute("SELECT id, session_id, status FROM measurement_runs"
                     " WHERE id=?", (run_id,)).fetchone()
    if not row or (row[2] or "") == "undone":
        return None
    if session_id is not None and row[1] is not None and row[1] != session_id:
        return None
    return row[0]


def runs_for_session(db, session_id, series_only=True):
    # The runs a visit holds, oldest first, with what the passes door needs
    # to show them: how many points each one holds and the stretch of night
    # it covers (so the observer can tell a full pass from the stub a
    # cancelled run leaves).
    # @return: [{id, session_id, created, cfg, status, points, mjd0, mjd1,
    #           band}, ...]
    rows = db.execute(
        "SELECT r.id, r.session_id, r.created, r.cfg_json, r.status,"
        " COUNT(p.id), MIN(p.mjd), MAX(p.mjd)"
        " FROM measurement_runs r"
        " LEFT JOIN photometry_points p ON p.run_id = r.id"
        " WHERE r.session_id=? GROUP BY r.id ORDER BY r.id",
        (session_id,)).fetchall()
    out = []
    for r in rows:
        cfg = json.loads(r[3] or "{}")
        if series_only and "series" not in cfg:
            continue
        series = cfg.get("series") or {}
        out.append({"id": r[0], "session_id": r[1], "created": r[2],
                    "cfg": cfg, "status": r[4], "points": r[5] or 0,
                    "mjd0": r[6], "mjd1": r[7],
                    "band": series.get("band")})
    return out


def discard_session_curve(db, session_id):
    # "Discard this visit's curve, and build it again from scratch": every
    # SERIES run of the visit is undone the way the per-run undo does it
    # (its points go, its run row stays marked undone, so the trail is never
    # silent). The visit's other points (hand-entered, survey) are not part
    # of the curve and are left alone.
    # @args: db - Database, session_id - the visit
    # @return: (runs undone, points removed)
    runs = runs_for_session(db, session_id)
    removed = 0
    for run in runs:
        removed += delete_points_for_run(db, run["id"])
        set_run_status(db, run["id"], "undone")
    # the visit has no curve left to show: the choice goes with it (and a
    # new run will set it again)
    set_session_curve_run(db, session_id, None)
    return len(runs), removed


def delete_points(db, ids):
    # Undo by explicit id list (ADR-048): never touches another run.
    # @return: the number of points deleted
    if not ids:
        return 0
    marks = ",".join("?" for _ in ids)
    cur = db.execute(f"DELETE FROM photometry_points WHERE id IN ({marks})",
                     tuple(ids))
    db.commit()
    return cur.rowcount


def delete_points_for_run(db, run_id):
    # "Undo this run" (D6): the run's points go; the run row stays for
    # the audit trail.
    # @return: the number of points deleted
    cur = db.execute("DELETE FROM photometry_points WHERE run_id=?",
                     (run_id,))
    db.commit()
    return cur.rowcount


def delete_point(db, point_id):
    # @return: True if the point was found and deleted
    cur = db.execute("DELETE FROM photometry_points WHERE id=?", (point_id,))
    db.commit()
    return cur.rowcount > 0


def delete_points_for_file(db, file_id):
    # The UFE's "delete this plate's measurements" reset (ADR-047): only
    # the points tied to ONE plate go. Points without a plate (legacy,
    # paste, survey) are never touched here.
    # @return: number of points deleted
    cur = db.execute("DELETE FROM photometry_points WHERE file_id=?",
                     (file_id,))
    db.commit()
    return cur.rowcount


def upsert_survey_points(db, project_id, points, source="survey:ztf"):
    # Idempotent survey sync (2026-09-17): the re-click button re-queries the
    # API and this mirrors the result into the DB. Key per point:
    # (round(mjd,6), coalesce(filter,'')). Only rows with source LIKE
    # 'survey:%' are ever read/updated/deleted — paste, manual, file and
    # quicklook points are off limits.
    # @args: points - [{"mjd","filter","mag","err"}] from
    #        surveys.fetch_points_detailed (may be empty), source -
    #        "survey:ztf" (must start with "survey:")
    # @return: {"added","updated","unchanged","removed"} (ints)
    # Raises ValueError on a non-gated project kind or a foreign source;
    # bad individual rows (no mjd/mag) are skipped, never fatal.
    row = db.execute("SELECT kind FROM projects WHERE id=?",
                     (project_id,)).fetchone()
    if not row or row[0] not in ("sn", "variable"):
        raise ValueError("survey points are only for sn/variable projects")
    if not str(source).startswith("survey:"):
        raise ValueError("source must start with 'survey:'")

    incoming = {}
    for p in points or []:
        mjd, mag = p.get("mjd"), p.get("mag")
        if mjd is None or mag is None:
            continue                        # not a point — drop it, no error
        incoming[(round(float(mjd), 6), p.get("filter") or "")] = (
            float(mjd), p.get("filter") or "", mag, p.get("err"))

    added = updated = unchanged = removed = 0
    if incoming:                            # empty = "no data", never wipe
        existing = db.execute(
            "SELECT id, ROUND(mjd, 6), COALESCE(filter,''), mag, err"
            " FROM photometry_points WHERE project_id=?"
            " AND source LIKE 'survey:%'", (project_id,)).fetchall()
        seen = set()
        for row_id, m, filt, mag, err in existing:
            key = (m, filt)
            if key not in incoming:
                # stale point the API no longer reports — drop it
                db.execute("DELETE FROM photometry_points WHERE id=?",
                           (row_id,)); removed += 1; continue
            seen.add(key)
            _, _, mag, err = incoming[key]
            cur = db.execute(
                "SELECT mag, err FROM photometry_points WHERE id=?",
                (row_id,)).fetchone()
            if cur and (cur[0] == mag and cur[1] == err):
                unchanged += 1
            else:
                db.execute(
                    "UPDATE photometry_points SET mag=?, err=? WHERE id=?",
                    (mag, err, row_id)); updated += 1
        for key, (mjd, filt, mag, err) in incoming.items():
            if key not in seen:
                db.execute(
                    "INSERT INTO photometry_points (project_id, session_id,"
                    " mjd, filter, mag, err, source)"
                    " VALUES (?, NULL, ?, ?, ?, ?, ?)",
                    (project_id, mjd, filt or None, mag, err, source))
                added += 1
    db.commit()
    return {"added": added, "updated": updated,
            "unchanged": unchanged, "removed": removed}
