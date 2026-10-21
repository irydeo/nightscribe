# ADR-045: El flujo del proyecto se reconstruye sobre visitas / the project flow rebuilds around visits

**Estado / Status**: Accepted · **Fecha / Date**: 2026-09-24 ·
**ejecutado / executed**: 2026-09-24 (suite unitaria green, i18n 0
unfinished) · **Enmendado / Amended**: 2026-09-24 (la vista de la visita
se mueve a su propia ventana no modal — VisitsPanel queda como resumen
ligero en la pestaña — y la astrometría MPC vive dentro de esa ventana:
forma A, sin visita no hay ni área de pegado; el reporte se registra en
la visita anfitriona y avisa si la fecha de la primera medida no cuadra
con la de la visita; y una visita puede fijarse 📌 arriba de la lista o
editar su fecha — su nombre — desde la cabecera de su ventana,
migración v10) · **Enmendado / Amended**: 2026-09-26 (ADR-047: clic
bidireccional; la fila de un punto con placa es clicable y reaparece
esa placa en el UFE con su estado guardado; sin placa, aviso llano)

**Enmendado / Amended**: 2026-10-02 (Interfaz 1.6: el UFE pasó de
diálogo flotante a página de la ventana principal, así que la ventana de
visita se aparta mientras el taller está en pantalla y vuelve al salir;
el taller trae su propio navegador de tomas, así que no se pierde nada)

**Enmendado / Amended**: 2026-10-08 (la ventana de visita se simplifica:
una sola acción de análisis elegida por el tipo del objeto, «Periodo y fase»
se muda al bloque de la curva del proyecto y las acciones de recurso pasan a
una puerta «Recursos ▾»)

**Ver / See**: ADR-019 (la UX v3 centrada en proyectos; revisado aquí) ·
ADR-041 (la barra de pestañas del proyecto; enmendado aquí) · ADR-043 (la
pestaña Observatory plegada en Captura; enmendado aquí) · ADR-044 (el UFE;
sus escrituras se registran siempre ahora) · ADR-036 (el diario: vista
derivada global; el gestor de visitas es su contraparte por proyecto)
· ADR-047 (el estado de la placa y el clic bidireccional; enmienda la
forma A de este ADR).

## Español

**Contexto.** El flujo de proyecto arrastraba tres fricciones reales,
todas confirmadas en campo:

1. **Separar «Procesado» de «Seguimiento» era antinatural**: el
   observador no procesa y luego sigue; observa, mide y aprende en el
   mismo acto, noche a noche.
2. **La gestión de visitas era caótica**: dos botones «Añadir visita»
   (uno en la pestaña, otro en el diálogo), un diálogo modal
   master-detail desconectado del flujo, y ninguna forma de quitar una
   imagen o un punto.
3. **Los recursos no sabían a qué visita pertenecían**: las imágenes de
   una visita se registraban dos veces (`session_images` +
   `project_files`), y el resto de ficheros (`project_files`) no
   conocía su visita en absoluto. Además el UFE dejaba ficheros sin
   registrar (el CSV/EFF de Medir, el PNG de escena de la barra
   superior).

**Decisión** (pactada con el observador, 2026-09-24):

1. **El flujo es Ficha → Captura → Análisis → Publicación.** La Ficha y
   la Captura no cambian; Publicar queda para otra revisión. La máquina
   de pasos pasa a `plan → analysis → publish` (la clave `plan` ya se
   muestra como «Captura» desde ADR-043 y sigue así). La migración v8
   renombra el paso `process` → `analysis`; la pestaña Seguimiento,
   limitada por tipo, desaparece, y las claves retiradas `process` /
   `followup` son alias permanentes de `analysis` para que todo deep
   link viejo (dashboard, diario, menú contextual, doble clic) siga
   aterrizando. La tarjeta «Siguiente» distingue la llamada de cadencia
   del trabajo de paso por la **carga** de la acción
   (`overdue_days`/`never_visited`), nunca por el nombre de la clave
   (ahora compartida).
