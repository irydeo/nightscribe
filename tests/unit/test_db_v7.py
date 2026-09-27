############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: v7 migration (campaigns)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import pytest

from nightscribe.core.db import Database


def test_fresh_db_has_campaigns_and_v7(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    assert db.execute("PRAGMA user_version").fetchone()[0] == 11
    cols = {r[1] for r in db.execute("PRAGMA table_info(campaigns)")}
    assert {"id", "name", "group_name", "coordinator", "goal", "protocol",
            "report_url", "data_url", "status", "created",
            "closed_at"} == cols
    pcols = {r[1] for r in db.execute("PRAGMA table_info(projects)")}
    assert "campaign_id" in pcols


def test_reopen_v7_is_idempotent(tmp_path):
    f = tmp_path / "t.db"
    Database(str(f)).close()
    db = Database(str(f))           # re-open: the guarded block is a no-op
    assert db.execute("PRAGMA user_version").fetchone()[0] == 11


def test_upgrade_from_v6_restores_campaigns(tmp_path):
    f = tmp_path / "t.db"
    db = Database(str(f))
    db.execute("DROP TABLE campaigns")
    db.execute("PRAGMA user_version = 6")
    db.commit()
    db.close()
    db = Database(str(f))           # migrates 6 -> 7 again
    assert db.execute("PRAGMA user_version").fetchone()[0] == 11
    db.execute("INSERT INTO campaigns (name, created) VALUES ('X', 1.0)")
    assert db.execute("SELECT name FROM campaigns").fetchone()[0] == "X"


def test_campaign_delete_sets_project_campaign_null(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    db.execute("INSERT INTO campaigns (name, created) VALUES ('C1', 1.0)")
    db.execute(
        "INSERT INTO projects (kind, object_name, status, created, updated,"
        " context, campaign_id) VALUES ('variable', 'T CrB', 'active', 1.0,"
        " 1.0, '{}', 1)")
    db.commit()
    db.execute("DELETE FROM campaigns WHERE id=1")
    db.commit()
    row = db.execute("SELECT campaign_id FROM projects").fetchone()
    assert row[0] is None
