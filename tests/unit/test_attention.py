############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: attention report (Track UX-PC, U2)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""`core/attention.attention_report` — the dashboard feed: which active
projects need you, in what order, and where the action lands. Pure local
maths over a temp database, no network, no GUI."""

import time

import pytest

from nightscribe.core import attention, campaign, followup, project
from nightscribe.core.db import Database


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "t.db"))


def _mk_points(db, pid, mags, filt="V", start_mjd=60900.0):
    # @args: mags - chronological magnitudes (the last one is "today")
    for i, m in enumerate(mags):
        followup.add_point(db, pid, start_mjd + i, filt, m)


def test_empty_db_reports_nothing(db):
    assert attention.attention_report(db) == []


def test_fresh_project_is_a_plain_step_info(db):
    p = project.create(db, "neo", "2026 QK", {"kind": "neo", "mag": 19.0})
    rep = attention.attention_report(db)
    assert len(rep) == 1
    e = rep[0]
    assert e["project_id"] == p["id"]
    assert e["urgency"] == "info"
    assert e["reason"] == "plan"          # a fresh project starts at plan
    assert e["section"] == "plan"
    assert e["event"] is None and e["extremum"] is None


def test_sn_cadence_due_is_due_urgency(db):
    p = project.create(db, "sn", "SN 2099zz", {"kind": "sn", "mag": 15.0})
    project.advance(db, p["id"])          # plan done -> observing started
    sid = followup.create_session(db, p["id"])
    # the cadence reads the session's created stamp — push it 5 days back
    db.execute("UPDATE project_sessions SET created=? WHERE id=?",
               (time.time() - 5 * 86400, sid))
    db.commit()
    rep = attention.attention_report(db)
    e = rep[0]
    assert e["urgency"] == "due"
    assert e["reason"] == "due"
    assert e["section"] == "analysis"
    assert e["overdue_days"] >= 5


def test_never_visited_variable_gets_the_first_visit_prompt(db):
    p = project.create(db, "variable", "T CrB",
                       {"kind": "variable", "variable": {}})
    project.advance(db, p["id"])   # the first-visit prompt needs a plan
    rep = attention.attention_report(db)
    e = rep[0]
    assert e["urgency"] == "due"
    assert e["reason"] == "never_visited"
    assert e["section"] == "analysis"


def test_detector_event_outranks_everything(db):
    # one calm project (step flow) + one SN with a brightness jump: the
    # event must lead the report even though the other project is older
    p_calm = project.create(db, "neo", "calm-NEO", {"kind": "neo"})
    p_sn = project.create(db, "sn", "SN-event", {"kind": "sn"})
    project.advance(db, p_sn["id"])
    _mk_points(db, p_sn["id"], [15.0, 15.05, 14.95, 15.0, 13.9])
    rep = attention.attention_report(db)
    assert rep[0]["project_id"] == p_sn["id"]
    assert rep[0]["urgency"] == "event"
    assert rep[0]["reason"] == "event"
    assert rep[0]["event"]["direction"] == "rise"   # got brighter
    assert rep[0]["section"] == "analysis"
    assert rep[1]["project_id"] == p_calm["id"]
    assert rep[1]["urgency"] == "info"


def test_imminent_extremum_makes_a_variable_due(db):
    # period/epoch chosen so the next maximum is tomorrow
    import math
    mjd_now = time.time() / 86400.0 + 40587.0
    epoch = math.ceil(mjd_now) + 0.5
    ctx = {"kind": "variable",
           "variable": {"period_d": 2.0, "epoch_mjd": epoch,
                        "var_type": "DSCT"}}
    # a variable that has already been visited (so the cadence does not
    # speak first) with the plan done
    p = project.create(db, "variable", "VSTAR", ctx)
    project.advance(db, p["id"])
    followup.create_session(db, p["id"])
    rep = attention.attention_report(db)
    e = rep[0]
    assert e["urgency"] == "due"
    assert e["reason"] == "extremum"
    assert e["extremum"]["days"] <= 3       # inside the imminence window
    assert e["section"] == "analysis"


def test_campaign_name_and_favorite_ride_along(db):
    cid = campaign.create(db, "T CrB 2026")
    p = project.create(db, "variable", "T CrB",
                       {"kind": "variable"}, campaign_id=cid)
    project.set_favorite(db, p["id"], True)
    rep = attention.attention_report(db)
    e = rep[0]
    assert e["campaign"] == "T CrB 2026"
    assert e["favorite"] is True


def test_closed_projects_never_call_for_attention(db):
    p = project.create(db, "sn", "SN-done", {"kind": "sn"})
    project.close(db, p["id"], "completed")
    assert attention.attention_report(db) == []


def test_thresholds_come_from_cfg(db):
    # a 0.3 mag jump fires with a 0.2 threshold but not with the 0.5 default
    class _Cfg(dict):
        def get(self, k, d=None):
            return super().get(k, d)
    p = project.create(db, "sn", "SN-thr", {"kind": "sn"})
    project.advance(db, p["id"])
    _mk_points(db, p["id"], [15.0, 15.0, 15.0, 15.0, 14.7])
    assert attention.attention_report(db)[0]["urgency"] == "info"
    rep = attention.attention_report(db, _Cfg(event_mag_threshold=0.2))
    assert rep[0]["urgency"] == "event"