2. **La pestaña Análisis se construye alrededor del gestor de visitas
   (`gui/widgets/visits_panel.py`), para TODOS los tipos**: cada día
   que se trabaja el objeto es una visita, y de ella cuelgan sus
   recursos. Un único punto de entrada primario («Nueva visita»), nada
   de botones duplicados, nada modal: la lista de visitas con filas
   ricas (fecha, nº de imágenes y de puntos, notas) y el detalle en la
   misma página. Por visita: recursos (adjuntar con auto-tipo, abrir en
   el editor FITS si es placa y con el sistema si no, quitar — el disco
   jamás se toca), medidas rápidas (los tipos con curva: SN, HADS,
   variables) y notas con autoguardado. La regla es estructural: **no
   existe ningún botón de adjuntar fuera de una visita seleccionada**.
   Los bloques del Procesado retirado se absorben: el reporte MPC
   (NEO/PCCP) aterriza en la visita seleccionada; el handoff EXOTIC
   (tránsitos) y los punteros FotoDif/WebObs (HADS) quedan; el bloque
   SN de importar FITS + blink desaparece (la placa de la visita abre
   en el editor, que ya lo cubre todo).

   *Revisión de usabilidad (mismo día)*: el detalle de la visita
   resultó demasiado cargado inline en la pestaña, así que vive en su
   **propia ventana no modal** (`VisitWindow`): la pestaña conserva la
   lista-resumen ligera y el botón primario («Nueva visita» crea y abre
   la ventana al momento; doble clic o «Abrir visita…» la reabren). Y
   para la astrometría pegada a mano, forma A: **el bloque MPC vive
   dentro de la ventana de la visita** (NEO/PCCP) — sin visita no hay
   ni área de pegado, y el reporte se registra en la visita anfitriona;
   si la fecha de la primera medida del reporte no cuadra con la de la
   visita (`mpc_report.first_obs_date`), la ventana avisa sin bloquear
   (un reporte colgado en la noche equivocada es un pecado silencioso).
   Enmienda (2026-09-26, ADR-047): el clic pasa a ser bidireccional: la
   fila de un punto que tiene placa (`file_id`) es clicable y reaparece
   esa placa en el UFE con su estado guardado (la pestaña Medir, a
   punto); sin placa (o placa no usable), aviso llano y no se abre
   nada. «Sin visita no hay medición» se mantiene.
3. **Un solo registro de ficheros** (migración v9): `project_files`
   gana `session_id` (SET NULL: borrar la visita desvincula, no borra)
   y `meta` (JSON: filtro/date_obs/exptime_s para placas). Las filas de
   `session_images` migran ahí y la tabla muere: se acabó el doble
   registro. `followup.py` lee/escribe imágenes de visita sobre el
   registro único, con el mismo contrato de antes.
4. **El UFE registra todo lo que escribe**: los huecos (CSV/EFF de
   Medir, el PNG de escena) llaman ahora a `notify_saved`; y si el
   editor se abrió desde una visita, los ficheros y los puntos caen en
   ella (`session_id` viaja por ambos hooks).
5. **Qué se conserva intacto**: la Ficha, la Captura, el diario global
   (ADR-036: vista derivada de solo lectura; el gestor es su contraparte
   por proyecto, no un duplicado), el quick-look retirado sigue
   retirado, y ninguna capacidad se pierde (ADR-038): se reubica.

**Consecuencias.** Migraciones v8 y v9 con notas traducibles; los tests
de migración siembran bases viejas y verifican ambas. El gestor tiene
su propia batería (`tests/unit/test_visits_panel.py`). El bug del hint
duplicado en el bloque de productos quedó corregido de paso. Documentan
el cambio las guías de flujos y la de interfaz; AGENTS.md sigue el
mapa.

