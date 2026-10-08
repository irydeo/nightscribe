# ADR-069: El flat sintético se enmascara, y el pedestal se quita

**Estado / Status**: Accepted · **Fecha / Date**: 2026-10-07

## Español

**Contexto**: el autor reabrió el tema del pseudo-flat (P5) con un requisito
que el código no cumplía: «un flat sintético que ha de salir de las imágenes
de la serie, pero en el que de ninguna manera pueden salir estrellas; en tal
caso, simplemente no es un flat».

El P5 construía el percentil 33 % entre tomas y **después** buscaba estrellas
dentro de él. Si las encontraba, se rendía y devolvía un modelo suave del
viñeteado, que no es un flat: no corrige el polvo. Y en un campo estático las
encontraba siempre, porque las estrellas no se mueven y un percentil entre
tomas no las puede quitar.

Antes de tocar el motor se midió con `tools/bench/bench_flat.py`, cuyo patrón
oro es el master real de las **150 flats de esa misma noche**
(`dataset/Flat-31-03-2025-3/20250331`, mediana por franjas, 55 s).

**Lo que se midió primero**:

| | valor |
| --- | --- |
| Deriva del campo en 2025 FG18 (17 a 33 estrellas emparejadas) | **2 px en 207 tomas** |
| Ruido por píxel / cielo de la toma | 117 ADU / 1.552 ADU (7,5 %) |
| Cuantización de la toma | 16 ADU (profundidad efectiva de 12 bits) |
| Picos aislados en una toma (3σ) | 11.785, de los cuales 11.714 de 1 a 2 px |
| Master real, rango normalizado | 0,389 (esquina) a 1,110 |

**El flat de hoy, en FG18, lleva estrellas y el criterio no lo ve**:

| | flat de hoy | master real |
| --- | --- | --- |
| Máximo | **2,832** | 1,110 |
| Residuo de pequeña escala (MAD escalada) | 0,06 % | 0,65 % |
| Desviación sobre el suavizado **en los píxeles con estrella** | **33,83 %** | 4,58 % |

El residuo del P5 es una **MAD escalada**, y la MAD es robusta por
construcción: las estrellas ocupan el 0,3 % de los píxeles, así que un flat
que las lleva (un máximo de 2,83, siete veces el del real) no mueve el número.
Por eso se colaba declarándose `pseudo_flat` con un residuo del 1,60 %.

**Y el pedestal es un confusor de primer orden**: el pseudo-flat se construye
de las tomas, así que lleva su pedestal (`flat_obs = P + cielo × R`). La
normalización no lo quita y la forma sale **comprimida**. Medido ajustando el
mejor pedestal contra el master real:

| p = pedestal / cielo | acuerdo con el master |
| --- | --- |
| 0,00 | 15,59 % |
| 1,00 | 4,45 % |
| **1,25** | **4,16 %** |
| 2,00 | 6,07 % |

El nivel de las tomas es 1.488 ADU, el cielo 661 y el pedestal **827 ADU (56 %
del nivel)**. La compresión es `1/(1+p) = 0,44`: **el pseudo-flat corregía
solo el 44 % del viñeteado** en estas tomas de 1 s de crepúsculo. (En 2025 UR,
con un cielo de 4.600 a 5.184, corregía el 81 %, y por eso parecía que iba
bien.)

**Decisión**:

1. **La máscara va ANTES del estadístico.** Por toma se detecta lo que está
   por encima de 5σ de la **mediana suavizada** del percentil (el único
   detector que ve las estrellas débiles: una que sume un 1 % del cielo está a
   S/N 0,13 en una toma y solo existe al combinar), y **solo lo extenso se
   dilata** (12 px). Lo que no pasa de 1 a 2 px es un **píxel caliente**, no
   una estrella: dilatar los 10.150 de FG18 enmascaraba el **50 % del
   fotograma**.
