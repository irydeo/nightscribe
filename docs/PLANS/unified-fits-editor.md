# Plan de implementación: Unified FITS Editor (UFE) (2026-09-22)

> **ESTADO: EN CURSO, FASE A SIN EMPEZAR.** Nada de código escrito todavía;
> la rama `feature/ufe` está en `ffca32c` (igual que `main`), árbol limpio.
> Toda la sesión previa fue: requisitos, decisiones firmadas con el usuario y
> exploración exhaustiva del código. **Empezar en la sección «Estado de la
> sesión» de este fichero e implementar la fase A desde ahí.**
>
> Documento vivo: se actualiza al cierre de cada fase. Requisitos del
> observador en `docs/unified-fits-editor.md`.

## Estado de la sesión (actualizado 2026-09-22, empezar AQUÍ)

**Hecho en esta sesión**

- Rama `feature/ufe` creada desde `main` (`ffca32c`) y subida a GitHub
  (`origin/feature/ufe`). En paralelo vive
  `feature/capture-integration` (`0a4e79b`), que no se toca.
- Requisitos en `docs/unified-fits-editor.md`; este plan en
  `docs/PLANS/unified-fits-editor.md`.
- Decisiones firmadas con el usuario (abajo), incluida la forma de hacer la
  fase B (refactor limpio del estiramiento a `core/stretch.py`) y el zoom,
  decidido desde la fase A porque condiciona el diseño de la vista.
- Exploración completa del código: `ChartView` (`gui/widgets/base_chart.py`)
  mapa de API entero; `core/fits_io.read_fits` y `core/wcs.Wcs`; punto de
  enganche del menú Herramientas en `gui/main_window.py`; patrones de test
  offscreen, fixtures FITS, i18n (`nightscribe_es.ts`), formato de ADR
  (modelo ADR-042). El mapa concreto está abajo en «Mapa de APIs y ficheros».

**Pendiente (todo lo que falta de la fase A)**

1. `nightscribe/gui/ufe_state.py`: `UfeImageState(QObject)` con `load(path)`
   vía `core/fits_io.read_fits` + `Wcs.from_header` (en try/except, None si
   no hay WCS), `d_min/d_max`, límites auto por percentiles 1/99.5,
   `set_stretch(black=, white=, gamma=)` con la invariante white > black,
   `toggle_invert()`, `display_uint8()` (orden fijo, documentado en el ADR:
   downscale 2×2 hasta 4096 px -> estiramiento lineal -> gamma -> invertir),
   `stretch_changed` y
   `image_loaded`, render en QThread con coalescencia de 120 ms (patrón
   `sn_annotate_dialog.py`).
2. `nightscribe/gui/widgets/ufe_image_view.py`: subclase de `ChartView`;
   `setSceneRect` = la imagen a tamaño original; `ZOOM_MAX ≈ 40`,
   `WHEEL_STEP ≈ 1.25-1.5`; sobreescribir el auto-fit de la base para que el
   Fit ocurra solo al cargar (se anula el `resizeEvent` de la base); `fit_to_factor(f)`
   para 50/100/200/400 (100% = 1:1 píxeles de dispositivo); probe hover
   (RA/Dec a través de `wcs.pixel_to_sky` + píxel x/y); estado vacío con
   pista de «abrir un FITS».
3. `nightscribe/gui/ufe_dialog.py`: constructed in code (sin .ui Designer,
   patrón `journal_dialog.py`); barra superior (load FITS / invertir /
   export PNG de lo visible con `ChartView.export_png` / presets de zoom);
   `UfeImageView` a la izquierda (dominante); pestañas a la derecha
   (Blink/Comparar/Anotar como placeholders); tira de histograma abajo
   (placeholder, fase B); `add_feature_tab()` = todo el API de extensión.
4. Menú Herramientas: «Editor FITS…» con acción nueva, handler perezoso
   `_tools_ufe` (patrón `_skycal_build`/`_tools_skycal` en
   `gui/main_window.py`); instancias mantenidas vivas en `self`.
