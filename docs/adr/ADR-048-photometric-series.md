# ADR-048: Photometric series measured frame by frame (T1–T8)

**Estado / Status**: Accepted · **Fecha / Date**: 2026-09-27 · **rev. 2026-09-28**
(revisión en profundidad del track: el error del punto cero nunca baja del
suelo que marcan la dispersión y los errores de catálogo de las comps; los
pesos del detrend son 1/σ (antes quedaban 1/σ⁴ efectivos); el FWHM se mide
por toma y mediana por grupo; el warp marca `align_edge`/`align_failed` y un
run cancelado persiste `incomplete` de verdad / deep review of the track: the
zero-point error never beats the floor set by the comps' scatter and
catalogue errors; the detrend weights are 1/σ (they used to come out 1/σ⁴
effective); the FWHM is measured per frame, median per group; the warp flags
`align_edge`/`align_failed` and a cancelled run truly persists `incomplete`)

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
  el estado de la ejecución.
- **Guardado automático por punto con `run_id` persistido** y acción «Deshacer esta
  ejecución» que revive reinicios; la serie cancelada deja el estado «incompleta»
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
  catálogo; guardia de banda; cada noche una ejecución con su Undo; la agregación por
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

## Revisión (2026-09-28): navegación de tomas y reducción desde el editor

**Contexto**: la serie y la reducción EXOTIC necesitaban la astrometría y la
secuencia de comparación, pero el editor abría siempre la **primera** toma, sin
forma de recorrer la visita, y los botones de EXOTIC vivían en la pestaña Análisis,
lejos de la secuencia que necesitan: si no la habías construido, la reducción
fallaba con «no hay estrellas de comparación». Además, al abrir el editor desde una
visita no se cargaba la secuencia ya guardada del proyecto.

**Decisión**:

- **Navegador de tomas** en el panel izquierdo del editor (visible con la visita
  armada): anterior/siguiente, `toma i/N`, nombre del fichero y «primera toma»
  (Av/Re Pág). Cargar una toma la deja como placa abierta, y **la toma abierta es
  la referencia** de la serie y del handoff EXOTIC (objetivo y comparsas en sus
  píxeles). Al cambiar de toma se conserva el estado de la pestaña Compare
  (campo y secuencia: las estrellas son RA/Dec y se recolocan por WCS).
- **Bloque EXOTIC en el editor**, solo en proyectos de tránsito con visita:
  «Reduce and fit with EXOTIC…» y «Export to EXOTIC (inits.json)…», con la
  secuencia a mano. Se desactiva y explica qué falta hasta que hay comparsas.
  La pestaña Análisis deja un acceso que abre la visita en el editor.
- **Cargar la secuencia guardada**: al abrir desde una visita/proyecto, si la
  placa no trae estado propio, se restaura `ctx["sequence"]` en la pestaña Compare
  (el estado de la placa siempre gana, ADR-047).

**Consecuencias**: el flujo serie/tránsito ya no manda al usuario a ciegas; la
reducción usa lo que tiene delante. La referencia del handoff es la toma abierta:
con dithering, EXOTIC debe respetar esos píxeles (valida la placa resuelta que ya
guardamos, ADR-051 rev.); si no, la referencia del handoff volvería a la primera
toma, aunque la serie sí usaría la abierta.

## Revision (2026-09-28): frame navigation and reduction from the editor

**Context**: the series and the EXOTIC reduction needed the astrometry and the
comparison sequence, but the editor always opened the **first** frame, with no way
to walk the visit, and the EXOTIC buttons lived in the Analysis tab, far from the
sequence they need: without it built, the reduction failed with "no comparison
stars". Worse, opening the editor from a visit did not load the sequence already
saved in the project.

**Decision**:

- **Frame navigator** in the editor's left panel (visible with the visit armed):
  previous/next, `frame i/N`, the file name and "first frame" (PageUp/PageDown).
  Loading a frame makes it the open plate, and **the open frame is the reference**
  of the series and the EXOTIC handoff (target and comps in its pixels). Changing
  frames preserves the Compare tab's state (field and sequence: the stars are
  RA/Dec and are re-placed through the WCS).
- **EXOTIC block in the editor**, only for transit projects opened from a visit:
  "Reduce and fit with EXOTIC…" and "Export to EXOTIC (inits.json)…", with the
  sequence at hand. It disables itself and says what is missing until there are
  comps. The Analysis tab keeps a door that opens the visit in the editor.
