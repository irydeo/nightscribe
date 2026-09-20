# Plan — `ApproachChart`: vista geocéntrica de la aproximación (Tierra / Luna de escala)

> **CIERRADO (2026-09-04)** — las 6 slices están implementadas y a commit
> (`6f91d92`, `a98327f`, `ab72de5`, `ecece37`, `127303b`, Slice 5 docs).
> Suite unitaria verde. Este documento queda como registro de diseño.

**rama**: `feat/qt-chart-widgets` (sobre el cierre de `explore-orbit-state`, ADR-029)
**arranca sobre**: `767633b` (Slice 2 `explore-orbit-state`)
**fecha**: 2026-09-04 · **autor**: FJC (con la IA)

## Objetivo

Añadir una nueva carta **vectorial, interactiva y animada** que muestre cómo
se acerca el objeto **visto desde la Tierra**, usando la **Luna como vara de
escala**. Es la versión en `gui/widgets/` del inset estático que `viz/orbit_view.py`
ya dibuja en las PNG de orbita (líneas 145-185: "_draw_approach_inset") — el
mismo "pasa a X distancias lunares" que ya usan `narrative`, `suggest` y `orbits`,
pero en vivo: con Play, scrub, hover y export PNG.

Hoy la carta geocéntrica de aproximación solo existe como **inset matplotlib
estático** en las exportaciones de redes. No hay equivalente vectorial en la
GUI. Este plan lo cierra.

No toca las exportaciones PNG: `viz/orbit_view._draw_approach_inset` sigue
haciendo su trabajo para los posts; solo se añade la carta vectorial a la UI.

## Decisiones pactadas (2026-09-04)

| # | Decisión | Valor |
|---|----------|-------|
| 1 | **Ubicación en la UI** | **Nuevo slot** `"approach"` en el grid de charts de `ObjectPanel`. Aparece **solo si el objeto tiene un CA válido**. No sustituye ni enmascara `OrbitChart`. |
| 2 | **Marco de referencia** | **Geocéntrico, eclíptico, norte arriba**: Tierra en el origen, unidades **Distancias Lunares (LD)** = 384 400 km. Referencia de escala: círculo de 1 LD (órbita lunar) + posición actual de la Luna. |
| 3 | **Unidad mostrada** | **LD** en la traza, el punto móvil y el status. (La carta heliocéntrica de `OrbitChart` sigue en AU; no se mezcla.) |
| 4 | **Traza dibujada** | La trayectoria **geocéntrica** del objeto en una ventana de ±30 días alrededor del CA (muestra el acercamiento y la salida). El objeto no siempre dibuja una trayectoria cerrada — es una **traza abierta**. |
| 5 | **Luna como referencia** | Una sola luna estática: la de la fecha actual (posición real en el círculo de 1 LD). No se anima en el círculo — es una **vara de escala**, no un cuerpo móvil. |
| 6 | **Ventana de animación** | ±30 días alrededor del CA por defecto (el CA es la mitad del recorrido). Configuración: `approach_window_days` (config, por defecto 30.0). |
| 7 | **Status line** | Misma forma que OrbitChart: `"<fecha> · <X.XX> LD <tendencia> · CA <X.XX> LD (<fecha CA>)"`. En órbita abierta: `<fecha> · <X.XX> LD <tendencia> · no return (open orbit)`. |
| 8 | **Umbral "más cerca que la Luna"** | Si `CA_LD < 0.5`, se muestra un chip destacado `"¡Más cerca que la Luna!"` (misma frase e idioma que la PNG, línea 171-175 de `viz/orbit_view.py`). |
| 9 | **Slot grid** | 5º slot: `("orbit", "sky", "approach", "field", "transit")`. Posición: fila 2, col 0. `_VECTOR_SLOTS` incluye `"approach"`. |
| 10 | **Orden de trabajo** | Primero `chart_zoom` removal (Slice 0), luego Slices 1→5. |

## Arco de diseño

### Lo que ya existe

