# ADR-019: UX v3 — project-centric workflow

**Estado / Status**: Accepted · **Fecha / Date**: 2026-08-24 · **Revisión / Review**: 2026-08-28

## Español

**Contexto**: tras la v2 (ADR-017), una reflexión de producto del usuario: NightScribe
no debe ser «otro planetario/planificador más», sino una herramienta que facilite la
vida al observador. La pregunta real de partida es «¿qué puedo hacer esta noche — o
ahora mismo?», respondida bajo las restricciones físicas del observatorio (horizonte
real, equipo, Luna — ADR-020); y de la sugerencia elegida nace un **proyecto** que guía
el resto del flujo **con todo el contexto**. Hoy cada pestaña vuelve a pedir los datos:
el blink pregunta objeto/coordenadas/FITS cada vez, aunque la app ya los conozca.

**Decisión**:

- **Cuatro pestañas**: Esta noche · **Proyectos** · Solar · Historial. Sustituye la
  disposición de pestañas de ADR-017 (el resto de ADR-017 sigue vigente: barra de menú,
  banda «ahora mismo», columnas dinámicas, un solo idioma en pantalla).
- **Esta noche = punto de entrada del usuario**: cada tarjeta/fila muestra la ventana
  real de observación (con «inicio seguro hasta HH:MM», ADR-020) y ofrece **«Crear
  proyecto»**.
- **Proyecto**: entidad persistente por objetivo, con tipo (`sn`, `neo`, `comet`,
  `pccp`, `transit`), estado (`active`/`done`/`archived`) y **pasos guiados**:
  Plan → Captura → Procesado → Publicar. El contexto (coords, mag, rate,
  ventana, secuencia exportada, FITS importado, medidas, posts) viaja con el proyecto:
  ningún paso vuelve a preguntar lo que ya se sabe. Flujos detallados por tipo en
  `docs/WORKFLOWS.md` / `docs/WORKFLOWS.es.md`.
- **Explore/Post/Blink contextuales**: dejan de ser pestañas de primer nivel; se abren
  desde un proyecto (o desde Esta noche) pre-rellenados. El acceso ad-hoc se conserva
  en el menú Herramientas (p. ej. blink suelto de una SN sin proyecto).
- **GUI primero**: toda la lógica vive en `core/` (compartida, per ARCHITECTURE); la
  CLI solo añadirá un subcomando `project` mínimo al final de la migración.

**Revisión (2026-08-28)** — paso «Análisis» eliminado (ahora 4 pasos, no 5):

- El paso «Análisis» quedaba redundante con la pestaña *Detalles* (`ObjectPanel`,
  fase D4/D5), que ya muestra la visión del objeto (frase de enganche, parámetros,
  gráficos) al abrir un proyecto. En 4 de los 5 tipos su única acción era «Explorar
  objeto…», que abría exactamente ese mismo panel.
- La única cosa que vivía ahí y no estaba en otra parte era el **blink de las SN**,
  que se mueve al paso *Procesado* (importa el FITS y confirma), donde encaja
  naturalmente.
- Consecuencias: `core/project.py` `STEPS` pasa a 4; migración `user_version` 1→2
  (borra las filas `analyse` y, si un proyecto se había quedado en ese paso, pasa
  `current` a `publish`); `gui/main_window.py` elimina `_build_analyse_tab` y
  `_project_explore`; el stepper muestra `/4`. El diálogo *Explore…* del menú
  Herramientas se conserva intacto (ad-hoc, sin proyecto).

**Persistencia** (migraciones `user_version` 0→1→2 en `core/db.py`, per ADR-002):

- `projects(id, kind, object_name, status, created, updated, context JSON)`
- `project_steps(project_id, step, status, data JSON, updated)`
- `project_files(project_id, path, kind, created)`
- `observations` gana columna `project_id` NULL.
- `user_version` 1→2: elimina el paso `analyse` (revisión 2026-08-28).

