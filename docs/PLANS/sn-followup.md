# Plan — Track B: supernova, seguimiento fotométrico multi-noche

> **Abierto (2026-09-09)** — hijo B de
> [project-concept-v2.md](project-concept-v2.md) (leer primero el padre;
> decisiones transversales T1–T10). Un subplan = un commit.
> **Reescrito 2026-09-09 (post-entrevista)** tras la entrevista en profundidad
> con el observador: la unidad de trabajo es el **apilado final por noche**
> (los crudos viven fuera), los filtros son **opcionales** (el camino estándar
> es sin filtro; multi-banda = caso avanzado que ayuda a clasificar), entran
> las **plantillas de curvas típicas**, el quick-look se redefine como
> **análisis de campaña**, nacen el **FITS anotado** (B10) y la **cadencia con
> memoria** (B11, T9), y el post pasa a ser un **documento vivo**.

**rama**: `feature/sn-followup` (nace de `feature/object-card` al día, tras cerrar el track A; mergea de vuelta a `feature/object-card`)
**fecha**: 2026-09-09 · **autor**: FJC (con la IA)

## Objetivo

Un proyecto SN deja de ser «una noche» y se convierte en un **seguimiento de
semanas o meses** — y a veces de años (mismo proyecto reabierto, «un año
después»): cada visita se registran el **apilado final** por filtro y la
fotometría (sin fricción: teclear la magnitud basta), NightScribe calcula un
**análisis de campaña indicativo** propio y dibuja la **curva de luz** frente a
las **plantillas típicas del tipo**, genera la **animación de la evolución**
(GIF/MP4), recomienda la **captura por brillo**, produce el **FITS anotado**,
**recuerda la cadencia** («hace N noches que no la visitas») y mantiene el
**post vivo**. Referencia real: la página de seguimiento de AT2020sum/AT2020sun
en irydeo.com (fotometría AIJ, comparaciones Gaia DR2, tablas por filtro
Clear/NIR, revisitas).

## Decisiones pactadas (2026-09-09, incl. post-entrevista)

| # | Decisión | Valor |
|---|----------|-------|
| B-a | **Fotometría de publicación = externa** | AIJ / Tycho-Tracker (flujo real del observatorio); NightScribe registra (entrada rápida / pegado / fichero), grafica, analiza tendencias y publica. Sin fotometría absoluta propia (T1). |
| B-b | **Quick-look = análisis de campaña** | El valor no es «el punto de hoy», es **el punto de hoy en contexto**: cae sobre la curva con la tendencia y un resumen numérico honesto («bajando 0.05 mag/día en Clear, dentro de lo normal para una Ia»). `source='quicklook'`, estilo hueco, etiqueta «indicativo» (T6). |
| B-c | **Comparaciones automáticas** | Criba estadística + filtro Gaia DR3 de variables si hay red; el usuario **nunca selecciona a mano**; como mucho excluye con un clic (T2). |
| B-d | **La unidad es el apilado; la medida no exige FITS** | Se registra **una imagen apilada por noche/filtro** (normalmente con WCS propio); los crudos viven y mueren fuera. Y si una visita solo aporta una magnitud anotada, la sesión se crea por fecha (`fits_path` nullable). |
| B-e | **La pestaña «Seguimiento» no es un paso** | Vive en `tabs_steps` solo para `kind='sn'`, entre Procesado y Publicar; **no entra en la máquina de pasos** (`STEPS` intacto, patrón de la pestaña Detalles). |
| B-f | **Filtros opcionales por defecto** | Sin filtro (Clear/ninguno) es el camino estándar y todo funciona igual; multi-banda es el caso avanzado — y didáctico: bandas distintas pueden comportarse distinto y **ayudar a clasificar** el tipo (B7). |
| B-g | **Cadencia con memoria (T9)** | Seguimiento típico cada 2-3 días; el proyecto muestra «última visita hace N noches», *Tonight* avisa cuando toca revisita, y la pendiente vs plantilla alimenta el **asesor de cierre** del track A (T10). |
| B-h | **El post es un documento vivo** | Se construye noche a noche: «Actualizar post» regenera narrativa + curva + animación + tablas con lo acumulado (B9). No es un cierre único. |

## Contexto clave (exploración 2026-09-09)

