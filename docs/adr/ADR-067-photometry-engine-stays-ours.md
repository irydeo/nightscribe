# ADR-067: El motor de fotometría se queda el nuestro (medido, no intuido)

**Estado / Status**: Accepted · **Fecha / Date**: 2026-10-07

## Español

**Contexto**: ADR-060 §3 dejó abierta la migración de los módulos viejos
(`fits_io`, `wcs`, `register`, `photometry`, `series_measure`) como «plan
futuro», y con una razón de peso: menos código numérico que mantener nosotros.
La duda concreta que la reabrió fue otra: las series fotométricas muy débiles,
las de los exoplanetas, están al límite, y la pregunta honesta era si un motor
apoyado en `astropy`/`scipy`/`photutils` mediría **mejor**.

Antes de tocar nada se fijaron los criterios, y esa es la parte que hace que
esta decisión valga:

1. **No hacer daño**: ningún conjunto de datos puede empeorar más de un 5 % en
   la dispersión de la curva.
2. **Ganar por velocidad**: el tiempo por fotograma baja 3× o más.
3. **Ganar por precisión**: la dispersión mejora un 10 % relativo o más en al
   menos 3 de 4 conjuntos, sin sesgo nuevo.

**Decisión**: **no se migra**. Los criterios 2 y 3 no se cumplen, y el 1 sí,
así que la respuesta es que el motor propio se queda, con los números delante.

### Lo que se midió

El banco vive en `tools/bench/` (no lo importa la app, no se envía con ella) y
trabaja sobre el corpus local: 2025 FG18 (207 fotogramas), 2025 HL5 (98), 2025
UR (140), 2026 PY9 (247), el tránsito real de Hat-P-32 b (142) y la inyección
de fuentes de flujo conocido.

**Medida individual (inyección y recuperación, 5 conjuntos, 240 medidas por
punto).** La tabla es la dispersión dividida por el suelo de ruido real de la
placa; 1,000 es el límite de la apertura:

| motor | SNR 3 | SNR 10 | SNR 30 | SNR 100 |
|---|---|---|---|---|
| el nuestro | 1,027 | 1,010 | 1,041 | 1,025 |
| photutils | 0,991 | 1,016 | 1,017 | 1,038 |

Todos los motores llegan al suelo dentro del 1 al 6 %, y la diferencia entre
ellos es del ~2 %, por debajo del error estándar. El estimador del cielo da
**el mismo número** en los dos (1551,8966 ADU de media, misma desviación,
sesgo −0,10 ADU), y la aritmética de apertura coincide a ±300 ppm. En un
control sintético con verdad conocida (600 pruebas, clics deterministas)
ningún centroide se distingue de otro a SNR 2,3, 23 ni 77. Lo único donde
photutils gana con claridad es la **posición** del centroide (1,5 a 4,6 veces
mejor), y no se traduce en mejor flujo.

**Serie real (mismos fotogramas, mismas comparsas, mismas aperturas, misma
alineación: sólo cambia la medida de una estrella en un fotograma).**

| conjunto | fotogramas | el nuestro (ms/f) | photutils (ms/f) | velocidad | dispersión nuestra | dispersión photutils | mejora |
|---|---|---|---|---|---|---|---|
| 2025 FG18 | 207 | 700,7 | 469,5 | 1,49× | 65,61 | 59,23 | +9,7 % |
| 2025 HL5 | 98 | 567,2 | 404,0 | 1,40× | 20,66 | 20,28 | +1,8 % |
| 2025 UR | 140 | 488,5 | 377,3 | 1,29× | 111,09 | 110,09 | +0,9 % |
| 2026 PY9 | 247 | 582,3 | 408,3 | 1,43× | 25,44 | 25,54 | −0,4 % |
| Hat-P-32 b | 142 | 226,9 | 130,1 | 1,74× | 23,67 | 23,07 | +2,5 % |

Mediana: **+1,8 % de precisión y 1,43× de velocidad**. Todo el efecto, cuando
lo hay, está en el centroide: cambiar sólo la aritmética deja el resultado
idéntico al ppm. Y el caso que más se acerca al umbral (FG18, +9,7 %) no se
reproduce en el control sintético, así que viene de cómo se comporta el
centroide en condiciones reales y no del estimador.

> La columna de velocidad es la del momento de la decisión. Las mejoras de los
> puntos 2 y 3 (más abajo) dejaron después al motor propio entre 1,2 y 1,5×
> más rápido, y movieron un poco la precisión: FG18 64,49 contra 53,68 de
> photutils, HL5 20,67 contra 20,13, UR 110,86 contra 109,13, PY9 24,91 contra
> 25,10 y HatP32 22,48 contra 22,59. La brecha de FG18 se ensancha porque el
> ajuste 2D de photutils saca más partido todavía de un FWHM sensato, y eso es
> un motivo para mirar **nuestro** centroide, no para migrar. El criterio sigue
> sin cumplirse: 1 de 4 conjuntos por encima del 10 %.

