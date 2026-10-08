# ADR-061: Calibración de imágenes y biblioteca de masters

**Estado / Status**: Accepted · **Fecha / Date**: 2026-10-04

> **Actualización (2026-10-05)**: la biblioteca de masters ya es
> administrable en Ajustes. Se añade la pestaña **Calibración**
> (`tab_calibration`), entre Observing e Integrations: la ayuda explica
> qué es un master y para qué sirven los cuatro tipos, el combo fija el
> tipo con el que se indexa un lote de ficheros y la tabla lista lo que
> hay (fichero, tipo, cámara, ganancia, temperatura, exposición, filtro,
> fecha) con su botón de quitar. Los ficheros se **enlazan, nunca se
> copian ni se mueven**, y quitar una fila toca solo el índice: el fichero
> en disco es dato del observador. Sin esta pestaña, `add_master` solo se
> llamaba desde los tests y la pestaña Calibración del editor no podía
> decir más que «falta».

## Español

**Contexto**: NightScribe no calibra imágenes. Solo usa la corriente de oscuridad
dentro del presupuesto de error y planifica tomas de calibración
(`core/sequence.py`). El apilado de objetos débiles (track & stack) no funciona
sin calibrar: el patrón térmico y las motas del tren óptico se apilan con la
señal y el objeto no emerge del ruido. Decisión del autor: **NightScribe calibra**,
y lo hace como un paso reutilizable, no escondido dentro del apilado.

**Decisión**:

1. **Biblioteca de masters indexada** (`core/calibration.py`): los ficheros master
   los construye el usuario fuera; NightScribe los apunta y los indexa por
   **cámara, ganancia, temperatura (±3 °C), tiempo de exposición (exacto) y
   filtro**. El índice vive en SQLite (`calib_masters`, migración v16) y los
   ficheros en disco. Si hay varios masters para la misma clave, gana el más
   reciente.
2. **Receta declarativa**: la receta dice qué piezas hay (offset, dark, flat) y el
   motor aplica lo que encuentra. Con **dark a la exposición exacta del light**,
   ese dark ya incluye el bias y la térmica, así que no se resta además el bias
   (sería restarlo dos veces). Sin dark, se resta el **bias** y se avisa de que
   la térmica queda. Sin ninguno, no se toca y se avisa.
3. **Flat por filtro**, con su propio offset restado (su dark-flat, o el bias si
   es corto) y **normalizado por la mediana** antes de dividir, para no cambiar el
   nivel de flujo. El orden importa: primero offset, después flat.
4. **Dark sin escalado**: coincidencia exacta de exposición. En CMOS el patrón
   térmico no escala bien con el tiempo, así que un dark de otra exposición deja
   residuo.
5. **En memoria por defecto**, con **export opcional** de FITS calibrados (no se
   duplican cientos de ficheros de 32 MB salvo que el usuario lo pida).
6. **Paso reutilizable**: pestaña propia en el Editor FITS unificado y biblioteca
   de masters administrable en Ajustes. La fotometría de series también se
   beneficiará.

**Alternativas**: delegar la calibración en el software externo (rechazado: el
objeto débil no emerge y el flujo se parte en dos herramientas); usar `ccdproc`
para todo (autorizado por ADR-060, pero la aritmética es simple y `ccdproc` tiene
mantenimiento irregular; se prefiere astropy + numpy); escalar el dark (rechazado
en CMOS por residuo).

**Consecuencias**: migración aditiva v16 (`calib_masters`); el motor devuelve
avisos en lenguaje llano en vez de excepciones cuando falta una pieza; y la
calibración pasa a ser la primera fase del pipeline de astrometría y una mejora
para la fotometría. Tests con masters sintéticos: la aritmética exacta, el
matching por tolerancia y la ausencia sin excepción.

**Revisión (2026-10-06): la calibración es un servicio, no una pestaña de un
motor**. Se pidió usarla más allá de la astrometría, y el estado anterior lo
impedía por confuso: la política del pseudo-flat estaba **duplicada** (una
casilla en la pestaña Calibración que leía `calib_pseudo_flat` y **nunca** lo
escribía, y otra en Ajustes que sí lo escribía y era la que leía el stack), así
que el interruptor que el observador tocaba no era el que funcionaba, y la
casilla «Aplicar la calibración al stack» **no se guardaba** (se reseteaba en
cada reconstrucción). Lo que cambia:

- **Un solo sitio para la receta, la biblioteca y la política del pseudo-flat**:
  la pestaña Calibración. Su casilla de pseudo-flat ahora **escribe** la clave y
  es la única; se retira la de Ajustes (Ajustes conserva la biblioteca de
  masters). Su botón se distingue de «aplicar»: es una pasada puntual sobre la
  visita que exporta copias si se pide.
