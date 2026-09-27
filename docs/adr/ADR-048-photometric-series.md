# ADR-048: Photometric series measured frame by frame (T1–T8)

**Estado / Status**: Accepted · **Fecha / Date**: 2026-09-27

## Español

**Contexto**: la pestaña Fotometría del Editor FITS mide una placa con calidad de
investigación (piezas H1–H7), pero la serie se queda en el quicklook de
`core/series.py`. `PRECISION.es.md` (apéndice B) define las piezas **T1–T8** para
tránsitos, SN y variables, y exige reabrir ADR-015 antes de código. El plan completo
es `docs/PLANS/series-photometry.md` (registro D1–D39, trece fases).

**Decisión**: medir la serie como una serie, con la misma receta que la placa.

- **Motor**: `core/series_measure.py`, alimentado por `core/photometry.measure_plate`
  (la receta de la placa única extraída de la GUI en la fase 1; una sola receta, una
  sola precisión).
- **Registro opt-in**: para sets sin WCS ni frames alineados, `core/register.py` alinea cada
  frame a la referencia (rotación sobre el centro + traslación subpíxel, por correlación de
  fase, numpy puro) y `SeriesConfig.align="similarity"` lo activa; por defecto apagado (D17).
- **Agnóstico por parámetros**: `SeriesConfig(zp_mode="catalog"|"relative",
  detrend_policy="off"|"airmass"|"auto", host_ref, comp_set, ...)`; **ninguna rama
  `if kind`**: los tipos (tránsito, variable, SN, HADS) cambian parámetros y las
  reglas de la capa de análisis, no el motor.
- **Punto cero por frame** (T1), **ensemble ponderado con veto MAD** por frame (T2),
  **puertas por frame** que marcan y **nunca borran** (T7: saturación, salto de
  guiado, cósmico, nube) y **error total honesto** con el centilleo integrado sobre
  el span temporal del grupo (T4).
- **Detrend** `a1·exp(a2·X)+a3` con `a1` analítico (receta de EXOTIC, citada; ni una
  línea de su código): la curva **cruda siempre visible junto a la detrendada**, los
  coeficientes en el panel de resumen, en la columna `notes` del CSV y en la meta de
  la serie. Sin columnas nuevas salvo `mag_raw REAL`, `flags TEXT` y `run_id` en
  `photometry_points` (migración v12), más la tabla `measurement_runs` con la configuración y
  el estado de la corrida.
- **Guardado automático por punto con `run_id` persistido** y acción «Deshacer esta
  corrida» que revive reinicios; la serie cancelada deja el estado «incompleta»
  visible (`measurement_runs.status`); presupuesto <0,5 s por frame y UI responsive con 142 frames.
- **Entrada desde la visita**: el botón «Medir la secuencia» solo existe con visita
  de proyecto (nunca diálogo de carpeta, nunca UFE ad-hoc); para llegar con un
  listado existe «Añadir ficheros a la visita» (selección múltiple).
- **Interfaz** (ADR-005): bloque de serie en `ufe_measure_tab.ui`, `LightCurveChart`
  compacto embebido en la pestaña (cruda + detrendada + marcados, leyenda por
  noche, binning solo de visualización); knobs de serie en `UfeAdvancedDialog`
  (default visible, tooltip con unidades y razón, restaurar), parámetros de sitio en
  Configuración (ADR-028).
- **Multinoche**: detrend local por noche con señal global compartida (reparto
  `glc_fitter` de EXOTIC; fallback a `a1` solo en noches cortas, dicho en el panel);
  set de comps fijo desde la noche de referencia; chequeo de ZP por noche vs.
  catálogo; guardia de banda; cada noche una corrida con su Undo; la agregación por
  objetivo la hace Análisis (D33/D36 del plan, sin reimplementar plegado).
- **Guardia de cadencia** en la capa de análisis: aviso con las reglas por tipo
  (tránsitos ≥3 puntos por ingress, HADS 12 puntos y tope de cadencia, variables
  Nyquist); rojo si se rompe el ingress; `group_n=1` por defecto en tránsitos y
  variables.
- **Validación ahora** (D12/D39): dip de 0,01 mag a ±0,001 mag; seno de 0,3 mag en
  2 h sin distorsión; SN con gradiente de galaxia al 1 %; serie de dos noches con 3 %
  de transparencia desplazada.
- **Documentación de usuario**: `docs/SEQUENCES.es.md` + `docs/SEQUENCES.md`.

**Alternativas**: medir desde una carpeta suelta (rechazado: sin contexto de
proyecto no hay undo, ni análisis, ni agregación); previsualizar y confirmar
(rechazado: la curva a medias no se puede evaluar, y el mal punto se corrige con
flags y undo); detrend con scipy (vetado por ADR-004); una receta aparte para
series (rechazado: dos recetas serían dos precisiones).

