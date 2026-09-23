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

"""Multi-night follow-up storage for SN projects.

A follow-up is a tree: project → sessions (one per observing night) →
images (one stacked FITS per filter) and photometry points (imported
from AIJ/Tycho-Tracker or produced by the quick-look differential engine).

All SQL goes through db.execute (ADR-002). The module mirrors the
pragmatic style of core/project.py: short functions, no ORM, no magic.
"""

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
    # @return: list of session dicts ordered by obs_date
    rows = db.execute(
        "SELECT id, project_id, obs_date, notes, created"
        " FROM project_sessions WHERE project_id=? ORDER BY obs_date DESC",
        (project_id,),
    ).fetchall()
    return [{"id": r[0], "project_id": r[1], "obs_date": r[2],
             "notes": r[3] or "", "created": r[4]} for r in rows]


def get_session(db, session_id):
    # @return: session dict or None
    row = db.execute(
        "SELECT id, project_id, obs_date, notes, created"
        " FROM project_sessions WHERE id=?",
        (session_id,),
    ).fetchone()
    if not row:
        return None
    return {"id": row[0], "project_id": row[1], "obs_date": row[2],
            "notes": row[3] or "", "created": row[4]}


def update_session_notes(db, session_id, notes):
    # @return: True if the session was found
    cur = db.execute(
        "UPDATE project_sessions SET notes=? WHERE id=?",
        (notes, session_id),
    )
    db.commit()
    return cur.rowcount > 0


def delete_session(db, session_id):
    # @return: True if the session was found and deleted (images cascade,
    #         photometry points keep their mag but lose the link)
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

def add_image(db, session_id, filter_name, fits_path, date_obs=None,
              exptime_s=None):
    # @args: filter_name - "Clear"/"None" for the no-filter path (B-f),
    #        fits_path - registered, never copied (T4), date_obs - from FITS
    #        header (B1) or None, exptime_s - exposure seconds or None
    # @return: image id
    cur = db.execute(
        "INSERT INTO session_images (session_id, filter, fits_path,"
        " date_obs, exptime_s) VALUES (?, ?, ?, ?, ?)",
        (session_id, filter_name, str(fits_path), date_obs, exptime_s),
    )
    db.commit()
    return cur.lastrowid


def list_images(db, session_id):
    # @return: list of image dicts
    rows = db.execute(
        "SELECT id, session_id, filter, fits_path, date_obs, exptime_s"
        " FROM session_images WHERE session_id=? ORDER BY id",
        (session_id,),
    ).fetchall()
    return [{"id": r[0], "session_id": r[1], "filter": r[2],
             "fits_path": r[3], "date_obs": r[4], "exptime_s": r[5]}
            for r in rows]


# ---------------- photometry points ----------------

def add_point(db, project_id, mjd, filter_name, mag, err=None, source="manual",
              session_id=None):
    # @args: mjd - Modified Julian Date (float), filter_name - band or
    #        "Clear"/"None", mag - magnitude (float), err - uncertainty or
    #        None, source - manual|paste|file|quicklook|measure|survey
    # @return: point id
    cur = db.execute(
        "INSERT INTO photometry_points (project_id, session_id, mjd,"
        " filter, mag, err, source) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (project_id, session_id, mjd, filter_name, mag, err, source),
    )
    db.commit()
    return cur.lastrowid


def list_points(db, project_id, filter_name=None):
    # @args: filter_name - filter to select, or None for all
    # @return: list of point dicts ordered by mjd
    if filter_name:
        rows = db.execute(
            "SELECT id, project_id, session_id, mjd, filter, mag, err, source"
            " FROM photometry_points WHERE project_id=? AND filter=?"
            " ORDER BY mjd",
            (project_id, filter_name),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT id, project_id, session_id, mjd, filter, mag, err, source"
            " FROM photometry_points WHERE project_id=? ORDER BY mjd",
            (project_id,),
        ).fetchall()
    return [{"id": r[0], "project_id": r[1], "session_id": r[2],
             "mjd": r[3], "filter": r[4], "mag": r[5], "err": r[6],
             "source": r[7]} for r in rows]


def delete_point(db, point_id):
    # @return: True if the point was found and deleted
    cur = db.execute("DELETE FROM photometry_points WHERE id=?", (point_id,))
    db.commit()
    return cur.rowcount > 0


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
