# Fase 4: medida astrométrica por grupo, magnitud y errores

> Fase del plan maestro [`PLAN.md`](PLAN.md). Decisiones: D7, D13, D16, D22,
> D23 y la reutilización de la receta de punto cero de `core/photometry.py`.

## Por qué

Un stack bonito no es una medida. Aquí se convierte el pico de luz de cada
observación en una posición con su incertidumbre, por dos vías que se
contrastan, y se decide si la magnitud se puede dar o no. El error importa
tanto como la posición: un reporte al MPC sin incertidumbre es una medida a
medias, y una incertidumbre inventada es peor que ninguna.

## Implementación

### 4.1 Centroide (`core/astrometry.py`)

El **mismo** centroide se usa para el stack y para cada frame (D7). Si cada vía
usara un método distinto, su comparación no diría nada.

- `centroid(data, xy, fwhm, cfg) -> CentroidResult`: usa `photutils`
  (`centroid_2dg` como método por defecto, con `centroid_com` disponible), con
  una ventana derivada del FWHM y una resta de cielo local antes de centrar
  (un gradiente de cielo desplaza un centro de masas; el `2dg` lo tolera
  mejor, y por eso es el default). `CentroidResult` lleva `x`, `y`, `fwhm`,
  `snr`, `roundness` (`b/a` de los segundos momentos) y `err_pix`.
- El **FWHM** sale de `photutils` o de la estimación de la propia imagen; se
  documenta cuál, porque la apertura depende de él.

### 4.2 Las dos vías, por grupo

Cada grupo tiene su stack (en su `q_g`, sobre la rejilla de referencia) y su
`T_mid` (fase 3). La medida se hace grupo a grupo:

- `measure_stack(stack_g, q_g, wcs0, cfg) -> AstrometryPoint`: mide en `q_g`
  sobre el stack del grupo y convierte a cielo con `wcs0`. El `mjd` del punto
  es el `T_mid` del grupo.
- `measure_frames(group, offsets, cfg) -> AstrometryPoint`: mide el objeto en
  cada frame del grupo (sobre el recorte desplazado, en `q_g`, o en su posición
  nativa `p_i`), convierte cada posición a cielo con el WCS **de ese frame** y
  combina las posiciones en una sola.

La combinación por frame es una **media ponderada por 1/σ²**, con la RA
ponderada por `cos(dec)` (un segundo de arco de RA no es un segundo de arco de
cielo). El error de la media es el de la media, no el de un punto: dividir por
`√N` es lo que hace que medir por frame aporte. Pero la dispersión observada
puede ser mayor que la predicha por el ruido (deriva, centelleo); en ese caso
se toma **la mayor de las dos** como incertidumbre, porque una barra de error
que se cree mejor de lo que es engaña.

- `combine_positions(points) -> (ra, dec, rms_ra, rms_dec, scatter)`.
- `measure_groups(stacks, groups, cfg, progress=None, cancel=None)
  -> list[GroupMeasurement]`: recorre los grupos y devuelve, por grupo, las dos
  vías y su contraste.

### 4.3 Contraste de las dos vías (D16)

- `compare(stack_point, frames_point, cfg) -> list[str]` (flags):
  - Si `|Δ| > astrometry_disagree_arcsec` (0,5″) **o** `|Δ| > astrometry_disagree_sigma`
    (3σ), el punto del stack se marca con el flag `disagree` y la ficha lo
    avisa en lenguaje llano. No se elige una vía en silencio: el usuario ve
    las dos y decide (o investiga).
- La posición **reportada** por defecto es la del stack (la convención de la
  astrometría profesional); el run guarda `report_source` en su `cfg_json` y
  el usuario puede cambiarla. Las dos vías se guardan como dos filas de
  `astrometry_points` con el mismo `mjd`, el mismo `group_index` y distinto
  `source`.

### 4.4 Magnitud

- `measure_magnitude(stack_g, q_g, wcs0, cfg) -> (mag, band, n_comps) | None`:
  reutiliza la receta de punto cero y magnitud de `core/photometry.py`
  (`calibrate_zero_point`, `calibrated_mag`) y las comparsas de
  `core/compstars.py`. **No se duplica** el conocimiento fotométrico; lo nuevo
  es solo el centroide (photutils).
