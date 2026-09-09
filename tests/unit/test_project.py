############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: project model and step machine (ADR-019)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

from nightscribe.core import project


def _sn_target():
    # Minimal target snapshot as the planner would pass it
    return {"id": "2026ziz", "name": "SN 2026ziz", "mag": 16.5,
            "ra_deg": 180.0, "dec_deg": 40.0, "kind": "sn"}


def test_create_initialises_three_steps(tmp_db):
    # ADR-019 dropped "analyse"; ADR-030 merged "capture" into "plan".
    p = project.create(tmp_db, "sn", "SN 2026ziz", _sn_target())
    assert p is not None
    assert p["kind"] == "sn"
    assert p["status"] == "active"
    assert p["object_name"] == "SN 2026ziz"
    assert len(p["steps"]) == 3
    assert [s["step"] for s in p["steps"]] == ["plan", "process", "publish"]
    assert p["steps"][0]["status"] == "current"
    for s in p["steps"][1:]:
        assert s["status"] == "pending"
    assert p["files"] == []
    # context is preserved
    assert p["context"]["mag"] == 16.5


def test_create_rejects_bad_kind(tmp_db):
    assert project.create(tmp_db, "galaxy", "M31") is None


def test_get_missing_returns_none(tmp_db):
    assert project.get(tmp_db, 999) is None


def test_advance_moves_current_forward(tmp_db):
    p = project.create(tmp_db, "sn", "SN 2026ziz")
    p = project.advance(tmp_db, p["id"])
    assert p["steps"][0]["status"] == "done"
    assert p["steps"][1]["status"] == "current"
    assert p["steps"][2]["status"] == "pending"
    assert p["status"] == "active"


def test_advance_through_all_marks_done(tmp_db):
    p = project.create(tmp_db, "neo", "2021EQ3")
    for _ in range(3):
        p = project.advance(tmp_db, p["id"])
    assert p["status"] == "done"
    assert all(s["status"] == "done" for s in p["steps"])
    # advancing past the end is a no-op
    p2 = project.advance(tmp_db, p["id"])
    assert p2["status"] == "done"


def test_current_step_helper(tmp_db):
    p = project.create(tmp_db, "sn", "SN 2026ziz")
    assert project.current_step(tmp_db, p["id"]) == "plan"
    project.advance(tmp_db, p["id"])
    assert project.current_step(tmp_db, p["id"]) == "process"


def test_list_projects_filters_by_status(tmp_db):
    project.create(tmp_db, "sn", "SN A")
    p2 = project.create(tmp_db, "neo", "NEO B")
    project.advance(tmp_db, p2["id"])  # still active
    active = project.list_projects(tmp_db, "active")
    assert len(active) == 2
    allp = project.list_projects(tmp_db)
    assert len(allp) == 2
    # mark one done via full advance (advance is a no-op past the end)
    for _ in range(3):
        project.advance(tmp_db, p2["id"])
    done = project.list_projects(tmp_db, "done")
    assert len(done) == 1
    assert done[0]["object_name"] == "NEO B"


def test_set_step_status_skip(tmp_db):
    p = project.create(tmp_db, "sn", "SN 2026ziz")
    assert project.set_step_status(tmp_db, p["id"], "process", "skipped")
    p = project.get(tmp_db, p["id"])
    assert p["steps"][1]["status"] == "skipped"


def test_update_step_data_merges(tmp_db):
    p = project.create(tmp_db, "sn", "SN 2026ziz")
    project.update_step_data(tmp_db, p["id"], "plan", {"exp_s": 60})
    project.update_step_data(tmp_db, p["id"], "plan", {"n_frames": 30})
    p = project.get(tmp_db, p["id"])
    data = p["steps"][0]["data"]
    assert data["exp_s"] == 60
    assert data["n_frames"] == 30


def test_update_context_merges(tmp_db):
    p = project.create(tmp_db, "neo", "2021EQ3", {"mag": 18.0})
    project.update_context(tmp_db, p["id"], {"rate_arcsec_min": 12.5})
    p = project.get(tmp_db, p["id"])
    assert p["context"]["mag"] == 18.0
    assert p["context"]["rate_arcsec_min"] == 12.5


def test_set_status(tmp_db):
    p = project.create(tmp_db, "sn", "SN 2026ziz")
    assert project.set_status(tmp_db, p["id"], "archived")
    assert project.get(tmp_db, p["id"])["status"] == "archived"


