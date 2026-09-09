# Plan — Proyecto de exoplaneta: captura guiada y secuencia con ventana

> **Abierto (2026-09-08)** — documento de diseño, sin implementar aún. Un
> subplan = un commit cuando se ejecute. Derivado de las buenas prácticas de
> Dennis Conti / AAVSO («Observing Exoplanet Transits with Small Telescopes»)
> y del hilo de Cloudy Nights «Tips for capturing exoplanet transits».
> **Enmendado 2026-09-08**: nuevo subplan 4 «Export a EXOTIC (handoff)»; la
> i18n/docs cierran en el subplan 5.

**rama**: `feature/exoplanet-transit-project` (derivada de `feature/object-card`)
**arranca sobre**: `07a29f8` (feature/object-card al día)
**fecha**: 2026-09-08 · **autor**: FJC (con la IA)

## Objetivo

Un proyecto de tránsito de exoplaneta debe decir al observador **cuándo
empezar a capturar**, **cuándo ocurre el tránsito** y **cómo debe ser la
secuencia**, con reglas fotométricas explícitas (no magia). El procesado es
**100% externo** con **EXOTIC** (NASA/JPL, ecosistema Exoplanet Watch/
AAVSO/ExoClock) como herramienta recomendada: NightScribe guía la captura y
**exporta el `inits.json`** que EXOTIC reduce aparte (Python ≤3.10, fuera del
intérprete de NightScribe). No se importan curvas de luz ni se mide O-C.

## Decisiones pactadas (2026-09-08)

| # | Decisión | Valor |
|---|----------|-------|
| 1 | **Proceso externo concreto** | El paso Process queda externo con **EXOTIC** como la reducción recomendada. NightScribe solo **exporta el `inits.json`** (subplan 4) y el usuario corre EXOTIC aparte. Sin importar su salida ni O-C en esta iteración (v2). `transit_view` sigue dibujando el trapecio ideal. |
| 2 | **Exposición fotométrica** | **Heurística v1 por magnitud** de la estrella + escala de placa (tabla explícita y testeable, sin config nueva ni parámetros de cámara adicionales). |
| 3 | **Ventana de captura** | La secuencia pide **baseline + tránsito + baseline**: empezar ≥ `ingress − 0.25·dur` (mín 20 min) y terminar ≥ `egress + 0.25·dur`, para fijar el nivel fuera de tránsito que se compara. Si la baseline no cabe en la ventana segura, aviso en tarjeta y panel. |
| 4 | **Granularidad temporal** | Muestrear el ingress (≈15% de `duration_h`) con ≥ 3 puntos: cadencia máx ≈ `ingress/3` (típico 30–60 s). Aviso si `exposure + overhead > cadencia_máx`. |
| 5 | **Export CCDciel** | Escribir `StartTime = capture_start`, `EndTime = capture_end`, `MandatoryStartTime = True` y **validar contra una exportación real del CCDciel del observatorio** (filosofía ADR-021 con `docs/ccdciel_sequence_sample.targets`). |
| 6 | **Herramienta de reducción** | **EXOTIC** (`rzellem/EXOTIC`): pipeline NASA/JPL de FITS → curva → Mid-Transit Time. Requiere Python ≤3.10 + astropy → se integra por **handoff de fichero**, nunca embebido (ADR-004 no-astropy). |
| 7 | **Integración EXOTIC = handoff** | NightScribe genera el `inits.json` pre-rellenado: planeta desde el **Exoplanet Archive ampliado** (4a), observatorio/cámara/binning/código AAVSO desde **Settings** (4c), filtro y escala de placa del plan. **No se ejecuta ni se lee la salida**. |

## Reglas de ejecución (de WORKFLOWS)

- Un subplan = un commit; cada subplan deja la app funcional con sus tests.
- Tests offscreen, sin red, patrón `tests/unit/test_overview_panel.py`.
- Cabecera GPL en todo `.py`; código en inglés; cadenas GUI por `self.tr()`;
  pares ES/EN por `orbits.pick`.
- i18n (`lupdate`/`lrelease`, ADR-014) y docs en el subplan 5.
- Toda consulta de red pasa por `core/db.py` (caché); nunca `requests` fuera
  de `core/sources/`.

## Contexto clave (exploración 2026-09-08)

- `core/transits.py` `transits_tonight` ya calcula `ingress/mid/egress`,
  `coverage`, `full`, `depth_mmag`, `duration_h`, `v_mag`, `priority`,
  `min_telescope_in`, `oc_min`, `max_alt`, y gating por horizonte en
  **mid-transit** (ADR-015/020) + apertura (`transit_scope_filter`, ADR-015
  update 2026-09-07). **Falta** la ventana de captura recomendada (baseline),
  la cadencia y la exposición.
- El target del planner (`planner.py:373`) viaja con el sub-dict `transit` y ya
  se copia al contexto del proyecto (`_create_project`, `main_window.py:2504`)
  y a `enrich` por el patrón ADR-027 (`_merge_transit_context`).
- La pestaña Plan & Capture es **genérica** (`_build_plan_tab`,
  `main_window.py:1529`): frames×exp, calibración darks/bias, export y control
  CCDciel. Solo NEO tiene ayuda específica. Nada para tránsitos.
