# Plan — Vista vectorial en la GUI de las gráficas de órbita y visibilidad

**rama**: `feat/qt-chart-widgets` · **arranca sobre**: `25e9346` (ux-v3-projects)
**fecha**: 2026-09-02 · **autor**: FJC (con la IA)

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

## Decisiones ya tomadas (no reabrir salvo causa)

| # | Decisión | Valor |
|---|----------|-------|
| 1 | El hotfix del "hueco lateral" del PNG exportado | **Dentro de este plan** (Fase 0) |
| 2 | El **post de redes** (PNGs `orbit.png/sky.png/…` del markdown) | Siguie vía **matplotlib** — ADR-010 intacto (opción **3a**) |
| 3 | Alcance de la 1ª iteración | **OrbitChart + SkyChart** (Transit como subclase) |
| 4 | El "hueco lateral" que se ve | Está en **el PNG que se descarga** (no solo en el panel) |

## Estado global (actualizar al terminar cada fase)

- [ ] **Fase 0** — PNGs exportados sin franja lateral (hotfix, dentro del plan)
- [ ] **Fase 1** — ADR-029 + `ChartView` base (zoom/pan/fit/export/hover)
- [ ] **Fase 2** — `OrbitChart` (animación + hover de r/ν/t)
- [ ] **Fase 3** — `SkyChart` (+`TransitChart`) (hover hora/altura, ventana segura)
- [ ] **Fase 4** — Integrar en `overview.py` / `chart_viewer.py` / proyectos
- [ ] **Fase 5** — Docs (ADR-010 alcance, WORKFLOWS) + limpieza

> Regla de oro: cada fase termina **con la suite verde** (`tests/unit` +
> `tests/functional`) y **commitado**. Después se decide si seguimos, paramos o
> corregimos. El estado global de arriba es el ancla de recuperación.

---

## Fase 0 — PNG exportado sin franja lateral

**Objetivo**: `style.save()` recorta al **contenidos del eje** (no a toda la
figura), de modo que en formatos anchos (`facebook` 1200×630, `panel` 1200×675) el
PNG ya no trae ~300 px vacíos a la derecha.

**Causa** (verificado): `fig.savefig(bbox_inches="tight")` mide la bounding box de
*toda la figura* (título + watermark + ax). Con un ax `set_aspect("equal")` en un
canvas rectangular, el ax queda centrado en vertical dejando hueco lateral que el
tight_bbox conserva.

**Ficheros**:
- `nightscribe/viz/style.py` — reemplazo de `save()`.
- `tests/unit/test_style.py` — test de "hueco lateral < 10% del ancho".

**Pasos**:
1. En `save()`: `fig.canvas.draw()`; `r = fig.canvas.get_renderer()`;
   `box = ax.get_tightbbox(r)` (o del ax más ancho si hay varios); aplicar
   padding que cubre título (arriba) y watermark (abajo); `fig.savefig(...,
   bbox_inches=box)`.
2. Careta: no romper `fig` (los tests comprueban `get_size_inches()` del `new_fig`),
   solo el recorte al guardar.
3. Test: para `facebook`/`panel`, medir el PNG y afirmar `hueco_derecho < 0.10*W`
   y `hueco_left < 0.10*W`.

**Verificación**: `pytest tests/unit/test_style.py -q` + una llamada de
`draw_orbit(..., fmt="facebook")` midiendo el PNG.

**Decisión al terminar**: ¿margen lateral mínimo aceptable? ¿padding fijo o %?

---

## Fase 1 — ADR-029 + `ChartView` base

**Objetivo**: un `ChartView(QGraphicsView)` reutilizable con zoom, pan, fit al
ventana, hover, y export PNG/SVG. Aquí no se dibuja órbita ni cielo todavía.

**Ficheros nuevos**:
- `docs/adr/ADR-029-qt-view-widgets.md` (bilingüe; aclara que la **GUI** usa
  PySide6/QGraphics y el **post** sigue en matplotlib ADR-010).
- `nightscribe/gui/widgets/__init__.py`
- `nightscribe/gui/widgets/base_chart.py` — `ChartView`.

