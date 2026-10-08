# Fase 5: validación de las observaciones y ficha del objeto

> Fase del plan maestro [`PLAN.md`](PLAN.md). Decisiones: D24, D25, D28, D29,
> D30, D31 y el hallazgo del MPC sobre falsas detecciones.

## Por qué

El MPC documenta que el apilado (synthetic tracking) produce detecciones
fantasma, que el ruido de patrón se apila si no hay dither, y que un tracklet
falso en el NEOCP **puede perder el objeto**. La respuesta no es apilar mejor,
es **verificar antes de enviar**. Esta fase construye las dos verificaciones
que el autor pidió: ver el objeto en cada observación y comprobar que nuestro
punto encaja con lo que ven los demás. Y de paso, el mismo source de MPC
alimenta la ficha del objeto con el número de observatorios distintos y la
fecha de su última observación.

## La idea de fondo: no reimplementar el ajuste de órbitas

El chequeo «¿es buena nuestra medida?» es, en el fondo, un *leave-one-out*:
ajustar la órbita **sin** nuestras observaciones y ver qué residual tienen las
nuestras. Eso ya lo hace Find_Orb, con perturbaciones y ponderación, y está
probado por toda la comunidad. **NightScribe no reimplementa ese ajuste**: le
pasa las observaciones y lee sus residuos. Lo único nuestro es bajar las
observaciones de los demás (que hace falta igual para la ficha, D28), escribir
el fichero y decidir sobre los residuos que Find_Orb devuelve.

Esto cubre los dos casos con el mismo camino: objetos con órbita y objetos del
NEOCP/PCCP (Find_Orb ajusta también arcos cortos y tracklets). No hacen falta
un chequeo out-of-sample propio ni un tracklet propio.

El matiz que hace honesto el veredicto: **no se compara contra cero, se compara
contra la nube de los demás**. Si el ajuste es malo (arco corto), todos los
residuos son grandes; nuestro punto puede ser bueno y tener un residual grande.
El veredicto sale de si estamos **fuera de la dispersión de los demás**.

## Implementación

### 5.1 Source `core/sources/mpc_obs.py`

Red solo por `core/db.py`, caché con TTL `mpc_obs_ttl_h` (6 h). Dos endpoints
del MPC (verificados en el checklist de la fase 0):

- `observations(desig, fmt="ades", force=False) -> list[Obs]`: `GET
  https://data.minorplanetcenter.net/api/get-obs` con
  `{"desigs": [desig], "output_format": ["ADES_DF"]}`. **Verificado el
  2026-10-04**: es un **GET con cuerpo JSON** (un POST responde 405), y los
  campos de `ADES_DF` vienen en **minúsculas**, no en camelCase como el ejemplo
  XML: `stn`, `obstime`, `ra`, `dec`, `rmsra`, `rmsdec`, `mag`, `band`,
  `astcat`, `ref`, `mode`. `rmsra`/`rmsdec` pueden faltar (en Apophis solo 2013
  de 9527 filas los traen) y hay que tratarlos como opcionales. El volumen es
  grande (Apophis: 9527 filas, 241 observatorios, última 2022-04-09), así que la
  ventana de ±30 días del chequeo es también un filtro de tamaño.
- `neocp_observations(trksub, force=False) -> list[Obs]`: `GET
  https://data.minorplanetcenter.net/api/get-obs-neocp` con
  `{"trksubs": [trksub], ...}`, para objetos **no confirmados** (PCCP/NEOCP).
- `observations_80(desig, force=False) -> str`: el mismo endpoint con
  `"output_format": ["OBS80"]`, que devuelve las líneas de 80 columnas ya
  formateadas (verificado), listas para concatenar con las nuestras en el
  fichero de Find_Orb.
- `history(desig, force=False) -> History`: cuenta las observaciones, los
  **observatorios distintos** (`len({o.stn})`) y la **fecha de la última**
  (`max(o.obstime)`). Alimenta la ficha (D28).

`Obs` es un dataclass normalizado (`stn`, `mjd`, `ra`, `dec`, `rms_ra`,
`rms_dec`, `mag`, `band`, `astcat`, `ref`). El parseo se prueba con fixtures en
`tests/fixtures/`, nunca contra la red en unitarios.

### 5.2 `core/findorb.py`: handoff y decisión

Mismo patrón que el handoff de EXOTIC (ADR-052) y que ASTAP (ADR-051). Se usa
el ejecutable **no interactivo** `fo` (no el `find_orb` interactivo).

**Handoff.**

- `write_input(ours, others, path, fmt="psv")`: genera el fichero de
  observaciones con las nuestras (de `core/mpc_astrometry.py`) y las de los
  demás (`mpc_obs.observations_80`). **Todas** las de los demás entran: cuantos
  más datos, mejor la órbita con la que se nos predice (D30). `fo` acepta PSV
  ADES, 80 columnas, XML ADES o mezcla.
