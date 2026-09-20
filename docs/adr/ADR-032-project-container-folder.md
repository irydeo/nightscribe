# ADR-032: Carpeta contenedora de proyectos — raíz global configurable y carpeta por proyecto

**Estado / Status**: Accepted · **Fecha / Date**: 2026-09-10

## Español

**Contexto**: todo lo que genera un proyecto (plan, secuencias, efemérides,
FITS, post, gráficos) se escribe debajo de `paths.data_dir()/projects/<id>-<slug>`,
una ruta fija gobernada por `platformdirs`. El usuario no tenía la menor idea de
dónde acababan sus ficheros ni forma de llevárselos a su disco de trabajo. Se
pidió control sobre la **carpeta contenedora**: una raíz global para todos los
proyectos y, si hace falta, una carpeta distinta para un proyecto concreto.

**Decisión**:

1. **Raíz global configurable**: clave `projects_root` en `config` (Ajustes >
   Observación, grupo «Projects folder»). Vacía (`""`) = comportamiento actual
   (`data_dir()/projects`). El cambio solo afecta a **proyectos nuevos**: los
   existentes guardan su carpeta en la BD y no se mueven.
2. **Carpeta por proyecto en la BD**: `root_dir` en la tabla `projects`
   (migración `user_version` 5→6: `ALTER TABLE ... ADD COLUMN root_dir TEXT` +
   backfill de filas existentes a la ruta heredada). Se **congela al crear** el
   proyecto; el hub permite cambiarla («Change folder…»), y `set_root_dir`
   solo re-ubica **exportaciones futuras** — v1 **no mueve** ficheros ya
   escritos (`project_files` guarda rutas absolutas).
3. **Resolución por capas en `core/project.storage_dir`**: `root_dir` del
   proyecto → `config.projects_root` → delegado `data_dir()/projects`. La resolución
   vive en `core/project` para no acoplar `paths` a `config`; `paths.project_dir`
   gana un parámetro `root=""` y sigue siendo puro.
4. **Encaje con las exportaciones**: cada guardado que antes construía
   `paths.project_dir(id, slug)` para escribir archivos ahora pasa por
   `project.storage_dir(p)` (9 call sites en `main_window.py`; `project show`
   del CLI imprime `folder:`). No cambia el modelo de datos de `project_files`.

**Alternativas**: mover los ficheros existentes al re-ubicar (rechazado: romper
rutas ya registradas y posibles referencias externas sin beneficio); sincronizar
iconos con un `QFileSystemWatcher` (fuera de alcance); un diálogo de «carpeta de
proyecto» en la creación (rechazado: añade fricción a Tonight; el override
existe vía hub).

**Consecuencias**: `user_version` de la BD sube a 6 (los tests que fijaban 5 se
actualizaron); 11 cadenas nuevas de GUI (ES/EN); no hay migración de ficheros;
los proyectos heredados conservan su carpeta exacta de siempre.

## English

**Context**: everything a project produces (plan, sequences, ephemerides,
FITS, posts, charts) is written under `paths.data_dir()/projects/<id>-<slug>`,
a fixed path governed by `platformdirs`. The user neither knew where the files
ended up nor had a way to point them at their working disk. Control over the
**container folder** was requested: a global root for all projects and, when
needed, a different folder for a specific project.

**Decision**:

1. **Configurable global root**: `projects_root` key in `config` (Settings >
   Observing, "Projects folder" group). Empty (`""`) = current behaviour
   (`data_dir()/projects`). The change only affects **new projects**: existing
   ones keep their folder in the DB and are never moved.
2. **Per-project folder in the DB**: `root_dir` in the `projects` table
   (`user_version` 5→6 migration: `ALTER TABLE ... ADD COLUMN root_dir TEXT` +
   backfill of existing rows to the legacy path). It is **frozen at creation**;
   the hub can change it ("Change folder…"), and `set_root_dir` only re-homes
   **future exports** — v1 does **not** move already-written files
   (`project_files` stores absolute paths).
3. **Layered resolution in `core/project.storage_dir`**: project `root_dir` →
   `config.projects_root` → legacy `data_dir()/projects`. Resolution lives in
   `core/project` so `paths` stays decoupled from `config`; `paths.project_dir`
   gains a `root=""` parameter and remains pure.
4. **Exports follow it**: every save that used to build
   `paths.project_dir(id, slug)` for writing files now goes through
   `project.storage_dir(p)` (9 call sites in `main_window.py`; the CLI's
   `project show` prints `folder:`). The `project_files` data model is unchanged.

**Alternatives**: move existing files on re-homing (rejected: breaks already
registered paths and possible external references for no benefit); sync the hub
icon with a `QFileSystemWatcher` (out of scope); a "project folder" picker at
creation time (rejected: adds friction to Tonight; the override exists via the
hub).

**Consequences**: DB `user_version` rises to 6 (tests hard-coding 5 were
updated); 11 new GUI strings (ES/EN); no file migration; legacy projects keep
their exact original folder.