def test_add_and_list_files(tmp_db):
    p = project.create(tmp_db, "sn", "SN 2026ziz")
    fid = project.add_file(tmp_db, p["id"], "/tmp/seq.json", "sequence")
    assert fid is not None
    project.add_file(tmp_db, p["id"], "/tmp/sn.fits", "fits")
    files = project.list_files(tmp_db, p["id"])
    assert len(files) == 2
    assert files[0]["kind"] == "sequence"
    assert files[1]["kind"] == "fits"


def test_delete_cascades(tmp_db):
    p = project.create(tmp_db, "sn", "SN 2026ziz")
    project.add_file(tmp_db, p["id"], "/tmp/seq.json", "sequence")
    project.update_step_data(tmp_db, p["id"], "plan", {"exp_s": 60})
    assert project.delete(tmp_db, p["id"])
    assert project.get(tmp_db, p["id"]) is None
    # steps and files are gone (cascade)
    rows = tmp_db.execute(
        "SELECT COUNT(*) FROM project_steps WHERE project_id=?",
        (p["id"],)).fetchone()
    assert rows[0] == 0
    rows = tmp_db.execute(
        "SELECT COUNT(*) FROM project_files WHERE project_id=?",
        (p["id"],)).fetchone()
    assert rows[0] == 0


def test_migration_user_version_is_four(tmp_db):
    v = tmp_db.execute("PRAGMA user_version").fetchone()[0]
    assert v == 4


def test_migration_v1_drops_analyse_step(tmp_path):
    # A pre-v2 database still knows the old "analyse" step. Build one by hand
    # (schema at user_version 1, a project stopped on "analyse"), then reopen
    # it so the v1->v2->v3 migrations run and check it cleaned up gracefully.
    import sqlite3
    import time
    from nightscribe.core import db as dbmod
    from nightscribe.core.db import Database

    file = tmp_path / "v1.db"
    conn = sqlite3.connect(str(file))
    conn.executescript(dbmod._SCHEMA)
    conn.executescript(dbmod._V1)
    conn.execute("ALTER TABLE observations ADD COLUMN project_id INTEGER")
    now = time.time()
    cur = conn.execute(
        "INSERT INTO projects (kind, object_name, status, created, updated,"
        " context) VALUES ('sn', 'SNx', 'active', ?, ?, '{}')", (now, now))
    pid = cur.lastrowid
    # the flow was parked on the analyse step
    for step, status in (("plan", "done"), ("capture", "done"),
                         ("process", "done"), ("analyse", "current"),
                         ("publish", "pending")):
        conn.execute(
            "INSERT INTO project_steps (project_id, step, status, data,"
            " updated) VALUES (?, ?, ?, '{}', ?)", (pid, step, status, now))
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()

    # reopen: the Database constructor applies the pending migrations
    db = Database(str(file))
    assert db.execute("PRAGMA user_version").fetchone()[0] == 4
    steps = db.execute(
        "SELECT step, status FROM project_steps WHERE project_id=? ORDER BY id",
        (pid,)).fetchall()
    # analyse (v2) and capture (v3) are gone; "current" ended on publish
    assert all(s not in (("analyse", "current"), ("capture", "current"))
               for s in steps)
    assert [s for s, _st in steps] == ["plan", "process", "publish"]
    assert dict(steps)["publish"] == "current"


