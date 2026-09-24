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
migración v10)

**Ver / See**: ADR-019 (la UX v3 centrada en proyectos; revisado aquí) ·
ADR-041 (la barra de pestañas del proyecto; enmendado aquí) · ADR-043 (la
pestaña Observatory plegada en Captura; enmendado aquí) · ADR-044 (el UFE;
sus escrituras se registran siempre ahora) · ADR-036 (el diario: vista
derivada global; el gestor de visitas es su contraparte por proyecto).

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

**Consequences.** Migrations v8 and v9 with translatable notes; the
migration tests seed old databases and verify both. The manager has its
own battery (`tests/unit/test_visits_panel.py`). The duplicated hint
label bug in the products block was fixed on the way. The workflow and
UI guides document the change; AGENTS.md follows the map.
