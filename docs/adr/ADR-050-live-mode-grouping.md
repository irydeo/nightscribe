# ADR-050: Live mode and grouping of short exposures

**Estado / Status**: Accepted · **Fecha / Date**: 2026-09-27

## Español

**Contexto**: con CMOS/sCMOS de lectura rápida (Gsense 400 del usuario, y su
literatura: QHY42Pro y las notas de medidas con la QHY42) la cadencia útil se
consigue exponiendo corto y **agrupando**, y el usuario quiere ver la curva
formarse mientras el telescopio sigue. Ambas cosas deben convivir con la serie
normal sin duplicar código.

**Decisión**: agrupar en el dominio de la medida, y componer el modo en vivo sobre
el mismo motor.

- **Agrupación (nunca apilado de píxeles)**: se mide **cada sub-toma** con
  `measure_plate` y se combinan los **flujos** con pesos `1/σ²` y veto MAD (mínimo
  2 tomas válidas); el error del grupo incluye el centilleo de Young integrado
  sobre su span temporal; el tiempo efectivo es la media ponderada de los medios de
  los miembros. Apilar en píxel destroza la fotometría de precisión y el modelo de
  error, así que queda descartado de raíz.
- **ExoClock**: con agrupación, el arranque exportado es
  `media de los medios − integración total/2`, documentado en el `ExoClock_info.txt`
  (ADR-049).
- **Composición con en vivo**: el driver de la fase 10 cierra un punto cuando el
  grupo se completa (N tomas o T segundos); se hacen commits de SQLite agrupados (5
  frames o 10 s) y se notifica por lote (`notify_points`); **un solo motor**: el
  mismo `measure_series`.
- **En vivo sin resolver**: los ficheros de la sesión en vivo **no necesitan
  astrometría**: la serie se siembra desde la placa de referencia (WCS o clic) y
  sigue por centroide; si hay un salto grande se marca `guide_jump` y se reancla;
  la anotación degrada con «sin WCS» en vez de mentir (ADR-048).
- **Guardia de cadencia**: agrupar cambia la cadencia efectiva, así que la capa de
  análisis avisa (≥3 puntos por ingress en tránsitos, HADS: 12 puntos y tope de
  cadencia, Nyquist en variables) y **ponga rojo si se rompe el ingress**; por
  defecto `group_n=1` en tránsitos y variables, donde agrupar es un riesgo. La
  agrupación es opt-in y aplica a **todos** los tipos de secuencia.
- **Polling**: sondeo de carpeta ~2 s con chequeo de estabilidad de tamaño antes de
  leer (nunca un fichero a medias).

**Alternativas**: apilar en píxel para «ganar SNR» (rechazado: contamina el error y
la forma del dip); un motor aparte para en vivo (rechazado: dos motores, dos
precisiones); exigir WCS por frame en vivo (rechazado: retrasa la curva y aporta
nada medible); agrupar por defecto en todo (rechazado: rompe la cadencia de
tránsitos y variables; se avisa en vez de bloquear).

**Consecuencias**: exposiciones de pocos segundos son usables sin cavar el rms;
la curva en vivo nace ya con flags y errores honestos; el rendimiento depende de
medir N frames en vez de N, pero el presupuesto de <0,5 s/frame sigue vigente por
frame; el usuario puede deshacer la corrida igual que en el flujo normal.

## English

**Context**: with fast-read CMOS/sCMOS cameras (the user's Gsense 400, and their
literature: QHY42Pro plus the QHY42 measurement notes) the useful cadence comes
from short exposures **grouped** together, and the user wants to watch the curve
grow while the telescope tracks. Both must live alongside the normal series
without duplicated code.

**Decision**: group in the measurement domain, and layer live mode on the same
engine.

- **Grouping (never pixel stacking)**: every **sub-exposure** is measured with
  `measure_plate` and the **fluxes** are combined with `1/σ²` weights and an MAD
  veto (≥2 valid exposures); the group error includes Young scintillation
  integrated over its time span; the effective time is the weighted mean of the
  members' mid-times. Pixel stacking breaks precision photometry and the error
  model, so it is ruled out.
- **ExoClock**: with grouping the exported start is `mean of mid-times − total
  integration/2`, documented in the `ExoClock_info.txt` (ADR-049).
- **Composition with live mode**: the phase-10 driver closes a point when the group
  completes (N frames or T seconds); SQLite commits are batched (5 frames or 10 s)
  and points are notified per batch (`notify_points`); **one engine**: the same
  `measure_series`.
- **Live without solving**: live session files **need no astrometry**: the series
  seeds from the reference plate (WCS or a click) and tracks by centroid; a large
  jump sets the `guide_jump` flag and re-anchors; annotation degrades with a
  "no WCS" note instead of lying (ADR-048).
- **Cadence guard**: grouping changes the effective cadence, so the analysis layer
  warns (≥3 points per ingress for transits, HADS: 12 points and cadence cap,
  Nyquist for variables) and **turns red if the ingress breaks**; `group_n=1` by
  default for transits and variables, where grouping is a risk. Grouping is opt-in
  and applies to **every** sequence type.
- **Polling**: ~2 s folder polling with a size-stability check before reading
  (never a half-written file).

**Alternatives**: pixel stacking to "gain SNR" (rejected: it contaminates the error
and the dip shape); a separate live engine (rejected: two engines, two precisions);
requiring per-frame WCS in live mode (rejected: it delays the curve and buys
nothing measurable); grouping on by default (rejected: it breaks transit and
variable cadence; we warn instead of blocking).

**Consequences**: a few-second exposure becomes usable without digging into the
rms; the live curve is born with honest flags and errors; performance scales with
measuring N frames instead of 1, but the <0.5 s/frame budget still holds per frame;
the run can be undone exactly like in the normal flow.
