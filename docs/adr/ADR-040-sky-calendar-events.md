# ADR-040: El sistema solar como fuente de eventos — «Calendario del cielo» / The solar system as an event source — the "Sky calendar"

**Estado / Status**: Accepted · **Fecha / Date**: 2026-09-17 · **ejecutado /
executed**: 2026-09-17 (Track SC2, fases/phases SC0+SD+SC1+SC2+SC3 —
suite/unitaria 1366 verde/green, i18n 940 cadenas/strings 0 unfinished)

**Ver / See**: [docs/PLANS/sky-calendar.md](../PLANS/sky-calendar.md)
(plan del track / track plan, con la tabla de validación) · ADR-036 (la
barra de pestañas se enmienda aquí) · ADR-038 (lenguaje llano y chips) ·
ADR-020 (el horizonte local) · ADR-009 (efemérides propias).

*(Numeración / numbering: el 039 queda reservado para el acordeón de la
web, un stream paralelo aún sin fusionar / 039 is reserved for the web
accordion, a parallel stream not yet merged.)*

## Español

**Contexto**: la pestaña «Sun & sky» (ADR-036) era un escaparate sin flujo
— bonita, pero sin papel en la planificación. Y el observador pidió más:
el sistema solar como **fuente de eventos** (calendario lunar y
planetario, conjunciones, oposiciones, eclipses, lluvias de meteoros) y
**fenómenos de las lunas de Júpiter** para su localización («¿cuándo pasa
una luna delante del planeta?»).

**Decisión** (pactada con el observador el 2026-09-17):

1. **La pestaña sale de la barra**. Quedan **cuatro**: Tonight · Projects
   · Campaigns · Observatory (Ctrl+1..4). Todo el contenido de «Sun & sky»
   (SDO/NOAA, datos solares, línea de impacto, almanaque, PNG para redes,
   post del cielo, enlaces) se mueve **intacto** al diálogo de
   Herramientas **«Calendario del cielo…»** (`gui/skycal_dialog.py` +
   `gui/ui/sky_calendar.ui`), que se enriquece con las secciones nuevas.
2. **`core/skyevents.py`**: el motor de eventos — **hoy + 60 días**, 100 %
   local (Schlyter + coordenadas locales; cero red). Familias: fases
   lunares (sizigias verdaderas por cruce de longitud eclíptica),
   perigeo/apogeo, conjunciones Luna–planeta (< 4°) y planeta–planeta
   (< 1.5°), oposiciones y conjunciones solares como **cruces de longitud
   eclíptica** (¡no por elongación! — la lección de Saturno 2026-10-04:
   con β ≈ −2.7° el pico de elongación llega a 177.28° y un gate de
   elongación la pierde), máximas elongaciones de Mercurio/Venus,
   **eclipses probables** por geometría de conos de sombra en km (etiqueta
   honesta «probable», sin horas de contacto), y lluvias de meteoros
   (tabla anual estática). Validado contra astropy + almanaques; la tabla
   vive en el plan.
3. **`core/satellites.py`**: tránsitos de los 4 galileanos sobre el disco
   de Júpiter **y de sus sombras** (la joya amateur), filtrados por la
   localización del usuario (Júpiter arriba + de noche durante el
   tránsito). Modelo: elementos de rotación **IAU WGCCRE** (fases al ritmo
   sidéreo verdadero; la página de elementos medios de JPL advierte que no
   sirven para efemérides — confirmado empíricamente) + radios JUP365 +
   calibración empírica por luna (`phase_cal_deg`, la libración física del
   cuerpo) ajustada contra Horizons q12. **Validado: 22 ventanas en
   sep/oct/nov 2026, todas ≤10 min (peor 9.6)**. La UI etiqueta la
   precisión («±10 min»). Saturno/Titán queda fuera (fuera de temporada
   hasta ~2040 — documentado en el diálogo); el afinado exacto vía
   Horizons es una opción futura (spike primero).
4. **Chips en Tonight**: hasta 3, lo grande primero (eclipse > sombra/
   tránsito galileano > oposición > máx. elongación > conjunciones > fases
   > lluvias > perigeo), uno por familia, satélites solo si son
   observables; clic → el diálogo. Se recalculan al arrancar y en cada
   cálculo de Tonight.
5. **Lenguaje llano y honestidad**: cada evento en palabras («Saturno en
   oposición — mag 0.6, toda la noche»), las incertidumbres visibles, y
   nada promete más de lo que el motor sabe.

**Consecuencias**: la barra se aligera a 4 pestañas; el calendario nace
como herramienta rica; el Tonight se entera solo de lo que pasa esta
noche. `ephem_minor` gana `planet_heliocentric_xyz` (aditivo) y
`moon(ecl_lat_deg)`. El motor no toca la red; lo solar sigue con la caché
NOAA/SILSO de siempre.

## English

**Context**: the "Sun & sky" tab (ADR-036) was a showcase without a
workflow. The observer asked for more: the solar system as an **event
source** (lunar and planetary calendar, conjunctions, oppositions,
eclipses, meteor showers) and **Jupiter's moon phenomena** for his
location ("when does a moon cross in front of the planet?").

**Decision** (agreed with the observer on 2026-09-17):

1. **The tab leaves the bar** — four remain (Tonight · Projects ·
   Campaigns · Observatory, Ctrl+1..4). All its content moves **intact**
   into the Tools-menu **"Sky calendar…"** dialog
   (`gui/skycal_dialog.py` + `gui/ui/sky_calendar.ui`), enriched with the
   new sections.
2. **`core/skyevents.py`**: the event engine — **today + 60 days**, 100 %
   local (no network). Families: true-syzygy Moon phases, perigee/apogee,
   Moon–planet (< 4°) and planet–planet (< 1.5°) conjunctions, oppositions
   and Sun conjunctions as **ecliptic-longitude crossings** (not
   elongation-gated — the Saturn 2026-10-04 lesson), Mercury/Venus
   greatest elongations, **likely eclipses** from shadow-cone geometry in
   km (honest "likely" label, no contact times), and meteor showers
   (static annual table). Validated against astropy + almanacs.
3. **`core/satellites.py`**: Galilean moon transits across Jupiter's disc
   **and their shadows**, gated by the observer's site (Jupiter up + dark
   during the event). IAU WGCCRE rotation elements + JPL radii + an
   empirical per-moon phase calibration (`phase_cal_deg`, the body's
   physical libration) fitted against Horizons q12. **Validated: 22
   windows across Sep/Oct/Nov 2026, all within ±10 min (worst 9.6)** — and
   the UI labels the precision. Saturn/Titan is out (out of season until
   ~2040, documented); exact Horizons refinement is a future option.
4. **Tonight chips**: up to 3, big things first, one per family,
   observability-gated; click opens the dialog. Recomputed at startup and
   on every Tonight run.
5. **Plain language and honesty**: every event in words, uncertainties
   visible, nothing over-promised.

**Consequences**: a leaner 4-tab bar; a rich calendar tool in the Tools
menu; Tonight learns the sky by itself. `ephem_minor` gains
`planet_heliocentric_xyz` (additive) and `moon(ecl_lat_deg)`. No network
in the engine; the Sun section keeps the NOAA/SILSO cache.