2. **Los píxeles enmascarados se tiran y el flat se interpola ahí.** En un
   campo estático el mismo píxel está enmascarado en todas las tomas, así que
   no hay dato y el valor tiene que salir del cielo que lo rodea. El relleno y
   el suavizado son **la misma operación**: una convolución normalizada,
   `uniform(x·m) / uniform(m)`, tres pasadas de 41 px. Medido: rellena el
   **1,50 %** de los píxeles.
3. **Los píxeles calientes se quedan en el flat**, porque están fijos en el
   sensor y la división es lo que los quita; y se **restauran después del
   suavizado**, porque el filtro de caja diluiría un solo píxel 1.681 veces y
   la división lo dejaría donde estaba (medido: 1.484 ADU en el flat suavizado
   contra 1.744 en el estadístico, sobre un cielo de 1.488).
4. **El pedestal se quita con el master de offset** (dark o bias), la misma
   receta que la toma: el pseudo-flat se construye de las tomas **con el
   offset ya restado** (`_OffsetSubtractor`). Esto además arregla un fallo que
   ya existía: con master de offset, la toma llegaba sin pedestal y se dividía
   por un flat que sí lo llevaba. **Sin master de offset la app lo dice**, con
   la cifra medida, y pide un bias.
5. **El criterio pasa a ser la desviación sobre el suavizado EN LOS PÍXELES
   ENMASCARADOS**, que es donde había una estrella y por tanto donde no puede
   haber bulto. Medido: 33,83 % en el flat que las llevaba, **2,11 %** en el
   enmascarado, y 4,58 % en el master real (que lleva el polvo, y el polvo no
   está enmascarado y es un hundimiento, no un bulto). El residuo de la MAD se
   conserva **como cifra**, no como comprobación.
6. **`vignette_model` queda como último recurso**, no como la salida del caso
   estático: solo cuando lo enmascarado pasa del 30 % del fotograma y no queda
   cielo con el que construir nada.
7. **El flat se escribe como producto de la visita** (FITS, con su
   procedencia en las tarjetas: `NS_FLAT`, `NS_NFRA`, `NS_MASK`, `NS_FILL`,
   `NS_HOT`, `NS_VERIF`, `NS_RESID`) y **se puede abrir en el visor del
   editor** con un botón. Un flat que nadie puede mirar es un flat que nadie
   puede comprobar, y el criterio del autor para «esto es un flat» es verlo y
   comprobar que no tiene estrellas.

**Lo que da, medido** (visita real de 207 tomas, contra el master real):

| | flat enmascarado | master real |
| --- | --- | --- |
| Máximo **sin los píxeles calientes** | **1,1136** | **1,1102** |
| Máximo con ellos (se quedan a propósito) | 6,22 | 1,11 |
| p1 / p99 | 0,8390 / 1,0289 | 0,8373 / 1,085 |
| Desviación en los enmascarados, p99 | **2,05 %** | 4,58 % |
| Tiempo, 207 tomas | **18,6 s** | (el motor anterior, 17,9 s) |

Que el máximo sin píxeles calientes coincida al **0,3 %** con el del flat real
es la prueba más fuerte de que las estrellas han desaparecido. El límite
honesto del método sigue siendo el otro 4,16 %: es **la forma del cielo metida
dentro del flat** (un flat real no la tiene), 0,045 mag.

**Consecuencias**: el pseudo-flat deja de ser un respaldo que solo funcionaba
con dither y pasa a ser un flat de resolución completa, con polvo y sin
estrellas, también en un campo estático; necesita un dark/bias para el
pedestal, y lo dice cuando no lo tiene; el criterio de la app deja de dar por
bueno un flat que lleva estrellas; y el flat es un producto que se mira. El
banco se conserva, sin enviarse con la app, para poder repetir la comparación
cuando cambie el régimen.

**La profundidad, medida aparte** (`tools/bench/bench_flat_depth.py`, un stack
medio propio de 60 tomas en las unidades de la toma, con la fuente inyectada
**modulada por la respuesta real** y medida con la fotometría de la app):

