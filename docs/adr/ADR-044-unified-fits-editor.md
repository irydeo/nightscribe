# ADR-044: Editor FITS unificado (UFE): una ventana, una pestaña por funcionalidad, escena en píxeles de placa

**Estado / Status**: Accepted · **Fecha / Date**: 2026-09-22 · **rev. 2026-09-23** (fases A-F + G/H implementadas. En D la pestaña Anotar fijó que las pestañas reciben `(state, lang, view)` y la activación por `set_active`; D.5: lectura y pintado de tarjetas ANNOTATE, flecha de norte y barra de escala como HUD común también en el PNG, resolución astrométrica común y en memoria; en E la pestaña Blink añadió el gancho `set_frame_override`; en F la pestaña Comparar usa la placa cargada como fondo del campo; G/H: la pestaña Medir con la fotometría calibrada y sus controles de calidad sobre `core/photometry.py`. **Conexión (2026-09-23)**: por defecto los flujos abren el UFE — ajuste `ufe_default` en Ajustes → Desarrollo, efecto inmediato — con prefill por pestaña, registro en el proyecto vía `set_save_hook` (incluidos contexto de secuencia y protocolo de campaña) y descarga del campo DSS2/PS1 dentro del UFE (esto supera la nota de la fase F: el fondo DSS2 ya no es exclusivo del legacy); la pestaña Medir puede guardar el punto calibrado en el proyecto (`source="measure"`) y la lista de visitas de Seguimiento abre el editor por visita («Medir en el Editor…» / "Measure in the editor…"), con resumen de campaña que se recalcula en cada guardado (retira el quick-look «Análisis rápido», ver ADR-019). Los tres diálogos legacy siguen vivos, intactos y alcanzables durante el periodo de revisión. **rev. 2026-09-24**: las secciones Comparar y Medir dejan de ser dos pestañas y viven juntas en la pestaña «Photometry» / «Fotometría»)

**Ver / See**: [docs/unified-fits-editor.md](../unified-fits-editor.md) (requisitos del observador) · [docs/PLANS/unified-fits-editor.md](../PLANS/unified-fits-editor.md) (plan vivo)

> **Nombre / Name (2026-09-23)**: la marca visible es «NightScribe Image
> Workbench» (menú y título, sin traducir: ya no es solo un editor);
> **UFE queda como codename interno** e inmutable en código, tests, ADR
> y planes. / The visible brand is "NightScribe Image Workbench" (menu
> and title, untranslated); **UFE stays as the immutable internal
> codename** in code, tests, ADRs and plans.

## Español

**Contexto**: tres funcionalidades cargan y muestran imágenes FITS con
interfaces e implementaciones distintas: el blink de supernovas
(`core/blink.py` + diálogo ad-hoc), la carta de comparación fotométrica
(ADR-042) y la exportación de FITS anotados (`sn_annotate_dialog.py`). La
duplicidad se paga dos veces: en mantenimiento (arreglar el estiramiento
en un sitio no lo arregla en los otros) y en el observador (tres interfaces
que aprender). El documento de requisitos pide un punto único donde
visualizar y trabajar las imágenes, extensible a futuras funcionalidades,
con control fino del histograma, inversión, exportación PNG de serie y un
zoom no limitado al Fit.

**Alternativas descartadas**:

- **(a) Reemplazar los diálogos legacy desde el día uno**: alto riesgo y
  dif enorme; el requisito manda convivencia (el UFE entra solo por el
  menú Herramientas) y las migraciones llegan por fases (D: anotar, E:
  blink, F: comparación). Los tres diálogos legacy no se tocan jamás.
- **(b) Un QLabel+QPixmap con scroll, como el diálogo de anotar**: sin
  overlays vectoriales precisos, sin zoom anclado al cursor, sin export
  de la escena visible; `ChartView` (ADR-029) ya resuelve todo eso.
- **(c) Escena en píxeles de pantalla (post-downscale)**: el zoom
  degradaría lo anotado y lo exportado; la escena vive en píxeles de
  placa originales y el pixmap reducido se estira con `QTransform`.
