# Plan — Vista vectorial en la GUI de las gráficas de órbita y visibilidad

**rama**: `feat/qt-chart-widgets` · **arranca sobre**: `25e9346` (ux-v3-projects)
**fecha**: 2026-09-02 (revisión 2026-09-03: se descarta la Fase 0) · **autor**: FJC (con la IA)

## Objetivo

Que las gráficas del resumen (órbita, cielo/visibilidad, tránsito, campo SN) sean
**vectoriales e interactivas** en la GUI:

- **Órbita**: se pueda **animar** respecto a la fecha (el punto del objeto recorre la
  elipse) y, al **pasar por encima**, ver en ese punto `r (AU)`, `ν (°)` y la fecha.
- **Cielo/visibilidad**: al **pasar por encima de la curva**, ver la **hora y altura
  exactas**; resaltar la ventana segura y la mejor hora.
- **Export**: el botón exporta a **PNG lo que se está viendo** en el widget (zoom
  incluido), con la resolución que se pida.

No es "cambiar el recorte del PNG": es reescribir la capa de visualización de la GUI
como **widgets nativos de PySide6** (`QGraphicsView`), sin nueva dependencia.

Sub-objetivo colateral que los widgets resuelven de raíz: el "**letterbox**" que hoy
se ve en el slot 2×2 del panel y en la ventana del viewer (bandas oscuras a los
laterales o arriba/abajo) desaparece, porque el widget vectorial pinta a medida exacta
del lienzo — sin recalcular ni escalar un bitmap de ratio fijo.

## Decisiones ya tomadas (no reabrir salvo causa)

| # | Decisión | Valor |
|---|----------|-------|
| 1 | El "hueco lateral" que se ve | No es un bug del PNG exportado (medido: ~1 %). Es el **letterbox del `QPixmap`** en el slot/viewer (ratio del PNG ≠ ratio del lienzo). Lo resuelve la **Fase 1 + Fase 4** (widget vectorial sin letterbox) |
| 2 | El hotfix de `style.save` (recorte al contenido del ejes) | **Descartado** (2026-09-03). El PNG ya llena el ancho (~1 %); recortar aún más rompería títulos/legend/watermark |
| 3 | El **post de redes** (PNGs `orbit.png/sky.png/…` del markdown) | Sigue vía **matplotlib** — ADR-010 intacto (opción **3a**) |
| 4 | Alcance de la 1ª iteración | **OrbitChart + SkyChart** (Transit como subclase) |
| 5 | Export **SVG** | **Fuera** de la 1ª iteración (el `QGraphicsSvgGenerator` maneja `QFont` distinto de la vista; se deja como follow-up con su propia ADR si se hace) |

## Estado global (actualizar al terminar cada fase)

- [x] **Fase 1** — ADR-029 + `ChartView` base (zoom/pan/fit/export/hover) — *10 tests en `tests/unit/test_chartview.py`, guard-test de hueco en `test_style.py`* (`fa94696`)
- [x] **Fase 2** — `OrbitChart` (animación + hover de r/ν/t) — *8 tests en `tests/unit/test_orbitchart.py`* (`bedf0ce`)
- [x] **Fase 3** — `SkyChart` (+ `TransitChart`) (hover hora/altura/azimut, ventana segura, click en banda → `best_time_clicked`) — *10 tests en `tests/unit/test_skychart.py`; sampler puro compartido `core/sky_math.sample_night` (mismo diccionario que `viz/sky_view.py`); fix del `QGraphicsScene.render(target=, source=)` en `ChartView.export_png` (el export daba PNG negro)*
- [x] **Fase 4a** — `ChartViewer` dual-mode (widget vectorial + pixmap PNG); zoom/fit → `widget.view`, export → `widget.export_png()`, memoria por título, fábrica `open_chart_widget()` (5 tests widget-mode)
- [x] **Fase 4b** — `overview.py`: slots orbit/sky → `OrbitChart`/`SkyChart` vivos (zoom/pan/hover), transit/field → `QLabel+QPixmap`; click re-construye widget y abre `ChartViewer`; se borran `_fit_slots`/`_orig_pngs`/`_labels`/`resizeEvent`
- [ ] **Fase 4c** — `main_window.py`: migrar referencias al viewer + comprobar compatibilidad
- [ ] **Fase 5** — Docs (ADR-010 alcance, WORKFLOWS) + limpieza

