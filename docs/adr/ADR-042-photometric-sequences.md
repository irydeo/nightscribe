# ADR-042: Secuencias fotométricas y cartas de comparación (fuentes VizieR, transformaciones Gaia/APASS, propuesta automática)

**Estado / Status**: Accepted · **Fecha / Date**: 2026-09-21 · **rev. 2026-09-21** (tras la ejecución: las cuatro fases están implantadas; ver el mapa en `docs/WORKFLOWS.es.md`, track SF)

**Ver / See**: [docs/DATA_SOURCES.es.md](../DATA_SOURCES.es.md) · [docs/DATA_SOURCES.md](../DATA_SOURCES.md)

## Español

**Contexto**: el seguimiento de variables, HADS y supernovas es fotometría
diferencial, y su primera pregunta es «¿con qué comparo?». Hoy NightScribe
deja esa respuesta al usuario: el protocolo de campaña guarda
`comp_stars` como texto libre y el reporte AAVSO EFF escribe
`CNAME/CMAG/KNAME/KMAG = na` (ADR-035 V-i). La herramienta web SecFot
(González Farfán & González Carballo 2026) resuelve justo esto: carta del
campo sobre imagen DSS2 con magnitudes de catálogo rotuladas, variables VSX
marcadas para no elegirlas jamás como comparación, y exportación de la
secuencia (PNG + CSV). Queremos esa capacidad dentro de la app, centrada en
el proyecto (el objetivo ya trae sus coordenadas; nadie teclea AR/Dec).

**Alternativas descartadas**:

- **(a) Incrustar SecFot en un QWebEngineView**: rompe la regla de GUI
  nativa PySide6, no pasa por la caché de `core/db.py`, no hereda el tema ni
  la i18n, y añade una dependencia pesada.
- **(b) Scraping del AAVSO VSP** (Variable Star Plotter): sin API pública
  estable y frágil; contra el principio de buen ciudadano que rige las
  fuentes (caché agresiva, TTLs largos).
- **(c) ATLAS Refcat2 desde el día uno**: aporta PS1 gri y 2MASS JHK, pero
  Gaia + APASS cubren la necesidad (profundidad y banda V directa). Queda
  como ampliación trivial del diccionario `CATALOGS` si se echa en falta.

**Decisión**:

1. **Nueva fuente `core/sources/vizier.py`**: cone search TSV contra el
   servicio `asu-tsv` de VizieR para **Gaia EDR3** (`I/350/gaiaedr3`,
   catálogo por defecto, banda G), **APASS DR9** (`II/336/apass9`, banda V)
   y **AAVSO VSX** (`B/vsx/vsx`, cruce de variables del campo). Todo por
   `db.http_get` con `SOURCE_TTL["vizier"] = 30 d`. Parseo tolerante con
   sonda de columnas y reintento `-out.all` (patrón de SecFot): un renombre
   de columna en VizieR no rompe la app. Fallo de red → `None` y aviso
   honesto; nada más se rompe. Cubre además el `gaiacat.py` previsto en el
   plan B5.4 del track de supernovas.
2. **`core/phototrans.py`** (math puro): transformaciones
   Gaia → Johnson-Cousins (polinomios de Riello et al. 2021, doc Gaia DR3
   5.5.1, rango de validez BP−RP ∈ [−0,5; 4,0]), B−V directo (APASS) o
   estimado (Gaia) con procedencia explícita, errores por cuadratura y
   clasificación de color bilingüe.
3. **`core/compstars.py`**: modelo de campo (estrellas normalizadas dentro
   del encuadre), cruce VSX a ≤ 5″ que **descalifica** a las variables como
   comparaciones, `propose_comps()` automático (más brillantes que el
   objetivo con margen, |Δ(B−V)| ≤ 0,4 cuando hay color, aisladas a 10″,
   repartidas por el campo, 1 check) con una **frase de razón por estrella**
   (la filosofía «¿por qué esta noche?» de `suggest.py` aplicada a «¿por qué
   esta estrella?») y `export_sequence_csv()`.
4. **Fases siguientes** (mismo ADR): carta PNG `viz/finder_view.py` +
   CLI `sequence` (Fase 2); botón primario en la pestaña Seguimiento con
   diálogo, PNG/CSV al proyecto y secuencia hacia `protocol.comp_stars` y el
   EFF (Fase 3); picker interactivo QGraphicsView (Fase 4, patrón ADR-029).
   El fondo de la carta es DSS2 vía `cutouts.py` por defecto o,
   opcionalmente, **el propio FITS del usuario** (WCS propio o resuelto con
   `astrometry.py`, como blink; el original jamás se modifica).
5. **Naming**: el módulo de secuencias fotométricas no puede llamarse
   `sequence.py`: ese nombre ya son las secuencias de captura NINA/CCDciel
   (ADR-021). Los módulos nuevos son `vizier.py`, `phototrans.py`,
   `compstars.py`, `field_math.py` (Fase 2), `finder_view.py` (Fase 2) y
   `finder_widget.py` (Fase 4).

