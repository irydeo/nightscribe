# Plan: astrometría de cuerpos menores por track & stack, y calibración de imágenes

*Plan de trabajo con todo lujo de detalles / Detailed working plan.*

- **Rama**: `plan/astrometry-minor-planets` (a crear desde `main` actualizado).
- **Alcance**: calibración de imágenes (bias, dark, flat) con biblioteca de
  masters, astrometría de cuerpos menores por apilado guiado por efeméride
  (track & stack), reparto en varias observaciones, validación (visual y
  contra otros observadores), reporte al Minor Planet Center (ADES PSV y 80
  columnas) y liberación de espacio de la visita.
- **Estado**: decisiones cerradas en conversación con el autor (D1 a D32). La
  **fase 0** las convierte en ADRs firmados antes de escribir código.
- **Estilo**: reglas de la casa (escribimos con «:», «,» y «;»; la semirraya
  «–» solo para rangos numéricos, nunca como raya).
- **Regla de código**: didáctico (AGENTS.md y ADR-058). Cada bloque no obvio
  explica el qué y el por qué; nada de comentarios obvios; cada cifra que ve
  el usuario va acompañada de su significado.

---

## 1. Contexto: qué hay y qué falta

Hoy NightScribe:

- **Resuelve placas** con ASTAP local o nova (ADR-051) y persiste el WCS en la
  cabecera de forma atómica (`core/solve.py`, `core/wcs_store.py`). El WCS
  propio es TAN puro y **ignora SIP** (`core/wcs.py`).
- **Registra frames sin WCS** con `core/register.py` (D44): traslación subpíxel
  por correlación de fase, rotación rígida, máscaras y puertas de confianza.
- **Mide series fotométricas** con `core/series_measure.py` (ADR-048), que
  recorre frames, mide con `core/photometry.py` y soporta objetos en
  movimiento vía `target_motion(jd)`. Agrupa en el dominio de la medida:
  **nunca apila píxeles**.
- **Valida y empaqueta reportes MPC** que el usuario pega (`core/mpc_report.py`,
  ADR-022). No genera medidas: ADR-022 lo dice explícitamente.
- Registra los frames de una visita por **ruta** en `project_files`
  (`session_id` + `meta`, ADR-045). **No los copia**.
- En la ficha del objeto ya muestra el **número de observaciones** (`n_resids`)
  y los días de arco (`core/orbits.py::explain_elements`); NEOfixer aporta
  además `last_obs` (`core/sources/neofixer.py`).

Lo que falta:

1. **Calibración de imágenes**: no existe. Ni master, ni resta de bias o dark,
   ni división de flat. Solo la corriente de oscuridad dentro del presupuesto
   de error y la planificación de tomas de calibración (`core/sequence.py`).
2. **Apilado de píxeles**: no existe en ningún sitio.
3. **Astrometría propia**: NightScribe no genera posiciones (ADR-022).
4. **Varias observaciones por secuencia** y su validación (visual y contra
   otros observadores): no existe.
5. **Observatorios distintos** que han visto un objeto y **fecha de su última
   observación**: no se muestran en la ficha.
6. **Gestión de espacio**: cientos de FITS de 16 MP por visita se acumulan.

Este plan añade las seis, en ese orden de dependencia, y **reabre ADR-004**
(prohibición de scipy y astropy) porque las librerías estándar ahorran
reimplementar mal lo que ya está resuelto.

**El referente del ramo es Tycho-Tracker.** Es la herramienta que usa el autor,
la que el MPC documenta para el apilado de objetos débiles (synthetic tracking)
y la que sirve de patrón en dos cosas: el **chequeo con Find_Orb** (fase 5) y la
**validación real** de nuestras medidas (fase 10). Donde el plan dice «como hace
Tycho-Tracker», se refiere a ese patrón.

---

## 2. Decisiones firmadas con el autor

### Núcleo del MVP

- **D1 · Solo tracking directo.** El MVP apila objetos **con efemérides u
  órbita** (NEO, cometa, PCCP con elementos). El grid search (búsqueda a
  ciegas de objetos desconocidos) queda fuera; la arquitectura deja el hueco
  previsto para no rehacerla después. El grid search multiplica el cómputo y
  el riesgo de falsos positivos, y no es lo que el autor necesita ahora.
- **D2 · NightScribe calibra.** La calibración entra en la app, no se delega:
  sin ella, el objeto débil no emerge del ruido. La receta es **declarativa**
  (bias o dark-flat según lo que haya en la biblioteca), nunca cableada a un
  sensor.
- **D3 · Masters del usuario, biblioteca indexada.** El autor ya construye sus
  masters fuera; NightScribe los **apunta** y los indexa por cámara, ganancia,
  temperatura (±3 °C), exposición (exacta) y filtro. Índice en SQLite
  (`calib_masters`), ficheros en disco.
- **D4 · Calibración reutilizable.** Es un paso de la app con pestaña propia en
  el Editor FITS unificado y biblioteca en Ajustes. No vive escondida dentro
  del track & stack: la fotometría de series también se beneficiará.
- **D5 · Flat por filtro, con dark-flat y normalizado.** Se resta al flat su
  propio dark-flat, se normaliza por la mediana y se divide. El dark no se
  escala: coincidencia exacta de exposición (en CMOS el patrón no escala bien).
- **D6 · Calibración en memoria, export opcional.** El apilado consume arrays
  calibrados; escribir cientos de FITS calibrados es opcional y explícito.
- **D7 · Medida doble con el mismo centroide.** Se mide el objeto sobre el
  stack final y en cada frame por separado; las dos vías usan el **mismo**
  centroide (photutils), para que su comparación tenga sentido. `photometry.py`
  queda intacto; su receta de punto cero y magnitud sí se reutiliza (no se
  duplica).
