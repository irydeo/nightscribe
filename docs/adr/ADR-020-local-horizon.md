# ADR-020: Local horizon and observing constraints

**Estado / Status**: Accepted · **Fecha / Date**: 2026-08-24
**Cronológico**: 2026-08-28 — formato canónico verificado contra
`docs/limits-sample.hrz` (fichero real del usuario); se puntualizan los puntos 1 y 3
(formato `.hrz`, prioridad frente a `min_alt`, definición de span seguro). 2026-08-29
— la puerta de visibilidad de transits pasa a "la estrella cruza horizonte + margen en
el instante del tránsito central" (punto 3); la puerta anterior ("uno de los tres
instantes de muestreo sobre el horizonte") admitía transits cuya estrella nunca salía.
La decisión no cambia: la referencia de seguridad es la misma para todas las familias.
2026-08-29 — el término visible «horizonte» pasa a «límite» en la leyenda de `sky_view`,
chips de Tonight/Overview, prosa bilingüe y grupo Settings («Local limit» / «Limit
file»: el ADR-020 ya lo llama «limits file» desde el export TheSkyX). `min_alt` queda
como el suelo plano que solo rige cuando faltan/son inválidos «limits».

## Español

**Contexto**: el planificador solo conoce un plano uniforme `min_alt` (30° por defecto).
El observatorio real tiene paredes y un **horizonte de seguridad ya construido en
TheSkyX** que conviene reutilizar. Además no existe ninguna restricción de Luna en
planificación/scoring, ni se comprueba que una sesión de exposiciones **termine antes**
de que el objeto cruce el horizonte (requisito de seguridad del usuario).

**Decisión**:

1. **`core/horizon.py` — horizonte por azimut.** Formato canónico (verificado el
   2026-08-28 contra `docs/limits-sample.hrz`, el fichero real del usuario): export de
   límites TheSkyX — cabecera `az|alt`, número de muestras (≤360), y una altitud por
   línea (azimut = índice). Se mantiene además el parser de pares `az alt` (NINA).
   Interpolación lineal `alt_at(az)` con envoltura 0/360.
   **Regla de prioridad**: si hay un fichero de horizonte válido, **ese es la referencia
   de seguridad** y Settings lo deja visible desactivando `min_alt` (tooltip: «la
   referencia la da el fichero»); `min_alt` solo se usa cuando falta o es inválido el
   fichero. `horizon_margin_deg` (por defecto 0) se suma sobre la referencia activa.
   Config: `horizon_file` (ruta). Un `.hrz` truncado/roto se **rechaza** (no se degrada
   a 1 punto): `open_reference` avisa y cae a `min_alt`.
2. **Luna**: restricción configurable (`moon_limit_enabled`, `moon_max_illum`,
   `moon_min_sep_deg`) usando la posición/iluminación de `ephem_minor` (ADR-009).
   Es **aviso + penalización del score** de observability, **no filtro duro**: el
   usuario decide.
3. **Viabilidad de sesión**: `safe_spans` enumera los tramos donde el objeto está
   sobre el horizonte (fichero o plano) + margen; `best_span` elige el tramo continuo
   más largo (duración mínima exigida); `best_time` es el inicio recomendado
   (centrado en el pico de altitud, clamp al tramo) y `latest_safe_start = end −
    duración`. Si la duración de la sesión (hub de captura: `frames × (exp + overhead)`)
    no cabe en ningún tramo → **advertencia roja** en tarjeta y chip («NO forzar el
    equipo»); `viz/sky_view` somorea el span seguro (`axvspan`) y marca `best_time`
    (línea «empezar hasta HH:MM»); la prosa ES/EN incluye la ventana y su aviso.
    **Transits** (2026-08-29): misma referencia de seguridad que el resto — la estrella
    debe estar sobre horizonte (fichero o plano) + `horizon_margin_deg` **en el instante
    del tránsito central**, momento en que el planeta cruza; el muestreo de
    entrada/salida (3 instantes) solo informa de la cobertura, ya no decide la puerta.
4. **`limit_mag` consistente**: se elimina el corte 14.0 hard-codeado de
   `transits.transits_tonight`; todas las familias usan la config.

**Consecuencias**: `planner._visibility`/`visible_now` consultan `horizon.alt_at(az)`
en vez del plano; `suggest.score_target` incorpora la penalización lunar y la
viabilidad; `viz/sky_view` dibuja la silueta del límite local real bajo la curva de
altura (leyenda «Límite / Limit» en ambos idiomas, silueta o plano 30°); Settings gana
los grupos «Límite local / Local limit» (importar fichero, vista previa, margen) y
«Luna». Tests unitarios con el fichero real del usuario como fixture.

## English

**Context**: the planner only knows a flat `min_alt` plane (30° default). The real
observatory has walls and a **safety horizon already built in TheSkyX** worth reusing.
There is also no Moon constraint in planning/scoring, and no check that an exposure
session **ends before** the object crosses the horizon (a user safety requirement).

**Decision**:

1. **`core/horizon.py` — horizon by azimuth.** Canonical format (verified on 2026-08-28
   against `docs/limits-sample.hrz`, the user's real file): TheSkyX limits export —
   `az|alt` header, sample count (≤360), then one altitude per line (azimuth = index).
   The `az alt` pairs parser (NINA) is kept too. Linear `alt_at(az)` with 0/360
   wrapping. **Priority rule**: if a valid horizon file exists, **it is the safety
   reference** and Settings reflects that by disabling `min_alt` (tooltip: «the file is
   the reference»); `min_alt` is only used when the file is missing or invalid.
   `horizon_margin_deg` (default 0) is added on top of the active reference.
   Config: `horizon_file` (path). A truncated/corrupt `.hrz` is **rejected** (never
   degraded to 1 point): `open_reference` warns and falls back to `min_alt`.
2. **Moon**: configurable constraint (`moon_limit_enabled`, `moon_max_illum`,
   `moon_min_sep_deg`) using `ephem_minor` position/illumination (ADR-009). It is a
   **warning + observability score penalty, not a hard filter**: the user decides.
3. **Session feasibility**: `safe_spans` lists the spans where the object is above the
   horizon (file or plane) + margin; `best_span` picks the longest continuous span
   (minimum duration required); `best_time` is the recommended start (centred on the
   altitude peak, clamped to the span) and `latest_safe_start = end − duration`.
    If the session duration (capture hub: `frames × (exp + overhead)`) does not fit any
    span → **red warning** on the card and chips («DO NOT force the instrument»);
    `viz/sky_view` shades the safe span (`axvspan`) and marks `best_time` (a
    «start by HH:MM» line); the ES/EN prose includes the window and its warning.
    **Transits** (2026-08-29): same safety reference as the rest — the star must
    clear the horizon (file or plane) + `horizon_margin_deg` **at mid-transit**, the
    moment the planet crosses; the ingress/egress samples (3 instants) only
    report coverage, they no longer decide the gate.
4. **Consistent `limit_mag`**: the hard-coded 14.0 cut in `transits.transits_tonight`
   goes away; every family uses the config value.

**Consequences**: `planner._visibility`/`visible_now` query `horizon.alt_at(az)`
instead of the plane; `suggest.score_target` adds the Moon penalty and feasibility;
`viz/sky_view` draws the real local limits silhouette under the altitude curve (the
legend reads «Límite / Limit» in both languages — the flat 30° fallback shares the
same label); Settings gains "Local limit / Límite local" (import file, preview,
margin) and "Moon" groups. Unit tests use the user's real file as a fixture.