- **Load the saved sequence**: opening from a visit/project, when the plate
  carries no state of its own, restores `ctx["sequence"]` into the Compare tab
  (the plate's own state always wins, ADR-047).

**Consequences**: the series/transit flow no longer sends the observer in blind;
the reduction uses what is in front of them. The handoff reference is the open
frame: with dithering, EXOTIC must respect those pixels (the persisted plate
solution of ADR-051 rev. validates it); otherwise the handoff reference would go
back to the first frame, while the series would still use the open one.

**Revisión (2026-09-28, la secuencia sobrevive a la navegación)**: al cambiar de
toma, la pestaña Compare re-proyecta la secuencia en la nueva placa. Antes se
**descartaban** las estrellas que no se podían situar (una toma sin WCS, o una
estrella fuera del marco por el dithering), así que moverse entre frames borraba la
secuencia ("0 stars, 0 in the sequence"). Ahora la secuencia es RA/Dec y se
**conserva entera**: solo las que se pueden situar reciben píxel y overlay, las
demás se quedan como entradas sin posición (la serie y el handoff EXOTIC las usan
igual). El mensaje cuenta "N en la secuencia (M situadas en esta toma)". Además, al
cargar una toma sin WCS se reutiliza la **solución cacheada** por hash (aunque
`solve_save` esté apagado y el FITS no se escriba), así que volver a una toma ya
resuelta la vuelve a situar sin re-resolver.

**Revision (2026-09-28, the sequence survives navigation)**: switching frames makes
the Compare tab re-project the sequence onto the new plate. It used to **drop** the
stars it could not place (a frame with no WCS, or a star off-frame from dithering),
so walking the frames erased the sequence ("0 stars, 0 in the sequence"). The
sequence is RA/Dec and is now **kept whole**: only the placeable stars get a pixel
and an overlay, the rest stay as entries without a position (the series and the
EXOTIC handoff use them all the same). The message reads "N in the sequence (M
placed on this frame)". A plate loaded without a WCS also reuses the **cached
solution** by hash (even with `solve_save` off, when the FITS is not written), so
returning to an already solved frame places the sequence again without re-solving.

**Revisión (2026-09-28, la secuencia se guarda sola)**: antes la secuencia solo se
persistía al exportar el CSV o al guardar una medida, así que cerrar y volver a
abrir la visita obligaba a reconstruir las comparsas. Ahora, cuando el observador
la construye o la cambia (proponer, añadir/quitar, cambiar tipo, vaciar) se guarda
en el **contexto del proyecto** (con la magnitud del objetivo), y al abrir la visita
se restaura. El estado propio de la placa sigue ganando (ADR-047), pero si no trae
secuencia ya no bloquea la del proyecto.

**Revision (2026-09-28, the sequence saves itself)**: the sequence used to be stored
only on CSV export or when saving a measurement, so closing and reopening the visit
meant rebuilding the comps. Now, when the observer builds or tweaks it (propose,
add/remove, change kind, clear) it is stored in the **project context** (with the
target magnitude), and restored when the visit opens. A plate's own state still
wins (ADR-047), but a saved state without a sequence no longer blocks the project's.

**Revisión (2026-09-28, comparsas editables a mano)**: la comunidad pedía poder
corregir una comparación. La tabla de la secuencia ahora trae columnas **Banda**
(combo editable) y **Magnitud** (spinbox): al cambiarlas se reescribe el valor de
esa banda en `star["bands"]` (`derived=False`, origen «manual»), así que
`photometry.band_of` y la calibración usan el valor manual; el combo de banda de
Medir se refresca al instante. El resto de bandas del catálogo se conservan.

**Revision (2026-09-28, hand-editable comps)**: the community asked to correct a
comparison. The sequence table now has **Band** (editable combo) and **Magnitude**
(spinbox) columns: editing them rewrites that band's value in `star["bands"]`
(`derived=False`, origin "manual"), so `photometry.band_of` and the calibration use
the manual value; the Measure band combo refreshes at once. The star's other
catalog bands are kept.

## Revisión (2026-09-29, D17/D44): la alineación por frame deja de ser opt-in

**Contexto**: una serie real del grupo ObSN (V0526 Per, 244 tomas de 40 s, sin WCS
en la cabecera) derivó **134" (87 px)** en 2.9 h. El motor medía a las coordenadas
de la placa de referencia, así que la estrella salió de la apertura de 6 px en menos
de un minuto y la curva quedó en un rango de 8 magnitudes con `err` = 0.5 mag: el
caso que abrió `docs/PLANS/series-quality.md`.

Medido con el motor real sobre esas tomas:

