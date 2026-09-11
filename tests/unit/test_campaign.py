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

from nightscribe.core import campaign
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
