# Plan — Ventana Explorar a su tamaño real + estado de la órbita en `OrbitChart`

**rama**: `feat/qt-chart-widgets` (sobre el cierre del plan `qt-chart-widgets`, ADR-029)
**arranca sobre**: `d9f8244` (cierre Fase 5 `qt-chart-widgets`)
**fecha**: 2026-09-03 · **autor**: FJC (con la IA)

## Objetivo

Dos mejoras de UX en el flujo de Explorar:

1. La ventana "Explorar — \<objeto\>" se abre hoy a **980×720 fijos**, con scroll
   horizontal y vertical para ver toda la información. Debe abrirse al **tamaño
   exacto que necesita su contenido** (hook, bullets, tabla 3-col, 2×2 de
   gráficas, CTA), sin scroll visible.
2. `OrbitChart` emite `date_moved` pero no lo explota: cuando el punto está
   **reproduciéndose** debe decir a qué fecha corresponde; cuando está
   **pausado** debe decir la fecha, la distancia actual (AU) y si en ese
   momento se **acercaba o alejaba** de la Tierra, con la **fecha del
   máximo acercamiento (CA)** dentro de ±60 días. En órbitas abiertas
   (cometas hiperbólicos, e ≥ 1) debe indicarse que **no tiene retorno**
   (no hay CA).

## Decisiones pactadas (2026-09-03)

| # | Decisión | Valor |
|---|----------|-------|
| 1 | Tamaño de la ventana Explorar | Al tamaño que necesite su contenido (el `sizeHint` del panel). No un número arbitrario. |
| 2 | Ventana de búsqueda del CA | ±60 días alrededor de la fecha actual. Sin `scipy`: grid grueso + 4 iteraciones de bisección (~500 evaluaciones de `position_now`, <0.5 s). |
| 3 | Estado de la órbita en el label | **Una sola línea** en AU: Running → `12 Sep 2026 · acercándose`; Pausado → `12 Sep 2026 · 0.421 AU · acercándose · CA: 24 Sep (0.283 AU)`; Abierto → `12 Sep 2026 · 0.512 AU · sin retorno (órbita abierta)`. |
| 4 | Idioma del label | El de la GUI (`config.language` + fallback OS, idéntico a `ObjectPanel._lang()`). Traducido en `.ts`. |
| 5 | Órbita abierta (e ≥ 1) | No se muestra CA ni tendencia (no hay retorno). El label lo indica explícitamente. |

## Arco de diseño

- `_open_explore_dialog` (main_window.py:1979) abre un `QDialog` con un
  `QScrollArea` que contiene `self._explore_panel(name)` (`ObjectPanel`).
  El worker corre **dentro** del panel (señal `finished(dict)` — ver
  `workers.py:26-66`). Cuando el worker termina, `_state_ready(e)` pinta
  todo. La ventana no sabe cuándo está "preparado" (no hay señal `ready`).
- `ObjectPanel` ya emite `project_create` / `project_continue` (líneas
  113-114). El sitio natural para una señal `ready` es justo al lado.
- `OrbitChart.date_moved = Signal(float)` (orbit_widget.py:98) ya existe
  y se emite en `set_elements` y en `_seek_to`. El widget no tiene hoy
  ningún "panel de estado" — los controles son solo `_play_btn` + `_slider`.
  El lugar natural para el nuevo label es la fila de controles (left).
- La matemática (distancia geocéntrica, CA) es pura y sin matplotlib:
  vive en `core/orbit_math.py` (igual que `position_now`, `hover_at`,
  `planet_heliocentric`). La GUI no repite cálculo.

### Cambios de Slice 1 (ventana)

1. **`nightscribe/gui/overview.py`**
   - Añadir señal: `ready = Signal(dict)` justo debajo de
     `project_continue` (línea 114).
   - Emitirla al final de `_state_ready(e)` (línea ~279, al final del
     método, tras `self._state = "ready"`): `self.ready.emit(e)`.

2. **`nightscribe/gui/main_window.py`** — método `_open_explore_dialog`
   (línea 1979):
   - `dlg.resize(720, 540)` — tamaño pequeño inicial (mientras carga).
   - Conectar `panel.ready` a un `_fit_to_content` que lee
     `panel.sizeHint()` y hace `dlg.resize(sh.width(), sh.height())`
     (solo si `sh.width() > dlg.sizeHint().width()` para no empequeñecer
     una ventana ya grande).
   - El `QScrollArea` queda como fallback: si la pantalla del usuario es
     más pequeña que el `sizeHint`, hay scroll; de otra forma no.
   - No tocar `area.setWidgetResizable(True)` ni
     `area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)` (esto
     último se **desactiva**: el scroll H es un último recurso).