**Corrección (2026-10-02).** La ventana de visita es un `QDialog` no
modal **con padre**, así que el gestor de ventanas la mantiene por encima
de la ventana principal. Mientras el UFE era un diálogo flotante no había
problema; desde que es una **página** de la ventana principal (Interfaz
1.0), abrir una placa desde la visita dejaba el editor **detrás** de la
ventana de visita. Afectaba a los tres caminos: la fila FITS
(`open_in_editor`), medir la serie y abrir la medida de un punto.

La ventana de visita **se aparta mientras el taller está en pantalla y
vuelve al salir**, con su estado intacto. Se oculta en vez de bajarse
(`lower()` sobre una ventana *transient* no es fiable) y en vez de
cerrarse, porque no se pierde nada: el propio taller trae el navegador de
tomas de la visita en su panel izquierdo (`ufe_visit_panel.ui`), que es
justo para lo que se usaría la ventana mientras se mide, y las notas de la
visita se guardan a cada tecla (`update_session_notes`).

**Enmendado (2026-10-08, la ventana de visita se simplifica).** La fila de
recursos de la ventana de visita tenía seis botones y tres de ellos abrían el
mismo editor en pestañas distintas («Medir la secuencia…», «Astrometría…»,
«Periodo y fase…»), así que el observador tenía que saber cuál le tocaba. La
revisión deja **una sola acción de análisis**, elegida por el tipo del objeto
(`core/kinds.py::analysis_of`): los que se mueven (NEO, PCCP, cometa, alerta)
van al track & stack («Medir la posición…») y los que varían (SN, HADS,
variable, tránsito) a la serie («Medir la serie…»); el blink de la SN vive en
el editor y no necesita botón. «Periodo y fase…» se muda al bloque de la curva
del proyecto, que es donde está la curva (y solo aparece con «Todas las
noches» y puntos suficientes). Las acciones de recurso («Adjuntar ficheros…»,
«Abrir», «Quitar de la visita») pasan a una puerta **«Recursos ▾»**, con sus
textos y tooltips en el Designer (ADR-005) y el mecanismo de puertas del UFE
(`build_door`). La cabecera (fecha, pin, borrar, guardar y cerrar) no cambia.

**Enmendado (2026-10-21, apartarse antes, y la serie guardada no cierra el
taller).** Dos cosas medidas sobre una visita real. La ventana de visita se
apartaba **al entrar** en el taller, es decir después de construirlo: esa
construcción tarda unos segundos en su primer uso y, con la ventana todavía
encima, la pausa se leía como un botón muerto, así que el observador volvía a
pulsar «Medir la serie…» y el mérito se lo llevaba el segundo clic. Ahora se
aparta **antes** del trabajo. Y guardar una serie refrescaba el proyecto
**reabriéndolo**, que cambia la pantalla al proyecto: el editor se cerraba solo y
la página reconstruida se llevaba por delante la ventana de visita. El refresco
es **en el sitio** (la lista de visitas con sus cuentas, la curva, la línea de
cadencia, las pasadas y la cabecera), y la ventana vuelve **rellena** al salir.

## English

**Context.** The project flow carried three real frictions, all
confirmed in the field:

1. Splitting "Process" from "Follow-up" was unnatural: the observer
   does not process and then follow up; they observe, measure and learn
   in one act, night after night.
2. Visit management was chaotic: two "Add visit" buttons (one in the
   tab, one in the dialog), a modal master-detail dialog detached from
   the flow, and no way to remove an image or a point.
3. Resources did not know their visit: a visit's images were registered
   twice (`session_images` + `project_files`), and every other file
   (`project_files`) had no visit link at all. The UFE also left files
   unregistered (the Measure CSV/EFF, the top-bar scene PNG).

**Decision** (agreed with the observer, 2026-09-24):

1. **The flow is Ficha → Captura → Análisis → Publicación** (Object
   card → Capture → Analysis → Publish). The card and the capture steps
   are untouched; Publish waits for another review. The step machine
   becomes `plan → analysis → publish` (the `plan` key already read
   "Captura"/"Capture" since ADR-043 and stays). Migration v8 renames
   the `process` step to `analysis`; the kind-gated Follow-up tab is
   gone, and the retired `process`/`followup` keys alias to `analysis`
   forever so every old deep link (dashboard, journal, context menu,
   double-click) keeps landing. The Next card tells a cadence call from
   step work by the action's **payload** (`overdue_days`/
   `never_visited`), never by the (now shared) key name.
