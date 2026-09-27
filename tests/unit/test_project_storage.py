############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: project container folder (ADR-032)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import sqlite3

from nightscribe import paths
from nightscribe.core import db as dbm
from nightscribe.core import project


class _Cfg:
    # Minimal config stub: only the projects_root key the model reads
    def __init__(self, root=""):
        self.root = root

    def get(self, key, default=None):
        return self.root if key == "projects_root" else default


def _stub_config(monkeypatch, root=""):
    monkeypatch.setattr(project, "config", _Cfg(root))


def test_fresh_db_migrates_to_v6(tmp_path):
    db = dbm.Database(tmp_path / "fresh.db")
    assert db.execute("PRAGMA user_version").fetchone()[0] == 11


def test_migration_v6_backfills_legacy_root(tmp_path):
    # Simulate a v5 database with projects that predate the column.
    f = tmp_path / "old.db"
    conn = sqlite3.connect(str(f))
    conn.executescript(dbm._SCHEMA)
    conn.executescript(dbm._V1)
    conn.execute("PRAGMA user_version = 5")
    conn.execute(
        "INSERT INTO projects (kind, object_name, status, created, updated,"
        " context) VALUES (?, ?, ?, ?, ?, ?)",
        ("sn", "AT2020old", "active", 1.0, 1.0, "{}"))
    conn.commit()
    conn.close()
    db = dbm.Database(str(f))
    assert db.execute("PRAGMA user_version").fetchone()[0] == 11
    row = db.execute("SELECT root_dir FROM projects").fetchone()
    # never moved: the legacy location is pinned as the project's own root
    assert row[0] == str(paths.data_dir() / "projects")
    # re-opening is idempotent (backfill is a no-op)
    db.close()
    db = dbm.Database(str(f))
    assert db.execute("PRAGMA user_version").fetchone()[0] == 11


def test_create_freezes_configured_root(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    _stub_config(monkeypatch, str(root))
    from nightscribe.core.db import Database
    db = Database(tmp_path / "t.db")
    p = project.create(db, "sn", "SN 2026ziz")
    assert p["root_dir"] == str(root)
    assert str(project.storage_dir(p)).startswith(str(root))
    # and the dict list/get round-trips the column
    assert project.get(db, p["id"])["root_dir"] == str(root)
    assert project.list_projects(db)[0]["root_dir"] == str(root)


def test_create_falls_back_to_legacy_root(tmp_path, monkeypatch):
    # no configured root -> the platformdirs projects folder (no crash,
    # same family of paths the app used before ADR-032)
    _stub_config(monkeypatch, "")
    from nightscribe.core.db import Database
    db = Database(tmp_path / "t.db")
    p = project.create(db, "neo", "2021EQ3")
    assert p["root_dir"] == str(paths.data_dir() / "projects")


def test_storage_dir_precedence(tmp_path, monkeypatch):
    _stub_config(monkeypatch, str(tmp_path / "config_root"))
    from nightscribe.core.db import Database
    db = Database(tmp_path / "t.db")
    p = project.create(db, "pccp", "PCCP 2026A")
    # project root wins over the config root
    moved = project.set_root_dir(db, p["id"], str(tmp_path / "moved"))
    assert moved["root_dir"] == str(tmp_path / "moved")
    assert str(project.storage_dir(moved)).startswith(str(tmp_path / "moved"))
    # a row without root_dir falls back to the config root
    no_root = dict(p, root_dir="")
    assert str(project.storage_dir(no_root)).startswith(
        str(tmp_path / "config_root"))


def test_storage_dir_slug_sanitised(tmp_path, monkeypatch):
    _stub_config(monkeypatch, str(tmp_path / "root"))
    from nightscribe.core.db import Database
    db = Database(tmp_path / "t.db")
    p = project.create(db, "comet", "C/2026 A (Test)")
    folder = project.storage_dir(p)
    assert folder.name == "1-C_2026_A__Test_"


def test_set_root_dir_missing_returns_none(tmp_path):
    from nightscribe.core.db import Database
    db = Database(tmp_path / "t.db")
    assert project.set_root_dir(db, 999, "/tmp/x") is None


def test_project_dir_root_param(tmp_path):
    p = paths.project_dir(7, "AT2020x", root=str(tmp_path / "base"))
    assert p == tmp_path / "base" / "7-AT2020x"
    assert p.is_dir()