# HADS — Fase A: núcleo (planner + scoring + frases)

> Subplanes A.1–A.3 del plan maestro [../hads-stars.md](../hads-stars.md).
> Un subplan = un commit. Anclas verificadas a HEAD `c607b81`; si una no
> coincide: **parar y reportar**.
> Precondición: Fase 0 hecha (`core/hads.py` con `catalog()`, `derive()`,
> `span_hours()`, `covered_this_month()`, `FAMOUS_HADS`).

---

## A.1 — package-data + planner (`_hads_targets`, gate 1 ciclo)

**Lee primero**: `nightscribe/core/planner.py` completo (409 líneas): `PHASES`
(:28), stages (:50-69), `_visibility` (:104-167), `_transit_targets`
(:374-396), `_transit_plate_scale` (:364-371), filtro genérico (:75-78).

**Toca**: `pyproject.toml`; `nightscribe/core/planner.py`;
`tests/unit/test_hads_planner.py` (**nuevo**).

**Implementa**:
1. `pyproject.toml` (:57-58), globs no recursivos → ambos patrones:
   ```toml
   [tool.setuptools.package-data]
   "nightscribe.gui" = ["ui/*.ui", "i18n/*.qm"]
   "nightscribe" = ["assets/*", "assets/hads-coverage/*"]
   ```
2. `planner.py:28`:
   `PHASES = ("neo", "sn", "comet", "pccp", "transit", "hads", "approach", "scoring")`
   — la etiqueta GUI llega en B.1; mientras tanto el mapa cae al fallback
   `phases.get(key, key)` (main_window.py:863), aceptable en rama.
3. Stages (:50-69): nueva tupla `(6, "hads", ...)` y `approach` pasa a `7`:
   ```python
   (6, "hads",
    lambda: _hads_targets(lat, lon, date, hor, limit_mag, margin,
                          _transit_plate_scale(cfg))),
   (7, "approach",
    lambda: _approach_alerts()),
   ```
4. `from . import coords, dates, exposure, hads, horizon, transits` (:18).
5. `_hads_targets(lat, lon, date, hor, limit_mag=20.0, margin=0.0,
   plate_scale_arcsec_px=None)` tras `_transit_targets` (:396):
   ```python
   for star in hads.catalog():
       mag_med = (star["max"] + star["min"]) / 2     # H-e: median gate
       if mag_med > limit_mag:
           continue
       vis = _visibility(star["ra_deg"], star["dec_deg"], lat, lon, date,
                         hor, margin, star["period_h"] * 2 * 3600)  # 2P (H-a)
       span = hads.span_hours(vis["window_start"], vis["window_end"])
       if span is None or span < star["period_h"]:   # gate: >= 1 contiguous cycle
           continue
       d = hads.derive(star, vis["hours_up"], plate_scale_arcsec_px)
       d["session_fits"] = vis["safe_window"] is not None
       d["covered_this_month"] = hads.covered_this_month(star)
       out.append({
           "id": star["name"], "kind": "hads", "name": star["name"],
           "mag": mag_med, "ra_deg": star["ra_deg"], "dec_deg": star["dec_deg"],
           **vis,
           "hads": {"period_h": star["period_h"], "max": star["max"],
                    "min": star["min"], "amp": d["amp"],
                    "cycles": d["cycles"], "cadence_s": d["cadence_s"],
                    "session_req_h": d["session_req_h"],
                    "session_fits": d["session_fits"], "exp_s": d["exp_s"],
                    "priority": star.get("priority"),
                    "observed": star.get("observed"),
                    "multiperiodic": star.get("multiperiodic"),
                    "non_radial": star.get("non_radial"),
                    "covered_this_month": d["covered_this_month"]},
       })
   ```
   `vis` aporta `max_alt/safe_max_alt/max_time/hours_up/window_start/
   window_end/safe_window/best_time/latest_safe_start` (ADR-020 en un solo
   sitio). El filtro genérico (:75-78) ya exige `window_start` no None.
6. Comentario de sección sobre `_hads_targets`: qué es una HADS y por qué el
   gate es «span contiguo ≥ 1 ciclo» (H-a), referencia al plan.

Tests `tests/unit/test_hads_planner.py`:
`monkeypatch.setattr("nightscribe.core.hads.catalog", fake_list)`; sitio fijo
(lat=28.3, lon=-16.5, date=2026-09-11, FlatHorizon 30°). Estrellas fabricadas:
(a) circumpolar `dec=+85`, P=2 h → aparece, `cycles > 1`, `session_fits True`;
(b) `dec=-70` → nunca visible → excluida; (c) visible pero P=12 h →
span < P → excluida por el gate; (d) `mag_med=15.5` con `limit_mag=14` →
excluida. Aserciones de forma (sub-dict `hads`, campos) y `cycles ==
hours_up / P`.

**Hecho cuando**: tests verdes; suite unitaria verde (N→M);
`python -c "from nightscribe.core import planner; print(planner.PHASES)"`
muestra `hads`.
**Commit**: `Core: HADS night-planner phase + 1-cycle visibility gate + assets packaging (ADR-034, subplan A.1)`
**Estado**: pendiente

---

## A.2 — Scoring (las cuatro familias)

**Lee primero**: `nightscribe/core/suggest.py:1-226` y
`tests/unit/test_suggest_transit.py` (fábrica `_transit()` :28-43, `_Cfg`
:46-52) — el test nuevo es su espejo.

**Toca**: `nightscribe/core/suggest.py`;
`tests/unit/test_suggest_hads.py` (**nuevo**).

