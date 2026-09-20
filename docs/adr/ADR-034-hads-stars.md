# ADR-034: Estrellas HADS como objetivo de la noche — fuente híbrida (hoja viva + snapshot), observación continua sin fase

**Estado / Status**: Accepted · **Fecha / Date**: 2026-09-11 · **rev. 2026-09-11** (tras la ejecución: H-b pasa de «empaquetado puro» a **híbrido**; se añaden H-i…H-n)

**Ver / See**: [docs/PLANS/hads-stars.md](../PLANS/hads-stars.md) · [docs/HADS.md](../HADS.md) · [docs/HADS.es.md](../HADS.es.md)

## Español

**Contexto**: NightScribe planifica la noche, entiende cada objeto y lo cuenta.
La lista actual de familias (NEO, SN, cometas, PCCP, tránsitos, alerts) no
incluye estrellas variables de alta amplitud, a pesar de ser objetivos
divulgativos y fotométricamente únicos: con ~1–5 h de periodo y ΔV ≥ 0.3 mag se
captura una curva de luz completa en una noche y se **ve pulsar la estrella en
directo**. El observatorio cuenta con el catálogo de 168 HADS del programa de
monitorización de **Patrick Wils** (VVS/AAVSO-VSX), y la infraestructura de
tránsitos (`core/transits.py`, bloque de plan, proyectos) es reutilizable —
pero los tránsitos son eventos predecibles (`t0 + n·P`) y las HADS no tienen
fase conocida en el catálogo: solo `Period_h` y el rango Max/Min.

**Decisión**:

1. **Nuevo tipo de objetivo `kind == "hads"`** con rama propia en planner,
   suggest (score + frases), theme, tabla, object card, proyectos y narrativa
   (mapa completo en `docs/PLANS/hads-stars.md`).
2. **Fuente híbrida (rev. 2026-09-11)**: la fuente de verdad es el **libro de
   Google Sheets de P. Wils** (público, una pestaña por año, **actualizado a
   diario**). La app lo descarga en runtime como XLSX (`export?format=xlsx`,
   una petición para todo el libro) a través de `core/db.py`
   (`SOURCE_TTL["hads"] = 12 h`), con parseo **solo stdlib**
   (`zipfile`+`xml.etree`; sin openpyxl en runtime) y **caché de dos niveles**
   (XLSX crudo + JSON parseado: el parseo de ~1-2 s ocurre una vez al día).
   El snapshot empaquetado `nightscribe/assets/HADS-stars.csv` (168 estrellas,
   aliases ricos, CRLF, campos con comillas; flags `multiperiodic`/`Non-radial`)
   queda como **respaldo offline** y fuente de aliases; el merge por
   coordenadas (< 1′) vive en `core/hads.py`. Si la red o el parseo fallan →
   snapshot puro (Tonight nunca se rompe). *(Primera versión de H-b: catálogo
   empaquetado sin red — descartada porque la hoja se actualiza a diario y un
   snapshot ataría la frescura de los datos a las releases de la app.)*
   La cobertura mensual llega fresca gratis en el mismo workbook (H-m).
2b. **Prioridades desde la leyenda de colores** (H-i): el color de fuente del
   XLSX — nombre rojo → `period_change` (+12 urgencia), naranja →
   `period_change_possible` (+8), coordenadas azules → `unobserved` (+6,
   H-k), nombre morado → `multiperiodic` (sin urgencia; noches consecutivas).
   Las señales de urgencia **no se apilan**: manda la mayor (máx. 20).
2c. **Cobertura mensual en v1** (H-m): celda vacía del mes actual en la
   pestaña del año en curso → «nadie la cubre este mes»: +10 urgencia +
   fragmento. Sin pestaña del año nuevo → `None` (ni bonus ni penalización).
3. **Sin fase → observación continua**: no se predice un "evento". El gate de
   observabilidad es visibilidad + **ventana contigua con ≥ 1 ciclo**; la
   recomendación es **captura continua de 2×P** (verlo repetir y plegar), con
   cadencia ≤ P/12 (cap 15 min reales, regla AAVSO) y ≥ 12 puntos por ciclo.
   Métrica clave: `cycles = hours_up / P`.
4. **mag del target = mediana** `(Max+Min)/2` para el filtro de magnitud (la
   fase es desconocida); el rango Max–Min y la amplitud siempre visibles en la
   ficha. `hads` se clasifica como **coordenadas fijas** en el flujo CCDciel.
