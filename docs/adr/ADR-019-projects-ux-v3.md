# ADR-019: UX v3 — project-centric workflow

**Estado / Status**: Accepted · **Fecha / Date**: 2026-08-24 · **Revisión / Review**: 2026-08-28, 2026-09-02, 2026-09-06, 2026-09 (Track UX), 2026-09-16

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

**Revisión (2026-09-02)** — punto de entrada unificado (fase E):

- **Explore es la única puerta de entrada desde Esta noche**: clic en una fila, doble
  clic en cualquier columna de la tabla y el botón de la tarjeta abren siempre el
  diálogo *Explorar* pre-rellenado. Antes, la fila abría el panel de detalles directamente
  y solo el botón de la tarjeta llevaba al diálogo.
- **El proyecto se crea o retoma *dentro* del diálogo**, desde la pestaña *Detalles*
  (`ObjectPanel`) con dos botones mutuamente excluyentes: «Continuar proyecto» (si ya
  existe uno `active` para ese objeto) o «Crear proyecto» (si no). El resto del tiempo
  (sin proyecto en foco, o en el hub) los botones no se muestran. `ObjectPanel` recibe
  `project_lookup` inyectado desde `MainWindow` — no importa `core.db` directamente.
- El botón de la tarjeta refleja el estado: «▶ Continuar» si hay proyecto `active`,
  «🔭 Explorar» si no; si al pulsar «Continuar» el proyecto ya no existe, cae a «Explorar».
- Consecuencias: `gui/overview.py` `ObjectPanel` gana la señal `project_action`, los
  botones `btn_project_continue`/`btn_project_create` y `_refresh_project_buttons()`;
  `gui/main_window.py` gana `_table_open_explore`, `_goto_active_project` y refactoriza
  `_start_or_continue`; i18n ES/EN ampliada; tests unitarios de las tres vistas.

**Revisión (2026-09-06)** — «Captura» se funde en «Plan» (paso único Plan & Captura):

- Planificar la sesión (tomas/exposición/filtro), exportar la secuencia y ejecutarla es
  **un único paso**, no dos. La pestaña «Captura» desaparece: su contenido (calibración
  CCDciel, exportación NINA/CCDciel/CSV, efemérides NEO) se integra en la pestaña del
  Plan, que además gana el **control real de CCDciel** (ADR-030).
- Consecuencias: `core/project.py` `STEPS` pasa a `("plan","process","publish")`;
  migración `user_version` 2→3 (funde los `data` de `capture` en `plan`, pasa `current`
  a `process` si un proyecto se había quedado en captura y borra la fila); el stepper
  muestra `/3`; `_build_capture_tab` se elimina y su contenido vive en `_build_plan_tab`.

**Persistencia** (migraciones `user_version` 0→1→2→3 en `core/db.py`, per ADR-002):

- `projects(id, kind, object_name, status, created, updated, context JSON)`
- `project_steps(project_id, step, status, data JSON, updated)`
- `project_files(project_id, path, kind, created)`
- `observations` gana columna `project_id` NULL.
- `user_version` 1→2: elimina el paso `analyse` (revisión 2026-08-28).
- `user_version` 2→3: elimina el paso `capture`, fundido en `plan` (revisión 2026-09-06).

**Consecuencias**: `gui/main_window.py` se reorganiza (hub de Proyectos con stepper por
tipo); las tarjetas de Esta noche ganan la acción «Crear proyecto»; el blink standalone
sigue existiendo pero pre-rellenado desde proyecto; los tests GUI offscreen se reescriben
a la nueva navegación. Cometas y tránsitos reutilizan el esqueleto de 4 pasos más
adelante. El trabajo se ejecuta por fases (ver §7 de WORKFLOWS): primero los ADRs y los
flujos sobre papel, después restricciones → modelo de proyecto → GUI → exportadores →
reporte MPC.

**Revisión (2026-09-10, Track D)**: el paso **Plan** gana el bloque de tránsito
(línea de tiempo visual de la noche, tira de tiempos UTC+local con overhead
explícito, exposición heurística preseleccionada, aviso de cadencia y checklist
pre-vuelo persistente en `project_steps.data`); el paso **Process** del tránsito
cita **EXOTIC** como herramienta externa de reducción y exporta su `inits.json`
(handoff — ADR-015). El esqueleto de 3 pasos no cambia: es contenido por tipo,
no pasos nuevos. El paso Process de NEO/PCCP/cometa (Track C, misma semana)
registra los productos de la sesión (FITS, imágenes anotadas, reporte MPC) en
`project_files` + `project_steps.data`.

**Revisión 2026-09 (Track UX, decisión UX-i/UX-j del plan)**: la presentación
de los pasos guiados cambia de «pestañas internas + stepper (Previous/Skip/Mark
done/Next)» a **página única con secciones plegables** y una tarjeta «Siguiente
acción» alimentada por `project.next_action()`. La auditoría de usabilidad
mostró el doble modelo de navegación (pestañas libres + wizard) y los iconos
de estado ✔/●/○/– como la fuente de complejidad del flujo de proyecto.
**El modelo no cambia**: `project_steps` y sus estados
(`pending/current/done/skipped`) siguen siendo la fuente de verdad; el cierre
automático al completar el último paso se conserva. El control de CCDciel sale
del paso Plan a la pestaña **Observatory** (6ª): la conexión ya era de
ventana, ahora también su UI.

