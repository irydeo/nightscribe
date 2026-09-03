# ADR-029: Vectorial chart widgets in the GUI (PySide6 QGraphics, no new dependency)

**Estado / Status**: Accepted · **Fecha / Date**: 2026-09-03

## Español

**Contexto**: las gráficas del resumen (órbita, cielo/visibilidad, tránsito,
campo SN) se renderizan hoy con matplotlib (`viz/orbit_view.py`,
`viz/sky_view.py`) como **ficheros PNG** y la GUI los muestra a través de
`QLabel` + `QPixmap` (el slot 2×2 del panel `overview.py`) o en una ventana de
zoom (`chart_viewer.py`). Esto trae tres limitaciones que bloqueaban las
funcionalidades pedidas del proyecto:

1. **No se puede animar**: un PNG es una foto fija. Animar la posición del
   objeto a lo largo de la órbita — o la curva de visibilidad — es imposible
   sin re-renderizar la figura completa cada frame (costo de matplotlib, y
   además el resultado nunca es "nativo" de la GUI).
2. **No se puede hover**: pasar el ratón por la órbita para leer `r (AU)`,
   `ν (°)` y la fecha en ese punto, o pasar por la curva de altitud para leer
   la hora y altura exactas, requiere una escena interactiva que sepa dónde
   está cada punto.
3. **Letterbox**: el PNG exportado tiene un ratio fijo (16:9 para `panel`,
   1:1 para `instagram`) que no coincide con el ratio del lienzo en que se
   muestra (slot 2×2, ventana de zoom). `QPixmap.scaled(..., KeepAspectRatio)`
   centra el bitmap dejando bandas oscuras laterales o arriba/abajo — es el
   "hueco de media página" que se veía en la GUI.

El "hueco" no es un bug de `style.save()` (un PNG recién exportado para
`facebook`/`panel` hoy llene el ancho del ~1 % — medido en los tests, y el
recorte `bbox_inches="tight"` ya hace su trabajo). Es la inevitable
consecuencia de mostrar un bitmap de ratio A en un lienzo de ratio B.

**Alternativas descartadas**:

- **(a) Matplotlib como widget inline** (`FigureCanvasQTAgg`): nueva capa de
  Qt/matplotlib, pierde ADR-010 de "sin dependencias" (ya se usa
  `matplotlib` pero se introduce una segunda forma de usarlo, con su propio
  ciclo de eventos, su own zoom/pan y su "export" distinta de la de `viz`),
  y no resuelve el letterbox (sigue siendo un bitmap renderizado).
- **(b) Solo arreglar el recorte de `style.save`** (más agresivo, al
  contenido del eje): no arregla el letterbox del slot 2×2, no habilita
  animación ni hover, y además el recorte actual ya es razonable.
- **(c) PyQtGraph / Vispy**: nueva dependencia (violación de la regla
  "dependencias mínimas" y el espíritu de ADR-010) y cambia la forma en que
  se exportan los PNGs de redes (hoy `viz/*` produce la imagen; con PyQtGraph
  habría que reescribirlo).

**Decisión**: la **capa de visualización de la GUI** pasa a ser
**`QGraphicsView` nativo** de PySide6, sin importar `matplotlib` ni añadir
dependencias. La **export para redes** (los PNGs que se adjuntan al post de
Facebook/Instagram/panel) sigue produciéndose por `viz/*` con matplotlib,
como hoy — ADR-010 sigue intacto **para ese ámbito**.

Concretamente:

1. **Paquete nuevo `nightscribe/gui/widgets/`** (ADR-029) con:
   - `base_chart.py` — `ChartView(QGraphicsView)`: contenedor oscuro
     (fondo `viz.palette.BG`), zoom bajo el cursor, pan, fit-automático al
     tamaño del padre, un tooltip propio en la escena (una
     `QGraphicsSimpleTextItem` sobre un `QGraphicsRectItem` de fondo) y una
     API `set_hover_probe(fn)` que los hijos usan para devolver `r/ν/t` ó
     `hora/alt/az` al pasar por encima.
   - `orbit_widget.py` (Fase 2) — `OrbitChart(ChartView)`: anillos, elipse,
     Sol, punto del objeto animado, hover.
   - `sky_widget.py` (Fase 3) — `SkyChart(ChartView)`: curva de altitud,
     Luna, ventana segura, mejor hora, hover; `TransitChart(SkyChart)`.
   - **`gui/widgets/*` no importa `matplotlib`** (prohibido — un test lo
     asienta). Solo `core/*` (matemática) y `PySide6`.
   - Los colores de los charts salen de un **módulo nuevo
     `nightscribe/viz/palette.py`** (sin matplotlib), que `viz/style.py`
     delega ahora; así `gui/widgets` toma los colores sin arrastrar a
     `viz.style` (que sí importa `matplotlib`).
