# ADR-044: Editor FITS unificado (UFE): una ventana, una pestaña por funcionalidad, escena en píxeles de placa

**Estado / Status**: Accepted · **Fecha / Date**: 2026-09-22 · **rev. 2026-09-23** (fases A-F + G/H implementadas. En D la pestaña Anotar fijó que las pestañas reciben `(state, lang, view)` y la activación por `set_active`; D.5: lectura y pintado de tarjetas ANNOTATE, flecha de norte y barra de escala como HUD común también en el PNG, resolución astrométrica común y en memoria; en E la pestaña Blink añadió el gancho `set_frame_override`; en F la pestaña Comparar usa la placa cargada como fondo del campo; G/H: la pestaña Medir con la fotometría calibrada y sus controles de calidad sobre `core/photometry.py`. **Conexión (2026-09-23)**: por defecto los flujos abren el UFE — ajuste `ufe_default` en Ajustes → Desarrollo, efecto inmediato — con prefill por pestaña, registro en el proyecto vía `set_save_hook` (incluidos contexto de secuencia y protocolo de campaña) y descarga del campo DSS2/PS1 dentro del UFE (esto supera la nota de la fase F: el fondo DSS2 ya no es exclusivo del legacy); la pestaña Medir puede guardar el punto calibrado en el proyecto (`source="measure"`) y la lista de visitas de Seguimiento abre el editor por visita («Medir en el Editor…» / "Measure in the editor…"), con resumen de campaña que se recalcula en cada guardado (retira el quick-look «Análisis rápido», ver ADR-019). Los tres diálogos legacy siguen vivos, intactos y alcanzables durante el periodo de revisión. **rev. 2026-09-24**: las secciones Comparar y Medir dejan de ser dos pestañas y viven juntas en la pestaña «Photometry» / «Fotometría». **rev. 2026-09-25**: la barra superior gana glifos SVG conmutables (ajuste `ufe_bar_icons`, por defecto solo iconos: carga, export, los conmutadores de HUD y los presets de zoom; «Solve astrometry…» y «Move marker…» conservan siempre su texto), «Move marker…» pasa a la barra como acción global desde cualquier pestaña, «Remove all» y «Export CSV…» se mudan al diálogo de Secuencia que enmarca la tabla, y la fila de objetivo y magnitud cabe en una línea; los controles de marca del objeto ganan nombres que dicen qué muestran y tooltips honestos, el anillo dibuja con el helper compartido `ring_marker_items` (gemelo de `cross_marker_items`) y el ámbar de esta familia de marcadores pasa a tener una única fuente, `palette.ACCENT`) · **rev. 2026-09-26**: el ajuste manual sale de la sección y vive en su propia pequeña ventana no modal, `UfeManualDialog` (cuerpo en `ui/ufe_manual_dialog.ui`), que abre y cierra el botón conmutable «Manual tweak…», a la derecha de DSS2: abierta el clic elige estrellas y cerrada (el estado normal) la placa mide; la pestaña de Comparar aliasa los widgets de la ventana y su estado sobrevive a cierre y reapertura, y el splitter de Fotometría conserva su reparto fijo; el estado de la ventana lo reporta la señal `openStateChanged` de la propia ventana, porque `visibilityChanged` no está expuesta en esta build de PySide6.

**Enmendado / Amended**: 2026-10-01 (Interfaz 1.0, ADR-055: el UFE deja de ser un `QDialog` flotante y pasa a ser una vista embebida del shell; su interior y su API de hooks no cambian, y al salir de la vista se llama a `shutdown()`, lo que antes hacía `closeEvent`).

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
pestaña Medir muestra el botón **Guardar…** y la medida
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
la pestaña. **fix 2026-09-24**: dentro de la pestaña hay dos conceptos
distintos, los clics (siguen a la sección armada, `self._active`) y los
overlays (siguen al escenario de la pestaña, `self._on_stage`): al abrir
desde una visita el enlace profundo arma Medir con la mitad Secuencia
visible pero desarmada, y las puertas de dibujo que leían `_active`
dejaban «Generar campo» y «Proponer secuencia» pintando nada; ahora
`_on_field_ready`, `_redraw_overlays`, `_redraw_entries` y
`_draw_measurement` se rigen por `_on_stage`. **fix 2 (mismo día)**:
`_on_stage` solo se armaba al armar la sección, así que abriendo desde
una visita (el deep link aterriza en Medir sin que Secuencia se haya
armado jamás) el campo seguía sin pintar; ahora
`set_active(False, keep_overlays=True)` establece `_on_stage` (su
significado literal: desarmada pero en escena), y el deep link
«measure» sin secuencia aterriza en la sección Secuencia (la regla de
la primera apertura del constructor, extendida a `show_tab`): sin
secuencia no hay con qué medir y el primer acto del observador es marcar
estrellas. **ADR-005 restaurado (2026-09-25)**: el diálogo, las cuatro
pestañas y los dos diálogos auxiliares definen su estructura en
`gui/ui/ufe_*.ui` (vista e histograma entran por placeholders; el
comportamiento no cambia). **ADR-046**: la barra
superior gana el conmutador «Cajas» (las cajas de metadatos de las
esquinas, en pantalla y en el PNG; con ellas la rosa baja al centro
inferior y gana la pata E, y la barra de escala se mueve a la derecha),
el marcador del objeto admite el estilo `cross` (cruz a todo el campo
con caja; helper compartido `cross_marker_items`, lo usan las pestañas
Anotar, Secuencia y Blink) y el contenido lo ensambla
`core/chart_annotate` vía `view.set_boxes_provider`.

