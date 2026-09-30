# ADR-052: EXOTIC orchestration (external run and result import)

**Estado / Status**: Accepted · **Fecha / Date**: 2026-09-27

## Español

**Contexto**: el plan de fotometría de series (`docs/PLANS/series-photometry.md`)
reabrió ADR-015 con la vía numpy puro como primera. Sobre el set real de 142 FITS
de MicroObservatory (HAT-P-32 b, sin WCS, frames que se desplazan y rotan,
saturados) la reducción propia no alcanza la precisión de EXOTIC: el motor de
ajuste numpy es correcto (paridad de modelo <1e-5 frente a batman), pero el
dato reducido por nosotros queda a decenas de mmag frente a un tránsito de
26 mmag. EXOTIC resuelve la reducción, pero no puede embeberse: necesita
Python ≤3.10 y astropy/scipy/pylightcurve/ultranest (ADR-004).

**Decisión**: **orquestar EXOTIC como herramienta externa**, sin copiar su
código:

- La app prepara y valida un entorno EXOTIC privado (Python ≤3.10 + `pip
  install exotic`) desde Ajustes (`core/exotic_env.py`).
- Genera el `inits.json` de la visita (`core/exotic.make_inits_for_visit`):
  carpeta de tomas, objetivo y comparaciones en píxeles (forma de cadena del
  sample), sin pedir comparaciones a AAVSO (headless fiable).
- Lo ejecuta headless: `exotic -red <inits.json> -ov`, con log fusionado,
  cancelación y timeout (`core/exotic_run.py`); `-ov` evita el prompt de
  parámetros contra el NASA Archive.
- **Importa** su curva y sus parámetros (T_mid, Rp/Rs, profundidad,
  inclinación, duración) al proyecto (`core/exotic_import.py`): la curva entra
  como puntos `source="exotic"` en una ejecución, y los parámetros en el contexto
  y el reporte.
- La vía numpy (`core/series_measure.py`, `core/transit_fit.py`) queda como
  **previsualización** y su ajuste se valida **contra la curva reducida por
  EXOTIC**.

**Alternativas**: portar los algoritmos de EXOTIC a numpy (rechazado: licencia
Caltech/JPL y dependencias astroalign/astropy/scipy, ADR-004); meter EXOTIC
dentro del instalador (rechazado: segundo Python y stack pesado en Windows);
dejar solo el handoff manual (insuficiente: no cierra el ciclo).

**Consecuencias**: el usuario cierra el flujo de tránsito sin salir de la app;
la app se mantiene ligera (EXOTIC es externo, opcional); la compuerta de paridad
mide ya el ajuste y pasa (T_mid 2 s, Rp/Rs 1,2 %, σ 96 %, profundidad 2,3 %);
sin entorno EXOTIC, la serie y su previsualización siguen funcionando. La
primera ejecución de EXOTIC necesita red (NASA Archive, LDTk, astrometry.net).

## English

**Context**: the photometric-series plan (`docs/PLANS/series-photometry.md`)
reopened ADR-015 with the pure-numpy path first. On the real 142-frame
MicroObservatory set (HAT-P-32 b, no WCS, drifting and rotating frames,
saturated) the in-house reduction does not reach EXOTIC's precision: the numpy
fit engine is correct (model parity <1e-5 against batman), but our reduced data
sits at tens of mmag against a 26 mmag transit. EXOTIC solves the reduction but
cannot be embedded: it needs Python <= 3.10 and astropy/scipy/pylightcurve/
ultranest (ADR-004).

**Decision**: **orchestrate EXOTIC as an external tool**, without copying its
code:

- The app prepares and validates a private EXOTIC environment (Python <= 3.10 +
  `pip install exotic`) from Settings (`core/exotic_env.py`).
- It writes the visit's `inits.json` (`core/exotic.make_inits_for_visit`):
  frames folder, target and comparisons in pixels (EXOTIC's sample string
  form), without fetching comparison stars from AAVSO (reliable headless).