3. **Tests** (nuevos, en `tests/unit/test_overview_panel.py`):
   - `test_ready_signal_exists_and_emits`: `ObjectPanel` (offscreen) con
     `FAKE_ELEMENT` fake → al llegar a `ready` el signal `ready` se
     recibe y su `payload` es el dict enriquecido.
   - `test_explore_dialog_resizes_to_panel_hint`: construir el diálogo
     (sin `exec`), entregar un payload fake al instante, `processEvents`
     → `dlg.size() ≈ panel.sizeHint()` (±24 px en ambos ejes). Si no es
     factible sin `exec`, comprobar al menos que el callback `_fit` se
     ejecutó (flag en una lista) y que se llamó a `dlg.resize`.

### Cambios de Slice 2 (órbita)

1. **`nightscribe/core/orbit_math.py`** — 2 funciones (~60 líneas):

   ```python
   def distance_to_earth(elements, jd):
       # @return: geocentric distance in AU, or None if data is
       #          insufficient (no time, or open orbit with no tp).
       pos = position_now(elements, jd)
       if pos is None:
           return None
       ox, oy, oz, _r, _nu = pos
       ex, ey, ez = ephem_minor.earth_ecliptic_xyz(jd)
       return math.hypot(ox - ex, oy - ey, oz - ez)

   def closest_approach(elements, jd_center, half_window_days=60.0, n=480):
       # Grid over [jd_center - half, jd_center + half], then 4 bisection
       # steps of ±1 d narrowing.
       # @return: (jd_ca, dist_au) or None when the orbit is open (e >= 1)
       #          or position_now keeps returning None.
       if elements.get("e", 0) >= 1.0:
           return None
       lo = jd_center - half_window_days
       hi = jd_center + half_window_days
       best_jd, best_d = lo, float("inf")
       for k in range(n + 1):
           jd = lo + (hi - lo) * k / n
           d = distance_to_earth(elements, jd)
           if d is not None and d < best_d:
               best_jd, best_d = jd, d
       # 4-pass bisection shrinking the ±window each time
       w = 1.0
       for _ in range(4):
           a, b = best_jd - w, best_jd + w
           da = distance_to_earth(elements, a)
           db = distance_to_earth(elements, b)
           dbest = distance_to_earth(elements, best_jd)
           if None in (da, db, dbest):
               break
           lo_b, hi_b = a, b
           cand = [(da, a), (db, b), (dbest, best_jd)]
           cand.sort(key=lambda x: x[0])
           best_jd, best_d = cand[0]
           w = (hi_b - lo_b) / 2.0
       return (best_jd, best_d) if best_d != float("inf") else None
   ```

2. **`nightscribe/gui/widgets/orbit_widget.py`**:
   - Importar `QLabel` y `QSizePolicy` (ya importados? — `QSizePolicy` sí; `QLabel` no).
   - Añadir en `__init__`:
     ```python
     self._status_label = QLabel("")
     self._status_label.setMinimumWidth(220)
     self._status_label.setMaximumWidth(560)
     ```
     y al final del layout de `controls` (`row.addWidget(self._status_label, 1)` tras `_play_btn`).
   - Añadir `_lang()` (idéntico al de `ObjectPanel`, línea 418 de `overview.py`).
   - Añadir `_format_date(jd)` — `datetime.fromtimestamp((jd - 2440587.5) * 86400.0, tz=timezone.utc)` → `strftime("%d %b %Y")` / `strftime("%d de %B de %Y".replace("%B" if lang == "es" else "", "%b"))` — simplificar: `strftime("%d %b %Y")` para en y `"%"` para es; o mejor aún: `locale-aware`. Más fácil: `datetime.strftime("%d %b %Y")` en ambos (los mes-abreviados en "es" ya salen en español en la mayoría de los locales).
   - Añadir `_trend(elements, jd, lookback_days=0.02)`:
     - `d0 = distance_to_earth(els, jd)`
     - `d1 = distance_to_earth(els, jd - lookback)`
     - `d0 < d1 - 1e-6` → "approaching" (traducido)
     - `d0 > d1 + 1e-6` → "receding"
     - else "stationary"
     - si `d0 is None` or `d1 is None` → None (no se puede decir)
   - Añadir `_ca` (tupla o None), recalculado en `set_elements()` (solo si `e < 1`) y `stop_animation()`.
   - Añadir `_refresh_status()`:
     - si `_elements is None` or `_cur_jd is None` → label vacío.
     - si `e >= 1` → `"{date} · {d} AU · sin retorno (órbita abierta)"`
     - si `_running` → `"{date} · {d} AU · {trend}"` (sin CA)
     - si no y `_ca` → `"{date} · {d} AU · {trend} · CA: {cad} ({cada} AU)"`
     - si no y `_ca is None` → `"{date} · {d} AU · {trend}"`
   - Llamar a `_refresh_status()` en:
     - `set_elements()` (tras recalcular `_ca`)
     - `_seek_to()` (al final)
     - `_play_tick()` (al final, barato)
     - `stop_animation()` (tras recalcular `_ca`)
   - Publicar `status_text()` (getter que devuelve `self._status_label.text()`).
   - Strings en `gui/i18n/nightscribe_es.ts` y `nightscribe_en.ts`:
     - "approaching" → "acercándose"
     - "receding"    → "alejándose"
     - "stationary"  → "estacionario"
     - "{date} · {d} AU · {trend}"
     - "{date} · {d} AU · {trend} · CA: {cad} ({cada} AU)"
     - "{date} · {d} AU · sin retorno (órbita abierta)"

