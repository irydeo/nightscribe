# Plan — Track A: ciclo de vida y clasificación de proyectos

> **Abierto (2026-09-09)** — hijo A de
> [project-concept-v2.md](project-concept-v2.md) (leer primero el padre;
> decisiones transversales T1–T10). Un subplan = un commit.
> **Enmendado 2026-09-09 (post-entrevista)**: el cierre gana **resultado
> final** (`outcome`), el proyecto gana **etiquetas** y **favoritos**, y nace
> el **asesor de cierre** (T10: la app sugiere, nunca decide). Reabrir queda
> confirmado como caso de uso real (revisita «un año después», precedente
> AT2020sum/sun en irydeo.com).

**rama**: `feature/project-lifecycle` (nace de `feature/object-card` al día; mergea de vuelta a `feature/object-card`)
**fecha**: 2026-09-09 · **autor**: FJC (con la IA)

## Objetivo

Los proyectos se pueden **cerrar** (hoy solo `archived`/`delete`; `done` solo se
alcanza por CLI) con **resultado final**, **reabrir** (la revisita al cabo de un
año es un flujo real), y el hub deja de ser una lista plana: clasificación por
**año**, filtro por **tipo** y por **etiquetas**, **favoritos**, **búsqueda**
por nombre y **orden** configurable. Además, los ficheros que el proyecto
genera (`project_files`) se **ven** y se abren desde la GUI.

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
- **Volumen real declarado** (entrevista): 4-5 proyectos activos a la vez,
  ~50-100/año → `QListWidget` con cabeceras de año basta; sin virtualización.

## Subplanes

### A0 — Migración `user_version 4`
`core/db.py::_migrate`:
- `ALTER TABLE projects ADD COLUMN closed_at REAL` (NULL)
- `ALTER TABLE projects ADD COLUMN outcome TEXT` (NULL — resultado final)
- `ALTER TABLE projects ADD COLUMN tags TEXT DEFAULT ''` (separadas por comas)
- `ALTER TABLE projects ADD COLUMN favorite INTEGER DEFAULT 0`
- Índice por `created`. Patrón de las migraciones 1-3.

**Tests**: migración 3→4 conserva filas; columnas nuevas con valores por
defecto; base nueva nace en v4.

### A1 — `close()` / `reopen()` / metadatos en core
`core/project.py`:
- `close(pid, outcome=None)` → `status='done'` + `closed_at=now` + `outcome`
  (idempotente; solo desde `active`).
- `reopen(pid)` → `status='active'` + `closed_at=NULL` + `outcome=NULL`
  (un proyecto reabierto aún no tiene resultado).
- `set_tags(pid, tags)` / `set_favorite(pid, fav)`.
- `OUTCOMES` por tipo (p. ej. SN: `confirmed_ia`/`confirmed_other`/
  `false_positive`/`lost`/`completed`; genérico: `completed`/`abandoned`) —
  lista cerrada traducible, con «Otro» libre.

**Tests**: ciclo active→done→active limpia cierre y resultado; outcome/tags/
favorite persisten; outcome inválido se rechaza.

### A2 — GUI: cerrar/reabrir con resultado + asesor
`projects_tab.ui` + `main_window.py`:
- Botón **Cerrar proyecto** → diálogo con confirmación **y selector de
  resultado** (`outcome`, con «Otro» libre). **Reabrir** cuando
  `status in (done, archived)`.
- **«Mark done» en el último paso propone cerrar** (mismo diálogo).
- Cabecera del proyecto muestra fecha de cierre y resultado cuando existan.
- Archive pide confirmación (hoy no); Reabrir sirve también desde `archived`.
- **Asesor (T10)**: infraestructura de sugerencia en la cabecera del proyecto
  (banner ámbar, descartable). v1: sugiere cerrar proyectos `active` sin
  actividad en `config["close_advisor_days"]` (default 30). El track B (B11)
  enchufa la señal de evolución SN («evolución normal desde N días») a esta
  misma infraestructura. **Sugiere, nunca decide.**

**Tests**: offscreen — botones por estado, diálogo con outcome, banner del
asesor visible/no según antigüedad, descarte del banner.

### A3 — Clasificación del hub
`project.list_projects(status=None, kind=None, search=None, tags=None,
favorites_first=False, order="updated")` (args nuevos, retrocompatible) y hub:
- **Agrupación por año** de `created` (cabeceras de sección en la lista).
- Combo **tipo** (All + `VALID_KINDS`).
- Caja **búsqueda** (nombre contiene, case-insensitive).
- **Etiquetas**: editor de tags en la cabecera del proyecto (chips editables)
  + filtro por etiqueta en el hub.
- **Favoritos**: estrella en la cabecera; opción «favoritos primero».
- Combo **orden**: actualización / creación / nombre.
- El combo de estado actual se conserva. Preferencias en `config`
  (`projects_filter_*`) restauradas al arrancar.

**Tests**: unit de `list_projects` con cada arg; offscreen del hub (secciones
por año, filtros tipo/etiqueta, favoritos primero, búsqueda, orden) con
proyectos fake.

### A4 — Ficheros visibles + carpeta por proyecto
- Pestaña **Detalles**: lista de `project_files` (icono por `kind`, nombre,
  fecha; doble clic = abrir; botón «mostrar en carpeta» — `QDesktopServices`).
- Se registran también: exports del blink (GIF/MP4/PNG) y la ruta del FITS del
  paso Process (persistir en `project_steps.data` + `project_files kind='fits'`).
- Los exports nuevos van a `data_dir()/projects/<id>-<slug>/` (creada al vuelo);
  los ficheros ya registrados con rutas planas antiguas siguen funcionando (no
  se migran ficheros, solo se leen rutas).
- **Los FITS nunca se copian**: solo se registran rutas (T4).

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
- Diario largo del proyecto (las notas por **sesión** son del track B, B2) —
  aquí solo etiquetas/resultado.
- Reescribir `observations.project_id` (código muerto) — se decide al tocar
  Historial, no aquí.

## Riesgos conocidos

- Cambiar el directorio de exports puede despistar al usuario si busca los
  ficheros viejos: la lista de A4 siempre muestra la ruta real registrada.
- El asesor de cierre basado en «sin actividad» es tosco para SN (cadencia
  2-3 días): por eso la señal buena llega en B11; mientras tanto el banner es
  descartable y nunca bloquea (T10).
- Etiquetas libres pueden degradarse (typos): autocompletado con las ya usadas.
