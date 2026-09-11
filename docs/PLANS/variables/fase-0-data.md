# Track V — Fase 0: datos (migración, campaña, variables, fuentes)

> Subplanes V0.1–V0.9 del plan maestro [../variables-campaigns.md](../variables-campaigns.md).
> Un subplan = un commit. Anclas verificadas a HEAD `4b7635a`; si una no
> coincide: **parar y reportar**. Lee antes `LEEME.md` (patrones y errores
> frecuentes). Sin GUI en toda esta fase.

---

## V0.1 — Migración `user_version` 7: tabla `campaigns` + `projects.campaign_id`

**Contexto a leer (solo esto)**: `nightscribe/core/db.py:219-232` (bloque v6
y cierre de `_migrate`), `tests/unit/test_project.py:340-353` (patrón de test
de migración).

**Toca**: `nightscribe/core/db.py`; `tests/unit/test_db_v7.py` (**nuevo**).

**Escribe exactamente esto**:

1. `core/db.py`, tras la línea `conn.execute("PRAGMA user_version = 6")`
   (:231) y antes de `conn.commit()` (:232), inserta:

```python
    if v < 7:
        # Track V (ADR-035): observation campaigns — a first-class entity a
        # project hangs from (1:N, any kind: campaigns are orthogonal, V-b).
        # The protocol rides as JSON: {cadence_nights, filters[],
        # comp_stars[], notes}. The ALTER is guarded so re-opening an
        # already-migrated DB is a no-op (pattern of v4/v6).
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS campaigns (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            group_name  TEXT DEFAULT '',
            coordinator TEXT DEFAULT '',
            goal        TEXT DEFAULT '',
            protocol    TEXT DEFAULT '{}',
            report_url  TEXT DEFAULT '',
            data_url    TEXT DEFAULT '',
            status      TEXT NOT NULL DEFAULT 'active',
            created     REAL NOT NULL,
            closed_at   REAL
        );
        """)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(projects)")}
        if "campaign_id" not in cols:
            conn.execute("ALTER TABLE projects ADD COLUMN campaign_id INTEGER"
                         " REFERENCES campaigns(id) ON DELETE SET NULL")
        conn.execute("PRAGMA user_version = 7")
```

2. `tests/unit/test_db_v7.py` (**nuevo**, con cabecera GPL de LEEME §1 —
   nombre del módulo: «Unit tests: v7 migration (campaigns)»):

```python
import pytest

from nightscribe.core.db import Database


def test_fresh_db_has_campaigns_and_v7(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    assert db.execute("PRAGMA user_version").fetchone()[0] == 7
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
    assert db.execute("PRAGMA user_version").fetchone()[0] == 7


def test_upgrade_from_v6_restores_campaigns(tmp_path):
    f = tmp_path / "t.db"
    db = Database(str(f))
    db.execute("DROP TABLE campaigns")
    db.execute("PRAGMA user_version = 6")
    db.commit()
    db.close()
    db = Database(str(f))           # migrates 6 -> 7 again
    assert db.execute("PRAGMA user_version").fetchone()[0] == 7
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
```

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_db_v7.py -q`
**Hecho cuando**: los 4 tests pasan y `tests/unit` sigue verde (anota N→M).
**Commit**: `Core: DB migration v7 — campaigns table + projects.campaign_id (ADR-035, subplan V0.1)`
**Estado**: ✅ Hecho (2026-09-11, suite 993)

---

## V0.2 — `core/campaign.py`: CRUD

**Contexto a leer (solo esto)**: `nightscribe/core/followup.py:1-60` (estilo
de módulo de dominio con `db.execute`).
**Precondición**: V0.1 hecha.

**Toca**: `nightscribe/core/campaign.py` (**nuevo**);
`tests/unit/test_campaign.py` (**nuevo**).

**Escribe exactamente esto** — `nightscribe/core/campaign.py` (con la
cabecera GPL; nombre del módulo: «Observation campaigns model (ADR-035)»):

```python
"""Observation campaigns: a first-class entity projects hang from (1:N).

A campaign is the group's shared commitment — a science goal, a protocol
(cadence in nights, filters, comparison stars, notes) and the report/data
URLs — and any project kind can join it (V-b). Storage: the `campaigns`
table (migration v7). All SQL goes through db.execute (ADR-002); the module
mirrors the pragmatic style of core/followup.py.
"""

import json
import logging
import time

logger = logging.getLogger(__name__)

CAMPAIGN_ACTIVE = "active"
CAMPAIGN_FINISHED = "finished"

# Editable fields (campaign.update whitelist)
_EDITABLE = ("name", "group_name", "coordinator", "goal", "protocol",
             "report_url", "data_url")


def _now():
    # @return: current epoch seconds
    return time.time()


def _row_to_campaign(row):
    # @return: campaign dict from a SELECT row (protocol JSON decoded)
    return {"id": row[0], "name": row[1], "group_name": row[2] or "",
            "coordinator": row[3] or "", "goal": row[4] or "",
            "protocol": json.loads(row[5] or "{}"),
            "report_url": row[6] or "", "data_url": row[7] or "",
            "status": row[8], "created": row[9], "closed_at": row[10]}


