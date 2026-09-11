############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Project model and step machine (ADR-019)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import datetime
import json
import logging
import time

from .. import paths
from ..config import config

logger = logging.getLogger(__name__)

# A project carries the full context of an observing target through a guided
# flow. Steps and kinds are fixed strings so the GUI and CLI can switch on
# them safely. All SQL goes through db.execute (ADR-002).
# Reviews: "analyse" dropped (2026-08-28, ADR-019) — its only real content
# (the SN blink) now lives in "process", and the explore view is already the
# Details tab. "capture" merged into "plan" (2026-09-06, ADR-030): planning
# the session and exporting/running it against CCDciel is one step now.

STEPS = ("plan", "process", "publish")
VALID_KINDS = ("sn", "neo", "comet", "pccp", "transit", "hads", "variable")

STEP_PENDING = "pending"
STEP_CURRENT = "current"
STEP_DONE = "done"
STEP_SKIPPED = "skipped"

STATUS_ACTIVE = "active"
STATUS_DONE = "done"
STATUS_ARCHIVED = "archived"

# Final outcome of a closed project (Track A, project-concept v2). The GUI
# builds its selector from these; "Other" is free text the caller passes
# straight through close() — the column is free TEXT, never validated here.
# SN carries the richest set (follow-up can confirm/reject a candidate); the
# rest share a generic completed/abandoned pair.
OUTCOMES = {
    "sn": ("confirmed_ia", "confirmed_other", "false_positive", "lost",
           "completed"),
    "neo": ("completed", "reported_mpc", "abandoned"),
    "comet": ("completed", "abandoned"),
    "pccp": ("confirmed", "false_positive", "lost", "completed"),
    "transit": ("completed", "reported_exoclock", "abandoned"),
    "hads": ("completed", "reported_aavso", "abandoned"),
    "variable": ("caught", "not_caught", "completed", "abandoned"),
}
OUTCOME_DEFAULT = ("completed", "abandoned")


def _now():
    # @return: current epoch seconds
    return time.time()


def _json_default(obj):
    # @args: obj - any object
    # @return: a JSON-safe representation (datetimes as ISO strings)
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    raise TypeError(f"not JSON serializable: {type(obj)}")


def _row_to_project(row):
    # @return: project dict from a SELECT row
    # Row order: id, kind, object_name, status, created, updated, context,
    # root_dir (ADR-032, the explicit container folder), closed_at, outcome,
    # tags, favorite (Track A columns, nullable), campaign_id (ADR-035, the
    # observation campaign the project hangs from; NULL if none).
    return {"id": row[0], "kind": row[1], "object_name": row[2],
            "status": row[3], "created": row[4], "updated": row[5],
            "context": json.loads(row[6] or "{}"), "root_dir": row[7],
            "closed_at": row[8], "outcome": row[9],
            "tags": row[10] or "", "favorite": bool(row[11]),
            "campaign_id": row[12]}


def _row_to_step(row):
    # @return: step dict from a SELECT row
    return {"id": row[0], "project_id": row[1], "step": row[2],
            "status": row[3], "data": json.loads(row[4] or "{}"),
            "updated": row[5]}


def _row_to_file(row):
    # @return: file dict from a SELECT row
    return {"id": row[0], "project_id": row[1], "path": row[2],
            "kind": row[3], "created": row[4]}


def create(db, kind, object_name, context=None, campaign_id=None):
    # Creates a project with all steps initialised; the first step is current.
    # @args: db - Database, kind - one of VALID_KINDS, object_name - target,
    #        context - dict snapshot from the planner (coords, mag, rate...),
    #        campaign_id - int or None (ADR-035, the campaign it hangs from)
    # @return: full project dict (with steps and files), or None on bad kind
    if kind not in VALID_KINDS:
        logger.warning("unknown project kind: %s", kind)
        return None
    now = _now()
    ctx = json.dumps(context or {}, ensure_ascii=False, default=_json_default)
    # The container root is frozen at creation: later changes to the
    # configured projects_root only affect new projects (ADR-032).
    root = config.get("projects_root") or str(paths.data_dir() / "projects")
    cur = db.execute(
        "INSERT INTO projects (kind, object_name, status, created, updated,"
        " context, root_dir, campaign_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (kind, object_name, STATUS_ACTIVE, now, now, ctx, root, campaign_id),
    )
    pid = cur.lastrowid
    for i, step in enumerate(STEPS):
        st = STEP_CURRENT if i == 0 else STEP_PENDING
        db.execute(
            "INSERT INTO project_steps (project_id, step, status, data,"
            " updated) VALUES (?, ?, ?, '{}', ?)",
            (pid, step, st, now),
        )
    db.commit()
    logger.info("created project %d (%s/%s)", pid, kind, object_name)
    return get(db, pid)


