# ADR-072: La ganancia se mide; la cabecera no manda

**Estado / Status**: Accepted · **Fecha / Date**: 2026-10-08

## Español

**Contexto**: la ecuación CCD, que es lo que convierte el ruido de una medida en
una barra de error, cuelga entera de la ganancia (`g`, e-/ADU). Sin ella, el
error de un punto se queda en la dispersión de las comparadas, que es un animal
distinto. La cadena de prioridad que la resuelve vivía en `core/gain.py`
(Ajustes → cabecera → medida en los frames), pero la placa suelta no la usaba y,
sobre todo, **la cabecera iba por delante de la medida**.

El 2026-10-08 se midió la ganancia en las propias tomas del autor (QHY42Pro,
2025 FG18, 1 s, Clear) y el resultado fue contundente:

* la cabecera lleva **`GAIN = 5`** (el ajuste de la cámara) y **`EGAIN = 1.0`**
  (SharpCap lo escribe de relleno: no son los e-/ADU reales);
* la ganancia real, medida por tres vías independientes (transferencia de fotones
  sobre 1020 cajas, var(F1−F2) frente al nivel, y el ruido del cielo de una sola
  toma frente al nivel), es **≈0.11 e-/ADU**; el ruido del cielo (1552 ADU,
  σ = 118 ADU) solo es Poisson con ese valor;
* `photometry.header_instrument` probaba `GAIN` **antes** que `EGAIN`, así que
  leía 5.0; y aun leyendo `EGAIN` habría leído 1.0, que también está mal.

El daño no es cosmético: la ecuación CCD escala como `1/√g`, así que con g = 1 el
error sale **3× más pequeño** de lo que es (y con g = 5, **7×**). Una SN débil
con un error real de 0.1 mag se reportaba con 0.03: el triple de precisión de la
que hay. Y el semáforo de la estrella de control (2,5 σ) quedaba demasiado
estrecho, marcando como no fiable una medida que sí lo era.

**Decisión**:

> **La ganancia de una medida se resuelve en un solo orden: Ajustes → la medida
> en los propios frames → la cabecera.** La medida gana a la cabecera, porque la
> cabecera es una afirmación (puede llevar el ajuste de la cámara o un valor de
> relleno) y la medida es física sobre los datos que se están midiendo. Cuando
> las dos discrepan, la app lo dice.

Cómo se hace cumplir:

1. **La conversión primero**: `header_instrument` lee `EGAIN`/`CCDGAIN` (e-/ADU
   por definición) antes que un `GAIN` suelto (que suele ser el ajuste de la
   cámara).
2. **La medida gana** (`gain.resolve`): con Ajustes vacío, la ganancia medida en
   los frames se usa aunque la cabecera traiga un valor; si no coinciden (factor
   mayor que 1,5), viaja una nota bilingüe. Un observador que fijó su ganancia en
   Ajustes no paga la medida.
3. **Todos los caminos la piden ahí**: la placa suelta (`photometry.measure_plate`),
   la pestaña Medir, la serie (`series_measure._resolve_gain`) y el track & stack
   (`gui/workers.py`). La placa obedece la ganancia resuelta que le pasa el
   llamador; un llamador que no resuelve cae a Ajustes y solo después a la
   cabecera. El panel dice de dónde salió («medida en tus propias tomas», «de la
   cabecera del FITS»).

**Consecuencias**: la barra de error dice la verdad y el semáforo de la control
vuelve a funcionar; el caso de la tarjeta que miente queda cubierto; y la medida
cuesta dos lecturas de frame por visita o run (nada frente a las cientos que la
serie ya hace), que se saltan si el observador fijó la ganancia. Tests: la
prioridad de las palabras clave, la medida que gana a una cabecera que discrepa,
la nota cuando coinciden y cuando no, y la cadena en la pestaña y en la serie.

**Revisión (2026-10-08, la ganancia se recuerda).** En una supernova el
observador suele entregar **una sola imagen**, y una imagen no puede medir la
ganancia: la transferencia de fotones necesita un par de la misma exposición. La
solución no es estimarla de una imagen (depende de que el cielo domine y de
conocer el número de tomas del apilado), sino **medirla cuando se pueda y
recordarla**:

1. **Un almacén** (`core/gain_store.py`, migración 19 de la BD): tabla `gains`
   con la clave `(INSTRUME, GAIN, XBINNING)` y el valor medido, la fuente, la
   fecha y la calidad del ajuste. `remember` guarda o actualiza; `recall`
   devuelve la mejor entrada para la placa. Si la placa no dice su ajuste (un
   apilado no lleva `GAIN`), usa la última medida de esa cámara y lo marca
   (`matched=False`).
2. **La cascada gana un escalón**: Ajustes → frames (fresca) → **recordada** →
   cabecera. La recordada es una medida real y también gana a la cabecera.
3. **Todos los caminos recuerdan**: la pestaña Medir, la serie y el track & stack
   piden `recall` antes de resolver y guardan con `remember` cuando la fuente ha
   sido `frames`. Así el almacén se llena solo cada vez que la app lee un par.
