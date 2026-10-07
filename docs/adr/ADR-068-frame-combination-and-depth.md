# ADR-068: La combinación decide la profundidad, la interpolación decide el aspecto

**Estado / Status**: Accepted · **Fecha / Date**: 2026-10-07

## Español

**Contexto**: el autor pidió comparar nuestros apilados con los de Tycho-Tracker
sobre la misma visita (2025 FG18, 207 fotogramas de 1 s, el NEO C44Q0Z1) y
«igualar su SNR y tener una imagen más limpia». A simple vista el stack de
Tycho se veía mucho menos ruidoso (5,93 ADU/px frente a 9,51). Antes de tocar
nada se midió **profundidad**, que es la magnitud más débil que se puede
detectar con confianza, con el único instrumento que no se deja engañar:
inyectar una fuente de flujo conocido en una copia del stack, medirla con la
misma receta y ver qué vuelve. 40 posiciones limpias en los dos stacks, por un
criterio **absoluto** (100 ADU sobre el cielo, el mismo rasero para los dos) y
8 niveles de flujo entre magnitud 18,2 y 21,3.

La primera lección fue de método: elegir las posiciones con el ruido de cada
stack mueve el resultado **más que el efecto que se mide** (tres corridas
dieron «Tycho +0,19 mag», «nosotros +0,29» y «Tycho +0,24»). La cifra
defendible es la tercera, con el criterio compartido.

**Decisión**, en cuatro partes:

1. **La media recortada sigma es el método por defecto** de la combinación de
   fotogramas, y ahora está medido y garantizado. La mediana **cuesta 0,26
   magnitudes de profundidad** por una razón de estadística pura: la mediana de
   N medidas es 1,25× más ruidosa que su media, y se midió 1,20×.
2. **El stack dice cómo se hizo.** La cabecera lleva `NS_COMB` (el método),
   `NS_ORDER` (el orden de interpolación), `NS_NUSED` (los fotogramas que de
   verdad entraron) y `NS_LEFT` (los que el registro descartó). Sin esas
   cartas, un fichero de hace un mes no dice cómo se combinó, y este estudio
   empezó precisamente porque hubo que deducirlo del ruido.
3. **El orden de interpolación es un ajuste, con el bilineal por defecto.**
   Órdenes 1 y 3 empatan en profundidad y sólo cambian el aspecto, así que el
   defecto pasa a ser el **bilineal (1)**, que da la imagen limpia que se pidió
   a coste cero en profundidad. El cúbico (3) y el quíntico (5) quedan
   disponibles para un campo poblado, donde la nitidez manda.
   **Y esto hay que decirlo con claridad: es presentación, no límite.** Al
   alisar, el ruido por píxel de un stack deja de ser una medida de hasta dónde
   llega, así que la app no lo usa como tal: la profundidad se mide por
   inyección y recuperación (ADR-067) y se decide con la combinación y con los
   fotogramas que entran. Por el mismo motivo, el **barrido de velocidad**
   (que es una medida: decide dónde va el objeto) mantiene su propio orden
   fijo, el cúbico, para que una elección de aspecto no mueva una velocidad
   medida; es la misma razón por la que ya fija su propio método de
   combinación.
   Un matiz medido, y por eso está escrito: el bilineal ensancha la PSF un 3 %,
   y un **filtro adaptado con plantilla fija** (que es como el banco de
   inyección compara tratamientos, a propósito) se desvía 0,12 mag con ese
   desajuste, mientras la **apertura**, que es lo que el pipeline publica, no
   lo nota. La app mide el seeing **en el stack** (`_seeing_on_stack`) y su
   plantilla se adapta, así que las magnitudes que salen no llevan ese sesgo;
   el instrumento de inyección sí lo ve, y por eso su listón quedó escrito con
   el número.
4. **La regla de no apilar un fotograma no verificado se mantiene**, y ahora se
   sabe por qué: en esta visita los 21 rechazados lo fueron por el seeing
   (8,34 px frente a 5,08), no por la alineación, y apilarlos **cuesta 0,11
   magnitudes** porque ensanchan la PSF del stack.

### Las medidas

**La combinación** (mismos 207 fotogramas, misma región, las mismas 40
posiciones de inyección en los cuatro):

| stack | ruido (ADU/px) | magnitud límite a SNR 5 |
|---|---|---|
| el stack que la app había guardado | 10,24 | 17,94 |
| **media recortada sigma** | 8,51 | **18,23** |
| mediana | 10,23 | 17,97 |
| Tycho-Tracker | 5,93 | 18,18 |

El stack guardado coincidía con la mediana (17,94 frente a 17,97, y ruidos
10,24 y 10,23): la corrida se había combinado con mediana. Con el método por
defecto **llegamos 0,05 mag más abajo que Tycho-Tracker** y 0,29 mag más abajo
que aquel stack.

