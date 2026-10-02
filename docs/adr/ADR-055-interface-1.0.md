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

**Revisión (2026-10-01, Interfaz 1.3).** El panel «Necesita tu atención» y
la banda «Toca revisar» se **disuelven en el listado**: la fila ya dice la
próxima acción, la urgencia y la edad de la última visita, así que una
segunda superficie era redundante. Home queda cabecera + banda del cielo +
lista + tira de campañas. Con la lista en pantalla, el **drawer lateral no
se muestra en Home** (la pestaña vertical `PROYECTOS` se oculta allí y solo
aparece en las demás vistas). Las flechas Atrás/Adelante de la barra crecen,
y el botón «Volver» del UFE se retira (lo cubre la pila general, ADR-056).

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

**Revisión (2026-10-01, Interfaz 1.4: el rediseño de Bienvenida).**
Bienvenida era correcta pero plana: una banda degradada con medio panel
vacío, un muro de casillas con párrafos largos y unos formularios que
pedían coordenadas sin devolver nada. El primer fotograma de una
herramienta que lee el cielo no parecía el cielo, y escribir la primera
latitud no tenía recompensa.

1. **El héroe es un cielo pintado.** `assets/welcome_sky.svg` (dibujo
   propio, GPL) se rasteriza una vez por tamaño y `gui/widgets/
   welcome_sky.py` pinta encima **la Luna real de esta noche**, leída de
   `ephem_minor.moon(jd)`: la fase que se ve es la que dice el almanaque.
   El widget entra por el patrón de siempre (placeholder `QWidget` +
   `drop_in`, ADR-005) y cae a un degradado pintado a mano si falta el
   asset o QtSvg.
2. **«Tu noche, ahora mismo».** Una banda viva, 100 % local
   (`coords.tonight_window` + `ephem_minor.moon`/`planet`): ventana de
   oscuridad en hora local, fase y puesta de Luna, y planetas sobre el
   horizonte al anochecer. Se recalcula con cada cambio de sitio; ninguna
   consulta sale a la red.
3. **El stepper es un rail.** El conector se rellena al avanzar y los
   pasos hechos llevan marca; el texto del `.ui` se conserva debajo.
4. **Los objetivos son tarjetas.** Rejilla de tarjetas con el color de
   `KIND_COLORS` de cada tipo, clicables enteras, con el resumen a un
   vistazo y el párrafo completo y la fuente en el tooltip.
   `_setup_kinds(..., card=True)` sigue devolviendo el mismo
   `{kind_id: QCheckBox}`, así que `_apply_kinds` y la compuerta no
   cambian.
5. **Los datos son un recibo**: una marca por línea (copia verificada en
   verde, avisos en naranja) en vez de un párrafo corrido.
6. **Las puertas** conservan sus `objectName` y ganan chips con los colores
   por tipo.
7. **El CTA** lleva subtítulo, y «Explorar primero» da salida a quien no
   quiere crear un proyecto todavía (bloqueado mientras una actualización
   esté sin confirmar).
8. **El movimiento es una preferencia** (`ui_animations`, Ajustes ▸
   Interfaz, activada por defecto): un fundido de entrada y unas pocas
   estrellas que parpadean, y ambos se detienen cuando la vista no se ve.

**Consecuencias.** Una primera ejecución aterriza en el paso del
observatorio, no en el informe de una base de datos que aún no existe. La
página cabe en el área de contenido de una ventana de 1280x860 sin
comprimir nada (el defecto que aplastaba el formulario hasta solapar sus
filas); un único scroll exterior cubre las pantallas cortas y las dos
listas que pueden crecer conservan su propia caja con tope. Los textos
nuevos entran por las traducciones ES/EN (0 sin terminar).

**Alternativas descartadas.** Dejar la banda plana (el primer fotograma de
una herramienta del cielo tiene que ser el cielo). Pintarlo todo por código
en vez de enviar un SVG (nuestro vector propio se mantiene mejor y no
engorda el instalador). Meter una foto (peso, licencia, y contradiría la
Luna que calculamos).

**Revisión (2026-10-02, Interfaz 1.5 bis: el sitio, en el mapa).** El paso
del observatorio pedía una latitud a quien sabe dónde vive pero no sus
coordenadas, y en una actualización la pantalla seguía diciendo «configura
tu observatorio en tres pasos» a alguien que llevaba meses usándola.

1. **Mapa para elegir el sitio** (`gui/widgets/site_map.py`): mapamundi
   equirectangular con **clic para fijar el punto**, rueda para acercar,
   arrastre para moverse y doble clic para recentrar. La base (costas,
   fronteras y rejilla, de `assets/world_map.json`, Natural Earth 110m en
   dominio público) se rasteriza una vez por vista; encima van el
   **terminador día/noche calculado en local** (`ephem_minor` + GMST: la
   mitad sombreada es la que está de noche ahora mismo), el marcador y la
   **lectura de coordenadas bajo el cursor**.