def create(db, name, group_name="", coordinator="", goal="", protocol=None,
           report_url="", data_url=""):
    # @args: db - Database, name - campaign name, protocol - dict with
    #        cadence_nights / filters / comp_stars / notes (all optional)
    # @return: campaign id
    cur = db.execute(
        "INSERT INTO campaigns (name, group_name, coordinator, goal,"
        " protocol, report_url, data_url, status, created)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (name, group_name, coordinator, goal,
         json.dumps(protocol or {}, ensure_ascii=False),
         report_url, data_url, CAMPAIGN_ACTIVE, _now()),
    )
    db.commit()
    return cur.lastrowid


def get(db, campaign_id):
    # @return: campaign dict or None
    row = db.execute(
        "SELECT id, name, group_name, coordinator, goal, protocol,"
        " report_url, data_url, status, created, closed_at"
        " FROM campaigns WHERE id=?",
        (campaign_id,),
    ).fetchone()
    return _row_to_campaign(row) if row else None


def list_campaigns(db, status=None):
    # @args: status - CAMPAIGN_ACTIVE | CAMPAIGN_FINISHED | None (all)
    # @return: list of campaign dicts, newest first
    sql = ("SELECT id, name, group_name, coordinator, goal, protocol,"
           " report_url, data_url, status, created, closed_at FROM campaigns")
    params = []
    if status:
        sql += " WHERE status=?"
        params.append(status)
    sql += " ORDER BY created DESC"
    return [_row_to_campaign(r) for r in db.execute(sql, params).fetchall()]


def update(db, campaign_id, **fields):
    # Edits the editable fields only (status changes go through
    # finish/reopen). Protocol accepts a dict (JSON-encoded here).
    # @return: True if the campaign was found and updated
    sets, params = [], []
    for key in _EDITABLE:
        if key in fields:
            val = fields[key]
            if key == "protocol":
                val = json.dumps(val or {}, ensure_ascii=False)
            sets.append(f"{key}=?")
            params.append(val)
    if not sets:
        return False
    params.append(campaign_id)
    cur = db.execute(f"UPDATE campaigns SET {', '.join(sets)} WHERE id=?",
                     params)
    db.commit()
    return cur.rowcount > 0


def finish(db, campaign_id):
    # Marks the campaign finished (stamps closed_at). Idempotent.
    # @return: updated campaign dict, or None if not found
    camp = get(db, campaign_id)
    if not camp:
        return None
    if camp["status"] == CAMPAIGN_FINISHED:
        return camp
    db.execute("UPDATE campaigns SET status=?, closed_at=? WHERE id=?",
               (CAMPAIGN_FINISHED, _now(), campaign_id))
    db.commit()
    return get(db, campaign_id)


def reopen(db, campaign_id):
    # Reopens a finished campaign (clears closed_at). Idempotent.
    # @return: updated campaign dict, or None if not found
    camp = get(db, campaign_id)
    if not camp:
        return None
    if camp["status"] == CAMPAIGN_ACTIVE:
        return camp
    db.execute("UPDATE campaigns SET status=?, closed_at=NULL WHERE id=?",
               (CAMPAIGN_ACTIVE, campaign_id))
    db.commit()
    return get(db, campaign_id)


def delete(db, campaign_id):
    # Deletes the campaign; projects keep going (campaign_id -> NULL).
    # @return: True if the campaign was found and deleted
    cur = db.execute("DELETE FROM campaigns WHERE id=?", (campaign_id,))
    db.commit()
    return cur.rowcount > 0
```

**Tests a añadir** — `tests/unit/test_campaign.py` (cabecera GPL; «Unit
tests: campaigns CRUD (Track V, V0.2)»):

```python
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
```

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_campaign.py -q`
**Hecho cuando**: tests verdes; suite verde (N→M).
**Commit**: `Core: campaign CRUD model (ADR-035, subplan V0.2)`
**Estado**: ✅ Hecho (2026-09-11, suite 998)

---

## V0.3 — `campaign.py`: protocolo + `due_campaigns`

**Contexto a leer (solo esto)**: `nightscribe/core/followup.py:93-102`
(`days_since_last_session`).
**Precondición**: V0.2 hecha.

**Toca**: `nightscribe/core/campaign.py` (ampliar);
`tests/unit/test_campaign.py` (ampliar, añadir al final).

**Escribe exactamente esto** — al final de `core/campaign.py`:

```python
# ---------------- protocol and the Tonight loop ----------------

def protocol_get(camp, key, default=None):
    # @args: camp - campaign dict, key - cadence_nights | filters |
    #        comp_stars | notes, default - when absent
    # @return: the protocol value
    return (camp.get("protocol") or {}).get(key, default)


def projects_of(db, campaign_id, status="active"):
    # The projects hanging from a campaign (any kind — V-b).
    # @return: [{id, object_name, kind, context}]
    sql = ("SELECT id, object_name, kind, context FROM projects"
           " WHERE campaign_id=?")
    params = [campaign_id]
    if status:
        sql += " AND status=?"
        params.append(status)
    rows = db.execute(sql, params).fetchall()
    return [{"id": r[0], "object_name": r[1], "kind": r[2],
             "context": json.loads(r[3] or "{}")} for r in rows]


def due_campaigns(db):
    # The Tonight loop (V-d): every DUE project of every active campaign —
    # a project is due when its last visit is >= the campaign cadence in
    # nights, or when it was never visited at all.
    # @return: [{"campaign", "project", "overdue_days", "cadence_nights",
    #          "never_visited"}] — one row per due project
    from . import followup
    out = []
    for camp in list_campaigns(db, status=CAMPAIGN_ACTIVE):
        cad = int(protocol_get(camp, "cadence_nights", 1) or 1)
        for proj in projects_of(db, camp["id"], status="active"):
            days = followup.days_since_last_session(db, proj["id"])
            never = days is None
            if never:
                overdue = cad      # as due as it gets: no visit at all
            elif days >= cad:
                overdue = days
            else:
                continue
            out.append({"campaign": camp, "project": proj,
                        "overdue_days": overdue, "cadence_nights": cad,
                        "never_visited": never})
    return out
```