- **D8 · Movimiento por efeméride completa.** Cada frame se desplaza a la
  posición efemérica de su instante (`ephemeris.position_at` /
  `motion_interpolator` sobre Horizons), no a un rate lineal constante. El
  rate lineal es solo la semilla del barrido. En una aproximación cercana el
  rate cambia dentro de la propia secuencia.
- **D9 · Fine-tuning por micro-cuadrícula.** Alrededor de la velocidad teórica
  se prueban 25 combinaciones (±5 %), y se elige la que **maximiza un score
  combinado de SNR y redondez** (segundos momentos). Corrige la deriva real
  entre efeméride y montura.
- **D10 · Puerta de no detección.** Si el apilado base con la velocidad teórica
  no supera el umbral de SNR (configurable, 3,5σ por defecto), **no se ejecuta
  el barrido** (evita medir ruido y fabricar falsos positivos), se marca
  `NOT_DETECTED` y se ofrece la **magnitud límite** de la pila. La magnitud
  límite es un dato útil aunque no haya objeto: dice hasta dónde llegaba la
  noche.
- **D11 · Recorte para el barrido, frame completo para el final.** El solve y la
  alineación usan el frame completo; el barrido (que re-apila decenas de
  veces) trabaja un **recorte** alrededor de la traza; el stack final, sobre
  el frame completo. Cuatro métodos de combinación seleccionables (suma,
  media, mediana, sigma-clipped) y **pesos iguales** (el sigma-clipped ya
  rechaza lo malo; el peso añade poco y complica la explicación).
- **D12 · Memoria adaptativa, multiproceso, calidad primero.** En RAM si cabe,
  streaming por franjas si no. Se puede paralelizar (ADR-004 no lo prohibía y
  ahora menos). El autor prioriza la calidad sobre el tiempo.
- **D13 · Reporte en los dos formatos.** Se generan **ADES PSV** y **MPC 80
  columnas**, con **T_mid** (punto medio de la exposición), magnitud calibrada
  **solo si hay comparsas** (si no, se omite en vez de inventarla) e
  incertidumbres **rmsRA/rmsDec** propagadas.
- **D14 · Persistencia en tablas nuevas.** `astrometry_runs` (configuración,
  velocidad resuelta, método, estado) y `astrometry_points` (posición, error,
  magnitud, flags, vía de medida, grupo y resultado del chequeo). El stack se
  guarda como fichero del proyecto. **Undo por ejecución** (mismo patrón que
  las series, D6 y D9 de ADR-048).
- **D15 · Entrada desde la visita.** El flujo arranca en la visita, con el
  objeto del proyecto (regla D8 de la casa: sin visita no hay serie). Los
  candidatos PCCP se empaquetan con su designación provisional tal cual; el
  validador existente ya avisa de desajustes.
- **D16 · Contraste de las dos medidas.** Si la posición del stack y la del
  promedio por frame difieren más de **0,5″ o 3σ**, el punto se **marca con un
  flag** y se avisa en la ficha. Nunca se elige en silencio.

### Varias observaciones, validación y envío

- **D22 · Multiobservación.** El usuario dice **cuántas observaciones quiere**
  y el software reparte la secuencia en ese número de **grupos contiguos de
  igual número de frames**. Cada grupo es una observación con su T_mid, su SNR
  y su medida. El barrido de velocidad se hace **una vez** sobre la secuencia
  completa y se aplica a todos los grupos. La interfaz muestra el **SNR
  previsto de cada grupo** al elegir el número (el SNR crece con `√n`, así que
  pedir más observaciones reparte la señal; hay que verlo antes de aceptar).
- **D23 · Posición por grupo.** Cada grupo tiene su propio instante de
  referencia (`T_mid` del grupo) y, por tanto, su propio punto `q_g` en la
  rejilla: el objeto se coloca en la posición efemérica **de ese instante**, no
  en la del primer frame. Así la posición medida corresponde al T_mid que se
  reporta. Si todos los grupos midieran en el mismo píxel darían la misma
  posición para instantes distintos, que es el error clásico de este tipo de
  código.
- **D24 · Secuencia de validación.** Cada grupo produce una imagen centrada en
  su `q_g` y se monta un **GIF/montaje con las N observaciones** para ver el
  objeto aparecer en todas. Reutiliza el motor de blink
  (`core/viz/blink_view.py`) y el `kind` `motion_gif` que ya existe en las
  visitas.
- **D25 · Chequeo delegado en Find_Orb.** No se reimplementa el ajuste de
  órbitas: Find_Orb ya está probado y hace el leave-one-out de verdad. Antes
  del reporte se descargan las observaciones publicadas del objeto (**MPC
  Observations API**) o del NEOCP (**NEOCP Observations API** si no está
  confirmado), NightScribe escribe el fichero con **las nuestras y las de los
  demás**, y lanza Find_Orb **excluyendo las nuestras del ajuste**. Find_Orb
  devuelve los residuos de todas, y nuestra capa fina separa los nuestros de
  los de los demás, calcula la dispersión robusta y decide. Si nuestro punto
  es outlier, se **bloquea por defecto**, con opción de forzar dejando
  constancia. Si Find_Orb no está configurado, el chequeo **no está
  disponible** y se dice: la red de seguridad son la secuencia centrada (D24)
  y el umbral de envío (D26). Esto cubre tanto objetos con órbita como
  NEOCP/PCCP (Find_Orb ajusta también arcos cortos), así que no hacen falta un
  chequeo out-of-sample propio ni un tracklet propio.
