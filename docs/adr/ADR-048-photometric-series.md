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

## Revisión (2026-09-29, la ganancia, la escala y el seeing): lo que hacía ilegibles las curvas

**Contexto**: con la alineación arreglada, la serie real seguía sin poder leerse. Tres
causas distintas, medidas:

1. **La ganancia no se podía introducir.** `ccd_gain` y `ccd_read_noise` estaban
   declaradas en la configuración y las leían tres módulos (la ecuación del CCD, la
   receta de la placa y el «full well ≈ X ADU at your gain» del panel de cámara),
   pero **ningún control de Ajustes las escribía**. Sin ganancia el error de un punto
   es la dispersión de las comparadas: 0.17 mag en esta serie.
2. **La gráfica dibujaba ese sistemático 244 veces.** Las barras de error tenían 0.17
   mag de media sobre una curva que varía 0.12: el panel entero eran barras. Y los
   ejes ponían una sola cifra decimal («12.5», «60297.8»), distinta para cada punto.
3. **Los frames 189-191 no eran una nube.** El cielo no se movió (4015 → 4020 ADU),
   el pico cayó un factor 4 y la FWHM pasó de 3.3 a 8.8 px: un **desenfoque**. El
   motor los marcaba `cloud` (o nada) y, con la apertura fija, perdían 0.75 mag.

**Decisión**:

- **`core/gain.py`**: la ganancia y el ruido de lectura se **miden en las propias
  tomas**. Dos tomas a la misma exposición dan `var(F1−F2) = 2·nivel/g + 2·RON²/g²`,
  así que una recta ajustada sobre cajas de cielo robustas da la ganancia (la
  pendiente) y el ruido de lectura (el término constante). Un segundo par a otro
  nivel abre la palanca y fija el RON; con un solo nivel se mide la ganancia y **se
  dice** que el RON queda desconocido. Medido en la serie real: **0.772 ± 0.002
  e-/ADU** con 473 de 475 cajas limpias.
- **Ajustes gana los dos campos** (Ajustes → perfil de cámara), con el ruido de
  lectura precargado del preset (es un dato de datasheet) y la ganancia nunca
  (depende de la unidad y del ajuste). El panel dice en vivo qué implica.
- **Cadena de prioridad**: Ajustes → cabecera del FITS (`GAIN`/`EGAIN`/`CCDGAIN`,
  `RDNOISE`/`READNOIS`/`RON`) → **estimada de las propias tomas** → ninguna. El valor,
  su origen y su incertidumbre viajan en el `cfg_json` de la ejecución y el panel lo
  dice en lenguaje llano. **Nunca** se escribe en Ajustes a espaldas del observador.
- **El punto guarda su propio error** (`photometry_points.err_internal`, migración
  **v13**): `err` sigue siendo el total, que es lo que ven AAVSO y el CSV.
- **La escala es robusta** (mediana ± 6 sigmas robustas, intersectada con el dato, más
  un 10 % de aire): un punto anómalo ya no aplasta la curva. Los que caen fuera se
  anclan al borde con una marca, nunca se esconden. Las etiquetas de los ejes llevan
  las cifras decimales que pide el rango.
- **La barra es el fotón, el sistemático es una banda.** Cuando el sistemático es más
  ancho que la ventana no se dibuja (llenaría el panel): lo dice la leyenda.
- **Las banderas se separan**: una bandera de DATO (saturado, cósmico, desenfoque,
  nube, sin alinear) es el rombo hueco de siempre; un AVISO de calibración (pocas
  comparsas) es el marcador normal con un borde ámbar tenue, para que una secuencia
  con pocas comps no parezca una secuencia con 200 puntos malos. «Ocultar marcados»
  oculta sólo los primeros y viene apagado (T7).
- **La apertura sigue el seeing de verdad**: los radios del observador son los de la
  **FWHM de referencia** y cada toma los escala por la suya (con topes). La FWHM de
  la toma alimenta además el ajuste gaussiano del centroide. La toma 190 pasa de
  desviarse 0.049 a 0.017 mag y su error baja un tercio.
- **`seeing` es una bandera nueva** (FWHM fuera del rango robusto de su noche), y
  `cloud` sólo salta cuando el punto cero se mueve **y** la PSF no se ha movido, que
  es lo que es una nube.