**Tests a añadir** (al final de `tests/unit/test_campaign.py`; necesitan
`from nightscribe.core import followup, project` arriba):

```python
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
```

**Estado**: ✅ Hecho (2026-09-11, suite 1004)

---

## V0.4 — `project.py`: kind `variable` + `campaign_id` + CLI

**Contexto a leer (solo esto)**: `nightscribe/core/project.py:32-58, 74-83,
99-127, 150-206`; `nightscribe/__main__.py:344-345`.
**Precondición**: V0.1 hecha.

**Toca**: `nightscribe/core/project.py`; `nightscribe/__main__.py`;
`tests/unit/test_project_variable.py` (**nuevo**).

**Escribe exactamente esto**:

1. `project.py:33` →
   `VALID_KINDS = ("sn", "neo", "comet", "pccp", "transit", "hads", "variable")`
2. `project.py`, dict `OUTCOMES` (:49-57): añade tras la entrada `"hads"`:
   ```python
       "variable": ("completed", "reported", "abandoned"),
   ```
3. `project.py` `_row_to_project` (:74-83): el comentario de orden de fila
   añade al final «, campaign_id (Track V, nullable)» y el dict gana
   `"campaign_id": row[12]`:
   ```python
       return {"id": row[0], "kind": row[1], "object_name": row[2],
               "status": row[3], "created": row[4], "updated": row[5],
               "context": json.loads(row[6] or "{}"), "root_dir": row[7],
               "closed_at": row[8], "outcome": row[9],
               "tags": row[10] or "", "favorite": bool(row[11]),
               "campaign_id": row[12]}
   ```
4. `create` (:99-127): firma → `def create(db, kind, object_name, context=None,
   campaign_id=None):`; el comentario `@args` añade «, campaign_id - optional
   campaigns.id link (ADR-035)»; el INSERT pasa a:
   ```python
       cur = db.execute(
           "INSERT INTO projects (kind, object_name, status, created, updated,"
           " context, root_dir, campaign_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
           (kind, object_name, STATUS_ACTIVE, now, now, ctx, root,
            campaign_id),
       )
   ```
5. `list_projects` (:150-184): firma añade `campaign_id=None` al final; el
   `@args` lo documenta («campaign_id - filter by campaigns.id or None»);
   `cols` (:159-160) →
   ```python
       cols = ("id, kind, object_name, status, created, updated, context,"
               " root_dir, closed_at, outcome, tags, favorite, campaign_id")
   ```
   y tras el bloque `if tags:` (:171-173) añade:
   ```python
       if campaign_id is not None:
           where.append("campaign_id=?")
           params.append(campaign_id)
   ```
6. `get` (:187-206): el SELECT (:190-193) termina ahora con
   `... tags, favorite, campaign_id FROM projects"`.
7. `__main__.py:344-345`: el help de `--kind` pasa a
   `help="sn|neo|comet|pccp|transit|hads|variable"`.

**Tests a añadir** — `tests/unit/test_project_variable.py` (cabecera GPL;
«Unit tests: variable kind + campaign link (Track V, V0.4)»):

```python
import pytest

from nightscribe.core import campaign, project
from nightscribe.core.db import Database


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "t.db"))


def test_variable_is_a_valid_kind_with_outcomes(db):
    assert "variable" in project.VALID_KINDS
    assert set(project.OUTCOMES["variable"]) >= {"completed", "abandoned"}
    p = project.create(db, "variable", "T CrB")
    assert p is not None and p["kind"] == "variable"
    assert p["campaign_id"] is None


def test_create_with_campaign_id_and_list_filter(db):
    cid = campaign.create(db, "Campaña T CrB")
    a = project.create(db, "variable", "T CrB", campaign_id=cid)
    b = project.create(db, "sn", "SN 2026abc")
    assert project.get(db, a["id"])["campaign_id"] == cid
    assert [p["object_name"] for p in
            project.list_projects(db, campaign_id=cid)] == ["T CrB"]
    # the generic filters keep working with campaign_id
    assert project.list_projects(db, campaign_id=cid, kind="sn") == []


def test_every_valid_kind_still_has_outcomes(db):
    for kind in project.VALID_KINDS:
        assert kind in project.OUTCOMES
        assert len(project.OUTCOMES[kind]) >= 2
```

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_project_variable.py tests/unit/test_project.py -q`
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Core: kind 'variable' + campaign_id on projects (ADR-035, V0.4)`
**Estado**: ✅ Hecho (2026-09-11, suite 1001)

---

## V0.5 — `core/variables.py`: `next_extremum` + `phase_at`

**Contexto a leer (solo esto)**: `nightscribe/core/hads.py:228-250` (estilo de
módulo de dominio puro).
**Precondición**: ninguna.

**Toca**: `nightscribe/core/variables.py` (**nuevo**);
`tests/unit/test_variables.py` (**nuevo**).

**Escribe exactamente esto** — `nightscribe/core/variables.py` (cabecera GPL;
«Long-period variable stars module (ADR-035)»):

