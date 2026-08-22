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
