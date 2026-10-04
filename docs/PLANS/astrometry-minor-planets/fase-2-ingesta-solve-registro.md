# Fase 2: ingesta, solve del primer frame y WCS compuesto

> Fase del plan maestro [`PLAN.md`](PLAN.md). Decisiones: D8, D13 (T_mid),
> D12 (memoria), y la decisión de la ronda de entrevista sobre el WCS por
> frame.

## Por qué

Para apilar guiando el movimiento hay que saber dos cosas: **cuándo** se tomó
cada frame (para evaluar la efeméride en su instante) y **dónde** está cada
frame en el cielo (para convertir el movimiento angular a píxeles). Resolver
cada uno de los cientos de frames es inviable; resolver el primero y componer
el WCS del resto con el registro estelar es lo rápido y es lo que el CONCEPT
describe. El riesgo es la distorsión diferencial del campo, y por eso esta fase
incluye un control de calidad que resuelve algún frame suelto y compara.

## Implementación

### 2.1 Ingesta de la visita (`core/track_stack.py`)

- `Frame` dataclass: `path`, `header`, `filter`, `exptime_s`, `date_obs`,
  `jd_start`, `mjd`, `t_mid_jd`, `t_mid_mjd`, `wcs` (se rellena después),
  `transform` (se rellena en el registro), `object_ra`, `object_dec`,
  `object_xy`.
- `load_sequence(paths, cfg) -> list[Frame]`: abre cada FITS con
  `astropy.io.fits` (solo la cabecera), y usa `core.fits_meta.meta_from_header`
  para los campos de tiempo (no se duplica el parseo de `DATE-OBS`, `JD`,
  `MJD`). Calcula `t_mid` sumando media exposición:
  `t_mid_jd = jd_start + exptime_s / 172800`, porque el tiempo que representa
  la observación es el centro de la exposición, no su inicio: en un objeto que
  se mueve, usar el inicio sesga la posición en `velocidad · EXPTIME/2`.

Por qué no se usa `core.fits_io` aquí: el módulo nuevo usa astropy (D18), y
astropy maneja extensiones, unidades y cabeceras con más soltura. `fits_io`
sigue siendo el lector de los módulos viejos. La lectura es **mmap** y por
`section` de la ROI (D32), con `memmap=True, do_not_scale_image_data=True`
(astropy se niega a mapear si hay `BZERO`/`BSCALE`/`BLANK`, que es lo habitual
en el uint16 de las CMOS) y el `BSCALE`/`BZERO` aplicado a mano. Aquí, en el
registro, se usa el frame completo (o una versión bineada) porque las estrellas
que votan están por todo el encuadre.

### 2.2 Solve del primer frame

- `solve_reference(frames, cfg, cancel=None) -> Wcs`:
  1. Elige el frame de referencia (por defecto el primero; si tiene poco campo
     estelar, el que más estrellas detecte).
  2. Llama a `core.solve.solve(path, cancel=cancel)` (ASTAP local o nova,
     ADR-051) y obtiene las tarjetas.
  3. Construye un `astropy.wcs.WCS` de esas tarjetas, **con SIP si el solver
     lo trajo** (aquí es donde la reapertura de ADR-004 se nota: el WCS propio
     TAN lo ignoraba).
  4. Si no hay solución, aborta con un mensaje en lenguaje llano: sin WCS no
     hay astrometría.

Nota: el solve trabaja sobre el fichero en disco. La calibración es en memoria
(D6), así que ASTAP ve el frame crudo; es aceptable porque la calibración
apenas mueve las estrellas y el centroide se mide después sobre el stack
calibrado.

### 2.3 Registro de la secuencia

- `register_sequence(frames, ref_index=0, progress=None, cancel=None)
  -> list[Transform]`: reutiliza `core/register.py` para **estimar** la
  transformación de cada frame sobre el de referencia (traslación subpíxel por
  correlación de fase, y rotación rígida solo si el residuo lo pide). No se
  reimplementa la votación por estrellas ni las puertas de confianza: eso ya
  está probado. Un frame cuyo registro no es fiable **hereda** la
  transformación del anterior y se marca; nunca se acepta en silencio.

