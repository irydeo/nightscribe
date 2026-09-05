# Plan — ApproachChart visual polish (halos + dashes + label plates)

**rama**: `feat/qt-chart-widgets` (sobre `e5b01b5` — cierre Slice 5 del plan approach-chart)
**fecha**: 2026-09-05 · **autor**: FJC (con la IA)

## Decisión del usuario (2026-09-05)

1. **Separación Tierra/Luna/objeto**: halos de separación (anillo fino del
   color del cuerpo), NO iconos.
2. **1 LD circle + traza**: **punteados** (`[2,4]` y `[8,5]` respectivamente).
3. **Etiquetas**: NO se mueven con el scrub (fijas en el frame).
4. **Plan aprobado** tal como se planteó (3 slices A/B/C).

## Problema a resolver

Los puntos actuales (Tierra, Luna, punto objeto, diaminante CA) son simples
dots sobre la traza; cuando `r_au` se acerca a la escala de la Luna los
cuerpos se pisan. Las etiquetas se dibujan a ciegas (offset fijo arriba-
derecha, sin fondo) y se funden con la traza o el círculo de 1 LD.

## Archivo a tocar

- **Código**: `nightscribe/gui/widgets/approach_widget.py` (único).
- **Tests**: `tests/unit/test_approachchart.py` (ampliar in-place, mismo
  fixture `qapp`/`_mk_chart`).
- **Docs**: `docs/VIZ.es.md`, `docs/VIZ.md`, `docs/adr/ADR-029-qt-view-
  widgets.md`.
- **Intactos**: `base_chart.py`, `core/*`, `orbit_widget.py`,
  `sky_widget.py`.

## Diseño

### 1. Nuevas constantes (top of file)

```
_Z_HALO      = 1.5        # nuevo, entre traza y marcadores
_DOT_EARTH   = 18         # era 14
_DOT_MOON    = 14         # era 10
_DOT_POINT   = 16         # era 14
_DOT_CA      = 14         # era 10
_HALO_EARTH  = 42         # diámetro del halo
_HALO_MOON   = 34
_HALO_POINT  = 40
_HALO_CA     = 34
_FONT_PX     = 28         # era 26
_CIRCLE_PEN  = 1.5        # era 1.0
_CIRCLE_DASH = (2, 4)     # nuevo: punteado
_TRACK_PEN   = 2.4        # era 1.8
_TRACK_DASH  = (8, 5)     # nuevo: punteado
_PLATE_PAD   = (6, 8)     # padding placa (x, y) en scene units
_PLATE_BG_A  = 217        # ~85 % alpha sobre BG reutilizado
_PLATE_BRD_A = 102        # ~40 % alpha sobre MUTED
_COL_TOL     = 0.05       # fracción de _HALF: "la etiqueta cruza la traza"
```

`DIRS8` (vectores normalizados, a ser probadas en orden con `preferred`):
```
( 1,-1) NE   ( 1, 0) E    ( 1, 1) SE   ( 0, 1) S
(-1,-1) NW   (-1, 0) W    (-1, 1) SW   ( 0,-1) N
```

### 2. Halos

Helper `_add_dot_with_halo(cx, cy, r, halo_d, color, z_dot)` en el widget:
- `QGraphicsEllipseItem` (diámetro `halo_d`, `NoBrush`,
  `QPen(color, 1.5)`, cosmetic, z `_Z_HALO`) — anillo de separación.
- dot clásico (relleno, sin pen) a z `_Z_MARK` — igual que hoy.

Se usa para: Tierra, Luna, punto móvil, diamante CA.

Z-order final:
```
0.0  1 LD circle
1.0  track polyline
1.5  halos
2.0  dots + diamante CA
3.0  punto móvil
4.0  placas de etiquetas
5.0  texto de etiquetas
```

### 3. Placas + anti-colisión

Estado nuevo del widget: `self._occupied: list[QRectF] = []`, reseteado
en `_build_scene`.

Helper puro (staticmethod, testable sin `QApplication`):
```
_pick_label_offset(anchor, text_size, track_pts, occupied, tol,
                   preferred=(1, -1)) -> (dir_used, offset_scene)
```
- Recorre `DIRS8` empezando por `preferred`.
- Para cada dirección: `plate = QRectF(anchor ± offset ± pad ± half)`.
- Descarta una dirección si:
  (a) alguna esquela de `plate` está a distancia < `tol` de algún punto
      de `track_pts` (hit-test contra la traza);
  (b) `plate.intersects(rect)` para algún `rect in occupied`.
- Devuelve `(dir, offset)`. Si todas fallan, usa el primero (caída simple).

`_add_label(text, ax, ay, color, bold, preferred_dir)`:
1. Mide el texto con `QFontMetrics` (font del widget, `_FONT_PX`).
2. Llama a `_pick_label_offset(anchor=(ax, ay), …)`.
3. Añade `QGraphicsRectItem` (placa): `QBrush(BG, _PLATE_BG_A)` +
   `QPen(QColor(MUTED), 1)` con alpha `_PLATE_BRD_A`, z `_Z_LABEL`.
4. Añade `QGraphicsSimpleTextItem` centrado en la placa, z `_Z_LABEL + 1`.
5. Guarda `plate` en `self._occupied`.