| | antes | después |
|---|---|---|
| puntos medibles | 5 de 244 (3 `unusable`) | **244** |
| rango de la curva | 8 mag | 0.06 mag |
| correlación con el informe del observador (FotoDif), 244 frames | 0.32 | **0.899** |
| residuo contra ese informe | 0.13 mag | **0.0094 mag** |
| estrella de control | | 0.005 mag |
| ritmo | 4.6 s/frame y sin converger | **0.23 s/frame** |

**Decisión**:

- **La alineación está encendida por defecto** (`align="auto"` en el diálogo
  Avanzado; `off`, `translation`, `similarity`, `warp` y `coords` siguen ahí) y
  queda registrada en `measurement_runs.cfg_json`. D17 describía un mundo donde
  todas las tomas traían WCS: en la práctica casi ninguna lo trae, y suponerlo es
  como perder la serie.
- **`coords` es el modo de `auto`**: cada frame se mide en su rejilla nativa con la
  WCS por frame compuesta, de modo que la PSF nunca se remuestrea; `warp` y
  `similarity` (que sí remuestrean) quedan como vías explícitas.
- **El registro es una cascada, no una búsqueda a ciegas** (`core/register.py`,
  numpy puro): se quita el cielo (medianas por bloques, que es lo que envenenaba la
  FFT con el viñeteo), las **estrellas votan** la transformación (para cada rotación
  candidata, cada par implica una traslación y gana la que más pares independientes
  confirma), y sólo si la traslación no explica las estrellas se ajusta la rigidez
  (lstsq + sigma-clip). La anterior búsqueda de ángulo por correlación de fase
  devolvía −166° con `quality` 43.8 sobre estas tomas y la aceptaba en silencio: el
  `peak/std` no discrimina. **Se jubila `QUALITY_MIN` como criterio**: la calidad es
  ahora **física** (`register.trusted`: nº de estrellas emparejadas y rms en px).
- **Una rotación tiene que ganarse el sitio**: sólo entra si reduce el residuo real
  ≥ 25 %; y una traslación que sólo ajusta las estrellas del centro (donde una
  rotación es invisible) no cuenta: los pares deben **cubrir el campo**
  (`_MIN_SPREAD`).
- **Un frame que no se puede verificar hereda la transformación anterior y se marca**
  `align_failed` (nunca se mide con una suposición): se acabó el `guide_jump` en
  todos los frames, que además era un defecto real (en `coords`, el centroide nunca
  se remapeaba a la referencia: el remapeo vivía dentro de la rama de `warp`).
- **El punto cero se ata por comparada** (`_tie_comps`): el residuo de catálogo de
  cada estrella es estable en el tiempo y, cuando una comp sale del campo o se
  satura, la mediana de las que quedan **saltaba** (0.23 mag en este set). Ahora cada
  comp mide su propio nivel y el punto cero deja de depender de quién estaba
  presente. La estrella de **chequeo nunca entra en el punto cero** (es el monitor).
  Los desacuerdos entre comps se **dicen** en el panel, no se esconden.
- **El motor dice lo que no sabe**: avisos en lenguaje llano de en qué han quedado
  las tomas, de la deriva, del residuo de las estrellas, de las comps que nunca
  entraron en el marco o están saturadas y de la ganancia que falta (sin ella la
  barra de error es la dispersión de las comps, no la ecuación del CCD).
- **Válvula de seguridad por noche y por tipo**: `chk_seeing` pasa el FWHM por frame
  a la receta en serie (H3) y, para `variable`/`hads`, el detrend por defecto es el
  mínimo honesto de masa de aire (D11).

**Alternativas**: añadir `astroalign`/`photutils`/`ccdproc` (rechazado: `autophot`
exige `TELESCOP`/`INSTRUME`/`FILTER` en la cabecera, justo lo que estos FITS no
tienen, y son 20+ dependencias conda; `astroalign` sólo por sí solo traería scipy y
la resolución aquí es una traslación + una rotación pequeña, que numpy resuelve en
0.23 s/frame); seguir con la alineación opt-in (rechazado: es la causa del
desastre); dejar el aviso del desacuerdo de comps sólo en el log (rechazado: C4).

**Consecuencias**: la calidad de una secuencia queda a la altura de la placa única
(0.0094 mag de residuo contra una reducción independiente); el coste es una etapa de
registro de ~0.15 s/frame (2 % del total) y la obligación de decir en el panel en qué
han quedado las tomas. `QUALITY_MIN` desaparece como puerta y aparece
`register.trusted`. La fixture de regresión (`tests/data/v0526per/`, 8 frames
recortados reales) guarda el caso para que no vuelva.