- **D30 · Normalización y nube del chequeo.** El residual se normaliza como
  `z = residual / sqrt(rms_nuestro² + scatter²)`, usando el rmsRA/rmsDec que ya
  propaga la fase 4; el outlier es `|z| > 3` **y** por encima del suelo
  absoluto de 1″. A Find_Orb se le dan **todas** las observaciones de los demás
  (cuantos más datos, mejor la órbita con la que se nos predice); la dispersión
  de comparación se calcula con las de los demás **dentro de ±30 días** y
  **excluyendo nuestro propio código de observatorio** (si no, el chequeo se
  vuelve circular). Sin nadie en la ventana, `no_reference` y no se bloquea (un
  objeto recuperado tras meses puede tener la órbita derivada, y eso no es
  culpa de nuestra medida).
- **D31 · Find_Orb se instala de forma guiada, no se empaqueta.** La app
  prepara un Find_Orb privado desde Ajustes, con el patrón de EXOTIC (ADR-052):
  en Linux/macOS descarga **micromamba** y crea un entorno privado con
  `findorb` de conda-forge; en Windows descarga `find_c64.zip` y `fo64.exe` de
  Project Pluto. Con progreso, cancelación y **respaldo manual** (apuntar a un
  binario propio). **No se incluye en el instalador**: Find_Orb es GPLv2 y su
  página añade una cláusula extra de uso comercial que no encaja en una app
  GPLv3, y sus efemérides DE430t pesan; como herramienta externa que solo se
  detecta y se ejecuta, la posición legal es la misma que con ASTAP y EXOTIC.
  Si no hay Find_Orb, el chequeo **no está disponible** y se dice (D25).
- **D32 · Disciplina de memoria.** Cuatro reglas para no reventar la RAM:
  - **Lectura con `memmap=True, do_not_scale_image_data=True`** y **solo la
    ROI** con `hdu.section`. Verificado el 2026-10-04: con `BZERO`/`BSCALE`/
    `BLANK` en la cabecera (el caso habitual del uint16 de las CMOS), astropy
    **se niega a mapear** y tanto `.data` como `.section` lanzan
    `ValueError: Cannot load a memory-mapped image`; con
    `do_not_scale_image_data=True` el mapeo funciona y devuelve el dato crudo
    (big-endian), así que el `BSCALE`/`BZERO` se aplica a mano y se convierte a
    float32 nativo.
  - **float32 en los frames, float64 en los acumuladores** de suma (mitad de
    memoria en lo grande, sin error de suma acumulado).
  - La **ROI del barrido se cachea una vez**: primero mmap + page cache del
    sistema, que ya comparte las páginas físicas entre procesos;
    `multiprocessing.shared_memory` solo si el banco de pruebas lo pide. Las
    **franjas quedan para el stack final a frame completo**, donde el conjunto
    de trabajo no cabe; mmap hace barato el leer, no el calcular.
  - **`del` explícito** de los frames de un grupo en cuanto su stack está a
    salvo, con `gc.collect()` por grupo como seguro barato y no como solución
    (los arrays no forman ciclos y el recolector no devuelve memoria
    fragmentada al sistema; lo que protege es acotar el conjunto de trabajo).
- **D26 · Umbral de envío, distinto del de detección.** El 3,5σ (D10) decide
  si hay algo y si se barre; para **enviar** al MPC el listón es **SNR ≥ 20
  por observación** (configurable), que es la recomendación explícita del MPC.
  Por debajo, no se genera el reporte y se explica por qué. Para NEOCP/PCCP,
  además, no se genera por defecto.
- **D27 · Aviso de dithering.** Si el registro muestra que la secuencia no está
  dithered (todos los frames casi en el mismo punto), se avisa: el ruido de
  patrón se apila y fabrica detecciones fantasma, y es la causa número uno que
  documenta el MPC. El aviso es informativo, no bloquea.
- **D28 · La ficha del objeto gana el historial.** Se muestra el **número de
  observaciones** (ya está), el **número de observatorios distintos** que lo
  han visto y la **fecha de la última observación**. Los dos últimos salen del
  nuevo source de MPC (contando `stn` distintos) y de SBDB/NEOfixer
  (`last_obs`). Se explican en la ficha (ADR-058): un objeto visto por muchos
  observatorios y con observación reciente es un objeto vivo y bien
  determinado; uno con un solo observatorio y meses sin verse es un candidato
  a perderse.
- **D29 · El chequeo filtra, no demuestra.** El propio MPC advierte que encajar
  en un ajuste de arco corto **no prueba** una detección. El chequeo de D25 es
  una red, no una garantía, y se dice así en la ficha. Y **si no hay otros
  observadores** (un descubrimiento real), no se bloquea: se avisa de que no
  hay referencia y deciden la secuencia visual (D24) y el umbral de envío
  (D26).

### Disciplina, dependencias y espacio

- **D17 · Validación doble.** El motor se valida con una **secuencia sintética
  de velocidad conocida** (recuperada dentro del 1 %) y la cadena completa con
  una **secuencia real de un asteroide conocido** comparada contra la salida
  de **Tycho-Tracker** del autor (residual < 0,3″, y < 0,1″ en el caso bueno).
- **D18 · Se reabre ADR-004.** scipy y astropy dejan de estar prohibidas en toda
  la app. En la práctica las usan los módulos nuevos: **astropy, scipy y
  photutils** de verdad; ccdproc, reproject y scikit-image/sep quedan
  disponibles pero **solo si aportan**. Los módulos que ya funcionan no se
  migran en este plan (evita romper lo probado y evita un diff gigante).