**El ruido de las series del autor no lo pone el motor.** Medido en 2025 FG18:
una pareja de estrellas a 6′ da 19,1 mmag de dispersión diferencial y a 30′ da
38,5 mmag. Esa dependencia con la separación es la firma de ruido
espacialmente correlacionado, y el propio modelo de centelleo de la app
predice 131 mmag para 0,43 m y 1 s. Ningún motor arregla eso; lo arregla
exponer más tiempo.

### Cuánto código se ahorraría (y por qué no basta)

Código real, sin comentarios ni docstrings:

| bloque de `photometry.py` | líneas reales |
|---|---|
| reemplazable por photutils | 725 (54 %) |
| parcial (las guardas se quedan) | 112 |
| nuestro, sin equivalente | 384 |

La versión photutils del **mismo núcleo de medida** (centroide, apertura,
cielo y guardas) que se escribió para el banco son 146 líneas reales contra
410 de las nuestras. Pero:

* `series_measure.py` tiene 1296 líneas reales y sólo **52 (4 %)** tienen
  equivalente: el motor de serie (ensemble, cero punto por fotograma, detrend,
  puertas) es nuestro y sigue siendo nuestro;
* ADR-058 obliga a explicar, y el 44 % de nuestras líneas son explicación, así
  que el ahorro en el editor es la mitad del ahorro en código;
* los tests que fijan el comportamiento numérico hay que reescribirlos (38 de
  3075 llaman directamente a una función reemplazable, y son justo los que
  fijan nuestra aritmética);
* las guardas se quedan: techos de ADR-066, motivos bilingües, desmezclado y
  tope de núcleo no los cubre photutils;
* la API se mueve (photutils 3.0 acaba de quitar los alias de nivel superior).

Ahorro neto realista: **de 250 a 450 líneas**, del 15 al 25 % de
`photometry.py`, que es el **0,5 al 0,8 % del código de la app**, y cero en la
serie.

### Lo que la medida encontró por el camino

El estudio valió más por lo que encontró que por lo que decidió, y las cuatro
cosas están arregladas o medidas:

1. **Un fallo real**: `measure_matched` devolvía `ok=True` con flujo negativo
   (medido en 2025 FG18, fotograma 15, objetivo T18: −845,6 ADU y snr −0,97) y
   la receta tomaba el logaritmo de ese número, matando la corrida entera de
   207 fotogramas con «math domain error». Alcanzable desde la serie normal de
   la GUI (que corre con el filtro adaptado) y desde la pestaña Medir. Un
   solo sitio lo arregla, y ahora **una medida es un flujo positivo**.
2. **El FWHM se autoestimaba por estrella**: de 3,2 a 11,0 px donde la sesión
   tenía 4,64, y movía el centroide hasta 0,28 px. El fotograma lo mide una
   vez, sobre las comparsas (que son las mismas en un pase y en una corrida
   suelta, o la paridad del pase se rompe), y lo comparte. Medido en los cinco
   conjuntos: **1,7 % de mediana de mejora en la dispersión** (FG18 −1,7 %,
   HL5 0 %, UR −0,2 %, PY9 −2,1 %, HatP32 −5,0 %) y entre **1,2 y 1,5× de
   velocidad**, porque medir el seeing una vez por fotograma sustituye una
   estimación por estrella. El primer intento lo medía sobre los objetivos
   además de las comparsas, y rompió la paridad del pase (un pase de dos
   objetos daba una curva distinta a la del mismo objeto medido solo): lo cazó
   el test que existe para eso.
3. **El desmezclado costaba 3,20 ms por medida (1,52×)** porque `local_sources`
   recorría el recorte píxel a píxel en Python (1369 iteraciones en la ventana
   de 45 px, para no encontrar nada en ruido). Vectorizado, con resultado
   idéntico (verificado en 1050 comparaciones: ruido, estrellas, gradientes,
   mesetas y recortes reales), cuesta **0,35 ms (1,06×)** y compra lo mismo:
   con un vecino a menos de 1,5 FWHM, de 15 a 60 % menos dispersión de flujo y
   hasta 3,5× menos error de posición. La pregunta «40 % del tiempo por 1 % de
   dispersión» deja de tener sentido: ahora cuesta un 6 %.
4. **El error declarado es de 5 a 20 veces la dispersión real** (FG18: 287 mmag
   declarados frente a 58 medidos). Es conservador por diseño, pero queda
   anotado.

