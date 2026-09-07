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
    - **Comandos** (`Telescope_slewasync`, `Telescope_sync`, `Astrometry_Goto_Async`,
      `Astrometry_Goto_Running`, `Astrometry_Goto_Result`, `Wheel_setfilter`,
      `Capture_set*`, `Capture_start`, `Telescope_slewing`) → **directos, sin caché**.
   - Envelope: `result` valor / `{"status": "OK!"|"Failed!"}` / `error` JSON-RPC;
     cualquier fallo explícito lanza `CCDcielError` con el mensaje del servidor.
2. **Coordenadas aparentes**: el plan guarda coords **J2000** (`ctx.ra_deg/dec_deg`);
   el slew/sync convierten a aparente con **`J2000_to_Apparent`** y piden
   **2 parámetros posicionales planos** (RA en horas, DEC en grados) —
   *no* una lista `[[RA, DEC]]`: el servidor real responde
   «Invalid number of parameter: 0, must be: 2» con la lista — antes de
   `Telescope_slewasync`/`Telescope_sync`, y esperan a que
   **`Telescope_slewing`** se apague. (Corrección 2026-09-06, contra el
   servidor del observatorio: la referencia ap-i.net citada no está
   disponible.) Los estados `Telescope_slewing`/`Telescope_tracking` se
   interpretan con tolerancia (bool, entero o texto «True»/«False»).
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
6. **Ajuste astrométrico** (revisión 2026-09-07): el botón «Sincronizar telescopio /
   Sync telescope» pasa a **«Ajuste astrométrico / Astrometric Goto»** y llama a
   `Client.astrometry_goto()`: dispara `Astrometry_Goto_Async [RA_aparente_h, DEC°]`,
   sondea `Astrometry_Goto_Running` a intervalos de 1 s hasta que se apague
   (tope **120 s**, `CCDcielError` si sigue activo), y comprueba
   `Astrometry_Goto_Result` (`False` → `CCDcielError`). `Telescope_sync` y
   `Client.sync_target` quedan en el cliente para compatibilidad/uso directo; el GUI
   ya no los llama. La fila del worker mantiene su polling de `Telescope_slewing`
   desactivado para este flujo, porque el bucle es el del astrometry.
7. **Efeméride fresca en el goto para cuerpos en movimiento** (revisión 2026-09-07):
   los NEOs, cometas y candidatos PCCP no tienen coordenadas fijas — un NEO a
   5″/min con un plan de hace 2 h lleva 10′ de error, y el goto astrométrico
   resolvería el campo equivocado. Regla: para los kinds `neo`/`comet`/`pccp` el
   botón de apuntar **recalcula la posición en el instante del click** antes del
   slew, dentro del `CcdcielWorker` (red fuera del hilo de GUI). El helper
   `core/ephemeris.py::position_at` consulta Horizons a paso fino (2 min, ventana
   ±2 h redondeada a 30 min para reutilizar la caché) e interpola linealmente a
   «ahora» (desenvolviendo AR en el salto 0h/24h); cadena de fallback sin red:
   elementos SBDB propagados con Kepler → órbita preliminar NEOfixer (NEOCP no
   confirmados) → snapshot del plan con aviso. SN y tránsitos siguen usando el
   snapshot (coordenadas fijas). El contexto del proyecto gana `coords_epoch`/
   `coords_source`/`rate_arcsec_min` frescos y el panel muestra
   «Posición a las HH:MM:SS UT»; la ficha de objeto muestra la época de la
   efeméride junto al RA/Dec copiable (`ephem_epoch`, fila más cercana a ahora
   con paso 30 m en vez de `eph[0]` a 00:00 UT). El goto astrométrico absorbe el
   residuo de efeméride con el plate solve, siempre que la predicción caiga
   dentro del campo de resolución. **Fuera de esta iteración**:
   `SolarTracking`/`UpdateCoord=True` en el `.targets` y tasas no siderales vía
   JSON-RPC — requieren validación contra el CCDciel real; el cap anti-traza por
   exposición (`max_exposure_no_trail` + `rate_arcsec_min`) ya protege los
   frames.

