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
        "SELECT id, project_id, obs_date, notes, created, pinned"
        " FROM project_sessions WHERE project_id=?"
        " ORDER BY pinned DESC, obs_date DESC",
        (project_id,),
    ).fetchall()
    return [{"id": r[0], "project_id": r[1], "obs_date": r[2],
             "notes": r[3] or "", "created": r[4], "pinned": bool(r[5])}
            for r in rows]


def get_session(db, session_id):
    # @return: session dict or None
    row = db.execute(
        "SELECT id, project_id, obs_date, notes, created, pinned"
        " FROM project_sessions WHERE id=?",
        (session_id,),
    ).fetchone()
    if not row:
        return None
    return {"id": row[0], "project_id": row[1], "obs_date": row[2],
            "notes": row[3] or "", "created": row[4],
            "pinned": bool(row[5])}


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


def list_points(db, project_id, filter_name=None):
    # @args: filter_name - filter to select, or None for all
    # @return: list of point dicts ordered by mjd (file_id: the plate it
    #          was measured on, or None; mag_raw/flags/run_id carry the
    #          series data when the point came from one, ADR-048)
    col = ("id, project_id, session_id, mjd, filter, mag, err, source,"
           " file_id, mag_raw, flags, run_id")
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
    return [_point_dict(r) for r in rows]


def _point_dict(row):
    # @args: row - a photometry_points row in the list_points column order
    # @return: the point dict the callers use (flags parsed from JSON)
    return {"id": row[0], "project_id": row[1], "session_id": row[2],
            "mjd": row[3], "filter": row[4], "mag": row[5], "err": row[6],
            "source": row[7], "file_id": row[8], "mag_raw": row[9],
            "flags": _flags_in(row[10]), "run_id": row[11]}


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
        " source, file_id, mag_raw, flags, run_id FROM photometry_points"
        " WHERE id=?", (point_id,)).fetchone()
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
    return cur.lastrowid


def set_run_status(db, run_id, status):
    # @return: True if the run was found and updated
    cur = db.execute("UPDATE measurement_runs SET status=? WHERE id=?",
                     (status, run_id))
    db.commit()
    return cur.rowcount > 0


def add_points(db, rows):
    # Batch write of series points (ADR-048, D9/D18): one transaction for
    # a whole run. Each row is a dict with project_id, session_id, mjd,
    # filter, mag, err, source, file_id, mag_raw, flags, run_id; missing
    # keys become NULL (the legacy single-point contract is unchanged).
    # @return: the list of new point ids
    ids = []
    for r in rows:
        flags = r.get("flags")
        if isinstance(flags, (list, tuple)):
            flags = json.dumps(list(flags), ensure_ascii=False)
        cur = db.execute(
            "INSERT INTO photometry_points (project_id, session_id, mjd,"
            " filter, mag, err, source, file_id, mag_raw, flags, run_id)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (r.get("project_id"), r.get("session_id"), r.get("mjd"),
             r.get("filter"), r.get("mag"), r.get("err"),
             r.get("source") or "measure", r.get("file_id"),
             r.get("mag_raw"), flags, r.get("run_id")))
        ids.append(cur.lastrowid)
    db.commit()
    return ids


def list_points_for_run(db, run_id):
    # @return: the points of one run, mjd-ordered
    rows = db.execute(
        "SELECT id, project_id, session_id, mjd, filter, mag, err, source,"
        " file_id, mag_raw, flags, run_id FROM photometry_points"
        " WHERE run_id=? ORDER BY mjd", (run_id,)).fetchall()
    return [_point_dict(r) for r in rows]


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