2. **The Analysis tab is built around the visits manager
   (`gui/widgets/visits_panel.py`), for EVERY kind**: every day you
   work the object is a visit, and its resources hang from it. One
   primary entry point ("New visit"), no duplicated buttons, nothing
   modal: the rich-row visits list and the detail live on the same
   page. Per visit: resources (attach with auto-kind, open FITS in the
   editor / the rest with the system, remove — the disk is never
   touched), quick measurements (the light-curve kinds: SN, HADS,
   variables) and auto-saving notes. The rule is structural: **no
   attach button exists outside a selected visit**. The retired Process
   tab's blocks are absorbed: the MPC report (NEO/PCCP) lands on the
   selected visit; the EXOTIC handoff (transits) and the FotoDif/WebObs
   pointers (HADS) stay; the SN FITS-import + blink block is gone (the
   visit's plate opens in the editor, which already owns it all).
3. **One file registry** (migration v9): `project_files` gains
   `session_id` (SET NULL: deleting the visit unlinks, never deletes)
   and `meta` (JSON: filter/date_obs/exptime_s for plates). The
   `session_images` rows migrate in and the table dies: the double
   registration ends. `followup.py` reads/writes visit images over the
   single registry with the same contract as before.
4. **The UFE registers everything it writes**: the gaps (the Measure
   CSV/EFF, the scene PNG) now call `notify_saved`; and when the editor
   was opened from a visit, files and points land on it (`session_id`
   rides both hooks).
5. **What stays untouched**: the object card, the capture step, the
   global journal (ADR-036: a derived read-only view; the manager is
   its per-project counterpart, not a duplicate), the retired
   quick-look stays retired, and no capability is lost (ADR-038): it is
   relocated.

   *Usability review (same day)*: the visit's detail proved too crowded
   inline in the tab, so it lives in its **own non-modal window**
   (`VisitWindow`): the tab keeps the light summary list and the primary
   button ("New visit" creates and opens the window at once; a
   double-click or "Open visit…" reopens it). And for hand-pasted
   astrometry, form A: **the MPC block lives inside the visit's window**
   (NEO/PCCP) — without a visit there is no paste area at all, and the
   report registers to the hosting visit; when the report's first
   measurement's date disagrees with the visit's
   (`mpc_report.first_obs_date`), the window warns without blocking (a
   report hung on the wrong night is a silent database sin). A visit can
   also be **pinned** (📌, it floats to the top of the list — migration
   v10) and its **date edited** in the window's header (the date is the
   visit's name; points already saved keep their own MJD).
   Amendment (2026-09-26, ADR-047): the click is now bidirectional: the
   row of a point that has a plate (`file_id`) is clickable and brings
   that plate back in the UFE with its saved state (the Measure tab,
   ready); without a plate (or an unusable one), a plain notice and
   nothing opens. "No visit, no measurement" is upheld.

**Consequences.** Migrations v8 and v9 with translatable notes; the
migration tests seed old databases and verify both. The manager has its
own battery (`tests/unit/test_visits_panel.py`). The duplicated hint
label bug in the products block was fixed on the way. The workflow and
UI guides document the change; AGENTS.md follows the map.

**Amended (2026-10-08, the visit window is simplified).** The visit window's
resource row carried six buttons and three of them opened the same editor in
different tabs ("Measure the sequence…", "Astrometry…", "Period and phase…"), so
the observer had to know which one applied. The revision leaves **a single
analysis action**, chosen by the object's kind (`core/kinds.py::analysis_of`):
the objects that move (NEO, PCCP, comet, alert) go to the track & stack
("Measure the position…") and the ones that vary (SN, HADS, variable, transit)
to the series ("Measure the series…"); the SN blink lives in the editor and
needs no button. "Period and phase…" moves to the project's curve block, which
is where the curve is (and only shows with "All the nights" and enough points).
The resource actions ("Attach files…", "Open", "Remove from visit") move into a
**"Resources ▾"** door, with their texts and tooltips in Designer (ADR-005) and
the UFE's door mechanism (`build_door`). The head (date, pin, delete, save and
close) does not change.