```python
"""Long-period variable stars: cycle maths, heliocentric dates and the
brightness-event advisor.

The molde is the multi-night follow-up (Track B): one point per night and
filter, folded later by the catalog period. All functions are pure and
local — no network, no db. Times are MJD inside the module; the VSX Epoch
arrives as JD and is converted by the VSX parser (MJD = JD - 2400000.5).
"""

import logging
import math
import statistics
import time

logger = logging.getLogger(__name__)

MJD0 = 2400000.5          # MJD = JD - MJD0

# VSX convention (V-e): for eclipsing binaries the Epoch marks the MINIMUM
# (primary eclipse); for pulsating/eruptive stars it marks the MAXIMUM.
# The FIRST component of a composite type decides: "E-DO" eclipses,
# "NR+ELL" does not (there ELL is the orbital ellipsoidal modulation).
_EPOCH_MIN_PREFIXES = ("EA", "EB", "EW", "E/", "E-")


def _epoch_is_minimum(var_type):
    # @args: var_type - VSX variability type, e.g. "M", "NR+ELL", "E-DO"
    # @return: True when the VSX Epoch marks the light minimum
    first = (var_type or "").split("+")[0].strip().upper()
    return first == "E" or first.startswith(_EPOCH_MIN_PREFIXES)


def _now_mjd():
    # @return: current MJD (UTC)
    return time.time() / 86400.0 + 2440587.5 - MJD0


def phase_at(mjd, period_d, epoch_mjd):
    # @args: mjd - instant, period_d - period in days, epoch_mjd - cycle
    #        epoch (phase 0)
    # @return: phase in [0, 1), or None when the ephemeris is incomplete
    if not period_d or epoch_mjd is None:
        return None
    return ((mjd - epoch_mjd) / period_d) % 1.0


def next_extremum(period_d, epoch_mjd, now_mjd=None, var_type=""):
    # The next extremum of the cycle from now — maximum for pulsating
    # stars, minimum for eclipsing ones (V-e) — whichever comes FIRST,
    # labelled, so Tonight can say "maximum expected in ~N days".
    # @return: {"kind": "max"|"min", "mjd": float, "days": float} or None
    if not period_d or epoch_mjd is None:
        return None
    now = now_mjd if now_mjd is not None else _now_mjd()
    if _epoch_is_minimum(var_type):
        min_ep, max_ep = epoch_mjd, epoch_mjd + period_d / 2.0
    else:
        max_ep, min_ep = epoch_mjd, epoch_mjd + period_d / 2.0

    def _next(ep):
        # @return: mjd of the first occurrence of epoch `ep` at/after now
        n = math.ceil((now - ep) / period_d - 1e-9)
        return ep + n * period_d

    nmax, nmin = _next(max_ep), _next(min_ep)
    if nmax <= nmin:
        return {"kind": "max", "mjd": nmax, "days": round(nmax - now, 1)}
    return {"kind": "min", "mjd": nmin, "days": round(nmin - now, 1)}
```

**Tests a añadir** — `tests/unit/test_variables.py` (cabecera GPL; «Unit
tests: variable star maths (Track V, V0.5-V0.7)»):

```python
import pytest

from nightscribe.core import variables


def test_phase_at_basic():
    assert variables.phase_at(1005.0, 10.0, 1000.0) == 0.5
    assert variables.phase_at(1000.0, 10.0, 1000.0) == 0.0
    assert variables.phase_at(1005.0, None, 1000.0) is None
    assert variables.phase_at(1005.0, 10.0, None) is None


def test_next_extremum_pulsating_returns_whichever_first():
    # Mira rule: epoch = maximum. now=1003: max at 1010 (7 d), min at
    # 1005 (2 d) -> the minimum comes first.
    out = variables.next_extremum(10.0, 1000.0, now_mjd=1003.0, var_type="M")
    assert out == {"kind": "min", "mjd": 1005.0, "days": 2.0}


def test_next_extremum_eclipsing_epoch_is_minimum():
    # EA rule: epoch = minimum. now=1003: min at 1010 (7 d), max at
    # 1005 (2 d) -> the maximum comes first.
    out = variables.next_extremum(10.0, 1000.0, now_mjd=1003.0,
                                  var_type="E-DO")
    assert out == {"kind": "max", "mjd": 1005.0, "days": 2.0}


def test_next_extremum_composite_type_uses_first_component():
    # "NR+ELL": NR decides -> epoch = maximum (the ELL is orbital, not
    # an eclipse) — documented limitation (V-e)
    out = variables.next_extremum(10.0, 1000.0, now_mjd=1001.0,
                                  var_type="NR+ELL")
    assert out["kind"] == "min"          # min (epoch+P/2=1005) before max (1010)


def test_next_extremum_incomplete_ephemeris():
    assert variables.next_extremum(None, 1000.0) is None
    assert variables.next_extremum(10.0, None) is None


def test_next_extremum_real_mira_ephemeris():
    # omi Cet from the frozen VSX fixture: P=331.3 d, epoch JD 2458457
    epoch_mjd = 2458457 - 2400000.5
    out = variables.next_extremum(331.3, epoch_mjd, now_mjd=61239.0,
                                  var_type="M")
    assert out["kind"] == "max"
    assert out["mjd"] == pytest.approx(epoch_mjd + 9 * 331.3, abs=1e-6)
```

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_variables.py -q`
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Core: variable star cycle maths — next extremum + phase (ADR-035, subplan V0.5)`
**Nota (2026-09-11)**: el test `real_mira_ephemeris` de la spec traía un `now_mjd=61239.0`
caído justo ANTES de la 8ª mínima, así que la regla "whichever first" (la que fijan los
otros dos tests y el código spec) devolvía la mínima, no la máxima. Se subió `now` a
61300.0 (justo después de la 8ª mínima) para que el máximo (9P) gane la carrera, que es
lo que el test quería fijar. Las aserciones (`max`, 9·P) y el código de `variables.py`
se mantienen tal cual spec.
**Estado**: ✅ Hecho (2026-09-11, suite 1010)

