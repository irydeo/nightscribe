############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: variable-star kind + campaign link (Track V, V0.4)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import pytest

from nightscribe.core import campaign, project
from nightscribe.core.db import Database


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "t.db"))


def test_create_variable_kind_with_campaign(db):
    cid = campaign.create(db, "Campaña T CrB")
    p = project.create(db, "variable", "T CrB", campaign_id=cid)
    assert p is not None
    assert p["kind"] == "variable"
    assert p["campaign_id"] == cid
    assert [s["step"] for s in p["steps"]] == list(project.STEPS)


def test_list_filters_by_campaign(db):
    cid1 = campaign.create(db, "A")
    cid2 = campaign.create(db, "B")
    p1 = project.create(db, "variable", "T CrB", campaign_id=cid1)
    p2 = project.create(db, "variable", "R SMC", campaign_id=cid2)
    others = project.create(db, "sn", "SN2026x")
    assert [p["id"] for p in project.list_projects(db, campaign_id=cid1)] == [p1["id"]]
    assert {p["id"] for p in project.list_projects(db, kind="variable")} == {p1["id"], p2["id"]}
    assert {p["id"] for p in project.list_projects(db)} == {p1["id"], p2["id"], others["id"]}


def test_variable_outcomes_include_caught_not_caught(db):
    p = project.create(db, "variable", "T CrB")
    closed = project.close(db, p["id"], outcome="caught")
    assert closed["outcome"] == "caught" and closed["status"] == "done"
    # "not_caught" is in the variable-star outcome list
    assert "not_caught" in project.OUTCOMES["variable"]
    assert "caught" in project.OUTCOMES["variable"]


def test_set_campaign_link_and_unlink(db):
    cid = campaign.create(db, "C")
    p = project.create(db, "sn", "SN 2026abc")
    assert project.set_campaign(db, p["id"], cid) is True
    assert project.get(db, p["id"])["campaign_id"] == cid
    assert project.set_campaign(db, p["id"], None) is True
    assert project.get(db, p["id"])["campaign_id"] is None