- **El análisis es robusto como puede serlo una curva periódica**: el recorte
  pliega la curva con el período de la primera pasada y descarta lo que se sale de su
  propio bin de fase, y vuelve a buscar. Se probó primero el recorte sobre la serie
  temporal y **se rechazó con medidas**: sobre una variable limpia de 0.3 mag se
  llevaba el 7 % de la curva y seguía sin aislar el punto salvaje. El diálogo de
  período gana las dos casillas (dejar fuera los marcados, descartar atípicos).

**Alternativas**: pedir la ganancia al observador sin darle forma de medirla
(rechazado: es lo que había); recortar la barra sin separar el sistemático
(rechazado: mezcla dos cosas distintas en el mismo símbolo); un recorte de atípicos
sobre la serie temporal (rechazado con medidas, arriba); llamar «nube» a un
desenfoque (rechazado: manda al observador a mirar lo que no es).

**Consecuencias**: `err_internal` pasa de inexistente a **0.0052 mag** en la serie
real, así que la gráfica se lee y el error dice la verdad (el total de 0.176 mag es
el sistemático, y ahora se ve como banda). Queda una deuda declarada: la **propuesta
de comparsas** debe validarse contra la placa del observador (saturación, linealidad,
rectángulo del sensor, SNR), no sólo contra el catálogo.

## Revision (2026-09-29, the gain, the scale and the seeing): what made the curves unreadable

**Context**: with alignment fixed, the real series was still unreadable. Three
different causes, measured:

1. **The gain could not be entered.** `ccd_gain` and `ccd_read_noise` were declared
   in the config and read by three modules (the CCD equation, the plate recipe and
   the camera panel's "full well ≈ X ADU at your gain"), but **no Settings control
   ever wrote them**. Without a gain a point's error is the scatter of the
   comparison stars: 0.17 mag on this series.
2. **The chart drew that systematic 244 times.** The error bars averaged 0.17 mag on
   a curve that varies 0.12: the whole panel was bars. And the axes printed a single
   decimal ("12.5", "60297.8"), the same for every point.
3. **Frames 189-191 were not a cloud.** The sky did not move (4015 → 4020 ADU), the
   peak fell by a factor of four and the FWHM went from 3.3 to 8.8 px: a **focus
   excursion**. The engine flagged them `cloud` (when it flagged them at all) and,
   with a fixed aperture, they lost 0.75 mag.

**Decision**:

- **`core/gain.py`**: the gain and the read noise are **measured on the frames
  themselves**. Two frames at the same exposure give
  `var(F1−F2) = 2·level/g + 2·ron²/g²`, so a line fitted over robust sky boxes
  yields the gain (the slope) and the read noise (the intercept). A second pair at
  another level widens the lever arm and pins the read noise; with one level only the
  gain comes out and the module **says** the read noise stays unknown. Measured on
  the real series: **0.772 ± 0.002 e-/ADU**, 473 of 475 boxes clean.
- **Settings gains the two fields** (Settings → camera profile), with the read noise
  filled from the preset (a datasheet fact) and the gain never (per unit and per gain
  setting). The panel says live what it implies.
- **Priority chain**: settings → the FITS header (`GAIN`/`EGAIN`/`CCDGAIN`,
  `RDNOISE`/`READNOIS`/`RON`) → **measured on the frames** → none. The value, its
  origin and its uncertainty travel in the run's `cfg_json` and the panel says it in
  plain language. It is **never** written into Settings behind the observer's back.
- **A point keeps its own error** (`photometry_points.err_internal`, migration
  **v13**): `err` stays the total, which is what AAVSO and the CSV see.
- **The scale is robust** (median ± 6 robust sigmas, intersected with the data, 10 %
  of air): an anomalous point can no longer flatten the curve. The ones outside are
  anchored to the edge with a caret, never hidden. The axis labels carry as many
  decimals as the span needs.
- **The bar is the photon, the systematic is a band.** When the systematic is wider
  than the window it is not drawn (it would fill the panel): the legend says it.
- **Flags are split**: a DATA flag (saturated, cosmic, focus, cloud, unaligned) is
  the hollow diamond it always was; a calibration CAVEAT (few comps) is the normal
  marker with a faint amber edge, so a thin comp set does not read as 200 bad points.
  "Hide flagged" hides only the first and is off by default (T7).
- **The aperture follows the seeing for real**: the observer's radii belong to the
  **reference FWHM** and each frame scales them by its own (within limits). The
  frame's FWHM also feeds the centroid's Gaussian fit. Frame 190's deviation drops
  from 0.049 to 0.017 mag and its error by a third.
- **`seeing` is a new flag** (FWHM outside its night's robust range), and `cloud`
  only fires when the zero point moves **and** the PSF did not, which is what a cloud
  is.
- **The analysis is robust the way a periodic curve can be**: the clip folds the
  curve by the first pass's period and rejects what leaves its own phase bin, then
  searches again. A clip on the time series was tried first and **rejected on
  measurements**: on a clean 0.3 mag variable it threw away 7 % of the curve and
  still could not isolate one wild point. The period dialog gains the two switches
  (leave out the flagged points, reject outliers).

**Alternatives**: asking for the gain without giving a way to measure it (rejected:
that was the state); clipping the bar without separating the systematic (rejected:
two different things in one symbol); an outlier clip on the time series (rejected on
measurements, above); calling a focus excursion a cloud (rejected: it sends the
observer to look at the wrong thing).

**Consequences**: `err_internal` goes from non-existent to **0.0052 mag** on the real
series, so the chart reads and the error tells the truth (the 0.176 mag total is the
systematic, and it now shows as a band). One debt is declared: the **comparison
proposal** must be validated against the observer's plate (saturation, linearity,
sensor rectangle, SNR), not only against the catalogue.

## Revisión (2026-09-29, comparsas validadas y la curva de la comunidad)

**Decisión** (cierre de la deuda anterior, más la D del plan):

- **`compstars.validate_on_plate`**: cada candidata se mide en la **placa abierta** y
  se descarta con su motivo: fuera del sensor (con margen de seguridad), anillo de
  cielo fuera del marco, saturada, por encima de la linealidad de la cámara, o
  demasiado débil (pico por debajo de 12 sigmas de cielo, o SNR de flujo por debajo
  de 30, el real cuando hay ganancia y un proxy honesto en ADU cuando no).
  `propose_comps` acepta un `validator` y devuelve la lista de descartes con su
  motivo; el núcleo sigue sin Qt y sin placa, y un validador falso ejercita los cinco
  veredictos en los tests. El panel de la pestaña Compare dice cuántas se han dejado
  fuera y por qué. El caso real (4 de 9 saturadas, 1 fuera del sensor) es justo lo
  que esto devuelve.
- **El campo es el rectángulo REAL del sensor**, no un cuadrado: 43' en una cámara de
  1663 × 1252 son 43' × 32', y el cuadrado proponía estrellas que el sensor no ve.
  Ambos lados se encogen además por un anillo de seguridad de 90" para que la deriva
  de la noche no se lleve una comp del borde.
- **La curva de la comunidad (AAVSO)**: `sources/aavso.py` gana
  `fetch_lightcurve(name, token, days, bands)` (toda la curva de la estrella, con sus
  errores, su banda y si el punto es una estimación visual; caché 12 h; el mismo
  token que las vigilias). El diálogo de período la añade y la pliega **con** la
  curva propia: en gris y hueca, nunca mezclada, con las visuales ponderadas
  conservadoramente. Es la vía para fijar el período de una sola noche, y es como se
  hizo el informe de referencia.
- **La búsqueda escala**: añadir una década de historia a una noche pedía cientos de
  miles de frecuencias y el bootstrap lo multiplicaba por 120 (medido: un minuto
  congelado). La rejilla tiene tope (`GRID_MAX`) con el sobremuestreo relajado y el
  tope **dicho**; el bootstrap y los niveles de FAP del gráfico reciben un
  presupuesto de trabajo que elige su rejilla y **compara el pico observado en esa
  misma rejilla**; el PDM tiene su propio tope y la ventana espectral está
  vectorizada. El mismo caso responde en 3-4 s.

## Revision (2026-09-29, validated comps and the community curve)

**Decision** (closing the debt above, plus phase D of the plan):

- **`compstars.validate_on_plate`**: every candidate is measured on the **open
  plate** and rejected with its reason: outside the sensor (with a safety margin),
  its sky annulus off the frame, saturated, above the camera's linearity limit, or
  too faint (a peak below 12 sky sigmas, or a flux SNR below 30, the real one when a
  gain is known and an honest ADU proxy when not). `propose_comps` takes a
  `validator` and returns the rejected list with the reason; the core stays free of
  Qt and of the plate, and a fake validator exercises the five verdicts in the tests.
  The Compare tab's panel says how many were left out and why. The real case (4 of 9
  saturated, 1 off-sensor) is exactly what this returns.