- **Blink**: `core/blink.py` (`resolve_sn` L60-100 cadena TNS→SIMBAD→Rochester;
  `load_user_image` L115-184 con WCS o blind-solve Astrometry.net; `WORK_MAX`
  2048 px; `prepare_pair` L187-223 alineado por construcción con PS1-g) y
  `viz/blink_view.py` (stretch/gain/crop, `make_blink_gif` L226, MP4 L248 —
  **estrictamente 2 frames**). Reutilizable para la animación N-frame.
- **Fuentes SN**: `rochester.py` (`latest_sne` L53-68), `tns.py`
  (`parse_object_page` L40-76: tipo, mag y fecha de descubrimiento — **hoy solo
  la usa el blink**, no `enrich`), `simbad.py` (`query_id` L73-101). No hay
  fuente ASASSN/ALeRCE/ZTF.
- **Ficha**: `orbits.explain_transient` (L532-627) con `_sn_type_text`
  (L485-520: Ia, Ib/Ic, II, I genérico, CV/nova, sin clasificar — faltan IIn,
  II-P/II-L, IIb, Iax, SLSN, kilonova y toda la didáctica de curvas).
- **No existe fotometría** en el repo (ni apertura ni zero point); `fits_io.py`
  es de **solo lectura** y conserva las cabeceras (DATE-OBS/FILTER/EXPTIME
  disponibles) — el FITS anotado (B10) necesita **escritura** de FITS (copia
  nueva; `fits_io` sigue sin modificar originales); `wcs.py` da
  `sky_to_pixel` por frame.
- **Secuencias**: `core/sequence.py` `make_plan` (L34-62, **un solo filtro**),
  `export_ccdciel` (L247-300, formato real CONFIG v5 validado contra
  `docs/ccdciel_sequence_sample.targets` — que es una secuencia SN, AT2026zjn);
  empuje en vivo `ccdciel.push_plan` mono-filtro. `core/exposure.py` solo tiene
  la lógica anti-traza por **movimiento** (NEO); nada por brillo.
- **Proyectos**: paso Process SN = campo de ruta FITS (no persistido) + botón
  blink (`_build_process_tab` L2115-2165, `_project_blink` L2462).
  `observations` no guarda mag/filtro; hace falta tabla nueva (B0).
- **Sin airmass** en todo el repo; si hiciera falta: 3 líneas sobre `coords.altaz`.
- **Dolor declarado nº 1 (selección) ya resuelto** (planner + goto): este track
  ataca los otros dos — **análisis y seguimiento**.

## Subplanes

### B0 — Migración `user_version 5` + `core/followup.py`
Tablas nuevas:
```sql
project_sessions(id, project_id REFERENCES projects(id) ON DELETE CASCADE,
                 obs_date TEXT, notes TEXT DEFAULT '', created REAL);
session_images(id, session_id REFERENCES project_sessions(id) ON DELETE CASCADE,
               filter TEXT, fits_path TEXT, date_obs TEXT, exptime_s REAL);
photometry_points(id, project_id REFERENCES projects(id) ON DELETE CASCADE,
                  session_id INTEGER NULL, mjd REAL, filter TEXT,
                  mag REAL, err REAL NULL, source TEXT);
  -- source: manual|paste|file|quicklook|survey
```
`core/followup.py`: CRUD de sesiones, imágenes y puntos (patrón de
`core/project.py`). El `filter` puede ser «Clear»/«None» (camino estándar) —
no se asume rueda de filtros (B-f).

**Tests**: migración 4→5 (conserva lo anterior), CRUD, borrado en cascada,
punto sin sesión (`session_id NULL`).

### B1 — `core/fits_meta.py`
Cabeceras FITS → dict `{date_obs, mjd, filter, exptime_s, object}`:
`DATE-OBS` (fallbacks `DATE`, `UTC-OBS`), `FILTER`, `EXPTIME`, `OBJECT`; MJD vía
`coords.jd_from_datetime`. Tolerante a formatos de fecha con/sin `T`.

**Tests**: cabeceras sintéticas (con/sin campos, formatos distintos), sin red.

### B2 — Pestaña «Seguimiento» en el proyecto SN
`tabs_steps` gana la pestaña **Seguimiento** solo para `kind='sn'` (no es paso;
prev/skip/done desactivados en ella, como en Detalles):
- Lista de visitas (sesiones, cada 2-3 días en el flujo real) con nº de
  imágenes y nº de medidas, y **«última visita hace N noches»** siempre visible.
- «Añadir visita» → por defecto hoy; por visita, «Añadir apilado» (diálogo de
  ficheros): filtro/fecha/exposición **auto desde B1**, editables; rutas
  registradas (nunca copiadas, T4). Una imagen por noche/filtro (B-d).