3. **Tests** (nuevos, en `tests/unit/test_orbit_math.py` y
   `tests/unit/test_orbitchart.py`):
   - `test_distance_to_earth_known_point`: elementos de 433 Eros + JD
     conocido → valor de referencia (SBDB/MPC: ~0.5 AU en 2026-06,
     comparar con ±0.05 AU).
   - `test_distance_to_earth_open_orbit`: elementos `e=1.1` + `tp` →
     número (no `None`), si `tp` está presente; sin `tp` → `None`.
   - `test_closest_approach_returns_minimum`: elementos cerrados con CA
     claro (p. ej. `a=2.3`, `e=0.6`, `ma`/`epoch` tal que CA sea a ~20 d
     de `jd_center`) → `jd_ca` dentro de ±1 d de lo esperado;
     `dist_au_ca < distance_to_earth(els, jd_center)`.
   - `test_closest_approach_open_orbit`: `e=1.1` → `None`.
   - `test_orbit_widget_status_label_bound_paused`: `OrbitChart` offscreen,
     `set_elements(_ELEMENTS, _JD)` → `status_text()` contiene "AU"
     y "CA:".
   - `test_orbit_widget_status_label_running`: `start_animation(...)`,
     `processEvents` (al menos un tick) → `status_text()` **no**
     contiene "CA:", sí contiene la fecha y "AU".
   - `test_orbit_widget_status_label_open`: elementos `e=1.1` →
     `status_text()` contiene el idioma activo para "sin retorno"
     (o "no return").
   - `test_orbit_widget_status_recalculates_on_pause`: `start_animation`,
     `stop_animation` → `status_text()` vuelve a contener "CA:".

   Todos en offscreen (`QT_QPA_PLATFORM=offscreen` — el `conftest.py`
   del plan `qt-chart-widgets` ya lo fija).

## Escopado

Este plan no toca:

- `sky_widget.py` (la curva de visibilidad ya sabe decir su "mejor hora";
  añadir CA de la Luna al horizonte es otra historia).
- `chart_viewer.py` (el `OrbitChart` ya tiene el label embebido; el
  viewer lo hereda gratis).
- `core/post.py` (los PNGs de redes siguen sin el estado: es solo un
  "instantánea" para publicar, no una herramienta interactiva).
- `QPixmap` en `transit` / `field` (out of scope de este plan).

## Orden de ejecución

| Slice | Tocado | Tests | Commit |
|---|---|---|---|
| 1 (ventana) | `overview.py` (+1 señal, +1 emit), `main_window.py` (resize dinámico), `test_overview_panel.py` (+2 tests) | unit+func | `Gui: Explore dialog resizes to panel content (ADR-029)` |
| 2 (órbita) | `core/orbit_math.py` (+2 fns), `orbit_widget.py` (label + lang + trend + CA), `gui/i18n/*.ts` (3 strings), `test_orbit_math.py` (nuevo), `test_orbitchart.py` (+4 tests) | unit+func | `Gui: OrbitChart date + closest-approach status (ADR-029)` |

Dos slices, dos commits, suite verde en cada uno.

## Verificación manual

Después de cada slice, con `DISPLAY=:10.0 .venv/bin/python -m nightscribe gui`:
1. Abrir un NEO de la lista "Esta noche" (click en "Explorar"). La ventana
   debe abrir a su tamaño natural, **sin** scroll H/V.
2. En `OrbitChart`, el punto debe estar en la posición del `ma`/`epoch`;
   el label (izq. fila de controles) debe decir la fecha actual, `d AU`,
   "acercándose/alejándose" y (al pausar) "CA: \<fecha\> (\<d\> AU)".
3. Click en Play → el punto se mueve y el label se Actualiza cada tick
   (fecha+d+trend, sin CA). Stop → vuelve a aparecer el CA.
4. Cambiar `Settings → Language` a EN y reabrir: los textos deben estar
   en inglés.
5. Un objeto con `e ≥ 1` (p. ej. el cometa 3I/ATLAS) → label con
   "sin retorno (órbita abierta)" (o "no return (open orbit)").
