# Plan de implementación: Unified FITS Editor (UFE) (2026-09-22)

> **ESTADO: TODAS LAS FASES CERRADAS (A-F + D.5, 2026-09-22).** La fase F
> trajo la pestaña Comparar real (`gui/ufe_compare_tab.py` sobre
> `core/compstars` con el lenguaje visual del `FinderChart` como overlays
> de la vista compartida): el campo se genera alrededor del centro de la
> placa con su FOV real (`UfeFieldWorker`, señal `object` para no pasar el
> dict anidado por QVariantMap), el picker por clic replica Comp/Check con
> rechazo de variables VSX y motivo, la propuesta automática usa la
> magnitud del objetivo, la tabla edita nombres/tipos, y los exports son
> el CSV de siempre y el PNG de la escena visible (overlays + HUD
> incluidos). Ya no quedan placeholders: las tres pestañas son reales.
> Suite 1614 verde, i18n 1203 cadenas.
> **Queda pendiente** solo la fusión a `main` cuando se decida, y el
> pulido opcional: atajos extra, drag de comp estrella a estrella, y la
> revisión visual con placas reales del observatorio. La siguiente
> funcionalidad sobre este editor (fotometría calibrada, pestaña Medir)
> tiene su propio plan: `docs/PLANS/ufe-photometry.md` (fases G y H
> cerradas 2026-09-23).
>
> **Revisión con placas reales (2026-09-23, CERRADA)**: los tres fallos
> reportados por el observador están corregidos con tests: las aperturas
> de Medir se aplican en vivo (editar un radio re-mide al instante) y la
> mano gana sobre el auto-seeing hasta la siguiente placa; la magnitud
> del objetivo en Comparar se busca en el proyecto (planner → VSX max →
> secuencia guardada) y se persiste en el contexto al exportar; la tira
> de histograma dejó la altura fija por mínima (las filas ya no se
> pisan).
>
> **Conexión con los flujos (2026-09-23, CERRADA)**: ajuste
> `ufe_default` (Ajustes → Desarrollo, por defecto UFE); enrutado de
> blink (menú y proyecto), carta de comparación y FITS anotado; APIs
> `open_plate`/`show_tab`/`prefill` por pestaña; registro en el proyecto
> vía `set_save_hook` (archivos + contexto de secuencia + protocolo de
> campaña); carga de campo DSS2/PS1 dentro del UFE (botón en Comparar,
> worker con caché `db`); revisión i18n con la causa raíz de los
> apóstrofos documentada (relleno quirúrgico que comparaba el XML crudo:
> `'` vive como `&apos;`). Legacy intacto y alcanzable.

> **Nota de la fase D (resuelta en D.5)**: la flecha de norte y la barra
> de escala llegaron como overlay COMÚN (HUD de viewport, también en el
> PNG exportado), y la resolución astrométrica como funcionalidad común;
> ver la fase D.5 más abajo.

> **Revisión de la convención de extensión (fase D)**: las pestañas de
> funcionalidad reciben `(state, lang, view)` (no solo `(state, lang)`):
> la vista es donde viven los overlays, los clics y el zoom. El API de
> registro sigue siendo solo `add_feature_tab(title, widget)`; la
> activación pasa por `set_active(bool)` en la propia pestaña.
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

### Mejoras firmadas en la revisión previa a la fase A (2026-09-22)

Revisión del diseño contra el código real antes de escribir nada; las
siete quedaron firmadas con el usuario y mandan sobre el texto original
cuando difieran:

1. **Orientación FITS centralizada**: `core/fits_io.read_fits` devuelve la
   fila 0 abajo (convención FITS) y la pantalla necesita `flipud` (patrón
   `sn_annotate_dialog.py:429`). La escena vive en píxeles de placa con y
   hacia abajo (convención de pantalla), y `UfeImageState` ofrece la única
   pareja de conversores `scene_to_data(x, y)` / `data_to_scene(col, row)`
   (`row = H-1-y`). Ninguna pestaña de las fases D/E/F hace flips a mano.
