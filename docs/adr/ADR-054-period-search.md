# ADR-054: Búsqueda de período, plegado e informe de fase / period search, folding and the phase report

**Estado / Status**: Accepted · **Fecha / Date**: 2026-09-29

## Español

**Contexto**: NightScribe medía curvas pero no las analizaba. El plegado existía
sólo con un período **de catálogo** (`lightcurve_view.fold_period_d`: VSX para
variables, el período HADS empaquetado): si la estrella no estaba en el catálogo, o
si el observador sospechaba que el período publicado no cuadraba, la herramienta no
tenía nada que decir. El grupo ObSN trabaja con PerWin/PhaseWin y compara sus
curvas con ASASSN, así que el listón del usuario era ese informe: periodograma,
pico, plegado y gráfico.

La restricción de la casa sigue siendo ADR-004 (sin astropy, sin scipy), y el caso
real que abrió la iniciativa (`docs/PLANS/series-quality.md`: V0526 Per) demostró
además que **una sola noche no fija un período**: 3.1 h de una variable de 0.127 d
son menos de un ciclo, y la línea base de 0.128 d deja el pico del periodograma a
merced del alias diario.

**Decisión**: la búsqueda de período es una pieza de primera clase, en numpy puro, y
dice siempre lo que **no** puede saber.

- **`core/periodogram.py`** con tres herramientas:
  - **Lomb-Scargle generalizado con media flotante** (Zechmeister & Kürster 2009),
    ponderado por los errores de cada punto;
  - **PDM de Stellingwerf** (minimización de la dispersión de fase), que no supone
    forma: es la contraprueba honesta para una eclipsante o una variable de tipo
    sierra;
  - **ventana espectral** (|Σ e^{-2πift}|²/N), que enseña en qué períodos el
    **patrón de observación** mete picos (el alias de un día de una sola estación).
- **Rejilla de frecuencias** con sobremuestreo (10 muestras por pico) de la ráfaga
  espectral, tope por cadencia y fondo por la línea base; refinado parabólico del
  pico.
- **FAP por bootstrap**: se barajan las magnitudes (nunca los tiempos, para que el
  patrón y sus alias queden intactos) y se cuenta cuántos barajados alcanzan el pico
  observado.