**Consecuencias**: `gui/main_window.py` se reorganiza (hub de Proyectos con stepper por
tipo); las tarjetas de Esta noche ganan la acción «Crear proyecto»; el blink standalone
sigue existiendo pero pre-rellenado desde proyecto; los tests GUI offscreen se reescriben
a la nueva navegación. Cometas y tránsitos reutilizan el esqueleto de 4 pasos más
adelante. El trabajo se ejecuta por fases (ver §7 de WORKFLOWS): primero los ADRs y los
flujos sobre papel, después restricciones → modelo de proyecto → GUI → exportadores →
reporte MPC.

## English

**Context**: after v2 (ADR-017), a product reflection from the user: NightScribe must
not be "yet another planetarium/planner", but a tool that makes the observer's life
easier. The real starting question is "what can I do tonight — or right now?", answered
under the observatory's physical constraints (real horizon, equipment, Moon — ADR-020);
and from the chosen suggestion a **project** is born that guides the rest of the flow
**with full context**. Today every tab re-asks for data: the blink asks for
name/coordinates/FITS every time, even when the app already knows them.

**Decision**:

- **Four tabs**: Tonight · **Projects** · Solar · History. This replaces the tab layout
  of ADR-017 (the rest of ADR-017 stands: menu bar, "right now" band, dynamic columns,
  single on-screen language).
- **Tonight = user entry point**: every card/row shows the real observing window (with
  "safe start until HH:MM", ADR-020) and offers **"Create project"**.
- **Project**: persistent entity per target, with kind (`sn`, `neo`, `comet`, `pccp`,
  `transit`), status (`active`/`done`/`archived`) and **guided steps**:
  Plan → Capture → Process → Publish. Context (coords, mag, rate, window,
  exported sequence, imported FITS, measurements, posts) travels with the project: no
  step re-asks what is already known. Per-kind flows detailed in `docs/WORKFLOWS.md`.
- **Contextual Explore/Post/Blink**: no longer top-level tabs; they open from a project
  (or from Tonight) pre-filled. Ad-hoc access stays under the Tools menu (e.g. a loose
  SN blink without a project).
- **GUI first**: all logic lives in `core/` (shared, per ARCHITECTURE); the CLI only
  gains a minimal `project` subcommand at the end of the migration.

**Review (2026-08-28)** — the "Analyse" step was removed (now 4 steps, not 5):

- The "Analyse" step was redundant with the *Details* tab (`ObjectPanel`, phases
  D4/D5), which already renders the object view (hook phrase, parameters, charts) as
  soon as a project is opened. In four of the five kinds its only action was
  "Explore object…", which opened exactly that same panel.
- The one thing that only lived there was the **SN blink**, which moves into the
  *Process* step (import the FITS, then confirm) where it fits naturally.
- Consequences: `core/project.py` `STEPS` drops to 4; `user_version` 1→2 migration
  (removes the `analyse` rows and, for a project that was parked there, moves the
  `current` flag to `publish`); `gui/main_window.py` drops `_build_analyse_tab` and
  `_project_explore`; the stepper now shows `/4`. The Tools-menu *Explore…* dialog is
  untouched (ad-hoc, no project).

**Persistence** (`user_version` 0→1→2 migrations in `core/db.py`, per ADR-002):

- `projects(id, kind, object_name, status, created, updated, context JSON)`
- `project_steps(project_id, step, status, data JSON, updated)`
- `project_files(project_id, path, kind, created)`
- `observations` gains a NULL `project_id` column.
- `user_version` 1→2: removes the `analyse` step (review 2026-08-28).

**Consequences**: `gui/main_window.py` is reorganised (Projects hub with a per-kind
stepper); Tonight cards gain the "Create project" action; the standalone blink survives
but pre-filled from a project; offscreen GUI tests are rewritten to the new navigation.
Comets and transits reuse the 4-step skeleton later. Work runs in phases (see §7 of
WORKFLOWS): ADRs and flows on paper first, then constraints → project model → GUI →
exporters → MPC report.