def test_migration_v2_merges_capture_into_plan(tmp_path):
    # A pre-v3 database (user_version 2) still has the "capture" step with
    # the calibration counts. Reopen it: the v3 migration moves that data
    # into "plan", hands "current" to "process" and drops the capture row.
    import sqlite3
    import json
    import time
    from nightscribe.core import db as dbmod
    from nightscribe.core.db import Database

    file = tmp_path / "v2.db"
    conn = sqlite3.connect(str(file))
    conn.executescript(dbmod._SCHEMA)
    conn.executescript(dbmod._V1)
    conn.execute("ALTER TABLE observations ADD COLUMN project_id INTEGER")
    now = time.time()
    cur = conn.execute(
        "INSERT INTO projects (kind, object_name, status, created, updated,"
        " context) VALUES ('neo', 'SNx2', 'active', ?, ?, '{}')", (now, now))
    pid = cur.lastrowid
    # capture holds real data and the flow is parked on it
    for step, status, data in (("plan", "done",
                                json.dumps({"n_frames": 30, "exp_s": 60.0})),
                               ("capture", "current",
                                json.dumps({"n_darks": 18, "n_bias": 40,
                                            "exp_dark": 90.0})),
                               ("process", "pending", "{}"),
                               ("publish", "pending", "{}")):
        conn.execute(
            "INSERT INTO project_steps (project_id, step, status, data,"
            " updated) VALUES (?, ?, ?, ?, ?)", (pid, step, status, data, now))
    conn.execute("PRAGMA user_version = 2")
    conn.commit()
    conn.close()

    db = Database(str(file))
    assert db.execute("PRAGMA user_version").fetchone()[0] == 4
    steps = db.execute(
        "SELECT step, status, data FROM project_steps WHERE project_id=?"
        " ORDER BY id",
        (pid,)).fetchall()
    assert [s for s, _st, _d in steps] == ["plan", "process", "publish"]
    plan = dict((s, st) for s, st, _d in steps)
    assert plan["process"] == "current"
    # the capture data landed inside the plan step (merged, not replaced)
    plan_data = json.loads(dict((s, d) for s, _st, d in steps)["plan"])
    assert plan_data["n_frames"] == 30
    assert plan_data["n_darks"] == 18
    assert plan_data["n_bias"] == 40
    assert plan_data["exp_dark"] == 90.0


def test_observations_has_project_id_column(tmp_db):
    cols = {r[1] for r in tmp_db.execute(
        "PRAGMA table_info(observations)").fetchall()}
    assert "project_id" in cols


def test_mark_observed_with_project_id(tmp_db):
    p = project.create(tmp_db, "neo", "2021EQ3")
    tmp_db.mark_observed("2021EQ3", "neo", "2026-08-24",
                         project_id=p["id"])
    row = tmp_db.execute(
        "SELECT project_id FROM observations WHERE object=?", ("2021EQ3",)
    ).fetchone()
    assert row[0] == p["id"]


def _build_v3_db(path):
    # @return: (path, project_id) of a hand-built user_version=3 database with
    # one SN project and its three steps — the state right before Track A.
    import sqlite3
    import time
    from nightscribe.core import db as dbmod

    conn = sqlite3.connect(str(path))
    conn.executescript(dbmod._SCHEMA)
    conn.executescript(dbmod._V1)
    conn.execute("ALTER TABLE observations ADD COLUMN project_id INTEGER")
    now = time.time()
    cur = conn.execute(
        "INSERT INTO projects (kind, object_name, status, created, updated,"
        " context) VALUES ('sn', 'SN2026abc', 'active', ?, ?, '{}')",
        (now, now))
    pid = cur.lastrowid
    for step, status in (("plan", "done"), ("process", "current"),
                         ("publish", "pending")):
        conn.execute(
            "INSERT INTO project_steps (project_id, step, status, data,"
            " updated) VALUES (?, ?, ?, '{}', ?)", (pid, step, status, now))
    conn.execute("PRAGMA user_version = 3")
    conn.commit()
    conn.close()
    return path, pid


def test_fresh_db_has_lifecycle_columns(tmp_db):
    # A brand-new database (Track A) must carry the four lifecycle columns and
    # the created-index straight out of the migration.
    cols = {r[1] for r in tmp_db.execute(
        "PRAGMA table_info(projects)").fetchall()}
    assert {"closed_at", "outcome", "tags", "favorite"} <= cols
    idx = tmp_db.execute(
        "SELECT name FROM sqlite_master WHERE type='index'"
        " AND tbl_name='projects'").fetchall()
    assert any("idx_projects_created" == r[0] for r in idx)


