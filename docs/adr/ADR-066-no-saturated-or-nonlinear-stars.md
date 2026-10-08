# ADR-066: Nunca una estrella saturada ni por encima de la linealidad

**Estado / Status**: Accepted · **Fecha / Date**: 2026-10-06

## Español

**Contexto**: el cero punto de una medida se construye con estrellas de
comparación (y, cuando la hay, una de control). Si una de esas estrellas está
saturada, su núcleo no es proporcional a la luz que recibió; si está por encima
del límite de linealidad de la cámara, su flujo dejó de seguir a la luz **aunque
no esté recortada todavía**. En los dos casos la estrella **no calibra nada** y
el cero punto que produce es un número que parece correcto y está mal: se lleva
por delante la curva entera sin que nadie lo vea. La parte suave del viñeteado
sin calibrar ya valía 0.087 mag de error sistemático en una visita real, así que
este es el tipo de error que se cuela sin dar la cara.

**Decisión**: la regla de la casa, y es una regla **a fuego**:

> **Nunca se usa una estrella saturada ni una estrella por encima del nivel de
> linealidad de la cámara**, en ningún camino que use el flujo de una estrella
> para calibrar (cero punto, estrella de control, propuesta de comparsas,
> ajuste de apertura o cualquier otro que venga después).

Cómo se hace cumplir:

1. **Un solo sitio para los dos techos**: `photometry.star_ceilings(header,
   cfg, linear_adu, saturate)` devuelve `(saturación, linealidad)`, con la
   tarjeta SATURATE de la cabecera por delante del ajuste y con el valor de la
   receta del run por delante del perfil de cámara. Cada camino los pide ahí:
   la placa suelta, la serie fotométrica, la astrometría, la propuesta de
   comparsas y el ajuste de apertura (T3). Antes cada llamada los pasaba a
   mano, y una se olvidó (el T3 medía la estrella de control sin techos): una
   regla que depende de que cada sitio se acuerde no es una regla.
2. **La medida los obedece en un solo sitio**: `photometry.measure_point`
   devuelve `ok=False` con el motivo **distinto** según el techo que se haya
   tocado («saturada» / «no lineal»), más el recorte inferido de la propia
   placa cuando no hay dato alguno. Una estrella que no es `ok` **no entra**
   en ningún cero punto, y el motivo se dice en el panel.
3. **Si la linealidad no se conoce, se dice**: la app sigue midiendo con el
   mejor techo que tenga (la tarjeta SATURATE o el recorte de la placa) y lo
   avisa con todas las letras (`photometry.ceiling_warning`), en el panel de
   medida y en las notas del run, con el sitio donde se ajusta (Ajustes →
   Perfil de cámara). Medir con un techo que no es el que manda, en silencio,
   es lo contrario de esta regla.

**Consecuencias**: el ajuste de apertura T3 ya no puede afinar con una estrella
recortada; una candidata a comparsa que toque cualquiera de los dos techos se
descarta con su motivo; y el observador ve un aviso cuando le falta el dato de
linealidad, en vez de un cero punto que no puede juzgar. Tests: uno por camino
(placa, serie, ajuste T3, propuesta) y uno del aviso.

## English

**Context**: a measurement's zero point is built from comparison stars (and a
check star when there is one). If one of them is saturated, its core is not
proportional to the light it received; if it is above the camera's linearity
limit, its flux stopped following the light **even though it is not clipped
yet**. In both cases the star **calibrates nothing** and the zero point it
produces is a number that looks right and is wrong: it takes the whole curve
down with it and nobody sees it. The smooth, uncalibrated vignetting alone was
worth 0.087 mag of systematic error on a real visit, so this is the kind of
error that slips in without showing its face.

**Decision**: the rule of the house, and it is a rule **burned in**:

> **A saturated star, or a star above the camera's linearity level, is NEVER
> used**, in any path that uses a star's flux to calibrate (zero point, check
> star, comparison proposal, aperture tuning, or anything that comes later).

How it is enforced:

1. **One home for the two ceilings**: `photometry.star_ceilings(header, cfg,
   linear_adu, saturate)` returns `(saturation, linearity)`, with the header's
   SATURATE card ahead of the setting and the run's own recipe ahead of the
   camera profile. Every path asks there: the single plate, the photometric
   series, the astrometry run, the comparison proposal and the aperture tuning
   (T3). Each caller used to pass them by hand and one forgot (T3 measured the
   check star without ceilings): a rule that depends on every site
   remembering is not a rule.
2. **The measurement obeys in one place**: `photometry.measure_point` returns
   `ok=False` with a **distinct** reason for the ceiling that was hit
   ("saturated" / "nonlinear"), plus the plate's own inferred clip when nothing
   is known. A star that is not `ok` **never enters** a zero point, and the
   reason is said in the panel.
3. **If the linearity is unknown, it is said**: the app keeps measuring with
   the best ceiling it has (the SATURATE card or the plate's clip) and warns in
   plain language (`photometry.ceiling_warning`), in the measurement panel and
   in the run's notes, with the place it is set (Settings → Camera profile).
   Measuring with a ceiling that is not the one that rules, in silence, is the
   opposite of this rule.

**Consequences**: the T3 aperture tuning can no longer tune with a clipped
star; a candidate comparison that touches either ceiling is dropped with its
reason; and the observer sees a warning when the linearity is missing, instead
of a zero point they cannot judge. Tests: one per path (plate, series, T3
tuning, proposal) and one for the warning.