2. **La matemática de la elipse** se extrae de `viz/orbit_view._orbit_xy`
   (que no depende de matplotlib en el cuerpo, pero vive en un módulo que sí)
   a **`core/orbit_math.py`** para que `viz/orbit_view.py` y
   `gui/widgets/orbit_widget.py` lo compartan de un lado y otro de la
   frontera.
3. **Integración en GUI** (Fase 4): `overview.py` monta los widgets en los
   slots 2×2 (sin `QPixmap`, sin letterbox, sin `_fit_slots`); `chart_viewer.py`
   abre el widget en la ventana de zoom (export PNG = "renderizar la escena
   actual al tamaño pedido", no "copiar un fichero"). `core/post.py` **no
   cambia** (sigue generando los PNGs de redes vía `viz/*`).

**Consecuencias**:

- Los charts en la GUI se vuelven vectoriales e interactivos; el "hueco
  lateral" visto en el slot 2×2 desaparece (el widget pinta a la medida
  exacta del slot, sin bitmap intermedio).
- El `export_png` del widget renderiza lo visible (zoom incluido) con
  `QPainter`, independiente del recorte de `style.save` (que sigue sirviendo
  para los PNGs de redes).
- `gui/widgets` queda libre de `matplotlib`: si en el futuro se retira
  matplotlib de la app, la GUI de gráficas sigue funcionando (solo cambian
  los PNGs de export).
- Se mantiene **una sola** forma de producir los PNGs de redes
  (`viz/*` + `style.save`), y **una sola** capa de visualización interactiva
  en la GUI (`gui/widgets/*`).
- `viz.palette` es una nueva fuente de la verdad de *colores de charts*.
  `viz.style` lo delega (sin romper su API: `style.ACCENT`, `style.BG`, …
  siguen importándose igual desde los módulos de `viz/*`).
- La ADR-026 (tema global de la app) y ADR-029 (tema de los charts) se
  complementan: la app usa `gui/theme.py` (el cromo de la aplicación), y los
  charts — tanto el widget GUI como el PNG exportado — usan `viz/palette.py`
  (el color "espacio oscuro" de cada gráfico).
- Al arrastrar el marco de la ventana, Qt encola docenas de eventos de
  redimensionado en un solo fotograma; si cada uno forzaba un `fitInView`
  completo (re-render sincrono de la escena), en un GPU de raster lento
  saturaba la GUI thread hasta que la app parecía congelarse. `ChartView.resizeEvent`
  coalesce los resizes a **una** `fit_to_scene()` retardada por vuelta de
  event-loop (`QTimer.singleShot(0, …)` + guard `_fit_pending`). El resultado
  visual es idéntico al del resize final; el coste es O(1) por arrastre.
  La misma estrategia protege `chart_viewer.py`.

**Escopado**: este ADR cubre la arquitectura de la capa interactiva y la
fuente de colores. La implementación se hace en fases autónomas para poder
parar, probar y commitar entre cada una (Fase 1: base `ChartView`; Fase 2:
`OrbitChart`; Fase 3: `SkyChart`; Fase 4: integración GUI + viewer dual-mode;
Fase 5: fixes de rendimiento y cierres). Ver `docs/PLANS/qt-chart-widgets.md`.

## English

**Context**: the overview charts (orbit, visibility/altitude curve, transit,
SN field) are today rendered with matplotlib (`viz/orbit_view.py`,
`viz/sky_view.py`) as **PNG files**, and the GUI shows them through
`QLabel` + `QPixmap` (the 2×2 slot in `overview.py`) or a zoom window
(`chart_viewer.py`). Three limits of that design blocked the features the
project asked for:

1. **Cannot animate**: a PNG is a frozen photo. Animating the object's
   position along the orbit — or the visibility curve — is impossible without
   re-rendering the full figure every frame (matplotlib cost, and the result
   is never "native" to the GUI).
2. **Cannot hover**: moving the cursor along the orbit to read `r (AU)`,
   `ν (°)` and the date at that point, or along the altitude curve to read
   the exact time and altitude, requires an interactive scene that knows
   where each point is.
3. **Letterbox**: the exported PNG has a fixed aspect ratio (16:9 for `panel`,
   1:1 for `instagram`) that does not match the aspect of the canvas it is
   shown in (the 2×2 slot, the zoom window). `QPixmap.scaled(...,
   KeepAspectRatio)` centres the bitmap leaving dark bands on the sides or
   top/bottom — this is the "half-page hole" that was visible in the GUI.

That hole is **not a `style.save()` bug** (a freshly exported PNG for
`facebook`/`panel` today fills its width to ~1% — measured in the tests; the
`bbox_inches="tight"` crop already does its job). It is the inevitable
consequence of showing a bitmap of aspect A inside a canvas of aspect B.

**Alternatives rejected**:

- **(a) Matplotlib as an inline widget** (`FigureCanvasQTAgg`): new Qt+
  matplotlib layer, blurs the ADR-010 boundary (already used, but introduced
  as a second way of using it, with its own event loop, its own zoom/pan, its
  own export), and does not solve the letterbox (still a rendered bitmap).