**Consecuencias**:

- El «¿con qué comparo?» queda respondido dentro de la app con datos de
  catálogo cacheados; el EFF deja de escribir `na` en las columnas de
  comparación cuando el usuario guarda su secuencia (Fase 3).
- Las transformaciones son ciencia publicada con rango de validez marcado;
  los valores derivados se muestran siempre como estimaciones («≈» /
  columna «(est.)»), nunca como magnitudes de catálogo.
- Atribución: algoritmos de campo y cruce portados de SecFot (González
  Farfán & González Carballo 2026); polinomios de Riello et al. 2021. La
  nota de fuente de cada catálogo acompaña los exports.

## English

**Context**: the variable/HADS/SN follow-up is differential photometry, and
its first question is "with what do I compare?". Today NightScribe leaves
that answer to the user: the campaign protocol stores `comp_stars` as free
text and the AAVSO EFF report writes `CNAME/CMAG/KNAME/KMAG = na`
(ADR-035 V-i). The web tool SecFot (González Farfán & González Carballo
2026) solves exactly this: a field chart over a DSS2 image with catalog
magnitudes labelled, VSX variables marked so they are never picked as
comparisons, and sequence export (PNG + CSV). We want that capability
inside the app, centred on the project (the target already carries its
coordinates; nobody types RA/Dec).

**Alternatives rejected**:

- **(a) Embedding SecFot in a QWebEngineView**: breaks the native PySide6
  GUI rule, bypasses the `core/db.py` cache, inherits neither the theme nor
  the i18n, and adds a heavy dependency.
- **(b) Scraping the AAVSO VSP** (Variable Star Plotter): no stable public
  API and fragile; against the good-citizen principle that rules the
  sources (aggressive caching, long TTLs).
- **(c) ATLAS Refcat2 from day one**: adds PS1 gri and 2MASS JHK, but Gaia
  + APASS cover the need (depth and a direct V band). It stays a trivial
  extension of the `CATALOGS` dict if ever missed.

**Decision**:

1. **New source `core/sources/vizier.py`**: TSV cone search against the
   VizieR `asu-tsv` service for **Gaia EDR3** (`I/350/gaiaedr3`, default
   catalog, G band), **APASS DR9** (`II/336/apass9`, V band) and **AAVSO
   VSX** (`B/vsx/vsx`, field variable cross-match). Everything through
   `db.http_get` with `SOURCE_TTL["vizier"] = 30 d`. Tolerant parsing with
   a column probe and an `-out.all` retry (SecFot's pattern): a renamed
   VizieR column breaks nothing. Network failure → `None` and an honest
   notice; nothing else breaks. It also covers the `gaiacat.py` planned in
   B5.4 of the supernova track.
2. **`core/phototrans.py`** (pure math): Gaia → Johnson-Cousins
   transformations (Riello et al. 2021 polynomials, Gaia DR3 doc 5.5.1,
   validity range BP−RP ∈ [−0.5; 4.0]), direct (APASS) or estimated (Gaia)
   B−V with explicit provenance, quadrature errors and bilingual colour
   classification.
3. **`core/compstars.py`**: field model (normalised stars inside the
   frame), VSX cross-match to 5″ that **disqualifies** variables as
   comparisons, automatic `propose_comps()` (brighter than the target with
   a margin, |Δ(B−V)| ≤ 0.4 when colour is known, isolated to 10″, spread
   across the field, 1 check) with a **plain-language reason per star**
   (the "why tonight" philosophy of `suggest.py` applied to "why this
   star?") and `export_sequence_csv()`.
4. **Next phases** (same ADR): PNG chart `viz/finder_view.py` + `sequence`
   CLI (phase 2); primary button in the Follow-up tab with options dialog,
   PNG/CSV into the project and the sequence flowing to
   `protocol.comp_stars` and the EFF (phase 3); interactive QGraphicsView
   picker (phase 4, ADR-029 pattern). The chart background is DSS2 via
   `cutouts.py` by default or, optionally, **the user's own FITS** (own WCS
   or solved with `astrometry.py`, as the blink does; the original is never
   modified).
5. **Naming**: the photometric-sequence module cannot be `sequence.py`:
   that name already means the NINA/CCDciel capture sequences (ADR-021).
   The new modules are `vizier.py`, `phototrans.py`, `compstars.py`,
   `field_math.py` (phase 2), `finder_view.py` (phase 2) and
   `finder_widget.py` (phase 4).

**Consequences**:

- "With what do I compare?" is answered inside the app with cached catalog
  data; the EFF stops writing `na` in the comparison columns once the user
  saves a sequence (phase 3).
- The transformations are published science with a marked validity range;
  derived values are always shown as estimates ("≈" / "(est.)" column),
  never as catalog magnitudes.
- Attribution: field building and cross-match algorithms ported from SecFot
  (González Farfán & González Carballo 2026); polynomials from Riello et
  al. 2021. Each catalog's source note travels with the exports.