- **(d) Render en QThread desde la fase A**: con el cap de 4096 px el
  estiramiento cuesta del orden de 50-150 ms; un hilo solo añade carreras
  y riesgo de segfault shiboken al cerrar (historial del proyecto). Se
  renderiza síncrono con coalescencia de 120 ms (patrón
  `sn_annotate_dialog.py`); el worker queda como opción de fase C si el
  profiling lo pide.
- **(e) Percentiles en el estado, como los diálogos legacy**: los sliders
  de porcentaje son la causa de la falta de precisión en los extremos que
  motiva este editor. El estado guarda DN absolutos; los percentiles solo
  existen en la UI legacy.

**Decisión**:

1. **Punto de entrada único**: menú Herramientas → «FITS editor…»
   (diálogo perezoso no modal, instancia viva en `MainWindow`, patrón
   `_skycal_build`/`_tools_skycal`). Convive con los diálogos legacy.
2. **Tres ficheros**: `gui/ufe_state.py` (controller `UfeImageState`),
   `gui/widgets/ufe_image_view.py` (`UfeImageView(ChartView)`),
   `gui/ufe_dialog.py` (`UfeDialog`, construido a código, patrón
   `journal_dialog.py`).
3. **Estado**: placa original float32 + header + `core.wcs.Wcs` (o None),
   `d_min/d_max` de la placa completa, stretch en DN absolutos
   (`black/white/gamma/inverted`), señales `image_loaded` y
   `stretch_changed`. Invariante `white > black` por clamp
   (`white = max(white, black + eps)`), nunca por excepción. Los
   percentiles auto (1/99.5) se calculan sobre la imagen reducida:
   visualmente idénticos, mucho más baratos en placas grandes.
4. **Pipeline de pantalla, orden fijo**: pasos de media 2×2 hasta caber
   en 4096 px de lado (sin nuevas dependencias), estiramiento lineal,
   gamma, inversión, flip vertical a orientación de pantalla. Las
   exportaciones a disco siempre usan el archivo original, nunca el
   pixmap de pantalla. En la fase A el motor es `viz/blink_view`
   (`auto_limits/apply_stretch/to_uint8`); la fase B lo extrae a
   `core/stretch.py` y la UFE solo cambia un import.
5. **Escena en píxeles de placa originales con y hacia abajo**
   (convención de pantalla: `scene y = H-1-fila`); la única conversión
   vive en `UfeImageState.scene_to_data` / `data_to_scene`, y ninguna
   pestaña futura hace flips a mano. El pixmap reducido se inserta con un
   `QTransform` que lo estira sobre la placa: el zoom 100 % es exactamente
   1 píxel de dispositivo por píxel de placa, y los overlays (cosméticos,
   `QPen.setCosmetic` como en `FinderChart`) nunca pierden precisión.
6. **Zoom**: `ZOOM_MIN 0.05`, `ZOOM_MAX 40`, paso de rueda 1.5 (patrón
   `FinderChart`); presets Fit/50/100/200/400 con escala absoluta que
   conserva el centro visible; el auto-fit de `ChartView.resizeEvent` se
   anula (el zoom del observador sobrevive a los resizes; el fit solo
   ocurre al cargar) y el `sceneRect` se relaja con un margen del 25 %
   tras cada fit para poder barrer más allá del borde de la placa. El
   pixmap usa `Qt.FastTransformation`: a 200/400 % se inspeccionan
   píxeles reales, no interpolados (estilo AstroImageJ). Regla QImage:
   siempre `.copy()` sobre buffer contiguo, nunca depender del numpy vivo.
7. **Extensibilidad**: una funcionalidad nueva es una pestaña cuyo widget
   recibe `(state, lang, view)` (revisado en la fase D: la vista es donde
   viven overlays, clics y zoom) y se suscribe a las señales del estado;
   `UfeDialog.add_feature_tab(title, widget)` es todo el API de registro,
   y `set_active(bool)` marca qué pestaña posee los clics y los overlays
   en cada momento. Los overlays de cada pestaña entran por
   `view.add_overlay(item)` y salen con `view.clear_overlays()` al
   desactivarla, sin pisarse entre pestañas.
8. **Probe**: el hover muestra píxel de placa, valor DN y RA/Dec
   (`core/coords.ra_deg_to_hms` / `dec_deg_to_dms`) cuando hay WCS; el DN
   prepara el ajuste fino del histograma de la fase B.