- `core/sequence.py`: el formato CCDciel `.targets` real (CONFIG v5) ya soporta
  `StartTime/EndTime/MandatoryStartTime`; hoy se escribe `StartRise="True"` y
  `MandatoryStartTime="False"` (`_ccdciel_times` usa `safe_window`, si existe).
- `core/exposure.py` tiene `plate_scale` y `max_exposure_no_trail`; la
  heurística v1 de tránsito reusará `plate_scale`.
- Frases de «por qué esta noche» (`suggest._fragments` transit) ya hablan de la
  profundidad/duración/prioridad, pero no dicen *cuándo empezar* ni avisan de
  baseline incompleta.
- **EXOTIC** (`rzellem/EXOTIC`, NASA/JPL): pipeline de fotometría de tránsitos
  (FITS → curva normalizada → Mid-Transit Time). El gancho de integración es su
  **`inits.json`** (`user_info` + `planetary_parameters` + `optional_info`), que
  EXOTIC carga para saltarse el asistente. El `pscomppars` actual
  (`exoplanet_archive._FIELDS`) **no trae** `pl_orbincl/pl_orbeccen/st_logg/
  st_metfe/pl_orbsmax/pl_tranmid`; config tiene `lat/lon` pero no elevación,
  tipo de cámara, binning ni código AAVSO. Requiere Python ≤3.10 + astropy →
  integración por fichero (ADR-004).

## Subplanes

### Subplan 0 — Núcleo de evento: ventana recomendada y cadencia
En `core/transits.py`:

- `recommended_window(transit, baseline_frac=0.25, baseline_min_min=20)` →
  `capture_start = ingress − max(0.25·dur, 20 min)` y
  `capture_end = egress + max(0.25·dur, 20 min)`.
- `transits_tonight` enriquece cada resultado con:
  - `capture_start` / `capture_end` (datetimes),
  - `baseline_fits` (la ventana de captura cabe entera en la noche segura),
  - `cadence_max_s = (0.15 · duration_h · 3600) / 3` (≥ 3 puntos en el ingress),
  - `exp_recommended_s` delegando en la heurística del subplan 2.
- El **gate de horizonte se mantiene** en mid-transit (ADR-020): la baseline
  es información de planificación, no un nuevo gate.

**Tests**: unit sin red — campos presentes; baseline mínima de 20 min
respeta/redondea; `baseline_fits` verdadero/falso; cadencia para ingress de
~0.5 h.

### Subplan 1 — Tarjeta y motivo: «empieza a capturar a HH:MM»
- `suggest._fragments` (kind `transit`): frase con la hora de `capture_start`
  («Si quieres la parte fuera de tránsito, empieza a capturar a las HH:MM») y
  aviso ámbar cuando `baseline_fits=False`.
- Ligera penalización en `_observability` cuando `baseline_fits=False` (el
  evento queda a medias). **Sin tocar** `transits.py`; los campos llegan desde
  el subplan 0.

**Tests**: frase con hora; aviso cuando la baseline no cabe; penalización en
el score.

### Subplan 2 — Panel de tránsito en Plan & Capture
En `_build_plan_tab`, bloque específico para `kind == "transit"`:

- **Tira de tiempos**: `capture_start · ingress · mid · egress · capture_end`
  (UTC + local) frente a la ventana segura; aviso si `baseline_fits=False`
  («la parte fuera de tránsito no cabe en tu ventana»).
- **Exposición heurística v1** (explícita, en `core/exposure.py` como
  `recommended_transit_exposure(v_mag, plate_scale)` — tabla por magnitud
  escalada por escala de placa, sin saturación obvia; capada a un máximo
  razonable). Preselecciona `spn_exps`.
- **Cadencia**: muestra `cadence_max_s`; aviso si
  `exposure + overhead > cadencia_máx` («no resuelves el ingress»).
- **Consejos de buena práctica** (Conti/AAVSO + Cloudy Nights), estáticos:
  defocus pequeño y constante + flats por sesión; estrella de comparación en
  el FOV, de brillo/color similar y no variable; filtro banda ancha L/R
  coherente (ExoClock reporta el filtro); mantener el target ≥ 30° y avisar
  de airmass/Luna (reusar `moon_info`).

**Tests**: offscreen — tira visible con datos fake; aviso baseline; exposición
preseleccionada en el spin; aviso de cadencia.

### Subplan 3 — Export con ventana (CCDciel + NINA/CSV)
En `core/sequence.py` + `core/sources/ccdciel.py`:

- Para `kind == "transit"` el contexto lleva `capture_start/capture_end`; el
  export CCDciel escribe `StartTime = capture_start`, `EndTime = capture_end`
  y `MandatoryStartTime = "True"` en `_ccdciel_times` / `_ccdciel_target`
  (hoy `StartRise="True"`, `MandatoryStartTime="False"`).
- **Validación contra el real**: antes de dar el formato por bueno, fijarlo
  contra un `.targets` exportado por el CCDciel del observatorio (como
  `docs/ccdciel_sequence_sample.targets`, ADR-021/030). Hasta entonces queda
  como «best-effort informativo» en el doc/pantalla.
