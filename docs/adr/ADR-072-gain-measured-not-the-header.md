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