def test_migration_v3_to_v4_preserves_projects(tmp_path):
    # A pre-Track-A database (user_version 3) with a real project must keep
    # every row and gain the lifecycle columns with sane defaults.
    from nightscribe.core.db import Database

    file, pid = _build_v3_db(tmp_path / "v3.db")
    db = Database(str(file))
    assert db.execute("PRAGMA user_version").fetchone()[0] == 4

    # the project itself is intact (kind/name/status/context unchanged)
    row = db.execute(
        "SELECT kind, object_name, status, context FROM projects WHERE id=?",
        (pid,)).fetchone()
    assert row[0] == "sn"
    assert row[1] == "SN2026abc"
    assert row[2] == "active"
    assert row[3] == "{}"

    # the new lifecycle columns exist with their default values
    row = db.execute(
        "SELECT closed_at, outcome, tags, favorite FROM projects WHERE id=?",
        (pid,)).fetchone()
    assert row[0] is None      # closed_at
    assert row[1] is None      # outcome
    assert row[2] == ""        # tags (default '')
    assert row[3] == 0         # favorite (default 0)

    # the three step rows survived the migration
    steps = db.execute(
        "SELECT step FROM project_steps WHERE project_id=? ORDER BY id",
        (pid,)).fetchall()
    assert [s[0] for s in steps] == ["plan", "process", "publish"]


def test_migration_v4_is_idempotent(tmp_path):
    # Re-opening a database already at v4 must not error and must not try to
    # re-add columns (ALTER TABLE ADD COLUMN is not repeatable).
    from nightscribe.core.db import Database

    file, _pid = _build_v3_db(tmp_path / "v3.db")
    Database(str(file))               # migrates 3 -> 4
    db = Database(str(file))          # re-open: no-op
    assert db.execute("PRAGMA user_version").fetchone()[0] == 4
    cols = {r[1] for r in db.execute(
        "PRAGMA table_info(projects)").fetchall()}
    assert {"closed_at", "outcome", "tags", "favorite"} <= cols


# ---------------- Track A / A1: close, reopen, tags, favorite ----------------

def test_close_sets_done_and_outcome(tmp_db):
    p = project.create(tmp_db, "sn", "SN2026abc")
    closed = project.close(tmp_db, p["id"], outcome="confirmed_ia")
    assert closed["status"] == "done"
    assert closed["closed_at"] is not None
    assert closed["outcome"] == "confirmed_ia"


def test_close_without_outcome(tmp_db):
    p = project.create(tmp_db, "neo", "2021EU3")
    closed = project.close(tmp_db, p["id"])
    assert closed["status"] == "done"
    assert closed["outcome"] is None
    assert closed["closed_at"] is not None


def test_close_is_idempotent(tmp_db):
    p = project.create(tmp_db, "sn", "SNx")
    project.close(tmp_db, p["id"], outcome="completed")
    first = project.get(tmp_db, p["id"])
    # second close must not change the stamp or the outcome
    second = project.close(tmp_db, p["id"], outcome="false_positive")
    assert second["status"] == "done"
    assert second["outcome"] == "completed"  # unchanged
    assert second["closed_at"] == first["closed_at"]


def test_reopen_clears_close_and_outcome(tmp_db):
    p = project.create(tmp_db, "sn", "SN2026abc")
    project.close(tmp_db, p["id"], outcome="confirmed_ia")
    reopened = project.reopen(tmp_db, p["id"])
    assert reopened["status"] == "active"
    assert reopened["closed_at"] is None
    assert reopened["outcome"] is None


def test_reopen_from_archived(tmp_db):
    p = project.create(tmp_db, "comet", "29P")
    project.set_status(tmp_db, p["id"], project.STATUS_ARCHIVED)
    reopened = project.reopen(tmp_db, p["id"])
    assert reopened["status"] == "active"
    assert reopened["closed_at"] is None


def test_reopen_active_is_noop(tmp_db):
    p = project.create(tmp_db, "neo", "2021EU3")
    reopened = project.reopen(tmp_db, p["id"])
    assert reopened["status"] == "active"
    assert reopened["closed_at"] is None


def test_close_not_found(tmp_db):
    assert project.close(tmp_db, 99999) is None
    assert project.reopen(tmp_db, 99999) is None


def test_set_tags_from_string(tmp_db):
    p = project.create(tmp_db, "sn", "SNx")
    assert project.set_tags(tmp_db, p["id"], "ia, red, bright")
    assert project.get(tmp_db, p["id"])["tags"] == "ia, red, bright"


def test_set_tags_from_list(tmp_db):
    p = project.create(tmp_db, "sn", "SNx")
    assert project.set_tags(tmp_db, p["id"], ["Ia", "", "favourite"])
    assert project.get(tmp_db, p["id"])["tags"] == "Ia,favourite"


