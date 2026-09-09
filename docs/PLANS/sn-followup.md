# Plan — Track B: supernova, seguimiento fotométrico multi-noche

> **Abierto (2026-09-09)** — hijo B de
> [project-concept-v2.md](project-concept-v2.md) (leer primero el padre;
> decisiones transversales T1–T8). Un subplan = un commit.

**rama**: `feature/sn-followup` (nace de `feature/object-card` al día, tras cerrar el track A; mergea de vuelta a `feature/object-card`)
**fecha**: 2026-09-09 · **autor**: FJC (con la IA)

## Objetivo

Un proyecto SN deja de ser «una noche» y se convierte en un **seguimiento de
días o meses**: cada noche se registran las imágenes por filtro y la fotometría
(sin fricción: teclear la magnitud basta), NightScribe calcula un **quick-look
diferencial indicativo** y dibuja la **curva de luz**, genera la **animación de
la evolución** (GIF/MP4), recomienda la **captura por brillo** con **secuencias
multi-filtro**, y la ficha explica los **tipos de supernova** de forma didáctica.
Referencia real: la página de seguimiento de AT2020sum/AT2020sun en irydeo.com
(fotometría AIJ, comparaciones Gaia DR2, tablas por filtro Clear/NIR).

## Decisiones pactadas (2026-09-09)

| # | Decisión | Valor |
|---|----------|-------|
| B-a | **Fotometría de publicación = externa (AIJ)** | NightScribe registra (entrada rápida / pegado / fichero), grafica y publica. No hay fotometría absoluta propia (T1 del padre). |
| B-b | **Quick-look diferencial propio, etiqueta «indicativo»** | `core/series.py`: Δmag contra ensemble automático de comparaciones. Sin promesa de calibración absoluta. Puntos con `source='quicklook'` y estilo hueco en la curva. |
| B-c | **Comparaciones automáticas** | Criba estadística (no saturada, aislada, constante) + filtro Gaia DR3 de variables si hay red. El usuario **nunca selecciona a mano**; como mucho excluye con un clic (T2). |
| B-d | **La medida no exige FITS** | Si solo se anota la magnitud, la sesión se crea por fecha (`fits_path` nullable). El FITS alimenta la animación y el registro, no es requisito. |
| B-e | **La pestaña «Seguimiento» no es un paso** | Vive en `tabs_steps` solo para `kind='sn'`, entre Procesado y Publicar; **no entra en la máquina de pasos** (`STEPS` intacto, patrón de la pestaña Detalles). |
| B-f | **Multi-filtro en secuencias** | `sequence.make_plan` gana lista de pasos `(filtro, n, exp)` retrocompatible (un plan mono-filtro = un paso); CCDciel escribe N pasos Light. |

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
  es de solo lectura y **conserva las cabeceras** (DATE-OBS/FILTER/EXPTIME
  disponibles); `wcs.py` da `sky_to_pixel` por frame.
- **Secuencias**: `core/sequence.py` `make_plan` (L34-62, **un solo filtro**),
  `export_ccdciel` (L247-300, formato real CONFIG v5 validado contra
  `docs/ccdciel_sequence_sample.targets` — que es una secuencia SN, AT2026zjn);
  empuje en vivo `ccdciel.push_plan` mono-filtro. `core/exposure.py` solo tiene
  la lógica anti-traza por **movimiento** (NEO); nada por brillo.
- **Proyectos**: paso Process SN = campo de ruta FITS (no persistido) + botón
  blink (`_build_process_tab` L2115-2165, `_project_blink` L2462).
  `observations` no guarda mag/filtro; hace falta tabla nueva (B0).
- **Sin airmass** en todo el repo; si hiciera falta: 3 líneas sobre `coords.altaz`.

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
                  mag REAL, err REAL NULL, source TEXT);  -- manual|paste|file|quicklook|survey