**Barra superior y compactado de Fotometría (2026-09-25)**: la barra
superior cargaba siete textos y en pantallas pequeñas se desbordaba y
ocultaba las últimas acciones, y los primeros gestos del flujo diario
vivían repartidos en tres lugares de la pestaña de Fotometría. La barra
gana un juego de glifos SVG (16×16, trazo azul acento `#6ab0ff`, una
variante `_off` por conmutador en azul atenuado `#456c9d` para que el
estado apagado se lea más quieto; los presets de zoom llevan el aro delgado
(1.6) y el dígito más grande y más grueso (1.9), claro y separado del borde;
los ficheros viven en `nightscribe/assets/` y los resuelve `theme.asset`): carga, exportar, los conmutadores de HUD
(norte, escala, anotación, cajas) y los presets de zoom pasan a icono
puro, con los tooltips y los atajos intactos; «Solve astrometry…» y
«Move marker…» conservan siempre su texto, porque esas palabras son
precisamente su identidad. El ajuste `ufe_bar_icons` (Ajustes →
Desarrollo, activo por defecto) conmuta la barra en el `showEvent`,
reaplicando textos e iconos: sin reconstruir nada, con efecto
inmediato; si un glifo falta, el botón vuelve a su texto en silencio.
«Move marker…» sale del panel Secuencia y pasa a la barra como acción
global: desde cualquier pestaña arma la colocación de la marca de
objetivo, conmuta a la sección Secuencia, y si la placa o el campo
faltan, explica qué falta en vez de armar. En el panel Secuencia,
«Remove all» y «Export CSV…» dejan de ser botones de la pestaña y
viven en el diálogo que enmarca la tabla; el panel conserva los alias
`btn_clear` / `btn_csv` (los pinan los tests de integración) y
«Sequence (N)…» se sienta junto a «Propose sequence» con el recuento
vivo de las estrellas de la tabla. La fila de objetivo y magnitud cabe
en una línea: el campo de nombre es estrecho (130 px) y la etiqueta es
solo «Mag». En el panel Medir, «Suggest» pasa a su propia línea,
justo debajo de las aperturas (así la fila de radios no desborda con
fuentes anchas) y las tres cajas de numeración se estrechan (70 px).

**Controles de marca del objeto: nombres y tooltips honestos (2026-09-25)**.
Los cuatro controles de marca (los casilleros de las pestañas Blink,
Anotar y Secuencia y el botón «Move marker…» de la barra) decían la
misma genérica palabra sin decir de qué cosa ni con qué efecto, y el
tooltip de «Move marker…» prometía re-proponer la secuencia, algo que
nunca hacía. Ahora cada casilla nombra lo que muestra: en Blink,
«Show the supernova marker» (marca la placa y también el GIF/MP4/PNG
exportado; desmarcarla es lo único que recorta del export); en Anotar,
«Show the annotation marker» (solo de pantalla: la anotación se guarda
en la placa pase lo que pase); en Secuencia, «Show the target marker»
(solo visual: la propuesta y la matemática de la secuencia jamás lo
leen). El tooltip del botón deja la promesa muerta y dice solo lo que
hace: mover la marca del objetivo a una nueva posición de la placa,
recordando que es una ayuda visual que la matemática jamás lee.

El dibujo queda unificado también: las ramas de anillo de las tres
pestañas, que repetían el mismo anillo en tres bloques propios, dibujan
ahora con el helper compartido `ring_marker_items` en
`widgets/ufe_image_view.py` (gemelo de `cross_marker_items`, el mismo
contrato de ítems: 1 elipse + 4 ticks, pinceles cosméticos, que las
 pruebas pinan por tipo y color), y el ámbar de esta familia de