5. ADR-044 bilingüe en `docs/adr/` (modelo: ADR-042): decisiones
   editor unificado + modelado del estado + zoom + límites de memoria +
   coexistencia + reglas de extensión.
6. Tests unitarios (Qt offscreen): `UfeImageState` (loading de ambos
   fixtures, límites auto, rango/gamma/invert del estiramiento, límite de
   downscale); humo offscreen de `UfeImageView` (tamaño de escena, preset
   zoom, probe); construcción del diálogo.
7. i18n: todas las cadenas por `self.tr()` + añadir al `.ts` de
   `nightscribe/gui/i18n/` y recompilar el `.qm` (ver la casa en el
   `test_i18n` test); luego `.venv/bin/python -m pytest tests/unit` verde
   antes del commit.
8. Commit de la fase A + actualización de este plan (marca los checkboxes).

**Reglas inamovibles (leer antes de escribir código)**

- Cabecera del proyecto en TODO `.py` nuevo (copiar de un vecino, adaptar
  el nombre del módulo). Código en inglés, identifiadores y comentarios;
  voz humana: comentarios cortos `# @args:`/`# @return:`, nada de docstring
  robótico.
- Toda cadena visible en la GUI por `self.tr()`; el código del ADR: la
  regla completa está en el `AGENTS.md` de arriba.
- **Coexistencia legacy (fuerte regla, no negociable)**:
  `gui/sn_annotate_dialog.py`, el diálogo legacy de blink y
  `gui/seqchart_dialog.py` no se tocan (salvo re-export de compatibilidad
  de `viz/blink_view.py` en la fase B). Los diálogos legacy siguen funcionando.
- La red SOLO vía `core/db.py` (caché); en la UFE no debería importar
  porque la fase A-F no requieren red excepto la fase F (VSX/DSS2, ya vía
  `core/sources`).
- Docs en lenguaje natural: sin raya «—»; «:», «,» y «;»; guion largo solo
  en rangos numéricos (50-70).

## Decisiones firmadas con el usuario

1. **Rama**: `feature/ufe` creada desde `main`, en paralelo a
   `feature/capture-integration`. Se fusiona a `main` cuando ambos estén
   listos.
2. **Estiramiento (fase B)**: refactor limpio a `core/stretch.py`,
   migrando a los cinco sitios que hoy consumen el pipeline de
   `viz/blink_view.py` (`blink_view` se queda con re-exports de
   compatibilidad, `evolution_view`, `motion_view`, `__main__.py`,
   `sn_annotate_dialog`, `seqchart_dialog`). Los diálogos legacy siguen
   recibiendo el input como hoy (sliders de porcentaje, que pasan
   `value()/10` a la pipeline); la UFE usa DN absoluto.
3. **Zoom**: decidido desde el principio (fase A) porque condiciona el
   diseño de la vista de imagen.

## Decisiones de diseño

### Modelo de escena y zoom

- `ufe_image_view.py` hereda de `gui/widgets/base_chart.py:ChartView`
  (rueda anclada al cursor, pan por arrastre, Fit, export PNG de lo
  visible ya existen).
- **Las coordenadas de escena son la imagen a tamaño original**, aunque
  el pixmap de pantalla se renderice a menor resolución. Marcadores y
  overlays viven en píxeles originales de la placa: el zoom nunca afecta
  la precisión de lo anotado ni de lo exportado (los rotuladores llevan
  `QPen.setCosmetic`, igual que `FinderChart`).
- Zoom: presets Fit/50/100/200/400, tope ~40× (no 4000×: el zoom de
  `ChartView` es en factor sobre fit, no multiplicador de escala; ver el
  ADR), clamping manual (patrón `_zoom_by`), paso de rueda ~1.5 (patrón
  `FinderChart.WHEEL_STEP`), teclas (F fit, +/− zoom, flechas pan).

### Controller de estado (extensibilidad)

- `gui/ufe_state.py`: `UfeImageState(QObject)`:
  - estado: `data` (float 2D original), `wcs` (`core.wcs.Wcs` o None),
    `black/white` (valores DN absolutos), `gamma`, `invertida`,
    `d_min/d_max` del rango de la data.
  - señales: `image_loaded`, `stretch_changed`.
  - métodos: `load(path)` (vía `core/fits_io.read_fits`, que ya colapsa
    RGB a luminancia), `set_stretch(...)`, `auto()` (percentiles 1/99.5),
    `toggle_invert()`, `display_float()` (data visible, estirada e
    invertida, en flotante 0..1).