4. **«Medir ganancia…»** (**Ajustes → Cámara**, bajo el campo de la
   ganancia): la acción de una vez para el que solo tiene imágenes. Apunta a una
   carpeta con dos tomas de la misma exposición, mide, enseña `g ± err` + ruido
   de lectura + cajas y lo guarda.

**Consecuencias de la revisión**: el caso de una sola imagen se resuelve en
cuanto el observador tenga un par (las tomas de su visita, o la acción de una
vez); a partir de ahí, cualquier placa suelta usa la recordada sin tocar la
cabecera. La acción cuesta dos lecturas de frame una vez; la recordada, ninguna.
Tests: el almacén (alta, actualización, coincidencia exacta y de respaldo), la
cascada (la recordada gana a la cabecera), la acción y la pestaña.

## English

**Context**: the CCD equation, which is what turns a measurement's noise into an
error bar, hangs entirely on the gain (`g`, e-/ADU). Without it, a point's error
falls back to the scatter of the comparison stars, which is a different animal.
The priority chain that resolves it lived in `core/gain.py` (Settings → header →
measurement on the frames), but the single plate did not use it and, above all,
**the header came before the measurement**.

On 2026-10-08 the gain was measured on the author's own frames (QHY42Pro,
2025 FG18, 1 s, Clear) and the result was blunt:

* the header carries **`GAIN = 5`** (the camera's setting) and **`EGAIN = 1.0`**
  (SharpCap writes it as a placeholder: it is not the real e-/ADU);
* the real gain, measured three independent ways (photon transfer over 1020
  boxes, var(F1−F2) against the level, and a single frame's sky noise against the
  level), is **≈0.11 e-/ADU**; the sky noise (1552 ADU, σ = 118 ADU) is Poisson
  only with that value;
* `photometry.header_instrument` tried `GAIN` **before** `EGAIN`, so it read 5.0;
  and even reading `EGAIN` it would have read 1.0, which is also wrong.

The damage is not cosmetic: the CCD equation scales as `1/√g`, so with g = 1 the
error comes out **3× smaller** than it is (and with g = 5, **7×**). A faint SN
with a real error of 0.1 mag was reported with 0.03: three times the precision it
has. And the check star's semaphore (2.5 σ) was too tight, flagging as unreliable
a measurement that was fine.

**Decision**:

> **A measurement's gain is resolved in one order: Settings → the measurement on
> the frames themselves → the header.** The measurement beats the header, because
> the header is a claim (it can carry the camera's setting or a placeholder) and
> the measurement is physics on the very data being measured. When the two
> disagree, the app says so.

How it is enforced:

1. **The conversion gain first**: `header_instrument` reads `EGAIN`/`CCDGAIN`
   (electrons per ADU by definition) before a bare `GAIN` (which is usually the
   camera's setting).
2. **The measurement wins** (`gain.resolve`): with Settings empty, the gain
   measured on the frames is used even when the header carries a value; if they
   do not agree (factor greater than 1.5), a bilingual note rides along. An
   observer who set their gain in Settings does not pay for the measurement.
3. **Every path asks there**: the single plate (`photometry.measure_plate`), the
   Measure tab, the series (`series_measure._resolve_gain`) and the track & stack
   (`gui/workers.py`). The plate obeys the resolved gain its caller hands in; a
   caller that resolves nothing falls back to Settings and only then to the
   header. The panel says where it came from ("measured on your own frames",
   "from the FITS header").

**Consequences**: the error bar tells the truth and the check star's semaphore
works again; the case of the lying card is covered; and the measurement costs two
frame reads per visit or run (nothing against the hundreds the series is about to
make), which are skipped when the observer set the gain. Tests: the keyword
priority, the measurement beating a header that disagrees, the note when they
agree and when they do not, and the chain in the tab and in the series.

**Revision (2026-10-08, the gain is remembered).** On a supernova the observer
usually hands in **a single image**, and one image cannot measure the gain: the
photon transfer needs a pair at the same exposure. The answer is not to estimate
it from one image (that depends on the sky dominating and on knowing the stack's
frame count), but to **measure it when possible and remember it**:

1. **A store** (`core/gain_store.py`, database migration 19): a `gains` table
   keyed by `(INSTRUME, GAIN, XBINNING)` with the measured value, the source, the
   date and the fit's quality. `remember` stores or updates; `recall` returns the
   best entry for the plate. When the plate does not say its setting (a stack
   carries no `GAIN`), it uses that camera's latest measurement and flags it
   (`matched=False`).
2. **The chain gains a rung**: Settings → frames (fresh) → **remembered** →
   header. The remembered one is a real measurement and beats the header too.
3. **Every path remembers**: the Measure tab, the series and the track & stack
   call `recall` before resolving and store with `remember` when the source was
   `frames`. The store fills itself every time the app reads a pair.
4. **"Measure gain…"** (**Settings → Camera**, under the gain field): the
   one-time action for whoever only has images. Point at a folder with two
   frames of the same exposure, measure, show `g ± err` + read noise + boxes
   and store it.

**Consequences of the revision**: the single-image case is solved as soon as the
observer has a pair (their visit's frames, or the one-time action); from then on
any single plate uses the remembered one without touching the header. The action
costs two frame reads once; the remembered gain, none. Tests: the store (insert,
update, exact and fallback match), the chain (the remembered gain beats the
header), the action and the tab.