- **Cajón de notas por visita** (seeing, nubes, incidencias — «en ocasiones» se
  guardan; alimentan el post vivo, B9).
- Sin FITS: la visita existe igualmente (B-d).

**Tests**: offscreen — pestaña solo en SN, añadir visita/apilado con
`fits_meta` fake, notas persisten, borrado de sesión.

### B3 — Entrada de fotometría sin fricción
Tres vías en la pestaña Seguimiento:
1. **Rápida** (la habitual): «Añadir medida» en la visita → fecha/hora y filtro
   auto del apilado (o noche actual si no hay), el usuario **solo teclea la
   magnitud** (error opcional). Otra fila = otra medida/filtro.
2. **Pegado en lote**: caja de texto (patrón reporte MPC, ADR-022: pegar →
   validar → previsualizar → guardar), parser tolerante a
   `fecha mag [err] filtro` separado por comas/tab/espacios, export de tabla de
   **AIJ** y de **Tycho-Tracker** (fotometría absoluta), y coma o punto decimal.
3. **Fichero CSV/AIJ/Tycho**: opcional, para campañas.

**Tests**: parser (cada formato, coma decimal, líneas malas con aviso),
previsualización, guardado con `source` correcto.

### B4 — Curva de luz con plantillas típicas
`viz/lightcurve_view.py` (PNG matplotlib para posts, ADR-010) +
`gui/widgets/lightcurve_widget.py` (QGraphicsView, ADR-029 — sin matplotlib):
- mag vs fecha, **eje Y invertido**, una serie por filtro (colores del tema,
  ADR-026), barras de error; Clear/None es una serie más (B-f).
- Estilo por fuente: `manual/paste/file` relleno; `quicklook` hueco +
  leyenda «indicativo»; `survey` gris tenue (B12).
- **Plantillas típicas por tipo** (Ia, II-P, II-L, Ib/c…): formas
  **esquemáticas** normalizadas (pico = 0 mag, días desde el pico) integradas
  en el repo como tablas pequeñas, dibujadas en línea tenue bajo los puntos,
  alineadas al pico (o al primer punto si aún sube). Multi-banda: best-effort
  (lo que se pueda codificar con honestidad; etiqueta «esquemática, no para
  análisis»). **Motivo declarado**: comparar con la curva típica es lo que
  permite decir «evoluciona normal» vs «hay algo brusco» — el criterio real de
  seguir/soltar (T10).
- Slot en la ficha del objeto (Detalles) cuando el proyecto tiene puntos.

**Tests**: offscreen del widget y render PNG con puntos fake; eje invertido;
series por filtro; estilos por fuente; plantilla alineada al pico.

### B5 — `core/series.py`: análisis de campaña (quick-look diferencial)
Motor compartido con la animación (B6), numpy puro (ADR-004), operando sobre
**los apilados registrados** (B-d):
1. Carga de apilados (`fits_io`) + **WCS por imagen** (vía del blink: header —
   lo habitual, el observador conserva el apilado resuelto — o blind-solve
   Astrometry.net si hay clave). Píxel de la SN en cada una.
2. **Detección de fuentes** en la imagen de referencia: máximos locales sobre
   `cielo + k·σ` + centroide en cajita (detector simple propio, nada de sep).
3. **Criba automática** de candidatas en *todas* las imágenes:
   no saturada (umbral estimado del histograma; `config["saturation_adu"]`
   opcional), aislada (sin vecino a 2× radio de apertura), constante (scatter
   bajo en la serie con rechazo iterativo, espíritu AIJ), lejos de la SN y de
   los bordes.
4. **Filtro Gaia DR3** si hay red: nuevo `core/sources/gaiacat.py` (cone-search
   VizieR `I/355/gaiadr3`, caché `db.http_get`) — descarta `phot_variable_flag`
   y anota mag G de contexto. Sin red: la criba estadística basta (diferencial
   puro).
5. Ensemble final (objetivo ~8, mínimo 3, aviso si <3): Δmag SN = mag
   instrumental − media del ensemble; **error honesto** = scatter del ensemble.
   Puntos a `photometry_points` con `source='quicklook'`.
6. **Análisis de campaña** (B-b): con los puntos propios (importados +
   quick-look), resumen numérico honesto en la pestaña: pendiente mag/día por
   filtro (ajuste lineal simple), Δmag desde el pico, noches cubiertas, y
   veredicto frente a plantilla («dentro de lo normal para una Ia» / «se
   desvía») — sin magia, y es la señal que consume el asesor de cierre (A2/B11).
