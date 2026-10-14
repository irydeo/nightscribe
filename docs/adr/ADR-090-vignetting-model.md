# ADR-090: El modelo de viñeteo se muestrea del cielo

**Estado / Status**: Accepted · **Fecha / Date**: 2026-10-14

> Sustituye la decisión de **ADR-069** (el flat sintético enmascarado). El
> ADR-069 queda como historia: describe lo que se midió entonces y por qué se
> hizo así, y esta revisión dice por qué se deja de hacer.

## Español

**Contexto**: el ADR-069 construía un «flat sintético» de resolución completa
desde las tomas: un percentil por píxel sobre la visita, una máscara de
estrellas, un relleno por convolución normalizada y la restauración de los
píxeles calientes. El autor pidió simplificarlo: «realmente lo único que nos
interesa es el viñeteo; muchos programas recogen el fondo del cielo a lo largo
de la imagen para muestrearla, y si hay alguna estrella ahí, se descarta».

Antes de tocar nada se midió con el banco de siempre (`tools/bench/bench_flat.py`,
patrón oro el master real de las 150 flats del 2025-03-31), sobre la visita
FG18 de 207 tomas de 2048², como **dispersión p5–p95 del cociente** entre cada
candidato y el master real:

| candidato | acuerdo con la FORMA | tiempo |
| --- | --- | --- |
| flat enmascarado del ADR-069 (resolución completa) | 4,16 % (0,045 mag) | 20 s |
| modelo, rejilla por defecto (51 px), grado 6 | 4,98 % | 2,4 s |
| modelo 48 px, grado 6 | 3,93 % (0,042 mag) | 2,4 s |
| modelo 32 px, grado 6 | 4,26 % | 2,5 s |
| modelo 64 px, grado 6 | 5,46 % | 2,4 s |
| sin ningún flat | 0,087 mag | |

Dos lecturas, y son las que deciden:

- **En el viñeteo, el modelo suave es COMPARABLE** al flat enmascarado: cae en
  la banda del 4-5,5 % según cómo caiga la rejilla sobre las motas, contra el
  4,16 % del enmascarado, y es **ocho veces más rápido** (2,4 s contra 20). La
  rejilla no se afina a una visita: es una fracción redonda del fotograma, y la
  banda es lo que hay.
- **Lo único que el enmascarado compraba era el polvo**: 2,38 % = **0,026 mag**
  (medido como la estructura fina del master real, su versión suavizada contra
  la cruda). El viñeteo vale 0,087 mag. Es exactamente lo que decía el autor.

Y el límite honesto no cambia con ninguno de los dos: ~0,04 mag es **la forma
del cielo metida dentro del modelo**, que un real no tiene.

**Decisión**:

1. **Se muestrea el cielo en una rejilla de teselas.** La viñeteo del tren es
   suave y fijo en el fotograma, y el cielo es la luz que lo llena: lo que ve
   una rejilla de teselas, una vez tiradas las que una estrella o una mota
   estropearon, ES el viñeteo. La tesela es una fracción del lado corto del
   fotograma (40 teselas por lado: 2048 px → 51 px), con un suelo de 32 px
   para que un fotograma pequeño no acabe con una rejilla demasiado gruesa.
2. **Se leen veinte tomas repartidas por la visita, no todas.** Una tesela de
   48 px tiene miles de píxeles, así que su mediana ya lleva ~0,1 % donde el
   ruido de un píxel es 7,5 %, y veinte lecturas en vez de doscientas es lo
   que hace que el modelo sean segundos. Medido: 20 y 40 tomas dan lo mismo
   (4,2 % a 32 px). La mediana entre tomas es la que aguanta una toma con un
   satélite, una nube o una fila mala.
3. **La tesela se resume en su MEDIANA**, no en su media: una estrella, un rayo
   cósmico o un avión dentro de una tesela no la mueven mientras no cubran más
   de la mitad.
4. **El rechazo es el propio ajuste, y es robusto.** Se ajusta una superficie
   de grado 6 y se repite tres veces descartando las teselas cuyo residuo pase
   de 3 MAD escaladas. Eso es TODO el rechazo: no hay máscara, ni dilatación,
   ni relleno, ni píxeles calientes. Medido en FG18: el 6 % de las teselas a
   64 px. El grado 6 es medida, no gusto: el 4 dejaba 5,75 % y el 8 y el 10 no
   mejoraban (4,85 % y 4,76 %) al doble de coste, con los bordes del fotograma
   empezando a moverse solos.
