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

**Revision (2026-09-28)**: the reduction starts from the **Unified FITS Editor**,
next to the sequence it needs (ADR-048 rev.), not from the Analysis tab. The editor
carries a "Transit reduction (EXOTIC)" block for transit projects opened from a
visit; it uses the **open frame** as the reference and the **sequence loaded** in
the editor. The Analysis tab keeps a door that opens the visit there.