7. **Revisión por exclusión**: vista de la serie con marcadores sobre las
   comparaciones elegidas; clic en una la excluye y recalcula (T2).

La fotometría se mide en los **píxeles nativos de cada imagen** (WCS propio) —
no hace falta remuestrear.

**Tests**: imágenes sintéticas con estrellas plantadas (numpy): criba por
regla, rechazo de variable, Δmag recuperada, camino sin red, aviso con <3,
resumen de campaña (pendiente conocida inyectada).

### B6 — Animación de evolución (GIF/MP4)
Sobre el motor de B5: transformación afín por imagen desde su WCS (centro,
escala, rotación → PIL) alineando cada recorte a la geometría de referencia;
recorte común alrededor de la SN con marcador (maquinaria de `blink_view`);
etiqueta de fecha por frame; un frame representativo por visita (filtro
elegible). GIF + MP4 registrados en `project_files`. Imagen con WCS malo → se
salta con aviso, no aborta.

**Tests**: matriz afín desde WCS fake, etiquetado de fecha, GIF/MP4 con frames
sintéticos, salto de imagen sin WCS.

### B7 — Didáctica de tipos de SN en la ficha
- `orbits._sn_type_text`: añadir IIn, II-P/II-L, IIb, Iax, SLSN, kilonova;
  por tipo: mecanismo progenitor, **forma de curva esperada** (plateau vs
  declive lineal — enlaza con las plantillas de B4), magnitud absoluta típica
  (Ia ≈ −19.3), escalas de subida/caída, y **por qué importa el multi-filtro**:
  bandas distintas pueden comportarse distinto y ayudar a clasificar (color →
  temperatura; el espectro es la clasificación definitiva).
- Bloque didáctico «Tipos de supernova» (árbol I sin H / II con H…) en la ficha,
  plegable, pares ES/EN por `orbits.pick`.
- `enrich._enrich_transient`: consulta **TNS** cuando SIMBAD no conoce la SN
  (tipo/mag/fecha de `tns.parse_object_page`, patrón ADR-027).

**Tests**: mapeo de tipos ES/EN, bloque visible por tipo, merge TNS con fake.

### B8 — Captura SN: exposición por brillo (+ multi-filtro avanzado)
- `core/exposure.py::recommended_sn_exposure(mag)`: tabla honesta por brillo
  (documentada, capada; p. ej. <14 → 30-60 s, 14-16 → 60-120 s, 16-18 →
  120-300 s, >18 → 300 s) escalada por escala de placa; aviso «guía, no SNR».
  La duración total real de una visita la marca el brillo (de 15 min a horas).
- `sequence.make_plan` gana `steps=[(filter, n, exp), ...]` (retrocompatible:
  mono-filtro/sin filtro = un paso); `export_ccdciel` escribe N pasos **Light**
  + calibración una vez; NINA/CSV igual; validación del `.targets` multi-paso
  contra un export real del observatorio (filosofía ADR-021).
- Bloque SN en `_build_plan_tab`: un paso por defecto (B-f); filas extra
  filtro×N×exp opcionales (añadir/quitar); preselección de exposición por mag;
  sin cap anti-traza (no aplica).
- Empuje en vivo `ccdciel.push_plan` sigue mono-filtro en v1 (anotado).

**Tests**: plan multi-paso, `.targets` con N pasos Light y atributos esperados,
GUI offscreen (filas, preselección), retrocompatibilidad mono-filtro.

### B9 — Post vivo de seguimiento (estilo irydeo)
`core/post.py` gana el documento vivo de seguimiento SN: **«Actualizar post»**
regenera todo con lo acumulado — narrativa de la evolución (visitas, Δmag desde
el pico, hitos) + curva de luz (B4) + animación (B6, referenciada como el
blink, ADR-024) + **tabla fotométrica por filtro** (fecha, mag, filtro — la
estructura de la página de ejemplo) + tabla de comparaciones (Gaia) + cabecera
de equipo desde config + **notas de las visitas** (B2) como diario. ES/EN.
El post nunca se «termina» hasta que se cierra el proyecto; cada actualización
es idempotente sobre el mismo fichero.

**Tests**: markdown contiene las secciones con datos fake; regenerar no duplica;
sin puntos → secciones se omiten; las notas aparecen en el diario.