2. **Render síncrono + coalescencia, no QThread**: el patrón real de
   `sn_annotate_dialog.py` es timer single-shot de 120 ms + estiramiento
   síncrono en el hilo GUI. Con el cap de 4096 px el render cuesta del
   orden de 50-150 ms; un QThread solo añade carreras y riesgo de segfault
   shiboken al cerrar. Fase A: coalesce + síncrono; el worker diferido
   queda como opción documentada para la fase C si el profiling lo pide.
3. **Motor de estiramiento provisional sin tocar legacy**: la fase A
   reutiliza `viz/blink_view.auto_limits/apply_stretch/to_uint8` (ya
   testados) más helpers privados de downscale e inversión (`1.0 - x`
   sobre el float 0-1). En la fase B `core/stretch.py` los absorbe y la
   UFE solo cambia un import.
4. **Pixmap con `setScale` + `FastTransformation`**: el pixmap reducido se
   inserta con `item.setScale(pasos)` de modo que la escena siga en
   píxeles de placa (zoom 100 % = 1:1 exacto; overlays precisos).
   `Qt.FastTransformation` (vecino más próximo): a 200/400 % se ven los
   píxeles reales, no interpolados (pixel-peeping estilo AstroImageJ).
5. **Regla QImage**: siempre
   `QImage(buf, w, h, w, Format_Grayscale8).copy()` (patrón
   `sn_annotate_dialog.py:437`); nunca depender del buffer numpy vivo.
6. **Probe con valor DN**: el hover muestra píxel x/y, valor DN y RA/Dec
   (`core/coords.ra_deg_to_hms` / `dec_deg_to_dms`) cuando hay WCS; el DN
   es justo lo que el ajuste fino del histograma de la fase B necesita.
7. **Invariante white > black por clamp, no por excepción**
   (`white = max(white, black + eps)`) para que sliders y spinners no se
   peleen en la fase B. Los percentiles auto se calculan sobre la imagen
   reducida (<= 4096 px): visualmente idénticos y mucho más baratos que
   ordenar decenas de Mpx; `d_min/d_max` salen de la placa completa.

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
- [x] `gui/ufe_state.py`: controller de estado + load de FITS
      (mono/RGB).
- [x] `gui/widgets/ufe_image_view.py`: vista con zoom completo y
      overlays.
- [x] `gui/ufe_dialog.py`: layout, barra superior (cargar, zoom,
      invertir, export PNG de lo visible), área de pestañas vacía
      (placeholder por funcionalidad para no romper la rejilla),
      histograma en fase B.
- [x] Menú Herramientas: «FITS editor…» (lazy, patrón
      `_skycal_build`; al final del menú, tras «Campaigns…»).
- [x] ADR-044 (bilingüe, estilo ADR-042).
- [x] Tests unitarios: `UfeImageState` (carga mono/RGB, límites auto,
      estirar, invertir) con Qt offscreen + fixtures FITS de tests
      existentes; más humo de vista y diálogo (34 tests, suite 1528).
- [x] i18n: todas las cadenas por `self.tr()` + `.ts` actualizado +
      `.qm` recompilado (1100 cadenas, 0 unfinished).

### B: Motor de estiramiento + histograma visual

- [x] `core/stretch.py`; migración de los consumidores
      (`evolution_view`, `motion_view`, `__main__.py`,
      `sn_annotate_dialog`; `seqchart_dialog` no lo usaba);
      `blink_view` re-exporta para compatibilidad (tests legacy intactos).
- [x] `gui/widgets/histogram_widget.py`: histograma QPainter 256 bins
      (escala log), tiradores arrastrables (estilo AstroImageJ, con salto
      del tirador más cercano al clic), gamma, DN con paso fino
      (rango/decimales adaptativos), Auto, Invertir.
- [x] Export PNG de lo visible como funcionalidad de serie (barra
      superior, desde la fase A).
- [x] Tests de `core/stretch.py` (percentiles, gamma, invertir,
      downscale, histograma, re-exports) y del widget (tiradores, spins,
      Auto, Invertir, estados vacío/lleno).

### C: Comunes pulidas