- El estiramiento corre en `QThread` con coalescencia de 120 ms (patrón
  ya probado en `sn_annotate_dialog.py: _RENDER_COALESCE_MS`).
- **Una funcionalidad nueva es una pestaña**: el widget recibe
  `(state, lang)` y se suscribe a `stretch_changed`. `UfeDialog` expone
  `add_feature_tab()`: ese es todo el API de extensión.
- Overlays de cada funcionalidad se añaden a la vista vía
  `view.add_overlay(item)` / `view.clear_overlays()`, sin pisarse entre
  pestañas.

### Memoria

- Imagen de pantalla a 4096 px de lado (media 2×2 en pasos, sin nuevas
  dependencias), aplicada **antes** de la parte lineal del estiramiento.
  Gamma posterior al redimensionado (el orden es documentado en el ADR).
- Las exportaciones a disco (FITS anotado, PNG completo, lado a lado)
  siempre usan el archivo original, nunca el pixmap de pantalla.

### Negros/blancos

- El estado guarda **DN absolutos** (valores reales de la data). Los
  percentiles solo viven en la UI de los diálogos legacy (blink,
  sn_annotate).
- `core/stretch.py` (fase B): `auto_limits(data, lo_pct, hi_pct)`,
  `apply_stretch(data, black, white, gamma)`, `to_uint8`, `apply_gain`,
  `invert`, `histogram(data, nbins, bounds)`, `display_downscale(data, cap)`.

## Mapa de APIs y ficheros (exploración completada 2026-09-22)

Referencia para la fase A; no rehacer la exploración.

### `gui/widgets/base_chart.py` → `ChartView`

- Atributos de clase: `ZOOM_MIN = 0.05`, `ZOOM_MAX = 8.0`,
  `WHEEL_STEP = 1.25`. `_zoom_by(factor)` clamp a esos límites.
  UFE: `ZOOM_MAX ≈ 40`, `WHEEL_STEP ≈ 1.25-1.5`.
- `fit_to_scene(pad=0.02)`: no-op cuando el viewport es <4 px.
- `resizeEvent`: auto-fit en cada resize vía `_fit_pending` +
  `QTimer.singleShot(0, self._do_fit)`. **UFE debe sobreescribir esto**
  para que el Fit ocurra SOLO al cargar (el zoom del usuario sobrevive a
  los resizes).
- `export_png(path, dpi=100, bg=palette.BG)`: renderiza la escena VISIBLE
  (source + target), cae a 800×450 offscreen si no hay viewport, devuelve
  `Path`. Usar para «Export PNG de lo visible».
- Hover probe: `set_hover_probe(fn)` donde
  `fn(scene_x, scene_y) -> (hit, text|list)`; la fuente de tooltip se
  auto-compensa por la escala de la vista.
- `scene_clicked` signal: se dispara en liberación izquierda con
  desplazamiento <4 px.
- Pan: `ScrollHandDrag`. Chrome cosmético de esquinas ya está.
- Paleta (`viz/palette.py`): `BG="#0b0d17"`, `FG="#e8eaf2"`,
  `MUTED="#8a90a6"`.

### `core/fits_io.py`

- `read_fits(path)` → **`(header dict, data 2-D float32)`** (header
  PRIMERO). La luminancia ya está colapsada (RGB → canal único); BSCALE/
  BZERO ya aplicados.
- `to_luminance(arr)` para el caso que el header diga RGB pero el caller
  quiera forzar la conversión.
- Excepción: `FitsError`.

### `core/wcs.py`

- `Wcs.from_header(header)` → `Wcs` o `None` (cuando no hay CTYPE o es
  inutilizable).
- `pixel_to_sky(x, y)` / `sky_to_pixel(ra, dec)`: 0-based.
- Soporta CD, PC+CDELT, CROTA.
- `pixel_scale()` (deg/px) para la barra de escala.