- **The field is the REAL sensor rectangle**, not a square: 43' on a 1663 x 1252
  camera is 43' x 32', and the square proposed stars the sensor never shows. Both
  sides also shrink by a 90" safety ring so the night's drift cannot lose a comp at
  the very edge.
- **The community curve (AAVSO)**: `sources/aavso.py` gains
  `fetch_lightcurve(name, token, days, bands)` (the star's whole curve, with its
  errors, its band and whether the point is a visual estimate; cached 12 h; the same
  token the vigils use). The period dialog adds it and folds it **with** the
  observer's own curve: grey and hollow, never mixed, with visual estimates weighted
  conservatively. It is how a one-night period gets fixed, and how the reference
  report was made.
- **The search scales**: adding a decade of history to one night asked for hundreds
  of thousands of frequencies and the bootstrap multiplied that by 120 (measured: a
  minute frozen). The grid is capped (`GRID_MAX`) with the oversampling relaxed and
  the cap **said**; the bootstrap and the plot's FAP levels get a work budget that
  picks their grid and **compares the observed peak on that same grid**; the PDM has
  its own cap and the spectral window is vectorised. The same case answers in 3-4 s.


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


**Revisión (2026-09-29, puntos sin magnitud)**: el resumen de campaña del Análisis
pasaba a `analyze_campaign` todos los puntos guardados, y un punto con `mag = None`
(una medida rechazada, importada o a mano) rompía la pestaña en su primera apertura
(`min()` comparaba `None` con `float`). Ahora `analyze_campaign` se queda con los
puntos que tienen `mjd` y `mag` numéricos, devuelve `no_data` si no queda ninguno y
cuenta los usados (`points`); el resumen dice cuántos se ignoraron. Ninguna fila
mala tumba ya la página.

**Revision (2026-09-29, points without a magnitude)**: the Analysis campaign summary
fed `analyze_campaign` every saved point, and a point with `mag = None` (a rejected
measure, an imported row, a hand entry) broke the tab on its first open (`min()`
compared `None` with `float`). `analyze_campaign` now keeps only the points with a
numeric `mjd` and `mag`, returns `no_data` when none is left and reports the used
count (`points`); the summary says how many were ignored. No bad row breaks the page
anymore.


**Revisión (2026-09-30, una noche es UNA curva)**: la gráfica de una visita
dibujaba TODAS sus ejecuciones a la vez. Medido en la base real (V0526 Per,
30 de septiembre): la visita 18 guardaba cuatro pasadas, 976 puntos, en dos
niveles distintos (11.96–12.07 calibrados en G y 12.70–12.81 en V) unidos por
un zigzag, mientras la gráfica en vivo había dibujado una sola ejecución
(244 puntos). Se veía «al cerrar y volver a cargar el programa» porque al
reabrir la visita se lee la curva del proyecto; el gráfico del proyecto, el
*sparkline*, el informe y el diálogo de período unían las pasadas igual (el
proyecto 113: 1014 puntos en la base para una curva de 282; el 96: 1255 para
284, dos noches de 142).

La regla pasa a estar escrita y en un solo sitio (`followup.curve_run_ids`):
**la curva de una noche es la ejecución que la visita marca y, si no marcó
ninguna, la de su última medida** (`MAX(id)`, el orden en que se midió). Los
puntos sin ejecución (a mano, pegados, de survey) no son una remedida y
siempre están. La visita recuerda su elección en `project_sessions.curve_run_id`
(migración v15, con el patrón idempotente de la v9–v14) y una ejecución nueva
la mueve a sí misma: medir otra vez manda, que es lo que la gráfica en vivo
enseñaba. Deshacer la última pasada cae a la anterior, que es lo que se espera
de un Undo.

Como guardar las pasadas sin poder volver a ninguna no tiene sentido (lo
preguntó el observador), entra la puerta **Serie ▾ → Pasadas de esta visita…**:
la lista con hora, banda, puntos, tramo de noche y estado, la que está dibujada
en negrita, y dos acciones por fila, «que sea la curva» (sin borrar nada) y
«deshacer esta pasada» (sus puntos se van, la fila queda marcada). El panel de
la visita dice qué pasada dibuja y cuántas más guarda.

