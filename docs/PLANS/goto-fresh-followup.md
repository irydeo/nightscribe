# Plan: Goto fresco — follow-up (vacíos de la revisión 7)

*Follow-up de `docs/PLANS/goto-fresh-ephemeris.md`. Cerramos los 4 vacíos
identificados en la revisión 7 del ADR-030 sin ampliar alcance.*

---

## Objetivo

Hacer el Goto fresco **seguro contra datos viejos** (no solo "menos viejos"),
que el fallback a snapshot sea **visible y cancelable**, y que el código no
pueda lanzar un `KeyError` opaco. Todo sin tocar la UX del Goto (sigue siendo
auto + label de época).

## Fuera de alcance

- Re-apuntado durante una secuencia (ADR-030 rev. 8 lo declara explícitamente;
  ADR-031 futuro lo tratará).
- `position_at` con fuente de ephemerides propia (`astropy`/`skyfield`): la
  cadena Horizons → SBDB → NEOfixer basta.
- Rediseñar `db.http_get`: solo añadimos un bypass puntual.

## Decisiones

1. **Umbral de staleness**: `max_age_min` configurable por kind.
   - `neo` / `pccp`: **10 min** (NEOs CP a 30″/min → 30′ de deriva en 10 min;
     demasiado para un FOV estrecho).
   - `comet`: **30 min** (movimiento típico < 5″/min).
   - `sn` / `transit`: no aplica (snapshot fijo, sin edad).
   - Valor por defecto en `config` (`max_coords_age_min`); override por kind
     hardcodeado mientras no haya necesidad de UI.
   - Si `age > max`: **no** lanzar el slew; `QMessageBox.warning` con dos
     botones "Forzar" / "Cancelar" (default = Cancelar). El label de la ficha
     pasa a rojo (o "¡antiguo!" — `self.tr()`).

2. **Fallback a snapshot**: solo si el usuario no tiene coords **o** si las
   coords tienen `age ≤ max_age_min`. Si tiene coords pero son viejas: se
   aplica la regla 1. Si **no tiene coords** y `position_at` devuelve `None`:
   `CCDcielError` claro ("No usable coordinates for X").

3. **Bypass de caché**: `db.http_get` gana un parámetro `no_cache=False`;
   cuando True no lee la caché (pero **sí** escribe — así el próximo Goto
   reutiliza el fetch fino recién hecho). `ephemeris._horizons_fine_rows` lo
   pasa `True` para kind `neo`/`pccp` cuando el caché de la ventana actual tiene
   > 5 min. Para `comet` usamos el TTL normal.
   - Razón: el cache key se alinea a 30 min, así que dos Gotos 5 min separados
     comparten caché. Con `no_cache` solo pagamos ~1 s de HTTP extra para los
     que más lo necesitan.

4. **Semántica de `position_at`**: no se rediseña (evita churn); sí se
   documenta en el docstring que `name` es el *identificador para la fuente
   principal* (Horizons) y `fallback_target` es *el dict de contexto para la
   cadena de fallback* (SBDB/NEOfixer). Pequeño refactor opcional: rename
   parámetro a `ctx` (sin breaking — es keyword-only).

5. **ADR**: se hace **ADR-030 revisión 8** con los tres parches. ADR-031
   (re-apuntado) se abre en rama posterior, fuera del alcance.

## Plan de trabajo

### Subplan 0 — Preparación

- [ ] `git checkout feature/goto-fresh-ephemeris`
- [ ] Correr la suite actual:
      `pytest tests/unit/test_ephemeris_position_at.py`
      `pytest tests/unit/test_projects_hub.py`
      `pytest tests/unit/test_overview_panel.py`
      para fijar baseline.
- [ ] Leer `docs/adr/ADR-030-ccdciel-json-rpc.md` sección "revisión 7" para
      enlazar.

### Subplan 1 — `db.http_get(no_cache=False)`

Fichero: `nightscribe/core/db.py`

- Añadir parámetro `no_cache: bool = False` a `http_get`.
- Si True: saltar `cache_get`, sí llamar `cache_put` al final.
- Tests unitarios (ubicación: donde estén los tests de caché del repo,
  `tests/unit/test_db*.py`):
  1. Escribe una entry con `ttl=0` (vencida) y `no_cache=False` → refetch.
  2. Escribe una entry fresca, `no_cache=False` → no fetch (hit).
  3. Escribe una entry fresca, `no_cache=True` → fetch sí, y re-escribe.

### Subplan 2 — `ephemeris` usa `no_cache` por kind

Ficheros: `nightscribe/core/ephemeris.py`, `nightscribe/core/sources/horizons.py`

- `position_at(name, site, when=None, fallback_target=None, no_cache=False)`:
  - Nuevo parámetro keyword, default `False` (no breaking).
  - Lo pasa a `_horizons_fine_rows(name, site, when, no_cache)`.
- `_horizons_fine_rows(name, site, when, no_cache=False)`:
  - Nuevo parámetro keyword, lo pasa a `horizons.ephemeris(..., no_cache=no_cache)`.
