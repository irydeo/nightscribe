############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Observation campaigns model (ADR-035)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Observation campaigns: a first-class entity projects hang from (1:N).

A campaign is the group's shared commitment — a science goal, a protocol
(cadence in nights, filters, comparison stars, notes) and the report/data
URLs — and any project kind can join it (V-b). Storage: the `campaigns`
table (migration v7). All SQL goes through db.execute (ADR-002); the module
mirrors the pragmatic style of core/followup.py.
"""

import json
import logging
import time

logger = logging.getLogger(__name__)

CAMPAIGN_ACTIVE = "active"
CAMPAIGN_FINISHED = "finished"

# Editable fields (campaign.update whitelist)
_EDITABLE = ("name", "group_name", "coordinator", "goal", "protocol",
             "report_url", "data_url")


def _now():
    # @return: current epoch seconds
    return time.time()


def _row_to_campaign(row):
    # @return: campaign dict from a SELECT row (protocol JSON decoded)
    return {"id": row[0], "name": row[1], "group_name": row[2] or "",
            "coordinator": row[3] or "", "goal": row[4] or "",
            "protocol": json.loads(row[5] or "{}"),
            "report_url": row[6] or "", "data_url": row[7] or "",
            "status": row[8], "created": row[9], "closed_at": row[10]}


def create(db, name, group_name="", coordinator="", goal="", protocol=None,
           report_url="", data_url=""):
    # @args: db - Database, name - campaign name, protocol - dict with
    #        cadence_nights / filters / comp_stars / notes (all optional)
    # @return: campaign id
    cur = db.execute(
        "INSERT INTO campaigns (name, group_name, coordinator, goal,"
        " protocol, report_url, data_url, status, created)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (name, group_name, coordinator, goal,
         json.dumps(protocol or {}, ensure_ascii=False),
         report_url, data_url, CAMPAIGN_ACTIVE, _now()),
    )
    db.commit()
    return cur.lastrowid


def get(db, campaign_id):
    # @return: campaign dict or None
    row = db.execute(
        "SELECT id, name, group_name, coordinator, goal, protocol,"
        " report_url, data_url, status, created, closed_at"
        " FROM campaigns WHERE id=?",
        (campaign_id,),
    ).fetchone()
    return _row_to_campaign(row) if row else None


def list_campaigns(db, status=None):
    # @args: status - CAMPAIGN_ACTIVE | CAMPAIGN_FINISHED | None (all)
    # @return: list of campaign dicts, newest first
    sql = ("SELECT id, name, group_name, coordinator, goal, protocol,"
           " report_url, data_url, status, created, closed_at FROM campaigns")
    params = []
    if status:
        sql += " WHERE status=?"
        params.append(status)
    sql += " ORDER BY created DESC"
    return [_row_to_campaign(r) for r in db.execute(sql, params).fetchall()]


def update(db, campaign_id, **fields):
    # Edits the editable fields only (status changes go through
    # finish/reopen). Protocol accepts a dict (JSON-encoded here).
    # @return: True if the campaign was found and updated
    sets, params = [], []
    for key in _EDITABLE:
        if key in fields:
            val = fields[key]
            if key == "protocol":
                val = json.dumps(val or {}, ensure_ascii=False)
            sets.append(f"{key}=?")
            params.append(val)
    if not sets:
        return False
    params.append(campaign_id)
    cur = db.execute(f"UPDATE campaigns SET {', '.join(sets)} WHERE id=?",
                     params)
    db.commit()
    return cur.rowcount > 0


def finish(db, campaign_id):
    # Marks the campaign finished (stamps closed_at). Idempotent.
    # @return: updated campaign dict, or None if not found
    camp = get(db, campaign_id)
    if not camp:
        return None
    if camp["status"] == CAMPAIGN_FINISHED:
        return camp
    db.execute("UPDATE campaigns SET status=?, closed_at=? WHERE id=?",
               (CAMPAIGN_FINISHED, _now(), campaign_id))
    db.commit()
    return get(db, campaign_id)


def reopen(db, campaign_id):
    # Reopens a finished campaign (clears closed_at). Idempotent.
    # @return: updated campaign dict, or None if not found
    camp = get(db, campaign_id)
    if not camp:
        return None
    if camp["status"] == CAMPAIGN_ACTIVE:
        return camp
    db.execute("UPDATE campaigns SET status=?, closed_at=NULL WHERE id=?",
               (CAMPAIGN_ACTIVE, campaign_id))
    db.commit()
    return get(db, campaign_id)


def delete(db, campaign_id):
    # Deletes the campaign; projects keep going (campaign_id -> NULL).
    # @return: True if the campaign was found and deleted
    cur = db.execute("DELETE FROM campaigns WHERE id=?", (campaign_id,))
    db.commit()
    return cur.rowcount > 0


# ---------------- protocol and the Tonight loop ----------------


def protocol_get(camp, key, default=None):
    # @args: camp - campaign dict, key - cadence_nights | filters |
    #        comp_stars | notes, default - when absent
    # @return: the protocol value
    return (camp.get("protocol") or {}).get(key, default)


def projects_of(db, campaign_id, status="active"):
    # The projects hanging from a campaign (any kind — V-b).
    # @return: [{id, object_name, kind, context}]
    sql = ("SELECT id, object_name, kind, context FROM projects"
           " WHERE campaign_id=?")
    params = [campaign_id]
    if status:
        sql += " AND status=?"
        params.append(status)
    rows = db.execute(sql, params).fetchall()
    return [{"id": r[0], "object_name": r[1], "kind": r[2],
             "context": json.loads(r[3] or "{}")} for r in rows]


def due_campaigns(db):
    # The Tonight loop (V-d): every DUE project of every active campaign —
    # a project is due when its last visit is >= the campaign cadence in
    # nights, or when it was never visited at all.
    # @return: [{"campaign", "project", "overdue_days", "cadence_nights",
    #          "never_visited"}] — one row per due project
    from . import followup
    out = []
    for camp in list_campaigns(db, status=CAMPAIGN_ACTIVE):
        cad = int(protocol_get(camp, "cadence_nights", 1) or 1)
        for proj in projects_of(db, camp["id"], status="active"):
            days = followup.days_since_last_session(db, proj["id"])
            never = days is None
            if never:
                overdue = cad      # as due as it gets: no visit at all
            elif days >= cad:
                overdue = days
            else:
                continue
            out.append({"campaign": camp, "project": proj,
                        "overdue_days": overdue, "cadence_nights": cad,
                        "never_visited": never})
    return out


def status_report(db, campaign_id):
    # The Campaigns tab data (UX-b): EVERY member project with its cadence
    # health and event flag, so the tab shows the whole campaign at a
    # glance — due_campaigns' narrower job is the Tonight loop (due only).
    # @args: db - Database, campaign_id - int
    # @return: {"campaign": camp, "members": [{"id", "object_name", "kind",
    #          "status", "days_since", "due", "overdue_days", "event"}]},
    #          or None when the campaign does not exist
    from . import followup, variables
    camp = get(db, campaign_id)
    if not camp:
        return None
    cad = int(protocol_get(camp, "cadence_nights", 1) or 1)
    rows = db.execute(
        "SELECT id, object_name, kind, status FROM projects"
        " WHERE campaign_id=? ORDER BY object_name COLLATE NOCASE",
        (campaign_id,)).fetchall()
    members = []
    for pid, name, kind, pstatus in rows:
        days = followup.days_since_last_session(db, pid)
        due = pstatus == "active" and (days is None or days >= cad)
        ev = None
        if kind in ("variable", "sn"):
            ev = variables.detect_event(followup.list_points(db, pid))
        members.append({"id": pid, "object_name": name, "kind": kind,
                        "status": pstatus, "days_since": days, "due": due,
                        "overdue_days": days if days is not None else cad,
                        "event": ev})
    return {"campaign": camp, "members": members}
