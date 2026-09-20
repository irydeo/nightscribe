# ADR-031: Ficha de objeto unificada — coordenadas copiables, tabla multilínea, SN/tránsitos con tabla, «Discovered» en NEOs y filtro duro de apertura

**Estado / Status**: Accepted · **Fecha / Date**: 2026-09-07

## Español

**Contexto**: la ficha de objeto (`gui/overview.py::ObjectPanel`, compartida por el
hub y por Explore) solo ofrecía tabla de parámetros a NEOs/cometas/PCCP; SN y
tránsitos se quedaban en hook + bullets, con chips de captura escasos y
desproporcionados. La tabla cortaba en vertical las explicaciones largas (sin
`wordWrap` ni auto-alto de fila). Las coordenadas del objeto no se veían por
ningún sitio. La columna «Discovered» de la lista completa solo se rellenaba para
SN (Rochester). Y ADR-015 prometió filtrar tránsitos por la apertura del usuario,
lo que nunca se implementó. Plan de trabajo: `docs/PLANS/object-card.md`.

**Decisión**:

1. **Coordenadas siempre visibles y copiables**: bloque bajo el hook con AR/Dec
   en decimal **y** sexagesimal + botón «Copiar» (ambos formatos al
   portapapeles). La cadena de fuentes (`_coords_from`: ephem → SIMBAD →
   NEOfixer → planner) es la misma que usa la carta de cielo.
2. **Tabla multilínea**: `setWordWrap(True)` + `resizeRowsToContents()` tras
   cada relleno, columnas Parámetro/Valor con tope (280 px) para dar aire a
   «Qué significa». Detalle técnico no obvio: `sectionResized` se emite **antes**
   de que `columnWidth()` reporte el nuevo tamaño, así que el re-ajuste de filas
   se engancha a esa señal forzando primero el ancho notificado.
3. **Una tabla por tipo**: `orbits.explain_transient` (SN: tipo, galaxia,
   distancia, brillo, descubrimiento; z a fondo) y `orbits.explain_transit`
   (tránsito: inicio/fin UTC, duración, profundidad en mmag y %, brillo de la
   estrella, **veredicto telescopio mínimo vs. tu apertura**; periodo, tamaño,
   masa, distancia, descubrimiento y deriva O-C a fondo). La rama «exoplanet»
   de `enrich` fusiona el target del planner con el patrón ADR-027
   (`setdefault`): sin ese arreglo el evento ExoClock de esta noche se perdía
   (bug que además apagaba la curva de luz en nombres tipo «HD 209458 b»).
4. **Chips con la misma gramática por tipo**: SN gana tipo de evento y
   frescura (días desde el descubrimiento, verde si ≤14 d); tránsito gana
   profundidad Δmmag. Los extras salen del dict enriquecido, así que también
   aparecen sin contexto de planner.
5. **«Discovered» exacto para NEOs y PCCP**: SBDB con `discovery=1`
   (fallback `orbit.first_obs`); NEOfixer `/orbit/` (`observations.earliest`)
   para NEOCP sin confirmar; PCCP mapea la columna que la propia página ya
   parseaba. Resolución en pool paralelo (4 hilos, patrón de los cometas) y
   caché de una semana. Nuevo `core/dates.py` único para los formatos de fecha
   de las fuentes (`YYYY/MM/DD`, `YYYY-MM-DD`, `YYYY-Mmm-DD`).
6. **Filtro duro de apertura en tránsitos**: `transits_tonight(aperture_in=)`
   descarta `min_telescope_in > aperture_inches`; interruptor
   `transit_scope_filter` (Configuración > Observación, activado por defecto).
   Espíritu ADR-025: sin dato de telescopio mínimo, **no** se descarta.

**Alternativas**: coordenadas como filas de la tabla (menos visibles, sin botón
copiar); fecha de NEO derivada de la designación provisional sin red (~15 días
de precisión — descartado: el usuario pidió fecha exacta); filtro de apertura
suave con aviso ⚠ (descartado: el telescopio mínimo de ExoClock es dato curado,
merece filtro duro como en ADR-025).

