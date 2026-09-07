# Plan — Goto con efeméride fresca para cuerpos en movimiento

> **ABIERTO (2026-09-07)** — plan guardado, pendiente de ejecutar. Decisión
> del alcance tomada con el usuario el 2026-09-07 (ver tabla).

**rama**: `feature/goto-fresh-ephemeris` (a crear desde `dev/v0.1` al arrancar)
**fecha**: 2026-09-07 · **autor**: FJC (con la IA)

## Objetivo

Los NEOs, cometas y candidatos PCCP **no tienen coordenadas fijas** (a
diferencia de SN y tránsitos): un NEO a 5″/min con un plan de hace 2 h lleva
10′ de error; un NEOCP rápido a 30″/min, 1° — el goto astrométrico resolvería
el campo equivocado (o «tendría éxito» apuntando a nada). Hoy
`_ccd_goto`/`_ccd_astrometry_goto` (`main_window.py:1906-1943`) usan el
**snapshot** que el planner guardó en `project.context` al crear el proyecto, y
la ficha muestra la fila Horizons de las 00:00 UT (`enrich._enrich_small_body`
usa `eph[0]` con paso diario).

Regla rectora (a fijar como revisión de ADR-030): **para kinds móviles
(`neo`, `comet`, `pccp`) ninguna coordenada almacenada se envía a la montura
sin edad; la posición se calcula para el instante del apuntado**. SN y
tránsitos siguen usando el snapshot fijo.

## Decisiones pactadas (2026-09-07)

| # | Decisión | Valor |
|---|----------|-------|
| 1 | **Obtención de la posición fresca** | **Consulta fina en vivo**: Horizons paso 1-5 min en ventana ±1-2 h alrededor del click, interpolada a «ahora». Fallbacks sin red: elementos SBDB (caché) propagados con Kepler → órbita preliminar NEOfixer → snapshot con aviso. |
| 2 | **UX del Goto** | **Auto + timestamp**: recalcula y apunta sin preguntar; el panel muestra «Posición a las HH:MM:SS UT». El goto astrométrico absorbe el residuo con plate solve. |
| 3 | **Alcance de esta iteración** | **Solo Goto fresco**: recalcular al apuntar + indicador de frescura + coords de ficha «a las HH:MM UT». El cap anti-traza por exposición (`max_exposure_no_trail` + `rate_arcsec_min`) ya existe. `SolarTracking`/`UpdateCoord` en `.targets` y tasas no siderales vía JSON-RPC quedan **fuera** (requieren validación contra el CCDciel real; se anotan en el ADR). |

## Reglas de ejecución (de WORKFLOWS)

- Un subplan = un commit; cada subplan deja la app funcional con sus tests.
- Cabecera GPL en todo `.py`; código en inglés; cadenas GUI por `self.tr()`;
  i18n (`lupdate` incluyendo `gui/widgets/*.py` + `lrelease`) en el cierre.
- Toda consulta de red pasa por `core/db.py` (caché); nunca `requests` fuera
  de `core/sources/`. Red **nunca** en el hilo de GUI (ADR-030).

## Contexto clave (exploración 2026-09-07)

- `Client.slew_target`/`astrometry_goto` reciben J2000 en grados y convierten
  a aparente con `J2000_to_Apparent` (cadena correcta: J2000 fresco → aparente
  al instante del slew). El cliente no tiene método de tasas no siderales.
- `core/ephemeris.py::generate()` ya produce tablas Horizons tiempo-etiquetadas
  con fallback Kepler local para NEOCP (`_preliminary_rows`); la caché Horizons
  (TTL 12 h) tiene `start/stop/step` en la clave → ventana redondeada a 30 min
  para reuso en gotos sucesivos.
- `enrich._enrich_preliminary_orbit` ya calcula la posición **para ahora** con
  `kepler_ra_dec` — patrón a reutilizar en el fallback.
- `_enrich_small_body` usa `eph[0]` (paso diario, 00:00 UT) también para
  `mag_now`/`dist_now` → pedir paso 30 m y elegir la fila más cercana a ahora
  mejora ficha y magnitud a la vez (±15 min de error máx.).
- El formato `.targets` real (`docs/ccdciel_sequence_sample.targets`) incluye
  `UpdateCoord="False"` y `SolarTracking="False"` — palancas para la iteración
  futura de seguimiento no sideral.
- `CcdcielWorker` ejecuta acciones fuera del hilo GUI: la resolución de
  `position_at` va **dentro** de la acción del worker.

## Subplanes

### Subplan 0 — `core/ephemeris.py::position_at(name, site, when=None)`
Devuelve `{ra_deg, dec_deg, rate_arcsec_min, pa_deg, epoch_iso, source,
preliminary}` o `None`. Ventana Horizons `when±2 h` redondeada a 30 min,
paso `"2m"`; interpolación lineal a `when` (desenvolviendo AR en el salto
0h/24h); tasa aparente (″/min) y PA desde filas consecutivas. Cadena de
fallback: Horizons → SBDB+Kepler → NEOfixer preliminar → `None`.
**Tests**: interpolación (incl. salto AR 0h), tasa/PA, fallback completo,
redondeo de ventana.

### Subplan 1 — Goto fresco en `main_window.py`
Si `kind ∈ {neo, comet, pccp}`, la acción del `CcdcielWorker` resuelve
`position_at` antes de `slew_target`/`astrometry_goto`. Al terminar con éxito:
`project.update_context` con `ra_deg`/`dec_deg`/`coords_epoch`/`rate_arcsec_min`
frescos y etiqueta **«Posición a las HH:MM:SS UT»** en Plan & Captura. Si
`position_at` es `None`: snapshot + aviso en barra de estado.
**Tests**: neo → llama `position_at` y actualiza contexto; sn → snapshot sin
red; mensaje de aviso sin efeméride (ccdciel y ephemeris falsos).

### Subplan 2 — Ficha con época visible
`_enrich_small_body` pide `step="30m"` y elige la fila más cercana a ahora
(guardando su `time`); bloque de coordenadas de `overview.py` muestra
«a las HH:MM UT» junto al RA/Dec copiable (preliminares: ya son «ahora», solo
ganan la etiqueta).
**Tests**: selección de fila cercana; etiqueta de época en el bloque de coords.

### Subplan 3 — Cierre
`lupdate`/`lrelease` ES/EN (~6 cadenas) · revisión bilingüe en **ADR-030**
(regla «coordenada fresca en el goto» + cadena de fallback + lo diferido:
`SolarTracking`/`UpdateCoord`, tasas JSON-RPC) · entrada de fase en
`WORKFLOWS.es/.md` · `pytest tests/unit` verde + funcional `position_at` de un
asteroide conocido contra Horizons.

## Orden de ejecución

0 → 1 → 2 → 3  (1 depende de 0; 2 es independiente de 1).

## Riesgos conocidos

- Horizons sin red en el click → fallback Kepler (peor precisión, sin
  perturbaciones): visible vía `source` en la etiqueta.
- Objetos NEOCP de muy corta duración de arco: la efeméride puede tener
  incertidumbre grande incluso «fresca» — el goto astrométrico y el aviso de
  «preliminary» lo cubren; no se persigue precisión absoluta, sino caer dentro
  del campo de resolución.
