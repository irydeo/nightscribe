# HADS — Fase C: proyectos y narrativa

> Subplanes C.1–C.3 del plan maestro [../hads-stars.md](../hads-stars.md).
> Un subplan = un commit. Anclas verificadas a HEAD `c607b81`; si una no
> coincide: **parar y reportar**.

---

## C.1 — Proyectos hads (`VALID_KINDS`/`OUTCOMES`/CLI)

**Lee primero**: `nightscribe/core/project.py` (`VALID_KINDS` :33, `OUTCOMES`
:49-56, `STEPS` :32); `nightscribe/gui/main_window.py` — mapa de outcomes
(:55), `_create_project` (gate :4114, whitelist ctx :4118-4127);
`nightscribe/__main__.py:343-345` (help de `project create --kind`).

**Toca**: `core/project.py`, `gui/main_window.py`, `__main__.py`; tests
`test_project.py`; i18n.

**Implementa**:
1. `project.py:33`: `VALID_KINDS = ("sn", "neo", "comet", "pccp", "transit",
   "hads")`. `:49-56`: `OUTCOMES["hads"] = ("completed", "reported_aavso",
   "abandoned")`. (Sin migración de BD: `projects.kind` no tiene CHECK.)
2. `main_window.py:55` (mapa de etiquetas de outcome, patrón A2): añade
   `reported_aavso` → ES «Reportada a la AAVSO» / EN «Reported to AAVSO»
   (replica la estructura exacta del mapa).
3. Whitelist de ctx (:4118-4127): añade `"hads"` tras `"transit"`.
4. `__main__.py:344-345`: help → `"sn|neo|comet|pccp|transit|hads"`.
5. Tests `test_project.py`: crear proyecto hads; outcomes correctos;
   `close(outcome="reported_aavso")` y `reopen()`; el CLI acepta el kind.
6. i18n (≈2 cadenas: etiqueta de outcome).

**Hecho cuando**: suite verde (N→M) + `test_i18n.py`;
`python -m nightscribe project create --kind hads "CY Aqr"` funciona.
**Commit**: `Core/Gui/CLI: HADS projects with the AAVSO outcome (ADR-034, subplan C.1)`
**Estado**: **Hecho** (962→963). Nota: el mapa `_OUTCOME_LABELS` usa dicts
bilingües en código (no `tr()`), lupdate reporta 0 cadenas nuevas.

---

## C.2 — Narrativa ES/EN (hook, facts, hashtags)

**Lee primero**: `nightscribe/core/narrative.py` — `hook()` (:25-147),
`_transit_hook` (:326-340, patrón del helper), `fact_bullets` (:150-166),
`hashtags` (:416-432); `docs/HADS.md` (referencias [1]-[5] para los textos).

**Toca**: `nightscribe/core/narrative.py`;
`tests/unit/test_narrative_hook.py`.

**Implementa**:
1. `_hads_hook(d)` nueva (espejo de `_transit_hook`), con rama en `hook()`
   antes de `sun` (:98). Texto base (ajústalo al tono de las demás ramas):
   ES: «Es una δ Scuti de gran amplitud: pulsa cada {P:.2f} h y cambia {amp:.1f}
   mag de brillo — esta noche la verás latir en directo.»
   EN: «A high-amplitude δ Scuti: it pulsates every {P:.2f} h and swings
   {amp:.1f} mag — tonight you'll watch it beat live.»
   Si `priority` rojo/naranja → añade la nota del programa de P. Wils; si es
   famosa (`hads.FAMOUS_HADS`) → menciona que es un prototipo de la clase.
2. `fact_bullets`: rama `if kind == "hads": return _hads_facts(d) +
   _safe_window_bullets(d)`. `_hads_facts(d)`: periodo/amplitud/rango;
   modos (fundamental vs overtone, ratio Petersen 0.76–0.78); «antes:
   cefeidas enanas»; AAVSO la recomienda como primer objetivo de fotometría;
   créditos: seguimiento de Patrick Wils (VVS), VSX de AAVSO (refs [1]-[5]
   nombradas; las URLs viven en `docs/HADS.md`, no en la prosa).
3. `hashtags` (:421-431): entrada `"hads"` → `"#VariableStars #HADS #AAVSO"`
   (replica el formato exacto del dict `per_kind`).
4. Tests `test_narrative_hook.py`: hook contiene el periodo y sale en ES/EN;
   facts citan a «Wils»; hashtags incluyen `#VariableStars`.

**Hecho cuando**: tests verdes; suite verde (N→M).
**Commit**: `Core: HADS narrative — hook, fact bullets, hashtags ES/EN (ADR-034, subplan C.2)`
**Estado**: **Hecho** (963→967)

---

## C.3 — Post/tuit (tests)

**Lee primero**: `nightscribe/core/post.py` (`render_post` :24-51, `_tweet`
:54-67 — agnósticos de kind, trabajan sobre narrative);
`tests/unit/test_transits_post.py` (patrón).

**Toca**: `tests/unit/test_hads_post.py` (**nuevo**). (No debería tocar
`post.py`: el render es genérico una vez existe la narrativa; si algo falta,
**parar y reportar**.)

**Implementa** tests con un `e` fabricado (`type: "hads"`, `data.hads` +
contexto de ventana), espejo del de tránsitos: el post ES/EN contiene el
periodo y «pulsa»/«pulsat»; el tuit ≤ 280 caracteres; hashtags incluyen
`#VariableStars`.

**Hecho cuando**: tests verdes; suite verde (N→M).
**Commit**: `Tests: HADS post/tweet rendering (ADR-034, subplan C.3)`
**Estado**: **Hecho** (967→969; `post.py` intacto, como mandaba la tarjeta)
