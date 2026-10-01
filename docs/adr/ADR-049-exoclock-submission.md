# ADR-049: ExoClock submission from the app (manual upload, no credentials)

**Estado / Status**: Accepted · **Fecha / Date**: 2026-09-27 · **rev. 2026-09-28**
(revisión series-photometry: el arranque agrupado es el arranque real de la
primera toma del grupo, `min(mjd_i − exp_i/2)`, no la media de medios menos la
integración total; la referencia de flujo es la **media de flujo fuera de
tránsito** (la mediana de magnitudes sesga la línea base cuando el tránsito
copan los puntos) y los Comments dicen de dónde cuelga; el info se llama
`ExoClock_info.txt` / the grouped start is the true start of the group's first
frame, `min(mjd_i − exp_i/2)`, not the mean of mid-times minus half the total
integration; the flux reference is the **mean out-of-transit flux** (a median
of magnitudes biases the baseline when in-transit points dominate) and the
Comments say where it hangs from; the info file is `ExoClock_info.txt`)

## Español

**Contexto**: el usuario mide tránsitos para enviarlos a ExoClock (proyecto ESA
Ariel), y el flujo hoy termina en un CSV genérico. Verificación 2026-09-27: ExoClock
**no tiene API pública de subida** (`/api/` responde 404 y solo existe el endpoint
de lectura `database/planets_json`; `/upload/` va detrás de login Django + CSRF y su
robots.txt prohíbe el scraping; el paquete oficial `exoclock` de PyPI es solo
lectura). Además, EXOTIC **no** sube a ExoClock.

**Decisión**: preparar la observación en la app y subirla a mano desde el navegador.

- **Formato HOPS**: archivo de **3 columnas** (JD_UTC del **arranque** de la
  exposición, flujo relativo = objetivo sobre la suma de comps, error) más
  `ExoClock_info.txt` con el encabezado oficial (Planeta, Time format JD_UTC,
  Time stamp: Exposure start, Flux format: Flux, Filter, Exposure time) y el campo
  **Comments rellenido** con la autocalificación honesta del observador (ADR-037 es
  el espíritu: lenguaje llano, sin diagnósticos rojos de Rp/Rs).
- **Sin credenciales guardadas** y **sin scraping** de `/upload/`: el botón genera
  los ficheros y **abre `https://exoclock.space/upload/` en el navegador** del
  usuario; al confirmar en la app se pone el outcome `reported_exoclock` del
  proyecto (estado ya existente en `core/project.py`).
- **Checklist previo con semáforo** (no bloquea): baseline ≥1 h a cada lado, ≥3
  puntos por ingress, sin flags rojos, dip coherente con la efemérides. Avisa, no
  muerde: el usuario decide.
- **Tiempo**: con agrupación de tomas cortas, el arranque exportado es
  `media de los medios − integración total/2`, documentado en el `info.txt` (plan
  D19); `BJD_TDB` lo devuelve el servidor de ExoClock, no nosotros.
- **API**: solo si algún día hay endpoint público documentado y el autor lo
  autoriza; se decide en la fase 11 del plan (compuerta con permiso explícito).

**Alternativas**: API con credenciales guardadas (rechazado: no existe endpoint y
guardar claves no compensa); scraping de `/upload/` (rechazado: lo prohíbe
robots.txt); delegar todo en EXOTIC (rechazado: tampoco sube a ExoClock, y nosotros
ya tenemos la curva medida en local).

**Consecuencias**: el usuario cierra el ciclo hasta ExoClock sin salir de
NightScribe; nada sensible vive en la base ni en el repo; si ExoClock publica API,
la fase 11 cambia solo el transporte y reutiliza el export; el checklist sube la
calidad media de lo que se envía sin bloquear a nadie.

## English

**Context**: the user measures transits to submit them to ExoClock (ESA Ariel
project), and today the flow ends in a generic CSV. Verified 2026-09-27: ExoClock
has **no public upload API** (`/api/` returns 404 and only the read endpoint
`database/planets_json` exists; `/upload/` sits behind Django login + CSRF and its
robots.txt forbids scraping; the official `exoclock` PyPI package is read-only).
Also, EXOTIC does not upload to ExoClock either.

**Decision**: prepare the observation in the app and upload it by hand from the
browser.

- **HOPS format**: a **3-column** file (JD_UTC of the exposure **start**, relative
  flux = target over the sum of comps, error) plus `ExoClock_info.txt` with the
  official header (Planet, Time format JD_UTC, Time stamp: Exposure start, Flux
  format: Flux, Filter, Exposure time) and a **prefilled Comments** field with the
  observer's honest self-assessment.
- **No stored credentials** and **no scraping** of `/upload/`: the button writes the
  files and **opens `https://exoclock.space/upload/` in the user's browser**;
  confirming in the app sets the project outcome `reported_exoclock` (an existing
  state in `core/project.py`).
- **Non-blocking pre-flight checklist** (traffic light): baseline ≥1 h each side,
  ≥3 points per ingress, no red flags, dip coherent with the ephemeris. It warns, it
  does not bite: the user decides.
- **Time**: with short-exposure grouping, the exported start is `mean of mid-times
  − total integration/2`, documented in the info file; `BJD_TDB` comes back from
  ExoClock's server, not from us.
- **API**: only if a documented public endpoint ever exists and the author gives
  permission; decided in phase 11 of the plan (explicit gate).

**Alternatives**: an API with stored credentials (rejected: no endpoint exists and
storing keys is not worth it); scraping `/upload/` (rejected: robots.txt forbids
it); delegating everything to EXOTIC (rejected: it does not upload to ExoClock
either, and we already have the curve measured locally).

**Consequences**: the user closes the loop up to ExoClock without leaving
NightScribe; nothing sensitive lives in the database or the repo; if ExoClock ever
publishes an API, phase 11 changes only the transport and reuses the export; the
checklist raises the average quality of submissions without blocking anyone.