| candidato | ruido local | mag límite (SNR 5) | sistemático vs el master |
| --- | --- | --- | --- |
| sin flat | 25,30 ADU/px | 17,46 | **9,06 %** |
| flat de hoy (sin máscara) | 25,08 | 17,48 | 6,22 % |
| enmascarado | 25,07 | 17,48 | 6,27 % |
| **enmasc + pedestal** | 24,90 | 17,48 | **4,16 %** |
| master real | 24,63 | 17,49 | (referencia) |

Dos lecturas, y son distintas a propósito:

- **La profundidad es la misma en los cinco** (17,46 a 17,49 mag): dividir por
  un mapa suave escala la fuente y el ruido por igual, así que la relación
  señal/ruido por píxel no cambia. El flat no compra profundidad.
- **El sistemático sí cambia**, y por dos vías independientes: 9,06 % sin flat
  y **4,16 %** con el enmascarado y el pedestal quitado. Ese 4,16 % coincide
  **exactamente** con el que da el otro banco (el ratio contra el master real
  sobre todo el campo), medido de otra manera y con otro instrumento.

El instrumento costó tres intentos y los tres fallos están escritos en el
banco: inyectar en el stack ya dividido (la fuente nunca se cruza con el
flat), inyectar flujo constante (una estrella llega multiplicada por la
respuesta) y comparar posiciones sin cancelar el cielo local (su error de
0,1 % sobre una apertura de 121 px son 185 ADU, que tapan una inyección de
210).

**Alternativas rechazadas**, todas medidas:

- **El ajuste de rango 1 por píxel** (`L = a + s_f·b`, que es la formulación
  físicamente correcta: el pedestal y las estrellas fijas caen en `a`). Falla
  por la palanca: el cielo de FG18 varía un 3,15 % (48 ADU) contra un ruido de
  117 ADU, así que la pendiente por píxel sale con un 43 % de error y el
  ajuste crudo iba de −820 a +554, con el 2,7 % de los píxeles negativos.
- **La MAD espacial como palanca** (es proporcional al cielo, no al
  pedestal): sale **exactamente constante** en las 207 tomas, porque está
  dominada por el ruido (118,6 ADU contra 47 de estructura).
- **La identidad de diferencias** (`f1 = P + K(f1 − f2)`): residuos de 337
  ADU, tres veces el ruido, porque la forma del cielo cambia en el crepúsculo;
  el intercepto (1.539 ADU) implicaría un cielo de cero.
- **El ruido fotónico** (`cielo = ganancia × ruido²`, con la ganancia que mide
  `core/gain.py`, 0,1236 ± 0,0001 e-/ADU): da un cielo de 1.704 ADU, mayor que
  el nivel, o sea un pedestal negativo.
- **El barrido por posición** (inyectar la misma fuente modulada por la
  respuesta en todo el campo y medirla): sale dominado por la dispersión de la
  propia apertura, 0,22 mag **incluso con el flat real**, así que no resuelve
  un sistemático de ese tamaño. El sistemático se mide donde está limpio: en
  el ratio entre cada flat y el master real, que es por lo que divide la
  fotometría.
- **`vignette_model` como camino normal del campo estático**: rechazado, es
  un modelo suave y no corrige el polvo (0,6 % = 0,007 mag), que es
  precisamente lo que distingue un flat de un ABE.
- **Delegar en PixInsight**: ABE y DBE son un modelo suave del fondo
  (resta o división), de la misma clase que `vignette_model`, y PixInsight no
  trae ningún proceso de flat desde las tomas. Se queda la puerta barata: la
  biblioteca ya acepta un master hecho fuera (WBPP incluido) y el flat se
  exporta a FITS para poder mirarlo o retocarlo allí.

## English

**Context**: the author reopened the pseudo-flat (P5) with a requirement the
code did not meet: "a synthetic flat that has to come out of the series
images, but in which no star can appear; in that case it is simply not a
flat".

