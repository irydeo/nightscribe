# ADR-086: Reporte combinado (chequeo y reporte a nivel de proyecto)

**Estado / Status**: Accepted · **Fecha / Date**: 2026-10-13

**Ver / See**: ADR-062 (astrometría), ADR-077 (residuos), ADR-078 (exclusión), ADR-080 (reporte MPC), ADR-084 (start and follow), ADR-085 (centroide manual).

## Español

**Contexto**: con «Start and follow» un objeto produce **varias series**, cada
una apilada por separado y con su medición. El chequeo y el reporte MPC se
construyen **por run**, así que ver cómo se alinean TODAS las mediciones juntas
—para enviarlas en conjunto o descartar una— obligaba a abrir cada run y sumar a
mano. Las piezas ya existen: `mpc_astrometry.generate` acepta una **lista de
puntos**, `findorb.check` acepta un bloque de líneas, la exclusión por
observación está (ADR-078) y la identidad de «lo nuestro» en el listado se
resuelve por instante y estación (ADR-077).

**Decisión**: un **chequeo y reporte combinados a nivel de proyecto**, en la
pestaña Análisis.

1. **Se listan todas las mediciones.** `astrometry_store.project_observations`
   junta los *stack points* de los runs **completos** del proyecto, en orden de
   tiempo, con su fecha, magnitud, movimiento y chequeo. (El punto por frame no
   entra: es el doble chequeo, no la medición que se envía.)
2. **El observador marca.** Cada observación lleva su **checkbox** (ADR-078 por
   observación, reversible, nada se borra). Por defecto van **todas**: el reporte
   lleva todo salvo lo que se descarte.
3. **Un solo chequeo.** «Comprobar en conjunto» construye **nuestras líneas** con
   las marcadas (`mpc_astrometry.to_mpc80`) y corre `findorb.check` UNA vez: el
   veredicto (nuestro residuo frente a la dispersión de los demás) se pinta en
   palabras. Si los datos ya están publicados (`ours_published`), se dice y no se
   cuenta como «los demás».
4. **Un solo reporte.** «Reporte combinado…» genera **un** MPC reporte
   (`mpc_astrometry.generate`) con las marcadas y lo enseña para copiar/guardar;
   el flujo de envío es el del editor (ADR-080).
5. **Se guarda.** `astrometry_combined` (una fila por proyecto) guarda la
   **selección** y el **resumen del chequeo**, así que reabrir muestra el mismo
   conjunto y el mismo veredicto. En su propia tabla, no en el contexto del
   proyecto (que se lee en cada fila de la lista y no debe cargar con el listado
   de residuos).
6. **Designación única.** Si una serie es de antes de confirmarse y otra de
   después, el reporte usa la designación **actual** (contexto `confirmed`,
   ADR-077).

**Consecuencias**: tabla `astrometry_combined` y helpers `save_combined`/
`get_combined`/`project_observations`; una sección «Reporte combinado» en
Análisis (tabla + «Comprobar en conjunto» + «Reporte combinado…» + veredicto).
No toca la medida: es una vista sobre lo ya medido.

**Alternativas**: (a) un run por envío y sumar a mano, descartado: es justo lo
que se quiere evitar; (b) guardar el chequeo en el contexto del proyecto,
descartado: pesa en cada lectura de la lista; (c) re-apilar al combinar,
descartado: no hace falta, las mediciones ya están.

## English

**Context**: with "start and follow" an object produces **several series**, each
stacked separately and each with its measurement. The check and the MPC report
are built **per run**, so seeing how ALL the measurements line up together —to
send them together or drop one— meant opening each run and adding them up by
hand. The pieces already exist: `mpc_astrometry.generate` takes a **list of
points**, `findorb.check` takes a block of lines, the per-observation exclusion
is there (ADR-078) and "ours" is identified in the listing by instant and
station (ADR-077).

**Decision**: a **combined check and report at the project level**, in the
Analysis tab.

