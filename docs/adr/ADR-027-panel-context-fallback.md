# ADR-027: Panel context fallback — la historia de una SN/cometa no depende de que SIMBAD/SBDB la conozca

**Estado / Status**: Accepted · **Fecha / Date**: 2026-08-29

## Español

**Contexto**: al abrir una supernova o un cometa que el planner ya había
sugerido, si la fuente de referencia no conocía el objeto (SIMBAD para
transientes, SBDB para cometas aún sin confirmar) el `ObjectPanel`
degradaba a un hook genérico ("Seguimiento de un fenómeno transitorio…"),
bullets vacías o incompletas, sin tabla de parámetros y sin gráfico de
campo. El usuario veía una ficha vacía aunque el planner llevaba horas
calculando qué ver, cuándo y desde dónde.

El fallo tenía tres rutas:

1. **Ruta A** — SN con nombre pleno (`AT2026…`): `enrich.enrich()` tiraba
   el `fallback_target` antes de `_enrich_transient`, así que el contexto
   del planner (galaxia anfitriona, tipo, magnitud, RA/Dec, fecha de
   descubrimiento, ventana) se perdía en cuanto SIMBAD no encontraba el
   nombre.
2. **Ruta B** — nombre corto (`2026…`): `detect_type()` no lo clasificaba
   como transiente y caía en la ruta de cuerpo menor; SBDB/NEOfixer fallan
   y el objeto salía como `type="sn"` con `data={"unconfirmed": target}`,
   pero `narrative.hook()` lo trataba como "objeto aún sin confirmar" genérico
   sin mencionar que era una SN, ni su galaxia, ni su tipo.
3. **Cometas** — COBS: `sbdb.get()` falla para el nombre corto → mismo
   `unconfirmed` kind="comet", pero el hook decía "Seguimiento de este
   objeto" sin contexto.

**Decisión**: cuando las fuentes externas no conocen el objeto, el panel
construye la historia a partir de lo que el planner ya sabía, en este orden
de prioridad:

1. **`enrich.py`** — `enrich()` ahora pasa `fallback_target` en la rama
   transiente (no solo en la de cuerpo menor). `_enrich_transient()` llama
   a dos helpers nuevos:
   - `_copy_window_context(out, t)`: copia `safe_window`, `best_time`,
     `window_start/end`, `hours_up`, `max_alt`, `latest_safe_start`,
     `duration_s` del target al data-dict, para que
     `narrative._safe_window_bullets()` y `post.build_charts()` las lean.
   - `_merge_transient_context(out, t)`: rellena `host` (normalizando un
     string a `{"name": host}`), `otype` (de `sn_type`), `mag`, `ra_deg/
     dec_deg`, `disc_date` — siempre con `setdefault`, **nunca** pisando lo
     que SIMBAD ya devolvió.
2. **`narrative.py`** — `hook()` y `fact_bullets()` para transientes y
   unconfirmed ahora usan el contexto:
   - `hook()` transiente: prioridad `dist_mly` (con host) → `otype+host` →
     `otype` → `host` → genérico.
   - `hook()` unconfirmed: si `kind == "sn"`, frase de SN que nombra host +
     tipo; si `kind == "comet"`, frase que nombra el cometa.
   - `_transient_facts()` incluye `otype`, `host`, `dist_mly`, `mag` y
     `disc_date`, en ese orden, usando siempre el dato no vacío.
   - `_unconfirmed_facts()` añade SN (`sn_type`, `host`, `disc_date`) y
     cometa (`perihelion_date`, `delta_au`, "candidato a cometa") antes de
     las filas clásicas neocp/pccp.
3. **`post.py`** — `build_charts()`: la cadena ra/dec ahora tiene una 4.ª
   fuente, `d.get("ra_deg")`/`dec_deg` (el data-dict), para que el gráfico
   de cielo se dibuje con las coordenadas del planner cuando no hay
   ephemeris ni SIMBAD.
4. **`gui/overview.py`** — `_capture_chips()` ahora usa
   `self._ctx or self._fallback or {}`, así que los chips de magnitud y
   ventana aparecen también en el flujo explore/dialog donde solo existe
   `self._fallback`.

**Consecuencias**:

- El panel de una SN/cometa que las fuentes no conocen muestra una historia
  real (host, tipo, magnitud, fecha, ventana segura) en vez de un hook
  genérico, bullets vacías y sin gráficos.
- El gráfico de cielo se dibuja con las coordenadas del planner cuando
  SIMBAD no responde; el gráfico de campo sigue ausente (no hay cutout)
  pero el resto de la ficha es completamente funcional.