5. **El pedestal se quita con el master de offset** (dark o bias), la misma
   receta que la toma: el modelo se construye de las tomas **con el offset ya
   restado** (`_OffsetSubtractor`). Sin él la forma sale comprimida (medido: el
   mejor pedestal que aplana el cociente contra el master real es p ≈ 1,25–2,5
   en FG18). **Sin master de offset la app lo dice**, con la cifra medida, y
   pide un bias.
6. **No se inventa nada cuando no se puede.** Si sobreviven menos teselas que
   el suelo (30, o los términos del ajuste más uno), no hay modelo y hay un
   motivo; nunca una superficie sostenida por tres puntos.
7. **Se llama por lo que es: un MODELO DE VIÑETEO, no un flat.** No lleva polvo
   y lleva dentro la forma del cielo. Cambia el nombre en la interfaz, en la
   clave del ajuste (`calib_vignette_model`, con migración desde
   `calib_pseudo_flat`) y en las tarjetas FITS (`NS_VIGN`, `NS_TILE`,
   `NS_ORDER`, `NS_TILES`, `NS_KEPT`, `NS_MED`). La biblioteca sigue
   aceptando un master real, y un flat real siempre gana.

**Alternativas rechazadas**, medidas o razonadas:

- **El flat enmascarado del ADR-069** (resolución completa): no es peor en el
  viñeteo (4,26 % contra 3,93 %), pero cuesta 20 s contra 3, y toda su
  maquinaria (máscara, dilatación, relleno, píxeles calientes, `verify_pct`)
  compra 0,026 mag de polvo. Se retira.
- **Interpolar la rejilla** (spline) en vez de ajustar una superficie: cogería
  algo de polvo, a cambio de ruido y de complejidad. La medida dice que el
  polvo vale 0,026 mag y que el ajuste ya está a la altura del flat completo.
- **Un modelo radial**: más simple todavía, pero la viñeteo no es perfectamente
  radial (el eje óptico puede estar descentrado) y el polvo no lo es en
  absoluto. El polinomio es lo bastante general y sigue siendo barato.
- **Delegar en el software externo**: sigue en pie la puerta barata del
  ADR-069: la biblioteca acepta un master hecho fuera (WBPP incluido) y el
  modelo se exporta a FITS para mirarlo o compararlo.

**Consecuencias**: el modelo deja de necesitar dither (las teselas que una
estrella estropea se tiran solas), deja de necesitar todas las tomas (veinte
bastan) y deja de tener knobs; el motor pasa de ~180 líneas con máscara,
relleno y píxeles calientes a una rejilla, un ajuste robusto y un rechazo por
residuo; y la app sigue diciendo qué master usó y por qué no usó uno que el
observador ve en la biblioteca. El banco se conserva, sin enviarse con la app,
para repetir la comparación cuando cambie el régimen.

## English

**Context**: ADR-069 built a full-resolution "synthetic flat" out of the
frames: a per-pixel percentile over the visit, a star mask, a fill by
normalised convolution and the restoration of the hot pixels. The author asked
for it to be simplified: "really the only thing we care about is the
vignetting; many programs sample the sky background across the image, and if
there is a star there, it is discarded".

Before touching anything it was measured with the usual bench
(`tools/bench/bench_flat.py`, gold standard the real master of the 150 flats
of 2025-03-31), on the FG18 visit of 207 frames of 2048², as the **p5–p95
spread of the ratio** between each candidate and the real master:

| candidate | agreement on the SHAPE | time |
| --- | --- | --- |
| ADR-069's masked flat (full resolution) | 4.16 % (0.045 mag) | 20 s |
| model, default grid (51 px), degree 6 | 4.98 % | 2.4 s |
| model 48 px, degree 6 | 3.93 % (0.042 mag) | 2.4 s |
| model 32 px, degree 6 | 4.26 % | 2.5 s |
| model 64 px, degree 6 | 5.46 % | 2.4 s |
| no flat at all | 0.087 mag | |

Two readings, and they are what decides:

- **On the vignetting, the smooth model is COMPARABLE** to the masked flat: it
  lands in the 4-5.5 % band depending on how the grid falls over the motes,
  against the masked one's 4.16 %, and it is **eight times faster** (2.4 s
  against 20). The grid is not tuned to one visit: it is a round fraction of
  the frame, and the band is what there is.
