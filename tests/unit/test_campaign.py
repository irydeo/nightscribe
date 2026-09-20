############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: campaigns CRUD (Track V, V0.2)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import time

import pytest

from nightscribe.core import campaign, followup, project, variables
from nightscribe.core.db import Database


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "t.db"))


def test_create_get_roundtrip(db):
    cid = campaign.create(db, "Campaña T CrB", group_name="obsSN",
                          goal="Catch the eruption",
                          protocol={"cadence_nights": 1,
                                    "filters": ["B", "V"],
                                    "comp_stars": ["000-BB0-123"]},
                          report_url="https://forms.example/tcrb")
    c = campaign.get(db, cid)
    assert c["name"] == "Campaña T CrB"
    assert c["group_name"] == "obsSN"
    assert c["protocol"]["cadence_nights"] == 1
    assert c["protocol"]["filters"] == ["B", "V"]
    assert c["status"] == "active" and c["closed_at"] is None


def test_list_filters_by_status(db):
    campaign.create(db, "A")
    cid = campaign.create(db, "B")
    campaign.finish(db, cid)
    names = [c["name"] for c in campaign.list_campaigns(db)]
    assert set(names) == {"A", "B"}
    assert [c["name"] for c in campaign.list_campaigns(db, "active")] == ["A"]
    assert [c["name"] for c in campaign.list_campaigns(db, "finished")] == ["B"]


def test_update_only_editable_fields(db):
    cid = campaign.create(db, "A")
    assert campaign.update(db, cid, goal="new goal", status="finished") is True
    c = campaign.get(db, cid)
    assert c["goal"] == "new goal"
    assert c["status"] == "active"          # status never via update()
    assert campaign.update(db, cid) is False   # nothing to update


def test_finish_and_reopen_are_idempotent(db):
    cid = campaign.create(db, "A")
    c1 = campaign.finish(db, cid)
    assert c1["status"] == "finished" and c1["closed_at"]
    assert campaign.finish(db, cid)["closed_at"] == c1["closed_at"]
    c2 = campaign.reopen(db, cid)
    assert c2["status"] == "active" and c2["closed_at"] is None
    assert campaign.reopen(db, cid)["status"] == "active"


def test_delete_keeps_projects(db):
    cid = campaign.create(db, "A")
    db.execute(
        "INSERT INTO projects (kind, object_name, status, created, updated,"
        " context, campaign_id) VALUES ('variable', 'T CrB', 'active', 1.0,"
        " 1.0, '{}', ?)", (cid,))
    db.commit()
    assert campaign.delete(db, cid) is True
    assert campaign.get(db, cid) is None
    assert db.execute("SELECT campaign_id FROM projects").fetchone()[0] is None


def _var_project(db, name, campaign_id=None):
    return project.create(db, "variable", name,
                          {"ra_deg": 10.0, "dec_deg": 20.0, "mag": 12.0},
                          campaign_id=campaign_id)


def test_due_campaigns_never_visited_is_due(db):
    cid = campaign.create(db, "C", protocol={"cadence_nights": 3})
    p = _var_project(db, "T CrB", campaign_id=cid)
    due = campaign.due_campaigns(db)
    assert len(due) == 1
    assert due[0]["never_visited"] is True
    assert due[0]["overdue_days"] == 3          # the cadence itself
    assert due[0]["project"]["object_name"] == "T CrB"


def test_due_campaigns_respects_cadence(db):
    cid = campaign.create(db, "C", protocol={"cadence_nights": 3})
    p = _var_project(db, "T CrB", campaign_id=cid)
    followup.create_session(db, p["id"])        # visited today: not due
    assert campaign.due_campaigns(db) == []
    # fake an old visit: 5 days ago
    sid = followup.list_sessions(db, p["id"])[0]["id"]
    import time as _t
    db.execute("UPDATE project_sessions SET created=? WHERE id=?",
               (_t.time() - 5 * 86400, sid))
    db.commit()
    due = campaign.due_campaigns(db)
    assert len(due) == 1 and due[0]["overdue_days"] == 5


def test_due_campaigns_skips_finished_and_done_projects(db):
    cid = campaign.create(db, "C", protocol={"cadence_nights": 1})
    p = _var_project(db, "T CrB", campaign_id=cid)
    project.close(db, p["id"], outcome="completed")
    campaign.finish(db, cid)
    assert campaign.due_campaigns(db) == []
    campaign.reopen(db, cid)
    assert campaign.due_campaigns(db) == []     # the project is still done