**Consecuencias**: la ficha cuenta la misma historia con la misma estructura
para los cinco tipos; Tonight hace ~15 llamadas SBDB extra la primera noche con
caché fría (paralelizadas, cacheadas 7 días); i18n: el comando lupdate documentado
en CONTRIBUTING ahora incluye `gui/widgets/` (su omisión marcaba «vanished»
cadenas vivas y rompía los tests de i18n al regenerar).

## English

**Context**: the object card (`gui/overview.py::ObjectPanel`, shared by the hub
and Explore) only gave a parameters table to NEOs/comets/PCCPs; SNe and
transits got just hook + bullets, with sparse, oversized-looking capture chips.
The table vertically clipped long explanations (no `wordWrap`, no row
auto-height). The object's coordinates were shown nowhere. The full list's
"Discovered" column was only filled for SNe (Rochester). And ADR-015 promised
to filter transits by the user's aperture — never implemented. Work plan:
`docs/PLANS/object-card.md`.

**Decision**:

1. **Coordinates always visible and copyable**: a block under the hook with
   RA/Dec in decimal **and** sexagesimal + a "Copy" button (both formats to
   the clipboard). The source chain (`_coords_from`: ephem → SIMBAD →
   NEOfixer → planner) is the same one the sky chart uses.
2. **Multi-line table**: `setWordWrap(True)` + `resizeRowsToContents()` after
   every refill, capped Parameter/Value columns (280 px) so "What it means"
   keeps its air. Non-obvious technical detail: `sectionResized` fires
   **before** `columnWidth()` reports the new size, so the row re-fit hooks
   that signal and forces the notified width first.
3. **One table per type**: `orbits.explain_transient` (SN: type, host galaxy,
   distance, brightness, discovery; redshift in depth) and
   `orbits.explain_transit` (transit: start/end UTC, duration, depth in mmag
   and %, star brightness, **minimum telescope vs. your aperture verdict**;
   period, size, mass, distance, discovery and O-C drift in depth). The
   "exoplanet" branch of `enrich` merges the planner target with the ADR-027
   pattern (`setdefault`): without that fix tonight's ExoClock event was lost
   (a bug that also switched the light curve off for names like "HD 209458 b").
4. **Chips with the same grammar per type**: SNe gain event type and freshness
   (days since discovery, green when ≤14 d); transits gain depth Δmmag. The
   extras come from the enriched dict, so they show even without a planner
   context.
5. **Exact "Discovered" for NEOs and PCCPs**: SBDB with `discovery=1`
   (fallback `orbit.first_obs`); NEOfixer `/orbit/` (`observations.earliest`)
   for unconfirmed NEOCPs; PCCP maps the column the page itself already
   parsed. Resolved in a parallel pool (4 threads, the comet pattern) with a
   one-week cache. New single `core/dates.py` for the sources' date formats
   (`YYYY/MM/DD`, `YYYY-MM-DD`, `YYYY-Mmm-DD`).
6. **Hard aperture gate for transits**: `transits_tonight(aperture_in=)` drops
   `min_telescope_in > aperture_inches`; `transit_scope_filter` toggle
   (Settings > Observing, on by default). ADR-025 spirit: no minimum-telescope
   datum, **no** discard.

**Alternatives**: coordinates as table rows (less visible, no copy button); NEO
date derived from the provisional designation without network (~15-day
precision — rejected: the user asked for the exact date); soft aperture filter
with a ⚠ warning (rejected: ExoClock's minimum telescope is curated data, it
earns a hard gate as in ADR-025).

**Consequences**: the card tells the same story with the same structure for all
five types; Tonight makes ~15 extra SBDB calls on the first cold-cache night
(parallel, cached for 7 days); i18n: the lupdate command documented in
CONTRIBUTING now includes `gui/widgets/` (omitting it marked live strings as
"vanished" and broke the i18n tests on regeneration).
