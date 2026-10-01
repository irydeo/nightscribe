# ADR-055: Interfaz 1.0: del arranque en Tonight al hub de proyectos / Interfaz 1.0: from a Tonight-first start to the project hub

**Estado / Status**: Accepted · **Fecha / Date**: 2026-10-01 ·
**ejecutado / executed**: 2026-10-01 (suite unitaria green, i18n 0
unfinished)

**Ver / See**: ADR-019 (UX v3 centrada en proyectos; enmendado aquí: la
navegación) · ADR-044 (el UFE; enmendado aquí: deja de ser una ventana
flotante y pasa a ser una vista embebida) · ADR-005 (los `.ui`; los nuevos
`.ui` de Bienvenida y del formulario manual siguen la regla) · ADR-038 (la
app habla primero: los avisos ganan un hogar en Home) · ADR-040 (los chips
de eventos del cielo) · ADR-045 (el flujo por visitas; intacto)

## Español

**Contexto.** La app nació con «Esta noche» como pantalla raíz: al abrir,
calculaba el planificador (red) antes de que el observador pidiera nada, y
los proyectos vivían en una pestaña secundaria. Con el tiempo la app se
convirtió en un **gestor de proyectos de observación**, así que el orden se
había invertido: lo primero que se veía era lo que menos se usa (abrir
objetivos nuevos) y lo último lo que más (trabajar en proyectos ya
creados). El asistente de primera ejecución/actualización era un `QWizard`
modal que bloqueaba el arranque; el UFE era un `QDialog` flotante; y el
buscador manual de objetos vivía escondido en Herramientas.

**Decisión** (pactada con el observador, 2026-10-01):

1. **El arranque es la lista de proyectos (Home), sin red.** No se calcula
   nada al abrir. `app.py` deja de llamar al asistente modal y pasa el
   snapshot de backup a `MainWindow`.
2. **Un shell con vistas apiladas y pestaña vertical.** El `QTabWidget` de
   tres pestañas se sustituye por un `QStackedWidget` (Home · Tonight ·
   Campaigns · Detalle · Bienvenida · UFE) con una **pestaña vertical
   «PROYECTOS»** de 28 px siempre visible: abre la lista como *drawer*
   superpuesto desde cualquier vista.
3. **Cada vista ocupa toda el área de contenido.** Los widgets internos
   (Tonight, UFE, detalle, campañas) **no se rediseñan**: se re-alojan a
   pantalla completa. El interior de `tonight_tab.ui` y `ufe_dialog.ui`
   queda intacto.
4. **Bienvenida = el asistente, en línea.** Los tres pasos del `QWizard`
   (Observatorio → Objetivos → Datos) viven en `welcome_tab.ui` como un
   *stepper* clicable; se reutilizan literalmente los ayudantes de
   `gui/wizard.py` (`_detect`, `_resolve_site`, `_setup_kinds`,
   `_setup_data`, `_apply_site`, `_apply_kinds`, `_mark_done`). Bienvenida
   se muestra **solo cuando hace falta**: primera ejecución, actualización
   pendiente o cero proyectos. El paso **Datos** es **bloqueante una vez
   por versión** (gate de vista, no modal): hasta «Entendido» no se sale.
   Una primera ejecución sin observatorio **no bloquea**: la app abre y el
   CTA queda a la espera.
5. **Tonight, bajo demanda.** Se calcula al entrar en la vista de nuevo
   proyecto (`_maybe_compute_tonight`), nunca al arrancar. El botón ↻
   sigue forzando un recálculo.
6. **El buscador manual se embebe** en la vista de nuevo proyecto
   (`new_project_bar.py`), heredando el lookup VSX → SIMBAD que estaba en
   Herramientas ▸ Explore. Si no localiza el objeto, se ofrece el
   **formulario manual** (`manual_object_panel.ui` +
   `manual_object_panel.py`), con campos comunes (nombre, tipo, AR, Dec,
   magnitud) y un bloque por tipo; `to_target()` devuelve el mismo
   `context` que `core/project.py` ya sabe guardar.
7. **El UFE deja de ser flotante.** `UfeDialog` pasa de `QDialog` a
   `QWidget` (mismo nombre, misma API de hooks) y se aloja como página del
   shell, con una barra de retorno propia del host. Al salir de la vista se
   llama a `shutdown()` (lo que antes hacía `closeEvent`).
8. **Los avisos ganan un hogar.** Los chips de eventos del cielo (que
   caían al fondo de Tonight por un accidente de *parenting*) y la cadencia
   de SN viven en bandas de **Home**: «Qué pasa en el cielo» y «Toca
   revisitar». Las campañas se pliegan al hub como una tira que abre su
   vista.

**Consecuencias.** El arranque es instantáneo y offline; el proyecto es el
centro. El asistente deja de bloquear salvo el informe de datos de una
actualización. El UFE conserva su comportamiento interno pero pierde su
marco de ventana (no hay maximizar/minimizar propios: la ventana principal
es la que se maximiza). El `QStackedWidget` sustituye a la barra de
pestañas, así que los atajos Ctrl+1..3 pasan a Home · Tonight · Campañas.
Los tests de navegación comprueban `_shell_stack().currentIndex()` en vez
del `QTabWidget`.