**Implementa** en `suggest.py` (añadir `hads` al import de :17):
1. `_scientific`, tras la rama transit (:48-50):
   ```python
   if kind == "hads":
       h = t.get("hads") or {}
       return (_clamp((h.get("amp") or 0.0) / 0.9 * 20, 0, 20) +
               _clamp((18 - (t.get("mag") or 99)) / 10.0 * 15, 0, 15))
   ```
2. `_observability`, tras el bloque transit (:86-89), antes del Moon penalty
   (:90):
   ```python
   if t.get("kind") == "hads":
       h = t.get("hads") or {}
       score += _clamp((h.get("cycles") or 0) / 5.0 * 6, 0, 6)
       if h.get("session_fits") is False:   # patrón baseline_fits
           score -= 4.0
   ```
3. `_urgency`, tras transit (:185-187):
   ```python
   elif kind == "hads":
       h = t.get("hads") or {}
       color = {"period_change": 12,
                "period_change_possible": 8}.get(h.get("priority"), 0)
       unobserved = 6 if h.get("observed") is False else 0
       coverage = 10 if h.get("covered_this_month") is False else 0
       score += max(color, unobserved, coverage)  # signals don't stack: the
                                                  # strongest one rules (H-i/k/m)
   ```
4. `_hook`, tras transit (:217-222):
   ```python
   elif kind == "hads":
       h = t.get("hads") or {}
       if t.get("name") in hads.FAMOUS_HADS:
           score += 6
       if (h.get("amp") or 0) >= 0.5:
           score += 4
       if h.get("multiperiodic"):
           score += 3
   ```

Tests `test_suggest_hads.py`: fábrica `_hads(**over)` con sub-dict completo +
`_Cfg` stub. Casos: amp grande > pequeña; brillante > débil; bonus cycles;
penalización `session_fits=False`; urgencias (rojo 12 > naranja 8; cobertura
10; azul 6; **rojo+cobertura = 12, no 22** — max, no suma); hook
famosa/amp≥0.5/multi; caps 35/30/20/15.

**Hecho cuando**: tests verdes; suite verde (N→M).
**Commit**: `Core: HADS scoring branches in suggest (ADR-034, subplan A.2)`
**Estado**: pendiente

---

## A.3 — Fragmentos ES/EN («por qué esta noche»)

**Lee primero**: `nightscribe/core/suggest.py:272-433` (`_fragments`,
`why_phrase`); `tests/unit/test_best_per_kind.py` (`_t()` :27-30).

**Toca**: `nightscribe/core/suggest.py`; `tests/unit/test_suggest_hads.py`
(continúa); `tests/unit/test_best_per_kind.py`.

**Implementa**: rama `elif kind == "hads":` en `_fragments` (tras transit,
antes de alert :407), **en este orden** (why_phrase toma las 3 primeras —
las señales de prioridad van delante):

```python
elif kind == "hads":
    h = t.get("hads") or {}
    pr = h.get("priority")
    if pr == "period_change":
        frags.append(("Se le han detectado cambios de periodo: cada curva nueva cuenta (programa de P. Wils)",
                       "Period changes detected: every new light curve counts (P. Wils' programme)"))
    elif pr == "period_change_possible":
        frags.append(("Posible cambio de periodo: el programa de seguimiento de P. Wils la marca como prioritaria",
                       "Possible period change: P. Wils' monitoring programme flags it as a priority"))
    if h.get("observed") is False:
        frags.append(("Aún no observada en el programa de seguimiento: serías de los primeros en medirla",
                       "Not yet observed in the monitoring programme: you'd be among the first to measure it"))
    if h.get("covered_this_month") is False:
        frags.append(("Nadie la ha medido este mes: tu curva cubre el hueco",
                       "Nobody has measured it this month: your curve fills the gap"))
    cyc = h.get("cycles")
    if cyc and cyc >= 1:
        frags.append((f"Caben {cyc:.1f} ciclos completos esta noche: la verás pulsar en directo",
                       f"{cyc:.1f} full cycles fit tonight: you'll watch it pulsate live"))
    per, amp = h.get("period_h"), h.get("amp")
    if per and amp:
        frags.append((f"Pulsa con un periodo de {per:.2f} h y una amplitud de {amp:.1f} mag",
                       f"It pulsates with a {per:.2f}-hour period and a {amp:.1f}-mag amplitude"))
    if h.get("multiperiodic"):
        frags.append(("Multiperiódica: obsérvala en noches consecutivas para separar los modos",
                       "Multiperiodic: observe it on consecutive nights to separate the modes"))
    if h.get("non_radial"):
        frags.append(("Muestra modos no radiales, un caso raro entre las HADS",
                       "It shows non-radial modes, a rare case among HADS stars"))
    if h.get("session_fits") is False:
        frags.append(("⚠ No caben 2 ciclos completos de seguida esta noche: captura lo máximo posible",
                       "⚠ Two full consecutive cycles don't fit tonight: capture as much as possible"))
```

Tests: presencia de cada fragmento por flag; orden (prioridad antes que
ciclos); pares ES/EN; `why_phrase` ≤ 3 fragmentos y termina en punto. En
`test_best_per_kind.py`: añadir una tupla hads con `_t()` (el comentario
«the other six» pasa a siete kinds).

**Hecho cuando**: tests verdes; suite verde (N→M).
**Commit**: `Core: HADS why-tonight phrases ES/EN (ADR-034, subplan A.3)`
**Estado**: pendiente