- `horizons.ephemeris(command, center, start, stop, step, no_cache=False)` /
  `_raw_ephemeris(command, center, start, stop, step, no_cache=False)`:
  - Ganan `no_cache=False` y lo pasan a `db.http_get(key, "horizons", fetch,
    no_cache=no_cache)`.
- Tests nuevos en `tests/unit/test_ephemeris_position_at.py`:
  - Mock `horizons.ephemeris` → verificar que cuando `no_cache=True` llega
    `no_cache=True`.
  - Mock `db.http_get` → verificar que el flag viaja.

### Subplan 3 — Umbral + UX de fallback

Fichero: `nightscribe/gui/main_window.py`

- Constante: en `_ccd_point_action`, según kind:
  - `max_age_min = {"neo": 10, "pccp": 10, "comet": 30}.get(kind)`,
    `None` para fixed.
  - Si `config.get("max_coords_age_min")` existe y es int `≥ 1`, la usa
    (override simple).
- `action(c)` para kinds móviles:
  1. `pos = ephemeris.position_at(obj_id, site, fallback_target=ctx,
       no_cache=(kind != "comet"))`.
  2. Si `pos` resuelve: `slew`; `_ccd_apply_position(pos)`; label verde.
  3. Si `pos is None`:
     - `stored = (ctx.get("ra_deg"), ctx.get("dec_deg"))`.
     - Si `any(v is None for v in stored)`: lanzar
       `CCDcielError(self.tr("No usable coordinates for {name}").replace("{name}", name))`.
     - Si `stored` OK: calcular `stored_age_min` desde `ctx.get("coords_epoch")`
       vs `now()`.
       - Si `stored_age_min ≤ max_age_min`: seguir con el snapshot (misma ruta
         de siempre).
       - Si `stored_age_min > max_age_min`: emitir señal para que el GUI
         pregunte (no lanzar el slew desde el worker).
- Nueva señal + slot para el "confirmar o cancelar":
  - `stale = Signal(object)` en `MainWindow` con payload de dict.
  - Slot `_ccd_confirm_stale(pos)` abre `QMessageBox.question` con
    "These coordinates are {age} min old (max {max}). Slew anyway?" — botones
    Sí (default No) / No.
  - Si No → `statusBar().showMessage(tr("Slew cancelled."))`; no cambia el
    contexto.
  - Si Sí → `slew_fn(client, ra, dec)` + `_ccd_apply_position` (con
    `fell_back=True` y `forced=True`).
  - Para esto la `action` del worker **no lanza el slew** en esta rama; emite
    la señal y termina con
    `result={"__needs_confirm__": True, "stored": stored, "age_min": age}`.
    El slot decide.
- Tests de UI (`test_projects_hub.py` o nuevo `test_ccd_stale_confirm.py`):
  - Proyectar un objeto con `coords_epoch` hace 30 min → `action` devuelve
    `__needs_confirm__`.
  - Proyectar con `coords_epoch` hace 5 min → `action` sinea directo.
  - Proyectar sin `ra_deg` → `action` lanza `CCDcielError`.
  - Verificar que el label pasa a "stale" cuando `fell_back=True`.

### Subplan 4 — ADR + docs

- `docs/adr/ADR-030-ccdciel-json-rpc.md`: añadir **revisión 8** con los tres
  cambios (umbral, `no_cache` por kind, error claro), enlazar a
  `PLANS/goto-fresh-followup.md`.
- `docs/WORKFLOWS.es.md` § 7octies: una línea sobre el umbral (no más
  detalle).
- `nightscribe/i18n/es.ts` / `en.ts`: strings nuevos ("Slew anyway?",
  "No usable coordinates", "too old").

### Subplan 5 — Verificación final

- [ ] `pytest tests/unit` sin red (todo verde).
- [ ] `pytest tests/functional -k ccd` (si hay) o `pytest tests/functional -k ephemeris`.
- [ ] Lint según `AGENTS.md` (buscar comando de lint en el repo).
- [ ] Smoke manual: arrancar la GUI, crear un proyecto NEO, mock CCDCiel (o
      dejarlo desconectado), verificar que el label muestra la época y que al
      Goto se consulta Horizons (log).
- [ ] Commit solo si el usuario lo pide explícitamente.

## Riesgos

- **HTTP extra** por Goto con `no_cache=True`: ~300 ms; aceptable un
  Goto/a noche.
- **Señal nueva en `MainWindow`**: pequeño riesgo de regresión (slot antes de
  señal). Mitigar con test de UI.
- **Configurable `max_coords_age_min`**: si el usuario pone 0, se rompe.
  Validar `≥ 1` al leer.
- **`coords_epoch` ausente** (proyectos antiguos): tratar como `age = ∞` →
  forzar la confirmación.

## Entregable

3 commits: (1) core (`db.http_get` + `ephemeris`), (2) GUI + tests,
(3) ADR + strings de i18n. O 1 commit si preferimos atomicidad.