- `resolve_binary(findorb_path=None) -> Path | None` y `probe()`: detecta el
  binario configurado en `findorb_path` (que apunta a `fo` / `fo64.exe`) y
  comprueba que **no** es el interactivo `find_orb`.
- `run(input_path, cancel=None, timeout=...)`: lo lanza headless **en un
  directorio temporal** (porque `fo` escribe sus salidas en el directorio de
  trabajo actual), con log fusionado y cancelación, como `core/exotic_run.py`,
  **excluyendo nuestras observaciones del ajuste** (el leave-one-out de
  verdad). Dos opciones que se usan siempre:
  - `-D <environ>`: un fichero de entorno propio, para que el resultado no
    dependa de la configuración del usuario en `~/.find_orb`.
  - `-r 60,65`: límite blando y duro de CPU, para que un ajuste atascado no
    cuelgue la app.
  Los flags exactos se verifican en el checklist de la fase 0, no se suponen.
- `parse_output(tmpdir) -> FindOrbReport`: lee **`total.json`**, donde `fo`
  escribe elementos, observaciones y **residuos por observación**, más
  `elements.txt` si hace falta. Nada de raspar texto.
- Sin binario: escribe el fichero y devuelve `handoff_only=True`; el usuario lo
  abre a mano (en la GUI, o en el `find_orb` interactivo).

Nota de instalación (documentada en `doc-findorb.es.md` / `doc-findorb.md`):
en Linux/macOS hay binarios listos con `conda install -c conda-forge findorb`
(instala `fo`, `find_orb` y las efemérides `findorb-data-de430t`); en Windows,
el `fo64.exe` de Project Pluto junto a la consola. `fo` crea `~/.find_orb` la
primera vez que corre: es normal y no se toca (por eso se usa `-D`).

**Decisión** (capa fina, en el mismo módulo).

- `scatter(others_residuals) -> (rms_ra, rms_dec, n)`: dispersión **robusta**
  (MAD, no desviación típica) de los residuos de los demás, tomando solo los
  que caen **dentro de `astrometry_check_window_days` (±30 días)** y
  **excluyendo nuestro propio `mpc_code`** (si no, compararíamos nuestra medida
  con la nuestra).
- `decide(report, our_rms, cfg) -> CheckReport`: normaliza
  `z = residual / sqrt(rms_nuestro² + scatter²)` con el rmsRA/rmsDec de la fase
  4 (D30); si `|z| > astrometry_check_sigma` (3) **y** supera el suelo
  `astrometry_check_floor_arcsec` (1″), marca `outlier` y `blocked=True`
  (D25). Sin nadie en la ventana, `no_reference`, `blocked=False`, con aviso
  (D29). `CheckReport`: `our_residual`, `scatter`, `z`, `n_others`,
  `n_stations`, `outlier`, `blocked`, `note`.
- `check(point, observations, cfg) -> CheckReport`: junta las dos piezas (es lo
  que llama la fase 6 antes de generar el reporte).

### 5.3 Instalación guiada de Find_Orb (`core/findorb_env.py`, D31)

Mismo patrón que `core/exotic_env.py` (ADR-052), que ya prepara un entorno
privado de EXOTIC desde Ajustes. **No se empaqueta en el instalador** (D31):
Find_Orb es GPLv2 con una cláusula extra de uso comercial que no encaja en una
app GPLv3, y sus efemérides DE430t pesan.

- `probe() -> dict`: detecta si hay un `fo` utilizable (propio, del sistema o
  configurado) y devuelve su ruta y su versión.
- `prepare(install_dir, progress=None, cancel=None) -> (ok, log)`:
  - **Linux/macOS**: descarga **micromamba** al directorio de datos de la app
    (`paths.data_dir() / "findorb"`), crea un entorno privado y
    `micromamba install -c conda-forge findorb`; `fo` queda en
    `<env>/bin/fo`. Se usa micromamba y no el conda del sistema para que el
    resultado no dependa del entorno del usuario.
  - **Windows**: descarga `find_c64.zip` y `fo64.exe` de Project Pluto al
    directorio de datos y descomprime; `fo` queda en `fo64.exe`.
- `fo_path(install_dir) -> Path`: la ruta del `fo` instalado, para rellenar
  `findorb_path` al terminar.
- Avisa del **tamaño** antes de descargar y verifica los **hashes**
  disponibles (el paquete de conda los tiene; los zips de Project Pluto no
  publican checksum, y se dice).
- **Respaldo manual** siempre: si el usuario ya tiene Find_Orb, apunta al
  binario y el instalador no hace nada.
- Nota de regla: el instalador lanza un subproceso (`micromamba`) que usa la
  red, como `exotic_env` con `pip`; la regla «toda red por `core/db.py`» es
  para las consultas de API, no para un instalador. Se escribe en el ADR.

### 5.4 Caso degradado: sin Find_Orb