- **Cada motor se apunta con su propia casilla**, junto a donde se lanza: en
  Astrometría, «Aplicar la calibración al apilado» (`calib_astrometry`),
  persistida. Una **pista de una línea** dice antes de lanzar qué va a pasar con
  los píxeles (dark/bias, flat real o pseudo-flat, o que el viñeteado se queda),
  tomada de la **misma** receta resuelta (una sola fuente, vía el host), y un
  botón **«Calibración…»** es el enlace profundo a la pestaña, como el de la
  receta de fotometría.
- **La extensión es una casilla**: cuando la serie fotométrica quiera calibrar,
  añade su `chk_calibrate`, su pista y su enlace, y lee la misma receta y el
  mismo `FrameCalibrator`. Nada que desmontar.

## English

**Context**: NightScribe does not calibrate images. It only uses dark current
inside the error budget and plans calibration exposures (`core/sequence.py`).
Stacking faint objects (track & stack) does not work uncalibrated: the thermal
pattern and the optical-train dust stack along with the signal and the object
never emerges from the noise. Author's decision: **NightScribe calibrates**, and
does so as a reusable step, not hidden inside stacking.

**Decision**:

1. **Indexed master library** (`core/calibration.py`): the user builds the master
   files elsewhere; NightScribe points at them and indexes them by **camera,
   gain, temperature (±3 °C), exposure time (exact) and filter**. The index lives
   in SQLite (`calib_masters`, migration v16) and the files on disk. If several
   masters share a key, the most recent wins.
2. **Declarative recipe**: the recipe says which pieces exist (offset, dark, flat)
   and the engine applies whatever it finds. With a **dark at the light's exact
   exposure**, that dark already includes bias and thermal, so the bias is not
   subtracted as well (that would subtract it twice). Without a dark, the **bias**
   is subtracted and a warning says the thermal remains. With neither, nothing is
   touched and a warning says so.
3. **Flat per filter**, with its own offset subtracted (its dark-flat, or the bias
   if short) and **normalised by the median** before dividing, so the flux level
   is unchanged. Order matters: offset first, flat second.
4. **Dark without scaling**: exact exposure match. In CMOS the thermal pattern
   does not scale well with time, so a dark at another exposure leaves a residual.
5. **In memory by default**, with optional **export** of calibrated FITS (hundreds
   of 32 MB files are not duplicated unless the user asks).
6. **Reusable step**: its own tab in the unified FITS editor and a master library
   managed from Settings. Series photometry will benefit too.

**Alternatives**: delegate calibration to external software (rejected: the faint
object does not emerge and the flow splits across two tools); use `ccdproc` for
everything (authorised by ADR-060, but the arithmetic is simple and `ccdproc` is
irregularly maintained; astropy + numpy is preferred); scale the dark (rejected in
CMOS due to residual).

**Consequences**: additive migration v16 (`calib_masters`); the engine returns
plain-language warnings instead of exceptions when a piece is missing; and
calibration becomes the first phase of the astrometry pipeline and an improvement
for photometry. Tests with synthetic masters: exact arithmetic, tolerance
matching and absence without exception.

**Revision (2026-10-06): calibration is a service, not one engine's tab**. It
was asked to be usable beyond astrometry, and the previous state got in the way
by being confusing: the pseudo-flat policy was **duplicated** (a checkbox in the
Calibration tab that read `calib_pseudo_flat` and **never** wrote it, and one in
Settings that did write it and was the one the stack read), so the switch the
observer touched was not the one that worked; and the "Apply the calibration to
the stack" checkbox was **not saved** (it reset on every rebuild). What changes:

- **One home for the recipe, the library and the pseudo-flat policy**: the
  Calibration tab. Its pseudo-flat checkbox now **writes** the key and is the
  only one; the Settings one is retired (Settings keeps the master library). Its
  button is told apart from "apply": it is a one-off pass over the visit that
  exports copies if asked.
- **Every engine opts in with its own checkbox**, next to where it is launched:
  in Astrometry, "Apply the calibration to the stack" (`calib_astrometry`),
  persisted. A **one-line hint** says before the run what will happen to the
  pixels (dark/bias, a real or pseudo flat, or that the vignetting stays), taken
  from the **same** resolved recipe (one source, through the host), and a
  **"Calibration…"** button is the deep link to the tab, like the photometry
  recipe's.
- **Extending it is one checkbox**: when the photometric series wants to
  calibrate, it adds its own `chk_calibrate`, hint and link, and reads the same
  recipe and the same `FrameCalibrator`. Nothing to dismantle.

**Revisión (2026-10-06): el defecto de la calibración sigue a la biblioteca.**
Con los ajustes escondidos (ADR-038 rev), el valor por defecto es el que manda,
y «apagada» no era el bueno: la calibración quita el viñeteado y el polvo del
tren óptico, y medido en una visita real el viñeteado suave solo ya vale 0.087
mag de error sistemático. La clave `calib_astrometry` pasa a **tres estados**:

- **ausente** = nadie ha elegido todavía, y decide la biblioteca: la casilla se
  enciende si la receta resuelta tiene un **offset o un flat real** para esa
  cámara y ese filtro (`UfeCalibrationTab.has_masters()`, reenviado por el
  diálogo). Un «no lo sé» (sin visita, primer frame ilegible) la deja apagada:
  encenderla sin saberlo prometería una calibración que nadie ha verificado.
- **0 / 1** = la palabra del observador, y no se pisa nunca.

Dos detalles que la implementación respeta: la elección automática **no se
escribe** (se marca la casilla con `blockSignals`, así el `toggled` no la
guarda como si fuera del observador y la congelaría para siempre), y el
subtítulo del botón dice qué masters se aplican, para que el defecto no sea
invisible.

**Revision (2026-10-06): the calibration's default follows the library.** With
the knobs hidden (ADR-038 rev) the default is what decides, and "off" was not
the right one: the calibration removes the optical train's vignetting and dust,
and measured on a real visit the smooth vignetting alone is worth 0.087 mag of
systematic error. The `calib_astrometry` key becomes **three-state**:

- **absent** = nobody has chosen yet, and the library decides: the checkbox
  comes on when the resolved recipe has an **offset or a real flat** for this
  camera and filter (`UfeCalibrationTab.has_masters()`, forwarded by the
  dialog). An "I do not know" (no visit, unreadable first frame) leaves it off:
  turning it on without knowing would promise a calibration nobody verified.
- **0 / 1** = the observer's word, and it is never overridden.