## Revision (2026-09-29, D17/D44): per-frame alignment stops being opt-in

**Context**: a real series from the ObSN group (V0526 Per, 244 frames of 40 s, no
WCS in the header) drifted **134" (87 px)** in 2.9 h. The engine measured at the
reference plate's coordinates, so the star left the 6 px aperture in under a minute
and the curve came out across 8 magnitudes with `err` = 0.5 mag: the case that
opened `docs/PLANS/series-quality.md`.

Measured with the real engine on those frames:

| | before | after |
|---|---|---|
| measurable points | 5 of 244 (3 `unusable`) | **244** |
| curve range | 8 mag | 0.06 mag |
| correlation with the observer's own reduction (FotoDif), 244 frames | 0.32 | **0.899** |
| residual against that reduction | 0.13 mag | **0.0094 mag** |
| check star | | 0.005 mag |
| speed | 4.6 s/frame and not converging | **0.23 s/frame** |

**Decision**:

- **Alignment is on by default** (`align="auto"` in the Advanced dialog; `off`,
  `translation`, `similarity`, `warp` and `coords` all remain) and is recorded in
  `measurement_runs.cfg_json`. D17 described a world where every frame carried a
  WCS: in practice almost none does, and assuming it is how a series is lost.
- **`auto` means `coords`**: each frame is measured on its native grid with the
  composed per-frame WCS, so the PSF is never resampled; `warp` and `similarity`
  (which do resample) stay as explicit choices.
- **Registration is a cascade, not a blind search** (`core/register.py`, pure
  numpy): the sky is removed (block medians, which is what used to poison the FFT
  with vignetting), the **stars vote** the transform (for every candidate rotation
  every pair implies a translation, and the one most independent pairs agree on
  wins), and only when the translation cannot explain the stars does a rigid fit
  enter (lstsq + sigma-clip). The old phase-correlation angle search answered
  −166° with `quality` 43.8 on these frames and accepted it in silence: `peak/std`
  does not discriminate. **`QUALITY_MIN` is retired as the gate**: quality is now
  **physical** (`register.trusted`: matched-star count and rms in px).
- **A rotation has to earn its place**: it enters only when it removes ≥ 25 % of the
  real residual; and a translation that only fits the stars near the centre (where
  a rotation is invisible) does not count: the pairs must **span the frame**
  (`_MIN_SPREAD`).
- **A frame that cannot be verified inherits the previous transform and is flagged**
  `align_failed` (never measured on a guess); the `guide_jump` firing on every frame
  is gone, and it was a real defect too (under `coords` the centroid was never
  mapped back to the reference: the mapping lived inside the `warp` branch).
- **The zero point is tied per comparison star** (`_tie_comps`): a comp's catalogue
  residual is stable in time, and when one leaves the frame or saturates the median
  of the rest used to **jump** (0.23 mag on this set). Each comp now measures its
  own level and the zero point no longer depends on who was present. The **check
  star never enters the zero point** (it is the monitor). Disagreements between
  comps are **said** in the panel, never hidden.
- **The engine says what it does not know**: plain-language notes on what happened
  to the frames, the drift, the star residual, the comps that never entered the
  sensor or are saturated, and the missing gain (without it the error bar is the
  scatter of the comps, not the CCD equation).
- **Safety valves per night and per type**: `chk_seeing` passes each frame's FWHM
  to the series recipe (H3) and, for `variable`/`hads`, the default detrend is the
  honest airmass minimum (D11).

**Alternatives**: adding `astroalign`/`photutils`/`ccdproc` (rejected: `autophot`
requires `TELESCOP`/`INSTRUME`/`FILTER` in the header, exactly what these FITS lack,
and brings 20+ conda dependencies; `astroalign` alone would drag scipy in, while
the geometry here is a translation plus a small rotation that numpy solves in
0.23 s/frame); keeping alignment opt-in (rejected: it is the cause of the desastre);
keeping the comp-disagreement warning in the log only (rejected: C4).

**Consequences**: a series now reaches single-plate quality (0.0094 mag residual
against an independent reduction); the cost is a ~0.15 s/frame registration stage
(2 % of the total) and the duty to tell the observer, in the panel, what became of
the frames. `QUALITY_MIN` is gone as a gate and `register.trusted` takes its place.
The regression fixture (`tests/data/v0526per/`, 8 cropped real frames) keeps the
case from coming back.