**Consecuencias**: `photometry.py` y `series_measure.py` **no se migran**, y
ADR-060 §3 queda cerrado para ellos: la convivencia con las bibliotecas sigue
abierta para **capacidades nuevas** (fotometría PSF, `Background2D`), y con la
misma condición que este estudio: entra lo que trae una ganancia medida, no lo
que suena bien. El banco se conserva en `tools/bench/` para poder repetir la
medida si el régimen cambia (otra cámara, otro cielo, otra versión de
photutils), y no se envía con la aplicación.

**Alternativas**: migrar de todos modos por el ahorro de líneas (rechazado: el
ahorro es medio punto porcentual de la app y cero en la serie); migrar sólo el
centroide, que es donde está el efecto (rechazado: el efecto no se reproduce
en el control sintético, así que no se sabe qué se está comprando; y el
arreglo que sí se entendía, el FWHM del fotograma, se hizo en casa); migrar
sólo la aritmética de apertura (rechazado: da el mismo número a ±300 ppm).

## English

**Context**: ADR-060 §3 left the migration of the old modules (`fits_io`,
`wcs`, `register`, `photometry`, `series_measure`) open as a "future plan", and
with a good reason: less numerical code for us to maintain. The concrete doubt
that reopened it was a different one: very faint photometric series, the
exoplanet ones, are at the limit, and the honest question was whether an engine
resting on `astropy`/`scipy`/`photutils` would measure **better**.

The criteria were fixed before anything was touched, and that is the part that
makes this decision worth anything:

1. **Do no harm**: no dataset may get worse by more than 5 % in the scatter of
   the curve.
2. **Win on speed**: the time per frame drops 3× or more.
3. **Win on precision**: the scatter improves by 10 % relative or more on at
   least 3 of 4 datasets, with no new bias.

**Decision**: **no migration**. Criteria 2 and 3 are not met, and 1 is, so the
answer is that our own engine stays, with the numbers in front of us.

### What was measured

The bench lives in `tools/bench/` (the app does not import it and it is not
shipped) and works on the local corpus: 2025 FG18 (207 frames), 2025 HL5 (98),
2025 UR (140), 2026 PY9 (247), the real Hat-P-32 b transit (142) and the
injection of sources of known flux.

**Single measurement (injection and recovery, 5 datasets, 240 measurements per
point).** The table is the scatter divided by the plate's real noise floor;
1.000 is the aperture's limit:

| engine | SNR 3 | SNR 10 | SNR 30 | SNR 100 |
|---|---|---|---|---|
| ours | 1.027 | 1.010 | 1.041 | 1.025 |
| photutils | 0.991 | 1.016 | 1.017 | 1.038 |

Every engine reaches the floor within 1 to 6 %, and the difference between them
is about 2 %, below the standard error. The sky estimator gives **the same
number** in both (mean 1551.8966 ADU, same deviation, bias −0.10 ADU), and the
aperture arithmetic agrees to ±300 ppm. In a synthetic control with known truth
(600 trials, deterministic clicks) no centroid is distinguishable from another
at SNR 2.3, 23 or 77. The only thing photutils clearly wins is the centroid's
**position** (1.5 to 4.6 times better), and it does not turn into a better
flux.

**Real series (same frames, same comparisons, same apertures, same alignment:
only the measurement of one star on one frame changes).**

| dataset | frames | ours (ms/f) | photutils (ms/f) | speed | our scatter | photutils scatter | gain |
|---|---|---|---|---|---|---|---|
| 2025 FG18 | 207 | 700.7 | 469.5 | 1.49× | 65.61 | 59.23 | +9.7 % |
| 2025 HL5 | 98 | 567.2 | 404.0 | 1.40× | 20.66 | 20.28 | +1.8 % |
| 2025 UR | 140 | 488.5 | 377.3 | 1.29× | 111.09 | 110.09 | +0.9 % |
| 2026 PY9 | 247 | 582.3 | 408.3 | 1.43× | 25.44 | 25.54 | −0.4 % |
| Hat-P-32 b | 142 | 226.9 | 130.1 | 1.74× | 23.67 | 23.07 | +2.5 % |

Median: **+1.8 % precision and 1.43× speed**. All of the effect, when there is
one, is in the centroid: swapping only the arithmetic leaves the result
identical to the ppm. And the case closest to the threshold (FG18, +9.7 %) does
not reproduce in the synthetic control, so it comes from how the centroid
behaves under real conditions and not from the estimator.

> The speed column is the one of the moment of the decision. The improvements
> of points 2 and 3 (below) later made our engine 1.2 to 1.5× faster, and moved
> the precision a little: FG18 64.49 against photutils' 53.68, HL5 20.67
> against 20.13, UR 110.86 against 109.13, PY9 24.91 against 25.10 and HatP32
> 22.48 against 22.59. The FG18 gap widens because photutils' 2D fit gets even
> more out of a sane FWHM, and that is a reason to look at **our** centroid,
> not to migrate. The criterion is still not met: 1 of 4 datasets above 10 %.