P5 built the 33 % percentile over the frames and looked for stars **inside it
afterwards**. When it found them it gave up and returned a smooth model of the
vignetting, which is not a flat: it does not correct the dust. And on a static
field it always found them, because the stars do not move and a percentile
over the frames cannot remove them.

Before touching the engine it was measured with `tools/bench/bench_flat.py`,
whose gold standard is the real master of the **150 flats of that same night**
(`dataset/Flat-31-03-2025-3/20250331`, median in row bands, 55 s).

**Measured first**: the field of 2025 FG18 drifts **2 px over 207 frames** (17
to 33 stars matched); the pixel noise is 117 ADU on a sky of 1,552 (7.5 %) and
the data is quantised to 16 ADU (an effective 12-bit depth); one frame holds
11,785 isolated spikes above 3 sigma, 11,714 of them 1 to 2 px wide; and the
real master spans 0.389 (the corner) to 1.110.

**Today's flat on FG18 carries stars and the check does not see it**: its
maximum is **2.832** against the real flat's 1.110, and over the pixels that
hold a star it deviates **33.83 %** from its own smoothed version. The P5
residual is a **scaled MAD**, and a MAD is robust by construction: the stars
cover 0.3 % of the pixels, so a flat carrying them moves it by nothing at all
(0.06 % against 0.05 %). That is why it passed while declaring itself
`pseudo_flat` with a residual of 1.60 %.

**And the pedestal is a first-order confuser**: the pseudo-flat is built from
the lights, so it carries their pedestal (`flat_obs = P + sky x R`). The
normalisation does not remove it and the shape comes out **compressed**.
Fitting the best pedestal against the real master: 15.59 % of disagreement at
p = 0, 4.45 % at p = 1 and **4.16 % at p = 1.25**. The level of the frames is
1,488 ADU, the sky 661 and the pedestal **827 ADU (56 % of the level)**, so the
compression is `1/(1+p) = 0.44`: **the pseudo-flat was correcting only 44 % of
the vignetting** on these 1 s twilight frames. (On 2025 UR, with a sky of
4,600 to 5,184, it corrected 81 %, which is why it looked fine.)

**Decision**:

1. **The mask comes BEFORE the statistic.** Each frame is searched for what
   sits above 5 sigma of the **smoothed** percentile (the only detector that
   sees the faint stars: one worth 1 % of the sky is at S/N 0.13 in a single
   frame and only exists in the combination), and **only what is extended is
   dilated** (12 px). What is not bigger than 1 to 2 px is a **hot pixel**, not
   a star: dilating the 10,150 of FG18 masked **50 % of the frame**.
2. **The masked pixels are dropped and the flat is interpolated there.** On a
   static field the same pixel is masked in every frame, so there is no data
   and the value has to come from the sky around it. The fill and the
   smoothing are **the same operation**: a normalised convolution,
   `uniform(x*m) / uniform(m)`, three passes of 41 px. Measured: it fills
   **1.50 %** of the pixels.
3. **The hot pixels stay in the flat**, because they are fixed on the sensor
   and the division is what removes them, and they are **put back after the
   smoothing**, because the box filter would dilute a single pixel 1,681 times
   and the division would leave it where it was (measured: 1,484 ADU in the
   smoothed flat against 1,744 in the statistic, over a sky of 1,488).
4. **The pedestal is removed with the offset master** (dark or bias), the same
   recipe as the light: the pseudo-flat is built from the frames **with the
   offset already subtracted** (`_OffsetSubtractor`). This also fixes a bug
   that already existed: with an offset master, the light arrived without its
   pedestal and was divided by a flat that still carried one. **Without an
   offset master the app says so**, with the measured figure, and asks for a
   bias.
