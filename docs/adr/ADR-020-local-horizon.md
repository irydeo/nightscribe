# ADR-020: Local horizon and observing constraints

**Estado / Status**: Accepted · **Fecha / Date**: 2026-08-24

## Español

**Contexto**: el planificador solo conoce un plano uniforme `min_alt` (30° por defecto).
El observatorio real tiene paredes y un **horizonte de seguridad ya construido en
TheSkyX** que conviene reutilizar. Además no existe ninguna restricción de Luna en
planificación/scoring, ni se comprueba que una sesión de exposiciones **termine antes**
de que el objeto cruce el horizonte (requisito de seguridad del usuario).

**Decisión**:

1. **`core/horizon.py` — horizonte por azimut.** El parser se escribe contra el
   **fichero real exportado de TheSkyX** del usuario (lo compartirá al empezar la fase
   2; si no fuera exportable, formato texto `az alt` estándar, compatible con el
   «custom horizon» de NINA). Interpolación lineal `alt_at(az)`; **fallback** al
   `min_alt` plano si no hay fichero configurado; margen de seguridad configurable
   (`horizon_margin_deg`, por defecto 0). Config: `horizon_file` (ruta).
2. **Luna**: restricción configurable (`moon_limit_enabled`, `moon_max_illum`,
   `moon_min_sep_deg`) usando la posición/iluminación de `ephem_minor` (ADR-009).
   Es **aviso + penalización del score** de observability, **no filtro duro**: el
   usuario decide.
3. **Viabilidad de sesión**: la ventana del objeto sobre el horizonte real debe cubrir
   la duración estimada de la sesión (ADR-021); Esta noche muestra **«inicio seguro
   hasta HH:MM»** y el paso Plan avisa si la sesión terminaría fuera de seguridad.
4. **`limit_mag` consistente**: se elimina el corte 14.0 hard-codeado de
   `transits.transits_tonight`; todas las familias usan la config.

**Consecuencias**: `planner._visibility`/`visible_now` consultan `horizon.alt_at(az)`
en vez del plano; `suggest.score_target` incorpora la penalización lunar y la
viabilidad; `viz/sky_view` dibuja la silueta del horizonte real bajo la curva de
altura; Settings gana los grupos «Horizonte» (importar fichero, vista previa, margen)
y «Luna». Tests unitarios con el fichero real del usuario como fixture.

## English

**Context**: the planner only knows a flat `min_alt` plane (30° default). The real
observatory has walls and a **safety horizon already built in TheSkyX** worth reusing.
There is also no Moon constraint in planning/scoring, and no check that an exposure
session **ends before** the object crosses the horizon (a user safety requirement).

**Decision**:

1. **`core/horizon.py` — horizon by azimuth.** The parser is written against the
   user's **real TheSkyX export file** (to be shared when phase 2 starts; if not
   exportable, standard `az alt` text format, compatible with NINA's "custom horizon").
   Linear interpolation `alt_at(az)`; **fallback** to the flat `min_alt` when no file
   is configured; configurable safety margin (`horizon_margin_deg`, default 0).
   Config: `horizon_file` (path).
2. **Moon**: configurable constraint (`moon_limit_enabled`, `moon_max_illum`,
   `moon_min_sep_deg`) using `ephem_minor` position/illumination (ADR-009). It is a
   **warning + observability score penalty, not a hard filter**: the user decides.
3. **Session feasibility**: the object's window above the real horizon must cover the
   estimated session duration (ADR-021); Tonight shows **"safe start until HH:MM"** and
   the Plan step warns if the session would end outside the safety range.
4. **Consistent `limit_mag`**: the hard-coded 14.0 cut in `transits.transits_tonight`
   goes away; every family uses the config value.

**Consequences**: `planner._visibility`/`visible_now` query `horizon.alt_at(az)`
instead of the plane; `suggest.score_target` adds the Moon penalty and feasibility;
`viz/sky_view` draws the real horizon silhouette under the altitude curve; Settings
gains "Horizon" (import file, preview, margin) and "Moon" groups. Unit tests use the
user's real file as a fixture.
