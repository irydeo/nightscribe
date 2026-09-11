# Track V — Fase A: núcleo (fase planner `campaigns` + scoring + frases)

> Subplanes VA.1–VA.4 del plan maestro
> [../variables-campaigns.md](../variables-campaigns.md). Un subplan = un
> commit. Anclas verificadas a HEAD `4b7635a`; si una no coincide: **parar y
> reportar**. Lee antes `LEEME.md`.
> Precondición de la fase: V0.1–V0.7 hechas (V0.8 la necesita VB.6, no aquí).

---

## VA.1 — Planner: fase `campaigns` (target básico)

**Contexto a leer (solo esto)**: `nightscribe/core/planner.py:18-29`
(imports y `PHASES`), `:51-82` (stages y filtro genérico), `:403-441`
(`_hads_targets`, el molde).
**Precondición**: V0.3, V0.4.

**Toca**: `nightscribe/core/planner.py`;
`tests/unit/test_planner_campaigns.py` (**nuevo**).

**Escribe exactamente esto**:

1. `planner.py:18` →
   ```python
   from . import campaign, coords, dates, exposure, hads, horizon, transits
   ```
2. `planner.py:28-29` →
   ```python
   PHASES = ("neo", "sn", "comet", "pccp", "transit", "hads", "campaigns",
             "approach", "scoring")
   ```
3. Stages (:51-73): tras la tupla `(6, "hads", ...)`, inserta la fase nueva
   y renumera `approach` a 8:
   ```python
           (7, "campaigns",
            lambda: _campaign_targets(cfg, lat, lon, date, hor, margin)),
           (8, "approach",
            lambda: _approach_alerts()),
   ```
4. Nueva función tras `_hads_targets` (tras :441):

```python
def _campaign_targets(cfg, lat, lon, date, hor, margin, db_obj=None):
    # Tonight from the observer's own commitments (ADR-035, V-d): the due
    # projects of the active campaigns. Fully local (SQLite + sky maths) —
    # no network, and nothing breaks without one. Each target re-surfaces
    # an EXISTING project, so the Explore CTA will offer "Continue
    # project" (phase E machinery, gui/main_window.py).
    # @args: db_obj - Database (tests inject a temp one; default: shared)
    if db_obj is None:
        from .db import db as db_obj
    limit_mag = float(cfg.get("limit_mag", 20.0))
    out = []
    for due in campaign.due_campaigns(db_obj):
        camp, proj = due["campaign"], due["project"]
        ctx = proj.get("context") or {}
        ra, dec = ctx.get("ra_deg"), ctx.get("dec_deg")
        if ra is None or dec is None:
            logger.debug("campaign %s: project %s has no coordinates",
                         camp["name"], proj["object_name"])
            continue
        mag = ctx.get("mag")
        try:
            mag = float(mag) if mag is not None else None
        except (TypeError, ValueError):
            mag = None
        if mag is not None and mag > limit_mag:
            continue           # known brightness: hard gate (SN-style, ADR-025)
        vis = _visibility(ra, dec, lat, lon, date, hor, margin)
        if vis.get("window_start") is None:
            continue           # not up tonight
        out.append({
            "id": proj["object_name"], "kind": proj["kind"],
            "name": proj["object_name"], "mag": mag,
            "ra_deg": ra, "dec_deg": dec, "project_id": proj["id"],
            **vis,
            "campaign": {"id": camp["id"], "name": camp["name"],
                         "overdue_days": due["overdue_days"],
                         "cadence_nights": due["cadence_nights"],
                         "never_visited": due["never_visited"],
                         "event": None},
        })
    return out
```

**Tests a añadir** — `tests/unit/test_planner_campaigns.py` (cabecera GPL;
«Unit tests: campaigns planner phase (Track V, VA.1)»):