def storage_dir(p):
    # @args: p - project dict (with the root_dir the DB row carries)
    # @return: Path to this project's container folder. The project's own
    #          root_dir wins; a row without it falls back to the configured
    #          projects_root and then to the legacy data dir location.
    root = p.get("root_dir") or config.get("projects_root") or ""
    return paths.project_dir(p["id"], p["object_name"], root=root)


def set_root_dir(db, project_id, path):
    # Re-homes a project's container folder. Only future exports follow the
    # new root (project_files keep absolute paths, so history stays intact).
    # @args: db - Database, project_id - int, path - new directory (absolute)
    # @return: updated project dict, or None if not found
    db.execute("UPDATE projects SET root_dir=?, updated=? WHERE id=?",
               (str(path), _now(), project_id))
    db.commit()
    return get(db, project_id)


def list_projects(db, status=None, kind=None, campaign_id=None, search=None,
                  tags=None, favorites_first=False, order="updated"):
    # @args: db - Database, status - active|done|archived or None for all,
    #        kind - filter by VALID_KINDS entry or None,
    #        campaign_id - int or None (filter by observation campaign),
    #        search - case-insensitive substring on object_name or None,
    #        tags - substring to match against the tags column or None,
    #        favorites_first - ORDER BY favorite DESC before the chosen order,
    #        order - "updated" | "created" | "name"
    # @return: list of project dicts (without steps/files)
    cols = ("id, kind, object_name, status, created, updated, context,"
            " root_dir, closed_at, outcome, tags, favorite, campaign_id")
    where, params = [], []
    if status:
        where.append("status=?")
        params.append(status)
    if kind:
        where.append("kind=?")
        params.append(kind)
    if campaign_id:
        where.append("campaign_id=?")
        params.append(campaign_id)
    if search:
        where.append("LOWER(object_name) LIKE ?")
        params.append(f"%{search.lower()}%")
    if tags:
        where.append("LOWER(tags) LIKE ?")
        params.append(f"%{tags.lower()}%")
    order_map = {"updated": "updated DESC", "created": "created DESC",
                 "name": "object_name COLLATE NOCASE"}
    order_clause = order_map.get(order, "updated DESC")
    if favorites_first:
        order_clause = f"favorite DESC, {order_clause}"
    sql = f"SELECT {cols} FROM projects"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += f" ORDER BY {order_clause}"
    rows = db.execute(sql, params).fetchall()
    return [_row_to_project(r) for r in rows]


def get(db, project_id):
    # @args: db - Database, project_id - int
    # @return: project dict with steps and files, or None if not found
    row = db.execute(
        "SELECT id, kind, object_name, status, created, updated, context,"
        " root_dir, closed_at, outcome, tags, favorite, campaign_id"
        " FROM projects WHERE id=?",
        (project_id,),
    ).fetchone()
    if not row:
        return None
    proj = _row_to_project(row)
    srows = db.execute(
        "SELECT id, project_id, step, status, data, updated"
        " FROM project_steps WHERE project_id=? ORDER BY id",
        (project_id,),
    ).fetchall()
    proj["steps"] = [_row_to_step(s) for s in srows]
    proj["files"] = list_files(db, project_id)
    return proj


def current_step(db, project_id):
    # @return: step name that is currently active, or None
    proj = get(db, project_id)
    if not proj:
        return None
    for s in proj["steps"]:
        if s["status"] == STEP_CURRENT:
            return s["step"]
    return None


def advance(db, project_id):
    # Marks the current step as done and activates the next one.
    # When the last step is done, the project status becomes 'done'.
    # @return: updated project dict, or None if not found
    proj = get(db, project_id)
    if not proj:
        return None
    steps = proj["steps"]
    idx = None
    for i, s in enumerate(steps):
        if s["status"] == STEP_CURRENT:
            idx = i
            break
    if idx is None:
        return proj  # nothing to advance
    now = _now()
    db.execute("UPDATE project_steps SET status=?, updated=? WHERE id=?",
               (STEP_DONE, now, steps[idx]["id"]))
    if idx + 1 < len(steps):
        db.execute("UPDATE project_steps SET status=?, updated=? WHERE id=?",
                   (STEP_CURRENT, now, steps[idx + 1]["id"]))
    else:
        db.execute("UPDATE projects SET status=?, updated=? WHERE id=?",
                   (STATUS_DONE, now, project_id))
    db.commit()
    return get(db, project_id)


def set_step_status(db, project_id, step, status):
    # Manually sets a step's status (e.g. skip a step).
    # @return: True if the step was found and updated
    now = _now()
    cur = db.execute(
        "UPDATE project_steps SET status=?, updated=?"
        " WHERE project_id=? AND step=?",
        (status, now, project_id, step),
    )
    db.commit()
    return cur.rowcount > 0