---

## V0.6 — `variables.py`: `jd_to_hjd`

**Contexto a leer (solo esto)**: `nightscribe/core/ephem_minor.py:220-240`
(`sun_ra_dec`).
**Precondición**: V0.5 hecha.

**Toca**: `nightscribe/core/variables.py` (ampliar);
`tests/unit/test_variables.py` (ampliar).

**Escribe exactamente esto** — al final de `core/variables.py`:

```python
# ---------------- heliocentric Julian date ----------------

_LIGHT_TIME_S_PER_AU = 499.004784   # 1 AU / c, in seconds


def jd_to_hjd(jd, ra_deg, dec_deg):
    # Heliocentric Julian Date: the geocentric JD corrected for the light
    # travel time between Earth and Sun (at most +/-499 s). AAVSO reports
    # are filed in HJD. The Sun position is Schlyter's (ephem_minor,
    # ADR-009), good to ~1 arcmin -> <0.2 s here, far below photometric
    # needs. Convention (checked): a star in the Sun's direction is seen
    # EARLIER from Earth, so HJD = JD + (n . s) * r * tau.
    # @args: jd - Julian date (UTC), ra_deg/dec_deg - target (degrees)
    # @return: HJD (float)
    from . import ephem_minor
    sra, sdec, r = ephem_minor.sun_ra_dec(jd)
    ra, dec = math.radians(ra_deg), math.radians(dec_deg)
    sra, sdec = math.radians(sra), math.radians(sdec)
    dot = (math.cos(dec) * math.cos(ra) * math.cos(sdec) * math.cos(sra)
           + math.cos(dec) * math.sin(ra) * math.cos(sdec) * math.sin(sra)
           + math.sin(dec) * math.sin(sdec))
    return jd + dot * r * _LIGHT_TIME_S_PER_AU / 86400.0
```

**Tests a añadir** (al final de `tests/unit/test_variables.py`):

```python
def test_hjd_frozen_reference_wesb1():
    # Frozen 2026-09-11 against the project Sun (Schlyter): +250.09 s
    jd = 2459653.44800
    hjd = variables.jd_to_hjd(jd, 15.2254, 55.0667)
    assert (hjd - jd) * 86400 == pytest.approx(250.09, abs=30.0)


def test_hjd_frozen_reference_tcrb():
    # Frozen 2026-09-11 against the project Sun (Schlyter): -196.45 s
    jd = 2459653.44800
    hjd = variables.jd_to_hjd(jd, 239.87567, 25.92017)
    assert (hjd - jd) * 86400 == pytest.approx(-196.45, abs=30.0)


def test_hjd_is_bounded_by_the_light_time_across_1_au():
    from nightscribe.core import ephem_minor
    for month in range(12):
        jd = 2460000.0 + 30 * month
        for ra in (0.0, 90.0, 180.0, 270.0):
            corr_s = abs(variables.jd_to_hjd(jd, ra, 30.0) - jd) * 86400
            assert corr_s <= 499.01


def test_hjd_sign_towards_and_away_from_the_sun():
    from nightscribe.core import ephem_minor
    jd = 2459653.44800
    sra, sdec, r = ephem_minor.sun_ra_dec(jd)
    towards = (variables.jd_to_hjd(jd, sra, sdec) - jd) * 86400
    away = (variables.jd_to_hjd(jd, (sra + 180) % 360, -sdec) - jd) * 86400
    assert towards == pytest.approx(r * 499.004784, rel=1e-3)
    assert away == pytest.approx(-r * 499.004784, rel=1e-3)
```

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_variables.py -q`
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Core: heliocentric Julian date (Schlyter Sun, frozen references) (ADR-035, subplan V0.6)`
**Nota (2026-09-11)**: el test `bounded` de la spec hardcodeaba la cota en 499.01 s
(1 AU exacta), pero la corrección HJD es la proyección del vector Tierra-Sol sobre la
dirección de la estrella, acotada por r · c donde r es la distancia real Tierra-Sol de esa
fecha (0.983–1.017 AU → máx ~507 s). La propia spec ya usa `r·499.004784` en el test
`towards/away` (que pasa), así que la implementación (multiplicar por r) es la correcta y
se mantiene tal cual. Se renombró el test a `..._across_the_earth_sun_distance` y la cota
pasa a derivarse de `ephem_minor.sun_ra_dec(jd)` (r · 499.004784). Código `variables.py`
intacto según spec.
**Estado**: ✅ Hecho (2026-09-11, suite 1014)

---

## V0.7 — `variables.py`: `detect_event` (asesor de eventos)

**Contexto a leer (solo esto)**: `nightscribe/core/followup.py:151-169`
(forma de los puntos).
**Precondición**: V0.5 hecha.

**Toca**: `nightscribe/core/variables.py` (ampliar);
`tests/unit/test_variables.py` (ampliar).

**Escribe exactamente esto** — al final de `core/variables.py`:

```python
# ---------------- brightness-event advisor (V-h) ----------------

# Only the observer's OWN points count; survey context (source="survey:*")
# has a different zero point and would fake events.
_EVENT_SOURCES = ("manual", "paste", "file", "quicklook")


def detect_event(points, threshold=0.5):
    # Spots a brightness jump (the WeSb 1 protocol: "if a drop is seen,
    # raise the cadence"). Per filter, the latest point is compared with
    # the median of the previous ones; a filter needs >= 4 points. Mind the
    # inverted magnitude axis: a brightness DROP is a POSITIVE delta.
    # @args: points - followup.list_points() dicts, threshold - min |Δmag|
    # @return: {"direction": "drop"|"rise", "delta_mag": float, "filter":
    #          str} for the strongest jump across filters, or None
    by_filter = {}
    for p in points:
        if (p.get("source") or "manual") not in _EVENT_SOURCES:
            continue
        if p.get("mag") is None or p.get("mjd") is None:
            continue
        by_filter.setdefault(p.get("filter") or "?", []).append(p)
    best = None
    for filt, pts in by_filter.items():
        pts = sorted(pts, key=lambda p: p["mjd"])
        if len(pts) < 4:
            continue
        med = statistics.median(p["mag"] for p in pts[:-1])
        delta = pts[-1]["mag"] - med
        if abs(delta) >= threshold and \
                (best is None or abs(delta) > best["delta_mag"]):
            best = {"direction": "drop" if delta > 0 else "rise",
                    "delta_mag": round(abs(delta), 2), "filter": filt}
    return best
```

**Tests a añadir** (al final de `tests/unit/test_variables.py`):

```python
def _pts(mags, filt="V", source="manual"):
    return [{"mjd": 1000.0 + i, "filter": filt, "mag": m, "err": None,
             "source": source} for i, m in enumerate(mags)]


def test_detect_event_drop():
    # flat 12.0, last point fades to 12.8 -> brightness drop (dip)
    ev = variables.detect_event(_pts([12.0, 12.1, 11.9, 12.0, 12.8]))
    assert ev["direction"] == "drop"
    assert ev["delta_mag"] == pytest.approx(0.8, abs=0.05)
    assert ev["filter"] == "V"


def test_detect_event_rise():
    # T CrB erupting: last point much BRIGHTER (mag down)
    ev = variables.detect_event(_pts([10.1, 10.0, 10.1, 10.0, 8.5]))
    assert ev["direction"] == "rise"


def test_detect_event_needs_four_points_and_threshold():
    assert variables.detect_event(_pts([12.0, 12.0, 13.0])) is None
    assert variables.detect_event(_pts([12.0, 12.1, 11.9, 12.0, 12.3])) \
        is None                               # 0.3 < 0.5 threshold


def test_detect_event_ignores_survey_points_and_splits_filters():
    pts = _pts([12.0, 12.0, 12.0, 12.0], source="survey:ztf")
    pts += _pts([12.0, 12.1, 11.9, 12.0, 12.9], filt="B")
    ev = variables.detect_event(pts)
    assert ev["filter"] == "B"                # the survey run never fires
```

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_variables.py -q`
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Core: brightness-event advisor (dip/outburst detection) (ADR-035, subplan V0.7)`
**Estado**: ✅ Hecho (2026-09-11, suite 1018)

---

## V0.8 — `core/sources/vsx.py` (AAVSO VSX)

**Contexto a leer (solo esto)**:
`nightscribe/core/sources/hads_sheet.py:29-70` (patrón de fuente con
`db.http_get`); `nightscribe/core/db.py:29-53` (`SOURCE_TTL`).
**Precondición**: ninguna. Los fixtures ya existen (commit 0):
`tests/fixtures/vsx_t_crb.json`, `vsx_omi_cet.json`, `vsx_ee_cep.json`,
`vsx_not_found.json`.

**Toca**: `nightscribe/core/sources/vsx.py` (**nuevo**);
`nightscribe/core/db.py` (una línea en `SOURCE_TTL`);
`tests/unit/test_vsx.py` (**nuevo**).

**Escribe exactamente esto**:

1. `core/db.py`, en `SOURCE_TTL`, tras la entrada `"hads"` (:40-41), añade:
   ```python
       "vsx": 7 * DAY,      # AAVSO VSX object data: stable for weeks
       "surveys": 30 * DAY,  # survey light-curve context (ALeRCE/ZTF)
   ```

2. `nightscribe/core/sources/vsx.py` (**nuevo**, cabecera GPL; «AAVSO VSX
   source module»):