- `viz/orbit_view.py:145-185` — `_draw_approach_inset`: inset matplotlib estático
  en la esquina superior derecha. Tierras en el origen, círculo lunar de 1 LD,
  Luna en (1,0) fija, aproximación como línea horizontal a `ld` LD. Etiqueta
  `"X.XX LD"` y, si `< 0.5`, `"¡Más cerca que la Luna!"`.
- `nightscribe/gui/widgets/base_chart.py` — `ChartView`: canvas vectorial con
  zoom/pan/fit/hover/export. Los dos widgets actuales (`OrbitChart`, `SkyChart`)
  ya la subclase. Este nuevo widget hará lo mismo.
- `nightscribe/gui/widgets/orbit_widget.py` — `OrbitChart`: patrón de referencia.
  `ChartView` + fila de controles (Play + slider + status). `_HALF = 500` scene
  units, `scale = _HALF / span_au`. `_build_scene()`, `_sync_point()`,
  `_hover()`, `status_text()`, `start_animation()`, `stop_animation()`,
  `date_moved`.
- `nightscribe/core/orbit_math.py` — puro, sin matplotlib: `position_now`,
  `closest_approach`, `distance_to_earth`.
- `nightscribe/core/ephem_minor.py:134` — `earth_ecliptic_xyz(jd)`: heliocéntrica
  de Tierra.
- `nightscribe/core/ephem_minor.py:151` — `moon(jd)`: posición, distancia, fase,
  elongación de la Luna. Devuelve `dist_km`.
- `nightscribe/viz/palette.py` — `ACCENT`, `ACCENT2`, `MUTED`, `SUN`, `DANGER`,
  `BG`, `FG`, `PLANET_COLORS`.

### Lo que NO hay (y este plan añade)

- `nightscribe/core/approach_math.py` — pura, sin matplotlib, funciones
  geocéntricas (posición geocéntrica, traza, CA geocéntrico, conversión AU↔LD).
- `nightscribe/gui/widgets/approach_widget.py` — `ApproachChart(QWidget)`.
- Slot `"approach"` en `nightscribe/gui/overview.py`.
- Strings i18n en `nightscribe/gui/i18n/nightscribe_{es,en}.ts` para el
  contexto `ApproachChart`.
- Tests unitarios (`test_approach_math.py`, `test_approachchart.py`).
- Actualización de `docs/VIZ.es.md`, `docs/VIZ.md` y `docs/adr/ADR-029-qt-view-
  widgets.md`.

### Matemática nueva (Slice 1)

```python
# nightscribe/core/approach_math.py (puro)
AU_PER_LD = 384400.0 / 149597870.7          # ~0.00257 AU

earth_geocentric(xo, yo, zo, jd) → (xg, yg, zg)   # (obj - Tierra) en AU

geocentric_position(elements, jd) → (xg, yg, zg, r_au, nu)
    # position_now(elements, jd) - earth_ecliptic_xyz(jd)

geocentric_track(elements, jd_center, half_window_days, n) → (xs, ys, zs, r_ls)
    # muestra n+1 puntos uniformes en [jd_center - half, jd_center + half]
    # en LD (r_ls = r_au / AU_PER_LD); los puntos en AU en (xs, ys, zs)

closest_approach_geocentric(elements, jd_center, half_window_days=60.0, n=480)
    → (jd_best, dist_au, dist_ld)
    # grid + bisección (misma lógica que orbit_math.closest_approach,
    #   aquí solo cambia que el resultado ya incluye las LD)

ld_from_au(au) = au / AU_PER_LD
au_from_ld(ld) = ld * AU_PER_LD
```

`closest_approach_geocentric` difiere de `orbit_math.closest_approach` solo en
devolver `dist_ld` también — la minimización es idéntica. Se implementa sobre
`distance_to_earth` para no duplicar el grid.

### Widget (Slice 2)

`class ApproachChart(QWidget)`:

