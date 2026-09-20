############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Attention report module (Track UX-PC, U2)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Which of YOUR projects needs you right now, and why (Track UX-PC, U2).

The feed for the Projects hub dashboard («Necesita tu atención»): one entry
per active project, urgency-sorted, carrying a machine reason the GUI turns
into plain words (the app speaks first, in the user's language — i18n lives
in the GUI layer, this module stays language-free).

Pure local maths over the database — never network. The campaign-signal
pieces reuse the same building blocks as `campaign.project_signal`
(ADR-037 SC1), so the dashboard, Tonight and the campaigns console can
never disagree.
"""

from . import campaign as _campaign
from . import followup as _followup
from . import project as _project
from . import variables as _variables

# The urgency ladder: a detector event outranks an overdue cadence, which
# outranks the plain step flow.
URGENCY_RANK = {"event": 0, "due": 1, "info": 2}


def attention_report(db, cfg=None):
    # @args: db - Database, cfg - Config or None (thresholds fall back to
    #        the documented defaults: campaign_extremum_days=3,
    #        event_mag_threshold=0.5)
    # @return: list of entries, most urgent first. One entry per ACTIVE
    #   project (the merge rule SC-g is built in: a signal about a star
    #   that already is a project lands on that project's row, never on a
    #   duplicate):
    #     {"project_id", "object_name", "kind", "favorite", "campaign",
    #      "urgency": "event"|"due"|"info",
    #      "reason": "event"|"due"|"never_visited"|"extremum"|
    #                "plan"|"process"|"publish"|"close",
    #      "section": project-page section the action lands on (or None),
    #      "overdue_days": int|None, "event": dict|None,
    #      "extremum": dict|None, "updated": epoch}
    extremum_days, event_threshold = 3, 0.5
    if cfg is not None:
        extremum_days = int(cfg.get("campaign_extremum_days", 3))
        event_threshold = float(cfg.get("event_mag_threshold", 0.5))
    camp_names = {c["id"]: c["name"] for c in _campaign.list_campaigns(db)}
    out = []
    for p in _project.list_projects(db, status=_project.STATUS_ACTIVE):
        full = _project.get(db, p["id"])
        if not full:
            continue
        act = _project.next_action(db, full)
        entry = {
            "project_id": p["id"],
            "object_name": p["object_name"],
            "kind": p["kind"],
            "favorite": bool(p.get("favorite")),
            "campaign": camp_names.get(p.get("campaign_id")),
            "urgency": "info",
            "reason": act["key"] or "close",
            "section": act["key"] if act["key"] != "close" else None,
            "overdue_days": act.get("overdue_days"),
            "event": None,
            "extremum": None,
            "updated": p.get("updated") or 0,
        }
        # an overdue cadence (or the first-visit prompt) calls for action
        # tonight; next_action() is the single source for that verdict
        if act["key"] == "followup":
            entry.update(
                urgency="due",
                reason="never_visited" if act.get("never_visited") else "due",
                section="followup")
        # an imminent extremum (campaign-style variables) also calls —
        # attached as extra context when the cadence already spoke
        if p["kind"] == "variable":
            v = (p.get("context") or {}).get("variable") or {}
            nxt = _variables.next_extremum(
                v.get("period_d"), v.get("epoch_mjd"),
                var_type=v.get("var_type", ""))
            if nxt and (nxt.get("days") or 0) <= extremum_days:
                entry["extremum"] = nxt
                if entry["urgency"] == "info":
                    entry.update(urgency="due", reason="extremum",
                                 section="followup")
        # a detector event outranks everything (the WeSb protocol: a drop
        # seen today must not wait for the cadence, ADR-035)
        if p["kind"] in ("sn", "variable"):
            ev = _variables.detect_event(
                _followup.list_points(db, p["id"]),
                threshold=event_threshold)
            if ev:
                entry.update(urgency="event", reason="event", event=ev,
                             section="followup")
        out.append(entry)
    out.sort(key=lambda e: (
        URGENCY_RANK.get(e["urgency"], 2),
        -(e["overdue_days"] or 0),
        e["updated"],
        e["object_name"]))
    return out