**Capacidades de `ChartView`**:
- zoom bajo el cursor (`setTransformationAnchor(AnchorUnderMouse)`, `setDragMode(RubberBandDrag)` desactivado; `wheelEvent` → `scale`).
- pan (arrastrar) — opcional, detrás de zoom.
- `fit_to_window()` recalculado en `resizeEvent`.
- `export_png(path, dpi=100)` → `QGraphicsView.render(QPainter(QPixmap))`.
- `export_svg(path)` → `QGraphicsSvgGenerator` (marcado "experimental").
- `set_hover_probe(fn)` — hook que los hijos usan para el tooltip; tooltip flotante
  propio (`QGraphicsSimpleTextItem` + `QTimer`).
- fondo + colores desde `viz.style` (BG/ACCENT/MUTED) — **solo lecturas**, sin
  importar `matplotlib.pyplot`.

**Reglas del paquete `gui/widgets`**:
- solo importa `core/*` (matemática) y `PySide6`.
- **no** importa `matplotlib`.
- si necesita la forma de una curva (p.ej. la elipse), usa `core/*` (ver Fase 0
  nota: `viz/orbit_view._orbit_xy` depende de `ephem_minor`; si `viz/orbit_view.py`
  importa `matplotlib.pyplot` a nivel de módulo, **extraer** `_orbit_xy` a
  `core/ephem_minor.py` o `core/orbit_math.py`).

**Verificación**: test unitario — construir un `ChartView` offscreen con un
`QGraphicsRectItem`, `fit_to_window`, `export_png` genera PNG > 2 KB; no se importa
`matplotlib` (`"matplotlib" not in sys.modules` tras el import — o usar un
subprocess limpio).

**Decisión al terminar**: ¿export SVG experimental en la 1ª iteración o lo dejamos
como follow-up? (mi lectura: fuera, para no alargar)

---

## Fase 2 — `OrbitChart`

**Objetivo**: el gráfico de órbita vectorial, con **animación** por fecha y **hover**
que devuelve `r/ν/t` en el punto bajo el cursor.

**Fichero nuevo**: `nightscribe/gui/widgets/orbit_widget.py`

**Escena** (fuentes de datos ya existentes):
- anillos de los planetas en el marco (`QGraphicsEllipseItem`) — mismo criterio "solo
  si cabe" que el `draw_orbit` corregido.
- la elipse del objeto: polyline 360 puntos (reutilizar/extraer `_orbit_xy`).
- el punto del objeto en `jd` (`core/ephem_minor.kepler_ra_dec` + `_elements_to_ecliptic`).
- Sol + etiquetas (`QGraphicsTextItem`).

**Interactividad**:
- **Animación**: `start_animation(jd0, jd1, period_s)` / `stop_animation()`;
  `QTimer(20 ms)` mueve el punto y actualiza un `QGraphicsTextItem` de fecha.
  Botón `⏵/⏸` + `QSlider` de fecha (JD).
- **Hover sobre la elipse**: hit-test sobre el path → `ν` por inversa de
  `r = a(1-e²)/(1+e·cos ν)` → tooltip `r = X.XX AU · ν = YY° · JDDDD.D`.
- **Reset** de encuadre (doble clic).

**API pública** (misma entrada que `draw_orbit`, sin `out`):
```python
class OrbitChart(ChartView):
    def set_elements(self, elements: dict, jd: float, obj_name: str = "") -> None: ...
    def start_animation(self, jd0: float, jd1: float, period_s: int = 8) -> None: ...
    def stop_animation(self) -> None: ...
```

**Verificación**: test unitario offscreen — `set_elements(…)` no lanza; el punto
en una `jd` concreta está donde `kepler_ra_dec` dice; `export_png` genera PNG > 8 KB;
`start_animation` + 100 ms → la fecha del widget avanzó; hover en un punto
mid-elíptico → el último tooltip contiene `ν =`.

**Decisión al terminar**: ¿control de animación con slider, o solo play/pause? ¿velocidad
por defecto razonable?

---

## Fase 3 — `SkyChart` (+`TransitChart`)

**Objetivo**: la curva de visibilidad vectorial con **hover hora/altura exactos**,
ventana segura resaltada y mejor hora marcada.

**Fichero nuevo**: `nightscribe/gui/widgets/sky_widget.py`