5. **Reporte a AAVSO**: outcome de proyecto `reported_aavso` (paralelo de
   `reported_exoclock`); la config ya tiene `aavso_code`. Material narrativo
   que cita a Patrick Wils, VVS y VSX (refs [1]–[5], en `docs/HADS.md`).
6. **Fotometría en vivo = handoff FotoDif/AIJ + curva plegada** (H-l, rev.):
   FotoDif (modo AUTO) sigue la captura en directo y genera el informe AAVSO
   Extended File Format; NightScribe importa su salida (el parser
   `photometry_import` ya admite «JD - mag»), **pliega la curva por fase**
   con el P del catálogo (widget QGraphicsView + PNG matplotlib, paridad
   ADR-029) y la publica. **Monitor nativo en vivo: aparcado** (FotoDif AUTO
   ya lo cubre en el flujo real del observatorio).
7. **Generalización preparada, no incluida** (H-n): las variables de largo
   periodo y las campañas fotométricas de grupo serán un **track posterior
   independiente en su propia rama** (modelo: campaña = atributo ortogonal
   del proyecto + nuevo kind `variable`). Guardarraíles respetados aquí:
   Follow-up kind-agnóstico (`FOLLOWUP_KINDS`), plegado/plantilla agnósticos
   de kind, `sawtooth_template` con API genérica.

**Alternativas**: una fuente de red tipo `sources/vsx.py` para el catálogo
(rechazado en v1: el catálogo es curado, compacto y estable — empaquetarlo da
cero dependencia de red y funciona offline, filosofía del observatorio); un
"evento" con fase sintética (rechazado: inventar el máximo sería engañoso; la
ciencia del plegado y el «ver en directo» no necesita fase); ~~añadir la
cobertura mensual como urgencia en v1~~ (rev. 2026-09-11: **entra en v1**,
H-m — al llegar fresca en el mismo workbook diario ya no requiere refresco
manual); ~~monitor nativo en vivo~~ (aparcado: FotoDif AUTO lo cubre, H-l).

**Consecuencias**: nueva fuente `core/sources/hads_sheet.py` (red vía
`core/db.py`, TTL 12 h) + nuevo módulo `core/hads.py`; snapshot asset +
`package-data` en pyproject; nuevo kind en `KIND_ORDER`/`config.enabled_kinds`
(con migración amable del default heredado); ramas nuevas en ~15 puntos de
código (ver mapa); cadenas de GUI nuevas ES/EN vía `self.tr()` + lupdate; sin
cambios de esquema en la BD; el PDF de Kotysz no se commitea (9.7 MB) —quedan
URL + extractos en `docs/HADS.[es.]md`; los CSV de cobertura empaquetados
(`assets/hads-coverage/`) quedan como referencia histórica (el runtime usa la
cobertura viva del workbook). **Nota de ejecución**: `lupdate` no extrae
`self.tr()` dentro de llaves de f-string — las cadenas nuevas se escriben
como `tr()` plano + concatenación; quedan dos cadenas preexistentes de
tránsitos con ese agujero (pendiente de corrección fuera de este plan).

## English

**Context**: NightScribe plans the night, understands every object and tells
it. The current target families (NEO, SN, comets, PCCP, transits, alerts) do
not include high-amplitude variable stars, even though they are uniquely
educational and photometric targets: with ~1–5 h periods and ΔV ≥ 0.3 mag a
complete light curve fits in one night and you **watch the star pulsate live**.
The observatory has the 168-star HADS catalogue from **Patrick Wils'**
monitoring programme (VVS/AAVSO-VSX), and the transit infrastructure
(`core/transits.py`, plan block, projects) is reusable — but transits are
predictable events (`t0 + n·P`) while HADS have no known phase in the
catalogue: only `Period_h` and the Max/Min range.

**Decision**:

1. **New target `kind == "hads"`** with its own branch in the planner,
   suggest (scoring + phrases), theme, table, object card, projects and
   narrative (full map in `docs/PLANS/hads-stars.md`).