- Ninguna ruta pisa los datos que SIMBAD/SBDB sí devuelven: el `setdefault`
  garantiza que el contexto solo rellena vacíos.
- Tests: `tests/unit/test_sn_comet_panel.py` (offline, 7 tests) y dos tests
  funcionales en `tests/functional/test_functional.py` (online, con datos
  reales de Rochester/COBS).

**Escopado**: este ADR cubre la degradación del panel cuando las fuentes
externas no conocen el objeto. No cambia el score del planner, ni el
orden de las sugerencias, ni el contenido de los posts (que ya usaban el
contexto vía `_unconfirmed_facts`).

## English

**Context**: when opening a supernova or comet the planner had already
suggested, if the reference source didn't know the object (SIMBAD for
transients, SBDB for unconfirmed comets) the `ObjectPanel` degraded to a
generic hook, empty/incomplete bullets, no parameter table and no field
chart. The user saw an empty card even though the planner had spent hours
computing what to observe, when and from where.

The failure had three routes:

1. **Route A** — full-name SN (`AT2026…`): `enrich.enrich()` dropped
   `fallback_target` before `_enrich_transient`, so the planner context
   (host, type, magnitude, RA/Dec, discovery date, safe window) was lost
   as soon as SIMBAD couldn't find the name.
2. **Route B** — short name (`2026…`): `detect_type()` didn't classify it
   as a transient and it fell through to the small-body path; SBDB/NEOfixer
   fail and the object came out as `type="sn"` with
   `data={"unconfirmed": target}`, but `narrative.hook()` treated it as a
   generic "object still unconfirmed" without saying it was a SN, nor
   naming its host or type.
3. **Comets** — COBS: `sbdb.get()` fails for the short name → same
   `unconfirmed` kind="comet", but the hook said "Follow-up of this object"
   with no context.

**Decision**: when the external sources don't know the object, the panel
builds the story from what the planner already knew, in this priority order:

1. **`enrich.py`** — `enrich()` now passes `fallback_target` in the
   transient branch (not only the small-body one). `_enrich_transient()`
   calls two new helpers:
   - `_copy_window_context(out, t)`: copies `safe_window`, `best_time`,
     `window_start/end`, `hours_up`, `max_alt`, `latest_safe_start`,
     `duration_s` from the target into the data-dict, so that
     `narrative._safe_window_bullets()` and `post.build_charts()` can read
     them.
   - `_merge_transient_context(out, t)`: fills `host` (normalising a string
     to `{"name": host}`), `otype` (from `sn_type`), `mag`, `ra_deg/
     dec_deg`, `disc_date` — always with `setdefault`, **never**
     overwriting what SIMBAD already returned.
2. **`narrative.py`** — `hook()` and `fact_bullets()` for transients and
   unconfirmed objects now use the context:
   - `hook()` transient: priority `dist_mly` (with host) → `otype+host` →
     `otype` → `host` → generic.
   - `hook()` unconfirmed: if `kind == "sn"`, SN phrasing that names host +
     type; if `kind == "comet"`, phrasing that names the comet.
   - `_transient_facts()` includes `otype`, `host`, `dist_mly`, `mag` and
     `disc_date`, in that order, always using the non-empty value.
   - `_unconfirmed_facts()` adds SN (`sn_type`, `host`, `disc_date`) and
     comet (`perihelion_date`, `delta_au`, "comet candidate") before the
     classic neocp/pccp rows.
3. **`post.py`** — `build_charts()`: the ra/dec chain now has a 4th source,
   `d.get("ra_deg")`/`dec_deg` (the data-dict), so the sky chart draws with
   the planner's coordinates when there's no ephemeris nor SIMBAD.
4. **`gui/overview.py`** — `_capture_chips()` now uses
   `self._ctx or self._fallback or {}`, so the magnitude and window chips
   appear in the explore/dialog flow where only `self._fallback` exists.

**Consequences**:

- The SN/comet panel for objects the sources don't know shows a real story
  (host, type, magnitude, date, safe window) instead of a generic hook,
  empty bullets and no charts.
- The sky chart draws with the planner's coordinates when SIMBAD doesn't
  respond; the field chart stays absent (no cutout) but the rest of the
  card is fully functional.
- No route clobbers data that SIMBAD/SBDB did return: `setdefault`
  guarantees the context only fills gaps.
- Tests: `tests/unit/test_sn_comet_panel.py` (offline, 7 tests) and two
  functional tests in `tests/functional/test_functional.py` (online, with
  real Rochester/COBS data).

**Scope**: this ADR covers the panel degradation when external sources
don't know the object. It doesn't change the planner's score, the
`suggestion` ordering, or the post content (which already used the context
via `_unconfirmed_facts`).