Si `findorb_path` está vacío o el binario no responde, **el chequeo no está
disponible** y se dice en lenguaje llano: no se finge un chequeo. La red de
seguridad son la secuencia centrada (5.5) y el umbral de envío (fase 6). El
usuario puede **instalarlo guiado** desde Ajustes (5.3) o apuntar a un binario
propio, y reintentar; mientras tanto, el fichero de observaciones queda escrito
para que lo use a mano.

### 5.5 Secuencia de validación centrada (D24)

- `core/viz/blink_view.py`: nueva `centered_sequence(stacks, q_list, out,
  fmt="gif")` que recorta cada observación alrededor de su `q_g`, aplica el
  mismo estirado (`core/stretch.py`) y monta un **GIF o un montaje PNG** con
  las N observaciones, el objeto siempre en el centro. Si el objeto está en
  todas, la detección es sólida; si en alguna no, se ve.
- Se registra en la visita como `project_files` con `kind="motion_gif"` (ya
  existe en `visits_panel._kind_label`).

### 5.6 Ficha del objeto (D28)

- `core/sources/sbdb.py::parse_sbdb`: añadir al dict normalizado `n_obs_used`,
  `last_obs` y `data_arc` (SBDB los trae en el bloque `orbit`), sin romper los
  campos actuales.
- `core/orbits.py::explain_elements`: además de `n_resids` y `arc_days`, añadir
  **observatorios distintos** y **fecha de la última observación**, con su
  explicación (ADR-058):
  - muchos observatorios y observación reciente: objeto vivo y bien
    determinado;
  - un solo observatorio y meses sin verse: candidato a perderse.
- `gui/widgets/object_hero.py` y el panel de objeto: pintar las tres cifras con
  su tooltip (densidad `short` de `core/explain.py`). Sin red, se muestran las
  que ya estén en caché y se dice que el historial no está actualizado.

## Tests

`tests/unit/test_mpc_obs.py`:

- Parseo de `ADES_DF` y de `OBS80` contra fixtures; `history` cuenta
  observaciones, `stn` distintos y la última fecha.
- Caché: la segunda llamada no toca la red; el TTL caduca.
- Sin red o sin objeto: devuelve vacío sin excepción.

`tests/unit/test_findorb.py`:

- **A13, outlier**: con un binario falso que escribe una salida de ejemplo con
  nuestros residuos dentro de la nube, no bloquea; con nuestros residuos a 5σ,
  bloquea; forzar deja la nota.
- **A13, sin referencia**: sin nadie en la ventana, `no_reference` y no
  bloquea.
- **Exclusión propia**: las observaciones de nuestro código de observatorio no
  entran en la nube.
- **Ventana**: una observación de los demás fuera de ±30 días no cuenta para la
  dispersión.
- **Robustez**: un observador malo aislado no infla la dispersión (MAD).
- **Normalización**: el mismo residual bloquea menos cuando nuestra rms es
  grande (D30).
- **Handoff**: sin binario, el fichero se escribe y `handoff_only` es True; con
  un `fo` falso que escribe un `total.json` de ejemplo en el directorio de
  trabajo, el parseo extrae residuos y, si está, el cambio de órbita; se
  comprueba que se lanza en un temporal y con `-D` y `-r`.
- **No es el interactivo**: si `findorb_path` apunta a `find_orb`, `probe`
  avisa y el chequeo queda no disponible.
- **Caso degradado**: sin Find_Orb, `check` devuelve `available=False` y no
  bloquea.

Prueba de integración real (marcada como funcional, con el binario instalado):
`micromamba install -c conda-forge findorb` en CI y correr `fo` sobre un PSV
de ejemplo, comprobando que `total.json` sale y que el parseo lo entiende.

`tests/unit/test_findorb_env.py`:

- `probe` detecta un `fo` falso y devuelve su ruta; sin binario, devuelve vacío.
- `prepare` con una descarga simulada (micromamba falso) crea la estructura del
  entorno y `fo_path` apunta al `fo`; con `cancel`, aborta sin dejar a medias.
- El respaldo manual: con `findorb_path` ya configurado, `prepare` no descarga.
- Aviso de tamaño y verificación de hash (con un hash falso que no cuadra, no
  se instala).

`tests/unit/test_object_history.py`:

- `explain_elements` incluye las tres cifras con su explicación en ES y EN.
- La ficha degrada con gracia sin red.

## Salida limpia

Antes de generar el reporte, el usuario ve la secuencia centrada con las N
observaciones y el veredicto de Find_Orb sobre su punto (o el aviso de que el
chequeo no está disponible). La ficha del objeto muestra observaciones,
observatorios distintos y última fecha. La GUI todavía no lo expone (fase 7).

## Hecho cuando

A13 pasa en sus casos (outlier, sin referencia, exclusión propia, ventana), la
secuencia centrada muestra el objeto en cada observación de un set sintético,
el handoff produce informe con y sin binario, la instalación guiada deja un
`fo` usable (o se declara no disponible), y la ficha pinta las tres cifras del
historial con su explicación.