def update_step_data(db, project_id, step, data):
    # Merges data (dict) into the step's JSON data field.
    # @return: True if the step was found and updated
    row = db.execute(
        "SELECT data FROM project_steps WHERE project_id=? AND step=?",
        (project_id, step),
    ).fetchone()
    if not row:
        return False
    existing = json.loads(row[0] or "{}")
    existing.update(data)
    db.execute(
        "UPDATE project_steps SET data=?, updated=?"
        " WHERE project_id=? AND step=?",
        (json.dumps(existing, ensure_ascii=False, default=_json_default),
         _now(), project_id, step),
    )
    db.commit()
    return True


def update_context(db, project_id, context):
    # Merges context (dict) into the project's JSON context.
    # @return: True if the project was found and updated
    row = db.execute(
        "SELECT context FROM projects WHERE id=?", (project_id,),
    ).fetchone()
    if not row:
        return False
    existing = json.loads(row[0] or "{}")
    existing.update(context)
    db.execute(
        "UPDATE projects SET context=?, updated=? WHERE id=?",
        (json.dumps(existing, ensure_ascii=False, default=_json_default),
         _now(), project_id),
    )
    db.commit()
    return True


def set_status(db, project_id, status):
    # @return: True if the project was found and updated
    cur = db.execute(
        "UPDATE projects SET status=?, updated=? WHERE id=?",
        (status, _now(), project_id),
    )
    db.commit()
    return cur.rowcount > 0


def close(db, project_id, outcome=None):
    # Closes an active project: status -> done, stamps closed_at and stores
    # the final outcome (free text, or None to close without one). Idempotent:
    # a project already done/archived is returned unchanged.
    # @args: outcome - free-text result string or None
    # @return: updated project dict, or None if not found
    proj = get(db, project_id)
    if not proj:
        return None
    if proj["status"] != STATUS_ACTIVE:
        return proj  # already closed — idempotent no-op
    now = _now()
    db.execute(
        "UPDATE projects SET status=?, closed_at=?, outcome=?, updated=?"
        " WHERE id=?",
        (STATUS_DONE, now, outcome, now, project_id),
    )
    db.commit()
    return get(db, project_id)


def reopen(db, project_id):
    # Reopens a closed/archived project: status -> active, clears closed_at
    # and outcome (a reopened project has no final result yet). The "un año
    # después" revisita is a real flow, so this works from done AND archived.
    # @return: updated project dict, or None if not found
    proj = get(db, project_id)
    if not proj:
        return None
    if proj["status"] == STATUS_ACTIVE:
        return proj  # already open — idempotent no-op
    now = _now()
    db.execute(
        "UPDATE projects SET status=?, closed_at=NULL, outcome=NULL, updated=?"
        " WHERE id=?",
        (STATUS_ACTIVE, now, project_id),
    )
    db.commit()
    return get(db, project_id)


def set_tags(db, project_id, tags):
    # Stores free-form tags as a single string (comma-separated by convention;
    # the GUI builds/splits them). An empty string clears them.
    # @args: tags - string or iterable of strings
    # @return: True if the project was found and updated
    if not isinstance(tags, str):
        tags = ",".join(t.strip() for t in tags if t.strip())
    cur = db.execute(
        "UPDATE projects SET tags=?, updated=? WHERE id=?",
        (tags, _now(), project_id),
    )
    db.commit()
    return cur.rowcount > 0


def set_favorite(db, project_id, favorite):
    # Toggles the favourite flag (star in the hub).
    # @args: favorite - bool
    # @return: True if the project was found and updated
    cur = db.execute(
        "UPDATE projects SET favorite=?, updated=? WHERE id=?",
        (1 if favorite else 0, _now(), project_id),
    )
    db.commit()
    return cur.rowcount > 0


def add_file(db, project_id, path, kind):
    # Registers a file produced or consumed by a step (sequence, fits, report).
    # @args: path - file path string, kind - sequence|ephemeris|fits|report|post
    # @return: file id
    cur = db.execute(
        "INSERT INTO project_files (project_id, path, kind, created)"
        " VALUES (?, ?, ?, ?)",
        (project_id, str(path), kind, _now()),
    )
    db.commit()
    return cur.lastrowid


def list_files(db, project_id):
    # @return: list of file dicts
    rows = db.execute(
        "SELECT id, project_id, path, kind, created"
        " FROM project_files WHERE project_id=? ORDER BY created",
        (project_id,),
    ).fetchall()
    return [_row_to_file(r) for r in rows]


def delete(db, project_id):
    # Deletes a project; steps and files cascade (PRAGMA foreign_keys = ON).
    # @return: True if the project was found and deleted
    cur = db.execute("DELETE FROM projects WHERE id=?", (project_id,))
    db.commit()
    return cur.rowcount > 0