2. **Proyección cover**: el mapa llena su hueco en vez de encogerse dentro
   de él. Con *contain* el mundo 2:1 dentro de una caja 3:1 dejaba dos
   bandas negras a los lados; alejando por debajo del nivel cover vuelven,
   y con ellas los polos, que es lo que se gana a cambio.
3. **El punto clicado tiene nombre**: `core/places.py` busca la ciudad más
   cercana en `assets/world_places.json` (1251 ciudades de Natural Earth
   50m, dominio público, 49 KB) y, si no hay ninguna a menos de 250 km,
   escribe las coordenadas. Offline: una geocodificación inversa costaría
   una petición de red por un gesto que se repite mientras se apunta.
4. **Un diálogo, no un panel empotrado**, para Ajustes ▸ Sitio: la página
   ya está cargada de grupos, así que el mapa se abre desde un botón
   («Elegir en el mapa…»). Comparte el mismo widget, así que no pueden
   divergir.
5. **El nombre se escribe siempre**, al resolver un MPC, al detectar la
   ubicación y al clicar el mapa: las tres son acciones explícitas sobre
   dónde está el sitio.
6. **La insignia de versión se muda al informe**: en el héroe competía con
   el wordmark y el dato pertenece al panel que pide el clic. En modo
   actualización el héroe explica qué pasó («NightScribe se ha actualizado
   a {versión}…»), el rail marca los pasos 1 y 2 como ya hechos y la
   **única acción vive con el informe**, pintada como primaria.

**Alternativas descartadas aquí.** Teselas de OpenStreetMap (red, política
de uso y atribución para un mapa que solo elige un punto). Estirar la
longitud para llenar el ancho (deforma el mapamundi y engaña al situarse).
Geocodificación inversa en línea (una petición por clic; el nombre es texto
libre de todos modos). Un panel empotrado en Ajustes (la página ya no da
más de sí).

**Revisión (2026-10-02, Interfaz 1.6: la lista y el proyecto, juntos otra
vez).** La Interfaz 1.0 separó la lista de proyectos y el detalle en dos
páginas de la pila. El resultado era peor de lo previsto: abrir un proyecto
se llevaba por delante la lista (y con ella el contexto de dónde estabas),
cambiar de proyecto costaba una ida y vuelta, y la pantalla de la lista,
con filas de 74 px casi vacías, no decía nada.

1. **Una sola página** (`VIEW_PROJECTS`): lista a la izquierda y proyecto a
   la derecha, con un **`QSplitter`** en medio. `VIEW_HOME` y `VIEW_DETAIL`
   pasan a ser **dos nombres del mismo índice**: el historial sigue
   distinguiendo los dos estados por el `pid` que ya llevaba, las migas se
   reconstruyen a partir de él y ninguna de las decenas de enlaces internos
   tuvo que cambiar.
2. **El ancho de la lista es del observador**: arrastrable, con mínimos y
   máximos (260–560), recordado en `config["projects_list_width"]`, doble
   clic en el separador para volver al valor por defecto y el botón `«` para
   plegarla. Ojo con `QSplitter::setSizes`: reparte **proporcionalmente**
   cuando la suma no cuadra con el ancho real, que es como una petición de
   400 px se quedaba en 250; por eso el ancho se aplica leyendo el ancho
   real del separador.
3. **Filas de 54 px** (eran 74) con el icono del tipo a 34, el color del
   tipo como **borde izquierdo de todas las filas** y la **selección teñida
   con el color del objeto** en vez del azul global. La segunda línea gana
   los números del objeto (`core/kinds.context_line`), y la fila **oculta
   lo menos importante según su ancho**: a 350 px pierde los números, a 460
   recupera la campaña y la miniatura de la curva.
4. **El cielo sube a la barra de navegación** (`gui/widgets/sky_bar.py`):
   la Luna dibujada con su fase real, la ventana de oscuridad, los planetas
   al anochecer y los chips de eventos, **visibles desde todas las vistas**.
   La banda «Qué pasa en el cielo» de Home desaparece y sus ~60 px vuelven
   a la lista; la tira de campañas se convierte en un botón del encabezado
   (~45 px más).
5. **El panel derecho en reposo es la noche**: cuando no hay proyecto
   elegido, el detalle muestra el mismo cielo pintado de Bienvenida, la
   ventana de oscuridad, los planetas y el camino hacia un proyecto nuevo
   (`gui/widgets/night_panel.py`).
6. **Una sola fuente para la noche** (`core/night_brief.py`): los números Y
   las frases de la Luna, la oscuridad y los planetas se calculan y se
   redactan en un solo sitio, que es lo que consumen Bienvenida, la barra
   del cielo y el panel en reposo.