Two details the implementation respects: the automatic choice is **not
written** (the box is set with `blockSignals`, so the `toggled` does not save it
as if it were the observer's and freeze it forever), and the button's subtitle
says which masters are applied, so the default is never invisible.

**Revisión (2026-10-06): un flat no comparte la ganancia, y el pseudo-flat que
lleva las estrellas se sustituye por un modelo suave.** Tres correcciones
medidas sobre las visitas reales del autor (2025 FG18 y 2025 HL5):

1. **La ganancia sale del emparejamiento del flat.** Un flat se **normaliza**
   antes de aplicarse, así que la ganancia solo escala su nivel entero, nunca su
   forma: exigirla era rechazar flats reales. Medido: los flats de esa noche se
   tomaron a ganancia 3 y las tomas a ganancia 5, así que la biblioteca
   respondía «no hay flat» y la visita caía al pseudo-flat. El **dark sí la
   conserva** (ahí el nivel ES la señal) y el dark de los flats también.
2. **La biblioteca se rellena desde donde se lee la receta.** El botón «Añadir
   masters…» vive ahora en la pestaña Calibración del editor (con su combo de
   tipo), no solo en Ajustes: un observador con 150 flats de una noche no tenía
   forma de meterlos desde donde se lee la receta. El diálogo abre el selector y
   el host indexa (la pestaña nunca toca la base de datos), y la línea de la
   receta se vuelve a resolver para que se vea qué cambió.
3. **Un flat que lleva las estrellas es peor que ningún flat.** Con montura
   sidereal las estrellas no se mueven entre tomas y el percentil las conserva:
   cada estrella se divide por sí misma. Medido en esa visita (16 tomas):
   `residual_pct = 2.8091`, rango del flat 0.683–2.724, y una comparada sobre
   una estrella brillante salía 1.08 mag desviada. Lo que sí queda de esas tomas
   es el **viñeteado**, que es suave y fijo: se enmascaran las fuentes (lo que
   está a más de 5σ sobre el percentil suavizado, dilatable 12 px) y se ajusta
   una superficie de grado 4. Medido contra el flat real de la misma noche: la
   relación tiene mediana 0.9963 y p5–p95 0.954–1.045 (concuerda al ~3 %); la
   estructura fina que no corrige (el polvo) vale 0.611 % = 0.007 mag. El
   resultado se dice por lo que es (`kind = "vignette_model"`), nunca como un
   flat completo.

**Revision (2026-10-06): a flat does not share the gain, and a pseudo-flat that
carries the stars becomes a smooth model.** Three fixes measured on the author's
real visits (2025 FG18 and 2025 HL5):

1. **The gain leaves the flat's match.** A flat is **normalised** before it is
   applied, so the gain only scales its whole level, never its shape: requiring
   it rejected real flats. Measured: that night's flats were taken at gain 3 and
   the lights at gain 5, so the library answered "no flat" and the visit fell
   back to a pseudo-flat. The **dark keeps it** (there the level IS the signal),
   and so does the dark of the flats.
2. **The library is filled from where the recipe is read.** The "Add masters…"
   button now lives in the editor's Calibration tab (with its kind combo), not
   only in Settings: an observer with 150 flats of one night had no way to put
   them in from where the recipe is read. The dialog opens the picker and the
   host indexes (the tab never touches the database), and the recipe line is
   resolved again so what changed is visible.
3. **A flat that carries the stars is worse than no flat.** With a sidereal
   mount the stars do not move between frames and the percentile keeps them:
   every star is divided by itself. Measured on that visit (16 frames):
   `residual_pct = 2.8091`, flat range 0.683–2.724, and a comparison star
   sitting on a bright star came out 1.08 mag off. What IS usable from those
   frames is the **vignetting**, which is smooth and fixed: the sources are
   masked (what is more than 5σ above the smoothed percentile, dilated by
   12 px) and a degree-4 surface is fitted. Measured against the real flat of
   the same night: the ratio has a median of 0.9963 and p5–p95 of 0.954–1.045
   (agreement within ~3 %); the fine structure it does not correct (the dust) is
   worth 0.611 % = 0.007 mag. The result is said for what it is
   (`kind = "vignette_model"`), never as a full flat.

**Revisión (2026-10-07): el pseudo-flat deja de rendirse, y el pedestal se
quita (ADR-069)**. El punto 3 de arriba describía una rendición, y era
correcta para el código de entonces: la máscara se calculaba **después** del
estadístico, así que las estrellas ya estaban dentro y lo único que quedaba era
devolver un modelo suave, que no es un flat (no corrige el polvo). Ahora la
máscara se calcula **antes**, los píxeles enmascarados se tiran y el flat se
interpola ahí (una convolución normalizada), así que un campo estático da un
flat de resolución completa, con polvo y **sin ninguna estrella**: medido
contra el master real de esa misma noche (150 flats), el máximo sin píxeles
calientes pasa de 2,83 a **1,1136** contra el 1,1102 del real, y la desviación
sobre los píxeles enmascarados de 33,83 % a **2,05 %**.

Y el pseudo-flat lleva el pedestal de las tomas (`flat_obs = P + cielo × R`),
que la normalización no quita: la forma salía **comprimida** y corregía solo el
44 % del viñeteado en tomas de 1 s de crepúsculo (pedestal de 827 ADU sobre un
cielo de 661). Ahora se construye de las tomas **con el offset ya restado**, el
mismo master que usa la receta; sin master de offset la app lo dice y pide un
bias. Esto además arregla un fallo que existía: con master de offset, la toma
llegaba sin pedestal y se dividía por un flat que sí lo llevaba.

El criterio de «¿lleva estrellas?» también cambia: el residuo era una **MAD
escalada**, robusta por construcción, y un flat con un máximo de 2,83 la movía
0,01 puntos (0,06 % contra 0,05 %). Ahora se mide la desviación sobre el
suavizado **en los píxeles que se enmascararon**, que separa limpiamente
(33,83 % contra 2,05 %). El residuo se conserva como cifra. Y el flat se
escribe a FITS como producto de la visita, para poder mirarlo en el editor: un
flat que nadie puede mirar es un flat que nadie puede comprobar.

**Revision (2026-10-07): the pseudo-flat stops giving up, and the pedestal is
removed (ADR-069)**. Point 3 above described a surrender, and it was right for
the code of the time: the mask was computed **after** the statistic, so the
stars were already inside it and the only thing left was to return a smooth
model, which is not a flat (it does not correct the dust). Now the mask is
computed **before**, the masked pixels are dropped and the flat is interpolated
there (a normalised convolution), so a static field gives a full-resolution
flat, with the dust and with **no star in it**: measured against the real
master of that same night (150 flats), the maximum without the hot pixels goes
from 2.83 to **1.1136** against the real flat's 1.1102, and the deviation over
the masked pixels from 33.83 % to **2.05 %**.

And the pseudo-flat carries the pedestal of the frames
(`flat_obs = P + sky x R`), which the normalisation does not remove: the shape
came out **compressed** and it corrected only 44 % of the vignetting on 1 s
twilight frames (a pedestal of 827 ADU over a sky of 661). It is now built from
the frames **with the offset already subtracted**, the same master the recipe
uses; without an offset master the app says so and asks for a bias. This also
fixes a bug that existed: with an offset master, the light arrived without its
pedestal and was divided by a flat that still carried one.

The "does it carry stars?" check changes too: the residual was a **scaled
MAD**, robust by construction, and a flat with a maximum of 2.83 moved it by
0.01 points (0.06 % against 0.05 %). It now measures the deviation from the
smoothed flat **at the pixels that were masked**, which separates cleanly
(33.83 % against 2.05 %). The residual is kept as a figure. And the flat is
written to FITS as a product of the visit, so it can be looked at in the
editor: a flat nobody can look at is a flat nobody can check.
