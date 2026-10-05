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