- **D19 · Siete módulos nuevos.** `core/calibration.py`,
  `core/track_stack.py`, `core/astrometry.py`, `core/findorb.py`,
  `core/findorb_env.py`, `core/mpc_astrometry.py` y `core/sources/mpc_obs.py`,
  con una responsabilidad cada uno. `findorb_env.py` es el instalador guiado
  (patrón de `exotic_env.py`); el chequeo no tiene módulo propio, vive dentro
  de `core/findorb.py`.
- **D20 · Tres ADRs.** ADR-060 (política de dependencias), ADR-061
  (calibración) y ADR-062 (track & stack, astrometría y validación), más la
  reapertura de ADR-004, ADR-018 y ADR-022.
- **D21 · Liberar espacio es una opción, nunca automática.** Tras un run con
  éxito se **ofrece** mover los originales usados a una carpeta `procesados`
  dentro del proyecto (movimiento, no borrado: recuperable), y borrar por
  separado los calibrados exportados. Queda un **manifiesto** del run en la
  base de datos (rutas, tamaño, filtro, exposición) para que la ejecución siga
  siendo auditable aunque el FITS ya no esté en su sitio.

---

## 3. Alcance

| Bloque | Fases | Qué incluye | Si hay que recortar |
|---|---|---|---|
| **Núcleo** | 0–10 | ADRs y dependencias, calibración, ingesta y WCS, apilado y grupos, medida, validación, reporte MPC, GUI, persistencia, liberar espacio, validación real y docs | **No se recorta**: es lo que cierra el bucle de astrometría |
| Fuera del MVP | futuro | Grid search (búsqueda a ciegas) | Hueco previsto en el motor |
| Fuera del MVP | futuro | Migrar los módulos viejos a astropy/scipy | Convivencia documentada |
| Fuera del MVP | futuro | Bias escalado por exposición, mapa de píxeles malos, pesos por frame | Se añaden si el dato los pide |
| Fuera del MVP | futuro | Distorsión interpolada del campo | Solo si el control de calidad de la fase 2 la exige |
| Fuera del MVP | futuro | Reparto por tiempo (en vez de por número de frames) | Se añade si la cadencia es irregular |
| Fuera del MVP | futuro | «Liberar espacio» genérico para cualquier visita | El mecanismo de la fase 9 se diseña reutilizable |
| Fuera del MVP | futuro | Ajuste de órbita propio (Find_Orb dentro de NightScribe) | El chequeo se apoya en la órbita de JPL, no la ajusta |

Orden de recorte si aprieta (del primero al último): liberar espacio (fase 9),
métodos de combinación extra (suma y media), el segundo formato de reporte, el
historial de la ficha (D28), la pestaña de calibración (dejando la calibración
dentro del track & stack).

---

## 4. Arquitectura e integración en NightScribe

### 4.1 Módulos nuevos

| Módulo | Responsabilidad |
|---|---|
| `core/calibration.py` | Biblioteca de masters, matching, receta declarativa, aplicación en memoria y export. |
| `core/track_stack.py` | Ingesta de la visita, solve del primer frame, registro, WCS compuesto, reparto en grupos, cutout, desplazamiento por efeméride, combinación, barrido y detección. |
| `core/astrometry.py` | Centroide (photutils), medida doble por grupo, comparación, magnitud y error propagado. |
| `core/findorb.py` | Handoff a Find_Orb (generar el fichero de observaciones, detectar el binario, lanzarlo headless, parsear residuos y cambio de órbita) y la capa fina de decisión (dispersión robusta, `z`, bloqueo). |
| `core/findorb_env.py` | Instalación guiada de Find_Orb (patrón de `exotic_env.py`): micromamba + conda-forge en Linux/macOS, zips de Project Pluto en Windows, con progreso, cancelación y respaldo manual. |
| `core/mpc_astrometry.py` | Generadores ADES PSV y MPC 80 columnas, validados contra `core/mpc_report.py`. |
| `core/sources/mpc_obs.py` | Observaciones publicadas (MPC) y del NEOCP, con caché: alimenta el chequeo y el historial de la ficha. |
| `gui/ufe_calibration_tab.py` (+ `.ui`) | Pestaña Calibración del Editor FITS unificado. |
| `gui/ufe_trackstack_tab.py` (+ `.ui`) | Pestaña Track & Stack del Editor FITS unificado (grupos, validación y reporte). |

Se enganchan al Editor FITS unificado por su API de extensión
(`gui/ufe_dialog.py::add_feature_tab`, ADR-044 y ADR-053): una funcionalidad
nueva es una pestaña nueva. La pestaña Track & Stack reutiliza el visor de
imagen y el motor de estirado (`gui/ufe_state.py`, `core/stretch.py`) para
mostrar el stack, y el motor de blink (`core/viz/blink_view.py`) para la
secuencia centrada.

### 4.2 Dependencias

`requirements.txt` suma, fijadas:

- **astropy**: FITS con extensiones, WCS con SIP, unidades y tiempo.
- **scipy**: `ndimage` (remuestreo subpíxel), `optimize` (ajustes), `stats`.
- **photutils**: centroides subpíxel, detección, fotometría de apertura.

Quedan disponibles pero **no se añaden salvo necesidad demostrada**: ccdproc,
reproject, scikit-image, sep. La calibración es aritmética simple y el apilado
va sobre la rejilla del frame 0, así que reproject probablemente sobre.

Gotchas que la fase 0 verifica antes de dar la dependencia por buena:

- **PyInstaller**: astropy arrastra datos (tablas IERS, `astropy.cosmology`,
  etc.). Hay que `collect_data_files`/`collect_submodules` y probar el build
  de Windows de preview.