**Escena** (datos de `core/coords.samples_tonight` + `core/planner`):
- rejilla + ticks de horas (UTC reales) y altitud.
- curva de altitud del objetivo (`QGraphicsPathItem`).
- curva de la Luna.
- `safe_window` → `QGraphicsRectItem` semi-transparente.
- `best_time` / `latest_safe_start` → `QGraphicsLineItem` vertical.
- límite local (30° o `horizon.alt_at(az)`).
- **`TransitChart(SkyChart)`**: `QGraphicsRectItem` de sombra del tránsito (entrada
  `transit`).

**Interactividad**:
- **Hover sobre la curva**: bisección en `samples_tonight` → tooltip
  `HH:MM UTC · alt NN° · az MM°` (no se recalcula nada, la serie ya vive en `core`).
- **Hover sobre `safe_window`**: `de HH:MM a HH:MM · empezar hasta HH:MM`.
- **Click en `best_time`** → señal `best_time_clicked(dt)`.

**API pública**:
```python
class SkyChart(ChartView):
    def set_target(self, ra, dec, lat, lon, date, obj_name="",
                   safe_window=None, best_time=None, horizon=None,
                   transit=None) -> None: ...
```

**Verificación**: test unitario offscreen — `set_target(…)` con `safe_window` hay
un rect en escena; hover en una hora concreta → tooltip contiene `HH:MM` y `alt`;
`TransitChart` con `transit={"ingress":t1,"egress":t2}` hay rect de sombra.

**Decisión al terminar**: ¿el tooltip muestra azimut o solo hora+altura? ¿señal
`best_time_clicked` la conecta ahora alguien o se deja para Fase 4?

---

## Fase 4 — Integración en GUI

**Ficheros**:
- `gui/overview.py` — slots 2×2 dejan de ser `QLabel+QPixmap` y pasan a ser el
  widget correspondiente. Borrar `_fit_slots` (el widget se auto-ajusta). `QLabel("—")`
  se queda solo para el estado *empty*.
- `gui/chart_viewer.py` — `ChartViewer` deja de cargar `QPixmap`; se vuelve el widget;
  "Export PNG…" → `ChartView.export_png()`; "Export SVG…" (si existe) → `export_svg()`.
- `gui/main_window.py` — abrir el gráfico del proyecto usa el widget.
- `core/post.py` — **no cambia la generación de PNGs** para el post (ADR-024/010 intacto).

**Tests a reescribir** (ahora asumen `QPixmap`):
- `tests/unit/test_overview_panel.py`
- `tests/unit/test_chart_viewer.py`

**Tests que NO tocan** (siguen verdes porque `draw_*`/`build_charts` no cambian):
- `tests/functional/test_functional.py` (líneas 272-434)
- `tests/unit/test_style.py::test_draw_orbit_panel_figure_dimensions`

**Verificación**: suite completa unit + functional.

**Decisión al terminar**: ¿el panel (overview) y el viewer usan el **mismo** widget
o dos instancias? ¿el proyecto guarda el "estado" (zoom/fecha) del widget?

---

## Fase 5 — Docs y limpieza

- `docs/adr/ADR-010-matplotlib.md` → "Accepted (alcance: export de redes)".
- `docs/WORKFLOWS.md` → marcar la fase y el siguiente punto de entrada.
- `AGENTS.md` → una línea sobre la capa `gui/widgets`.
- Revisar imports de `QPixmap` ya huérfanos.
- Suite verde + commit de cierre.

---

## Riesgos / notas de implementación

1. Offscreen: `widget.show(); app.processEvents()` antes de `render()`/`get_tightbbox`.
2. `QGraphicsSvgGenerator` no maneja `QFont` igual → SVG marcarse como experimental.
3. `hover` preciso: bisección en `samples_tonight` (144 pts) — barato.
4. `QGraphicsView` sin `setSceneRect` limita el zoom → fijar `sceneRect` al contenido.
5. `_orbit_xy` vive en `viz/orbit_view.py` que importa `matplotlib.pyplot`; si es a
   nivel de módulo, **extraer** la matemática a `core/` para que `gui/widgets` no
   arrastre matplotlib.

## Comandos

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/unit -q
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/functional -q
```