- NINA/CSV: metadata de inicio best-effort (campo `start_time` por fila en CSV;
  metadato en el JSON de NINA).

**Tests**: export con ventana escribe los atributos esperados; sin ventana cae
al comportamiento actual.

### Subplan 4 — Export a EXOTIC (inits.json, handoff)
La reducción de tránsitos de NightScribe es externa con **EXOTIC**: NightScribe
solo escribe su `inits.json` pre-rellenado (filosofía ADR-021 de ficheros de
handover) y el usuario corre EXOTIC en su propio entorno (Python ≤3.10).

**4a. Exoplanet Archive ampliado** (`core/sources/exoplanet_archive.py`):
extender `_FIELDS` con `pl_orbincl`, `pl_orbeccen`, `st_logg`, `st_metfe`,
`pl_orbsmax`, `pl_tranmid` (misma fuente, misma caché; **bump de clave de
caché** porque el JSON cacheado no trae los campos nuevos).

**4b. `core/exotic.py`** (nuevo, sin red):
- `make_inits(ctx, d, cfg)` con la estructura exacta de EXOTIC:
  - `user_info`: lat/lon (config), elevación, tipo de cámara, binning, código
    AAVSO (Settings, 4c), fecha, notas, «Plate Solution (y/n) = y»; **target y
    comparison pixels en `null`** (el usuario los marca en el asistente de
    EXOTIC).
  - `planetary_parameters`: periodo, T0 publicado (`pl_tranmid`, fallback el
    `t0` de ExoClock), `Rp/Rs` (`pl_radj × 0.10045`), `a/Rs`
    (`pl_orbsmax / (st_rad × 0.00465047)`), inclinación, excentricidad, Teff,
    [Fe/H], log g, RA/Dec; **`null` cuando falte** (EXOTIC admite nulos).
  - `optional_info`: escala de placa (`exposure.plate_scale`), exposición del
    plan, filtro (mapeo a los filtros fila AAVSO; L → «N/A» + longitudes de
    onda si no hay mapeo limpio).
- `export_inits(inits, out)` escribe `inits_MM_DD_YYYY__HH_MM_SS.json`
  (convención de nombres de EXOTIC).

**4c. Settings** (`settings_dialog.ui` + `config.py`): `elevation_m`,
`camera_type` (CCD/DSLR/CMOS, default CCD), `pixel_binning` (default 1x1) y
`aavso_code`; i18n ES/EN.

**4d. GUI**: botón **«Export to EXOTIC (inits.json)»** en la pestaña Process;
usa `ctx` + el `enrich` del proyecto (lo que ya muestra la ficha); QFileDialog
con el nombre sugerido; registra el fichero en `project_files`; aviso «corre
EXOTIC en tu entorno Python 3.10».

**Tests**: unit — plantilla con la estructura EXOTIC; conversiones Rp/Rs y
a/Rs; `null` cuando falta el dato; campos nuevos del TAP; nombre de salida.
Funcional: generación con un `ctx`/`d` fake, sin red.

### Subplan 5 — Cierre
`lupdate`/`lrelease` (ES/EN, ≈10–12 cadenas) · revisión corta de **ADR-015**
(ventana recomendada + cadencia + heurística de exposición) y **ADR-019**
(review del paso Plan: bloque transit; Process cita EXOTIC como herramienta
externa) · sección nueva en `docs/WORKFLOWS.es/.md` con los estados finales ·
`pytest tests/unit` verde + funcionales relevantes.

## Orden de ejecución

0 → 1 → 2 → 3 → 4 → 5
(2 depende de 0; 3 depende de 0; 1 depende de 0; 4 es independiente pero vive
en el mismo paso Process; 5 cierra.)

## Fuera de alcance

- Leer la salida de EXOTIC (Mid-Transit Time → O-C, curva real en el post,
  marca observed): **v2**, mantenida fuera para conservar el handoff limpio.
- Lanzar EXOTIC desde NightScribe (subproceso / conda env Python 3.10):
  requiere validación contra el entorno real; el botón de 4d solo escribe el
  fichero.
- Importación de curva de luz observada y ajuste O-C propios (sin EXOTIC).
- `transit_view` sigue dibujando la curva ideal del evento.
- SNR fotométrico real (read noise/gain/sky en config) — posible v2.
- `Sequence_start` vía JSON-RPC sigue fuera (ADR-030, requiere la instancia
  real).

## Riesgos conocidos

- El `MandatoryStartTime` del `.targets` puede comportarse distinto en la
  versión del usuario: la validación contra el real es obligatoria antes de
  prometerlo.
- Heurística v1 de exposición es «guía honesta», no promesa de SNR: el aviso
  debe dejar claro que cada instrumento es distinto.
- El esquema de `inits.json` de EXOTIC evoluciona: fijar contra el actual
  (`docs/inits.json` del repo) y **validar con una corrida real** del usuario
  antes de prometer la compatibilidad.
- Los campos nuevos del TAP invalidan la caché de `exoplanet_archive`
  (bump de clave de caché / expiración corta la primera vez).