2. **Hybrid source (rev. 2026-09-11)**: the source of truth is **P. Wils'
   public Google Sheets workbook** (one tab per year, **updated daily**). The
   app downloads it at runtime as XLSX (`export?format=xlsx`, one request for
   the whole workbook) through `core/db.py` (`SOURCE_TTL["hads"] = 12 h`),
   parsed **stdlib-only** (`zipfile`+`xml.etree`; no openpyxl at runtime) with
   a **two-level cache** (raw XLSX + parsed JSON: the ~1-2 s parse happens
   once a day). The bundled snapshot `nightscribe/assets/HADS-stars.csv`
   (168 stars, rich aliases, CRLF, quoted fields; parseable
   `multiperiodic`/`Non-radial` flags) stays as the **offline fallback** and
   alias source; the coordinate merge (< 1′) lives in `core/hads.py`. Network
   or parse failure → pure snapshot (Tonight never breaks). *(First version
   of H-b: bundled, no network — dropped because the sheet is updated daily
   and a snapshot would tie data freshness to app releases.)* Monthly
   coverage arrives fresh for free in the same workbook (H-m).
2b. **Priorities from the color legend** (H-i): XLSX font color — red name →
   `period_change` (+12 urgency), orange → `period_change_possible` (+8),
   blue coordinates → `unobserved` (+6, H-k), purple name → `multiperiodic`
   (no urgency; consecutive nights). Urgency signals **never stack**: the
   strongest one rules (cap 20).
2c. **Monthly coverage in v1** (H-m): an empty current-month cell in the
   current-year tab → "nobody covers it this month": +10 urgency + fragment.
   A missing new-year tab → `None` (no bonus, no penalty).
3. **No phase → continuous observation**: no "event" is predicted. The
   observability gate is visibility + **contiguous window with ≥ 1 cycle**; the
   recommendation is **2×P continuous capture** (see it repeat and fold), with
   cadence ≤ P/12 (15-min real-world cap, AAVSO rule) and ≥ 12 points per
   cycle. Key metric: `cycles = hours_up / P`.
4. **Target mag = median** `(Max+Min)/2` for the magnitude filter (phase is
   unknown); the Max–Min range and amplitude always shown on the card. `hads`
   is classified as **fixed coordinates** in the CCDciel flow.
5. **AAVSO reporting**: project outcome `reported_aavso` (parallel to
   `reported_exoclock`); config already carries `aavso_code`. Narrative
   material citing Patrick Wils, VVS and VSX (refs [1]–[5], in
   `docs/HADS.md`).
6. **Live photometry = FotoDif/AIJ handoff + folded curve** (H-l, rev.):
   FotoDif (AUTO mode) watches the capture live and produces the AAVSO
   Extended File Format report; NightScribe imports its output (the
   `photometry_import` parser already accepts "JD - mag"), **folds the curve
   by phase** with the catalog period (QGraphicsView widget + matplotlib PNG,
   ADR-029 parity) and publishes it. **Native live monitor: parked**
   (FotoDif AUTO already covers it in the observatory's real workflow).
7. **Generalisation prepared, not included** (H-n): long-period variables
   and group photometric campaigns will be a **separate later track on its
   own branch** (model: campaign = orthogonal project attribute + a new
   `variable` kind). Guardrails respected here: kind-agnostic Follow-up
   (`FOLLOWUP_KINDS`), kind-agnostic fold/template, `sawtooth_template` with
   a generic API.

**Alternatives**: a network source like `sources/vsx.py` for the catalogue
(rejected for v1: it is curated, compact and stable — bundling gives zero
network dependency and works offline, the observatory philosophy); a
"predictable event" with a synthetic phase (rejected: inventing the maximum
would be misleading; the science of folding and "watching live" needs no
phase); ~~including monthly coverage as urgency in v1~~ (rev. 2026-09-11:
**in v1**, H-m — arriving fresh daily in the same workbook, no manual refresh
needed); ~~native live monitor~~ (parked: FotoDif AUTO covers it, H-l).

**Consequences**: new source `core/sources/hads_sheet.py` (network via
`core/db.py`, 12 h TTL) + new module `core/hads.py`; snapshot asset +
`package-data` in pyproject; new kind in `KIND_ORDER`/`config.enabled_kinds`
(with a friendly migration of the legacy default); new branches in ~15 code
points (see map); new ES/EN GUI strings via `self.tr()` + lupdate; no DB
schema changes; the Kotysz PDF is not committed (9.7 MB) — URL + extracts
live in `docs/HADS.[es.]md`; the bundled coverage CSVs
(`assets/hads-coverage/`) stay as historical reference (the runtime uses the
workbook's live coverage). **Execution note**: lupdate does not extract
`self.tr()` inside f-string braces — the new strings are written as plain
`tr()` + concatenation; two pre-existing transit strings carry that same
extraction hole (to be fixed outside this plan).