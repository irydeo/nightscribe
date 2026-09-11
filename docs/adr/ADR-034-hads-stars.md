# ADR-034: Estrellas HADS como objetivo de la noche — catálogo empaquetado, observación continua sin fase

**Estado / Status**: Accepted · **Fecha / Date**: 2026-09-11

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
2. **Catálogo empaquetado, sin red**: `nightscribe/assets/HADS-stars.csv`
   (168 estrellas: `Name,RA,DEC,Max,Min,Period_h`; ASCII, CRLF, campos con
   comillas; flags parseables `multiperiodic`/`Non-radial`). Carga por el
   patrón `Path(__file__).parent.parent / "assets"` (igual que `moon_disk.png`).
   El instalador ya recoge `nightscribe/assets/*`; se añade el `package-data`
   en `pyproject.toml`. La cobertura mensual del programa de Wils
   (`assets/hads-coverage/HADS-Project-YYYY.csv`, 2011–2026) queda
   **empaquetada como dato de referencia** para un stretch de urgencia.
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

**Alternativas**: una fuente de red tipo `sources/vsx.py` para el catálogo
(rechazado en v1: el catálogo es curado, compacto y estable — empaquetarlo da
cero dependencia de red y funciona offline, filosofía del observatorio); un
"evento" con fase sintética (rechazado: inventar el máximo sería engañoso; la
ciencia del plegado y el «ver en directo» no necesita fase); añadir la
cobertura mensual como urgencia en v1 (diferido: es una foto fija que requiere
refresco manual documentado).

**Consecuencias**: nuevo asset + `package-data` en pyproject; nuevo kind en
`KIND_ORDER`/`config.enabled_kinds` (con migración amable del default
heredado); ramas nuevas en ~15 puntos de código (ver mapa); cadenas de GUI
nuevas ES/EN vía `self.tr()` + lupdate; sin cambios de esquema en la BD; el
PDF de Kotysz no se commitea (9.7 MB) —quedan URL + extractos en
`docs/HADS.[es.]md`; la cobertura mensual dormita como datos de referencia
hasta el stretch.

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
2. **Bundled catalogue, no network**: `nightscribe/assets/HADS-stars.csv`
   (168 stars: `Name,RA,DEC,Max,Min,Period_h`; ASCII, CRLF, quoted fields;
   parseable `multiperiodic`/`Non-radial` flags). Loaded with the
   `Path(__file__).parent.parent / "assets"` pattern (same as `moon_disk.png`).
   The installer already collects `nightscribe/assets/*`; `package-data` is
   added to `pyproject.toml`. Wils' monthly coverage
   (`assets/hads-coverage/HADS-Project-YYYY.csv`, 2011–2026) is **bundled as
   reference data** for an urgency stretch.
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

**Alternatives**: a network source like `sources/vsx.py` for the catalogue
(rejected for v1: it is curated, compact and stable — bundling gives zero
network dependency and works offline, the observatory philosophy); a
"predictable event" with a synthetic phase (rejected: inventing the maximum
would be misleading; the science of folding and "watching live" needs no
phase); including monthly coverage as urgency in v1 (deferred: it is a
snapshot that needs documented manual refresh).

**Consequences**: new asset + `package-data` in pyproject; new kind in
`KIND_ORDER`/`config.enabled_kinds` (with a friendly migration of the legacy
default); new branches in ~15 code points (see map); new ES/EN GUI strings via
`self.tr()` + lupdate; no DB schema changes; the Kotysz PDF is not committed
(9.7 MB) — URL + extracts live in `docs/HADS.[es.]md`; the monthly coverage
rests as reference data until the stretch.