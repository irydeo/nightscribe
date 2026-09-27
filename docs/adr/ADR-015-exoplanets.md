# ADR-015: Exoplanet transits via ExoClock + NASA Exoplanet Archive

**Estado / Status**: Accepted · **Fecha / Date**: 2026-08-21

## Español

**Contexto**: los tránsitos de exoplanetas son la primera funcionalidad basada en
*eventos* con ventana horaria. El usuario sugirió var.astro.cz/ETD, que devolvía 404
en la verificación.

**Decisión**: **ExoClock** (proyecto ESA Ariel) como catálogo: `planets_json` público
con efeméride de tránsito (`ephem_mid_time`, `ephem_period`), profundidad (mmag),
duración, prioridad, telescopio mínimo y deriva O-C. Los instantes de tránsito se
calculan **en local** (`t0 + n·P`, `core/transits.py`) y se cruzan con la noche y la
altitud de la estrella. La ficha detallada del planeta sale del **NASA Exoplanet
Archive** (TAP). ETD queda como enlace externo.

**Alternativas**: ETD como fuente (caída en la verificación); Swarthmore Transit
Finder (web scrapeable pero sin API); predecir con TESS oficial (más complejo).

**Consecuencias**: planificación de tránsitos offline tras una descarga diaria;
prioridades científicas reales de la comunidad Ariel; factibilidad filtrada por la
apertura del telescopio del usuario (Configuración).

**Actualización (2026-09-07, plan object-card, subplan 6)**: la consecuencia de
apertura ya está implementada — `transits_tonight(aperture_in=...)` descarta los
eventos cuyo `min_telescope_inches` de ExoClock supera la apertura del usuario;
interruptor `transit_scope_filter` (Configuración > Observación, por defecto
activado) y, siguiendo el espíritu de ADR-025, un evento sin dato de telescopio
mínimo **nunca** se descarta. La ficha del tránsito muestra el veredicto
«telescopio mínimo vs. tu apertura» (`orbits.explain_transit`).

**Actualización (2026-09-10, Track D — captura guiada)**: el evento gana la
**ventana de captura recomendada** — `transits.recommended_window`: baseline +
tránsito + baseline, con baseline = max(25 % de la duración, **30 min**)
(recetas Conti/AAVSO) — más `baseline_fits` (cabe en la noche segura: oscuridad
y horizonte en ambos bordes; **avisa y penaliza** en el score, nunca un gate
nuevo — el gate sigue en mid-transit, ADR-020), la **cadencia máxima** que
resuelve el ingress (≥ 3 puntos: `0.15 · duración / 3`) y la **exposición
heurística** `exposure.recommended_transit_exposure(v_mag, plate_scale)`
(tabla por magnitud escalada por el cuadrado de la escala de placa; «guía
honesta», el ajuste fino es la toma de prueba del checklist). La reducción es
**100 % externa con EXOTIC** (NASA/JPL): NightScribe exporta el `inits.json`
pre-rellenado (`core/exotic.py`, esquema fijado contra el `inits.json` vivo de
`rzellem/EXOTIC`, re-verificado 2026-09-10; campos TAP ampliados con bump de
caché v2) y el usuario lo ejecuta en su propio entorno Python ≤ 3.10 — nunca
embebido (ADR-004). El cierre del flujo científico (subida a ExoClock / AAVSO
Exoplanet Database) se guía desde la pestaña Process.

**Actualización (2026-09-27, reapertura firmada; plan de fotometría de series)**:
la reducción de tránsitos pasa a hacerse **en local**: NightScribe calcula su
detrend, su ajuste de tránsito y su profundidad en numpy puro (sin scipy ni
astropy, ADR-004), tomando a EXOTIC como espejo de calidad con su **método citado**
(detrend `a1·exp(a2·X)+a3` con `a1` analítico, bounds `rprs ∈ [0; 1,25·prior]` y
`tmid ± 25σ` con tope `±P/4`, sigma-clip de 25–30 min por `lstsq` deslizante,
errores desde la dispersión OOT, diagnósticos con duración medida vs. esperada) y
sin copiar ni una línea de su código (licencia Caltech/JPL). La compuerta de
paridad se fija **antes** de medir (T_mid dentro de 3σ, Rp/Rs dentro de 5 %, σ de
parámetros dentro de 20 %; si no, bootstrap paramétrico) y **no se relaja** para
que un test pase. El handoff con `inits.json` **sigue siendo la vía experta** para
el stack pesado (muestreo anidado, LDTk, ajustes multi-noche, fotometría PSF),
nunca embebido. La subida a ExoClock queda en la app como export manual en formato
HOPS (ADR-049). Plan: `docs/PLANS/series-photometry.md`; compañeros: ADR-048
(series), ADR-050 (en vivo y agrupación), ADR-051 (ASTAP).

**Actualización (2026-09-27, opción A: orquestación de EXOTIC)**: la reapertura
anterior (vía numpy la primera) se **matiza**. La reducción real de los 142 FITS
de MicroObservatory (sin WCS, frames desplazados y rotados, saturados) no alcanza
la precisión de EXOTIC con la vía numpy, así que el flujo científico de tránsitos
pasa a **orquestar EXOTIC**: NightScribe genera el `inits.json` de la visita
(`core/exotic.make_inits_for_visit`), lo ejecuta headless en un entorno
Python ≤3.10 externo (`core/exotic_env.py`, `core/exotic_run.py`; `exotic -red
inits.json -ov`) y **importa** su curva y parámetros al proyecto
(`core/exotic_import.py`). La vía numpy (`core/series_measure.py` +
`core/transit_fit.py`) queda como **previsualización** y se valida contra la
curva reducida por EXOTIC. La compuerta de paridad se mide ya sobre el ajuste
(nuestro `transit_fit` sobre la curva de EXOTIC) y **pasa**: T_mid a 2 s, Rp/Rs
a 1,2 %, σ al 96 % y profundidad a 2,3 %. Se sigue **sin copiar** código de
EXOTIC (licencia Caltech/JPL): se ejecuta y se lee su salida. ADR-052
(orquestación de EXOTIC); plan: `docs/PLANS/exotic-orchestration.md`.