9. **Fases**: A esqueleto+carga+vista (este ADR), B motor de estiramiento
   en `core/stretch.py` + histograma visual con tiradores, C comunes
   pulidas (teclado, persistencia del stretch, accesibilidad), D pestaña
   Anotar (`core/fits_annotate`), E pestaña Blink (`core/blink`), F
   pestaña Comparar (`core/compstars` + overlays `FinderChart`).

**Conexión con el proyecto (2026-09-23, ADR-019)**: la pestaña Seguimiento
retira su quick-look «Análisis rápido» (fallo silencioso de 0 puntos, la
respuesta «Nada» sin explicar; ver ADR-019) y su medida por visita pasa a
la pestaña Medir. Cuando el editor se abre a partir de un proyecto, la
pestaña Medir muestra el botón **Save in the project** y la medida
calibrada se registra en el proyecto con `source="measure"`: se pinta en
la curva, cuenta para la detección de eventos de la campaña y sale en las
exportaciones (los puntos históricos `source="quicklook"` siguen pintados
discontinuos, «indicativa», excluidos de las exportaciones por defecto).
El API lo da `UfeDialog`: `set_point_hook(fn)` / `point_hook()` /
`notify_point(payload)` (devuelve True/False y nunca lanza) y
`open_plate()` (informa si la placa entró). Del lado de Seguimiento, cada
fila de la lista de visitas ofrece «Medir en el Editor…» (EN: "Measure
in the editor…"), que abre el editor sobre la placa apilada de esa visita
con la pestaña Medir activa, y el panel **Resumen de campaña**
(`series.analyze_campaign`: pendiente diaria, distancia desde la cumbre y
veredicto contra la plantilla) se recalcula al abrir la pestaña y tras
cada guardado.

**Pestaña Fotometría (2026-09-24)**: las secciones Comparar y Medir dejan
de ser dos pestañas y viven juntas en una única pestaña
«Photometry» / «Fotometría»: el contenedor `UfePhotometryTab` lleva una
fila de radios exclusiva (Sequence | Measure) y un splitter vertical
entre ambos paneles, intactos en su interior; el conjunto de pestañas es
ahora Blink, Photometry, Annotate. En el panel Medir el flujo diario es
banda, aperturas y el botón Suggest, que queda justo bajo las tres
aperturas; las cinco opciones de receta (Sky, Sigma-clip, Seeing,
Colour term + B−V, Subtract host galaxy) viven en `UfeAdvancedDialog`,
una pequeña ventana no modal que el botón «Advanced…» abre y deja
seguir midiendo mientras está abierta. El registro de resultados es un
editor de texto solo lectura con scroll, para que un informe largo
(comps, guardas, veredicto) nunca aplaste los controles de encima. La
barra superior del editor gana un conmutador «A» que muestra u oculta
las anotaciones guardadas en la placa (las tarjetas ANNOTATE); las
marcas de fotometría y las estrellas de la secuencia no dependen de
ese conmutador y siguen siempre visibles en su sección. La ventana del
editor abre a 1440x960 (mínimo 1000x640), para que las dos secciones
quepan sin scroll. El cambio de modo va por `tab_photometry.set_mode("sequence" |
"measure")`, nunca con `setCurrentWidget` sobre los paneles internos;
el panel Medir conserva sus overlays cuando se activa la sección
Secuencia (`set_active(False, keep_overlays=True)`) y solo los retira al
abandonar de verdad la pestaña Fotometría; el botón «Go to the sequence»
/ «Ir a la secuencia» y los enlaces profundos heredados (prefills,
`show_tab`) siguen funcionando: el diálogo registra `self.tab_photometry`
y mantiene `self.tab_compare` / `self.tab_measure` como alias de los
paneles internos, y al recibir un panel interno cambia de modo y activa
la pestaña.

**Consecuencias**: cargar y trabajar un FITS tiene un solo camino; las
mejoras del motor de estiramiento (fase B) llegan a la vez a todo lo que
lo use; añadir una funcionalidad al editor no modifica `ufe_dialog.py`
salvo un `add_feature_tab`. Los diálogos legacy se mantienen congelados
mientras el UFE madura; la fase B es la única que toca código legacy, y
solo para re-exportar (`viz/blink_view.py` mantiene compatibilidad).

## English

**Context**: three features load and show FITS images with different
interfaces and implementations: the supernova blink, the photometric
comparison chart (ADR-042) and the annotated FITS export. The duplication
costs twice: maintenance (fixing the stretch in one place leaves the
others broken) and the observer learning three interfaces. The
requirements document asks for a single place to view and work images,
extensible to future features, with fine histogram control, inversion,
PNG export as a standard feature and a zoom not limited to Fit.

**Discarded alternatives**:

- **(a) Replacing the legacy dialogs from day one**: high risk, huge
  diff; the requirement mandates coexistence (the UFE only opens from the
  Tools menu) and migrations come in phases (D: annotate, E: blink, F:
  compare). The three legacy dialogs are never touched.
- **(b) A QLabel+QPixmap with scroll, like the annotate dialog**: no
  precise vector overlays, no cursor-anchored zoom, no visible-scene
  export; `ChartView` (ADR-029) already solves all of that.
- **(c) Scene in display (post-downscale) pixels**: zoom would degrade
  what is annotated and exported; the scene lives in original plate
  pixels and the downscaled pixmap is stretched back with a `QTransform`.
- **(d) QThread rendering from phase A**: with the 4096 px cap the
  stretch costs around 50-150 ms; a thread only adds races and shiboken
  segfault risk on close (project history). Rendering is synchronous with
  120 ms coalescing (the `sn_annotate_dialog.py` pattern); the worker
  stays as a documented phase-C option if profiling asks for it.
- **(e) Percentiles in the state, like the legacy dialogs**: percentage
  sliders are the root cause of the coarse extremes this editor exists to
  fix. The state keeps absolute DN; percentiles only live in the legacy
  UI.

**Decision**:

1. **Single entry point**: Tools menu → "FITS editor…" (lazy non-modal
   dialog, instance kept alive on `MainWindow`, `_skycal_build` /
   `_tools_skycal` pattern). It coexists with the legacy dialogs.
2. **Three files**: `gui/ufe_state.py` (the `UfeImageState` controller),
   `gui/widgets/ufe_image_view.py` (`UfeImageView(ChartView)`),
   `gui/ufe_dialog.py` (`UfeDialog`, code-built, `journal_dialog.py`
   pattern).
3. **State**: original float32 plate + header + `core.wcs.Wcs` (or None),
   full-plate `d_min/d_max`, stretch in absolute DN
   (`black/white/gamma/inverted`), `image_loaded` and `stretch_changed`
   signals. The `white > black` invariant is kept by clamping
   (`white = max(white, black + eps)`), never by raising. Auto
   percentiles (1/99.5) are computed on the downscaled frame: identical
   to the eye, far cheaper on big plates.
4. **Display pipeline, fixed order**: 2x2 averaging steps until the frame
   fits a 4096 px side (no new dependencies), linear stretch, gamma,
   inversion, vertical flip to screen orientation. Disk exports always
   use the original file, never the display pixmap. Phase A's engine is
   `viz/blink_view` (`auto_limits/apply_stretch/to_uint8`); phase B
   extracts it into `core/stretch.py` and the UFE only changes an import.
5. **Scene in original plate pixels, y down** (screen convention:
   `scene y = H-1-row`); the only conversion lives in
   `UfeImageState.scene_to_data` / `data_to_scene`, and no future tab
   flips by hand. The downscaled pixmap is inserted with a `QTransform`
   that stretches it over the plate: 100 % zoom is exactly one device
   pixel per plate pixel, and overlays (cosmetic, `QPen.setCosmetic` like
   `FinderChart`) never lose precision.
6. **Zoom**: `ZOOM_MIN 0.05`, `ZOOM_MAX 40`, wheel step 1.5
   (`FinderChart` pattern); Fit/50/100/200/400 presets with absolute
   scale that keeps the view centre; `ChartView.resizeEvent`'s auto-fit
   is overridden (the observer's zoom survives resizes; fit only happens
   on load) and the `sceneRect` is relaxed with a 25 % margin after each
   fit so panning can go past the plate edge. The pixmap uses
   `Qt.FastTransformation`: at 200/400 % you inspect real pixels, not an
   interpolation (AstroImageJ style). QImage rule: always `.copy()` on a
   contiguous buffer, never lean on the live numpy one.
7. **Extensibility**: a new feature is a tab whose widget receives
   `(state, lang, view)` (revised in phase D: the view is where overlays,
   clicks and zoom live) and subscribes to the state's signals;
   `UfeDialog.add_feature_tab(title, widget)` is the whole registration
   API, and `set_active(bool)` marks which tab owns the clicks and
   overlays at any moment. Each tab's overlays enter through
   `view.add_overlay(item)` and leave with `view.clear_overlays()` on
   deactivation, never stomping on each other.
8. **Probe**: hover shows the plate pixel, the DN value and RA/Dec
   (`core/coords.ra_deg_to_hms` / `dec_deg_to_dms`) when a WCS exists;
   the DN prepares phase B's fine histogram work.
9. **Phases**: A skeleton+load+view (this ADR), B stretch engine in
   `core/stretch.py` + visual histogram with draggable handles, C polished
   commons (keyboard, stretch persistence, accessibility), D Annotate tab
   (`core/fits_annotate`), E Blink tab (`core/blink`), F Compare tab
   (`core/compstars` + `FinderChart` overlays).

**Project connection (2026-09-23, ADR-019)**: the follow-up tab retires
its quick-look "Quick analysis" button (silent 0-point failure, a
"Nada" with no explanation; see ADR-019), and its per-visit
measurement moves to the Measure tab. When the editor is opened from a
project, the Measure tab shows a **Save in the project** button and the
calibrated point is registered in the project as `source="measure"`: it
renders on the curve, counts for the campaign's event detection and is
included in the exports (historic `source="quicklook"` points keep
rendering dashed, "indicativa", excluded from the exports by default).
The API is `UfeDialog`: `set_point_hook(fn)` / `point_hook()` /
`notify_point(payload)` (returns True/False, never raises) and
`open_plate()` (reports whether the plate loaded). On the follow-up
side, every visit row offers "Measure in the editor…", which opens the
editor on that visit's stacked plate with the Measure tab active, and
the **Campaign summary** panel (`series.analyze_campaign`: daily slope,
distance from the peak, tab open and after every save.

**Photometry tab (2026-09-24)**: the Compare and Measure sections stop
being two tabs and live together inside a single "Photometry" tab: the
`UfePhotometryTab` container carries an exclusive radio row
(Sequence | Measure) and a vertical splitter between both panels, whose
interiors are untouched; the tab set is now Blink, Photometry,
Annotate. On the Measure panel the daily flow is band, apertures, and
the Suggest button, which sits right under the three apertures; the
five recipe options (Sky, Sigma-clip, Seeing, Colour term + B−V,
Subtract host galaxy) live in `UfeAdvancedDialog`, a small non-modal
window the "Advanced…" button opens and that lets measuring continue
while it stays open. The result log is a read-only text editor with
scrolling, so a long report (comps, guards, verdict) can never squash
the controls above it. The editor's top bar gains an "A" toggle that
shows or hides the annotations saved on the plate (the ANNOTATE
cards); the photometry markers and the sequence stars do not depend on
that toggle and always stay visible in their own section. The editor
window opens at 1440x960 (minimum 1000x640) so both sections fit
without scrolling. Mode
switching goes through `tab_photometry.set_mode("sequence" |
"measure")`, never `setCurrentWidget` on the inner panels; the Measure
panel keeps its overlays while the Sequence section is active
(`set_active(False, keep_overlays=True)`) and only clears them when the
Photometry tab is actually left; the "Go to the sequence" button and
the inherited deep links (prefills, `show_tab`) keep working: the
dialog registers `self.tab_photometry` and keeps `self.tab_compare` /
`self.tab_measure` as aliases of the inner panels, and receiving an
inner panel switches the mode and activates the tab.

**Consequences**: loading and working a FITS has a single path; stretch
engine improvements (phase B) reach every consumer at once; adding a
feature to the editor does not modify `ufe_dialog.py` beyond an
`add_feature_tab`. The legacy dialogs stay frozen while the UFE matures;
phase B is the only one touching legacy code, and only to re-export
(`viz/blink_view.py` keeps compatibility).
