# ADR-044: Editor FITS unificado (UFE): una ventana, una pestaña por funcionalidad, escena en píxeles de placa

**Estado / Status**: Accepted · **Fecha / Date**: 2026-09-22 · **rev. 2026-09-22** (fases A, B y C implementadas: esqueleto/carga/vista, motor de estiramiento `core/stretch.py` + histograma visual, y comunes pulidas con teclado y persistencia del stretch; fases D-F pendientes)

**Ver / See**: [docs/unified-fits-editor.md](../unified-fits-editor.md) (requisitos del observador) · [docs/PLANS/unified-fits-editor.md](../PLANS/unified-fits-editor.md) (plan vivo)

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
   recibe `(state, lang)` y se suscribe a las señales del estado;
   `UfeDialog.add_feature_tab(title, widget)` es todo el API. Los
   overlays de cada pestaña entran por `view.add_overlay(item)` y salen
   con `view.clear_overlays()` al desactivarla, sin pisarse entre
   pestañas.
8. **Probe**: el hover muestra píxel de placa, valor DN y RA/Dec
   (`core/coords.ra_deg_to_hms` / `dec_deg_to_dms`) cuando hay WCS; el DN
   prepara el ajuste fino del histograma de la fase B.
9. **Fases**: A esqueleto+carga+vista (este ADR), B motor de estiramiento
   en `core/stretch.py` + histograma visual con tiradores, C comunes
   pulidas (teclado, persistencia del stretch, accesibilidad), D pestaña
   Anotar (`core/fits_annotate`), E pestaña Blink (`core/blink`), F
   pestaña Comparar (`core/compstars` + overlays `FinderChart`).

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
   `(state, lang)` and subscribes to the state's signals;
   `UfeDialog.add_feature_tab(title, widget)` is the whole API. Each
   tab's overlays enter through `view.add_overlay(item)` and leave with
   `view.clear_overlays()` on deactivation, never stomping on each other.
8. **Probe**: hover shows the plate pixel, the DN value and RA/Dec
   (`core/coords.ra_deg_to_hms` / `dec_deg_to_dms`) when a WCS exists;
   the DN prepares phase B's fine histogram work.
9. **Phases**: A skeleton+load+view (this ADR), B stretch engine in
   `core/stretch.py` + visual histogram with draggable handles, C polished
   commons (keyboard, stretch persistence, accessibility), D Annotate tab
   (`core/fits_annotate`), E Blink tab (`core/blink`), F Compare tab
   (`core/compstars` + `FinderChart` overlays).

**Consequences**: loading and working a FITS has a single path; stretch
engine improvements (phase B) reach every consumer at once; adding a
feature to the editor does not modify `ufe_dialog.py` beyond an
`add_feature_tab`. The legacy dialogs stay frozen while the UFE matures;
phase B is the only one touching legacy code, and only to re-export
(`viz/blink_view.py` keeps compatibility).