> Regla de oro: cada fase termina **con la suite verde** (`tests/unit` +
> `tests/functional`) y **commitado**. Después se decide si seguimos, paramos o
> corregimos. La lista de arriba es el ancla de recuperación.

---

## Fase 1 — ADR-029 + `ChartView` base

**Objetivo**: un `ChartView(QGraphicsView)` reutilizable con zoom bajo el cursor, pan,
fit al tamaño de su padre, callback de hover (tooltip propio de clase), export PNG,
y fondo/colores coherentes con `viz.style`. Aquí **no** se dibuja órbita ni cielo
todavía; solo la capa de contenedores.

**ADR-029** (bilingüe, `docs/adr/ADR-029-qt-view-widgets.md`):

- Contexto: ADR-010 declara matplotlib como único motor de render de la app.
  Con el paso del tiempo los charts se convirtieron en *ficheros PNG* y la GUI
  terminó mostrando bitmaps de ratio fijo en lienzos de otro ratio (letterbox).
  No es una limitación de ADR-010, pero impide animar, hovernear y exportar "lo
  que se ve".
- Decisión: los **widgets GUI de gráficas** pasan a ser `QGraphicsView` nativos
  (`gui/widgets/*`). La **export/pos para redes** sigue renderizándose con
  matplotlib vía `viz/*` y `core.post.build_charts` — ADR-010 se mantiene para
  ese ámbito. El paquete `gui/widgets` **no importa** `matplotlib`; solo `core/*`
  (matemática pura) y `PySide6`.
- Evidencia: medir un PNG exportado de `style.save()` hoy da ~1 % de hueco
  lateral para los fmt `instagram/facebook/panel` (ver `tests/unit/test_style.py`
  que añade la aserción como guardia); la queja del "hueco de media página"
  venía del **letterbox del QPixmap**, no del PNG.
- Consecuencias: el "Export PNG" pasa a ser "renderizar el QGraphicsScene al
  tamaño pedido" (`QPainter`), no "copiar un fichero". El slot 2×2 del panel deja
  de escalar bitmaps y monta widgets. `chart_viewer.py` deja de abrir `QPixmap`.
- Alternativas descartadas: (a) seguir con PyQtGraph (nueva dependencia;
  conflicto con ADR-010 de "sin dependencias"); (b) solo "fix del recorte"
  del PNG (no arregla el hueco del slot, ni habilita animación/hover);
  (c) QGraphicsScene con matplotlib renderizado a QPixmap (mezcla lo peor de
  ambos).

**Ficheros nuevos**:
- `docs/adr/ADR-029-qt-view-widgets.md`
- `nightscribe/gui/widgets/__init__.py`
- `nightscribe/gui/widgets/base_chart.py` — `ChartView`.
- `tests/unit/test_chartview.py` — test unitario offscreen.
- `tests/unit/test_style.py` — añade un test que midiendo un PNG exportado
  (orbit + sky en `facebook`) asegure el hueco lateral < 10 % del ancho (guardia
  de regresión, evita que un cambio en `savefig` rompa el encuadre).

**Capacidades de `ChartView`** (todas en `base_chart.py`):

- **Contenedor `QGraphicsView`** con `setTransformationAnchor(
  AnchorUnderMouse)`, `setRenderHint(Antialiasing)`, `setDragMode(ScrollHandDrag)`
  (pan), y fondo `viz.style.BG`.
- **Zoom** con rueda: `wheelEvent` → `scale(1.2, 1.2)` dentro de `setZoomLimits(0.05,
  8.0)`.
- **Pan** con el botón izquierdo (ScrollHandDrag del propio view).
- **`fit_to_scene()`**: recalcular la transformación para que la **escena** ocupe el
  vista. **`resizeEvent`** la llama.
- **`export_png(path, dpi=100)`**: `QPixmap(size * dpi)` → `scene.render(QPainter)`
  con `setRenderHint(Antialiasing)` → `save()`. Devuelve `Path`.