```python
import datetime
import time

import pytest

from nightscribe.core import campaign, followup, horizon, planner, project
from nightscribe.core.db import Database

LAT, LON = 28.3, -16.5          # Irydeo-ish site
DATE = datetime.date(2026, 9, 11)


class _Cfg:
    def __init__(self, limit_mag=14.0):
        self._d = {"limit_mag": limit_mag}

    def get(self, k, default=None):
        return self._d.get(k, default)


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "t.db"))


def _make_due(db, name="T CrB", ra=10.0, dec=80.0, mag=10.0,
              kind="variable", cadence=1, visited_days_ago=None, ctx=None):
    # @return: (campaign_id, project_id) of a campaign + project pair
    cid = campaign.create(db, "Campaña " + name,
                          protocol={"cadence_nights": cadence})
    full_ctx = {"ra_deg": ra, "dec_deg": dec, "mag": mag}
    full_ctx.update(ctx or {})
    p = project.create(db, kind, name, full_ctx, campaign_id=cid)
    if visited_days_ago is not None:
        followup.create_session(db, p["id"])
        sid = followup.list_sessions(db, p["id"])[0]["id"]
        db.execute("UPDATE project_sessions SET created=? WHERE id=?",
                   (time.time() - visited_days_ago * 86400, sid))
        db.commit()
    return cid, p["id"]


def _targets(db, limit_mag=14.0):
    return planner._campaign_targets(_Cfg(limit_mag), LAT, LON, DATE,
                                     horizon.FlatHorizon(10.0), 0.0,
                                     db_obj=db)


def test_phases_include_campaigns_before_approach():
    assert "campaigns" in planner.PHASES
    assert planner.PHASES.index("campaigns") < \
        planner.PHASES.index("approach")


def test_due_campaign_project_is_listed(db):
    _make_due(db)                            # never visited -> due
    out = _targets(db)
    assert len(out) == 1
    t = out[0]
    assert t["kind"] == "variable" and t["id"] == "T CrB"
    assert t["project_id"] is not None
    assert t["campaign"]["name"] == "Campaña T CrB"
    assert t["campaign"]["never_visited"] is True
    assert t["campaign"]["event"] is None
    assert t["window_start"] is not None


def test_up_to_date_campaign_is_not_listed(db):
    _make_due(db, cadence=3, visited_days_ago=0)
    assert _targets(db) == []


def test_not_visible_tonight_is_excluded(db):
    _make_due(db, dec=-70.0)                 # never up from lat 28.3
    assert _targets(db) == []


def test_magnitude_gate(db):
    _make_due(db, mag=15.5)
    assert _targets(db, limit_mag=14.0) == []
    assert len(_targets(db, limit_mag=16.0)) == 1


def test_missing_coordinates_are_skipped(db):
    cid = campaign.create(db, "C")
    project.create(db, "variable", "NoCoords", {}, campaign_id=cid)
    assert _targets(db) == []


def test_no_campaigns_no_targets(db):
    assert _targets(db) == []
```

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_planner_campaigns.py -q`
**Hecho cuando**: verde; suite verde (N→M). (El label de progreso GUI llega
en VB.2; mientras tanto cae al fallback `phases.get(key, key)` —
`main_window.py:894` — aceptable en rama.)
**Commit**: `Core: campaigns night-planner phase — due projects as Tonight targets (ADR-035, subplan VA.1)`
**Estado**: ✅ Hecho (2026-09-11, suite 1025→1032)

---

## VA.2 — Planner: sub-dict `variable` + flag de evento

**Contexto a leer (solo esto)**: tu `_campaign_targets` de VA.1;
`nightscribe/core/variables.py` (V0.5-V0.7).
**Precondición**: VA.1, V0.5, V0.7.

**Toca**: `nightscribe/core/planner.py`;
`tests/unit/test_planner_campaigns.py` (ampliar).

**Escribe exactamente esto**:

1. `planner.py:18` (quedó en VA.1) →
   ```python
   from . import campaign, coords, dates, exposure, followup, hads, horizon
   from . import transits, variables
   ```
2. En `_campaign_targets`, sustituye el bloque `out.append({...})` por:

```python
        t = {
            "id": proj["object_name"], "kind": proj["kind"],
            "name": proj["object_name"], "mag": mag,
            "ra_deg": ra, "dec_deg": dec, "project_id": proj["id"],
            **vis,
            "campaign": {"id": camp["id"], "name": camp["name"],
                         "overdue_days": due["overdue_days"],
                         "cadence_nights": due["cadence_nights"],
                         "never_visited": due["never_visited"],
                         "event": None},
        }
        # variable sub-dict: the context snapshot + tonight's fresh values
        # (the next extremum is computed nightly — pure local maths)
        v = dict(ctx.get("variable") or {})
        if v:
            if v.get("amp") is None and v.get("max") is not None \
                    and v.get("min") is not None:
                v["amp"] = round(v["min"] - v["max"], 2)  # inverted axis
            v["next_extremum"] = variables.next_extremum(
                v.get("period_d"), v.get("epoch_mjd"),
                var_type=v.get("var_type", ""))
            t["variable"] = v
        # event advisor (V-h): a dip/outburst in the observer's own points
        # rides on the target so suggest can boost and phrase it
        ev = variables.detect_event(
            followup.list_points(db_obj, proj["id"]),
            threshold=float(cfg.get("event_mag_threshold", 0.5)))
        if ev:
            t["campaign"]["event"] = ev
        out.append(t)