**Consecuencias**: T1–T8 se validan con pruebas sintéticas de semilla antes que con
datos reales; los puntos marcados siguen siendo datos honestos y exportables; la
migración v12 es mínima e idempotente; SN, variables y HADS entran por parámetros,
sin código propio; el rendimiento de la serie pasa a ser un presupuesto medible.

## English

**Context**: the FITS editor's Photometry tab measures one plate to research
quality (pieces H1–H7), but the series stays at the `core/series.py` quick-look.
`PRECISION.md` (appendix B) defines pieces **T1–T8** for transits, SNe and
variables, and requires reopening ADR-015 before any code. The full plan is
`docs/PLANS/series-photometry.md` (register D1–D39, thirteen phases).

**Decision**: measure the series as a series, with the same recipe as the plate.

- **Engine**: `core/series_measure.py`, fed by `core/photometry.measure_plate`
  (the single-plate recipe extracted from the GUI in phase 1; one recipe, one
  precision).
- **Opt-in registration**: for sets without WCS or aligned frames, `core/register.py`
  aligns each frame to the reference (rotation about the centre plus subpixel
  translation, by phase correlation, pure numpy) and `SeriesConfig.align="similarity"`
  turns it on; off by default (D17).
- **Kind-agnostic by parameters**: `SeriesConfig(zp_mode="catalog"|"relative",
  detrend_policy="off"|"airmass"|"auto", host_ref, comp_set, ...)`; **no `if kind`
  branch**: the types change parameters and the analysis-layer rules, not the
  engine.
- **Per-frame zero point** (T1), **weighted ensemble with per-frame MAD veto**
  (T2), **per-frame gates** that flag and **never delete** (T7: saturation, guide
  jump, cosmic ray, cloud) and an **honest total error** with scintillation
  integrated over the group's time span (T4).
- **Detrend** `a1·exp(a2·X)+a3` with analytic `a1` (EXOTIC's recipe, cited; not one
  line of its code): the **raw curve always visible next to the detrended one**,
  coefficients in the summary panel, in the CSV `notes` column and in the series
  meta. No new columns beyond `mag_raw REAL`, `flags TEXT` and `run_id` in
  `photometry_points` (migration v12), plus the `measurement_runs` table holding the run's
  configuration and status.
- **Auto-save per point with a persisted `run_id`** and an "Undo this run" action
  that survives restarts; a cancelled series shows a visible "incomplete" state
  (`measurement_runs.status`); budget <0.5 s per frame and a responsive UI on 142 frames.
- **Entry from the visit**: the "Measure sequence" button exists only with a
  project visit (never a folder dialog, never an ad-hoc FITS); "Add files to the
  visit" (multi-select) is how a file list gets there.
- **Interface** (ADR-005): sequence block in `ufe_measure_tab.ui`, compact
  `LightCurveChart` embedded in the tab (raw + detrended + flagged, legend per
  night, display-only binning); series knobs in `UfeAdvancedDialog` (default
  shown, tooltip with units and reason, restore), site parameters in Settings
  (ADR-028).
- **Multi-night**: detrend local per night over a shared global signal (EXOTIC's
  `glc_fitter` split; `a1`-only fallback on short nights, said in the panel); comp
  set fixed from the reference night; per-night ZP check against the catalogue;
  band guard; one run per night with its own Undo; the analysis view aggregates by
  target (no re-implemented folding).
- **Cadence guard** in the analysis layer: warning with per-type rules (transits
  ≥3 points per ingress, HADS 12 points and cadence cap, variables Nyquist); red if
  the ingress breaks; `group_n=1` by default for transits and variables.
- **Validated now**: 0.01 mag dip recovered to ±0.001 mag; a pure 0.3 mag/2 h sine
  undistorted; an SN host gradient recovered to 1 %; a two-night series with 3 %
  transparency offset.
- **User documentation**: `docs/SEQUENCES.es.md` + `docs/SEQUENCES.md`.

**Alternatives**: measure from a loose folder (rejected: no project context means
no undo, no analysis, no aggregation); preview-then-confirm (rejected: a half
curve cannot be judged, flags and undo do that job better); scipy detrend (vetoed
by ADR-004); a separate series recipe (rejected: two recipes mean two precisions).

**Consequences**: T1–T8 validate against seeded synthetic data before real data;
flagged points stay honest, exportable data; migration v12 is minimal and
idempotent; SN, variables and HADS enter through parameters with no type-specific
code; series performance becomes a measurable budget.