**Revisión 2026-09 (acordeón + chip de estado)**: la página del proyecto
gana la regla del «único lugar de aterrizaje» — toda la página es un único
acordeón exclusivo donde como mucho una de las secciones **Ficha de objeto /
plan / procesado / publicar / seguimiento** está abierta a la vez (0 abiertas
es un estado de reposo legal; nada se fuerza abierto). Un clic real en la
cabecera lo gobierna (`sectionToggled`, disparado solo por el clic del
usuario; el `setCollapsed()` programático permanece silencioso, así que el
cierre de hermanas nunca rebota), y cada enlace profundo (el botón «Go»,
los chips de cadencia, las acciones de contexto) se enruta por el mismo
camino de scroll-a-sección que impone el invariante. Un proyecto recién
creado se abre con solo su sección de siguiente acción expandida — la ficha
de objeto arranca plegada como las demás (un borrador anterior mantenía la
ficha y la lista de ficheros inmunes al grupo; quedó revocado: la ficha
participa para que la página nunca muestre dos secciones abiertas a la vez).
Los *estados* ya vivían en palabras en la fila del toggle de cada paso
(«hecho el <fecha>» / «saltado» / «pendiente»); esas mismas palabras viajan
ahora en la cabecera de la sección como chip, de modo que el estado del paso
sobrevive aunque el paso esté plegado.

**Revisión (2026-09-16)** — reasentamiento de pestañas y rol de Campañas
(ADR-036 / ADR-037): la línea «Cuatro pestañas: Esta noche · Proyectos ·
Solar · Historial» queda **superseded**. La barra final son **cinco**
pestañas — *Esta noche · Proyectos · Campañas · Sol y cielo · Observatorio*:
History sale de la barra y se convierte en el diálogo «Diario de
observación…» del menú Herramientas (vista derivada auto-generada — la
tabla `observations` llevaba sin escritor desde `8822ca7`), y Solar se
renombra «Sol y cielo» como pestaña de divulgación con salida a redes
(ADR-036). El rol de la pestaña Campaigns se redefine como **consola de
señales** del compromiso (eventos ⚡ y extremos ⏳ agregados), frente a
Proyectos = ejecutar (ADR-037). El modelo de proyecto (3 pasos, página
única, ciclo de vida) no cambia.

**Revisión (2026-09-17, ADR-038)** — el hub aprende a hablar primero: sin
selección, el panel derecho es el dashboard **«Necesita tu atención»**
(alimentado por el nuevo `core/attention.py`, aditivo). La página del
proyecto conserva las secciones en acordeón, pero la máquina de pasos se
comanda desde la **tarjeta Next** (Mark done/Skip junto a Go →); las
secciones conservan solo un pie discreto con «Reopen step»/«Skip step». El
ciclo de vida se consolida en el menú **⋯** de la cabecera (tags, carpetas,
Close/Reopen/Archive/Delete) y la lista pasa a filas ricas con filtros
avanzados tras «Filters ▸». El modelo (3 pasos, ciclo de vida, página
única) sigue sin cambiar.

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

**Review (2026-09-02)** — single unified entry point (phase E):

- **Explore is the only doorway from Tonight**: clicking a row, double-clicking any
  table column and the card button all open the pre-filled *Explore* dialog. Before,
  the row opened the details panel directly and only the card button went to the dialog.
- **The project is created or resumed *inside* the dialog**, on the *Details* tab
  (`ObjectPanel`) via a **single CTA** (one full-width button at the bottom): it shows
  "Continue project" (green) when an `active` one already exists for that object, or
  "Create project" (orange) when it does not. Otherwise (no project in focus, or in the
  hub) the CTA is hidden. `ObjectPanel` receives `project_lookup` injected from
  `MainWindow` — it does not import `core.db` directly. The CTA fires one of two
  distinct signals (`project_create` / `project_continue`, each `(name, fallback)`), so
  the owner never decodes a flag argument to know the intent. The D5 "Create post"
  button is gone: posts are written inside the project (Publish step) or ad-hoc from Tools.
- The card button reflects the state: "▶ Continue" if there is an `active` project,
  "🔭 Explore" if not; pressing "Continue" on a project that no longer exists falls
  back to "Explore".
- Consequences: `gui/overview.py` `ObjectPanel` gains the `btn_project` CTA, the
  `project_create` / `project_continue` signals and `_refresh_cta()` / `_cta_clicked()`;
  `gui/main_window.py` gains `_table_open_explore`, `_goto_active_project`, the
  `_on_create` / `_on_continue` glue and refactors `_start_or_continue`; ES/EN i18n
  extended (stale "Create post" strings retired from both `.ts`, `.qm` recompiled);
  unit tests cover the three views.

**Review (2026-09-06)** — "Capture" merged into "Plan" (single Plan & Capture step):