**Fix (2026-10-02).** The visit window is a non-modal `QDialog` **with a
parent**, so the window manager keeps it above the main window. While the
UFE was a floating dialog that was fine; since it became a **page** of the
main window (Interfaz 1.0), opening a plate from a visit left the editor
**behind** the visit window. It affected all three paths: the FITS row
(`open_in_editor`), measuring the series and opening a point's measurement.

The visit window **steps aside while the workbench is on screen and comes
back when it leaves**, with its state intact. It hides rather than lowers
(`lower()` on a transient window is not reliable) and rather than closes,
because nothing is lost: the workbench carries the visit's frame navigator
in its left pane (`ufe_visit_panel.ui`), which is exactly what the window
would be used for while measuring, and the visit's notes are saved on every
keystroke (`update_session_notes`).

**Amendment (2026-10-16, the visit gains a name and the normal path stands out).**
Two changes to the visit window, both from the same review. The visit now carries a
**name of its own** (`project_sessions.label`, migration v24), edited next to the date
and saved by the same gesture: the date stays the folder and the sort key, and the name
is what the observer calls the night (a project worked twice in one day, a session that
ran past midnight). The list shows `name · date` when there is one. The window also
stopped hiding its two entry points: the kind's analysis action ("Measure the
position…" / "Measure the series…") is painted as the panel's **hero button** in the
object's own hue (ADR-038's grammar, the same `theme.hero_button_style` the Ficha uses)
and sits on its own row together with a visible **"Attach files…"**; the "Resources ▾"
door is gone, because with Attach out of it only "Open" and "Remove from visit" were
left, and two buttons do not need a menu. Finally, a visit that already holds an
astrometry run opens with its **MPC report already in the box**, rebuilt from the run's
own points by the same generator the editor uses (the host rebuilds it:
`_visit_mpc_prefill`), so the observer is not asked to paste what the app has just
measured; saving the report is still a deliberate gesture.

**Amendment (2026-10-16, the visit reuses the report window).** The visit's MPC block
stops being a paste box with its own validator: it is now a **button** ("MPC report…")
that opens the SAME window the editor's Astrometry tab opens, plus one **status line**.
The report is rebuilt from the visit's own astrometry run (`_visit_mpc_report`) by the
same generator and the same shared controller (ADR-080), so there are no longer two
behaviours that can drift apart; on save, the file is registered to the visit. "Form A"
holds where it matters: without a visit there is no block, and the report still hangs
from the visit.

**Enmienda (2026-10-16, la visita gana nombre y el camino normal se destaca).** Dos
cambios en la ventana de visita, ambos de la misma revisión. La visita pasa a tener
**nombre propio** (`project_sessions.label`, migración v24), editable junto a la fecha
y guardado con el mismo gesto: la fecha sigue siendo la carpeta y el criterio de orden,
y el nombre es como el observador llama a la noche (un proyecto trabajado dos veces en
un día, una sesión que pasó de medianoche). La lista muestra `nombre · fecha` cuando lo
hay. La ventana además deja de esconder sus dos entradas: la acción de análisis del tipo
(«Medir la posición…» / «Medir la serie…») se pinta como el **botón héroe** del panel
con el color del propio objeto (la gramática del ADR-038, el mismo
`theme.hero_button_style` de la ficha) y vive en su propia fila junto a un **«Añadir
ficheros…»** visible; el cajón «Recursos ▾» desaparece, porque sin Añadir solo quedaban
«Abrir» y «Quitar de la visita», y dos botones no necesitan un menú. Por último, una
visita que ya tiene un run de astrometría se abre con su **reporte MPC ya en la caja**,
reconstruido desde los propios puntos del run con el mismo generador que usa el editor
(lo reconstruye el anfitrión: `_visit_mpc_prefill`), así que al observador no se le pide
pegar lo que la app acaba de medir; guardar el reporte sigue siendo un gesto deliberado.