- **(b) Just make `style.save` crop harder** (to the axes content): does not
  fix the 2×2 slot letterbox, does not enable animation or hover, and the
  current crop is already reasonable.
- **(c) PyQtGraph / Vispy**: new dependency (against the "minimal
  dependencies" rule and the spirit of ADR-010) and changes how the social-
  media PNGs are produced (today `viz/*` produces the image; with PyQtGraph
  that would have to be rewritten).

**Decision**: the **GUI visualisation layer** becomes **native PySide6
`QGraphicsView`**, no `matplotlib` import, no new dependency. The **social-
media export** (the PNGs attached to the Facebook / Instagram / panel post)
keeps being produced by `viz/*` with matplotlib, as today — ADR-010 remains
intact **for that scope**.

Specifically:

1. **New package `nightscribe/gui/widgets/`** (ADR-029) with:
   - `base_chart.py` — `ChartView(QGraphicsView)`: dark canvas (background
     `viz.palette.BG`), zoom under the cursor, drag pan, fit-to-parent
     automatic, an in-scene tooltip (a `QGraphicsSimpleTextItem` on top of a
     `QGraphicsRectItem` background), and a `set_hover_probe(fn)` API for
     subclasses to return `r/ν/t` or `time/alt/az` at each scene coordinate.
   - `orbit_widget.py` (phase 2) — `OrbitChart(ChartView)`: planet rings,
     the ellipse, the Sun, the animated object marker, hover.
   - `sky_widget.py` (phase 3) — `SkyChart(ChartView)`: altitude curve, Moon,
     safe window, best time, hover; `TransitChart(SkyChart)`.
   - **`gui/widgets/*` does not import `matplotlib`** (prohibited — a test
     asserts this). Only `core/*` (math) and `PySide6`.
   - Chart colours come from a **new module `nightscribe/viz/palette.py`**
     (matplotlib-free), which `viz/style.py` now delegates to; this way
     `gui/widgets` takes the colours without dragging `viz.style` (which
     does import matplotlib).
2. **The ellipse math** is extracted from `viz/orbit_view._orbit_xy` (whose
   body does not use matplotlib, but which lives in a module that does) to
   **`core/orbit_math.py`** so that `viz/orbit_view.py` and
   `gui/widgets/orbit_widget.py` share it from either side of the border.
3. **GUI integration** (phase 4): `overview.py` mounts the widgets in the
   2×2 slots (no `QPixmap`, no letterbox, no `_fit_slots`); `chart_viewer.py`
   opens the widget in the zoom window (export PNG = "render the current
   scene at the requested size", not "copy a file"). `core/post.py` is
   **unchanged** (it still produces the social PNGs via `viz/*`).

**Consequences**:

- The GUI charts become vectorial and interactive; the "side hole" seen in
  the 2×2 slot disappears (the widget paints to the exact slot size, no
  intermediate bitmap).
- The widget's `export_png` renders what is visible (zoom included) with
  `QPainter`, independent of the `style.save` crop (which still serves the
  social PNGs).
- `gui/widgets` is free of `matplotlib`: if matplotlib is ever removed from
  the codebase, the GUI charts keep working (only the export PNGs change).
- There is exactly **one** way to produce the social PNGs (`viz/*` +
  `style.save`) and exactly **one** layer of interactive visualisation in
  the GUI (`gui/widgets/*`).
- `viz.palette` is a new single-source-of-truth for *chart colours*.
  `viz.style` delegates to it (breaking nothing: `style.ACCENT`,
  `style.BG`, … are still importable from the `viz/*` modules).
- ADR-026 (global app theme) and ADR-029 (charts theme) are complementary:
  the app uses `gui/theme.py` (the application's chrome), and the charts —
  both the GUI widget and the exported PNG — use `viz/palette.py` (the
  "dark space" look of each chart).
- When the window is being dragged, Qt queues dozens of resize events in a
  single frame; if each one forced a full `fitInView` (a synchronous
  scene re-render), on a slow GPU raster path the GUI thread saturates
  and the app appears frozen. `ChartView.resizeEvent` now coalesces the
  resize burst to a **single** deferred `fit_to_scene()` per event-loop
  turn (`QTimer.singleShot(0, …)` + a `_fit_pending` flag). The visual
  output is identical to the final resize; the cost is O(1) per drag.
  The same strategy protects `chart_viewer.py`.

**Scope**: this ADR covers the architecture of the interactive layer and the
colour source of truth. The implementation happens in autonomous phases so
we can stop, test and commit between each one (phase 1: base `ChartView`;
phase 2: `OrbitChart`; phase 3: `SkyChart`; phase 4: GUI integration +
dual-mode viewer; phase 5: performance fixes and close-out). See
`docs/PLANS/qt-chart-widgets.md`.
