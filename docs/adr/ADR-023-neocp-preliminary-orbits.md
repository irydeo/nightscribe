# ADR-023: Preliminary orbits for unconfirmed NEOCP objects via NEOfixer /orbit/

**Estado / Status**: Accepted · **Fecha / Date**: 2026-08-25

## Español

**Contexto**: los NEOs sin confirmar (NEOCP) son el caso más urgente de NightScribe
(hay que medirlos *esta noche* o se pierden), pero SBDB no los conoce, así que
`enrich()` no podía ofrecer ni órbita ni efeméride — justo cuando más se necesitan
para evaluar si merece la pena apuntarles. ADR-021 asumía que para esos objetos
«la efeméride NEOfixer/Horizons es la única vía — se exporta la tabla, no elementos».
Investigando la API de NEOfixer (0.3) encontramos el endpoint público
`GET /orbit/?object=<packed>`: una solución preliminar de Find_Orb (Bill Gray) con
elementos keplerianos completos, σ por elemento, MOIDs por planeta, nº de residuos y
arco observado, actualizada varias veces al día.

**Decisión**:

1. `core/sources/neofixer.py::orbit(packed)` — nuevo endpoint cacheado con TTL corto
   (1.5 h: estos objetos cambian rápido), normalizado por `parse_neofixer_orbit()` a
   la **misma forma que `parse_sbdb`** (`elements` con claves SBDB: `a, e, q, Q, i,
   om←asc_node, w←arg_per, ma←M, tp←Tp, epoch`) más `sigmas`, `moid`, `phys`,
   `n_resids`, `arc_days` y la marca `preliminary: True`.
2. `core/enrich.py::_enrich_preliminary_orbit()` — cuando SBDB falla y hay
   `fallback_target`, intentar la órbita de NEOfixer antes de rendirse. Si existe, el
   dict resultante lleva `sbdb` (forma estándar) + `preliminary` + `unconfirmed` (los
   campos del planner se conservan para narrativa y scoring). La efeméride se calcula
   **localmente** con `ephem_minor.kepler_ra_dec` (Horizons no conoce estos objetos).
3. Tabla de parámetros: `orbits.explain_elements()` acepta `sigmas`/`n_resids`/
   `arc_days` y añade tres filas bilingües (banner «órbita preliminar», σ(a)/σ(e)/σ(i),
   arco y observaciones).
4. `core/ephemeris.py::generate()` — si Horizons no devuelve filas, propagar la órbita
   preliminar localmente (mismo formato de filas, marcadas `preliminary`), con banner
   bilingüe en la cabecera de los exportadores CSV/TheSkyX/CdC.
5. JPL Scout (`scout.api?tdes=X&orbits=1` → órbitas muestreadas; `eph-start` →
   efeméride mediana con σ-pos) queda documentado como posible fase futura:
   visualización tipo abanico de la incertidumbre y efeméride que integra las 1000
   órbitas muestreadas.

**Consecuencias**: el tab Orbit del diálogo Explore dibuja NEOs sin confirmar sin
tocar el GUI; la tabla explica la incertidumbre; las efemérides exportables cubren
NEOCP. La palabra «preliminar» aparece siempre que se usan estos elementos. Se corrige
además un bug preexistente en `ephem_minor`: la posición geocéntrica se calculaba
sumando (en vez de restando) la posición heliocéntrica terrestre — detectado al
validar la propagación contra Horizons (Apophis/Mars) y Scout (6HK2621); tests de
regresión añadidos con tolerancias que asumen la diferencia de marco (equinoccio de la
fecha vs J2000, ADR-009).

## English

**Context**: unconfirmed NEOs (NEOCP) are NightScribe's most urgent use case (they
must be measured *tonight* or they are lost), but SBDB does not know them, so
`enrich()` could offer neither an orbit nor an ephemeris — exactly when they are most
needed to evaluate whether they are worth pointing at. ADR-021 assumed that for those
objects "the NEOfixer/Horizons ephemeris is the only route — the table is exported,
not elements". Investigating the NEOfixer API (0.3) we found the public endpoint
`GET /orbit/?object=<packed>`: a preliminary Find_Orb (Bill Gray) solution with full
Keplerian elements, per-element σ, per-planet MOIDs, residual count and observed arc,
updated several times a day.

**Decision**:

1. `core/sources/neofixer.py::orbit(packed)` — new cached endpoint with a short TTL
   (1.5 h: these objects change fast), normalised by `parse_neofixer_orbit()` into the
   **same shape as `parse_sbdb`** (`elements` with SBDB keys: `a, e, q, Q, i,
   om←asc_node, w←arg_per, ma←M, tp←Tp, epoch`) plus `sigmas`, `moid`, `phys`,
   `n_resids`, `arc_days` and a `preliminary: True` flag.
2. `core/enrich.py::_enrich_preliminary_orbit()` — when SBDB fails and a
   `fallback_target` exists, try the NEOfixer orbit before giving up. If found, the
   resulting dict carries `sbdb` (standard shape) + `preliminary` + `unconfirmed`
   (planner fields are kept for narrative and scoring). The ephemeris is computed
   **locally** with `ephem_minor.kepler_ra_dec` (Horizons does not know these
   objects).
3. Params table: `orbits.explain_elements()` accepts `sigmas`/`n_resids`/`arc_days`
   and adds three bilingual rows (preliminary-orbit banner, σ(a)/σ(e)/σ(i), arc and
   observations).
4. `core/ephemeris.py::generate()` — when Horizons returns nothing, propagate the
   preliminary orbit locally (same row format, flagged `preliminary`), with a
   bilingual banner in the CSV/TheSkyX/CdC exporter headers.
5. JPL Scout (`scout.api?tdes=X&orbits=1` → sampled orbits; `eph-start` → median
   ephemeris with σ-pos) is documented as a possible future phase: fan-style
   uncertainty visualisation and an ephemeris integrating the 1000 sampled orbits.

**Consequences**: the Explore dialog's Orbit tab draws unconfirmed NEOs with no GUI
changes; the table explains the uncertainty; exportable ephemerides now cover NEOCP.
The word "preliminary" appears wherever these elements are used. A pre-existing bug in
`ephem_minor` is also fixed: the geocentric position was computed by adding (instead
of subtracting) the heliocentric Earth position — caught while validating the
propagation against Horizons (Apophis/Mars) and Scout (6HK2621); regression tests
added with tolerances that account for the frame difference (equinox-of-date vs
J2000, ADR-009).