**Consecuencias**: `config.py` gana `ccdciel_host`/`ccdciel_port`/`ccdciel_auto_connect`;
Settings gana el tab **CCDciel**; `db.py` `SOURCE_TTL["ccdciel"] = 60`; i18n ES/EN
ampliada (~35 cadenas); tests unitarios del cliente con `requests.post` falso + worker
offscreen + migración 2→3; test funcional que hace **skip** si no hay servidor en
`localhost:3277`. `core/ephemeris.py` gana `position_at` (+ helpers de interpolación
y propagación); `enrich._enrich_small_body` usa paso 30 m y la fila más cercana a
ahora (`ephem_epoch`); el contexto del proyecto lleva `coords_epoch`/`coords_source`;
tests unitarios de interpolación, fallback y goto fresco. El control de
foco/dome/guiding/weather queda para una iteración
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
    - **Commands** (`Telescope_slewasync`, `Telescope_sync`, `Astrometry_Goto_Async`,
      `Astrometry_Goto_Running`, `Astrometry_Goto_Result`, `Wheel_setfilter`,
      `Capture_set*`, `Capture_start`, `Telescope_slewing`) → **direct, uncached**.
   - Envelope: plain `result` / `{"status": "OK!"|"Failed!"}` / JSON-RPC `error`; any
     explicit failure raises `CCDcielError` with the server message.
2. **Apparent coordinates**: the plan stores **J2000** coords (`ctx.ra_deg/dec_deg`);
   slew/sync convert to apparent via **`J2000_to_Apparent`** and send
   **2 flat positional params** (RA in hours, DEC in degrees) — *not* a
   `[[RA, DEC]]` list: the real server answers “Invalid number of parameter:
   0, must be: 2” with the list — before `Telescope_slewasync`/`Telescope_sync`,
   and wait for **`Telescope_slewing`** to stop. (Fix 2026-09-06, against the
   observatory server: the ap-i.net reference cited is not available.) The
   `Telescope_slewing`/`Telescope_tracking` states read tolerantly (bool,
   integer or "True"/"False" text).
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
6. **Astrometric goto** (revision 2026-09-07): the "Sync telescope" button becomes
   **"Astrometric Goto"** and calls `Client.astrometry_goto()`: it fires
   `Astrometry_Goto_Async [RA_app_hours, DEC°]`, polls `Astrometry_Goto_Running`
   every 1 s until it goes low (hard cap **120 s**, `CCDcielError` otherwise),
   then checks `Astrometry_Goto_Result` (`False` → `CCDcielError`). `Telescope_sync`
    and `Client.sync_target` remain in the client for compatibility/direct use; the
    GUI no longer calls them. The worker keeps `poll_slew=False` for this flow
    because the loop is the astrometry one, not `Telescope_slewing`.
7. **Fresh ephemeris in the goto for moving targets** (revision 2026-09-07):
   NEOs, comets and PCCP candidates have no fixed coordinates — a 5″/min NEO
   with a 2-hour-old plan is 10′ off, and the astrometric goto would solve the
   wrong field. Rule: for kinds `neo`/`comet`/`pccp` the point button
   **recomputes the position at click time** before slewing, inside the
   `CcdcielWorker` (network off the GUI thread). The helper
   `core/ephemeris.py::position_at` queries Horizons at a fine step (2 min,
   ±2 h window rounded to 30 min to reuse the cache) and linearly interpolates
   to "now" (RA unwrapped at the 0h/24h seam); offline fallback chain: SBDB
   elements propagated with Kepler → NEOfixer preliminary orbit (unconfirmed
   NEOCP) → plan snapshot with a warning. SN and transits keep using the
   snapshot (fixed coordinates). The project context gains fresh
   `coords_epoch`/`coords_source`/`rate_arcsec_min` and the panel shows
   "Position at HH:MM:SS UT"; the object card shows the ephemeris epoch next
   to the copyable RA/Dec (`ephem_epoch`, nearest row to now at a 30-min step
   instead of `eph[0]` at 00:00 UT). The astrometric goto absorbs ephemeris
   residual with the plate solve, as long as the prediction lands inside the
   solve field. **Out of this iteration**: `SolarTracking`/`UpdateCoord=True`
   in the `.targets` and non-sidereal rates via JSON-RPC — they need validation
   against the real CCDciel; the per-exposure no-trail cap
   (`max_exposure_no_trail` + `rate_arcsec_min`) already protects the frames.

**Consequences**: `config.py` gains `ccdciel_host`/`ccdciel_port`/`ccdciel_auto_connect`;
Settings gains the **CCDciel** tab; `db.py` `SOURCE_TTL["ccdciel"] = 60`; ES/EN i18n
extended (~35 strings); client unit tests with a faked `requests.post` + offscreen
worker + 2→3 migration; functional test that **skips** when no server listens on
`localhost:3277`. `core/ephemeris.py` gains `position_at` (+ interpolation and
propagation helpers); `enrich._enrich_small_body` uses a 30-min step and the row
nearest now (`ephem_epoch`); the project context carries
`coords_epoch`/`coords_source`; unit tests for interpolation, fallback and the
fresh goto. Focuser/dome/guiding/weather control is deferred to a later iteration
(same transport, more methods).