5. **The check becomes the deviation from the smoothed flat AT THE MASKED
   PIXELS**, which is where a star was and therefore where a bump cannot
   exist. Measured: 33.83 % on the flat that carried them, **2.11 %** on the
   masked one, and 4.58 % on the real master (it carries the dust, which is
   not masked and is a dip, not a bump). The MAD residual is kept **as a
   figure**, not as the check.
6. **`vignette_model` is the last resort**, not the answer to a static field:
   only when what is masked passes 30 % of the frame and there is no sky left
   to build anything from.
7. **The flat is written as a product of the visit** (FITS, with its
   provenance in the cards: `NS_FLAT`, `NS_NFRA`, `NS_MASK`, `NS_FILL`,
   `NS_HOT`, `NS_VERIF`, `NS_RESID`) and **it can be opened in the editor's own
   viewer** with a button. A flat nobody can look at is a flat nobody can
   check, and the author's criterion for "this is a flat" is to see it and
   find no star in it.

**What it gives, measured** (a real 207-frame visit, against the real master):
the maximum **without the hot pixels** is **1.1136** against the real flat's
**1.1102** (a 0.3 % agreement, and the strongest evidence that the stars are
gone); p1/p99 are 0.8390/1.0289 against 0.8373/1.085; the deviation over the
masked pixels is **2.05 %** against 4.58 %; and it takes **18.6 s** for 207
frames (the old engine, 17.9 s). The honest limit of the method is the other
4.16 %: it is **the sky's shape baked into the flat** (a real flat does not
have it), 0.045 mag.

**Consequences**: the pseudo-flat stops being a fallback that only worked with
dither and becomes a full-resolution flat, with the dust and without the
stars, on a static field too; it needs a dark/bias for the pedestal and says
so when it has none; the app's check stops accepting a flat that carries
stars; and the flat is a product the observer can look at. The bench is kept,
not shipped with the app, so the comparison can be repeated when the regime
changes.

**The depth, measured separately** (`tools/bench/bench_flat_depth.py`: its own
mean stack of 60 frames in the single frame's units, with the source injected
**modulated by the real response** and measured with the app's own photometry):
without a flat the systematic is **9.06 %** and the depth 17.46 mag; with
today's flat 6.22 % and 17.48; with the masked one 6.27 % and 17.48; and with
the masked one and the pedestal removed **4.16 %** and 17.48 (the real flat,
17.49, is the reference). Two readings, and they are different on purpose: the
**depth is the same in all five** (dividing by a smooth map scales the source
and the noise together, so the signal-to-noise per pixel does not change: a
flat does not buy depth), while the **systematic does change**, and its 4.16 %
matches **exactly** the figure the other bench gives (the ratio against the
real master over the whole field), measured another way and with another
instrument. The instrument took three tries and all three failures are written
in the bench: injecting into the already-divided stack (the source never meets
the flat), injecting a constant flux (a star arrives multiplied by the
response) and comparing positions without cancelling the local sky (its 0.1 %
error over a 121-pixel aperture is 185 ADU, which swamps a 210 ADU injection).

**Rejected alternatives**, all measured: the **per-pixel rank-1 fit** (the
physically right formulation, defeated by the lever: a 3.15 % sky variation
against a 117 ADU noise gives a 43 % error per pixel and 2.7 % of them
negative); the **spatial MAD as a lever** (exactly constant over the 207
frames, dominated by the noise); the **difference identity** (residuals of 337
ADU, three times the noise, because the sky's shape changes during twilight);
the **photon-noise route** (the gain that `core/gain.py` measures gives a sky
larger than the level, i.e. a negative pedestal); the **position sweep**
(dominated by the aperture's own scatter, 0.22 mag even with the real flat);
**`vignette_model` as the normal path** for a static field (it is a smooth
model and does not correct the dust); and **delegating to PixInsight** (ABE
and DBE are a smooth background model, the same class as `vignette_model`, and
PixInsight has no process for a flat built from the frames). The cheap door
stays open: the library already accepts a master made elsewhere (WBPP
included) and the flat is exported to FITS so it can be looked at or refined
there.