- **IERS**: astropy intenta descargar tablas de tiempo al vuelo. Hay que
  desactivar la descarga automática y decidir si se empaqueta una tabla con
  fecha de corte (misma política que el plan de series, D16).
- **Tamaño**: el instalador crecerá de forma notable; el autor lo acepta.

### 4.3 Base de datos (migraciones aditivas e idempotentes)

Dos saltos, uno por bloque, al estilo de las migraciones existentes en
`core/db.py`, para que cada fase sea autocontenida:

**`user_version` 15 → 16 (fase 1, calibración):**

- `calib_masters(id, camera, gain, temp_c, exptime_s, filter, kind, path,
  created, meta)`, con `kind` en `bias | dark | dark_flat | flat`. Índice por
  la clave de búsqueda (cámara, ganancia, temperatura, exposición, filtro,
  tipo); si hay varios masters para la misma clave, gana el más reciente.

**`user_version` 16 → 17 (fase 8, astrometría):**

- `astrometry_runs(id, project_id, session_id, created, cfg_json, status,
  object_name, method, n_frames, n_obs, rate_arcsec_min, pa_deg, sweep_json,
  dither, snr_gate, submit_snr, detected)`, con `status` en
  `complete | not_detected | incomplete | undone`.
- `astrometry_points(id, run_id, project_id, session_id, group_index, mjd,
  ra, dec, rms_ra, rms_dec, mag, band, x, y, n_frames, snr, mag_limit,
  source, method, flags, check_residual_ra, check_residual_dec,
  check_scatter, check_ok, check_note)`, con `source` en `stack | frames`
  (una fila por vía, mismo `mjd` y `group_index`: así el contraste de D16 es
  una consulta) y `method` en `sum | mean | median | sigma`.
- `astrometry_frames(id, run_id, path, size, filter, exptime_s, date_obs,
  archived, moved_to)`: el manifiesto de la fase 9.

El `session_id` de todas ellas sigue siendo **la visita** (FK a
`project_sessions`), nunca un id de ejecución: `db.py` activa
`PRAGMA foreign_keys = ON` y reusar esa columna rompería el enlace
punto → visita que necesita el multinoche. El `run_id` es la ejecución.

### 4.4 Configuración (`config.py`, `DEFAULTS`)

- `calib_root`: carpeta base de los masters en disco (el índice vive en la
  base de datos).
- `calib_temp_tol_c`: 3,0 (tolerancia de temperatura del matching).
- `calib_export`: False (escribir FITS calibrados a disco).
- `astrometry_snr_sigma`: 3,5 (puerta de detección).
- `astrometry_submit_snr`: 20,0 (listón de envío, recomendación del MPC).
- `astrometry_sweep_pct`: 5,0 y `astrometry_sweep_steps`: 25 (barrido).
- `astrometry_method`: `sigma` (método del stack final).
- `astrometry_cutout_margin_px`: 64 (margen del recorte alrededor de la traza).
- `astrometry_full_frame_final`: True.
- `astrometry_disagree_arcsec`: 0,5 y `astrometry_disagree_sigma`: 3,0
  (contraste de las dos medidas).
- `astrometry_check_enabled`: True (chequeo contra otros observadores).
- `astrometry_check_sigma`: 3,0 y `astrometry_check_floor_arcsec`: 1,0
  (umbral de outlier del chequeo).
- `astrometry_check_window_days`: 30 (ventana de la nube de comparación).
- `findorb_path`: ruta al binario **no interactivo** (`fo` en Linux/macOS,
  `fo64.exe` en Windows); vacío = solo handoff manual.
- `findorb_run`: False (lanzarlo automáticamente; requiere `findorb_path`).
- `astrometry_astcat`: catálogo astrométrico que reporta el solver (Gaia).
- `mpc_obs_ttl_h`: 6 (caducidad de la caché de observaciones del MPC).

### 4.5 Interfaz

- **Pestaña Calibración** (`ufe_calibration_tab`): aplica la receta a la toma
  o a la visita, muestra qué master usa para cada pieza (o avisa de que
  falta), y permite exportar los calibrados.
- **Pestaña Track & Stack** (`ufe_trackstack_tab`): objeto y efeméride, número
  de observaciones (con el SNR previsto de cada grupo), botón de apilar con
  progreso y cancelación, barrido con el score a la vista, elección de método,
  visor del stack por grupo, secuencia centrada (GIF/montaje), medida con el
  contraste de las dos vías, chequeo contra otros observadores, generación del
  reporte y guardado en la visita.
- **Ajustes**: pestaña de biblioteca de masters (alta, listado, borrado), con
  los parámetros del matching.
- **Ficha del objeto** (`gui/widgets/object_hero.py`, panel de objeto y
  `core/orbits.explain_elements`): número de observaciones, **observatorios
  distintos** y **fecha de la última observación** (D28), con su explicación.
- **Ventana de la visita** (`gui/widgets/visits_panel.py`): botón «Astrometría
  de la secuencia» que abre la pestaña; el bloque MPC existente recibe el
  reporte generado y lo pasa por el validador de ADR-022 (ida y vuelta).
- **Workers** (`gui/workers.py`): `CalibrationWorker` y `TrackStackWorker`,
  con señales de progreso, cancelación y sin dejar QThread colgado.
- **Explicaciones** (`core/explain.py`, ADR-058): SNR, residual, magnitud
  límite, método de combinación, observatorios distintos y última observación,
  en dos densidades.

### 4.6 Frontera con lo viejo

Los módulos propios que ya funcionan **no se tocan**: `fits_io`, `wcs`,
`register`, `photometry`, `series_measure`, `mpc_report`. El módulo nuevo
**reutiliza** lo que le sirve y no lo duplica:

- `core/solve.py` y `core/sources/astap.py` para resolver el primer frame.
- `core/ephemeris.py` (`position_at`, `motion_interpolator`) para el
  movimiento; la red va por su caché de `core/db.py`.
- `core/project.py::files_for_session` y `add_file` para leer los frames y
  registrar los productos.
- `core/photometry.py` para la receta de punto cero y magnitud (el centroide
  sí es nuevo, D7).
- `core/compstars.py` para las comparsas de la magnitud.
- `core/mpc_report.py` como validador del reporte generado.
- `core/viz/blink_view.py` para la secuencia centrada (D24).
- `core/orbits.py::explain_elements` y `core/sources/sbdb.py` para el
  historial de la ficha (D28).

Riesgo asumido y documentado: conviven **dos implementaciones de WCS** (la
propia TAN y `astropy.wcs`) y **dos de centroide** (numpy y photutils). Se
acota con tests y con una nota en el ADR-060; la migración de los módulos
viejos queda como plan futuro.

---

## 5. Las 11 fases

Cada fase declara **decisión**, **por qué**, **implementación**, **tests** y
**salida limpia**. Regla transversal: una fase = la app funcionando + suite
unitaria verde + i18n sin `unfinished` si toca cadenas. El detalle vive en el
fichero de cada fase.

| Fase | Entregable | Detalle |
|---|---|---|
| 0 | ADRs, reaperturas, dependencias y spike del build Windows | [`fase-0-adrs-dependencias.md`](fase-0-adrs-dependencias.md) |
| 1 | Calibración y biblioteca de masters (`core/calibration.py`) | [`fase-1-calibracion.md`](fase-1-calibracion.md) |
| 2 | Ingesta, T_mid, solve del primer frame y WCS compuesto | [`fase-2-ingesta-solve-registro.md`](fase-2-ingesta-solve-registro.md) |
| 3 | Reparto en grupos, motor de apilado, barrido y no detección | [`fase-3-apilado.md`](fase-3-apilado.md) |
| 4 | Medida astrométrica doble por grupo, magnitud y errores | [`fase-4-medida-astrometrica.md`](fase-4-medida-astrometrica.md) |
| 5 | Secuencia centrada, chequeo contra otros y ficha del objeto | [`fase-5-validacion-observaciones.md`](fase-5-validacion-observaciones.md) |
| 6 | Generadores ADES PSV y 80 columnas | [`fase-6-reporte-mpc.md`](fase-6-reporte-mpc.md) |
| 7 | Pestañas, workers, Ajustes e i18n | [`fase-7-gui.md`](fase-7-gui.md) |
| 8 | Migración v17, Undo y flujo de proyecto | [`fase-8-persistencia-proyecto.md`](fase-8-persistencia-proyecto.md) |
| 9 | Liberar espacio: `procesados`, manifiesto y restaurar | [`fase-9-liberar-espacio.md`](fase-9-liberar-espacio.md) |
| 10 | Validación real, docs bilingües y cierre | [`fase-10-validacion-docs.md`](fase-10-validacion-docs.md) |

Dependencias entre fases: 1 y 2 son independientes entre sí; 3 depende de 1 y
2; 4 depende de 3; 5 depende de 4, del source `mpc_obs` y de `core/findorb.py`;
6 depende de 4 y 5;
7 depende de 1 a 6; 8 depende de 7; 9 depende de 8; 10 cierra todo.

---

## 6. Checklist de verificaciones de la fase 0

Se cierran **antes** de la fase 1, con binarios y datos reales. Cada una tiene
su fallback decidido (no abren preguntas nuevas):

1. **ASTAP y SIP**: resolver un frame real y comprobar si el WCS trae
   distorsión SIP; verificar que `astropy.wcs` la lee. *Fallback*: WCS TAN
   lineal (el que ya se usa) y anotar la limitación.
2. **Horizons**: `ephemeris.position_at` devuelve rate y PA topocéntricos
   para un NEO de prueba; `motion_interpolator` interpola dentro de la
   secuencia; la caché permite repetir sin red. *Fallback*: usar
   `ephem_minor` con la órbita de SBDB y asumir su precisión menor.
3. **Dependencias en Windows**: instalar astropy, scipy y photutils, y hacer
   un build de PyInstaller de preview que arranque e importe las tres.
   *Fallback*: revisar hooks y `collect_data_files`; si aun así no entra,
   replantear la fase 0 antes de tocar la fase 1.
4. **IERS sin red**: comprobar que el pipeline de tiempo funciona con la
   descarga automática desactivada. *Fallback*: empaquetar tabla con fecha de
   corte documentada.
5. **Dataset real**: el autor aporta la secuencia del asteroide conocido y su
   salida de **Tycho-Tracker**. *Fallback*: validar solo con la secuencia
   sintética hasta que el dato exista, dejando la compuerta real abierta.
6. **Tamaño real**: número de frames, resolución y exposición de esa
   secuencia, para dimensionar el motor (memoria, recorte, franjas).
7. **Ida y vuelta del reporte**: comprobar que `mpc_report.validate` acepta
   un bloque 80 col y un ADES PSV generados a mano con el formato que
   pensamos emitir. *Fallback*: ajustar el formato al validador antes de
   escribir el generador.
8. **Biblioteca de masters**: qué masters tiene ya el autor, con qué nombres
   y metadatos, y si el sensor es CMOS refrigerado. *Fallback*: construir un
   master sintético para los tests y documentar la nomenclatura esperada.
