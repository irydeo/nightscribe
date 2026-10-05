# ADR-046: Anotación de cartas: cajas de metadatos y estilo de marcador / chart annotation: metadata boxes and marker style

**Estado / Status**: Accepted · **Fecha / Date**: 2026-09-24 · **rev. 2026-09-25** (el anillo clásico gana su helper compartido `ring_marker_items`, gemelo de `cross_marker_items`; el ámbar de la familia de marcadores tiene una única fuente, `palette.ACCENT`)

**Ver / See**: ADR-044 (el UFE: su HUD y su exportación PNG; enmendado
aquí) · ADR-042 (la carta de secuencia fotométrica; enmendada aquí) ·
ADR-018 (el blink de SN; sus exportaciones ganan la capa aquí).

## Español

**Contexto.** Las cartas que el observatorio publica (la placa medida del
UFE, el blink de una SN, la carta de secuencia fotométrica) llevaban solo
el marcador del objeto y la marca de agua. Las cartas de seguimiento
clásicas (el ejemplo de referencia: las del Tycho Tracker) estampan en la
propia imagen todo lo que un reporte necesita: identificación, fecha,
posición, brillo, exposición, observador, estación, equipo y escala. Se
pidió esa capacidad con dos condiciones: no copiar la estética de nadie,
y que el marcador actual (anillo con ticks) siga disponible.

**Decisión.**

1. **Un solo ensamblador puro**: `core/chart_annotate.py` decide el
   contenido de las cajas aplicando las reglas de verdad: el nombre
   siempre; posición (AR/Dec sexagesimal vía `coords`), escala por
   píxel y FOV solo con solución astrométrica; el brillo solo cuando hay
   una medida calibrada en la sesión (una magnitud de catálogo del
   proyecto NO es una calibración de la placa); las líneas de sitio y
   equipo vacías simplemente se omiten. Las etiquetas son las
   abreviaturas estándar de reporte (RA, Dec, Date, Mag, Exp, Obs, Msr,
   Stn, Tel, PSc, FOV, Cam), neutras por idioma a propósito.
2. **Dos ajustes independientes** en Ajustes → Sitio y equipo (grupo
   «Anotación de cartas»): `marker_style` (`"ring"` clásico | `"cross"`,
   cruz a todo el campo con caja sobre el objeto) y `chart_boxes`
   (bool). Los valores por defecto (`ring`, `False`) dejan cada
   exportación exactamente como estaba. El grupo también gana los campos
   de identidad que faltaban: `observer_name`, `measurer_name` (vacío:
   cae al observador), `telescope_desc`, `camera_model`.
3. **Dos stacks de render, una fuente**: el UFE pinta las cajas como
   capa HUD en coordenadas de dispositivo (`UfeImageView._paint_boxes`,
   consultada al pintar vía `set_boxes_provider`, así resolver WCS o
   medir se reflejan sin cableado extra) y las estampa en el PNG
   exportado; un conmutador «Cajas» en la barra superior gobierna la
   visibilidad (su estado inicial sale de `chart_boxes` en cada show;
   en el modo de iconos de la barra el botón lleva el glifo `boxes`,
   ver ADR-044, rev. 2026-09-25).
   Con las cajas activas la rosa de los vientos baja al centro inferior
   y gana la pata E, y la barra de escala se mueve a la derecha: las
   esquinas quedan libres. matplotlib (`blink_view`) dibuja las mismas
   cajas como textos de esquina con fondo oscuro (el patrón del caption
   ya existente) en GIF, MP4 y el PNG antes/después.
4. **La posición del objeto en el UFE** sigue una cadena de verdad:
   centroide de la última medida → coordenadas del objeto adjunto →
   marca de objetivo movida en Secuencia → sin línea (un centro de campo
   no es el objeto). La cruz del estilo `cross` la dibujan las propias
   pestañas como ítems de escena (helper compartido
   `cross_marker_items` en `ufe_image_view.py`), así el export la
   recoge por el render de escena sin código duplicado. El anillo
   clásico (estilo `ring`) tiene su gemelo `ring_marker_items` (mismo
   contrato de ítems: 1 elipse + 4 ticks, pinceles cosméticos), lo
   llaman Blink, Anotar y Secuencia cada una a su tamaño y escala, y el
   ámbar de esta familia de marcadores pasa a tener una única fuente,
   `palette.ACCENT`: los colores locales duplicados se retiran y el
   color de apertura de Medir se une a la misma familia, sin cambio
   visual (rev. 2026-09-25).