Dos cosas más que la recarga tenía mal: la banda de la leyenda y del fichero
AAVSO es **la que usó la calibración** (los puntos de una serie real no traían
`FILTER` y una curva en G decía «sin filtro», y el cargador forzaba «V»), y la
curva **detrended** se reajusta al cargar (`series_measure.detrend_stored`,
determinista: los mismos puntos con la misma masa de aire dan los mismos
coeficientes). Una sesión en vivo pasa a ser UNA ejecución (sus lotes se
añaden a la que abrió el primero): era lo que el propio test declaraba y lo que
el host real no cumplía, y sin ello la curva recargada de una sesión en vivo
habría sido solo su último lote.

**Revision (2026-09-30, one night is ONE curve)**: a visit's chart drew EVERY
run of the visit at once. Measured on the real database (V0526 Per, 30
September): visit 18 held four passes, 976 points, at two different levels
(11.96–12.07 calibrated in G and 12.70–12.81 in V) joined by a zigzag, while
the live chart had drawn one run (244 points). It showed up "when closing and
reloading the program" because reopening a visit reads the curve from the
project; the project's chart, the sparkline, the report and the period dialog
added the passes up in the same way (project 113: 1014 points in the database
for a curve of 282; project 96: 1255 for 284, two nights of 142).

The rule is now written down and in one place (`followup.curve_run_ids`): **the
curve of a night is the run the visit marks and, if it marked none, the one its
last measurement belongs to** (`MAX(id)`, insertion order). Points with no run
(hand-entered, pasted, survey) are not a re-measurement and always belong to
it. The visit remembers its choice in `project_sessions.curve_run_id` (v15
migration, the idempotent v9–v14 pattern) and a new run moves it to itself:
measuring again rules, which is what the live chart showed. Undoing the last
pass falls back to the previous one, which is what an Undo is for.

Since keeping the passes with no way back to any of them makes no sense (the
observer asked), the door **Series ▾ → Passes of this visit…** comes in: the
list with time, band, points, stretch of night and state, the drawn one in
bold, and two actions per row, "make this the curve" (deleting nothing) and
"undo this pass" (its points go, the row stays marked). The visit's panel says
which pass it draws and how many more it holds.

Two more things the reload got wrong: the band in the legend and in the AAVSO
file is **the one the calibration used** (the points of a real series carried no
`FILTER` and a curve in G said "no filter", and the loader forced "V"), and the
**detrended** curve is refitted on load (`series_measure.detrend_stored`,
deterministic: the same points with the same airmass give the same
coefficients). A live session is now ONE run (its batches append to the one the
first opened): that is what the test itself declared and what the real host did
not honour, and without it the curve reloaded from a live session would have
been only its last batch.


**Revisión (2026-09-30, una serie multinoche en UNA pasada)**: el bloque de
serie medía solo las tomas de la visita abierta, así que una campaña de cinco
noches eran cinco aperturas, cinco pasadas y cinco curvas sueltas (el
observador acabó con cuatro pasadas de la misma noche en su V0526 Per). El
motor, en cambio, ya era multinoche: el detrend se ajusta por noche, el ZP
vecino y las nubes son por noche y `night_qc` informa por noche.

Entra un **alcance** en el bloque (`cmb_series_scope`, «this visit» / «all
visits»), ofrecido solo cuando el proyecto tiene más de una visita con tomas
(el host lo dice en el contexto, `visits`). Con «all visits» el contexto son
las tomas de **todas** las visitas, y el host archiva **una ejecución por
visita**: cada toma lleva sus puntos a la visita que le corresponde (resuelta
por su fila en `project_files`), así que la curva de la visita sigue siendo su
noche y la del proyecto es la unión de las noches (una pasada por noche, la
regla del 2026-09-30 de arriba). Las ejecuciones de una misma pasada comparten
un grupo en su cfg (`series.pass.group`, sin esquema nuevo: es el patrón que
ya usaba `save_pass` con las campañas) y **el Undo deshace la pasada entera**
(`run_pass_group` / `runs_in_pass`), que es lo que el observador midió de una
vez. La puerta de pasadas dice a qué pasada pertenece cada noche.