```
`core/followup.py`: CRUD de sesiones, imágenes y puntos (patrón de
`core/project.py`).

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
- Lista de noches (sesiones) con nº de imágenes y nº de medidas.
- «Añadir noche» → por defecto hoy; por sesión, «Añadir FITS» (diálogo de
  ficheros, multi-selección): filtro/fecha/exposición **auto desde B1**,
  editables; rutas registradas (nunca copiadas, T4).
- Sin FITS: la noche existe igualmente (B-d).

**Tests**: offscreen — pestaña solo en SN, añadir noche/FITS con `fits_meta`
fake, borrado de sesión.

### B3 — Entrada de fotometría sin fricción
Tres vías en la pestaña Seguimiento:
1. **Rápida** (la habitual): «Añadir medida» en la sesión → fecha/hora y filtro
   auto del FITS de la sesión (o noche actual si no hay), el usuario **solo
   teclea la magnitud** (error opcional). Otra fila = otra medida/filtro.
2. **Pegado en lote**: caja de texto (patrón reporte MPC, ADR-022: pegar →
   validar → previsualizar → guardar), parser tolerante a
   `fecha mag [err] filtro` separado por comas/tab/espacios, export de tabla de
   AIJ, y coma o punto decimal.
3. **Fichero CSV/AIJ**: opcional, para campañas.

**Tests**: parser (cada formato, coma decimal, líneas malas con aviso),
previsualización, guardado con `source` correcto.

### B4 — Curva de luz
`viz/lightcurve_view.py` (PNG matplotlib para posts, ADR-010) +
`gui/widgets/lightcurve_widget.py` (QGraphicsView, ADR-029 — sin matplotlib):
- mag vs fecha, **eje Y invertido**, una serie por filtro (colores del tema,
  ADR-026), barras de error.
- Estilo por fuente: `manual/paste/file` relleno; `quicklook` hueco +
  leyenda «indicativo»; `survey` gris tenue (B10).
- Slot en la ficha del objeto (Detalles) cuando el proyecto tiene puntos.

**Tests**: offscreen del widget y render PNG con puntos fake; eje invertido;
series por filtro; estilos por fuente.

### B5 — `core/series.py`: motor de series + quick-look diferencial
Motor compartido con la animación (B6), numpy puro (ADR-004):
1. Carga de frames (`fits_io`) + **WCS por frame** (vía del blink: header o
   blind-solve Astrometry.net si hay clave). Píxel de la SN en cada frame.
2. **Detección de fuentes** en el frame de referencia: máximos locales sobre
   `cielo + k·σ` + centroide en cajita (detector simple propio, nada de sep).
3. **Criba automática** de candidatas en *todos* los frames:
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
6. **Revisión por exclusión**: vista de la serie con marcadores sobre las
   comparaciones elegidas; clic en una la excluye y recalcula. El usuario nunca
   selecciona a mano (T2).

La fotometría se mide en los **píxeles nativos de cada frame** (WCS propio) —
no hace falta remuestrear imágenes.

**Tests**: frames sintéticos con estrellas plantadas (numpy): criba por regla,
rechazo de variable, Δmag recuperada, camino sin red, aviso con <3.

### B6 — Animación de evolución (GIF/MP4)
Sobre el motor de B5: transformación afín por frame desde su WCS (centro,
escala, rotación → PIL) alineando cada recorte a la geometría de referencia;
recorte común alrededor de la SN con marcador (maquinaria de `blink_view`);
etiqueta de fecha por frame; un frame representativo por noche (filtro elegible).
GIF + MP4 registrados en `project_files`. Frame con WCS malo → se salta con
aviso, no aborta.

**Tests**: matriz afín desde WCS fake, etiquetado de fecha, GIF/MP4 con frames
sintéticos, salto de frame sin WCS.

### B7 — Didáctica de tipos de SN en la ficha
- `orbits._sn_type_text`: añadir IIn, II-P/II-L, IIb, Iax, SLSN, kilonova;
  por tipo: mecanismo progenitor, **forma de curva esperada** (plateau vs
  declive lineal), magnitud absoluta típica (Ia ≈ −19.3), escalas de
  subida/caída, y por qué importa el multi-filtro (color → temperatura).
- Bloque didáctico «Tipos de supernova» (árbol I sin H / II con H…) en la ficha,
  plegable, pares ES/EN por `orbits.pick`.
- `enrich._enrich_transient`: consulta **TNS** cuando SIMBAD no conoce la SN
  (tipo/mag/fecha de `tns.parse_object_page`, patrón ADR-027).

**Tests**: mapeo de tipos ES/EN, bloque visible por tipo, merge TNS con fake.

### B8 — Captura SN: exposición por brillo + multi-filtro
- `core/exposure.py::recommended_sn_exposure(mag)`: tabla honesta por brillo
  (documentada, capada; p. ej. <14 → 30-60 s, 14-16 → 60-120 s, 16-18 →
  120-300 s, >18 → 300 s) escalada por escala de placa; aviso «guía, no SNR».
- `sequence.make_plan` gana `steps=[(filter, n, exp), ...]` (retrocompatible:
  mono-filtro = un paso); `export_ccdciel` escribe N pasos **Light** + calibración
  una vez; NINA/CSV igual; validación del `.targets` multi-paso contra un export
  real del observatorio (filosofía ADR-021).
- Bloque SN en `_build_plan_tab`: filas de pasos filtro×N×exp (añadir/quitar),
  preselección de exposición por mag, sin cap anti-traza (no aplica).
- Empuje en vivo `ccdciel.push_plan` sigue mono-filtro en v1 (anotado).

**Tests**: plan multi-paso, `.targets` con N pasos Light y atributos esperados,
GUI offscreen (filas, preselección), retrocompatibilidad mono-filtro.

### B9 — Post de seguimiento (estilo irydeo)
`core/post.py` gana sección «Seguimiento» para SN con datos: narrativa de la
evolución (noches, Δmag desde el pico) + curva de luz (B4) + animación (B6,
referenciada como el blink, ADR-024) + **tabla fotométrica por filtro**
(fecha, mag, filtro — la estructura de la página de ejemplo) + tabla de
comparaciones (Gaia) y cabecera de equipo desde config. ES/EN.

**Tests**: markdown contiene las secciones con datos fake; sin puntos → la
sección se omite.

### B10 — Contexto de surveys (opcional)
Nueva fuente (`core/sources/`: ASASSN Sky Patrol y/o ALeRCE-ZTF según viabilidad
del endpoint): botón «Descargar fotometría de surveys» → puntos grises tenues
bajo las propias en la curva (B4), `source='survey:…'`, leyenda clara. Nunca se
mezclan con las medidas propias.

**Tests**: parser con fixture JSON, puntos dibujados como contexto, sin red →
aviso y nada se rompe.

### B11 — Cierre del track
i18n ES/EN (~30-40 cadenas) · revisión de ADR-016/ADR-018 (alcance blink vs
animación) y nota en ADR-021 (multi-filtro) · sección en
`docs/WORKFLOWS.es/.md` + marca «Hecho» en el padre · `pytest tests/unit` verde.

## Orden de ejecución

B0 → B1 → B2 → B3 → B4 → B5 → B6 → B7 → B8 → B9 → B10 → B11
(B2/B3 cuelgan de B0/B1; B4 puede ir con datos fake desde B3; B6 cuelga de B5;
B9 cuelga de B4/B6; B7/B8 son independientes entre sí.)

## Fuera de alcance

- Fotometría absoluta propia (términos de color; posible v2, ver padre).
- Sustracción de galaxia anfitriona / ajuste PSF (lo hace AIJ).
- Importación automática periódica de surveys (B10 es bajo demanda).

## Riesgos conocidos

- **Precisión del quick-look** según campo (Vía Láctea, crowding): la criba +
  el error honesto + la etiqueta «indicativo» son la defensa; nunca se mezcla
  con la fotometría de publicación (T6).
- **FITS sin WCS ni clave Astrometry**: esa noche entra en la curva (fecha del
  header) pero no en la animación (se salta con aviso).
- **Formatos de export de AIJ variables**: parser tolerante + previsualización
  antes de guardar (B3).
- **VizieR/Gaia caído o sin red**: el quick-look funciona igual (criba
  estadística); el filtro de variables es un extra, no un requisito.