5. **Blink**: las cajas llevan nombre, fecha, exposición, posición de la
   SN y la escala de la placa (PSc; el FOV se omite: los recortes de
   zoom lo harían mentira). El mini-compás N/E se calcula numéricamente
   del WCS del par (`compass_angles`), que ya casa con la orientación de
   los frames exportados (flip incluido). Los diálogos legacy no se
   tocan: sus exportaciones pasan por el mismo worker y heredan los
   ajustes; sus previews en pantalla quedan clásicas. En `draw_pair` el
   marcador se unifica con el de los frames (gana los 4 ticks; era el
   pato cojo) y las cajas se pintan solo en el panel «después», que es
   la placa del observador.
6. **Carta de secuencia** (ADR-042): misma capa en el widget Qt
   (`FinderChart._draw_boxes`, lee la config él mismo) y en
   `finder_view.draw_finder` (matplotlib, CLI `sequence`). Allí NO hay
   caja sup-izq con el nombre: el título de la carta ya lo lleva, y la
   rosa N/E ya posee la esquina sup-izq; solo se pintan sup-der
   (posición) e inf-izq (sitio, PSc, FOV).

**Consecuencias.** Toda carta exportada puede contar quién, qué, cuándo,
dónde y con qué, sin maquetación externa; el contenido sigue reglas
honestas (nada de brillo sin calibrar, nada de posición sin WCS, nada de
líneas vacías). Cambiar los ajustes con el UFE ya abierto no redibuja los
marcadores al instante: se aplica en la siguiente interacción o reapertura
(el toggle de cajas sí se relee en cada show). En el blink, la escala PSc
es la de la placa fuente cuando el llamador la conoce (UFE) y la del frame
de trabajo en los caminos legacy/CLI.

## English

**Context.** The charts the observatory publishes carried only the object
marker and the watermark. The classic tracker charts stamp everything a
report needs into the image itself: identification, epoch, position,
brightness, exposure, observer, station, equipment and scale. The feature
was requested with two conditions: copy nobody's aesthetics, and keep the
current marker (ring with ticks) available.

**Decision.** (1) One pure assembler, `core/chart_annotate.py`, owns the
box-content rules: the name always; position, pixel scale and FOV only
with an astrometric solution; brightness only with a calibrated
measurement from the session (a project catalog magnitude is NOT a
calibration of the plate); empty site/equipment fields omit their line.
Labels are the standard report abbreviations, language-neutral on
purpose. (2) Two independent settings (Site & equipment, "Chart
annotations" group): `marker_style` (`"ring"` | `"cross"`, the cross
being a full-frame crosshair with a box on the object) and `chart_boxes`
(bool); defaults (`ring`, off) leave every export as it was. The group
also gains the missing identity fields: `observer_name`,
`measurer_name` (empty falls back to the observer), `telescope_desc`,
`camera_model`. (3) One source, two renderers: the UFE paints the boxes
as a device-coordinates HUD layer (`_paint_boxes`, consulted at paint
time through `set_boxes_provider`, so a solve or a measurement shows up
with no extra wiring) and stamps them into the exported PNG; a "Boxes"
top-bar toggle governs visibility (its initial state comes from
`chart_boxes` at every show; in the bar's icon mode the button
carries the `boxes` glyph, see ADR-044, rev. 2026-09-25). With the boxes on, the compass moves to
the bottom centre and gains the east leg, and the scale bar moves right:
the corners stay free. matplotlib (`blink_view`) draws the same boxes as
dark-backed corner texts (the existing caption pattern) on GIF, MP4 and
the before/after PNG. (4) The object position in the UFE follows a truth
chain: last measurement centroid, attached object coordinates, moved
Sequence target mark, or no line at all (a field centre is not the
object). The `cross` marker is drawn by the tabs themselves as scene
items (shared `cross_marker_items` helper), so the export picks it up
through the scene render. The classic ring (the `ring` style) gets its
twin `ring_marker_items` (same item contract: 1 ellipse + 4 ticks,
cosmetic pens), called by the Blink, Annotate and Sequence tabs each
at their own size and scale, and the amber of this marker family gets
a single source, `palette.ACCENT`: the duplicated local colours are
retired and the Measure tab's aperture colour joins the same family,
with zero visual change (rev. 2026-09-25). (5) Blink boxes carry name, date, exposure, SN
position and the plate scale (FOV omitted: the zoom crops would make it
a lie); the N/E mini-compass is computed numerically from the pair's WCS
(`compass_angles`), which already matches the exported frames, flip
included. The legacy dialogs stay untouched: their exports flow through
the same worker and inherit the settings; their on-screen previews stay
classic. `draw_pair`'s marker is unified with the frames' (it gains the
four ticks; it was the odd one out) and the boxes paint on the "after"
panel only, which is the observer's plate. (6) The sequence chart
(ADR-042) gets the same layer in both the Qt widget and the matplotlib
export; no top-left name box there: the chart title already carries it
and the N/E compass owns that corner.