```
┌────────────────────────────────────┐
│  ChartView                         │  ← scene normalizada
│  ┌──────────────────────────────┐  │
│  │  círculo 1 LD (MUTED, 1px)  │  │
│  │  Luna actual (punto gris)    │  │
│  │  traza geocéntrica (ACCENT,  │  │
│  │    discontinua, 180 pts)     │  │
│  │  punto objeto (móvil, ACCENT)│  │
│  │  Tierra (origen, ACCENT2)    │  │
│  └──────────────────────────────┘  │
├────────────────────────────────────┤
│ [Play]  ─────────────────  26Sep · 0.78 LD → · CA 0.61 LD (17Sep)  │
└────────────────────────────────────┘
```

- Mismo `ChartView` que los otros (zoom, pan, fit, hover, export PNG).
- `_HALF = 500.0` scene units. `scale = _HALF / span_au`, `span_au` =
  el diámetro de la ventana geocéntrica/2.
- `set_elements(elements, jd, name="")`:
  1. Calcula `_ca_jd`, `_ca_au`, `_ca_ld` una vez (si `e < 1`; si `e ≥ 1`
     no hay CA, pero la traza sí se muestra).
  2. Calcula `_span_au` = `span_au_for_track`, tal que la traza + la Luna
     entran en el frame (regla: el mayor de 1.5 LD y el max |r_ld| de la
     traza, más 10 % de margen).
  3. Muestra la Luna de la fecha `jd` en su posición real (no gira mientras
     se anima — es una **vara de escala fija** en el instante de carga).
  4. Pinta la traza (polylínea discontinua) y el punto móvil.
- `_build_scene()`: círculo lunar, Luna, Tierra, traza, punto móvil,
  etiquetas ("Tierra", "Luna", `"X.XX LD"`, fecha CA, chip "¡Más cerca!" si
  `CA_LD < 0.5`).
- `_sync_point()`: mueve el punto móvil a `position_now(els, _cur_jd)`
  **geocéntrico** (no heliocéntrico) → `self._to_scene(xg, yg)`.
- `_hover(sx, sy)`: hit-test sobre la traza (misma tolerancia 8 % del
  `orbit_widget._HIT_TOL`); devuelve `"r = X.XX LD"` (y la fecha si
  `date_hint` está activada).
- `status_text()`: como la de OrbitChart, pero en LD y con CA en LD.
- `start_animation(jd0, jd1, period_s)`: punto móvil a lo largo de la traza
  geocéntrica.
- `date_moved = Signal(float)`: mismo que OrbitChart.

Colores (todos de `viz/palette`):
| Elemento | Token |
|---|---|
| Punto objeto (móvil) | `ACCENT` |
| Tierra (origen) | `ACCENT2` |
| Círculo de 1 LD / órbita lunar | `MUTED` |
| Luna | `#c9c9c9` (literal — mismo que la PNG y el icono lunar de la GUI) |
| Traza geocéntrica | `ACCENT` (discontinua) |
| Etiquetas | `MUTED` |
| Etiqueta de CA / chip destacado | `ACCENT` |
| Fondo | `BG` |

### Integración en el panel (Slice 3)

`nightscribe/gui/overview.py`:

- `_TITLE["approach"] = "Approach"` (ES: `"Aproximación"`).
- `_CHART_SLOTS = ("orbit", "sky", "approach", "field", "transit")` — 5 slots.
- `_VECTOR_SLOTS = frozenset({"orbit", "sky", "approach"})`.
- `_slot_rowcol("approach")` → `(2, 0)`.
- `_make_vector("approach", e)`: extrae `els` de `e["data"]["sbdb"]["elements"]`
  (mismo que `orbit`); llama a `ApproachChart.set_elements(els, jd, name)`.
  Devuelve `None` si no hay `els` o si `e.get("e", 0) >= 1.0` **y** `q is
  None` (sin `q` no se puede dibujar la traza).
- `_extract("approach", e)`: dict `{"elements": els, "jd": jd, "name": ...}`.
- `_rebuild_widget("approach", data)`: construye el `ApproachChart` al
  hacer clic y abrir el `ChartViewer`.