**Correcciones (2026-10-01, tras la revisión del observador).** Dos
escollos reales que la primera pasada no vio (y que los tests tapaban al
forzar `is_configured=False`, que construía Bienvenida y hacía cuadrar los
índices por casualidad):

1. **Índices fijos.** La pila reserva SIEMPRE seis páginas: las cuatro
   vistas más dos placeholders para Bienvenida (4) y el UFE (5). Construir
   las perezosas con `addWidget()` las ponía en el primer índice libre y
   `VIEW_UFE` quedaba fuera de rango (el taller nunca se veía).
2. **Reparentar des-oculta.** `QStackedWidget.removeWidget()` esconde la
   página, y añadirla a un layout **no** la vuelve a mostrar: el panel
   «Te necesita» y la página de detalle salían en blanco («los proyectos
   no se cargan»). Hay que llamar a `show()` al re-alojarlas.
3. El `on_refresh_projects()` de arranque, sin selección, llamaba a
   `_show_dashboard` y saltaba a Home: ahora solo navega si ya se está en
   Home o en un proyecto, para no expulsar de Bienvenida en el primer
   fotograma. El UFE se mantiene vivo al cambiar de vista (solo se apaga al
   cerrar la app) y `TonightWorker` gana `cancel()`.

**Alternativas descartadas.** Mantener el `QWizard` modal (contradice «la
app habla primero» y bloquea el arranque). Un `QDockWidget` para el drawer
(más pesado que la geometría manual actual y con cromo nativo). Reparentar
la lista entre Home y el drawer (dos widgets de lista es más simple y no
puede divergir, porque el drawer se rellena desde la misma fuente).

## English

**Context.** The app was born with "Tonight" as the root screen: on open it
ran the planner (network) before the observer asked for anything, and
projects lived in a secondary tab. Over time the app became a **project
manager for scientific observing**, so the order had inverted: the first
thing seen was the least used (opening new targets) and the last was the
most used (working on existing projects). The first-run/update wizard was a
modal `QWizard` that blocked startup; the UFE was a floating `QDialog`; and
the manual object search hid in Tools.

**Decision** (agreed with the observer, 2026-10-01):

1. **Startup is the project list (Home), offline.** Nothing is computed on
   open. `app.py` stops calling the modal wizard and hands the backup
   snapshot to `MainWindow`.
2. **A shell of stacked views and a vertical tab.** The three-tab
   `QTabWidget` becomes a `QStackedWidget` (Home · Tonight · Campaigns ·
   Detail · Welcome · UFE) with an always-visible 28 px vertical
   **"PROJECTS" tab** that opens the list as an overlay drawer from any
   view.
3. **Every view fills the whole content area.** The internal widgets
   (Tonight, UFE, detail, campaigns) are **not redesigned**: they are
   re-hosted full-screen. The interior of `tonight_tab.ui` and
   `ufe_dialog.ui` is untouched.
4. **Welcome = the wizard, inline.** The three `QWizard` steps
   (Observatory → Targets → Data) live in `welcome_tab.ui` as a clickable
   stepper, reusing the helpers in `gui/wizard.py` verbatim. Welcome shows
   **only when needed**: first run, pending update or no projects. The
   **Data** step is **blocking once per version** (a view gate, not a
   modal): nothing else opens until "Got it". A first run with no
   observatory does **not** block.
5. **Tonight, on demand.** Computed when the new-project view is opened
   (`_maybe_compute_tonight`), never at start. The ↻ button still forces a
   fresh run.
6. **The manual search is embedded** in the new-project view, inheriting
   the VSX → SIMBAD lookup from Tools ▸ Explore. When it does not locate
   the object, the **manual form** is offered; `to_target()` returns the
   same `context` `core/project.py` already stores.
7. **The UFE is no longer floating.** `UfeDialog` goes from `QDialog` to
   `QWidget` (same name, same hook API) and is hosted as a shell page, with
   a host-owned back bar. Leaving the view calls `shutdown()`.
8. **Alerts get a home.** The sky-event chips (which fell to the bottom of
   Tonight by a parenting accident) and the SN cadence live in **Home**
   bands. Campaigns fold into the hub as a strip opening its view.

**Consequences.** Startup is instant and offline; the project is the
centre. The wizard only blocks for an update's data report. The UFE keeps
its internal behaviour but loses its own window frame. The stacked widget
replaces the tab bar, so Ctrl+1..3 map to Home · Tonight · Campaigns.
Navigation tests check `_shell_stack().currentIndex()` instead of the
`QTabWidget`.

**Corrections (2026-10-01, after the observer's review).** Two real traps
the first pass missed (and that the tests masked by forcing
`is_configured=False`, which built Welcome and made the indices line up by
accident): (1) **fixed indices**: the stack always reserves six pages (the
four views plus placeholders for Welcome at 4 and the UFE at 5), because
building the lazy ones with `addWidget()` put them at the first free index
and left `VIEW_UFE` out of range; (2) **reparenting un-hides**: a
`QStackedWidget.removeWidget()` page stays hidden, and adding it to a
layout does not show it again, so the dashboard and the project detail came
up blank. The startup `on_refresh_projects()` no longer yanks the observer
out of Welcome, the UFE stays alive across views (only shut down on app
close) and `TonightWorker` gained `cancel()`.