9. **MPC Observations API**: comprobar `get-obs` con un objeto conocido y
   `get-obs-neocp` con un tracklet del NEOCP. *Fallback*: si el NEOCP no
   responde, un objeto no confirmado se queda sin nube de comparación
   (`no_reference`) y se avisa; no se inventa una referencia.
   **Cerrado (2026-10-04), `get-obs`**: es un GET con cuerpo JSON (POST da 405);
   `ADES_DF` trae los campos en minúsculas (`stn`, `obstime`, `rmsra`, `rmsdec`,
   `astcat`); Apophis devuelve 9527 filas, 241 observatorios y última
   2022-04-09; `OBS80` devuelve las líneas de 80 columnas ya formateadas.
   Queda por probar `get-obs-neocp` con un tracklet vivo.
10. **SBDB y NEOfixer**: confirmar qué campos de historial traen
    (`n_obs_used`, `last_obs`, `data_arc`) para no pedir por red lo que ya
    está. *Fallback*: el historial se calcula solo desde el source de MPC.
11. **Find_Orb (`fo`)**: instalar el paquete de conda-forge (`micromamba
    install -c conda-forge findorb`, que trae `fo`, `find_orb` y las
    efemérides `findorb-data-de430t`) y fijar con el binario real: cómo se le
    pasa el fichero de observaciones, cómo se excluyen las nuestras del ajuste,
    que `-D` aísla la configuración y `-r` limita la CPU, y el formato exacto
    de `total.json` (residuos por observación). Comprobar que la primera
    ejecución crea `~/.find_orb` y que las salidas van al directorio de
    trabajo. *Fallback*: si el paquete no cubre la arquitectura, compilar del
    código fuente (los cuatro repos de Bill Gray); si no hay modo headless
    fiable, la capa B queda como handoff manual.
12. **Instalación guiada**: comprobar la descarga de micromamba y la creación
    del entorno privado en Linux/macOS (`micromamba create` + `install -c
    conda-forge findorb`), y los zips de Project Pluto en Windows. Medir el
    **tamaño real** del paquete y de las efemérides DE430t (para avisar antes
    de descargar), y verificar los **hashes** disponibles (el paquete de conda
    los tiene; los zips de Project Pluto no publican checksum, y hay que
    decirlo). *Fallback*: si micromamba no es viable, dejar la instalación
    manual documentada y el botón limitado a detectar el binario.
13. **Memoria con datos reales**: medir el pico de RSS del apilado completo y
    del barrido sobre la secuencia real (checklist 6), y verificar el
    comportamiento de mmap con los ficheros donde los tenga el autor (disco
    local o red). *Fallback*: si mmap sobre red da un rendimiento pobre, leer por
    bloques a un buffer propio en lugar de mapear.
    **Cerrado (2026-10-04), la parte de lectura**: con `BZERO`/`BSCALE`/`BLANK`
    en la cabecera, astropy se niega a mapear (`.data` y `.section` lanzan
    `ValueError: Cannot load a memory-mapped image`); con
    `memmap=True, do_not_scale_image_data=True` funciona y devuelve el dato
    crudo, que hay que escalar a mano. Queda pendiente el pico de RSS y el
    rendimiento sobre red, que necesitan la secuencia real.

---

## 7. Criterios de aceptación

| Criterio | Fase | Aceptación |
|---|---|---|
| **A1** Velocidad sintética | 3 | Una fuente inyectada con velocidad conocida se recupera dentro del 1 % tras el barrido. |
| **A2** Métodos de combinación | 3 | Los cuatro métodos apilan correctamente; el sigma-clipped elimina trazos de estrellas; el resultado en RAM y en streaming coincide. |
| **A3** No detección | 3 | Con solo ruido, la puerta dispara, no hay barrido y se reporta magnitud límite. |
| **A4** Calibración | 1 | Con masters sintéticos, la resta y la división son exactas; sin master, aviso y no excepción. |
| **A5** WCS compuesto | 2 | El WCS compuesto por registro coincide con un solve directo de un frame suelto dentro de la tolerancia del control de calidad. |
| **A6** Medida doble | 4 | Las dos vías coinciden; el flag dispara con una discrepancia inyectada; la magnitud se omite sin comparsas. |
| **A11** Grupos | 3, 4 | Partir la secuencia en N observaciones da N medidas con su T_mid propio; el SNR por grupo baja como `√n`; el número elegido se refleja en el reporte. |
| **A12** Secuencia centrada | 5 | El GIF/montaje muestra el objeto en el centro de cada observación; un grupo sin objeto se ve distinto. |
| **A13** Chequeo | 5 | Con un outlier inyectado, el chequeo bloquea; sin otros en la ventana, avisa y no bloquea; forzar deja constancia; las observaciones de nuestro propio código no entran en la nube; Find_Orb cubre también los no confirmados; sin binario, el handoff deja el fichero y no finge un chequeo. |
| **A14** Ficha del objeto | 5 | La ficha muestra número de observaciones, observatorios distintos y fecha de la última, con su explicación. |
| **A7** Reporte | 6 | El 80 col y el ADES PSV generados validan con `mpc_report.validate` a la ida y a la vuelta; con N observaciones, N líneas. |
| **A15** Umbral de envío | 6 | Un grupo por debajo de SNR 20 no entra en el reporte y se explica; NEOCP/PCCP no se genera por defecto. |
| **A16** Memoria | 3 | El pico de RSS del apilado, sobre el tamaño real del checklist 6, queda por debajo del presupuesto fijado **antes** de medir; el barrido no re-lee la ROI en cada pasada. |
| **A8** Undo | 8 | «Deshacer esta ejecución» borra los puntos del run y no toca otros runs ni los puntos legacy. |
| **A9** Liberar espacio | 9 | Mover y restaurar dejan el registro coherente; un run sin éxito no ofrece nada; el manifiesto sobrevive al movimiento. |
| **A10** Residual real | 10 | La secuencia real da residual < 0,3″ contra Tycho-Tracker (< 0,1″ en el caso bueno). |
| **C1** Suite verde | todas | `pytest tests/unit` verde al cerrar cada fase. |
| **C2** Docs bilingües | 10 | `docs/ASTROMETRY.es.md` y `docs/ASTROMETRY.md`; cada pieza explicada con un ejemplo en ambos idiomas. |
| **C3** Legacy intacto | todas | series, UFE, blink, visitas y el validador MPC siguen verdes. |
| **C4** Honestidad | todas | Errores propagados, avisos en lenguaje llano, ninguna cifra sin su explicación (ADR-058); el chequeo se presenta como filtro, no como prueba (D29). |