**Consequences.** Every exported chart can state who, what, when, where
and with what, with no external layout work, and the content follows
honest rules (no uncalibrated brightness, no position without WCS, no
empty lines). Changing the settings with the UFE already open does not
redraw the markers instantly: they apply on the next interaction or
reopen (the boxes toggle is re-read at every show). In the blink, the
PSc scale is the source plate's when the caller knows it (the UFE), and
the work frame's on the legacy/CLI paths.

**Revisión (2026-09-30): la placa dice lo suyo en una banda, no en cajas**. Se pidió
repensar las cajas: el mismo estilo que la banda que ya encabeza la imagen (nombre,
coordenadas, magnitud), con lo que faltaba (exposición, Stn, PSc, FOV) y **un color por
dato**, para no copiar la estética de las cartas clásicas. Lo que cambia:

- **El UFE deja de tener cajas de esquina**: `UfeImageView._paint_boxes` desaparece y
  `core/chart_annotate.build_band` alimenta una **banda de dos líneas** en la parte
  alta de la placa, dentro de la misma placa oscura. Línea 1 (identidad): objeto,
  posición y magnitud. Línea 2 (contexto): fecha, exposición, filtro, equipo,
  estación, escala y campo de visión. Las cajas de esquina **siguen existiendo** en las
  otras cartas (el blink GIF/MP4 y la carta de secuencia), que no se tocan.
- **Un color por rol**, decidido en el módulo puro y mapeado por el render
  (`BAND_COLOURS`): `name` y `pos` en tinta (lo coloca la propia solución de esta
  placa), `pos-cat` apagado y con la palabra `cat` (es la posición del catálogo, no la
  de esta placa; el color no basta en un papel), y `context` apagado.
- **La magnitud tiene escala propia, de tres estados más el catálogo** (revisión
  2026-09-30, a petición del observador): **verde** (`palette.GOOD`) cuando la medida
  está limpia: error ≤ 0,05, más de tres comparsas sosteniendo el punto cero,
  estrella de chequeo que pasa, núcleo sin recortar y sin avisos; **naranja**
  (`palette.FAIR`) cuando es usable pero no limpia: error ≤ 0,15, o exactamente tres
  comparsas, o la magnitud derivada de un color, o la secuencia sin estrella de
  chequeo, o un aviso del propio punto; **rojo** (`palette.DANGER`) cuando no es una
  medida que se deba reportar sin mirarla: error > 0,15, menos de tres comparsas,
  chequeo que dice que la noche no va, o núcleo recortado; y **blanco**
  (`palette.CATALOG`) cuando es un valor de catálogo, que no es una medida de esta
  placa. Las señales son las que la receta ya calcula; los umbrales (0,05 y 0,15) son
  la línea entre «una placa suelta honrada» y «esto no se reporta sin mirar».
- **La magnitud de la banda es la que se ha medido**, en este orden: el punto de la
  curva de la visita **de esa toma** (el flujo normal: se mide la serie, no una placa),
  después una medida de placa de esta placa, y solo entonces el catálogo, en blanco.
  Así el color no miente por omisión cuando lo medido es una serie.
- **Nunca se corta una palabra**: cuando el ancho no da, se sueltan campos enteros en
  `DROP_ORDER` (`fov`, `psc`, `equip`, `filter`, `stn`, `date`: lo menos necesario para
  un reporte primero, la fecha la última) y, en el peor caso, la línea 2 entera; la
  línea 1 pierde la magnitud y luego la posición, y solo se elide un nombre que no cabe
  ni solo. La línea de contexto va un punto más pequeña y sin negrita: está para leerse,
  no para competir con el nombre de la placa. El equipo se acota a **10 caracteres** (un
  nombre de cámara puede ser un serial de 31 y se comía el FOV; 10 dicen SXV-H18,
  ASI2600 o QHY42PRO, y el valor completo sigue en la cabecera y en las otras cartas), y
  el fondo de la banda es opaco a propósito (205 de 255): sobre un campo brillante, la
  primera versión se perdía.