```

**Tests a añadir** (al final de `tests/unit/test_planner_campaigns.py`):

```python
def test_variable_subdict_with_fresh_extremum(db):
    _make_due(db, ctx={"variable": {"var_type": "M", "period_d": 300.0,
                                    "epoch_mjd": 60000.0, "max": 9.0,
                                    "min": 13.5, "spectral": "M6e"}})
    t = _targets(db)[0]
    v = t["variable"]
    assert v["amp"] == 4.5                       # min - max (inverted axis)
    assert v["next_extremum"]["kind"] in ("max", "min")
    assert v["next_extremum"]["days"] >= 0


def test_event_flag_from_own_points(db):
    _cid, pid = _make_due(db)
    for i, m in enumerate((12.0, 12.1, 11.9, 12.0, 12.9)):
        followup.add_point(db, pid, 61000.0 + i, "V", m)
    t = _targets(db)[0]
    assert t["campaign"]["event"]["direction"] == "drop"


def test_no_variable_no_subdict(db):
    _make_due(db)
    assert "variable" not in _targets(db)[0]
```

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_planner_campaigns.py -q`
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Core: campaign targets carry variable sub-dict + event flag (ADR-035, subplan VA.2)`
**Estado**: ✅ Hecho (2026-09-11, suite 1032→1035)

---

## VA.3 — `suggest`: scoring de objetivos de campaña

**Contexto a leer (solo esto)**: `nightscribe/core/suggest.py:35-57`
(`_scientific`), `:175-209` (`_urgency`), `:212-255` (`_hook`).
**Precondición**: VA.2.

**Toca**: `nightscribe/core/suggest.py`;
`tests/unit/test_suggest_campaign.py` (**nuevo**).

**Escribe exactamente esto**:

1. `_scientific` (:35-57): antes del `return 0` final, añade:
   ```python
       if kind == "variable":
           # a campaign membership is itself the science signal (someone
           # with a goal asked for this star); amplitude and brightness make
           # the measurement easier
           v = t.get("variable") or {}
           return (_clamp((v.get("amp") or 0.0) / 3.0 * 15, 0, 15) +
                   _clamp((18 - (t.get("mag") or 99)) / 10.0 * 15, 0, 15))
   ```
2. `_urgency` (:175-209): tras el bloque `elif kind == "hads":` (:201-208) y
   antes del `return _clamp(score, 0, 20)`, añade (sin `elif`: la campaña es
   **ortogonal al kind** y se suma a la urgencia propia del tipo):
   ```python
       c = t.get("campaign") or {}
       if c:
           # the group's own commitment: cadence lapsed + event advisor (V-h)
           score += _clamp((c.get("overdue_days") or 0) * 3, 0, 15)
           if c.get("event"):
               score += 10
   ```
3. `_hook` (:212-255): tras el bloque `elif kind == "hads":` (:243-250),
   añade:
   ```python
       elif kind == "variable":
           v = t.get("variable") or {}
           days = (v.get("next_extremum") or {}).get("days")
           if days is not None and days <= 7:
               score += 5            # an extremum within the week is a hook
           if (v.get("amp") or 0) >= 2.0:
               score += 3
   ```

**Tests a añadir** — `tests/unit/test_suggest_campaign.py` (cabecera GPL;
«Unit tests: campaign target scoring (Track V, VA.3)»):

```python
import pytest

from nightscribe.core import suggest


class _Cfg:
    def __init__(self, **kw):
        self._d = {"limit_mag": 20.0, "moon_limit_enabled": False}
        self._d.update(kw)

    def get(self, k, default=None):
        return self._d.get(k, default)


def _var(**over):
    t = {"id": "T CrB", "kind": "variable", "name": "T CrB", "mag": 10.1,
         "ra_deg": 239.9, "dec_deg": 25.9,
         "max_alt": 60.0, "safe_max_alt": 58.0, "hours_up": 6.0,
         "window_start": "2026-09-11T22:00", "window_end": "2026-09-12T04:00",
         "variable": {"var_type": "NR", "period_d": 227.55,
                      "epoch_mjd": 55828.4, "max": 2.0, "min": 10.8,
                      "amp": 8.8, "next_extremum": None},
         "campaign": {"id": 1, "name": "Campaña T CrB", "overdue_days": 0,
                      "cadence_nights": 1, "never_visited": False,
                      "event": None}}
    t.update(over)
    return t