- **`set_hover_probe(fn)`**: hook que un widget hijo instala. `fn(x, y)` recibe
  coordenadas de la escena y devuelve `(ok: bool, text: str)`. `ChartView` dibuja
  un `QGraphicsSimpleTextItem` flotante cerca del cursor mientras `fn(...)` responde
  `ok=True`; se quita al salir. `enterEvent/leaveEvent/mouseMoveEvent` lo orquestan.
- **`scene_rect_hint(w, h)`**: método overrideable que devuelve `(x, y, w, h)`
  en unidades de escena que `fit_to_scene` toma como referencia (por defecto el
  rect unió de los items, o el rect explícito fijado con `set_scene_rect`).
- **`add_item(item)`**: atajo a `scene().addItem` que además recuerda el item para
  poder limpiarlo con `clear()` — un `ChartView` nuevo lo usa para borrar y
  redibujar al cambiar de objeto.
- **Colores**: `style_bg()`, `style_accent()`, `style_muted()` — solo lecturas de
  las constantes de `viz.style` (NO llama a `matplotlib.pyplot` ni a `new_fig`).

**Reglas del paquete `gui/widgets`**:
- Solo `core/*`, `PySide6`, `stdlib`.
- **Prohibido** `import matplotlib` (asegurado por un test de "import limpio" en
  `test_chartview.py`).
- Las clases concretas (`OrbitChart`, `SkyChart`) viven en sus propios módulos y
  heredan de `ChartView`.

**Verificación**:
1. `test_chartview.py::test_export_png_writes_file` — offscreen, agregar un
   `QGraphicsRectItem`, `fit_to_scene`, `export_png(tmp_path)` → existe, > 2 KB.
2. `test_chartview.py::test_zoom_limits_respected` — `wheelEvent` +5 clicks no
   supera `zoomLimits().upper`.
3. `test_chartview.py::test_fit_to_scene_refills_on_resize` — tras `resize()` +
   `processEvents` la `scale()` no es 0 y `mapToScene(0, 0)` sigue dentro del
   límite.
4. `test_chartview.py::test_hover_probe_shows_and_hides_tooltip` — `set_hover_probe`
   con `(True, "hello")`; `mouseMoveEvent` en el centro del viewport → un item de
   texto `hello` en la escena; `leaveEvent` → desaparece.
5. `test_chartview.py::test_widgets_package_no_matplotlib_import` — `import
   nightscribe.gui.widgets.base_chart` como **subprocéso** limpio (o `sys.modules`
   reset) → `"matplotlib.pyplot" not in sys.modules`.
6. `test_style.py::test_exported_orbit_png_fills_width` — renderizor `draw_orbit(
   els_low_e, fmt="facebook", out=tmp)` + `PIL` para medir el hueco lateral:
   `< 0.10 * W`. Lo mismo para `sky` con `draw_sky(…)` (misma regla).
7. Suite unit + funcional completa verde.