- It runs it headless: `exotic -red <inits.json> -ov`, with a merged log,
  cancellation and timeout (`core/exotic_run.py`); `-ov` skips the parameter
  prompt against the NASA Archive.
- It **imports** its light curve and parameters (T_mid, Rp/Rs, depth,
  inclination, duration) into the project (`core/exotic_import.py`): the curve
  lands as `source="exotic"` points in a run, and the parameters in the context
  and the report.
- The numpy path (`core/series_measure.py`, `core/transit_fit.py`) becomes a
  **preview** and its fit is validated **against EXOTIC's reduced curve**.

**Alternatives**: porting EXOTIC's algorithms to numpy (rejected: Caltech/JPL
licence and astroalign/astropy/scipy dependencies, ADR-004); embedding EXOTIC
in the installer (rejected: a second Python and a heavy stack on Windows);
keeping only the manual handoff (insufficient: it does not close the loop).

**Consequences**: the user closes the transit flow without leaving the app; the
app stays light (EXOTIC is external, optional); the parity gate now measures the
fit and passes (T_mid 2 s, Rp/Rs 1.2 %, sigma 96 %, depth 2.3 %); without an
EXOTIC environment, the series and its preview keep working. EXOTIC's first run
needs network (NASA Archive, LDTk, astrometry.net).