def test_status_report_health_per_member(db):
    from nightscribe.core import followup, project
    cid = campaign.create(db, "Campaña WeSb 1",
                          protocol={"cadence_nights": 2})
    p_new = project.create(db, "variable", "WeSb 1",
                           {"ra_deg": 15.2, "dec_deg": 55.0},
                           campaign_id=cid)
    p_ok = project.create(db, "sn", "SN 2099aa", {}, campaign_id=cid)
    followup.create_session(db, p_ok["id"])        # visited today
    rep = campaign.status_report(db, cid)
    assert rep["campaign"]["name"] == "Campaña WeSb 1"
    by_name = {m["object_name"]: m for m in rep["members"]}
    assert by_name["WeSb 1"]["due"] is True        # never visited
    assert by_name["WeSb 1"]["days_since"] is None
    assert by_name["SN 2099aa"]["due"] is False    # visited today
    assert by_name["SN 2099aa"]["days_since"] == 0
    assert by_name["SN 2099aa"]["event"] is None


def test_status_report_flags_events(db):
    from nightscribe.core import followup, project
    cid = campaign.create(db, "C")
    p = project.create(db, "variable", "R CrB", {}, campaign_id=cid)
    # >= 4 own points, latest one a >0.5 mag jump (inverted axis: mag up
    # = brightness drop)
    for i, mag in enumerate((11.0, 11.1, 11.0, 11.05, 12.0)):
        followup.add_point(db, p["id"], 60100.0 + i, "V", mag,
                           source="manual")
    rep = campaign.status_report(db, cid)
    assert rep["members"][0]["event"]["direction"] == "drop"


def test_status_report_unknown_campaign(db):
    assert campaign.status_report(db, 9999) is None


# ---------------- ADR-037 SC1: the three signals ----------------

EVENT_MAGS = (12.0, 12.1, 11.9, 12.0, 12.9)   # last point: 0.9 mag drop


def _mk(db, name, cadence=3, visited_days_ago=None, ctx=None, mags=None):
    # @return: (campaign_id, project_id) of a variable project; default is
    #          never visited (cadence-due), pass visited_days_ago=0 for an
    #          up-to-date member, mags=EVENT_MAGS for a drop event
    cid = campaign.create(db, name, protocol={"cadence_nights": cadence})
    full = {"ra_deg": 10.0, "dec_deg": 80.0, "mag": 10.0}
    full.update(ctx or {})
    p = project.create(db, "variable", name, full, campaign_id=cid)
    if visited_days_ago is not None:
        followup.create_session(db, p["id"])
        sid = followup.list_sessions(db, p["id"])[0]["id"]
        db.execute("UPDATE project_sessions SET created=? WHERE id=?",
                   (time.time() - visited_days_ago * 86400, sid))
        db.commit()
    if mags:
        for i, m in enumerate(mags):
            followup.add_point(db, p["id"], 61000.0 + i, "V", m)
    return cid, p["id"]


def test_project_signal_due_only(db):
    cid, _ = _mk(db, "T CrB", cadence=3)          # never visited -> due
    camp = campaign.get(db, cid)
    sig = campaign.project_signal(db, camp, campaign.projects_of(db, cid)[0])
    assert sig["due"] is True and sig["never_visited"] is True
    assert sig["event"] is None
    assert sig["imminent_extremum"] is False
    assert sig["reasons"] == ["due"]


def test_project_signal_event_survives_fresh_visit(db):
    # ADR-037: the bug due_campaigns had — an up-to-date member that RAISES
    # an event must still be listable, with reasons == ["event"]
    _cid, _ = _mk(db, "R CrB", cadence=3, visited_days_ago=0, mags=EVENT_MAGS)
    camp = campaign.get(db, campaign.list_campaigns(db)[0]["id"])
    sig = campaign.project_signal(db, camp,
                                  campaign.projects_of(
                                      db, camp["id"])[0])
    assert sig["due"] is False
    assert sig["event"]["direction"] == "drop"
    assert sig["reasons"] == ["event"]


def test_project_signal_extremum_window(db):
    # maximum ~2 days out: imminent inside a 3-day window, not inside 1
    epoch = variables._now_mjd() + 2 - 300.0 * 100
    cid, _ = _mk(db, "WeSb 1", cadence=3, visited_days_ago=0,
                 ctx={"variable": {"var_type": "M", "period_d": 300.0,
                                   "epoch_mjd": epoch}})
    camp = campaign.get(db, cid)
    p = campaign.projects_of(db, cid)[0]
    sig3 = campaign.project_signal(db, camp, p, extremum_days=3)
    assert sig3["imminent_extremum"] is True
    assert sig3["extremum"]["kind"] == "max"
    assert sig3["reasons"] == ["extremum"]
    sig1 = campaign.project_signal(db, camp, p, extremum_days=1)
    assert sig1["imminent_extremum"] is False
    assert sig1["reasons"] == []