## English

**Context**: exoplanet transits are the first *event*-based feature with a time
window. The user suggested var.astro.cz/ETD, which returned 404 during verification.

**Decision**: **ExoClock** (ESA Ariel project) as the catalogue: public
`planets_json` with transit ephemeris (`ephem_mid_time`, `ephem_period`), depth
(mmag), duration, priority, minimum telescope and O-C drift. Transit times are
computed **locally** (`t0 + n·P`, `core/transits.py`) and matched against the night
and the star's altitude. The detailed planet card comes from the **NASA Exoplanet
Archive** (TAP). ETD remains an external link.

**Alternatives**: ETD as source (down during verification); Swarthmore Transit Finder
(scrapeable web but no API); official TESS predictions (more complex).

**Consequences**: offline transit planning after one daily download; real scientific
priorities from the Ariel community; feasibility filtered by the user's telescope
aperture (Settings).

**Update (2026-09-07, object-card plan, subplan 6)**: the aperture consequence is
now implemented — `transits_tonight(aperture_in=...)` drops events whose ExoClock
`min_telescope_inches` exceeds the user's aperture; the `transit_scope_filter`
toggle (Settings > Observing, default on) disables it, and following the ADR-025
spirit an event with no minimum-telescope datum is **never** dropped. The transit
card shows the "minimum telescope vs. your aperture" verdict
(`orbits.explain_transit`).

**Update (2026-09-10, Track D — guided capture)**: the event gains a
**recommended capture window** — `transits.recommended_window`: baseline +
transit + baseline, with baseline = max(25 % of the duration, **30 min**)
(Conti/AAVSO recipes) — plus `baseline_fits` (fits the safe night: darkness
and horizon at both edges; it **warns and penalises** the score, never a new
gate — the gate stays at mid-transit, ADR-020), the **maximum cadence** that
resolves the ingress (≥ 3 points: `0.15 · duration / 3`) and the **heuristic
exposure** `exposure.recommended_transit_exposure(v_mag, plate_scale)`
(per-magnitude table scaled by the square of the plate-scale ratio; an
"honest guide" — the fine adjustment is the checklist's test shot). The
reduction is **100 % external with EXOTIC** (NASA/JPL): NightScribe exports a
pre-filled `inits.json` (`core/exotic.py`, schema fixed against the live
`inits.json` of `rzellem/EXOTIC`, re-verified 2026-09-10; TAP fields extended
with a v2 cache bump) and the user runs it in their own Python ≤ 3.10
environment — never embedded (ADR-004). The closing of the scientific loop
(upload to ExoClock / AAVSO Exoplanet Database) is guided from the Process
tab.

**Update (2026-09-27, signed reopening; photometric series plan)**: transit
reduction now happens **in-house**: NightScribe computes its detrend, its transit
fit and its depth in pure numpy (no scipy, no astropy, ADR-004), taking EXOTIC as
the quality mirror with its **method cited** (detrend `a1·exp(a2·X)` with analytic
`a1`, bounds `rprs ∈ [0; 1.25×prior]` and `tmid ± 25σ` capped at `±P/4`, 25–30 min
sigma-clip via sliding `lstsq`, errors from the OOT scatter, diagnostics including
measured vs. expected duration) and copying not one line of its code (Caltech/JPL
licence). The parity gate is fixed **before** measuring (T_mid within 3σ, Rp/Rs
within 5 %, parameter σ within 20 %; otherwise a parametric bootstrap) and is
**never relaxed** to make a test pass. The `inits.json` handoff **remains the
expert path** for the heavy stack (nested sampling, LDTK, multi-night fits, PSF
photometry), never embedded. Uploading to ExoClock stays in the app as a manual
HOPS-format export (ADR-049). Plan: `docs/PLANS/series-photometry.md`;
companions: ADR-048 (series), ADR-050 (live mode and grouping), ADR-051 (ASTAP).

**Update (2026-09-27, option A: EXOTIC orchestration)**: the earlier reopening
(the numpy path first) is **nuanced**. Reducing the 142 MicroObservatory FITS
(no WCS, drifting and rotating frames, saturated stars) with the numpy path does
not reach EXOTIC's precision, so the scientific transit flow now **orchestrates
EXOTIC**: NightScribe writes the visit's `inits.json`
(`core/exotic.make_inits_for_visit`), runs it headless in an external Python
≤3.10 environment (`core/exotic_env.py`, `core/exotic_run.py`; `exotic -red
inits.json -ov`) and **imports** its light curve and parameters into the project
(`core/exotic_import.py`). The numpy path (`core/series_measure.py` +
`core/transit_fit.py`) becomes a **preview** and is validated against EXOTIC's
reduced curve. The parity gate is now measured on the fit (our `transit_fit` on
EXOTIC's curve) and **passes**: T_mid within 2 s, Rp/Rs within 1.2 %, sigma at
96 % and depth within 2.3 %. No line of EXOTIC code is copied (Caltech/JPL
licence): it is run and its output read. ADR-052 (EXOTIC orchestration); plan:
`docs/PLANS/exotic-orchestration.md`.