```python
"""AAVSO VSX (Variable Star Index) object lookup.

One HTTP call per star through the db cache (TTL 7 days, V-c). NOTE: the
API lives on the `vsx.aavso.org` subdomain — `www.aavso.org` sits behind a
Cloudflare challenge that blocks plain clients (verified 2026-09-11).
Failure never breaks anything: lookup() returns None and the caller falls
back to SIMBAD/manual.
"""

import json
import logging

import requests

from ..db import db

logger = logging.getLogger(__name__)

URL = "https://vsx.aavso.org/index.php"


def lookup(name, force=False):
    # One variable star from the VSX API (name or AUID).
    # @args: name - e.g. "T CrB", force - bypass the cache read
    # @return: dict {name, auid, ra_deg, dec_deg, var_type, period_d,
    #          epoch_mjd, max, min, max_band, min_band, spectral,
    #          constellation} or None when unknown / on failure
    def fetch():
        r = requests.get(URL, params={"view": "api.object", "ident": name,
                                      "format": "json"}, timeout=30)
        r.raise_for_status()
        return r.content, "application/json"
    try:
        body, _ = db.http_get(f"vsx:object:{name}", "vsx", fetch,
                              force=force)
    except requests.RequestException as err:
        logger.warning("VSX lookup failed for %s: %s", name, err)
        return None
    return parse_object(body)


def _float(text):
    # @return: float of the first token of a VSX numeric string, or None
    try:
        return float(str(text).split()[0])
    except (TypeError, ValueError, IndexError):
        return None


def _mag(text):
    # VSX magnitudes carry the band: "2.0 V" -> (2.0, "V")
    # @return: (value or None, band string)
    parts = str(text or "").split()
    return _float(text), (parts[1] if len(parts) > 1 else "")


def parse_object(body):
    # @args: body - raw JSON bytes of the api.object answer
    # @return: curated dict, or None when VSX does not know the name
    #          ({"VSXObject":[]}) or the payload is broken
    try:
        obj = json.loads(body.decode("utf-8", "replace")).get("VSXObject")
    except (ValueError, AttributeError) as err:
        logger.warning("VSX payload not parseable: %s", err)
        return None
    if not obj:
        return None
    epoch_mjd = None
    if _float(obj.get("Epoch")) is not None:
        epoch_mjd = _float(obj.get("Epoch")) - 2400000.5  # JD -> MJD
    max_mag, max_band = _mag(obj.get("MaxMag"))
    min_mag, min_band = _mag(obj.get("MinMag"))
    return {"name": obj.get("Name") or "",
            "auid": obj.get("AUID") or "",
            "ra_deg": _float(obj.get("RA2000")),
            "dec_deg": _float(obj.get("Declination2000")),
            "var_type": obj.get("VariabilityType") or "",
            "period_d": _float(obj.get("Period")),
            "epoch_mjd": epoch_mjd,
            "max": max_mag, "min": min_mag,
            "max_band": max_band, "min_band": min_band,
            "spectral": obj.get("SpectralType") or "",
            "constellation": obj.get("Constellation") or ""}
```

**Tests a añadir** — `tests/unit/test_vsx.py` (cabecera GPL; «Unit tests:
VSX source (Track V, V0.8)»):

```python
import json
from pathlib import Path

import pytest

from nightscribe.core.sources import vsx

FIX = Path(__file__).resolve().parent.parent / "fixtures"


def _fixture(name):
    return (FIX / name).read_bytes()


def test_parse_t_crb():
    v = vsx.parse_object(_fixture("vsx_t_crb.json"))
    assert v["name"] == "T CrB"
    assert v["auid"] == "000-BBW-825"
    assert v["ra_deg"] == pytest.approx(239.87567)
    assert v["dec_deg"] == pytest.approx(25.92017)
    assert v["var_type"] == "NR+ELL"
    assert v["period_d"] == pytest.approx(227.5528)
    assert v["epoch_mjd"] == pytest.approx(2455828.9 - 2400000.5)
    assert v["max"] == 2.0 and v["max_band"] == "V"
    assert v["min"] == 10.8 and v["min_band"] == "V"
    assert v["spectral"] == "M3III+WD"


def test_parse_mira_and_eclipsing():
    mira = vsx.parse_object(_fixture("vsx_omi_cet.json"))
    assert mira["var_type"] == "M"
    assert mira["period_d"] == pytest.approx(331.3)
    ee = vsx.parse_object(_fixture("vsx_ee_cep.json"))
    assert ee["var_type"] == "E-DO"


def test_parse_not_found_is_none():
    assert vsx.parse_object(_fixture("vsx_not_found.json")) is None
    assert vsx.parse_object(b"broken") is None


def test_lookup_uses_the_cache_and_swallows_network_errors(monkeypatch):
    calls = []

    def fake_http_get(key, source, fetch, force=False):
        calls.append(key)
        return _fixture("vsx_t_crb.json"), "application/json"

    monkeypatch.setattr(vsx.db, "http_get", fake_http_get)
    v = vsx.lookup("T CrB")
    assert v["name"] == "T CrB"
    assert calls == ["vsx:object:T CrB"]

    import requests
    def failing(key, source, fetch, force=False):
        raise requests.RequestException("no network")
    monkeypatch.setattr(vsx.db, "http_get", failing)
    assert vsx.lookup("T CrB") is None
```

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_vsx.py -q`
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Core/Sources: AAVSO VSX client with cache + frozen fixtures (ADR-035, subplan V0.8)`
**Estado**: ✅ Hecho (2026-09-11, suite 1022)

---

## V0.9 — `core/sources/surveys.py` (ALeRCE/ZTF)

**Contexto a leer (solo esto)**: tu propio `core/sources/vsx.py` de V0.8
(mismo patrón).
**Precondición**: ninguna. Fixtures ya existentes:
`tests/fixtures/alerce_conesearch_wesb1.json`,
`tests/fixtures/alerce_lightcurve_wesb1.json` (recortada a 40 detecciones
reales + 3 no-detecciones).

**Toca**: `nightscribe/core/sources/surveys.py` (**nuevo**);
`tests/unit/test_surveys.py` (**nuevo**).

**Escribe exactamente esto** — `nightscribe/core/sources/surveys.py`
(cabecera GPL; «Survey light-curve context source (ALeRCE/ZTF)»):