**Alternativas descartadas aquí.** Mantener las dos páginas y limitarse a
densificar las filas (el problema de fondo era no ver la lista y el
proyecto a la vez). Ancho de lista fijo (el observador sabe mejor que
nosotros cuánto quiere ver de cada cosa). Pintar la noche en una franja
dentro de la vista (se come justo el alto que veníamos a recuperar).

**Revisión (2026-10-02, Interfaces 1.7 y 1.8: la ficha del proyecto y la
noche dibujada).** La Interfaz 1.7 apretó el cromo del proyecto (de cinco
filas a tres: la barra de navegación con el cielo, los pasos Ficha →
Captura → Análisis → Publicar y una sola fila de acción) y puso los
parámetros y los gráficos uno al lado del otro. La Interfaz 1.8 llevó a las
tres pestañas del proyecto el truco que ya usaban Bienvenida y la tira de
la noche: **una banda que dibuja la noche del objeto** con sus números
reales (`gui/widgets/night_ribbon.py`), la tabla de parámetros convertida
en lista de definición, el plan dibujado sobre la noche con su veredicto en
Captura, las tomas de la visita dibujadas en Análisis y el estado de
CCDciel como color con significado. El detalle, los números medidos y el
criterio de aceptación (las cuatro pestañas caben a 1360x940 y 1360x860,
Captura incluida con CCDciel conectado) viven en el ADR-041.

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

**Revision (2026-10-01, Interfaz 1.4: the Welcome redesign).** Welcome was
correct but flat: a gradient banner with half a panel of dead space, a wall
of checkboxes with long paragraphs, and forms that asked for coordinates
without ever answering back. The first frame of a tool that reads the sky
did not look like the sky, and typing the first latitude earned nothing.

1. **The hero is a painted sky.** `assets/welcome_sky.svg` (our own art,
   GPL) is rasterised once per size and `gui/widgets/welcome_sky.py` paints
   **tonight's real Moon** on top, read from `ephem_minor.moon(jd)`: the
   phase you see is the one the almanac states. The widget enters through
   the usual pattern (placeholder `QWidget` + `drop_in`, ADR-005) and falls
   back to a hand-painted gradient when the asset or QtSvg is missing.
2. **"Your night, now".** A live strip, 100% local (`coords.tonight_window`
   + `ephem_minor.moon`/`planet`): the darkness window in local time, the
   Moon's phase and set, and the planets above the horizon at dusk. It
   recomputes on every site change; nothing goes to the network.
3. **The stepper is a rail.** The connector fills as you advance and the
   steps behind you carry a tick; the `.ui`'s own text is kept underneath.
4. **Targets are cards.** A grid of cards in each kind's `KIND_COLORS` hue,
   clickable as a whole, with a one-glance summary and the full paragraph
   plus the data source in the tooltip. `_setup_kinds(..., card=True)`
   still returns the same `{kind_id: QCheckBox}`, so `_apply_kinds` and the
   gate are untouched.
5. **Data is a receipt**: one mark per line (verified backup in green,
   warnings in orange) instead of a run-on paragraph.
6. **The doors** keep their `objectName` and gain chips in the per-kind
   colours.
7. **The CTA** carries a subtitle, and "Explore first" gives an out to
   whoever does not want to create a project yet (blocked while an update
   is unacknowledged).
8. **Motion is a preference** (`ui_animations`, Settings ▸ Interface, on by
   default): a one-shot fade and a few twinkling stars, both stopped when
   the view is off screen.

**Consequences.** A first run lands on the observatory step, not on a
report about a database that does not exist yet. The page fits the content
area of a 1280x860 window without squeezing anything (the defect that
compressed the form until its rows overlapped); a single outer scroll
covers short screens and the two lists that can grow keep their own capped
scroll box. New strings go through the ES/EN translations (0 unfinished).

**Rejected alternatives.** Keeping the flat banner (the first frame of a
sky tool has to be the sky). Painting everything in code instead of
shipping an SVG (our own vector is easier to maintain and does not bloat
the installer). Embedding a photo (weight, licence, and it would contradict
the Moon we compute).

**Revision (2026-10-02, Interfaz 1.5 bis: the site, on a map).** The
observatory step asked for a latitude from someone who knows where they
live but not their coordinates, and on an update the screen still said
"set up your observatory in three steps" to an observer who had been using
the app for months.

1. **A map to choose the site** (`gui/widgets/site_map.py`): an
   equirectangular world map with **click to set the point**, wheel to
   zoom, drag to move and double click to recentre. The base (coastlines,
   borders and graticule, from `assets/world_map.json`, Natural Earth 110m,
   public domain) is rasterised once per view; on top go the **day/night
   terminator computed locally** (`ephem_minor` + GMST: the shaded half is
   the half that is dark right now), the marker and the **coordinates read
   out under the cursor**.