def test_set_tags_clear(tmp_db):
    p = project.create(tmp_db, "sn", "SNx")
    project.set_tags(tmp_db, p["id"], "ia")
    project.set_tags(tmp_db, p["id"], "")
    assert project.get(tmp_db, p["id"])["tags"] == ""


def test_set_favorite_toggle(tmp_db):
    p = project.create(tmp_db, "sn", "SNx")
    assert project.get(tmp_db, p["id"])["favorite"] is False
    project.set_favorite(tmp_db, p["id"], True)
    assert project.get(tmp_db, p["id"])["favorite"] is True
    project.set_favorite(tmp_db, p["id"], False)
    assert project.get(tmp_db, p["id"])["favorite"] is False


def test_outcomes_dict_has_all_kinds():
    for kind in project.VALID_KINDS:
        assert kind in project.OUTCOMES
        assert len(project.OUTCOMES[kind]) >= 2


def test_get_returns_lifecycle_fields(tmp_db):
    p = project.create(tmp_db, "sn", "SNx")
    project.set_tags(tmp_db, p["id"], "ia")
    project.set_favorite(tmp_db, p["id"], True)
    got = project.get(tmp_db, p["id"])
    assert got["tags"] == "ia"
    assert got["favorite"] is True
    assert got["closed_at"] is None
    assert got["outcome"] is None


def test_list_projects_returns_lifecycle_fields(tmp_db):
    p = project.create(tmp_db, "sn", "SNx")
    project.close(tmp_db, p["id"], outcome="completed")
    items = project.list_projects(tmp_db)
    assert items[0]["outcome"] == "completed"
    assert items[0]["closed_at"] is not None
    assert items[0]["status"] == "done"


# ---------------- Track A / A3: list_projects classification ----------------

def test_list_projects_filter_by_kind(tmp_db):
    project.create(tmp_db, "sn", "SN1")
    project.create(tmp_db, "neo", "NEO1")
    sns = project.list_projects(tmp_db, kind="sn")
    assert len(sns) == 1
    assert sns[0]["kind"] == "sn"


def test_list_projects_search(tmp_db):
    project.create(tmp_db, "sn", "SN2026abc")
    project.create(tmp_db, "sn", "SN2026xyz")
    results = project.list_projects(tmp_db, search="abc")
    assert len(results) == 1
    assert "abc" in results[0]["object_name"]


def test_list_projects_search_case_insensitive(tmp_db):
    project.create(tmp_db, "sn", "SN_BrightOne")
    results = project.list_projects(tmp_db, search="brightone")
    assert len(results) == 1


def test_list_projects_filter_by_tags(tmp_db):
    p1 = project.create(tmp_db, "sn", "SN1")
    project.set_tags(tmp_db, p1["id"], "ia, red")
    p2 = project.create(tmp_db, "sn", "SN2")
    project.set_tags(tmp_db, p2["id"], "iin, blue")
    results = project.list_projects(tmp_db, tags="red")
    assert len(results) == 1
    assert results[0]["object_name"] == "SN1"


def test_list_projects_favorites_first(tmp_db):
    p1 = project.create(tmp_db, "sn", "SN1")
    p2 = project.create(tmp_db, "sn", "SN2")
    project.set_favorite(tmp_db, p2["id"], True)
    results = project.list_projects(tmp_db, favorites_first=True)
    assert results[0]["favorite"] is True


def test_list_projects_order_by_name(tmp_db):
    project.create(tmp_db, "sn", "ZZZ")
    project.create(tmp_db, "sn", "AAA")
    results = project.list_projects(tmp_db, order="name")
    assert results[0]["object_name"] == "AAA"


def test_list_projects_order_by_created(tmp_db):
    p_old = project.create(tmp_db, "sn", "Old")
    p_new = project.create(tmp_db, "sn", "New")
    results = project.list_projects(tmp_db, order="created")
    assert results[0]["object_name"] == "New"


def test_list_projects_combined_filters(tmp_db):
    p1 = project.create(tmp_db, "sn", "SN2026abc")
    project.set_tags(tmp_db, p1["id"], "ia")
    project.set_favorite(tmp_db, p1["id"], True)
    p2 = project.create(tmp_db, "neo", "NEO2026abc")
    results = project.list_projects(tmp_db, kind="sn", search="abc",
                                     tags="ia", favorites_first=True)
    assert len(results) == 1
    assert results[0]["id"] == p1["id"]