def _parts(t):
    _score, parts = suggest.score_target(t, _Cfg())
    return parts


def test_variable_scientific_uses_amp_and_brightness():
    bright = _var()
    faint = _var(mag=15.0)
    no_amp = _var(variable={"amp": 0.0, "next_extremum": None})
    assert _parts(bright)["scientific"] > _parts(faint)["scientific"]
    assert _parts(bright)["scientific"] > _parts(no_amp)["scientific"]
    assert _parts(bright)["scientific"] <= 35


def test_campaign_urgency_grows_with_overdue_and_caps():
    c1 = dict(_var()["campaign"], overdue_days=1)
    c5 = dict(_var()["campaign"], overdue_days=5)
    c99 = dict(_var()["campaign"], overdue_days=99)
    assert _parts(_var(campaign=c5))["urgency"] > \
        _parts(_var(campaign=c1))["urgency"]
    assert _parts(_var(campaign=c99))["urgency"] == 20


def test_event_adds_urgency():
    c = dict(_var()["campaign"])
    c["event"] = {"direction": "drop", "delta_mag": 0.8, "filter": "V"}
    assert _parts(_var(campaign=c))["urgency"] == \
        _parts(_var())["urgency"] + 10


def test_extremum_hook():
    v = dict(_var()["variable"])
    v["next_extremum"] = {"kind": "max", "mjd": 61250.0, "days": 3.0}
    assert _parts(_var(variable=v))["hook"] > _parts(_var())["hook"]


def test_campaign_signals_stack_on_other_kinds():
    # a campaign SN keeps its own urgency AND wins the campaign boost (V-b)
    sn = {"id": "SN 2026abc", "kind": "sn", "name": "SN 2026abc",
          "mag": 14.0, "ra_deg": 10.0, "dec_deg": 20.0,
          "max_alt": 50.0, "safe_max_alt": 49.0, "hours_up": 4.0,
          "window_start": "2026-09-11T23:00", "window_end": "2026-09-12T03:00",
          "disc_date": None,
          "campaign": dict(_var()["campaign"], overdue_days=4)}
    plain = dict(sn)
    plain.pop("campaign")
    assert _parts(sn)["urgency"] > _parts(plain)["urgency"]
```

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_suggest_campaign.py -q`
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Core: campaign target scoring in suggest (ADR-035, subplan VA.3)`
**Estado**: ✅ Hecho (2026-09-11, suite 1035→1040; desviación: a `_urgency` se sumó un
`score += 5` base por pertenecer a una campaña — el test propio de la tarjeta
espera `urgency == 20` con `overdue=99`, imposible solo con el clamp 0-15;
con el +5 base el cap queda 5+15=20 y `test_event_adds_urgency` sigue pasando)

---

## VA.4 — `suggest`: fragmentos ES/EN de campaña

**Contexto a leer (solo esto)**: `nightscribe/core/suggest.py:301-308`
(cabecera de `_fragments`) y `:469-495` (rama alert, cierre y `why_phrase`).
**Precondición**: VA.3.

**Toca**: `nightscribe/core/suggest.py`;
`tests/unit/test_suggest_campaign.py` (ampliar).

**Escribe exactamente esto**:

1. Nueva función tras `_fragments` (tras el `return frags` de :482, antes de
   `why_phrase` :485)... **OJO**: primero cambia ese `return frags` final de
   `_fragments` por:
   ```python
       return _campaign_fragments(t) + frags
   ```
   (las señales de campaña **encabezan**: `why_phrase` conserva las tres
   primeras — la campaña es la razón de que el objetivo esté en la lista).
2. Y a continuación, la función nueva (textos literales, no los cambies):

```python
def _campaign_fragments(t):
    # Campaign signals, heaviest first (ADR-035). They lead the why-phrase:
    # the campaign is the reason the target is listed at all (V-d).
    # @args: t - target dict with a "campaign" sub-dict (maybe empty)
    # @return: list of (es, en) fragment pairs
    c = t.get("campaign") or {}
    if not c:
        return []
    frags = []
    ev = c.get("event") or {}
    if ev:
        d = ev.get("delta_mag") or 0.0
        if ev.get("direction") == "drop":
            frags.append((f"¡Posible descenso de brillo (Δ≈+{d:.1f} mag en tu última medida)! El protocolo pide subir la cadencia",
                          f"Possible brightness drop (Δ≈+{d:.1f} mag on your latest point)! The protocol calls for a higher cadence"))
        else:
            frags.append((f"¡Posible erupción o subida de brillo (Δ≈−{d:.1f} mag)! Máxima prioridad esta noche",
                          f"Possible outburst (Δ≈−{d:.1f} mag)! Top priority tonight"))
    if c.get("never_visited"):
        frags.append((f"Campaña {c['name']}: sin ninguna visita todavía — la primera medida abre la serie",
                      f"Campaign {c['name']}: no visits yet — the first measurement opens the series"))
    elif c.get("overdue_days"):
        frags.append((f"Campaña {c['name']}: {c['overdue_days']} noches sin medida (cadencia: {c['cadence_nights']})",
                      f"Campaign {c['name']}: {c['overdue_days']} nights without a measurement (cadence: {c['cadence_nights']})"))
    v = t.get("variable") or {}
    nxt = v.get("next_extremum") or {}
    if nxt.get("days") is not None:
        if nxt.get("kind") == "max":
            frags.append((f"Máximo esperado en ~{nxt['days']:.0f} días",
                          f"Maximum expected in ~{nxt['days']:.0f} days"))
        else:
            frags.append((f"Mínimo esperado en ~{nxt['days']:.0f} días",
                          f"Minimum expected in ~{nxt['days']:.0f} days"))
    if v.get("period_d"):
        frags.append((f"Varía con un periodo de {v['period_d']:.1f} días",
                      f"It varies with a {v['period_d']:.1f}-day period"))
    return frags
