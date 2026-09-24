############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: project.next_action (UX, UD.1)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import pytest

from nightscribe.core import campaign, followup, project
from nightscribe.core.db import Database


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "t.db"))


def _proj(db, kind="sn", campaign_id=None):
    return project.create(db, kind, "OBJ", {"mag": 15.0},
                          campaign_id=campaign_id)


def test_fresh_project_says_plan(db):
    assert project.next_action(db, _proj(db))["key"] == "plan"


def test_plan_done_says_analysis(db):
    p = _proj(db)
    project.advance(db, p["id"])
    assert project.next_action(db, project.get(db, p["id"]))["key"] == \
        "analysis"


def test_analysis_done_says_publish(db):
    p = _proj(db)
    project.advance(db, p["id"])
    project.advance(db, p["id"])
    assert project.next_action(db, project.get(db, p["id"]))["key"] == \
        "publish"


def test_all_done_says_close(db):
    p = _proj(db)
    for _ in range(3):
        project.advance(db, p["id"])
    assert project.next_action(db, project.get(db, p["id"]))["key"] == \
        "close"


def test_skipped_step_counts_as_passed(db):
    p = _proj(db)
    project.set_step_status(db, p["id"], "plan", project.STEP_SKIPPED)
    assert project.next_action(db, project.get(db, p["id"]))["key"] == \
        "analysis"


def test_cadence_due_beats_analysis(db):
    p = _proj(db)
    project.advance(db, p["id"])                 # plan done
    followup.create_session(db, p["id"])
    db.execute("UPDATE project_sessions SET created=? WHERE project_id=?",
               (1_700_000_000, p["id"]))         # aged far beyond 3 d
    db.commit()
    act = project.next_action(db, project.get(db, p["id"]))
    assert act["key"] == "analysis" and act["overdue_days"] >= 3


def test_no_session_and_no_plan_says_plan_not_analysis(db):
    # "measure tonight" is not actionable without a plan (rule 1 guard)
    assert project.next_action(db, _proj(db, kind="variable"))["key"] == \
        "plan"


def test_never_visited_with_plan_says_analysis(db):
    p = _proj(db, kind="variable")
    project.advance(db, p["id"])                 # plan done, no visits
    act = project.next_action(db, project.get(db, p["id"]))
    assert act["key"] == "analysis" and act["never_visited"] is True


def test_campaign_cadence_overrides_default(db):
    cid = campaign.create(db, "Campaña lenta",
                          protocol={"cadence_nights": 10})
    p = _proj(db, campaign_id=cid)
    project.advance(db, p["id"])
    followup.create_session(db, p["id"])
    db.execute("UPDATE project_sessions SET created=? WHERE project_id=?",
               (1_700_000_000, p["id"]))
    db.commit()
    act = project.next_action(db, project.get(db, p["id"]))
    assert act["key"] == "analysis" and act["overdue_days"] >= 10


def test_reopen_step_keeps_single_current(db):
    p = _proj(db)
    project.advance(db, p["id"])                 # plan done, process current
    assert project.reopen_step(db, p["id"], "plan") is True
    steps = {s["step"]: s["status"]
             for s in project.get(db, p["id"])["steps"]}
    assert steps["plan"] == "current"
    assert steps["analysis"] == "pending"