- [x] Teclado completo (F fit, 1 a 1:1, +/- en pasos de rueda, flechas
      pan de un cuarto de ventana, Ctrl+O cargar, Ctrl+E exportar; el
      QPA offscreen no entrega activación de ventana, así que los tests
      disparan `activated.emit()` sobre los atajos registrados: mismo
      punto ciego que los Ctrl+1..4 de main_window), persistencia del
      estiramiento entre cargas (`state.keep_stretch` + checkbox),
      accesibilidad (accessibleName en vista, canvas y spins; tooltips
      con atajos) y pulido (etiqueta de zoom %, título con el fichero,
      doble clic = Fit).
- [x] Docs de usuario: `docs/UFE.es.md` y `docs/UFE.md`.

### D: Pestaña Anotar

- [x] `gui/ufe_annotate_tab.py` sobre
      `core/fits_annotate.write_annotated_fits`: multiplicación de
      imágenes (lista de visitas; el marcador se mapea por el WCS de cada
      placa), marcador por clic (clics y overlays solo mientras la
      pestaña es la visible, regla `set_active`) y ajuste fino (nudge
      dx/dy, tamaño, color), etiqueta y notas, guardar copia (original
      intacto; test que compara bytes).
- [x] El `SnAnnotateDialog` legacy sigue vivo y no se toca (sus tests
      siguen verdes).

### D.5: puntualización del observador (previo a la fase E)

- [x] Las placas anotadas presentan sus anotaciones al cargar:
      `core/fits_annotate.read_annotations` (las tarjetas ANNOTATE
      repetidas colapsan en el dict de cabecera y la etiqueta vive en el
      comentario de la tarjeta: el parser recorre las tarjetas crudas) +
      capa de solo lectura en la vista (círculos en píxeles de placa como
      AIJ, rótulos a tamaño de pantalla constante; la capa sobrevive a
      `clear_overlays`). Verificado visualmente con el fixture AIJ real
      (NGC 7331 y su séquito).
- [x] Flecha de norte y barra de escala como overlays COMUNES: HUD en
      coordenadas de viewport (`drawForeground`), con relé en la
      exportación PNG (`export_png` reestampa el HUD entre la escena y la
      marca de agua), botones «N»/«Escala» activos solo cuando hay WCS.
      En Anotar NO se duplican: la funcionalidad es común.
- [x] Resolución astrométrica común: botón «Resolver astrometría…» en la
      barra superior, `UfeSolveWorker` (QThread, red fuera del hilo GUI),
      `state.set_wcs_cards` fusiona la solución en memoria (señal
      `wcs_changed` nueva); la sonda, el HUD y Anotar la recogen al
      instante. Sin clave o sin solución: mensaje claro, nada se rompe.

### E: Pestaña Blink

- [x] Sobre `core/blink.prepare_pair` + `BlinkWorker`: resolver
      SN/manual, blink vivo (timer), marcador con nudge, balance, export
      GIF/MP4/PNG lado a lado del par. Notas de la migración: la pestaña
      posee el frame de la vista por `set_frame_override` (nuevo gancho
      de `UfeImageView`); la placa es la del estado (la carga es común);
      el estiramiento del obs son los DN absolutos compartidos (la tira
      de histograma manda también sobre el blink); placas espejadas se
      des-espejan para la vista y el marcador va por cielo
      (`state.wcs.sky_to_pixel` sobre ra/dec resueltos); la registración
      en proyecto del export queda en el legacy (el UFE es agnóstico de
      proyecto).
- [x] El diálogo legacy de blink sigue vivo (suite verde sin tocarlo).

### F: Pestaña Comparación

- [x] Sobre `core/compstars` + lenguaje visual de `FinderChart` como
      overlays de la vista compartida: generar campo (la placa cargada
      ES el fondo; sin WCS se pide resolver con el botón común), picker
      de estrellas por clic (Comp/Check, radio de pantalla constante,
      VSX rechazadas con motivo), propuesta automática por magnitud del
      objetivo, tabla de secuencia (nombre/tipo/quitar/limpiar), CSV
      (`export_sequence_csv`) y PNG de la carta (el export común de la
      escena visible, overlays + HUD dentro). Nota: el fondo DSS2 del
      flujo legacy queda en el legacy; en el UFE la placa propia es el
      fondo por diseño (el editor es FITS-céntrico y la astrometría se
      resuelve in situ desde D.5).
- [x] `SeqChartDialog` legacy sigue vivo (suite verde sin tocarlo).

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