```

**Tests a añadir** (al final de `tests/unit/test_suggest_campaign.py`):

```python
def _frags(t):
    return suggest._fragments(t, _Cfg())


def test_campaign_fragments_lead():
    t = _var(campaign=dict(_var()["campaign"], overdue_days=4))
    frags = _frags(t)
    assert frags and "Campaña T CrB" in frags[0][0]
    assert "4 noches sin medida" in frags[0][0]
    assert "Campaign T CrB" in frags[0][1]


def test_event_fragment_goes_first():
    c = dict(_var()["campaign"], overdue_days=4,
             event={"direction": "drop", "delta_mag": 0.8, "filter": "V"})
    frags = _frags(_var(campaign=c))
    assert frags[0][0].startswith("¡Posible descenso")
    assert frags[1][0].startswith("Campaña")


def test_never_visited_fragment():
    c = dict(_var()["campaign"], never_visited=True)
    assert "sin ninguna visita" in _frags(_var(campaign=c))[0][0]


def test_extremum_and_period_fragments():
    v = dict(_var()["variable"])
    v["next_extremum"] = {"kind": "max", "mjd": 61250.0, "days": 3.0}
    txt = " · ".join(f[0] for f in _frags(_var(variable=v)))
    assert "Máximo esperado en ~3 días" in txt
    assert "periodo de 227.6 días" in txt


def test_why_phrase_keeps_at_most_three_and_ends_with_period():
    c = dict(_var()["campaign"], overdue_days=4,
             event={"direction": "rise", "delta_mag": 1.2, "filter": "V"})
    v = dict(_var()["variable"])
    v["next_extremum"] = {"kind": "min", "mjd": 61252.0, "days": 5.0}
    phrase = suggest.why_phrase(_var(campaign=c, variable=v), _Cfg())
    assert phrase["es"].endswith(".") and phrase["en"].endswith(".")
    assert phrase["es"].count("·") <= 2
```

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_suggest_campaign.py -q`
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Core: campaign why-tonight phrases ES/EN (ADR-035, subplan VA.4)`
**Estado**: ✅ Hecho (2026-09-11, suite 1040→1045; desviación: el fixture `_var` usaba
`name="Campaña T CrB"` pero el test espera `"Campaign T CrB"` en la rama EN —
la única lectura coherente es que `c["name"]` sea el nombre del objetivo y la
plantilla aporte la etiqueta `Campaña`/`Campaign`; corregido el fixture a
`name="T CrB"`. Los templates de `suggest.py` son literales, como pide el card)

---

## Cierre de la fase A

Cuando VA.1–VA.4 estén hechas: `.venv/bin/python -m pytest tests/unit -q`
verde y anota el conteo total aquí: 1025 → 1045. ✅ Hecho (2026-09-11).