**Revisión (2026-09-28)**: la reducción arranca desde el **Editor FITS unificado**,
junto a la secuencia que necesita (ADR-048 rev.), no desde la pestaña Análisis. El
editor expone un bloque «Reducción de tránsito (EXOTIC)» para proyectos de tránsito
abiertos desde una visita; usa la **toma abierta** como referencia y la **secuencia
cargada** en el editor. La pestaña Análisis deja un acceso que abre la visita ahí.
Toda la cadena de recogida/sondeo muestra un **diálogo de progreso** (con Cancel), y
la secuencia sobrevive al paso de auto-resolución (antes se perdía cuando la toma de
referencia no tenía WCS, y la reducción fallaba con "no hay estrellas de
comparación" aunque estuviera construida). La carpeta de trabajo
`<proyecto>/exotic/` se crea antes de escribir el `inits.json` (antes no existía y
el lanzamiento moría con `FileNotFoundError` justo al cerrarse el diálogo: la
ventana parpadeaba y "no pasaba nada"), y el lanzamiento va **envuelto para que
cualquier error salga en un aviso**, nunca en la consola.

**Revisión (2026-09-30)**: la app **no pide la solución de placa a
astrometry.net**. El `inits.json` va con `"Plate Solution? (y/n)" = "n"`: con
«y», EXOTIC sube la primera toma a nova.astrometry.net y sondea la cola pública
**antes** de mirar la WCS del FITS, con 10 reintentos por etapa y esperas de 4 a
37 s (medido: unos 4 min por corrida, y fallando más veces de las que acertaba).
El síntoma era el spinner «Thinking | ...» repitiéndose minutos, que se lee como
un cuelgue. Con «n», EXOTIC usa la WCS que ya traiga el FITS; si la toma no tiene
ninguna, alinea los frames con astroalign, toma la escala de IM_SCALE/PIXSCALE (o
de nuestro `optional_info`) y la masa de aire de la RA/Dec del inits, así que la
reducción corre igual, sin red y al instante. Se pierden el chequeo VSX de las
comparadas y el reencuadre del píxel del objetivo, que solo informan. En la misma
revisión: el lector del log ya no puede quedarse colgado si EXOTIC muere dejando
el tubo abierto (drena lo que quede y sale, en vez de esperar al timeout de dos
horas), el resultado distingue el **timeout** de un fallo, y el diálogo de
progreso descarta el spinner y traduce «Finding transformation i of N» a «Toma i
de N».

La misma revisión rellena las **incertidumbres** del archivo en el `inits.json`
(período, tiempo de tránsito, Rp/Rs y a/Rs propagadas desde `pl_radj`/`st_rad` y
`pl_orbsmax`/`st_rad`, inclinación, Teff, [Fe/H], log g) y el **argumento del
periastro**. Sin ellas EXOTIC las sustituye por 1 (`exotic.py:1996-2002`) y la
ventana donde ajusta el tiempo de tránsito se vuelve tan ancha que la búsqueda
de apertura/comparada **no puede ajustarlo**: medido sobre el set de HAT-P-32 b
(142 tomas), 3 valores distintos de `tmid` en 3809 ajustes de la búsqueda frente
a 1289 con las incertidumbres, y el T_mid final pasó de ±0,0019 a ±0,0011 d (de
1σ a 0,5σ del valor publicado). La `Observation date` sale ya de la **cabecera de
las tomas** (MJD-OBS, con DATE-OBS de respaldo): un set de diciembre de 2017 se
entregaba fechado «hoy» (30-September-2026) y EXOTIC nombraba así todas las
salidas, figuras y el reporte AAVSO.

**Revision (2026-09-28)**: the reduction starts from the **Unified FITS Editor**,
next to the sequence it needs (ADR-048 rev.), not from the Analysis tab. The editor
carries a "Transit reduction (EXOTIC)" block for transit projects opened from a
visit; it uses the **open frame** as the reference and the **sequence loaded** in
the editor. The Analysis tab keeps a door that opens the visit there. The whole
gather/probe chain shows a **progress dialog** (Cancel included), and the sequence
survives the auto-solve step (it used to be dropped when the reference frame had no
WCS, so the reduce failed with "no comparison stars" although it was built). The
`<project>/exotic/` work folder is created before writing the `inits.json` (it did
not exist, so the launch died with `FileNotFoundError` right as the dialog closed:
the window flashed and "nothing happened"), and the launch is **wrapped so any
error lands in a message box**, never in the console.

**Revision (2026-09-30)**: the app **does not ask astrometry.net for a plate
solution**. The `inits.json` carries `"Plate Solution? (y/n)" = "n"`: with "y",
EXOTIC uploads the first frame to nova.astrometry.net and polls the public queue
**before** looking at the frame's own WCS, with 10 retries per stage and waits of
4 to 37 s (measured: about 4 min per run, and failing more often than it
succeeded). The symptom was the "Thinking | ..." spinner repeating for minutes,
which reads as a hang. With "n", EXOTIC uses the WCS the FITS already carries; if
the frame has none, it aligns the frames with astroalign, takes the scale from
IM_SCALE/PIXSCALE (or our `optional_info`) and the airmass from the target RA/Dec
in the inits, so the reduction runs just the same, offline and at once. What is
lost is the VSX check on the comparisons and the target-pixel reframing, both
informational. In the same revision: the log reader can no longer hang when
EXOTIC dies leaving the pipe open (it drains what is left and stops, instead of
waiting for the two-hour timeout), the result tells a **timeout** apart from a
failure, and the progress dialog drops the spinner and turns "Finding
transformation i of N" into "Frame i of N".

The same revision fills the archive **uncertainties** into the `inits.json`
(period, transit time, Rp/Rs and a/Rs propagated from `pl_radj`/`st_rad` and
`pl_orbsmax`/`st_rad`, inclination, Teff, [Fe/H], log g) plus the **argument of
periastron**. Without them EXOTIC replaces each with 1
(`exotic.py:1996-2002`) and the window it fits the transit time in becomes so
wide that its aperture/comparison search **cannot fit the time at all**:
measured on the HAT-P-32 b set (142 frames), 3 distinct `tmid` values in 3809
search fits against 1289 with the uncertainties, and the final T_mid went from
+-0.0019 to +-0.0011 d (1 sigma to 0.5 sigma from the published value). The
`Observation date` now comes from the **frame headers** (MJD-OBS, DATE-OBS as
fallback): a December 2017 set was handed over dated "today"
(30-September-2026) and EXOTIC named every output, figure and the AAVSO report
that way.
