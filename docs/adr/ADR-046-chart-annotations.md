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