**Enmienda (2026-10-16, la visita reutiliza la ventana de reporte).** El bloque MPC de
la visita deja de ser una caja de pegado con su propio validador: ahora es un **botón**
(«Reporte MPC…») que abre la MISMA ventana que la pestaña Astrometría del editor, más
una **línea de estado**. El reporte se reconstruye desde el propio run de astrometría
de la visita (`_visit_mpc_report`) con el mismo generador y el mismo controlador
compartido (ADR-080), así que ya no hay dos comportamientos que puedan divergir; al
guardar, el fichero se registra en la visita. La «forma A» se mantiene en lo que
importa: sin visita no hay bloque, y el reporte sigue colgando de la visita.

**Enmienda (2026-10-16, la ventana de visita es una página).** La ventana había
acumulado quince widgets en seis filas y mezclaba edición, acción y gestión de
contenido al mismo nivel. Ahora responde, en orden de lectura, a tres preguntas:
qué noche es, qué toca hacer con ella y qué contiene. La **cabecera** lee la fecha
(es la carpeta y el orden: se cambia desde el menú **⋯** con un calendario, nunca
escribiendo encima) y edita el **nombre** en línea, que se guarda al confirmar con
una línea «Guardado» en lugar del botón permanente. Debajo, **una** acción héroe
(elegida por el tipo) y «Añadir ficheros…». El contenido se parte en dos: los
**Resultados** (runs, reportes, cartas y medidas, en una lista ordenada por hora,
con doble clic para abrir y menú por fila para todo lo demás) y los **Ficheros de
la noche** (las placas y demás materia prima) en un bloque **plegado** con su
recuento. Las filas de botones «Open / Remove» y «Bring back… / Free space…»
desaparecen: sus acciones viven en el menú de la fila. La entrada rápida de
magnitud se pliega tras «Añadir una medida a mano» (las medidas ya son filas de
Resultados, estaban listadas dos veces). Borrar la visita vive en el menú ⋯.

**Amendment (2026-10-16, the visit window is one page).** The window had
accumulated fifteen widgets in six rows, mixing editing, action and content
management at the same level. It now answers, in reading order, three questions:
which night this is, what to do with it, and what it holds. The **head** reads the
date (it is the folder and the order: it is changed from the **⋯** menu with a
calendar, never by typing over it) and edits the **name** in place, saved on commit
with a "Saved" line instead of the permanent button. Below it, **one** hero action
(chosen by the kind) and "Attach files…". The content is split in two: **Results**
(runs, reports, charts and measurements, in one list ordered by time, double-click
to open and a per-row menu for everything else) and the **Files of the night** (the
plates and the rest of the raw material) in a **folded** block with its count. The
"Open / Remove" and "Bring back… / Free space…" button rows are gone: their actions
live in the row's menu. The quick magnitude entry is folded behind "Add a
measurement by hand" (measurements are rows in Results now, they were listed
twice). Deleting the visit lives in the ⋯ menu.

**Amendment (2026-10-21, step aside first, and a saved series does not close the
workbench).** Two things measured on a real visit. The visit window stepped
aside **on entering** the workbench, that is, after building it: that build
takes a few seconds on its first use and, with the window still on top, the
pause read as a dead button, so the observer pressed "Measure the series…" again
and the second press got the credit for opening it. It steps aside **before**
the work now. And saving a series refreshed the project by **re-opening** it,
which switches the screen to the project: the editor closed itself and the
rebuilt page took the visit window down with it. The refresh is **in place**
(the visits list with its counts, the curve, the cadence line, the passes and
the header), and the window comes back **filled** on the way out.