**Decisión al terminar**: (ninguna bloqueante) el `QGraphicsSvgGenerator` queda
fuera de la 1ª iteración (decisión #5).

---

## Fase 2 — `OrbitChart`

**Objetivo**: el gráfico de órbita vectorial, con **animación** por fecha y **hover**
que devuelve `r/ν/t` en el punto bajo el cursor.

**Fichero nuevo**: `nightscribe/gui/widgets/orbit_widget.py`

**Escena** (fuentes de datos ya existentes):
- anillos de los planetas en el marco (`QGraphicsEllipseItem`) — mismo criterio "solo
  si cabe" que `draw_orbit` usa hoy.
- la elipse del objeto: polyline 360 puntos. **Fuente**: `_orbit_xy` de
  `viz/orbit_view.py` (matemática ya en el proyecto; no duplicar, extraer a
  `core/orbit_math.py` o similar que ambos usen, así `gui/widgets` no arrastra a
  `viz` ni a `matplotlib.pyplot`).
- el punto del objeto en `jd` (`kepler_ra_dec` / `_elements_to_ecliptic`).
- Sol + etiquetas (`QGraphicsTextItem`).

**Interactividad**:
- **Animación**: `start_animation(jd0, jd1, period_s=8)` / `stop_animation()`;
  `QTimer(20 ms)` mueve el punto y actualiza un `QGraphicsTextItem` de fecha +
  barra de progreso inferior (`QSlider` de 1..1000 mapeado al intervalo).
  Botón `⏵/⏸` (un solo toggle; el estado visual cambia).
- **Hover sobre la elipse**: hit-test sobre el path → `ν` por inversión directa de
  `r = a(1-e²)/(1+e·cos ν)` → tooltip `r = X.XX AU · ν = YY° · JDDDD.D`.
- **Reset** de encuadre: doble clic sobre la escena llama `fit_to_scene()`.

**API pública** (misma entrada que `draw_orbit`, sin `out`):
```python
class OrbitChart(ChartView):
    def set_elements(self, elements: dict, jd: float, obj_name: str = "") -> None: ...
    def start_animation(self, jd0: float, jd1: float, period_s: int = 8) -> None: ...
    def stop_animation(self) -> None: ...
    @Signal
    def date_moved(self, jd: float): ...  # emite al arrastrar el slider / play
```

**Verificación**: test unitario offscreen
- `set_elements` no lanza; el punto en un `jd` dado coincide (a ±1e-6) con la
  posición calculada por `kepler_ra_dec` del mismo objeto.
- `export_png(tmp)` > 8 KB.
- `start_animation(jd0, jd0+10, period_s=1)` → `processEvents(200 ms)` →
  `date_moved` se ha recibido y el `jd` mostrado es distinto de `jd0` (o el punto
  se movió).
- Hover en el punto medio de la elipse (bisección por `mapToScene`) → el último
  texto del tooltip contiene `ν =` y `r =`.

**Decisión al terminar**: ¿control de animación con slider + play/pause, o solo
play/pause? (mi lectura: slider + play/pause, porque el slider es el "punto de
partida" para arrancar la animación y el widget no puede arrancar sin saber
"desde cuándo"); ¿velocidad por defecto razonable (8 s para una órbita completa)?

---

## Fase 3 — `SkyChart` (+ `TransitChart`)

**Objetivo**: la curva de visibilidad vectorial con **hover hora/altura exactos**,
ventana segura resaltada y mejor hora marcada.

**Fichero nuevo**: `nightscribe/gui/widgets/sky_widget.py`

**Escena** (datos de `core/coords` — misma fuente que `draw_sky`):
- rejilla + ticks de horas (UTC reales) y altitud.
- curva de altitud del objetivo (`QGraphicsPathItem`).
- curva de la Luna.
- `safe_window` → `QGraphicsRectItem` semi-transparente.
- `best_time` / `latest_safe_start` → `QGraphicsLineItem` vertical + etiqueta.
- límite local (30° o `horizon.alt_at(az)`).
- **`TransitChart(SkyChart)`**: `QGraphicsRectItem` de sombra del tránsito
  (entrada `transit`).

**Interactividad**:
- **Hover sobre la curva**: bisección en `samples_tonight` (mismo diccionario de
  series que `draw_sky` construye hoy, 10 min de resolución) → tooltip
  `HH:MM UTC · alt NN° · az MM°`.
- **Hover sobre `safe_window`**: `de HH:MM a HH:MM · empezar hasta HH:MM`.
- **Click en `best_time`** → señal `best_time_clicked(dt)` (quién la conecta: Fase
  4).

**API pública**:
```python
class SkyChart(ChartView):
    def set_target(self, ra, dec, lat, lon, date, obj_name="",
                   safe_window=None, best_time=None, horizon=None,
                   transit=None) -> None: ...
    @Signal
    def best_time_clicked(self, dt: object): ...  # datetime UTC
```

**Verificación**:
- `set_target(..., safe_window=(t0, t1))` → hay un `QGraphicsRectItem` en la escena.
- Hover en el pixel del medio de la curva → el tooltip contiene `HH:MM` y `alt`.
- `TransitChart` con `transit={"ingress":t1,"egress":t2}` → hay rect de sombra.
- `export_png` > 8 KB.

**Decisión al terminar**: ¿el tooltip muestra azimut o solo hora+altura? (mi lectura:
hora+alt+az, ya que la azimut es la dato útil para apuntar — se agrega al texto sin
cambiar el layout).

---

## Fase 4 — Integración en GUI

**Ficheros**:
- `gui/overview.py` — los slots 2×2 dejan de ser `QLabel+QPixmap` y pasan a ser el
  widget correspondiente (`OrbitChart`/`SkyChart`/`TransitChart`). Borrar
  `_fit_slots` (el widget se auto-ajusta). La etiqueta `QLabel("—")` de *empty* se
  queda solo para el estado sin datos.
- `gui/chart_viewer.py` — `ChartViewer` deja de cargar `QPixmap`; se convierte en un
  contenedor que abre el widget. "Export PNG…" → `ChartView.export_png()`; el
  botón "1:1" → `fit_to_scene()`. **Borrar** el "Export SVG" (o dejarlo ausente, seg
  decisión #5). **Borrar** el `QScroller` y el `QScrollArea` (el widget gestiona
  zoom/pan).
- `gui/main_window.py` — si hay referencias al viewer, migrarlas.
- `core/post.py` — **no cambia** (sigue generando los PNGs de redes, ADR-010/024
  intacto).
- `tests/unit/test_overview_panel.py` — actualizar para el widget (en vez de
  `QPixmap`).
- `tests/unit/test_chart_viewer.py` — actualizar (en vez de `QPixmap`).

**Tests que NO se tocan** (siguen verdes porque no cambian):
- `tests/functional/test_functional.py` (líneas 272-434)
- `tests/unit/test_style.py::test_draw_orbit_panel_figure_dimensions`

**Verificación**: suite completa unit + funcional verde.

**Decisión al terminar**: ¿panel y viewer usan **la misma instancia** del widget (un
mismo widget se re-pinta al cambiar de tamaño) o se usan dos instancias idénticas
(simpler pero un poco más caro en memoria)? ¿el proyecto guarda el "estado"
(zoom/fecha) del widget entre sesiones?

---

## Fase 5 — Docs y limpieza

- `docs/adr/ADR-010-matplotlib.md` → actualizar el "Scope" para que quede
  explícito que el **post/exports** sigue en matplotlib y la GUI tiene su propia
  capa de widgets (referencia a ADR-029).
- `docs/WORKFLOWS.md` → marcar la fase y el siguiente punto de entrada.
- `AGENTS.md` → una línea sobre la capa `gui/widgets` (paquete nuevo).
- Revisar imports de `QPixmap` huérfanos (si quedó alguno).
- Suite verde + commit de cierre.

---

## Riesgos / notas de implementación

1. **Offscreen (`QT_QPA_PLATFORM=offscreen`)**: en algunos entornos `render()`
   necesita `processEvents()` antes; añadirlo en los tests que exportan.
2. **`_orbit_xy`** vive en `viz/orbit_view.py` que importa `matplotlib.pyplot` a
   nivel de método (no de módulo), pero `viz.orbit_view` sí lo importa a su
   import. Extraer la matemática (elipse por Kepler) a `core/orbit_math.py` para
   que `gui/widgets` no arrastre a `viz` y no arrastre a `matplotlib.pyplot`.
   Ambos módulos (`viz/orbit_view.py` y `gui/widgets/orbit_widget.py`) pasan a
   importarlo.
3. **Colores**: `viz.style` ya define `BG/ACCENT/MUTED` sin depender de
   `matplotlib.pyplot` (solo de `matplotlib` para `rcParams`, que sí arrastra).
   Para evitar arrastrar `matplotlib` en `gui/widgets`, copiar las 6 constantes
   de color a `gui/theme.py` (que ya existe) o a `gui/widgets/palette.py` nuevo,
   y que `viz.style` las importe de allí (no al revés). Así `gui/widgets` no
   necesita `viz.style` en absoluto.
4. **Zoom/pan sin perder el contenido**: `setSceneRect` al rect unió del
   contenido (lo devuelve `scene_rect_hint` por defecto), para que el zoom no
   "corte" el contenido al salir del rect original.
5. **Tooltip**: `QGraphicsSimpleTextItem` con fondo semi-transparente
   (`QBrush(QColor(0, 0, 0, 160))`); se mueve con `moveBy` en cada
   `mouseMoveEvent` (no re-crear, es lento).

## Comandos

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/unit -q
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/functional -q
```
