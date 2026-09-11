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