**The noise of the author's series is not put there by the engine.** Measured
on 2025 FG18: a pair of stars 6′ apart gives 19.1 mmag of differential scatter
and at 30′ it gives 38.5 mmag. That dependence on separation is the signature
of spatially correlated noise, and the app's own scintillation model predicts
131 mmag for 0.43 m and 1 s. No engine fixes that; a longer exposure does.

### How much code would be saved (and why it is not enough)

Real code, without comments or docstrings:

| block of `photometry.py` | real lines |
|---|---|
| replaceable by photutils | 725 (54 %) |
| partial (the guards stay) | 112 |
| ours, with no equivalent | 384 |

The photutils version of the **same measurement core** (centroid, aperture,
sky and guards) written for the bench is 146 real lines against 410 of ours.
But:

* `series_measure.py` has 1296 real lines and only **52 (4 %)** have an
  equivalent: the series engine (ensemble, per-frame zero point, detrend,
  gates) is ours and stays ours;
* ADR-058 requires explaining, and 44 % of our lines are explanation, so the
  saving in the editor is half the saving in code;
* the tests that pin the numerical behaviour must be rewritten (38 of 3075
  call a replaceable function directly, and they are exactly the ones pinning
  our arithmetic);
* the guards stay: ADR-066's ceilings, the bilingual reasons, the deblending
  and the core cap are not covered by photutils;
* the API moves (photutils 3.0 has just removed the top-level aliases).

Realistic net saving: **250 to 450 lines**, 15 to 25 % of `photometry.py`,
which is **0.5 to 0.8 % of the app's code**, and zero in the series.

### What the measurement found along the way

The study was worth more for what it found than for what it decided, and the
four things are fixed or measured:

1. **A real bug**: `measure_matched` returned `ok=True` with a negative flux
   (measured on 2025 FG18, frame 15, target T18: −845.6 ADU and snr −0.97) and
   the recipe took the logarithm of that number, killing the whole 207-frame
   run with "math domain error". Reachable from the GUI's normal series flow
   (which runs with the matched filter) and from the Measure tab. One place
   fixes it, and now **a measurement is a positive flux**.
2. **The FWHM was estimated per star**: 3.2 to 11.0 px where the session had
   4.64, moving the centroid by up to 0.28 px. The frame measures it once, on
   the comparisons (which are the same in a pass and in a solo run, or the
   pass's parity breaks), and shares it. Measured on the five datasets: **1.7 %
   median improvement in the scatter** (FG18 −1.7 %, HL5 0 %, UR −0.2 %,
   PY9 −2.1 %, HatP32 −5.0 %) and between **1.2 and 1.5× speed**, because
   measuring the seeing once per frame replaces one estimate per star. The
   first attempt measured it on the targets as well as the comparisons, and it
   broke the pass's parity (a pass of two objects gave a different curve from
   the same object measured alone): the test that exists for that caught it.
3. **The deblending cost 3.20 ms per measurement (1.52×)** because
   `local_sources` walked the cutout pixel by pixel in Python (1369 iterations
   on the 45 px window, to find nothing at all on noise). Vectorised, with an
   identical result (verified over 1050 comparisons: noise, stars, gradients,
   plateaus and real crops), it costs **0.35 ms (1.06×)** and buys the same:
   with a neighbour closer than 1.5 FWHM, 15 to 60 % less flux scatter and up
   to 3.5× less position error. The question "40 % of the time for 1 % of
   scatter" stops making sense: it now costs 6 %.
4. **The reported error is 5 to 20 times the real scatter** (FG18: 287 mmag
   reported against 58 measured). It is conservative by design, but it is
   noted.

**Consequences**: `photometry.py` and `series_measure.py` are **not migrated**,
and ADR-060 §3 is closed for them: coexistence with the libraries stays open
for **new capabilities** (PSF photometry, `Background2D`), and with the same
condition as this study: what comes in is what brings a measured gain, not what
sounds good. The bench is kept in `tools/bench/` so the measurement can be
repeated if the regime changes (another camera, another sky, another photutils
version), and it is not shipped with the application.

**Alternatives**: migrate anyway for the line saving (rejected: the saving is
half a percentage point of the app and zero in the series); migrate only the
centroid, which is where the effect is (rejected: the effect does not reproduce
in the synthetic control, so it is not known what would be bought, and the fix
that was understood, the frame's FWHM, was done at home); migrate only the
aperture arithmetic (rejected: it gives the same number to ±300 ppm).