- **Honestidad primero**: cada resultado trae **ciclos cubiertos**, FAP, los picos de
  la ventana y notas en lenguaje llano ("la línea base cubre solo 1.0 ciclos: el
  período no está fijado por estos datos, solo acotado"; "Lomb-Scargle y PDM no
  coinciden: una ve un armónico o un alias"). Un pico que sólo ve uno de los dos
  métodos se marca como tal.
- **`viz/phase_view.py`**: el informe de dos paneles del grupo ObSN (periodograma
  con niveles de FAP y el pico marcado, a la izquierda; curva plegada a dos ciclos
  **con un color por noche** y media binneada, a la derecha) y el veredicto en texto
  bajo el gráfico. Sigue el camino PNG de los demás gráficos (ADR-010).
- **`gui/phase_dialog.py` + `ui/phase_dialog.ui`** (ADR-005): método, rango de
  períodos, «Buscar», el PNG, el resumen, «Guardar el período en el proyecto» y
  exportación PNG + CSV (periodograma y curva plegada). Dos puertas, como pidió el
  autor: desde la ventana de la visita (Análisis) y desde la pestaña Medir del
  editor.
- **El período encontrado se puede guardar en el proyecto** (`context.period_d`,
  con método, FAP y ciclos), de modo que la curva del proyecto se plega por él. Sólo
  se guarda cuando el observador lo pide y sólo si hay período.
- **Datos de la comunidad**: cuando la línea base no llega a dos ciclos, la salida
  lo dice y ofrece la vía de sumar otra noche o fotometría de la comunidad. La
  fuente AAVSO de `core/sources/aavso.py` (hoy sólo la última magnitud de las
  vigilias) se extiende con la curva completa en una iniciativa aparte, reutilizando
  su token y su caché.

**Alternativas**: `astropy.timeseries.LombScargle` (vetado por ADR-004); una
periodograma sólo de LS (rechazado: una eclipsante estrecha es donde el LS falla y
el PDM brilla, y en una variable de 0.08 mag la discrepancia entre métodos es la
señal de alarma); plegar sin FAP ni ciclos (rechazado: es exactamente cómo se
publica un alias); usar el período VSX y callar (rechazado: el catálogo no siempre
tiene el objeto y el observador debe poder contrastarlo).

**Consecuencias**: una noche de observación se puede analizar de verdad (pico,
plegado, residuo), y con dos o más noches el período se fija; con una sola, la
herramienta lo dice en vez de inventarlo. El coste es un módulo nuevo con sus tests
(sintéticos y con semilla: seno conocido, eclipsante estrecha, ruido puro, la
trampa de una noche) y un diálogo más. El informe del V0526 Per sale con la misma
pinta que el del grupo ObSN, con la advertencia de que 1.0 ciclos no fijan nada.

## English

**Context**: NightScribe measured curves but did not analyse them. Folding existed
only with a **catalogue** period (`lightcurve_view.fold_period_d`: VSX for
variables, the bundled HADS period): if the star was not in the catalogue, or if the
observer suspected the published period did not fit, the tool had nothing to say.
The ObSN group works with PerWin/PhaseWin and cross-checks its curves against
ASASSN, so that report was the user's bar: periodogram, peak, folding and a chart.

The house constraint is still ADR-004 (no astropy, no scipy), and the real case that
opened the initiative (`docs/PLANS/series-quality.md`: V0526 Per) proved something
else too: **a single night does not fix a period**. 3.1 h of a 0.127 d variable is
less than one cycle, and a 0.128 d baseline leaves the periodogram peak at the mercy
of the daily alias.

**Decision**: the period search is a first-class piece, in pure numpy, and it always
says what it **cannot** know.

- **`core/periodogram.py`** with three tools:
  - the **generalised Lomb-Scargle periodogram with a floating mean**
    (Zechmeister & Kürster 2009), weighted by each point's own error;
  - **Stellingwerf's PDM** (phase dispersion minimisation), which assumes no shape:
    the honest cross-check for an eclipsing or a sawtooth variable;
  - the **spectral window** (|Σ e^{-2πift}|²/N), which shows the periods the
    **observing pattern** itself peaks at (the daily alias of a single-site run).
- **Frequency grid** oversampled (10 samples per spectral peak), capped by the
  cadence and floored by the baseline, with parabolic peak refinement.
- **Bootstrap FAP**: the magnitudes are shuffled (never the times, so the pattern
  and its aliases stay intact) and the share of shuffles reaching the observed peak
  is counted.
- **Honesty first**: every result carries the **cycles covered**, the FAP, the
  window peaks and plain-language notes ("the baseline covers only 1.0 cycles: the
  period is not fixed by this data, only bounded"; "Lomb-Scargle and PDM disagree:
  one of them is seeing a harmonic or an alias"). A peak only one of the two methods
  sees is flagged as such.
- **`viz/phase_view.py`**: the ObSN group's two-panel report (periodogram with the
  FAP levels and the peak marked, at the left; the curve folded to two cycles
  **coloured by night** with a binned mean, at the right) and the verdict as text
  under the chart. It follows the PNG path of the other charts (ADR-010).
- **`gui/phase_dialog.py` + `ui/phase_dialog.ui`** (ADR-005): method, period range,
  "Search", the PNG, the summary, "Save the period to the project" and a PNG + CSV
  export (periodogram and folded curve). Two doors, as the author asked: from the
  visit window (Analysis) and from the editor's Measure tab.
- **The period found can be saved into the project** (`context.period_d`, with its
  method, FAP and cycles), so the project's curve folds by it. It is saved only when
  the observer asks, and only when there is a period.
- **Community data**: when the baseline does not reach two cycles, the output says
  so and offers another night or community photometry. The AAVSO source in
  `core/sources/aavso.py` (today only the latest magnitude for vigils) gets the full
  curve in a separate initiative, reusing its token and cache.

**Alternatives**: `astropy.timeseries.LombScargle` (vetoed by ADR-004); an LS-only
periodogram (rejected: a narrow eclipsing binary is where LS fails and PDM shines,
and on a 0.08 mag variable the disagreement between the two is the alarm signal);
folding with neither FAP nor cycles (rejected: that is exactly how an alias gets
published); using the VSX period and saying nothing (rejected: the catalogue does not
always have the object, and the observer must be able to contradict it).

**Consequences**: one night of observation can be analysed properly (peak, fold,
residual), and two or more nights fix the period; with one, the tool says so instead
of inventing it. The cost is a new module with its tests (seeded synthetic anchors: a
known sine, a narrow eclipser, pure noise, the one-night trap) and one more dialog.
The V0526 Per report comes out looking like the ObSN group's, with the warning that
1.0 cycles fix nothing.
