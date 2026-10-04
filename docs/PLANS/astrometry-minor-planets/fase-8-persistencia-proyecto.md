# Fase 8: persistencia y flujo de proyecto

> Fase del plan maestro [`PLAN.md`](PLAN.md). Decisiones: D14, D15, D22, D25,
> D26.

## Por qué

Una medida que no se guarda no existe. Las observaciones, la velocidad
resuelta, el resultado del chequeo y los stacks tienen que quedar en el
proyecto, atados a la visita, con su **Undo por ejecución** y sin romper el
esquema ni los flujos de hoy. Esta fase es la que convierte el motor en algo
auditable y reutilizable (multinoche, publicaciones, informes).

## Implementación

### 8.1 Migración `user_version` 16 → 17

Aditiva e idempotente, al estilo de las migraciones existentes de `core/db.py`:

```sql
CREATE TABLE IF NOT EXISTS astrometry_runs (
    id              INTEGER PRIMARY KEY,
    project_id      INTEGER,
    session_id      INTEGER,          -- la VISITA (FK project_sessions)
    created         TEXT,
    cfg_json        TEXT,             -- método, umbrales, report_source...
    status          TEXT,             -- complete|not_detected|incomplete|undone
    object_name     TEXT,
    method          TEXT,             -- sum|mean|median|sigma
    n_frames        INTEGER,
    n_obs           INTEGER,
    rate_arcsec_min REAL,
    pa_deg          REAL,
    sweep_json      TEXT,             -- la rejilla del barrido
    dither          INTEGER,
    snr_gate        REAL,
    submit_snr      REAL,
    detected        INTEGER
);

CREATE TABLE IF NOT EXISTS astrometry_points (
    id                 INTEGER PRIMARY KEY,
    run_id             INTEGER,
    project_id         INTEGER,
    session_id         INTEGER,       -- la VISITA
    group_index        INTEGER,       -- qué observación de la secuencia
    mjd                REAL,          -- T_mid del grupo
    ra                 REAL,
    dec                REAL,
    rms_ra             REAL,
    rms_dec            REAL,
    mag                REAL,
    band               TEXT,
    x                  REAL,
    y                  REAL,
    n_frames           INTEGER,
    snr                REAL,
    mag_limit          REAL,
    source             TEXT,          -- stack|frames
    method             TEXT,
    flags              TEXT,
    check_residual_ra  REAL,
    check_residual_dec REAL,
    check_scatter      REAL,
    check_ok           INTEGER,
    check_note         TEXT
);

CREATE TABLE IF NOT EXISTS astrometry_frames (
    id        INTEGER PRIMARY KEY,
    run_id    INTEGER,
    path      TEXT,
    size      INTEGER,
    filter    TEXT,
    exptime_s REAL,
    date_obs  TEXT,
    archived  INTEGER DEFAULT 0,
    moved_to  TEXT
);
```

Por qué `session_id` es la **visita** y no la ejecución: `db.py` activa
`PRAGMA foreign_keys = ON` y `session_id` es FK a `project_sessions`; meter ahí
un id de ejecución rompería la FK y el enlace punto → visita que necesita el
multinoche. La ejecución es `run_id` (mismo patrón que `measurement_runs` de
ADR-048).

### 8.2 Helpers (`core/followup.py` o `core/project.py`)

- `create_astrometry_run(db, project_id, session_id, cfg, ...) -> run_id`.
- `add_astrometry_points(db, rows)` en lote.
- `set_run_status(db, run_id, status)`.
- `delete_run(db, run_id)`: borra puntos y frames del run y marca la ejecución
  `undone` (auditoría). Es el «Deshacer esta ejecución» (D14), que **no toca**
  otros runs ni los puntos legacy.
- `list_runs(db, project_id)` y `points_for_run(db, run_id)`.
- `add_astrometry_frames(db, run_id, rows)`: el manifiesto de la fase 9.

### 8.3 Ficheros del proyecto

- Cada stack de grupo se guarda como `project_files` con `kind="stack"` y
  `meta` con `group_index`, `t_mid`, `method`, `n_frames` y `snr`.
- El reporte generado se registra con `kind="report"` (ya existe) y el GIF con
  `kind="motion_gif"` (ya existe).
- Todo atado a la visita (`session_id`), como manda ADR-045.

### 8.4 Vista de Análisis y bloque MPC

- La vista de Análisis del proyecto lista las ejecuciones y sus observaciones:
  hora, posición, residual, SNR, veredicto del chequeo y vía. Reutiliza el
  patrón de las series (ADR-048) y `lightcurve_data` solo si aplica; aquí la
  gráfica natural es residual vs tiempo.
- El bloque MPC de la visita (ADR-045/ADR-022) recibe el reporte generado en
  la caja de pegado, lo valida y lo guarda; el usuario decide el envío.

### 8.5 Migración de datos y compatibilidad

- Las tablas son nuevas; nada de lo existente cambia.
- `photometry_points` y `measurement_runs` no se tocan.
- Los tests de migración cubren desde v16 y desde esquema limpio.

## Tests

`tests/unit/test_db_v17.py`:

- Migración desde v16 y desde limpio; idempotencia; reapertura.
- Escritura en lote de puntos y frames; `delete_run` borra solo lo suyo.

`tests/unit/test_astrometry_persist.py`:

- **A8, Undo**: dos ejecuciones en la misma visita; deshacer una no toca la
  otra ni los puntos legacy.
- Un run `not_detected` no tiene puntos y guarda su magnitud límite.
- Los stacks y el GIF se registran en `project_files` con su meta.

## Salida limpia

El flujo completo se persiste por visita, con Undo por ejecución, y la vista de
Análisis y el bloque MPC lo consumen. Nada de lo anterior se entera.

## Hecho cuando

A8 pasa, la migración v17 abre bases existentes sin pérdida, y el reporte
generado aparece en el bloque MPC de la visita listo para validar y guardar.