### B10 — FITS anotado (nuevo)
El observador guarda «la imagen anotada, resuelta astrométricamente»: AIJ
guarda la anotación en la **cabecera del FITS** y la pinta al cargar; Tycho
genera imágenes anotadas para NEOs (precedente en el track C). NightScribe:
- Lee el apilado registrado, escribe una **copia** con keywords de anotación
  (cruz sobre la SN, escala, norte, etiquetas) — `fits_io` sigue siendo de solo
  lectura; la escritura es una función nueva mínima (copia + cabeceras extra).
- **Investigación previa obligatoria**: formato exacto de anotación de AIJ en
  cabecera (si es público/estable, ser compatibles; si no, keywords propias
  documentadas — riesgo marcado abajo).
- **Export PNG** de la imagen anotada para compartir (viz; estilo del tema).
- Registrado en `project_files` (`kind='fits'` / `'chart'`).

**Tests**: la copia no toca el original; keywords escritas y releídas; PNG
generado con anotaciones visibles (render sintético).

### B11 — Cadencia con memoria (T9)
- `core/followup.py`: `days_since_last_session(project)` + cadencia sugerida
  (`config["sn_cadence_days"]`, default 3).
- Pestaña Seguimiento: «última visita hace N noches» + «toca revisita» cuando
  N ≥ cadencia.
- **Tonight**: los proyectos SN activos que tocan revisita aparecen como aviso
  (no como objetivo nuevo — el objeto ya tiene proyecto; patrón del chip de
  proyecto activo existente).
- **Señal para el asesor de cierre (A2)**: «evolución normal desde N días»
  (pendiente dentro de lo esperado vs plantilla, B5.6) alimenta la sugerencia
  de cierre. Sugiere, nunca decide (T10).

**Tests**: cálculo de días, aviso en la pestaña, hint en Tonight con proyecto
fake, señal de cierre con pendiente sintética.

### B12 — Contexto de surveys (opcional)
Nueva fuente (`core/sources/`: ASASSN Sky Patrol y/o ALeRCE-ZTF según viabilidad
del endpoint): botón «Descargar fotometría de surveys» → puntos grises tenues
bajo las propias en la curva (B4), `source='survey:…'`, leyenda clara. Nunca se
mezclan con las medidas propias.

**Tests**: parser con fixture JSON, puntos dibujados como contexto, sin red →
aviso y nada se rompe.

### B13 — Cierre del track
i18n ES/EN (~40-50 cadenas) · revisión de ADR-016/ADR-018 (alcance blink vs
animación) y nota en ADR-021 (multi-filtro) · sección en
`docs/WORKFLOWS.es/.md` + marca «Hecho» en el padre · `pytest tests/unit` verde.

## Orden de ejecución

B0 → B1 → B2 → B3 → B4 → B5 → B6 → B7 → B8 → B9 → B10 → B11 → B12 → B13
(B2/B3 cuelgan de B0/B1; B4 puede ir con datos fake desde B3; B6 cuelga de B5;
B9 cuelga de B4/B6; B7/B8 son independientes entre sí; B10 es independiente
tras B2; B11 cuelga de B5.6 y A2.)

## Fuera de alcance

- Fotometría absoluta propia (términos de color; posible v2, ver padre).
- Sustracción de galaxia anfitriona / ajuste PSF (lo hace AIJ).
- Importación automática periódica de surveys (B12 es bajo demanda).
- Clasificación espectroscópica (fuera del alcance del software; la didáctica
  de B7 lo explica como la vía definitiva).

## Riesgos conocidos

- **Precisión del quick-look** según campo (Vía Láctea, crowding): la criba +
  el error honesto + la etiqueta «indicativo» son la defensa; nunca se mezcla
  con la fotometría de publicación (T6).
- **Formato de anotación de AIJ** puede no ser público/estable: investigación
  previa en B10; si no, keywords propias documentadas (el PNG de compartición
  no depende de ello).
- **Plantillas típicas** son esquemáticas por construcción: etiqueta clara y
  nunca alimentan el score ni decisiones automáticas (solo el asesor, que
  sugiere y no decide, T10).
- **FITS sin WCS ni clave Astrometry**: esa visita entra en la curva (fecha del
  header) pero no en la animación (se salta con aviso).
- **Formatos de export de AIJ/Tycho variables**: parser tolerante +
  previsualización antes de guardar (B3).
- **VizieR/Gaia caído o sin red**: el quick-look funciona igual (criba
  estadística); el filtro de variables es un extra, no un requisito.
