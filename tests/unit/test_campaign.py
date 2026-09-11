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

import pytest

from nightscribe.core import campaign, followup, project
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