### `gui/main_window.py` (punto de enganche del menú)

- wiring del menú Herramientas: ~línea 679.
- `_open_blink_dialog` (línea 7107): patrones de sliders de blink a
  reusar en fase E; pasa `sld.value()/10` a la pipeline de estiramiento.
- Patrón de diálogo perezoso a clonar: `_skycal_build` (línea 7720) +
  `_tools_skycal` (línea 7763). Clonar para `_tools_ufe` + `_ufe_build`.

### `gui/widgets/finder_widget.py` → `FinderChart`

- `WHEEL_STEP` más profundo, `ZOOM_MAX` alto, overlays de picker de
  estrellas (fase F). Modelo de referencia para `ufe_image_view.py`.

### `viz/blink_view.py`

- Funciones en la parte superior: `auto_limits`, `apply_stretch`,
  `auto_gain`, `apply_gain`, `to_uint8`, `crop_zoom`. GIF/MP4 encode
  reusado en `motion_view`/`evolution_view`.
- Fase B: se extraen a `core/stretch.py` y `blink_view` mantiene
  re-exports finos para compatibilidad.

### `gui/sn_annotate_dialog.py` (no tocar)

- Patrones a robar para UFE: `_RENDER_COALESCE_MS = 120` y el patrón de
  render-thread con coalescencia.
- Warning de test: shiboken GC-ing de timers/slots segfaulted al final de
  la suite (commit `e31f394`); usar fixture autouse que recoja diálogos
  top-level (close + deleteLater) + stub silencioso de `QMessageBox`.
- Backend de fase D: `core/fits_annotate.write_annotated_fits`.

### Backends de fases

- Fase D (Anotar): `core/fits_annotate.py`.
- Fase E (Blink): `core/blink.py` (`WORK_MAX = 2048`, `resolve_sn`,
  `load_user_image`, `prepare_pair`).
- Fase F (Comparar): `core/compstars.py` (campo, cruce VSX, propuestas
  de comps, CSV).

### Convenciones de test e i18n

- Offscreen: `QT_QPA_PLATFORM=offscreen`, fixture module-scoped `qapp`.
- Imports estilo `from nightscribe.gui.widget import ...` (ver
  `tests/unit/test_finder_widget.py`).
- Fixtures FITS: `tests/fixtures/sn2026zji_new_image.fits` (2047×2047
  float32, rango 0-65535, CTYPE1=RA---TAN-SIP) y
  `tests/fixtures/sample_annotated_image_from_aij.fits`.
- i18n: `nightscribe/gui/i18n/nightscribe_es.ts` (+ `_en.ts`, `.qm`).
  El test `tests/unit/test_i18n*.py` mira que todas las cadenas `tr()`
  estén en el `.ts`; añadir los strings nuevos y recompilar el `.qm`
  (ver el mensaje del commit `c9e2c98`: lupdate puede saltarse cadenas;
  usar literales si no las recoge).
- ADR: `docs/adr/ADR-044-*.md`, estilo de ADR-042 (bilingüe,
  Estado/Fecha, Contexto, Alternativas descartadas, Decisión).

## Layout final (siguiendo el boceto del documento)

```
| Barra superior: Cargar · Invertir · Export PNG · Fit 50 100 200 400  |
|────────────────────────────────────────────────────────────|
|                                | [Blink][Comparar][Anotar]  |
|        IMAGEN (QGraphicsView)  |  controles de la pestaña   |
|                                |                            |
|____________________________|____________________________|
| Histograma visual (tiradores) + gamma + Auto + Invertir + DN finos |
```

## Fases

### A: Esqueleto, carga y vista

- [x] Rama `feature/ufe` desde `main`.
- [x] Plan + documentos en `docs/`.
- [ ] `gui/ufe_state.py`: controller de estado + load de FITS
      (mono/RGB).
- [ ] `gui/widgets/ufe_image_view.py`: vista con zoom completo y
      overlays.