- Planning the session (frames/exposure/filter), exporting the sequence and running it
  is **one step**, not two. The "Capture" tab disappears: its content (CCDciel
  calibration, NINA/CCDciel/CSV export, NEO ephemerides) moves into the Plan tab, which
  additionally gains **real CCDciel control** (ADR-030).
- Consequences: `core/project.py` `STEPS` becomes `("plan","process","publish")`;
  `user_version` 2→3 migration (merges the `capture` data into `plan`, hands `current`
  to `process` if a project was parked there, and drops the row); the stepper now shows
  `/3`; `_build_capture_tab` is gone, its content lives in `_build_plan_tab`.

**Persistence** (`user_version` 0→1→2→3 migrations in `core/db.py`, per ADR-002):

- `projects(id, kind, object_name, status, created, updated, context JSON)`
- `project_steps(project_id, step, status, data JSON, updated)`
- `project_files(project_id, path, kind, created)`
- `observations` gains a NULL `project_id` column.
- `user_version` 1→2: removes the `analyse` step (review 2026-08-28).
- `user_version` 2→3: removes the `capture` step, merged into `plan` (review 2026-09-06).

**Consequences**: `gui/main_window.py` is reorganised (Projects hub with a per-kind
stepper); Tonight cards gain the "Create project" action; the standalone blink survives
but pre-filled from a project; offscreen GUI tests are rewritten to the new navigation.
Comets and transits reuse the 4-step skeleton later. Work runs in phases (see §7 of
WORKFLOWS): ADRs and flows on paper first, then constraints → project model → GUI →
exporters → MPC report.

**Review (2026-09-10, Track D)**: the **Plan** step gains the transit block
(visual night timeline, UTC+local times strip with explicit overhead,
preselected heuristic exposure, cadence warning and a persistent pre-flight
checklist in `project_steps.data`); the transit **Process** step names
**EXOTIC** as the external reduction tool and exports its `inits.json`
(handoff — ADR-015). The 3-step skeleton is unchanged: this is per-kind
content, not new steps. The NEO/PCCP/comet Process step (Track C, same week)
registers the session products (FITS, annotated images, MPC report) in
`project_files` + `project_steps.data`.

**Review 2026-09 (Track UX, plan decision UX-i/UX-j)**: the guided-steps
presentation changes from "inner tabs + stepper (Previous/Skip/Mark done/Next)"
to a **single page with collapsible sections** and a "Next action" card fed by
`project.next_action()`. The usability audit showed the doubled navigation
model (free tabs + wizard) and the state icons ✔/●/○/– as the source of the
project flow's complexity. **The model does not change**: `project_steps` and
its states (`pending/current/done/skipped`) remain the source of truth; the
auto-close on the last completed step is kept. The CCDciel control leaves the
Plan step for the **Observatory** tab (6th): the connection was already
window-level, now so is its UI.

**Review 2026-09 (accordion + state chip)**: the project page gains the
missing "one landing spot" rule — the whole page is one exclusive
accordion where at most one of **Object card / plan / process / publish /
follow-up** is open at a time (0 open is a legal resting state; nothing
is force-opened). A real header click drives it (`sectionToggled`, fired
only from the user click; programmatic `setCollapsed()` stays silent, so
sibling-closes never echo back), and every deep link (the "Go" button,
cadence chips, context actions) routes through the same scroll-to-section
path that enforces the invariant. A fresh project opens with only its
next-action section expanded — the object card starts folded like the
rest (an earlier draft kept the card and the project-files list immune to
the group; that was revoked: the card participates so the page never
shows two open sections at once). The *states* already lived in words on
each step's toggle row ("done on <date>" / "skipped" / "pending"); the
same words now ride the section header as a chip so the step status
survives even when a step is collapsed.

**Review (2026-09-16)** — tab settlement and the Campaigns role (ADR-036 /
ADR-037): the line "Four tabs: Tonight · Projects · Solar · History" is
**superseded**. The final bar holds **five** tabs — *Tonight · Projects ·
Campaigns · Sun & sky · Observatory*: History leaves the bar and becomes
the "Observing journal…" dialog under the Tools menu (an auto-generated
derived view — the `observations` table had no writer since `8822ca7`),
and Solar is renamed "Sun & sky" as the outreach tab with a social-media
output (ADR-036). The Campaigns tab's role is redefined as the
commitment's **signals console** (aggregated ⚡ events and ⏳ extrema),
versus Projects = execute (ADR-037). The project model (3 steps, single
page, lifecycle) is unchanged.

**Review (2026-09-17, ADR-038)** — the hub learns to speak first: with no
selection, the right pane is the **"Needs your attention"** dashboard (fed
by the new, additive `core/attention.py`). The project page keeps its
accordion sections, but the step machine is commanded from the **Next
card** (Mark done/Skip beside Go →); sections keep only a discreet footer
("Reopen step"/"Skip step"). The lifecycle consolidates into the header
**⋯** menu (tags, folders, Close/Reopen/Archive/Delete) and the list
becomes rich rows with the advanced filters behind "Filters ▸". The model
(3 steps, lifecycle, single page) still does not change.