- Si no hay comparsas suficientes para atar el punto cero, **se omite la
  magnitud** (D13): es mejor un reporte sin magnitud que una magnitud
  inventada. Se dice en la ficha por qué falta.
- La magnitud se calcula por grupo (cada observación tiene su propio stack) y
  se anota también el SNR, que es el que decide el listón de envío (D26).

### 4.5 Incertidumbre astrométrica (D13)

- `error_budget(...) -> (rms_ra, rms_dec, parts)`: suma en cuadratura las
  fuentes de error y guarda el desglose para poder explicarlo:
  - **Centroide**: `err_pix` convertido a segundos de arco con la escala de
    placa. En RA, dividido por `cos(dec)`.
  - **WCS**: el rms del solver, o el residual del control de calidad de la
    fase 2 si es mayor.
  - **Tiempo**: `velocidad · σ_t`, con `σ_t` la incertidumbre del instante
    (pequeña, pero no nula; se documenta de dónde sale).
  - En la vía por frame, el término del centroide se divide por `√N`.

`rms_ra` y `rms_dec` son las cifras que van al ADES. El panel muestra el
desglose, porque una cifra sin su porqué no enseña nada (ADR-058).

## Tests

`tests/unit/test_astrometry.py`:

- **A6, doble medida**: con un stack sintético y sus frames, las dos vías
  coinciden dentro de la tolerancia; se inyecta una discrepancia (desplazando
  la posición del stack) y el flag `disagree` dispara.
- **A11, por grupo**: tres grupos sintéticos dan tres pares de puntos con su
  `T_mid` y su `q_g` propios; el `mjd` de cada punto es el del grupo, no el de
  la secuencia.
- **Centroide**: un pico gaussiano sintético se recupera a nivel subpíxel; un
  gradiente de cielo no desplaza el `2dg`; el `err_pix` crece con el ruido.
- **Combinación**: con N frames de ruido conocido, el error de la media baja
  como `√N`; con dispersión inyectada mayor que la predicha, se reporta la
  dispersión.
- **RA/Dec**: la división por `cos(dec)` se comprueba con un punto a dec alta.
- **Magnitud**: con comparsas, la magnitud calibrada coincide con la esperada;
  sin comparsas, se devuelve `None` y la ficha lo dice.
- **Error total ≥ interno** siempre (coherente con la regla de las series).

## Salida limpia

El módulo mide una posición por grupo y por las dos vías, las contrasta,
calcula la magnitud si puede y devuelve rmsRA/rmsDec con su desglose. La GUI
todavía no lo expone.

## Resultado (2026-10-04)

Implementado `core/astrometry.py` (rama `feature/astrometry-minor-planets`):

- `centroid`: centroide subpíxel con `photutils` (`centroid_2dg`) sobre una
  ventana con cielo local restado; devuelve error en píxeles, FWHM, redondez y
  SNR. Rechaza una fuente pegada al borde de la ventana.
- `measure_stack` / `measure_frames`: las dos vías, con el **mismo** centroide
  (D7). La de frames combina con pesos 1/σ² y la RA ponderada por `cos(dec)`.
- `combine_positions`: media ponderada con el desenrollado de la RA alrededor
  de la media (para no romper en el salto 0/360) y la dispersión observada.
- `compare`: el contraste de D16 (flag `disagree` si superan 0,5″ o 3σ).
- `error_budget`: centroide + WCS + tiempo en cuadratura, con el desglose; la
  RA dividida por `cos(dec)` (un píxel de RA no es un segundo de arco).
- `measure_magnitude`: reutiliza la receta de punto cero de `core/photometry.py`;
  sin comparsas ni punto cero devuelve `None` (se omite, no se inventa).

Tests: `tests/unit/test_astrometry.py` (12), offline. El ancla del centroide es
subpíxel (0,15 px) y el error crece con el ruido.

## Hecho cuando

A6 y A11 pasan, el error total nunca es menor que sus partes, y la magnitud se
omite sin comparsas en vez de inventarse.
