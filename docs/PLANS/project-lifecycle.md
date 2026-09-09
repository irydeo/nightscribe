# Plan — Track A: ciclo de vida y clasificación de proyectos

> **Abierto (2026-09-09)** — hijo A de
> [project-concept-v2.md](project-concept-v2.md) (leer primero el padre).
> Un subplan = un commit.

**rama**: `feature/project-lifecycle` (nace de `feature/object-card` al día; mergea de vuelta a `feature/object-card`)
**fecha**: 2026-09-09 · **autor**: FJC (con la IA)

## Objetivo

Los proyectos se pueden **cerrar** (hoy solo `archived`/`delete`; `done` solo se
alcanza por CLI), **reabrir**, y el hub deja de ser una lista plana:
clasificación por **año**, filtro por **tipo**, **búsqueda** por nombre y
**orden** configurable. Además, los ficheros que el proyecto genera
(`project_files`) se **ven** y se abren desde la GUI.

## Contexto clave (exploración 2026-09-09)

- Modelo: `core/project.py` — `STEPS = ("plan","process","publish")`,
  estados `active/done/archived`; `set_status` (L232), `advance` (L151, pone
  `done` al acabar el último paso — **la GUI nunca lo llama**, usa
  `set_step_status`), `list_projects` (L103-116, `ORDER BY updated DESC`
  fijo), `add_file`/`list_files` (L242/L255).
- Esquema: `core/db.py` — `_V1` (L74-101: `projects`, `project_steps`,
  `project_files`), migraciones en `_migrate` (L104-160; hoy `user_version` 3).
  `observations.project_id` existe pero **nadie lo escribe** (código muerto).
- Hub: `gui/ui/projects_tab.ui` (combo Active/All/Done/Archived L14-19,
  `lst_projects`, `btn_archive`/`btn_delete` L32-33) y `gui/main_window.py`
  (`on_refresh_projects` L1368, `_project_archive` L2473 — sin confirmación ni
  deshacer —, `_project_delete` L2480, `_render_project_header` L1459).
- Exports hoy a **carpetas planas**: `data_dir()/exports` y `data_dir()/posts`;
  ADR-022 ya decía «carpeta del proyecto» — nunca se hizo.
- Blink no registra sus GIF/MP4/PNG; la ruta del FITS de SN no se persiste.

## Subplanes

### A0 — Migración `user_version 4`
`core/db.py::_migrate`: `ALTER TABLE projects ADD COLUMN closed_at REAL` (NULL)
+ índice por `created`. Patrón de las migraciones 1-3.

**Tests**: migración 3→4 conserva filas; `closed_at` NULL por defecto; base
nueva nace en v4.

### A1 — `close()` / `reopen()` en core
`core/project.py`: `close(pid)` → `status='done'` + `closed_at=now` (idempotente;
solo desde `active`); `reopen(pid)` → `status='active'` + `closed_at=NULL`.
`delete` y `set_status('archived')` siguen igual.

**Tests**: ciclo active→done→active; close sobre done no rompe; closed_at se
limpia al reabrir.

### A2 — GUI: cerrar/reabrir
`projects_tab.ui` + `main_window.py`:
- Botón **Cerrar proyecto** (confirmación con `QMessageBox`), **Reabrir** cuando
  `status in (done, archived)`.
- **«Mark done» en el último paso propone cerrar** («¿Cerrar el proyecto?»).
- Cabecera del proyecto muestra la fecha de cierre cuando exista.
- Archive pide confirmación (hoy no) y se puede desarchivar con Reabrir.

**Tests**: offscreen — botones por estado, diálogo de cierre, fecha visible.

### A3 — Clasificación del hub
`project.list_projects(status=None, kind=None, search=None, order="updated")`
(args nuevos, retrocompatible) y hub:
- **Agrupación por año** de `created` (cabeceras de sección en la lista; el año
  de creación es el «año del proyecto»).
- Combo **tipo** (All + `VALID_KINDS`).
- Caja **búsqueda** (nombre contiene, case-insensitive).
- Combo **orden**: actualización / creación / nombre.
- El combo de estado actual se conserva. Preferencias en `config`
  (`projects_filter_*`) restauradas al arrancar.

**Tests**: unit de `list_projects` con cada arg; offscreen del hub (secciones
por año, filtro por tipo, búsqueda, orden) con proyectos fake.

### A4 — Ficheros visibles + carpeta por proyecto
- Pestaña **Detalles**: lista de `project_files` (icono por `kind`, nombre,
  fecha; doble clic = abrir; botón «mostrar en carpeta» — `QDesktopServices`).
- Se registran también: exports del blink (GIF/MP4/PNG) y la ruta del FITS del
  paso Process (persistir en `project_steps.data` + `project_files kind='fits'`).
- Los exports nuevos van a `data_dir()/projects/<id>-<slug>/` (creada al vuelo);
  los ficheros ya registrados con rutas planas antiguas siguen funcionando (no
  se migran ficheros, solo se leen rutas).
- **Los FITS nunca se copian**: solo se registran rutas.

**Tests**: offscreen — lista poblada desde `project_files` fake; registro de
blink/FITS; creación de la subcarpeta.

### A5 — Cierre del track
CLI `project close|reopen|files` (paridad mínima, `__main__.py`) · i18n ES/EN
(`lupdate` con `gui/widgets/*.py`, ADR-014) · sección en `docs/WORKFLOWS.es/.md`
y marca «Hecho» en el padre · `pytest tests/unit` verde.

## Orden de ejecución

A0 → A1 → A2 → A3 → A4 → A5
(A2 depende de A1; A3 y A4 son independientes entre sí; A5 cierra.)

## Fuera de alcance

- Bundle/export del proyecto cerrado a disco (zip) — posible v2.
- Notas/diario del proyecto y etiquetas libres — posible v2.
- Reescribir `observations.project_id` (código muerto) — se decide al tocar
  Historial, no aquí.

## Riesgos conocidos

- Cambiar el directorio de exports puede despistar al usuario si busca los
  ficheros viejos: la lista de A4 siempre muestra la ruta real registrada.
- Agrupar por año con muchos proyectos exige lista virtualizada si crece
  (hoy decenas — `QListWidget` basta; revisar si supera ~500).