- [ ] `gui/ufe_dialog.py`: layout, barra superior (cargar, zoom,
      invertir, export PNG de lo visible), área de pestañas vacía
      (placeholder por funcionalidad para no romper la rejilla),
      histograma en fase B.
- [ ] Menú Herramientas: «Editor FITS…» (lazy, patrón
      `_skycal_build`).
- [ ] ADR-044 (bilingüe, estilo ADR-042).
- [ ] Tests unitarios: `UfeImageState` (carga mono/RGB, límites auto,
      estirar, invertir) con Qt offscreen + fixtures FITS de tests
      existentes.
- [ ] i18n: todas las cadenas por `self.tr()` + `.ts` actualizado +
      `.qm` recompilado.

### B: Motor de estiramiento + histograma visual

- [ ] `core/stretch.py`; migración de los cinco consumidores;
      `blink_view` re-exporta para compatibilidad.
- [ ] `gui/widgets/histogram_widget.py`: histograma QPainter 256 bins,
      tiradores arrastrables (estilo AstroImageJ), gamma, DN con paso
      fino, Auto, Invertir.
- [ ] Export PNG de lo visible como funcionalidad de serie (ya en barra
      superior).
- [ ] Tests de `core/stretch.py` (percentiles, gamma, invertir,
      downscale).

### C: Comunes pulidas

- [ ] Teclado completo, persistencia del estiramiento entre cargas,
      accesibilidad, pulido.
- [ ] Docs de usuario en `docs/` si procede.

### D: Pestaña Anotar

- [ ] `gui/ufe_annotate_tabs...` sobre
      `core/fits_annotate.write_annotated_fits`: multiplicación de
      imágenes (visitaciones), marcador por clic y ajuste, etiqueta y
      notas, guardar copia (original intacto).
- [ ] El `SnAnnotateDialog` legacy sigue vivo y no se toca.

### E: Pestaña Blink

- [ ] Sobre `core/blink.prepare_pair` + `BlinkWorker`: resolver
      SN/manual, blink vivo (timer), marcador con nudge, balance, export
      GIF/MP4/PNG lado a lado del par.
- [ ] El diálogo legacy de blink sigue vivo.

### F: Pestaña Comparación

- [ ] Sobre `core/compstars` + overlays de `FinderChart`: generar campo
      (DSS2 o FITS propio), picker de estrellas por clic (Comp/Check),
      tabla de secuencia, CSV, PNG de la carta.
- [ ] `SeqChartDialog` legacy sigue vivo.

## Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| `ChartView` asume escenas cuadradas/sintéticas | Probar primero con una placa real de tests; `setSceneRect` ya acepta W×H distinto |
| El pixmap grande (16k px) agota memoria | Cap de 4096 px con 2×2 averaging; los saves usan el archivo original |
| Los percentiles vs DN rompen los diálogos legacy | DN absolutos solo en UFE; legacy sigue con percentiles; `blink_view` re-exporta sin cambios |
| Overlays que se pierden al cambiar de pestaña | `clear_overlays()` del estado de la pestaña al desactivarla |
| Tests GUI lentos | Qt offscreen (`QT_QPA_PLATFORM=offscreen`), fixtures FITS existentes |
| Segfault al final de la suite (shiboken GC) | Fixture autouse que recoja diálogos top-level + `QMessageBox` stub silencioso (patrón del commit `e31f394`) |

## Criterios de aceptación globales

1. Menú Herramientas → Editor FITS… abre la ventana.
2. Cargar una placa mono y una RGB; la imagen ocupa la mayor parte de la
   ventana.
3. Zoom Fit/50/100/200/400 y rueda funcionan; se puede salir del Fit.
4. Las tres funcionalidades legacy siguen funcionando sin tocar (tests
   verdes).
5. Añadir una pestaña nueva no modifica `ufe_dialog.py` salvo un
   `add_feature_tab`.
6. Todo el `tr()` está en su sitio; los tests unitarios pasan en CI.

## Lista de control por fase (cierre)

- [ ] Tests unitarios y funcionales de la fase verdes.
- [ ] Manual de usuario / docs actualizado si aplica.
- [ ] ADR actualizado si alguna decisión cambió.
- [ ] Changelog / README si aplica.