El **remuestreo** sí es nuevo y usa scipy: `scipy.ndimage.shift` con
interpolación spline (orden 3) para el desplazamiento subpíxel, en vez del
bilineal de `register.apply_transform`. El motivo: un spline de orden 3
preserva mejor la forma del pico de una fuente puntual, y de esa forma sale el
centroide. El bilineal suaviza y sesga ligeramente.

- `compose_wcs(w0, transform) -> Wcs`: compone el WCS de la referencia con la
  transformación medida. Si `transform` lleva el punto de la rejilla de
  referencia a la rejilla del frame (`ref -> src`), entonces el WCS del frame
  es `CRPIX' = T(CRPIX0)` y `CD' = CD0 · R`, donde `R` es la rotación. Se
  documenta la convención con un dibujo en el comentario, porque confundir la
  dirección de la transformación es el error clásico.

- `object_positions(frames, motion) -> None` (rellena cada `Frame`): evalúa la
  efeméride de Horizons en `t_mid_jd` de cada frame
  (`core.ephemeris.motion_interpolator`), obtiene RA/Dec y las convierte a
  píxeles con el WCS compuesto de ese frame (`wcs.sky_to_pixel`). Esas son las
  posiciones que la fase 3 convierte en desplazamientos.

### 2.4 Aviso de dithering (D27)

- `dither_check(frames) -> DitherReport`: mira la dispersión de las
  traslaciones de registro. Si todos los frames caen casi en el mismo punto
  (por debajo de un puñado de píxeles), la secuencia **no está dithered** y se
  avisa: el ruido de patrón se apila y fabrica detecciones fantasma, que es la
  causa número uno que documenta el MPC. Es informativo, no bloquea.

### 2.5 Control de calidad del WCS compuesto

- `verify_composed_wcs(frames, sample=2, tol_arcsec=0.3, cancel=None)
  -> QCReport`: resuelve directamente uno o dos frames (además del de
  referencia) y compara, para un puñado de estrellas, la posición que predice
  el WCS compuesto con la que da el solve directo. Si la discrepancia supera
  la tolerancia en los bordes, se avisa: es la señal de que la distorsión
  diferencial muerde. No bloquea, pero el aviso va a la ficha (y es la puerta
  que decidiría una fase extra de distorsión interpolada).

## Tests

`tests/unit/test_track_stack_ingest.py`:

- **T_mid**: con `DATE-OBS` y `EXPTIME` conocidos, `t_mid` cae exactamente a
  media exposición; con cabeceras con `JD`/`MJD` en vez de `DATE-OBS` también.
- **Solve**: con un WCS simulado en la cabecera, `solve_reference` lo lee sin
  red; con tarjetas SIP, `astropy.wcs` las conserva.
- **Registro**: con frames sintéticos desplazados una cantidad conocida, la
  transformación recuperada coincide; un frame ilegible hereda la anterior y
  se marca.
- **Compuesto**: la posición de cielo que predice el WCS compuesto de un frame
  sintético coincide con la del WCS conocido del frame; se prueba con rotación
  y con traslación solas.
- **Posiciones del objeto**: con un interpolador lineal de prueba, `object_xy`
  cae donde debe en la rejilla.
- **Dithering**: una secuencia sintética sin desplazamiento dispara el aviso;
  una con dither, no.

## Salida limpia

La secuencia de una visita se lee, se resuelve el primer frame, se registra el
resto y cada frame conoce su WCS, su transformación y la posición efemérica de
su instante. El control de calidad dice si el WCS compuesto es de fiar y si la
secuencia está dithered.

## Hecho cuando

La suite unitaria está verde y el control de calidad de un set real (checklist
1 de la fase 0) da un residual dentro de la tolerancia, o queda documentado el
aviso de distorsión.