- **De dónde sale cada cosa**: el nombre del proyecto (o del fichero), la fecha, la
  exposición, el filtro y el equipo **de la cabecera de la propia toma** (el equipo de
  la toma gana al de Ajustes y no se mezclan: su cámara con mi telescopio sería una
  mentira peor que cualquiera de las dos), la estación de Ajustes, la posición, la
  escala y el FOV de la solución de la placa, y la magnitud solo de una medida de esta
  sesión.
- **Ajuste nuevo `chart_data`** (por defecto activado) para lo que dice la banda;
  `chart_boxes` (por defecto desactivado) pasa a gobernar solo las cajas de las otras
  cartas. La rosa de los vientos y la barra de escala vuelven a sus sitios clásicos
  (arriba a la derecha bajo la banda, abajo a la izquierda): ya no hay esquinas que
  liberar.

**Revisión (2026-10-05): la banda de un stack de asteroide dice su movimiento.** Al
apilar una secuencia de un asteroide (ADR-062), la banda que ya encabeza la placa añade
lo que el run ha medido, con las mismas reglas de color:

- **Línea 1 (identidad)**: nombre, **posición medida**, magnitud medida, **velocidad y
  PA**. La posición medida (el centroide astrométrico de esa placa) gana a la del
  catálogo colocada por la solución: es de esta placa, así que va en tinta y sin el
  `(cat)`. La velocidad y el PA llevan el mismo color por rol: `motion` en tinta cuando
  el barrido de velocidad los midió, y `motion-eph` apagado y con la palabra `(eph)`
  cuando solo son la predicción de la efeméride (simétrico a `pos` / `pos-cat` y a
  `mag` / `mag-cat`). El formato es el de `viz/motion_view` (`1.23″/min PA 245°`).
- **Línea 2 (contexto)**: la exposición de un stack se escribe **«N × T s»** (las tomas
  que combina por su exposición), no una exposición suelta que ocultaría cuánta luz hay.
  `format_exposure` lo decide y `n_frames` viaja dentro de `meta`.
- **Orden de descarte**: en la línea 1 el movimiento se suelta primero (es el relato, no
  la identidad), luego la magnitud y por último la posición (`DROP_ORDER_NAME`).
- **De dónde salen los datos del stack**: se escriben en la **cabecera del propio
  stack** cuando el run lo guarda (`gui/ufe_trackstack_tab.py`): `NS_RATE` / `NS_PA` /
  `NS_MOT` (el movimiento medido o predicho), `NS_MAG` / `NS_MAGER` / `NS_MAGB` /
  `NS_MAGNC` / `NS_MAGOK` (la magnitud de esa observación con las señales que la
  colorean) y, copiadas del frame, `EXPTIME` / `DATE-OBS` / `FILTER` / `INSTRUME` /
  `TELESCOP` (sin ellas un stack no tenía fecha, exposición ni filtro). La posición
  medida ya viajaba como `NS_RA` / `NS_DEC` (la anotación). Así la banda dice lo mismo
  recién hecho el run y meses después, sin la base de datos y sin el run en memoria. El
  stack de estrellas lleva el movimiento pero nunca la magnitud: allí el objeto es una
  traza y no se midió.

**Revision (2026-09-30): the plate says its own thing in a band, not in boxes**. The
boxes were to be rethought: the same style as the band that already heads the image
(name, coordinates, magnitude), with what was missing (exposure, Stn, PSc, FOV) and
**a colour per datum**, so as not to copy the classic charts' look. What changes:

- **The UFE has no corner boxes any more**: `UfeImageView._paint_boxes` is gone and
  `core/chart_annotate.build_band` feeds a **two-line band** at the top of the plate,
  inside the same dark plaque. Line 1 (identity): object, position and magnitude. Line
  2 (context): date, exposure, filter, equipment, station, scale and field of view.
  The corner boxes **still exist** in the other charts (the blink GIF/MP4 and the
  sequence chart), which are untouched.