Direcciones preferidas por etiqueta:
- Tierra → `(1, -1)` NE
- Luna → `(1, -1)` NE
- "1 LD" → `(-1, -1)` NW — entra *dentro* del círculo de 1 LD
- CA → perpendicular **hacia fuera** a la traza local (tangente a
  ±1 punto en `_track_pts` alrededor del CA; si tangente ~ 0 cae a
  `(0, -1)`)

Los textos son **fijos en el frame** (no se mueven con el scrub — pedida
del usuario).

### 4. Dashes de traza y 1 LD circle

`_draw_track`:
```
pen = QPen(QColor(palette.ACCENT), _TRACK_PEN)
pen.setCosmetic(True)
pen.setDashPattern(list(_TRACK_DASH))
```

1 LD circle:
```
pen = QPen(QColor(palette.MUTED), _CIRCLE_PEN)
pen.setCosmetic(True)
pen.setDashPattern(list(_CIRCLE_DASH))
```

(En ambos: `cosmetic=True` obligatorio con `setDashPattern` — la línea no
engrosa con zoom, regla ADR-029.)

## Tests (añadidos a `tests/unit/test_approachchart.py`)

5 nuevos tests + mantener los 12 existentes:

1. `test_halos_present` — tras `set_elements`, la escena tiene ≥ 4
   `QGraphicsEllipseItem` con `brush() == NoBrush` y pen width ≥ 1.0.
2. `test_track_pen_dashed_wider` — el `QGraphicsPathItem` de la traza tiene
   `pen().widthF() >= 2.0` y `pen().dashPattern()` no vacío.
3. `test_circle_pen_dashed` — el `QGraphicsEllipseItem` de 1 LD
   (`NoBrush`) tiene pen width ≥ 1.2 y `dashPattern ≈ [2, 4]` (±0.01).
4. `test_label_plates_present` — ≥ 4 `QGraphicsRectItem` con brush alpha
   (placas, no tooltip — `tip_panel` tiene `_TT_BG` alpha 170 y borde
   `_TT_BORDER`, las placas alpha 217 sobre BG).
5. `test_labels_clear_of_track` — para cada placa,
   `min(dist(corner, p)) > _HALF * _COL_TOL * 0.5` para todo `p in
   track_pts`. (La placa no está "pegada" a la traza salvo en el
   ancla — la distancia mínima desde el anchor sí puede ser 0, pero
   desde la placa no.)

`tests/unit/test_approach_math.py`: **sin cambios** (la matemática de
etiquetas vive en el widget, no en core — es estética, no astrofísica).

## Docs

**`VIZ.es.md`** — añadir a la sección *ApproachChart* (tras las viñetas
actuales):
> Halos de separación (anillo fino del color del cuerpo) alrededor de
> Tierra, Luna, punto del objeto y diamante CA. Etiquetas (Tierra / Luna /
> 1 LD / CA) sobre una placa de fondo (BG al 85 % + borde MUTED) que no se
> funde con la traza. Posicionamiento anti-colisión: cada etiqueta prueba 8
> direcciones alrededor de su ancla (empezando por la más natural) y elige
> la primera cuyo rect no cruce la traza ni otra placa. Traza discontinua
> 2.4 px `[8, 5]`; círculo de 1 LD punteado 1.5 px `[2, 4]`.

**`VIZ.md`** — réplica en inglés.

**`ADR-029-qt-view-widgets.md`** — ampliar la línea `approach_widget.py`
(ES + EN) con "halos de separación, placas de rótulo con anti-colisión,
traza discontinua y círculo 1 LD punteado".

## Slices / commits

| # | Contenido | Files | Tests | Suite |
|---|---|---|---|---|
| **A** | Halos + tamaños + dashes de traza y círculo. Sin placas aún (etiquetas en su offset original, solo más grandes). | `approach_widget.py` | 3 (halos, dashes traza, dashes círculo) | verde + commit |
| **B** | Placas + `_pick_label_offset` + `DIRS8` + `preferred` por etiqueta + CA perpendicular. | `approach_widget.py` | 2 (placas, anti-colisión) | verde + commit |
| **C** | Docs (VIZ×2 + ADR-029). Sin código nuevo. | 3 docs | 0 | verde + commit |

Regla de oro: cada slice termina con `pytest tests/unit` verde y
`git commit` antes de empezar la siguiente.

Mensajes:
```
Gui: ApproachChart visual polish — halos, dashed track + 1 LD circle (ADR-029)
Gui: ApproachChart label plates + anti-collision direction picker (ADR-029)
Docs: ApproachChart visual details in VIZ.es/md and ADR-029 (ADR-029)
```

## Riesgos / notas

- **Rendimiento**: 4 esquinas × ~180 pts × 4 etiquetas ≈ 3 000 distancias
  cuadradas por `set_elements` — ignorable.
- **`setDashPattern`** requiere `cosmetic=True` — ya marcado.
- **`_pick_label_offset`** es puro pero usa `QRectF`; `QRectF` es
  construible sin app (se confirma en los tests nuevos).
- **`_occupied` se re-construye en cada `set_elements`** (vía
  `_build_scene`) — sin estado residual entre objetos.
- **No toca** `ChartView.export_png`, `base_chart` ni `orbit_widget` — la
  capa visual de `ApproachChart` es autocontenida.
- **API pública invariante**: `set_elements` / `status_text` /
  `export_png` / `fit` / `date_moved` / `elements` / `geocentric_position`
  tienen la misma firma antes y después; `tests/unit/test_approachchart.py`
  existente sigue verde sin tocar.