---

## 8. Riesgos y mitigaciones

1. **Peso y empaquetado de las dependencias en Windows.** astropy y scipy son
   grandes y traen datos. *Mitigación*: spike del build en la fase 0, no al
   final; si no entra, replantear antes de escribir la fase 1.
2. **El WCS compuesto ignora la distorsión diferencial.** Con 16 MP y SIP del
   solver, la rejilla del frame 0 puede no representar bien los bordes.
   *Mitigación*: control de calidad con solves sueltos (fase 2); si muerde,
   distorsión interpolada como fase extra, sin relajar el objetivo de
   precisión.
3. **Dos implementaciones de WCS y dos de centroide.** Divergencia silenciosa.
   *Mitigación*: ADR-060 lo declara, los tests acotan cada una, y la
   migración de los módulos viejos queda como plan futuro.
4. **Memoria y tiempo del sigma-clipped a frame completo.** Cientos de 16 MP
   no caben. *Mitigación*: diseño por franjas desde la fase 3 y recorte para
   el barrido (D11).
5. **Falsas detecciones por apilado.** Es el problema que el MPC documenta:
   ruido de patrón, SNR bajo, no dither. *Mitigación*: umbral de envío
   (D26), aviso de dithering (D27), secuencia centrada (D24) y chequeo (D25);
   y el aviso de D29 de que el chequeo filtra, no demuestra.
6. **El chequeo depende de Find_Orb y de la API del MPC.** Sin el binario
   configurado o sin respuesta del MPC, el chequeo no corre. *Mitigación*:
   caché, el caso degradado declarado (no se finge un chequeo) y la regla de
   D29 (sin referencia, se avisa y no se bloquea). El fichero de observaciones
   queda escrito para usarlo a mano.
7. **ccdproc y reproject con mantenimiento irregular.** *Mitigación*: no se
   usan salvo que aporten; la calibración es aritmética simple con
   astropy+numpy.
7b. **La instalación guiada descarga binarios.** Riesgo de tamaño, de hashes y
   de licencia. *Mitigación*: no se empaqueta en el instalador (D31); se avisa
   del tamaño antes de descargar, se verifican los hashes disponibles y se
   documenta que los zips de Project Pluto no publican checksum; el respaldo
   manual siempre existe.
7c. **La page cache se atraganta y mmap no rinde.** Con ficheros en red o con
   un conjunto de trabajo mayor que la caché, mmap puede ir más lento que leer
   por bloques. *Mitigación*: la verificación 13 lo mide; el fallback es leer
   por bloques a un buffer propio. Y ojo con el **`memmap` abierto al mover o
   borrar ficheros** (fase 9): en Windows un fichero mapeado no se puede
   renombrar ni borrar, así que la liberación de espacio exige cerrar los
   handles primero.
8. **Designación PCCP en 80 columnas.** El empaquetado puede no ser limpio.
   *Mitigación*: el validador avisa; la designación se empaqueta tal cual
   (D15) y se documenta el caso.
9. **ADR-022 invertida.** El plan hace que NightScribe genere medidas, justo
   lo que el ADR prohíbe. *Mitigación*: reapertura explícita en la fase 0,
   con el alcance acotado (solo objetos conocidos, el usuario revisa y envía).
10. **Datos reales que aún no están.** La validación real depende de que el
    autor aporte la secuencia y su salida de Tycho-Tracker. *Mitigación*:
    fallback del checklist (solo sintética) y compuerta real abierta y
    visible, sin bajar el umbral para que un test pase.

---

## 9. Punto de entrada y siguientes pasos

**Punto de entrada**: `fase-0-adrs-dependencias.md`. Firmar ADR-060, ADR-061 y
ADR-062, reabrir ADR-004, ADR-018 y ADR-022, añadir las dependencias, hacer el
spike del build de Windows y cerrar el checklist de la sección 6. **Nada de
código de producto hasta que eso esté firmado.**

**Después**: fases 1 a 10 en orden. La implementación arranca en una rama de
feature desde `main` una vez los ADRs de la fase 0 estén fusionados; este
documento y sus fases viven en la rama de plan.

**Criterio de éxito final**: el observador abre su visita de un NEO o un PCCP,
calibra las tomas con su biblioteca de masters, reparte la secuencia en las
observaciones que quiere, apila guiando el movimiento con la efeméride, ve el
asteroide en la secuencia centrada, mide su posición por dos vías que se
contrastan, comprueba que su punto encaja con lo que ven otros observatorios,
genera el reporte ADES y 80 columnas, lo valida con el validador de siempre y,
si quiere, libera espacio moviendo los cientos de originales a `procesados`.
Todo sin salir de NightScribe y entendiendo cada cifra que se le enseña.