1. **Every measurement is listed.** `astrometry_store.project_observations`
   gathers the *stack points* of the project's **complete** runs, in time order,
   with their date, magnitude, motion and check. (The per-frame point is not
   included: it is the double check, not the measurement that is sent.)
2. **The observer ticks.** Each observation carries its **checkbox** (ADR-078
   per observation, reversible, nothing is deleted). By default they are **all**
   in: the report carries everything unless one is dropped.
3. **One check.** "Check together" builds **our lines** from the ticked ones
   (`mpc_astrometry.to_mpc80`) and runs `findorb.check` ONCE: the verdict (our
   residual against the others' scatter) is painted in plain words. If the data
   is already published (`ours_published`), it is said and not counted as "the
   others".
4. **One report.** "Combined report…" generates **one** MPC report
   (`mpc_astrometry.generate`) with the ticked ones and shows it to copy/save;
   the send flow is the editor's (ADR-080).
5. **It is saved.** `astrometry_combined` (one row per project) stores the
   **selection** and the **check summary**, so a reopen shows the same set and
   the same verdict. In its own table, not in the project context (which is read
   for every list row and should not carry the residual listing).
6. **One designation.** If one series is from before confirmation and another
   from after, the report uses the **current** designation (context `confirmed`,
   ADR-077).

**Consequences**: the `astrometry_combined` table and the `save_combined`/
`get_combined`/`project_observations` helpers; a "Combined report" section in
Analysis (table + "Check together" + "Combined report…" + verdict). It does not
touch the measurement: it is a view over what was already measured.

**Alternatives**: (a) one run per submission and adding by hand, rejected: that
is exactly what is to be avoided; (b) storing the check in the project context,
rejected: it weighs on every list read; (c) re-stacking when combining, rejected:
not needed, the measurements are already there.

**Review (2026-10-13, dedupe and the visit's runs)**: two fixes after a real case. (1) A project accumulates **re-measures** of the same observation (the same frames stacked again with another method or another observation count): four runs sat at mjd 61322.915954 with the same position, and feeding all of them to Find_Orb gave it several identical points at one instant, a degenerate set that produced **absurd residuals**. The combined view now **dedupes**: one point per `(mjd, group_index)`, the one from the **newest run**, and the section says how many were merged (`astrometry_store.dedupe_observations`). (2) The **visit window** now lists its OWN runs (`astrometry_store.runs_for_session`), oldest first, with their state; an undone run shows "—" for its observations (its positions are gone) and opening it is refused with a message instead of silently swapping to another run. Clicking a run opens it in the editor (the combined set is worked in the UFE, per the observer's request). Opening a run with no visit, or an undone one, is SAID and never swapped (that silent swap is what made "the run with two observations" look like it had lost one).

**Revisión (2026-10-13, dedup y los runs de la visita)**: dos arreglos tras un caso real. (1) Un proyecto acumula **re-medidas** de la misma observación (los mismos fotogramas apilados otra vez con otro método u otro número de observaciones): cuatro runs estaban en mjd 61322.915954 con la misma posición, y dárselos todos a Find_Orb le entregaba varios puntos idénticos en un instante, un conjunto degenerado que producía **residuos absurdos**. La vista combinada ahora **deduplica**: un punto por `(mjd, group_index)`, el del **run más nuevo**, y la sección dice cuántas se fusionaron (`astrometry_store.dedupe_observations`). (2) La **ventana de la visita** lista ahora SUS runs (`astrometry_store.runs_for_session`), del más antiguo al más nuevo, con su estado; un run deshecho muestra «—» en sus observaciones (sus posiciones ya no están) y abrirlo se rechaza con un mensaje en vez de cambiar en silencio a otro run. Al hacer clic en un run se abre en el editor (el conjunto combinado se trabaja en el UFE, como pidió el observador). Abrir un run sin visita, o uno deshecho, se DICE y nunca se cambia por otro (ese cambio silencioso es lo que hizo parecer que «el run con dos observaciones» había perdido una).

**Review (2026-10-13, the verdict is per observation, the set opens in the editor)**: four fixes after testing with a real project. (1) `findorb._match_ours` flagged only ONE of our records (the first match) and `_decide_from_residuals` used `ours[0]`, so a combined check reported the residual of an arbitrary observation: with a spurious point (SNR 1.6) and a good one, it blocked at 255" and looked absurd. Now ALL of ours are flagged and the verdict uses the **worst** (largest distance from the others' cloud), and the combined section lists **each of our observations with its own residual**, so the observer sees which one to drop. (2) The Analysis runs table filters to the **visit clicked** (`_analysis_visit_filter`): one click on a visit shows only its runs. (3) The combined set opens **in the editor** (`tab_trackstack.show_combined`): the host gathers each ticked observation's own stack (by `NS_RUN` + `_obs<N>`) and the tab paints them as ONE run-like result (strip, points, check), instead of opening a single run. (4) The image's context menu mapped the position from the view, not the viewport, so the menu landed off-screen (reported "the image menu did not appear"): it now maps from the viewport.

**Revisión (2026-10-13, el veredicto es por observación, el conjunto se abre en el editor)**: cuatro arreglos tras probar con un proyecto real. (1) `findorb._match_ours` marcaba solo UNO de nuestros registros (el primer match) y `_decide_from_residuals` usaba `ours[0]`, así que un chequeo combinado reportaba el residuo de una observación arbitraria: con un punto espurio (SNR 1.6) y uno bueno, bloqueaba a 255″ y parecía absurdo. Ahora se marcan TODAS las nuestras y el veredicto usa la **peor** (mayor distancia a la nube de los demás), y la sección combinada lista **cada una de nuestras observaciones con su propio residuo**, para que el observador vea cuál descartar. (2) La tabla de runs de Análisis filtra a la **visita pulsada** (`_analysis_visit_filter`): un clic en una visita muestra solo sus runs. (3) El conjunto combinado se abre **en el editor** (`tab_trackstack.show_combined`): el host reúne el stack propio de cada observación marcada (por `NS_RUN` + `_obs<N>`) y la pestaña las pinta como UN resultado tipo run (tira, puntos, chequeo), en vez de abrir un solo run. (4) El menú contextual de la imagen mapeaba la posición desde la vista, no desde el viewport, así que el menú caía fuera de pantalla (reportado «no aparece el menú de la imagen»): ahora se mapea desde el viewport.

**Review (2026-10-13, double-click opens a run)**: the Analysis "Astrometry runs" table opened a run only with its "Open in the editor" button; double-clicking a row now opens it too (the visit window's "Runs" block already had it). Both go through the busy dialog.

**Revisión (2026-10-13, doble clic abre un run)**: la tabla «Astrometry runs» de Análisis abría un run solo con su botón «Open in the editor»; ahora doble clic en una fila también lo abre (el bloque «Runs» de la visita ya lo tenía). Los dos pasan por el diálogo de espera.

**Review (2026-10-16, picking another run of the same visit)**: opening a run with 7 observations showed the run that was already on stage, not the picked one (reported). The editor's session key is `(project, visit)`, so another run of the SAME visit reset nothing and `_restore_result` refused to replace what it held (its guard is "_result is not None"). The run is not the session: `_visit_astrometry` now asks the tab to `forget_run(run_id)` before loading the plate, so the picked run is the one that loads; with the right run already on stage it is a no-op (re-reading the stacks from disk is not free).

**Revisión (2026-10-16, elegir otro run de la misma visita)**: abrir un run de 7 observaciones mostraba el run que ya estaba en escena, no el elegido (reportado). La clave de sesión del editor es `(proyecto, visita)`, así que otro run de la MISMA visita no reseteaba nada y `_restore_result` se negaba a reemplazar lo que tenía (su guarda es «_result is not None»). El run no es la sesión: `_visit_astrometry` ahora pide a la pestaña `forget_run(run_id)` antes de cargar la placa, así que el run elegido es el que carga; con el run correcto ya en escena no hace nada (releer los apilados del disco no es gratis).