**La interpolación** (mismo motor, mismos fotogramas, mismas posiciones; el
defecto es ahora el orden 1):

| orden | ruido de píxel | magnitud límite | dispersión en r=5 |
|---|---|---|---|
| 1 (bilineal) | 6,58 | 18,20 | 141,1 |
| 3 (cúbico, el actual) | 8,49 | 18,21 | 139,1 |
| 5 | 8,90 | 18,08 | 157,5 |

Empatan en profundidad mientras el ruido de píxel difiere un 29 %: es la
demostración de que **alisar baja el ruido por píxel sin añadir información**.
El bilineal es el mando para tener la imagen limpia que se pedía, y es gratis
en profundidad.

**Los fotogramas que el registro descarta** (21 de 207, todos con `NS_LEFT`):

| stack | ruido | PSF efectiva | dispersión en r=5 | magnitud límite |
|---|---|---|---|---|
| 186 (los verificados) | 8,51 | 6,16 px | 153,6 | **18,11** |
| 207 (todos) | 8,12 | 6,51 px | 168,7 | 18,00 |

Los 21 bajan el ruido un 1,05× (el 10 % de integración que aportan) pero
ensanchan la PSF de 6,16 a 6,51 px, la apertura tiene que crecer y la
dispersión sube un 10 %. El balance es **−0,11 mag**: la regla del motor acierta
al dejarlos fuera.

### Por qué esto importa más allá de esta visita

La profundidad **no es uniforme en el campo**: en un stack que sigue al objeto
el campo se desliza (705 px en esta visita) y la cobertura cambia de zona a
zona. Medido en una rejilla 9×9, el ruido de apertura varía un factor 3,6 en
nuestro stack y 4,0 en el de Tycho. Cualquier «magnitud límite» que se cite es
un promedio, y dónde caiga el objeto importa tanto como la imagen.

**Consecuencias**: el método por defecto queda como estaba (media recortada
sigma) y ahora con su coste medido en el tooltip de la interfaz; el orden de
interpolación pasa a ser un ajuste con el bilineal por defecto
(`astrometry_warp_order`, con el cúbico y el quíntico disponibles) y las dos
elecciones **se guardan** al cambiarlas, que era la raíz del problema: antes se
leían del archivo de ajustes y nunca se escribían, así que una corrida con
mediana no dejaba rastro; la cabecera de cada stack dice cómo se hizo; la regla
del registro se mantiene y se documenta su razón; y el banco de medida (`tools/bench/bench_depth.py`,
`bench_combine.py`, `bench_order.py`, `bench_frames.py`) se conserva, sin
enviarse con la aplicación, para poder repetir la comparación si cambia el
régimen (otra cámara, otro cielo, otro Tycho).

**Alternativas**: igualar a Tycho copiando su alisado (rechazado: el alisado no
compra profundidad, y ya tenemos un mando más barato para el aspecto); subir la
profundidad apilando los fotogramas rechazados (rechazado: cuesta 0,11 mag);
elegir la mediana por su robustez frente a los trazos (rechazado: nuestra media
recortada descarta el 17,5 % de los píxeles y conserva la SNR, así que la
robustez ya está y la mediana sólo añade ruido).

## English

**Context**: the author asked to compare our stacks with Tycho-Tracker's on the
same visit (2025 FG18, 207 one-second frames, NEO C44Q0Z1) and to "match its
SNR and have a cleaner image". To the eye Tycho's stack looked much less noisy
(5.93 ADU/px against 9.51). Before touching anything, **depth** was measured,
which is the faintest magnitude that can be detected with confidence, with the
only instrument that cannot be fooled: inject a source of a known flux into a
copy of the stack, measure it back with the same recipe and see what comes out.
40 clean positions in both stacks, by an **absolute** criterion (100 ADU above
the sky, the same ruler for both) and 8 flux levels between magnitude 18.2 and
21.3.

The first lesson was about method: choosing the positions from each stack's own
noise moves the result **more than the effect being measured** (three runs gave
"Tycho +0.19 mag", "ours +0.29" and "Tycho +0.24"). The defensible figure is
the third one, with the shared criterion.

**Decision**, in four parts:

1. **The sigma-clipped mean is the default method** for combining frames, and it
   is now measured and guaranteed. The median **costs 0.26 magnitudes of
   depth** for a plain statistical reason: the median of N measurements is
   1.25x noisier than their mean, and 1.20x was measured.
2. **The stack says how it was made.** The header carries `NS_COMB` (the
   method), `NS_ORDER` (the interpolation order), `NS_NUSED` (the frames that
   really went in) and `NS_LEFT` (the ones the registration left out). Without
   those cards a month-old file does not say how it was combined, and this
   study started precisely because that had to be deduced from the noise.