marcadores tiene una única fuente, `palette.ACCENT` (#ffb347): los
colores locales duplicados se retiran y el color de apertura de Medir
se une a la misma familia. Cero cambio visual: las pruebas de
geometría siguen pasando sin tocar.

**Sección Comparisons: un clic y marca de objeto global (2026-09-25,
segunda revisión del día)**. La sección Secuencia se presentaba como un
marcador manual de estrellas, cuando el flujo normal es automático:
generar el campo y proponer la secuencia. Ahora el camino principal es
un solo botón, «Build the sequence…» / «Construir la secuencia…»: lanza
la consulta de catálogo (con el diálogo de progreso modal que ya
cubre las esperas de red, para que nunca parezca un cuelgue) y la
propuesta se ejecuta sola en cuanto el campo aterriza; con el campo ya
cargado, el mismo botón solo re-propone. «Generate field» y «Propose
sequence» quedan como acciones secundarias por separado. Los controles
de marcado manual (la pista de clics, los radios Comparison/Check y el
casillero de etiquetas de catálogo) se pliegan bajo una
`CollapsibleSection` («Manual tweak» / «Ajuste manual», plegada por
defecto; su cuerpo vive en `ui/ufe_compare_manual.ui` para que sus
textos sigan siendo traducibles). La sección se renombra:
«Comparisons» / «Comparaciones» en el conmutador de la pestaña
Fotometría (los modos internos `sequence`/`measure` y los deep links no
cambian). Y la marca ámbar de objetivo de la sección desaparece entera
(casillero, colocación con clic y el «Move marker…» de la barra): el
objeto adjunto lo marca ahora la marca global roja tenue de la barra
superior (cruz a todo el campo con caja, alfa 50 %, capa propia de la
vista que sobrevive a los cambios de pestaña y sale en el PNG exportado
solo cuando está visible; necesita WCS, y el botón se deshabilita sin
objeto con coordenadas).

**Fotometría sin modos (2026-09-25, tercera revisión del día)**. El
conmutador «Comparisons»/«Measure» desaparece: Fotometría es una sola
columna con las dos secciones siempre visibles (secuencia arriba, medida
abajo), y lo que hace un clic en la placa lo decide el plegado de
«Manual tweak» de la sección de secuencia: plegado (el estado normal)
el clic mide; desplegado el clic marca estrellas. Todas las acciones
manuales viven dentro del plegable: la pista de clics, los radios
Comparison/Check, las etiquetas de catálogo y ahora también «Generate
field», «Propose sequence» y «Sequence (N)…»; la cara visible de la
sección es solo el objetivo, «Build the sequence…» y el estado. El
botón «Go to the comparisons» de Medir sobra y se retira (el mensaje
sin secuencia apunta a «Build the sequence…»). Los deep links
«compare»/«measure» siguen aceptados y simplemente seleccionan la
pestaña. Corrección de paso: el diálogo de progreso del campo nunca
llegaba a mostrarse (un QProgressDialog indeterminado solo se
auto-muestra con setValue, que nunca llega): `_busy_wait` lo muestra
explícitamente y el diálogo cubre la cadena entera campo → propuesta
(se cierra tras proponer, no al llegar el campo). Tres detalles más de
la misma revisión: el diálogo se centra sobre la ventana del editor y
su cierre es incondicional (try/finally: un modal que sobrevive a una
excepción se lee como un cuelgue); el splitter de Fotometría reparte de
nuevo al desplegar «Ajuste manual» (la mitad superior crece para que
quepa todo); y el panel de Medir, cuando no hay calibración, desglosa
las causas junto al titular («Why: 5 saturated/clipped…») con la guía
en lenguaje llano, en vez de ahogarlas al final de las notas.

**Ajuste manual en su ventana (2026-09-26, cuarta revisión)**. Los
controles de marcado manual salen de la sección y viven en la pequeña
ventana no modal `UfeManualDialog`; su cuerpo es
`ui/ufe_manual_dialog.ui` (renombre de `ui/ufe_compare_manual.ui`) para
que los textos sigan siendo traducibles. La abre y cierra un botón
conmutable, «Manual tweak…», a la derecha del botón DSS2, y es ahora
la única cara del ajuste manual en la sección. Lo que hace un clic en
la placa sigue la visibilidad de la ventana: abierta, el clic elige
comparaciones y estrellas de control; cerrada (el estado normal), la
placa mide como siempre. La pestaña de Comparar aliasa los widgets de
la ventana (los radios, las etiquetas, «Generate field»,
«Propose sequence», «Sequence (N)…» y la pista de clics) y el estado
vive en ellos, así que cerrar y reabrir la ventana conserva todo lo ya
elegido; y cerrar por la X desmarca el botón, con el estado de la
ventana reportado por la señal `openStateChanged` de la propia
ventana, porque `visibilityChanged` no está expuesto en esta build de
PySide6. Y el splitter de Fotometría ya no reparte para el ajuste
manual: la ventana flota y las dos mitades conservan su tamaño.

**Consecuencias**: cargar y trabajar un FITS tiene un solo camino; las
mejoras del motor de estiramiento (fase B) llegan a la vez a todo lo que
lo use; añadir una funcionalidad al editor no modifica `ufe_dialog.py`
salvo un `add_feature_tab`. Los diálogos legacy se mantienen congelados
mientras el UFE madura; la fase B es la única que toca código legacy, y
solo para re-exportar (`viz/blink_view.py` mantiene compatibilidad).

**Revisión (2026-10-07, Interfaz 1.9: se cierra el periodo de revisión).** El
UFE dejó de ser una alternativa y pasó a ser la puerta: los tres diálogos
clásicos que sobrevivían «por si acaso» se retiran, y con ellos el interruptor
que elegía entre ellos y el editor.

- Fuera el **diálogo clásico de blink** (`_open_blink_dialog`, sus ayudantes
  `_dialog_blink_*` y `_blink_*`, su estado, sus timers y `blink_tab.ui`).
  Estaba ya sin puerta desde el 2026-10-06; ahora tampoco ocupa código.
- Fuera **`SnAnnotateDialog`** (`gui/sn_annotate_dialog.py`): el anotado de la
  SN vive en la pestaña Anotar del editor, y el gancho de guardado del UFE ya
  registra la copia en el proyecto.
- Fuera la **carta de comparación clásica** (`gui/seqchart_dialog.py`, la rama
  clásica de `_fu_sequence_dialog`, `_fu_sequence_done` / `_fu_sequence_save`)
  y su **`SequenceWorker`**: el UFE usa `UfeFieldWorker` / `UfeProposeWorker`, y
  el gancho del editor ya guarda la secuencia, el PNG/CSV y el
  `protocol.comp_stars` de la campaña. No se pierde ninguna capacidad.
- Fuera el interruptor **`ufe_default`** de Ajustes → Desarrollo (que además
  dejaba la medición y la astrometría solo con un mensaje cuando se apagaba).
  En esa pestaña queda la barra de iconos del editor, que sí es una preferencia
  real.
- **No se toca** lo que el editor reutiliza: `BlinkWorker`,
  `BlinkExportWorker`, `viz/blink_view.py` (los usan el UFE y el CLI),
  `core/compstars.py` y el gancho `_ufe_save_hook`.

**Punto de entrada**: `gui/main_window.py` (fuera los caminos clásicos y
`_use_ufe`), `gui/workers.py` (fuera `SequenceWorker`), `gui/ui/settings_dialog.ui`
(fuera la fila del interruptor).

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
project, the Measure tab shows a **Save…** button and the
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
inner panel switches the mode and activates the tab. **fix 2026-09-24**:
inside the tab there are two distinct concepts, the clicks (they follow
the armed section, `self._active`) and the overlays (they follow the
tab's stage, `self._on_stage`): opened from a visit, the deep link arms
Measure with the Sequence half visible but disarmed, and the draw gates
reading `_active` left "Generate field" and "Propose sequence" painting
nothing; `_on_field_ready`, `_redraw_overlays`, `_redraw_entries` and
`_draw_measurement` now follow `_on_stage`. **fix 2 (same day)**:
`_on_stage` was only set when a section got armed, so opening from a
visit (the deep link lands on Measure without Sequence ever being
armed) still painted nothing; now `set_active(False,
keep_overlays=True)` sets `_on_stage` (its literal meaning: disarmed
but on stage), and the "measure" deep link with an empty sequence lands
on the Sequence section (the constructor's first-open rule, extended to
`show_tab`): without a sequence there is nothing to measure with, and
the observer's first act is marking stars. **ADR-005 restored
(2026-09-25)**: the dialog, the four tabs and the two auxiliary dialogs
define their structure in `gui/ui/ufe_*.ui` (the view and the histogram
enter through placeholders; behaviour unchanged). **ADR-046**: the top bar
gains the "Boxes" toggle (the metadata corner boxes, on screen and in
the exported PNG; with them on, the compass moves to the bottom centre
and gains the east leg, and the scale bar moves right), the object
marker admits the `cross` style (full-frame crosshair with a box; shared
`cross_marker_items` helper, used by the Annotate, Sequence and Blink
tabs) and the content is assembled by `core/chart_annotate` through
`view.set_boxes_provider`.

**Top bar and Photometry compaction (2026-09-25)**: the top bar
carried seven texts and on small screens it overflowed and hid the
last actions, and the first gestures of the daily flow lived spread
over three places inside the Photometry tab. The bar gains a set of
SVG glyphs (16×16, accent blue `#6ab0ff` stroke, one `_off` variant per
toggle in a dimmed blue `#456c9d` so the off state reads quieter; the zoom
presets carry a thin rim (1.6) and a larger, bolder digit (1.9), clearly
separated from the border; the files live in `nightscribe/assets/` and
`theme.asset` resolves them):
load, export, the HUD toggles (north, scale, annotations, boxes) and
the zoom presets become icon-only, with the tooltips and the shortcuts
intact; "Solve astrometry…" and "Move marker…" always keep their
text, because those words are precisely their identity. The
`ufe_bar_icons` setting (Settings → Development, on by default)
swaps the bar in `showEvent` by re-applying texts and icons: no
rebuild, immediate effect; if a glyph is missing, the button silently
falls back to its text. "Move marker…" leaves the Sequence panel and
moves to the bar as a global action: from any tab it arms the target
marker placement, switches to the Sequence section, and if the plate
or the field is missing it explains what is missing instead of
arming. In the Sequence panel, "Remove all" and "Export CSV…" stop
being buttons of the tab and live in the dialog that frames the
table; the panel keeps the `btn_clear` / `btn_csv` aliases (the
integration tests pin them) and "Sequence (N)…" sits next to "Propose
sequence" with the live count of the table's stars. The target and
magnitude row fits one line: the name field is narrow (130 px) and
the label is just "Mag". On the Measure panel, "Suggest" moves to
its own line right under the apertures (so the radii row never
overflows on wide-font platforms) and the three spin boxes go narrow
(70 px).

**Object-mark controls: honest names and tooltips (2026-09-25)**.
The four object-mark controls (the Blink, Annotate and Sequence
checkboxes and the "Move marker…" bar button) all said the same vague
word without saying of what, or with what effect, and the "Move
marker…" tooltip promised a re-propose it never did. Each checkbox now
names what it shows: on Blink, "Show the supernova marker" (it marks
the plate and also the exported GIF/MP4/PNG; unchecking it is the only
change the export sees); on Annotate, "Show the annotation marker"
(screen only: the annotation itself is always saved to the plate); on
Sequence, "Show the target marker" (display only: the proposal and the
sequence math never read it). The button's tooltip drops the dead
promise and says only what it does: move the target mark to a new
position on the plate, keeping in mind it is a visual aid the math
never reads.

The drawing unifies too: the ring branches of the three tabs, which
repeated the same ring in three bespoke blocks, now draw through the
shared `ring_marker_items` helper in `widgets/ufe_image_view.py` (twin
of `cross_marker_items`, same item contract: 1 ellipse + 4 ticks,
cosmetic pens, which the tests pin by type and colour), and the amber
of this marker family has a single source, `palette.ACCENT` (#ffb347):
the duplicated local colours are retired and the Measure tab's aperture
colour joins the same family. Zero visual change: the geometry pins
still pass untouched.

**Comparisons section: one click and a global object mark (2026-09-25,
second revision of the day)**. The Sequence section presented itself as
a manual star picker, when the normal flow is automatic: generate the
field and propose the sequence. The main path is now a single button,
"Build the sequence…": it runs the catalog query (under the modal
progress dialog that already covers the network waits, so it never
reads as a hang) and the proposal runs by itself the moment the field
lands; with a field already loaded, the same button only re-proposes.
"Generate field" and "Propose sequence" stay as separate secondary
actions. The manual picking controls (the click hint, the
Comparison/Check radios and the catalog-labels checkbox) fold under a
`CollapsibleSection` ("Manual tweak", collapsed by default; its body
lives in `ui/ufe_compare_manual.ui` so its texts stay translatable).
The section is renamed: "Comparisons" on the Photometry tab's mode
toggle (the internal `sequence`/`measure` modes and the deep links are
unchanged). And the section's own amber target mark is gone entirely
(checkbox, click placement and the bar's "Move marker…"): the attached
object is now marked by the top bar's subtle global red mark (a
full-frame cross with a box, 50 % alpha, its own view layer that
survives tab switches and lands in the exported PNG only while visible;
it needs a WCS, and the button disables with no object coordinates).

**Photometry without modes (2026-09-25, third revision of the day)**.
The "Comparisons"/"Measure" toggle is gone: Photometry is a single
column with both sections always visible (sequence on top, measuring
below), and what a plate click does follows the "Manual tweak" fold of
the sequence section: folded (the normal state) the click measures;
expanded it picks stars. Every hand-driven action lives inside the
fold: the click hint, the Comparison/Check radios, the catalog labels
and now also "Generate field", "Propose sequence" and "Sequence (N)…";
the section's visible face is just the target, "Build the sequence…"
and the status line. The Measure section's "Go to the comparisons"
button is removed (the no-sequence message points at "Build the
sequence…"). The "compare"/"measure" deep links stay accepted and
simply select the tab. Fix along the way: the field's progress dialog
never actually appeared (an indeterminate QProgressDialog only
auto-shows on setValue, which never comes): `_busy_wait` shows it
explicitly and the dialog covers the whole field → proposal chain (it
closes after proposing, not when the field lands). Three more details
of the same revision: the dialog is centred over the editor window and
its reaping is unconditional (try/finally: a modal surviving an
exception reads as a hang); the Photometry splitter re-deals when
"Manual tweak" unfolds (the top half grows so everything fits); and the
Measure panel, with no calibration, itemises the causes right under the
headline ("Why: 5 saturated/clipped…") with plain-language guidance
instead of drowning them at the bottom of the notes.

**Manual tweak in its own window (2026-09-26, fourth revision)**. The
manual picking controls leave the section and live in a small
non-modal window of their own, `UfeManualDialog`; its body is
`ui/ufe_manual_dialog.ui` (renamed from `ui/ufe_compare_manual.ui`) so
the texts stay translatable. A checkable button, "Manual tweak…",
right of the DSS2 button, opens and closes it, and it is now the only
face of the manual tweak in the section. What a plate click does
follows the window's visibility: open, the click picks comparisons and
check stars; closed (the normal state), the plate measures as before.
The Compare tab aliases the window's widgets (the radios, the labels,
"Generate field", "Propose sequence", "Sequence (N)…" and the click
hint) and the state lives on them, so closing and reopening the window
keeps everything already chosen; and closing it by the X unchecks the
button, the window's state being reported by the window's own
`openStateChanged` signal, because `visibilityChanged` is not exposed
in this PySide6 build. And the Photometry splitter no longer re-deals
for the manual tweak: the window floats and the two halves keep their
size.

**Consequences**: loading and working a FITS has a single path; stretch
engine improvements (phase B) reach every consumer at once; adding a
feature to the editor does not modify `ufe_dialog.py` beyond an
`add_feature_tab`. The legacy dialogs stay frozen while the UFE matures;
phase B is the only one touching legacy code, and only to re-export
(`viz/blink_view.py` keeps compatibility).

**Revisión (2026-10-06): la calibración se enlaza desde el motor que la usa.**
El editor mantiene la pestaña **Calibración** como casa única de la receta, la
biblioteca de masters y la política del pseudo-flat, y **cada motor se apunta**
desde su propia pestaña: en Astrometría, «Aplicar la calibración al apilado»
(persistida), una **pista de una línea** con lo que va a pasar con los píxeles y
un botón **«Calibración…»** que es el enlace profundo a la pestaña, con el mismo
patrón que el enlace a la receta de fotometría. El diálogo expone
`calibration_summary()` (que reenvía al resumen de una línea de la pestaña
Calibración) para que la pista no duplique la resolución de la receta. Ajustes
deja de duplicar la política del pseudo-flat: conserva solo la biblioteca.

**Revision (2026-10-06): calibration is linked from the engine that uses it.**
The editor keeps the **Calibration** tab as the single home of the recipe, the
master library and the pseudo-flat policy, and **every engine opts in** from its
own tab: in Astrometry, "Apply the calibration to the stack" (persisted), a
**one-line hint** with what will happen to the pixels, and a **"Calibration…"**
button that is the deep link to the tab, the same pattern as the photometry
recipe's. The dialog exposes `calibration_summary()` (which forwards the
Calibration tab's one-liner) so the hint does not resolve the recipe twice.
Settings stops duplicating the pseudo-flat policy: it keeps only the library.

**Revisión (2026-10-06): las pestañas que eran recados son ventanas.** La
columna derecha tenía cinco pestañas: Blink, Fotometría, Anotar, Calibración
y Astrometría. Tres de ellas (Blink, Calibración, Anotar) y la serie
fotométrica **no son lo que un observador hace todo el rato**: son recados, y
cada una pagaba una columna permanente de 380 px y un título. Se pidió lo
contrario: un botón en la barra y el panel en una ventana que se abre encima
de la placa. Así queda:

- **La columna conserva los dos paneles donde se vive**: Fotometría
  (Comparaciones + Medir) y Astrometría. La pestaña sigue siendo el mismo
  `QTabWidget` y `add_feature_tab` sigue siendo toda la API de extensión.
- **Los cuatro recados son ventanas no modales** (`gui/ufe_tool_dialog.py`),
  alojando el panel que ya existía: la clase y su `.ui` no cambian (ADR-005
  intacto) y la ventana no tiene estructura propia que diseñar (un área de
  contenido), así que no lleva `.ui`. El tamaño se mide en el primer
  `showEvent`, sobre las filas ya colocadas, como documenta `UfeManualDialog`
  (las pistas de tamaño mienten sobre el alto de un formulario).
- **Una a la vez y el escenario**: la ventana abierta manda sobre la placa
  (`set_active(True)`: el frame del blink, la marca y los clics de anotar);
  al cerrarse el escenario vuelve al panel seleccionado, y abrir otra cierra
  la anterior (nunca hay duda de quién manda). **Solo lo toman las que lo
  necesitan**: Blink (su frame) y Anotar (los clics); Calibrar es un panel de
  receta y la serie un panel de ejecución, y quitarle el escenario a
  Fotometría mientras corre una serie apagaría los anillos de la secuencia
  justo cuando se quieren ver. Un panel sin escenario conserva sus
  superposiciones si le corresponden.
- **El escenario se resuelve en un solo sitio** (`_apply_stage`), y el
  cursor de pick lo sigue (los paneles y las herramientas declaran
  `pick_clicks`). Cambiar de panel en la columna **no** le roba la placa a
  una ventana abierta.
- **Los deep links siguen funcionando**: `show_tab("blink" | "calibration" |
  "annotate" | "series")` (o el propio widget) abre la ventana; el host no
  cambió una línea. `show_tab` rearma el escenario aunque el panel pedido ya
  estuviera seleccionado (un deep link que no emite señal dejaría el panel
  sin armar).
- **Al salir del banco, las ventanas se esconden** (`leave_view()`, que llama
  el shell al cambiar de vista): son hijas de la página y colgarían sobre el
  proyecto. Escondidas, nunca destruidas: al volver están donde estaban.
- **Los cuatro botones van en una puerta (Herramientas ▾) y no en la barra**,
  por una razón medida: cuatro etiquetas cuestan 331 px, la barra pasa de 508
  a 1039 y el **distintivo del proyecto** (lo único que dice en qué proyecto
  trabajas) se comprime desde 1100 px hacia abajo. Dentro de la puerta cada
  botón conserva su icono y su etiqueta, que es lo que se pidió.
- **Image | Light curve** deja su fila propia (encima de la placa) y pasa al
  extremo derecho de la barra: es una vista del **centro**, así que pertenece
  a la barra. Los botones son los mismos widgets y el cableado no cambió.

**Revision (2026-10-06): the tabs that were errands are windows.** The right
column had five tabs: Blink, Photometry, Annotate, Calibration and Astrometry.
Three of them (Blink, Calibration, Annotate) and the photometric series **are
not what an observer does all the time**: they are errands, and each paid for a
permanent 380 px column and a title. What was asked for is the opposite: a
button in the bar and the panel in a window over the plate. This is how it
lands:

- **The column keeps the two panels where the work happens**: Photometry
  (Comparisons + Measure) and Astrometry. The tab widget is the same one and
  `add_feature_tab` is still the whole extension API.
- **The four errands are non-modal windows** (`gui/ufe_tool_dialog.py`)
  hosting the panel that already existed: the class and its `.ui` do not
  change (ADR-005 intact) and the window has no structure of its own to design
  (one content area), so it carries no `.ui`. The size is measured on the
  first `showEvent`, on the laid-out rows, as `UfeManualDialog` documents (the
  size hints lie about a form's height).
- **One at a time, and the stage**: the open window owns the plate
  (`set_active(True)`: the blink frame, the annotate marker and clicks);
  closing it hands the stage back to the selected panel, and opening another
  closes the previous one (there is never a question of who owns it). **Only
  the ones that need it take it**: Blink (its own frame) and Annotate (the
  clicks); Calibration is a recipe panel and the series is a run panel, and
  taking the stage from Photometry while a series runs would drop the
  sequence's rings exactly when they are wanted. A panel without the stage
  keeps its overlays when they belong to it.
- **The stage is resolved in one place** (`_apply_stage`), and the pick cursor
  follows it (panels and tools declare `pick_clicks`). Switching the panel in
  the column does **not** steal the plate from an open window.
- **The deep links keep working**: `show_tab("blink" | "calibration" |
  "annotate" | "series")` (or the widget itself) opens the window; the host
  did not change a line. `show_tab` re-arms the stage even when the requested
  panel was already selected (a deep link that emits no signal would leave the
  panel unarmed).
- **Leaving the workbench hides the windows** (`leave_view()`, which the shell
  calls on every view change): they are children of the page and would hang
  over the project. Hidden, never destroyed: coming back finds them where they
  were.
- **The four buttons live in a door (Tools ▾) and not in the bar**, for a
  measured reason: four labels cost 331 px, the bar goes from 508 to 1039 and
  the **project badge** (the one thing that says which project you are working
  on) is squeezed from 1100 px down. Inside the door each button keeps its icon
  and its label, which is what was asked for.
- **Image | Light curve** leaves its own row (above the plate) and moves to the
  right end of the bar: it is a view of the **centre**, so it belongs to the
  bar. The buttons are the same widgets and the wiring did not change.

**Revisión (2026-10-06, segunda del día): los recados, en su fila, y los
fotogramas de la visita a la vista.**

1. **Los cuatro recados vuelven a la barra como botones independientes**
   (pedido: la puerta no valía). Están en **su propia fila** bajo la barra, no
   dentro de ella, y el motivo está medido: con el tema aplicado, cuatro
   botones de icono cuestan 232 px y dentro de la barra dejaban al distintivo
   del proyecto sin sitio desde 1200 px hacia abajo (a 900 no cabía ni el
   nombre). En su fila, la barra mide 1060 px y el distintivo conserva el
   nombre desde ~1100. Los cuatro siguen el ajuste `ufe_bar_icons`: icono con
   su tooltip por defecto, icono y etiqueta si el observador los enciende.
   (La puerta de la revisión anterior queda retirada.)
2. **El botón héroe cabe siempre** (`gui/widgets/hero_fit.py`): un QPushButton
   ni parte la línea ni elide, así que la etiqueta se recorta a la anchura real
   en cada `resize` y el ancho del botón deja de depender de su texto. Medido:
   «Construir la secuencia (comparsas)…» pide 329 px y la columna puede bajar a
   280 (262 útiles): antes se salía, ahora se lee entera o elidida con puntos.
3. **El panel de Astrometría recupera lo que el refactor a grupos dejó
   escondido**: la tabla de «Measurement per observation», su título y la tira
   de previews por observación se quedaron invisibles para siempre (el
   `_show_result_area` antiguo los mostraba y el bucle sobre las secciones los
   perdió). Es la regresión que dejaba ese grupo vacío.
4. **Los fotogramas de la visita, en previews** (`gui/widgets/frame_previews.py`
   en el panel izquierdo): una lista vertical con una miniatura de 140 px por
   toma, su nombre, sus números en el tooltip (tamaño en disco, cielo medido,
   filtro, exposición, fecha) y las **marcas de problema** que hacen útil una
   lista de doscientas tomas: ilegible, sin registrar por el último run. Con un
   filtro «solo problemas», el clic abre la toma en el editor y el menú
   contextual la quita de la visita (desenlaza, el fichero no se toca) o la
   mueve a `descartados/` (nada se borra). La lectura es **muestreada**
   (`fits_io.read_sample`: una fila de cada N, ~1 MB por toma de 2048² en vez
   de 16 MB) y va en un worker.

**Revision (2026-10-06, second of the day): the errands in their own row, and
the visit's frames in sight.**

1. **The four errands are back in the bar as independent buttons** (asked for:
   the door did not do). They live in **their own row** under the bar, not
   inside it, and the reason is measured: with the theme applied, four icon
   buttons cost 232 px and inside the bar they left the project badge without
   room from 1200 px down (at 900 not even the name fitted). In their row the
   bar measures 1060 px and the badge keeps its name from ~1100. The four follow
   the `ufe_bar_icons` setting: icon with its tooltip by default, icon and label
   when the observer turns the labels on. (The door of the previous revision is
   withdrawn.)
2. **The hero button always fits** (`gui/widgets/hero_fit.py`): a QPushButton
   neither wraps nor elides, so its label is trimmed to the real width on every
   `resize` and the button's width stops depending on its text. Measured:
   "Build the sequence (comparisons)…" asks for 329 px and the column can go
   down to 280 (262 usable): it used to run over its own edges, now it reads
   whole or elided with dots.
3. **The Astrometry panel gets back what the refactor to groups left hidden**:
   the "Measurement per observation" table, its title and the per-observation
   strip of previews stayed invisible for good (the old `_show_result_area`
   showed them and the loop over the sections lost them). That is the regression
   that left that group empty.
4. **The visit's frames, as previews** (`gui/widgets/frame_previews.py` in the
   left panel): a vertical list with a 140 px thumbnail per frame, its name, its
   numbers in the tooltip (size on disk, measured sky, filter, exposure, date)
   and the **problem marks** that make a list of two hundred frames useful:
   unreadable, not registered by the last run. With an "only problems" filter,
   a click opens the frame in the editor and the context menu takes it out of
   the visit (unlink, the file is not touched) or moves it to `discarded/`
   (nothing is deleted). The read is **sampled** (`fits_io.read_sample`: one row
   out of every N, ~1 MB per 2048² frame instead of 16 MB) and runs in a worker.

**Revisión (2026-10-06, tercera del día): la miniatura ocupa la columna y la
leyenda va encima.** La lista de previews nació con miniaturas de 140 px y la
leyenda al lado (dos líneas de texto por fila). Se pidió lo contrario: la
imagen lo más grande posible y el texto encima.

- **La lista llena el alto**: el espaciador final del panel de la visita era
  `Expanding` y se llevaba 264 px de 640 (medido); pasa a `Fixed` y la lista
  pasa de 264 a 518 px.
- **La miniatura se ajusta al ancho de la lista** en cada `resize` (140 px
  antes, **252** en una columna de 300, y sigue al divisor). La proporción de
  la toma se respeta: una no cuadrada ajusta al ancho y se centra.
- **La leyenda se pinta SOBRE la imagen** con un delegado propio
  (`QStyledItemDelegate`): tipo de 11 px, **en rojo** (`theme.C_EVENT`) con un
  contorno oscuro y una banda semitransparente debajo, para que se lea sobre
  un cielo negro o sobre una nebulosa brillante. La fila es la imagen y nada
  más: los 24 px que gastaba la leyenda lateral son los que pagan la imagen
  más grande. El nombre completo sigue en el tooltip y en el texto del ítem.
- **El aviso de problema cambia de canal**: como la leyenda es roja para
  todas, una toma ilegible o sin registrar lleva **borde rojo** alrededor de
  la miniatura (y la palabra en la leyenda). El contador y el filtro «Solo
  problemas» no cambian.
- **La muestra se lee a 320 px** (`read_sample(max_px=320)`, ~2 MB por toma de
  2048² en vez de 1): una muestra más pequeña que la miniatura se vería
  blanda. El coste de una visita de 200 sigue siendo un segundo.
- **Lo que cuesta**: con miniaturas de ~250 px se ven dos tomas por pantalla,
  así que recorrer una visita larga es cosa del filtro y del navegador.

**Revision (2026-10-06, third of the day): the preview takes the column and the
caption rides on it.** The preview list was born with 140 px thumbnails and the
caption beside them (two lines of text per row). What was asked for is the
opposite: the image as big as possible and the text over it.

- **The list fills the height**: the visit panel's trailing spacer was
  `Expanding` and took 264 px of 640 (measured); it is `Fixed` now and the list
  goes from 264 to 518 px.
- **The preview fits the list's width** on every `resize` (140 px before, **252**
  in a 300 px column, and it follows the splitter). The frame's own proportions
  are kept: a non-square one fits the width and is centred.
- **The caption is painted ON the image** by a delegate of its own
  (`QStyledItemDelegate`): 11 px type, **in red** (`theme.C_EVENT`) with a dark
  outline and a semi-transparent band under it, so it reads over black sky and
  over a bright nebula alike. The row is the image and nothing else: the 24 px
  the side caption took are what pays for the bigger picture. The whole name
  stays in the tooltip and in the item's text.
- **The problem mark changes channel**: since the caption is red for every
  frame, one that cannot be read or was not registered wears a **red border**
  around the preview (and the word in the caption). The count and the "only
  problems" filter do not change.
- **The sample is read at 320 px** (`read_sample(max_px=320)`, ~2 MB per 2048²
  frame instead of 1): a sample smaller than the preview would be shown soft.
  A 200-frame visit is still a second.
- **What it costs**: with ~250 px previews, two frames fit on screen, so walking
  a long visit is the filter's and the navigator's job.

**Revisión (2026-10-06, cuarta del día): la leyenda en el color del objeto y
EXOTIC con la serie.**

1. **La leyenda de las previews deja el rojo y viste el color del tipo de
   objeto** (pedido: el rojo se lee como error). El color sale del mismo
   payload que ya usan el chip, el botón héroe y las espinas de los bloques
   (`project_accent()`), con el acento de la app como respaldo cuando el
   editor se abre sin proyecto; el diálogo lo reparte donde ya reparte los
   demás (`set_project_badge`). El **rojo queda para lo que es un problema**:
   el borde de la miniatura y la palabra de aviso, que el delegado pinta en
   rojo después del nombre (la leyenda se parte por el símbolo ⚠ y cada mitad
   va de su color). El contorno oscuro y la banda siguen ahí, así que
   cualquiera de los colores del tipo se lee sobre cielo o sobre nebulosa.
2. **El bloque EXOTIC se muda a la ventana de la serie fotométrica** (pedido:
   es su sitio). Un ajuste de tránsito ES la serie de una visita de tránsito,
   así que el bloque vive en la ventana de «Serie», debajo del bloque de
   serie, y el panel de la visita se queda con el navegador y las previews.
   El bloque tiene su propio `.ui` (`gui/ui/ufe_exotic_block.ui`, con la misma
   clase `UfeDialog` para que las traducciones no se muevan de contexto), la
   ventana de serie aloja un cuerpo con los dos bloques, y el comportamiento
   no cambia: sigue apareciendo solo en tránsitos con secuencia armada, con
   los mismos hooks y los mismos botones (que ahora cuelgan de `exotic.*`).

**Revision (2026-10-06, fourth of the day): the caption in the object's colour
and EXOTIC with the series.**

1. **The previews' caption leaves red and wears the object kind's colour**
   (asked for: red reads as an error). The colour comes from the same payload
   the chip, the hero button and the block spines already use
   (`project_accent()`), with the app's accent as the fallback when the editor
   is opened with no project; the dialog hands it out where it hands out the
   rest (`set_project_badge`). **Red stays for what is a problem**: the
   preview's border and the warning word, which the delegate paints in red
   after the name (the caption is split on the ⚠ and each half goes in its own
   colour). The dark outline and the band stay, so any of the kind colours
   reads over sky and over a nebula.
2. **The EXOTIC block moves to the photometric series window** (asked for: it
   belongs there). A transit fit IS the series of a transit visit, so the
   block lives in the "Series" window, under the series block, and the visit
   panel keeps the navigator and the previews. The block has its own `.ui`
   (`gui/ui/ufe_exotic_block.ui`, with the same `UfeDialog` class so the
   translations do not change context), the series window hosts a body with
   both blocks, and the behaviour does not change: it still appears only in
   transits with an armed sequence, with the same hooks and the same buttons
   (which now hang from `exotic.*`).

**Revisión (2026-10-06, quinta del día): la banda de los paneles cabe su
contenido.**

Se reportó que «los mensajes de la derecha se cortan». Medido: la columna de
los paneles medía **380 px (362 útiles)** y el contenido del panel de
Astrometría necesitaba **396**, así que aparecía una **barra horizontal** y las
etiquetas que sobresalían se cortaban (`lbl_recipe` pedía 276 y recibía 213).
Las dos filas que forzaban ese mínimo estaban en «Stacking settings»:

- la casilla de la calibración y su botón compartían línea (334 px): la casilla
  pasa a **«Aplicar la calibración»** (la explicación larga ya vivía en su
  tooltip) y la fila baja a 272;
- «Campo» y «Margen» compartían línea (368 px): el margen **baja a su propia
  fila** y los dos combos aceptan encogerse
  (`AdjustToMinimumContentsLengthWithIcon` + `minimumContentsLength`), con lo
  que un combo deja de imponer el ancho de su ítem más largo.

Con eso el mínimo del panel queda en **331** y cabe sin barra horizontal. Y la
columna **abre más ancha**: `_TABS_W` de 380 a **420** y `_TABS_MAX_W` de 520 a
**560** (el divisor sigue arrastrándose), para que los mensajes y el botón
héroe tengan aire; la placa se queda con el resto.

La línea de estado deja además de elidirse y **envuelve hasta tres líneas**
(con tope de altura): lo que había que evitar era el crecimiento sin freno (el
párrafo que medía 204 px), no que el mensaje se lea. El texto completo sigue en
el tooltip y en la línea única de la ventana.

Un test lo vigila: con un run en Astrometría y todo desplegado, a la anchura
por defecto no hay barra horizontal, ninguna etiqueta visible se corta (las que
envuelven tienen la altura que su texto pide) y el mínimo del panel cabe.

**Revision (2026-10-06, fifth of the day): the panel column fits its content.**

Reported: "the messages on the right get cut". Measured: the panels' column was
**380 px (362 usable)** and the Astrometry panel's content needed **396**, so a
**horizontal scrollbar** appeared and the labels that stuck out were cut
(`lbl_recipe` asked for 276 and was given 213). The two rows that forced that
minimum were in "Stacking settings":

- the calibration checkbox and its button shared a line (334 px): the checkbox
  becomes **"Apply the calibration"** (the long explanation already lived in
  its tooltip) and the row drops to 272;
- "Field" and "Margin" shared a line (368 px): the margin **moves to its own
  row** and both combos accept shrinking
  (`AdjustToMinimumContentsLengthWithIcon` + `minimumContentsLength`), so a
  combo stops imposing the width of its longest entry.

With that the panel's minimum is **331** and it fits with no horizontal
scrollbar. And the column **opens wider**: `_TABS_W` from 380 to **420** and
`_TABS_MAX_W` from 520 to **560** (the splitter still drags), so the messages
and the hero button have air; the plate keeps the rest.

The Astrometry status line also stops eliding and **wraps up to three lines**
(capped height): what had to be avoided was unbounded growth (the paragraph
that measured 204 px), not the message being readable. The whole text stays in
the tooltip and in the window's single line.

A test watches it: with a run in Astrometry and everything expanded, at the
default width there is no horizontal scrollbar, no visible label is cut (the
wrapping ones have the height their text asks for) and the panel's minimum fits.

**Revisión (2026-10-06, sexta del día): fuera la entrada ad-hoc de Blink.**
El menú Herramientas llevaba «Blink (ad-hoc)…», que con el editor unificado en
marcha (el defecto) abría la ventana de Blink del banco de imágenes, la misma
que ya tiene su botón en la fila de herramientas, y con el editor apagado
abría el diálogo clásico. Se pidió quitarla: era una segunda puerta a lo mismo.

- Fuera la entrada del menú, su acción (`action_blink`) y su manejador
  (`_tools_blink`): nada los usaba ya.
- **El diálogo clásico se queda en el código, sin puerta** (decisión del
  observador): `_open_blink_dialog` y `blink_tab.ui` siguen ahí, documentados
  como el camino clásico al que hoy no llega nada de la interfaz, y con su test
  funcional. Es el camino de vuelta si algún día se quiere una entrada otra vez.
- La puerta del observador es el botón **Blink** del banco de imágenes, que no
  se toca.

**Revision (2026-10-06, sixth of the day): the ad-hoc Blink entry is gone.**
The Tools menu carried "Blink (ad-hoc)…", which with the unified editor on (the
default) opened the editor's own Blink window, the one that already has its
button in the tools row, and with the editor off opened the classic dialog. It
was asked out: it was a second door to the same thing.

- The menu entry, its action (`action_blink`) and its handler (`_tools_blink`)
  are gone: nothing used them any more.
- **The classic dialog stays in the code, without a door** (the observer's
  choice): `_open_blink_dialog` and `blink_tab.ui` are still there, documented
  as the classic path nothing in the interface reaches today, with their
  functional test. It is the way back if a door is ever wanted again.
- The observer's door is the workbench's **Blink** button, which is untouched.

**Revision (2026-10-07, Interfaz 1.9: the review period closes).** The UFE
stopped being an alternative and became the door: the three classic dialogs
that survived "just in case" are retired, and with them the switch that chose
between them and the editor.

- The **classic blink dialog** is gone (`_open_blink_dialog`, its
  `_dialog_blink_*` and `_blink_*` helpers, its state, its timers and
  `blink_tab.ui`). It had been doorless since 2026-10-06; now it takes no code
  either.
- **`SnAnnotateDialog`** is gone (`gui/sn_annotate_dialog.py`): the SN
  annotation lives in the editor's Annotate tab, and the UFE's save hook
  already registers the copy in the project.
- The **classic comparison chart** is gone (`gui/seqchart_dialog.py`, the
  classic branch of `_fu_sequence_dialog`, `_fu_sequence_done` /
  `_fu_sequence_save`) and so is its **`SequenceWorker`**: the UFE uses
  `UfeFieldWorker` / `UfeProposeWorker`, and the editor's hook already saves the
  sequence, the PNG/CSV and the campaign's `protocol.comp_stars`. No capability
  is lost.
- The **`ufe_default`** switch is gone from Settings -> Development (it also
  left measuring and astrometry with a bare message when turned off). The
  editor's icons-only top bar stays there: it is a real preference.
- **Untouched** is everything the editor reuses: `BlinkWorker`,
  `BlinkExportWorker`, `viz/blink_view.py` (the UFE and the CLI use them),
  `core/compstars.py` and the `_ufe_save_hook`.

**Entry point**: `gui/main_window.py` (the classic paths and `_use_ufe` gone),
`gui/workers.py` (`SequenceWorker` gone), `gui/ui/settings_dialog.ui` (the
switch's row gone).