El modo en vivo se queda en una visita (vigila una carpeta) y con «all
visits» se apaga diciendo por qué; «descartar la curva» también es por visita
y con «all visits» se deshabilita explicándolo. Y el gráfico de UFE carga la
curva **del alcance**: con «all visits», la del proyecto, con el detrend
reajustado **por ejecución** (una noche, una política).

**Revision (2026-09-30, a multi-night series in ONE pass)**: the series block
measured only the frames of the open visit, so a five-night campaign meant
five openings, five passes and five loose curves (the observer ended up with
four passes of the same night in his V0526 Per). The engine, on the other
hand, was already multi-night: the detrend is fitted per night, the neighbour
ZP and the clouds are per night and `night_qc` reports per night.

A **scope** lands in the block (`cmb_series_scope`, "this visit" / "all
visits"), offered only when the project has more than one visit with frames
(the host says so in the context, `visits`). With "all visits" the context is
the frames of **every** visit, and the host files **one run per visit**: each
frame's points go to the visit it belongs to (resolved by its row in
`project_files`), so a visit's curve is still its night and the project's is
the union of the nights (one pass per night, the rule above from 2026-09-30).
The runs of one pass share a group in their cfg (`series.pass.group`, no
schema change: it is the pattern `save_pass` already used for campaigns) and
**Undo removes the whole pass** (`run_pass_group` / `runs_in_pass`), which is
what the observer measured in one go. The passes door says which pass each
night belongs to.

Live mode stays per visit (it watches one folder) and with "all visits" it is
turned off saying why; "discard the curve" is per visit too and with "all
visits" it is disabled and explains itself. And the UFE chart loads the
curve of the **scope**: with "all visits", the project's, with the detrend
refitted **per run** (one night, one policy).


**Revisión (2026-09-30, un fotograma, una medida)**: la regla anterior («la
curva de una noche es la ejecución que la visita marca, o la última») se
quedaba corta con los datos reales: las 244 tomas de la visita 18 estaban
medidas otra vez como visitas 20 (35 tomas) y 21 (3), **todas dentro** de las
244, así que la unión por visitas daba 282 puntos con 38 duplicados a dos
niveles (12.79-12.83 junto a 11.96-12.06). La invariante que faltaba es la
que el observador reportó dos veces: **una curva nunca enseña el mismo
fotograma dos veces**.

`followup.curve_point_ids` es ahora el único lector: la clave de un fotograma
es su **ruta** (no la fila del registro, porque el mismo fichero puede estar
registrado en dos visitas: son dos filas y un solo fotograma) con su noche, y
gana la medida de id más alto, que es la más reciente. La **curva del
proyecto** (`list_points`) es la unión objetiva, sin la elección de ninguna
visita en medio; la **curva de la visita** (`points_for_session`) honra su
pasada elegida y rellena los fotogramas que esa pasada no cubre con su medida
más reciente (una noche medida en dos pasadas es una curva). El `file_id` de
cada punto se resuelve por (ruta, visita) y el tab manda la visita de cada
toma en su fila, así que una toma registrada en dos visitas archiva su punto
en la suya y no en la que aparezca última. Medido sobre su base: la curva del
proyecto 113 pasa de 282 a **244** puntos (una noche, 244 fotogramas) y la
del 96 de 284 a 142.

**Revision (2026-09-30, one frame, one measurement)**: the previous rule ("a
night's curve is the run the visit marks, or the last one") fell short on the
real data: the 244 frames of visit 18 had been measured again as visits 20
(35 frames) and 21 (3), **every one inside** the 244, so the per-visit union
gave 282 points with 38 of them duplicated at two levels (12.79-12.83 next to
11.96-12.06). The invariant that was missing is the one the observer reported
twice: **a curve never shows the same frame twice**.

`followup.curve_point_ids` is now the only reader: a frame's key is its
**path** (not the registry row, because the same file can be registered in
two visits: two rows, one frame) with its night, and the highest point id
wins, which is the newest measurement. The **project's curve**
(`list_points`) is the objective union, with no visit's choice in the middle;
the **visit's curve** (`points_for_session`) honours its chosen pass and
fills the frames that pass does not cover with their newest measurement (a
night measured in two passes is one curve). Each point's `file_id` is
resolved by (path, visit) and the tab sends each frame's visit in its row, so
a frame registered in two visits files its point in its own and not in
whichever came last. Measured on his database: project 113's curve goes from
282 to **244** points (one night, 244 frames) and project 96's from 284 to
142.