El slot aparece **solo si** hay elementos orbitales para `els` — la regla
"omit what is missing" ya se aplica en `_render_charts` (línea 491-508).

### Slices

| Slice | Contenido | Tests | Commits |
|---|---|---|---|
 | **0** — `chart_zoom` removal ✅ | `settings_dialog.ui` (quitar `tab_charts`), `main_window.py:405-410,472-475`, `overview.py:54,479,688-691`, `config.py:52`, `test_settings_tabs.py` (4→3), `ADR-028`, `WORKFLOWS` | suite verde | `6f91d92` |
 | **1** — `core/approach_math.py` ✅ | `AU_PER_LD`, `earth_geocentric`, `geocentric_position`, `geocentric_track`, `closest_approach_geocentric`, `ld_from_au`, `au_from_ld`. Puro, sin matplotlib. | 10 cases en `test_approach_math.py` (no net) | `a98327f` |
 | **2** — `approach_widget.py` ✅ | `ApproachChart`: `set_elements`, `_build_scene`, `_sync_point`, `_hover`, `status_text`, Play/animation. | 12 cases en `test_approachchart.py` (offscreen) | `ab72de5` |
 | **3** — Integración `overview.py` ✅ | Slot `"approach"`, `_TITLE`, `_CHART_SLOTS`, `_VECTOR_SLOTS`, `_slot_rowcol`, `_make_vector`, `_extract`, `_rebuild_widget`. | suite verde + 3 tests nuevos en `test_overview_panel.py` (slot aparece/desaparece) | `ecece37` |
 | **4** — i18n ✅ | Strings en contexto `ApproachChart`: "Tierra", "Luna", "1 LD", "CA X.XX LD", "Play"/"Pause", "no return (open orbit)"; título "Approach" en ObjectPanel. `lrelease` ambos `.qm`. | 3 tests (`test_i18n_approachchart.py`) | `127303b` |
 | **5** — Docs ✅ | `VIZ.es.md`, `VIZ.md`: nuevo § "ApproachChart". `ADR-029-qt-view-widgets.md`: `approach_widget.py` en el scope (ambas lenguas). Este PLAN cerrado. | suite verde | 1 commit (docs) |

### Reglas del paquete (repetidas para el que implemente)

- `gui/widgets/*` **nunca importa `matplotlib`** (ADR-029). Solo `core/*`
  (puro) y `PySide6`.
- Colores de `viz/palette` (no `viz.style`).
- Toda cadena visible → `self.tr(...)`.
- Cabeceras en todos los ficheros `.py`.
- Cada slice termina con suite verde **y** commit antes de empezar el
  siguiente.

### Riesgos / decisiones abiertas que el implementador debe resolver

- **Luna estática vs. animada**: las Decisiones pactadas dicen estática
  (vara de escala). Si algún día se quiere girar, es un añadido, no una
  corrección.
- **Trayectoria geocéntrica abierta en `e ≥ 1`**: la traza sí se muestra
  (se muestra desde q hasta la fecha actual), pero no hay CA ni chip.
  El status lo indica con `"no return"`.
- **`geocentric_track` en órbitas muy abiertas**: el grid de puntos
  uniformes en el tiempo en `[ca_jd - W, ca_jd + W]` puede dejar un objeto
  muy lejano en los extremos. Regla práctica: `n = 180` y el `span_au`
  se calcula sobre los puntos muestreados (no sobre el máx teórico). Si
  la traza sale del frame por un extremo, el `fit_to_scene` la encuadra
  igual (el frame sigue siendo la unión de traza + luna + Tierra).
- **Clic en el slot "approach"**: debe reabrir `ChartViewer` con un nuevo
  `ApproachChart` (no reutilizar el del panel, para no arrastrarle el
  estado). Es el mismo pattern que `"orbit"` / `"sky"` ya usan en
  `_SlotClick`.

### Verificación al cerrar

```bash
.venv/bin/python -m pytest tests/unit tests/functional   # verde
.venv/bin/python -m nightscribe gui    # visual: slot 5 visible solo si hay CA
```