3. **The interpolation order is a setting, with the bilinear by default.**
   Orders 1 and 3 tie in depth and only change the look, so the default becomes
   the **bilinear (1)**, which gives the clean image that was asked for at no
   cost in depth. The cubic (3) and the quintic (5) stay available for a
   crowded field, where sharpness rules.
   **And this has to be said plainly: it is presentation, not limit.** By
   smoothing, a stack's pixel noise stops being a measure of how faint it
   reaches, so the app does not use it as one: depth is measured by injection
   and recovery (ADR-067) and decided by the combination and by the frames that
   go in. For the same reason the **velocity sweep** (which is a measurement: it
   decides where the object goes) keeps its own fixed order, the cubic, so that
   a choice about the look cannot move a measured velocity; it is the same
   reason it already pins its own combination method.
   One measured nuance, and it is written down for that reason: the bilinear
   broadens the PSF by 3 %, and a **matched filter with a fixed template**
   (which is how the injection bench compares treatments, on purpose) lands
   0.12 mag off with that mismatch, while the **aperture**, which is what the
   pipeline publishes, does not notice it. The app measures the seeing **on the
   stack** (`_seeing_on_stack`) and its template adapts, so the magnitudes it
   publishes do not carry that bias; the injection instrument does see it, and
   that is why its threshold is written down with the number.
4. **The rule of not stacking an unverified frame stays**, and now its reason is
   known: on this visit the 21 refused frames were refused because of the
   seeing (8.34 px against 5.08), not because of the alignment, and stacking
   them **costs 0.11 magnitudes** because they broaden the stack's PSF.

### The measurements

**The combination** (same 207 frames, same region, the same 40 injection
positions in all four):

| stack | noise (ADU/px) | limiting magnitude at SNR 5 |
|---|---|---|
| the stack the app had saved | 10.24 | 17.94 |
| **sigma-clipped mean** | 8.51 | **18.23** |
| median | 10.23 | 17.97 |
| Tycho-Tracker | 5.93 | 18.18 |

The saved stack matched the median (17.94 against 17.97, and noises 10.24 and
10.23): that run had been combined with the median. With the default method
**we reach 0.05 mag deeper than Tycho-Tracker** and 0.29 mag deeper than that
stack.

**The interpolation** (same engine, same frames, same positions; the default
is now order 1):

| order | pixel noise | limiting magnitude | scatter at r=5 |
|---|---|---|---|
| 1 (bilinear) | 6.58 | 18.20 | 141.1 |
| 3 (cubic, the current one) | 8.49 | 18.21 | 139.1 |
| 5 | 8.90 | 18.08 | 157.5 |

They tie in depth while the pixel noise differs by 29 %: that is the proof that
**smoothing lowers the pixel noise without adding information**. The bilinear
is the knob for the clean image that was asked for, and it is free in depth.

**The frames the registration leaves out** (21 of 207, all with `NS_LEFT`):

| stack | noise | effective PSF | scatter at r=5 | limiting magnitude |
|---|---|---|---|---|
| 186 (the verified ones) | 8.51 | 6.16 px | 153.6 | **18.11** |
| 207 (all) | 8.12 | 6.51 px | 168.7 | 18.00 |

The 21 lower the noise by 1.05x (the 10 % of integration they add) but broaden
the PSF from 6.16 to 6.51 px, the aperture has to grow and the scatter rises by
10 %. The balance is **−0.11 mag**: the engine's rule is right to leave them
out.

### Why this matters beyond this visit

Depth is **not uniform across the field**: in a stack that follows the object
the field slides (705 px on this visit) and the coverage changes from zone to
zone. Measured on a 9x9 grid, the aperture noise varies by a factor of 3.6 in
our stack and 4.0 in Tycho's. Any "limiting magnitude" that gets quoted is an
average, and where the object falls matters as much as the image.

**Consequences**: the default method stays as it was (the sigma-clipped mean)
and now with its cost measured in the interface's tooltip; the interpolation
order becomes a setting with the bilinear by default (`astrometry_warp_order`,
with the cubic and the quintic available) and BOTH choices are **saved** when
they change, which was the root of the problem: they used to be read from the
settings file and never written, so a run combined with the median left no
trace; every stack's header says how it was made; the registration's rule stays
and its reason is documented; and the measurement bench (`tools/bench/bench_depth.py`,
`bench_combine.py`, `bench_order.py`, `bench_frames.py`) is kept, without being
shipped with the application, so the comparison can be repeated if the regime
changes (another camera, another sky, another Tycho).

**Alternatives**: matching Tycho by copying its smoothing (rejected: smoothing
does not buy depth, and we already have a cheaper knob for the look); raising
depth by stacking the refused frames (rejected: it costs 0.11 mag); choosing the
median for its robustness against the trails (rejected: our sigma-clipped mean
discards 17.5 % of the pixels and keeps the SNR, so the robustness is already
there and the median only adds noise).