- **A colour per role**, decided in the pure module and mapped by the render
  (`BAND_COLOURS`): `name` and `pos` in ink (this plate's own solution places it),
  `pos-cat` dimmed and with the word `cat` (it is the catalogue's position, not this
  plate's; colour alone is not enough on a printout), and `context` dimmed.
- **The magnitude has a scale of its own: three states plus the catalogue** (revision
  2026-09-30, asked for by the observer): **green** (`palette.GOOD`) when the
  measurement is clean: error ≤ 0.05, more than three comparisons holding the zero
  point, a check star that passes, a core that is not clipped and no flags;
  **orange** (`palette.FAIR`) when it is usable but not clean: error ≤ 0.15, or exactly
  three comparisons, or a magnitude derived from a colour, or a sequence with no check
  star, or a flag on the point itself; **red** (`palette.DANGER`) when it is not a
  measurement to report without looking: error > 0.15, fewer than three comparisons, a
  check star that says the night is off, or a clipped core; and **white**
  (`palette.CATALOG`) when it is a catalogue value, which is not a measurement of this
  plate. The signals are the ones the recipe already computes; the thresholds (0.05 and
  0.15) are the line between "a single plate's honest error" and "do not report this
  without looking".
- **The band's magnitude is the one that has been measured**, in this order: the visit
  curve's point **for that frame** (the normal flow: a series is measured, not one
  plate), then a single-plate measurement of this plate, and only then the catalogue,
  in white. The colour cannot lie by omission when what was measured is a series.
- **A word is never cut**: when the width runs out, whole fields are dropped in
  `DROP_ORDER` (`fov`, `psc`, `equip`, `filter`, `stn`, `date`: the least needed for a
  report first, the date last) and, in the worst case, line 2 entirely; line 1 loses
  the magnitude and then the position, and only a name that does not fit even alone is
  elided. The context line is a point smaller and not bold: it is there to be read, not
  to compete with the plate's name. The equipment is capped at **10 characters** (a
  camera name can be a 31-character serial and it was eating the FOV; 10 say SXV-H18,
  ASI2600 or QHY42PRO, and the full value stays in the header and in the other charts),
  and the band's plaque is opaque on purpose (205 of 255): over a bright field the first
  version was lost.
- **Where each datum comes from**: the name from the project (or the file), the date,
  exposure, filter and equipment **from the plate's own header** (the frame's kit wins
  over the Settings and the two are never mixed: his camera with my telescope would be
  a worse lie than either), the station from the Settings, the position, scale and FOV
  from the plate's solution, and the magnitude only from a measurement of this session.
- **New `chart_data` setting** (on by default) for what the band says; `chart_boxes`
  (off by default) now governs the other charts' boxes only. The compass and the scale
  bar return to their classic spots (top right under the band, bottom left): there are
  no corners to free any more.

**Revision (2026-10-05): an asteroid stack's band says its motion.** When a sequence of
an asteroid is stacked (ADR-062), the band that already heads the plate adds what the
run measured, under the same colour rules:

- **Line 1 (identity)**: name, **measured position**, measured magnitude, **velocity
  and PA**. The measured position (that plate's astrometric centroid) beats the
  catalogue's placed by the solution: it is this plate's, so it wears the ink and no
  `(cat)`. Velocity and PA follow the same colour-per-role: `motion` in ink when the
  velocity sweep measured them, and `motion-eph` dimmed with the word `(eph)` when they
  are only the ephemeris' prediction (symmetric to `pos` / `pos-cat` and `mag` /
  `mag-cat`). The format is `viz/motion_view`'s (`1.23″/min PA 245°`).
- **Line 2 (context)**: a stack's exposure is written **"N × T s"** (the frames it
  combines times their exposure), not a bare exposure that would hide how much light
  there is. `format_exposure` decides it and `n_frames` travels inside `meta`.
- **Drop order**: on line 1 the motion goes first (it is the story, not the identity),
  then the magnitude and the position last (`DROP_ORDER_NAME`).
- **Where a stack's data comes from**: it is written into the **stack's own header**
  when the run saves it (`gui/ufe_trackstack_tab.py`): `NS_RATE` / `NS_PA` / `NS_MOT`
  (the measured or predicted motion), `NS_MAG` / `NS_MAGER` / `NS_MAGB` / `NS_MAGNC` /
  `NS_MAGOK` (that observation's brightness with the signals that colour it) and, copied
  from the frame, `EXPTIME` / `DATE-OBS` / `FILTER` / `INSTRUME` / `TELESCOP` (without
  them a stack had no date, exposure or filter). The measured position already travelled
  as `NS_RA` / `NS_DEC` (the annotation). So the band says the same right after the run
  and months later, with no database and no run in memory. The star stack carries the
  motion but never the magnitude: there the object is a trail and was not measured.
