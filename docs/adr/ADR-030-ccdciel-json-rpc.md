# ADR-030: CCDciel live integration (JSON-RPC) — Plan & Captura

**Estado / Status**: Accepted · **Fecha / Date**: 2026-09-06

## Español

**Contexto**: ADR-021 dejó «controlar telescopios» fuera de alcance (solo ficheros) y
`docs/ccdciel_sequence_sample.targets` fijó el formato de plan **contra una exportación
real del usuario**. El siguiente salto natural: no exportar un fichero y abrirlo a mano,
sino **entregar el plan y apuntar/capturar en vivo** con el propio CCDciel del
observatorio. CCDciel expone un servidor **JSON-RPC 2.0** en `http://host:3277/jsonrpc`
(referencia oficial: `docs/jsonrpc_reference` ap-i.net, revisión 2026-05-25), lo que
permite una integración real **sin drivers ni INDI** desde la GUI de NightScribe.

**Decisión**: integración **v1 (Dashboard + control básico)** dentro de la pestaña
«Plan & Captura» (ADR-019, revisión 2026-09-06):

1. **Cliente `core/sources/ccdciel.py`** — JSON-RPC 2.0 sobre HTTP POST (puerto por
   defecto **3277**). Regla AGENTS.md respetada: `requests` vive solo en `core/sources/`.
   - **Lecturas** (estado, versión, filtros, dashboard `status`) → **cacheadas** vía
     `db.http_get` (source `"ccdciel"`, TTL **60 s**): el dashboard no machaca al
     programa del observatorio. **Nunca** cachear coordenadas de la montura en vivo.
   - **Comandos** (`Telescope_slewasync`, `Telescope_sync`, `Wheel_setfilter`,
     `Capture_set*`, `Capture_start`, `Telescope_slewing`) → **directos, sin caché**.
   - Envelope: `result` valor / `{"status": "OK!"|"Failed!"}` / `error` JSON-RPC;
     cualquier fallo explícito lanza `CCDcielError` con el mensaje del servidor.
2. **Coordenadas aparentes**: el plan guarda coords **J2000** (`ctx.ra_deg/dec_deg`);
   el slew/sync convierten a aparente con **`J2000_to_Apparent`** (RA en horas, DEC en
   grados) antes de `Telescope_slewasync`/`Telescope_sync`, y esperan a que
   **`Telescope_slewing`** se apague.
3. **Envío del plan**: el botón «Enviar plan» prepara en CCDciel
   `Capture_setobjectname/exposure/count/frametype=Light` + `Wheel_setfilter` (el combo
   de filtros se autorrellena de la rueda vía `Wheel_GetfiltersName`, con la lista
   estática L/R/G/B/Ha/OIII/SII como respaldo si la rueda no responde) y
   «Iniciar captura» dispara `Capture_start`. **`Sequence_start` queda FUERA de v1**:
   su parámetro es una serialización de plan cuya forma solo podemos fijar contra una
   instancia real (igual filosofía que ADR-021).
4. **Conexión manual**: botón «Conectar CCDciel» (host/puerto en Settings);
   `ccdciel_auto_connect` opcional, **off por defecto** — conectar un observatorio es
   una decisión humana, no algo que la app haga en silencio.
5. **GUI**: `CcdcielWorker` (QThread) ejecuta cada acción fuera del hilo de UI;
   dashboard de estado (versión, temperatura CCD, tracking, slew) y barra de estado de
   la conexión. Red nunca en el hilo de GUI.

**Consecuencias**: `config.py` gana `ccdciel_host`/`ccdciel_port`/`ccdciel_auto_connect`;
Settings gana el tab **CCDciel**; `db.py` `SOURCE_TTL["ccdciel"] = 60`; i18n ES/EN
ampliada (~35 cadenas); tests unitarios del cliente con `requests.post` falso + worker
offscreen + migración 2→3; test funcional que hace **skip** si no hay servidor en
`localhost:3277`. El control de foco/dome/guiding/weather queda para una iteración
posterior (mismo transporte, más métodos).

## English

**Context**: ADR-021 left "telescope control" out of scope (files only) and
`docs/ccdciel_sequence_sample.targets` pinned the plan format **against a real export
from the user's setup**. The natural next step: not exporting a file and opening it by
hand, but **delivering the plan and pointing/capturing live** on the observatory's own
CCDciel. CCDciel exposes a **JSON-RPC 2.0** server on `http://host:3277/jsonrpc`
(official reference, ap-i.net JSON-RPC reference, 2026-05-25 revision), enabling real
integration **without drivers or INDI** from NightScribe's GUI.

**Decision**: **v1 integration (Dashboard + basic control)** inside the "Plan & Capture"
tab (ADR-019, review 2026-09-06):

1. **`core/sources/ccdciel.py` client** — JSON-RPC 2.0 over HTTP POST (default port
   **3277**). AGENTS.md rule respected: `requests` lives only in `core/sources/`.
   - **Reads** (state, version, filters, `status` dashboard) → **cached** through
     `db.http_get` (source `"ccdciel"`, TTL **60 s**): the dashboard does not hammer the
     observatory software. **Never** cache live mount coordinates.
   - **Commands** (`Telescope_slewasync`, `Telescope_sync`, `Wheel_setfilter`,
     `Capture_set*`, `Capture_start`, `Telescope_slewing`) → **direct, uncached**.
   - Envelope: plain `result` / `{"status": "OK!"|"Failed!"}` / JSON-RPC `error`; any
     explicit failure raises `CCDcielError` with the server message.
2. **Apparent coordinates**: the plan stores **J2000** coords (`ctx.ra_deg/dec_deg`);
   slew/sync convert to apparent via **`J2000_to_Apparent`** (RA in hours, DEC in
   degrees) before `Telescope_slewasync`/`Telescope_sync`, and wait for
   **`Telescope_slewing`** to stop.
3. **Sending the plan**: "Send plan" stages
   `Capture_setobjectname/exposure/count/frametype=Light` + `Wheel_setfilter` on
   CCDciel (the filter combo auto-fills from the wheel via `Wheel_GetfiltersName`, with
   the static L/R/G/B/Ha/OIII/SII list as fallback when the wheel does not answer) and
   "Start capture" fires `Capture_start`. **`Sequence_start` is OUT of v1**: its
   parameter is a plan serialization whose shape we can only pin against a real instance
   (same philosophy as ADR-021).
4. **Manual connection**: "Connect CCDciel" button (host/port in Settings);
   `ccdciel_auto_connect` optional, **off by default** — connecting an observatory is a
   human decision, not something the app does silently.
5. **GUI**: `CcdcielWorker` (QThread) runs every action off the UI thread; status
   dashboard (version, CCD temperature, tracking, slew) plus a connection status bar.
   No network on the GUI thread.

**Consequences**: `config.py` gains `ccdciel_host`/`ccdciel_port`/`ccdciel_auto_connect`;
Settings gains the **CCDciel** tab; `db.py` `SOURCE_TTL["ccdciel"] = 60`; ES/EN i18n
extended (~35 strings); client unit tests with a faked `requests.post` + offscreen
worker + 2→3 migration; functional test that **skips** when no server listens on
`localhost:3277`. Focuser/dome/guiding/weather control is deferred to a later iteration
(same transport, more methods).