- **The only thing the masked one bought was the dust**: 2.38 % = **0.026 mag**
  (measured as the real master's fine structure, its smoothed version against
  the raw one). The vignetting is worth 0.087 mag. It is exactly what the
  author said.

And the honest limit does not change with either: ~0.04 mag is **the sky's
shape baked into the model**, which a real one does not have.

**Decision**:

1. **The sky is sampled on a grid of tiles.** The train's vignetting is smooth
   and fixed on the frame, and the sky is the light that fills it: what a grid
   of tiles sees, once the tiles a star or a mote spoiled are thrown away, IS
   the vignetting. The tile is a fraction of the frame's short side (40 tiles
   per side: 2048 px -> 51 px), with a 32-px floor so a small frame does not
   end up with a grid too coarse.
2. **Twenty frames spread over the visit are read, not all of them.** A 48-px
   tile holds thousands of pixels, so its median already carries ~0.1 % where a
   single pixel's noise is 7.5 %, and twenty reads instead of two hundred is
   what makes the model seconds. Measured: 20 and 40 frames give the same
   (4.2 % at 32 px). The median across the frames is what survives a frame with
   a satellite, a cloud or a bad row.
3. **A tile is summarised by its MEDIAN**, not its mean: a star, a cosmic ray
   or a plane inside a tile does not move it while it covers less than half.
4. **The rejection IS the fit, and it is robust.** A degree-6 surface is fitted
   and three times over the tiles whose residual passes 3 scaled MADs are
   dropped. That is ALL the rejection: no mask, no dilation, no fill, no hot
   pixels. Measured on FG18: 6 % of the tiles at 64 px. The degree 6 is
   measured, not taste: 4 left 5.75 % and 8 and 10 were no better (4.85 % and
   4.76 %) at twice the cost, with the frame's edges starting to move on their
   own.
5. **The pedestal is removed with the offset master** (dark or bias), the same
   recipe as the light: the model is built from the frames **with the offset
   already subtracted** (`_OffsetSubtractor`). Without it the shape comes out
   compressed (measured: the best pedestal that flattens the ratio against the
   real master is p ~ 1.25-2.5 on FG18). **Without an offset master the app
   says so**, with the measured figure, and asks for a bias.
6. **Nothing is invented when it cannot be built.** If fewer tiles survive than
   the floor (30, or the fit's own terms plus one), there is no model and there
   is a reason; never a surface held up by three points.
7. **It is named for what it is: a VIGNETTING MODEL, not a flat.** It carries
   no dust and it folds in the sky's own shape. The name changes in the
   interface, in the setting key (`calib_vignette_model`, with a migration from
   `calib_pseudo_flat`) and in the FITS cards (`NS_VIGN`, `NS_TILE`,
   `NS_ORDER`, `NS_TILES`, `NS_KEPT`, `NS_MED`). The library still takes a real
   master, and a real flat always wins.

**Rejected alternatives**, measured or reasoned:

- **ADR-069's masked flat** (full resolution): it is not worse on the vignetting
  (4.26 % against 3.93 %), but it costs 20 s against 3, and all of its
  machinery (mask, dilation, fill, hot pixels, `verify_pct`) buys 0.026 mag of
  dust. It is retired.
- **Interpolating the grid** (a spline) instead of fitting a surface: it would
  catch some dust, at the price of noise and complexity. The measurement says
  the dust is worth 0.026 mag and that the fit is already at the full flat's
  level.
- **A radial model**: simpler still, but the vignetting is not perfectly radial
  (the optical axis can be off-centre) and the dust is not radial at all. The
  polynomial is general enough and still cheap.
- **Delegating to external software**: ADR-069's cheap door stays open: the
  library takes a master made elsewhere (WBPP included) and the model is
  exported to FITS to be looked at or compared.

**Consequences**: the model stops needing dither (the tiles a star spoiled are
thrown away by themselves), stops needing every frame (twenty are enough) and
stops having knobs; the engine goes from ~180 lines with a mask, a fill and hot
pixels to a grid, a robust fit and a residual rejection; and the app still says
which master it used and why it did not use one the observer can see in the
library. The bench is kept, not shipped with the app, so the comparison can be
repeated when the regime changes.