2. **Cover projection**: the map fills its box instead of shrinking inside
   it. With contain, a 2:1 world inside a 3:1 box left two black bands at
   the sides; zooming out below the cover level brings them back, and with
   them the poles, which is what the trade buys.
3. **A clicked point gets a name**: `core/places.py` looks up the nearest
   city in `assets/world_places.json` (1251 places from Natural Earth 50m,
   public domain, 49 KB) and, when none is within 250 km, writes the
   coordinates. Offline: reverse geocoding would cost a network round trip
   on a gesture that gets repeated while aiming.
4. **A dialog, not an embedded panel**, for Settings ▸ Site: the page is
   already crowded, so the map opens from a button ("Pick on the map…").
   Same widget underneath, so the two cannot drift.
5. **The name is written every time**, when resolving an MPC code, when
   detecting the location and when clicking the map: all three are explicit
   statements of where the site is.
6. **The version badge moves to the report**: in the hero it fought the
   wordmark, and the fact it announces belongs to the panel that asks for
   the click. In update mode the hero explains what happened, the rail
   marks steps 1 and 2 as already done and the **only action lives with the
   report**, painted as the primary one.

**Rejected alternatives here.** OpenStreetMap tiles (network, usage policy
and attribution for a map that only picks a point). Stretching longitude to
fill the width (it distorts the world map and misleads when placing
yourself). Online reverse geocoding (a request per click; the name is free
text anyway). An embedded panel in Settings (the page has no room left).

**Revision (2026-10-02, Interfaz 1.6: the list and the project, together
again).** Interfaz 1.0 split the project list and the detail into two shell
pages. The result was worse than expected: opening a project threw the list
away (and with it the context of where you were), switching projects cost a
round trip, and the list screen, with 74 px rows that were nearly empty,
said very little.

1. **One page** (`VIEW_PROJECTS`): list on the left, project on the right,
   with a **`QSplitter`** between them. `VIEW_HOME` and `VIEW_DETAIL` become
   **two names for the same index**: the history still tells the two states
   apart by the `pid` it already carried, the breadcrumbs are rebuilt from
   it, and none of the dozens of internal deep links had to change.
2. **The list's width belongs to the observer**: draggable, with limits
   (260–560), remembered in `config["projects_list_width"]`, double click on
   the handle to reset, and the `«` button to fold it. Watch out for
   `QSplitter::setSizes`: it distributes **proportionally** when the sum
   does not match the real width, which is how a request for 400 px became
   250; that is why the width is applied by reading the splitter's real
   width.
3. **54 px rows** (were 74) with the kind icon at 34, the kind hue as the
   **left edge of every row** and the **selection tinted with the object's
   colour** instead of the global blue. The second line gains the object's
   numbers (`core/kinds.context_line`), and the row **hides the least
   important parts as it narrows**: below 350 px it drops the numbers, at
   460 it gets the campaign and the curve thumbnail back.
4. **The sky moves up to the navigation row** (`gui/widgets/sky_bar.py`):
   the Moon drawn at its real phase, the darkness window, the planets at
   dusk and the event chips, **visible from every view**. Home's "What's up
   in the sky" band goes away and its ~60 px return to the list; the
   campaigns strip becomes a header button (~45 px more).
5. **The resting right pane is the night**: with no project selected, the
   detail shows the same painted sky as Welcome, the darkness window, the
   planets and the way in to a new project
   (`gui/widgets/night_panel.py`).
6. **One source for the night** (`core/night_brief.py`): the numbers AND the
   wording of the Moon, the darkness and the planets are computed and
   phrased in one place, which is what Welcome, the sky bar and the resting
   panel all read.

**Rejected alternatives here.** Keeping the two pages and just densifying
the rows (the real problem was not seeing the list and the project at
once). A fixed list width (the observer knows better than we do how much of
each they want to see). Painting the night in a band inside the view (it
eats exactly the height we came to recover).

**Revision (2026-10-02, Interfaces 1.7 and 1.8: the project card and the
night, drawn).** Interfaz 1.7 tightened the project chrome (five rows down
to three: the navigation row with the sky, the Ficha → Captura → Análisis →
Publicar steps and a single action row) and put the parameters and the
charts side by side. Interfaz 1.8 took the trick Welcome and the night
strip already used into the three project tabs: **a band that draws the
object's night** with its real numbers (`gui/widgets/night_ribbon.py`), the
parameters table turned into a definition list, the plan drawn on the night
with its verdict in Capture, the visit's frames drawn in Analysis, and the
CCDciel state as colour with meaning. The detail, the measured numbers and
the acceptance criterion (all four tabs fit at 1360x940 and 1360x860,
Capture included with CCDciel connected) live in ADR-041.