def test_project_signal_no_signals(db):
    cid, _ = _mk(db, "Calm 1", cadence=3, visited_days_ago=0)
    camp = campaign.get(db, cid)
    sig = campaign.project_signal(db, camp, campaign.projects_of(db, cid)[0])
    assert sig["due"] is False and sig["event"] is None
    assert sig["imminent_extremum"] is False
    assert sig["reasons"] == []


def test_tonight_listable_mixes_the_three_signals(db):
    epoch = variables._now_mjd() + 1 - 300.0 * 100     # max ~1 day out
    _mk(db, "Due 1")                                    # cadence signal
    _mk(db, "Event 1", visited_days_ago=0, mags=EVENT_MAGS)
    _mk(db, "Max 1", visited_days_ago=0,
        ctx={"variable": {"var_type": "M", "period_d": 300.0,
                          "epoch_mjd": epoch}})
    _mk(db, "Calm 1", visited_days_ago=0)               # no signal at all
    rows = campaign.tonight_listable(db)
    names = sorted(r["project"]["object_name"] for r in rows)
    assert names == ["Due 1", "Event 1", "Max 1"]


def test_tonight_listable_respects_lifecycle(db):
    cid, pid = _mk(db, "Gone")                          # due (never visited)
    assert len(campaign.tonight_listable(db)) == 1
    project.close(db, pid, outcome="completed")
    assert campaign.tonight_listable(db) == []          # project finished
    campaign.finish(db, cid)
    assert campaign.tonight_listable(db) == []          # campaign finished too


# ---------------- ADR-037 SC2: the signals console ----------------

def test_signals_report_empty(db):
    rep = campaign.signals_report(db)
    assert rep == {"members": 0, "up_to_date": 0, "signals": []}


def test_signals_report_counts_coverage(db):
    # 2 up-to-date members + 1 overdue, none with event/extremum ->
    # coverage 2/3 and an EMPTY signals list
    _mk(db, "Fresh 1", cadence=7, visited_days_ago=0)
    _mk(db, "Fresh 2", cadence=7, visited_days_ago=2)
    _mk(db, "Overdue 1", cadence=3, visited_days_ago=5)
    rep = campaign.signals_report(db)
    assert rep["members"] == 3
    assert rep["up_to_date"] == 2
    assert rep["signals"] == []


def test_signals_report_events_rank_before_extrema(db):
    # "Z" sorts AFTER "M" alphabetically — event order must win
    _mk(db, "Z Event", visited_days_ago=0, mags=EVENT_MAGS)
    now = variables._now_mjd()
    _mk(db, "M Max", visited_days_ago=0, ctx={"variable": {
        "var_type": "M", "period_d": 300.0, "epoch_mjd": now + 1}})
    rep = campaign.signals_report(db)
    assert [r["project"]["object_name"] for r in rep["signals"]] == \
        ["Z Event", "M Max"]
    assert rep["signals"][0]["event"]["direction"] == "drop"
    assert rep["signals"][1]["event"] is None
    assert rep["signals"][1]["extremum"]["kind"] == "max"


def test_signals_report_keeps_far_extrema(db):
    # A countdown, not an imminence flag: 145 days out still surfaces
    now = variables._now_mjd()
    _mk(db, "Far", visited_days_ago=0, ctx={"variable": {
        "var_type": "M", "period_d": 300.0, "epoch_mjd": now + 145}})
    rep = campaign.signals_report(db)
    assert len(rep["signals"]) == 1
    assert rep["signals"][0]["extremum"]["days"] > 3


def test_signals_report_extrema_ordered_by_days(db):
    now = variables._now_mjd()
    _mk(db, "Far", visited_days_ago=0, ctx={"variable": {
        "var_type": "M", "period_d": 300.0, "epoch_mjd": now + 40}})
    _mk(db, "Near", visited_days_ago=0, ctx={"variable": {
        "var_type": "M", "period_d": 300.0, "epoch_mjd": now + 10}})
    rep = campaign.signals_report(db)
    names = [r["project"]["object_name"] for r in rep["signals"]]
    assert names == ["Near", "Far"]


def test_signals_report_excludes_finished_campaign(db):
    cid, _ = _mk(db, "Done")                             # due member
    assert campaign.signals_report(db)["members"] == 1
    campaign.finish(db, cid)
    assert campaign.signals_report(db) == \
        {"members": 0, "up_to_date": 0, "signals": []}


def test_signals_report_excludes_archived_project(db):
    cid, pid = _mk(db, "Archived")                       # due member
    assert campaign.signals_report(db)["members"] == 1
    project.set_status(db, pid, "archived")
    rep = campaign.signals_report(db)
    assert rep["members"] == 0 and rep["signals"] == []