```python
"""Survey photometry context for light curves (V-f): grey reference points
under the observer's own ones, never mixed with them (source="survey:ztf").

Provider: the ALeRCE ZTF API v1 (verified live 2026-09-11). Two cached
calls per object (conesearch -> oid, oid -> lightcurve), TTL 30 days.
Failure returns [] — nothing downstream may break.
"""

import json
import logging

import requests

from ..db import db

logger = logging.getLogger(__name__)

_BASE = "https://api.alerce.online/ztf/v1"
_FID = {1: "g", 2: "r", 3: "i"}      # ZTF band ids


def fetch_points(ra_deg, dec_deg, radius_arcsec=3.0, force=False):
    # ZTF detections near a position, as followup-point shaped dicts.
    # @args: ra_deg/dec_deg - target (degrees), radius_arcsec - match
    #        radius, force - bypass the cache reads
    # @return: [{"mjd", "filter", "mag", "err", "source": "survey:ztf"}]
    oid = _conesearch_oid(ra_deg, dec_deg, radius_arcsec, force=force)
    if not oid:
        return []
    return _to_points(_lightcurve(oid, force=force))


def _get(url, params, cache_key, force):
    # One cached GET; returns the decoded JSON or None on failure.
    def fetch():
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        return r.content, "application/json"
    try:
        body, _ = db.http_get(cache_key, "surveys", fetch, force=force)
        return json.loads(body.decode("utf-8", "replace"))
    except (requests.RequestException, ValueError) as err:
        logger.warning("survey fetch failed (%s): %s", cache_key, err)
        return None


def _conesearch_oid(ra_deg, dec_deg, radius_arcsec, force=False):
    # @return: the oid of the nearest ALeRCE object inside the radius, None
    data = _get(f"{_BASE}/objects/",
                {"ra": ra_deg, "dec": dec_deg, "radius": radius_arcsec,
                 "page_size": 5},
                f"surveys:cone:{ra_deg:.4f}:{dec_deg:.4f}", force)
    items = (data or {}).get("items") or []
    best, best_d = None, None
    for it in items:
        d2 = ((it.get("meanra") or 1e9) - ra_deg) ** 2 \
            + ((it.get("meandec") or 1e9) - dec_deg) ** 2
        if best is None or d2 < best_d:
            best, best_d = it, d2
    return (best or {}).get("oid")


def _lightcurve(oid, force=False):
    # @return: {"detections": [...], "non_detections": [...]} or None
    return _get(f"{_BASE}/objects/{oid}/lightcurve", {},
                f"surveys:lc:{oid}", force)


def _to_points(data):
    # ALeRCE detections -> point dicts. Prefer the corrected PSF mag when
    # its error is valid; fid maps to the ZTF band letter.
    out = []
    for d in (data or {}).get("detections") or []:
        mag, err = d.get("magpsf_corr"), d.get("sigmapsf_corr_ext")
        if mag is None or err is None:
            mag, err = d.get("magpsf"), d.get("sigmapsf")
        if mag is None or d.get("mjd") is None:
            continue
        out.append({"mjd": d["mjd"],
                    "filter": _FID.get(d.get("fid"), str(d.get("fid"))),
                    "mag": mag, "err": err, "source": "survey:ztf"})
    return out
```

**Tests a añadir** — `tests/unit/test_surveys.py` (cabecera GPL; «Unit
tests: ALeRCE survey context (Track V, V0.9)»):

```python
from pathlib import Path

import pytest

from nightscribe.core.sources import surveys

FIX = Path(__file__).resolve().parent.parent / "fixtures"


def _fake_http_get(key, source, fetch, force=False):
    if key.startswith("surveys:cone:"):
        return (FIX / "alerce_conesearch_wesb1.json").read_bytes(), \
            "application/json"
    return (FIX / "alerce_lightcurve_wesb1.json").read_bytes(), \
        "application/json"


def test_fetch_points_happy_path(monkeypatch):
    monkeypatch.setattr(surveys.db, "http_get", _fake_http_get)
    pts = surveys.fetch_points(15.2254, 55.0667)
    assert len(pts) == 40                       # the trimmed fixture
    p = pts[0]
    assert p["source"] == "survey:ztf"
    assert p["filter"] in ("g", "r", "i")
    assert 15.0 < p["mag"] < 18.0               # WeSb 1 in ZTF
    assert p["mjd"] > 58000


def test_fetch_points_network_failure_returns_empty(monkeypatch):
    import requests

    def failing(key, source, fetch, force=False):
        raise requests.RequestException("no network")
    monkeypatch.setattr(surveys.db, "http_get", failing)
    assert surveys.fetch_points(15.2254, 55.0667) == []


def test_to_points_falls_back_to_raw_psf_when_corr_invalid():
    det = {"mjd": 59000.0, "fid": 2, "magpsf": 15.5, "sigmapsf": 0.02,
           "magpsf_corr": None, "sigmapsf_corr_ext": None}
    pts = surveys._to_points({"detections": [det]})
    assert pts == [{"mjd": 59000.0, "filter": "r", "mag": 15.5,
                    "err": 0.02, "source": "survey:ztf"}]
```

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_surveys.py -q`
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Core/Sources: ALeRCE ZTF survey context client (ADR-035, subplan V0.9)`
**Estado**: Pendiente

---

## Cierre de la fase 0

Cuando V0.1–V0.9 estén hechas: `.venv/bin/python -m pytest tests/unit -q`
verde y anota el conteo total aquí: ______ → ______.
