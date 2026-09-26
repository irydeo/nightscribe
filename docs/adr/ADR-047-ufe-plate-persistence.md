# ADR-047: El estado de la placa vive en la placa: mediciones ligadas a su origen y recuperación completa / plate state lives on the plate: points tied to their source plate, full recovery

**Estado / Status**: Accepted · **Fecha / Date**: 2026-09-26 ·
**ejecutado / executed**: 2026-09-26 (suite unitaria 1840 green + smoke
offscreen) · **Enmendado / Amended**: ADR-045 (forma A «sin visita no hay
medición»: ahora, si la medición tiene placa, clic en la fila reaparece la
placa con su estado; sin placa, aviso llano)

**Ver / See**: ADR-044 (el UFE; extendido aquí con el ciclo de vida del estado
de placa) · ADR-045 (la visita y su bloque de mediciones; enmendado aquí) ·
ADR-042 (secuencias fotométricas: su CSV viaja ahora con el estado de la placa)
· ADR-037 (campañas: `context["sequence"]` se conserva, no se reemplaza).

## Español

**Contexto.** El UFE es donde una placa se convierte en medición calibrada
(ADR-044), y la pestaña Análisis organiza cada noche como una visita con sus
mediciones y recursos (ADR-045). Allí quedaban dos fricciones:

1. **El editor olvidaba todo al cerrar.** El estiramiento, la receta de
   medida y la secuencia de comparaciones vivían en memoria. Reabrir la
   misma placa obligaba a rehacer de cero todo lo que la semana anterior
   ya se había montado para ella.
2. **El punto no sabía de qué placa salió.** `photometry_points` solo
   llevaba valor y origen textual. Un punto «por libre» (sin proyecto)
   era imposible de rastrear de vuelta a su placa, y desde la ventana
   de la visita no había camino de la medida al origen. Regla de campo:
   «las mediciones asociadas a ficheros no pueden ir por libre».

En resumen: ni la medición ni el estado de trabajo tenían referencia a
la placa, que es su origen natural.

**Decisión.**

1. **La placa tiene un estado de trabajo**
   (`project_files.meta["ufe"]`, sin migración: `meta` ya es JSON). Un
   único bloque que la app escribe con el guardado *explícito* (no hay
   autoguardado; `closeEvent` del UFE sigue sin guardar, ADR-044):
   `{"stretch": {black, white, gamma, invert}, "measure": <receta>,
   "sequence": <campos y comparaciones>, "saved_at": <ISO-8601>}`.
   La persistencia es de la receta, no de los puntos (los puntos son su
   propio registro). `subtract` **no** se persiste: depende de la placa
   de referencia del blink, que es de sesión (ADR-044). `meta` se *mergea*: guardar el estado
   conserva las claves ajenas (p. ej. `"campaign"`), y el restado de
   estado escribe `{"ufe": None}` para borrar solo esa clave.
2. **El punto sabe de qué placa salió** (migración v11): columna
   `file_id INTEGER` en `photometry_points` (FK `project_files.id`,
   `ON DELETE SET NULL`, con índice). Un punto guardado sin placa
   registrada se guarda igual, con `file_id=None`, y la barra de estado
   lo deja claro (la placa no está registrada en el proyecto); el
   guardado de estado se omite: no hay fila de placa a la que colgarlo.
   Si hay placa, la referencia va siempre con el punto.
3. **Guardar la secuencia es un doble guardado.** El CSV sale como
   siempre (registro de fichero + proyecto, ADR-045), y **además** el
   estado completo de la placa (stretch + measure + sequence +
   `saved_at`) se guarda en el `meta["ufe"]` de la placa abierta,
   resuelta por camino dentro del proyecto. El `context["sequence"]`
   de la campaña (ADR-037) se conserva igual que antes: el guardado
   explícito de la secuencia no toca el protocolo.
4. **El UFE recupera la placa.** Abrir una placa desde una visita
   restaura el estado guardado en orden: estiramiento primero (la
   imagen queda como la dejaste), luego la receta y la secuencia.
   Restauración tolerante: un estado guardado sin secuencia (o con
   `None`) restaura lo que hay; sin placa cargada es un *no-op*.
5. **Clic en una medición reaparece la placa.** La fila de cada punto
   en la ventana de la visita es clicable: con placa, el UFE abre sobre
   esa placa con su estado guardado restaurado (la pestaña Medir, a
   punto); sin placa, o la placa ya no es una imagen usable, un aviso
   llano en la barra de estado (no error, nada que recuperar).
   `file_id` es la única fuente de verdad del origen: reports (CSV,
   AAVSO EFF), dashboard «Necesita tu atención» y vigilias siguen
   leyendo `photometry_points` (ADR-045 no cambia de superficie).
6. **Dos resets desde la pestaña Medir del UFE.** «Restablecer estado…»
   *sin* confirmación (el editor vuelve a sus valores por defecto *y*
   se borra el `meta["ufe"]` de la placa; los puntos de la placa no
   se tocan) y «Reiniciar puntos…» *con* confirmación (borra los
   puntos de esa placa; refresco de la página del proyecto: curva de
   luz y visitas). Sin proyecto no hay botones (misma regla que
   «Guardar…»).

**Consecuencias.** Un único punto de contacto del estado entre el
editor y la app (ganchos `set_reset_hooks` / `notify_reset_*` del
diálogo, sin que el editor sepa nada de proyectos): el UFE sigue
siendo una ventana de edición pura. La migración v11 es aditiva y
`ON DELETE SET NULL`: borrar una placa no borra mediciones, las deja
huérfanas, que es la situación ya existente (punto sin registro). El
estado de placa por diseño no incluye nada que dependa de sesión
(subtract, placa de referencia del blink): reabrir una placa siempre
da un resultado coherente.

## English

**Context.** The UFE is where a plate turns into a calibrated
measurement (ADR-044), and the Analysis tab organizes each night as a
visit with its measurements and resources (ADR-045). Two frictions
remained:

1. **The editor forgot everything on close.** The stretch, the measure
   recipe and the comparison sequence were all in memory. Reopening the
   same plate meant rebuilding from scratch every setup that had already
   been made for it.
2. **The point did not know which plate it came from.**
   `photometry_points` only carried a value and a textual source. A
   lone point (no project) could not be traced back to its plate, and
   the visit window gave no path from the measurement back to its
   origin. Field rule: "measurements tied to a file must not
   float free."

In short: neither the measurement nor the working state referenced the
plate, their natural source.

**Decision.**

1. **The plate has a working state**
   (`project_files.meta["ufe"]`, no migration needed: `meta` is already
   JSON). One block the app writes on an *explicit* save (no
   autosave; the UFE's `closeEvent` still saves nothing, ADR-044):
   `{"stretch": {black, white, gamma, invert}, "measure": <recipe>,
   "sequence": <field and comparisons>, "saved_at": <ISO-8601>}`.
   What is persisted is the recipe, not the points (the points are
   their own record). `subtract` is *not* persisted: it depends on the
   blink reference plate, which is session-scoped (ADR-044). `meta` is *merged*: saving the
   state keeps the sibling keys (e.g. `"campaign"`), and a state reset
   writes `{"ufe": None}` to drop only that key.
2. **The point knows its source plate** (migration v11): a new
   `file_id INTEGER` column on `photometry_points` (FK
   `project_files.id`, `ON DELETE SET NULL`, indexed). A point saved
   without a registered plate is still saved, with `file_id=None`, and
   the status bar makes it clear (the plate is not registered in the
   project); the state save is skipped: there is no plate row to hold
   it. When a plate exists, the reference always rides with the point.
3. **Saving the sequence is a double save.** The CSV is written as
   before (file registration + project, ADR-045), and *additionally*
   the plate's full state (stretch + measure + sequence + `saved_at`)
   is stored in the open plate's `meta["ufe"]`, resolving the plate by
   path within the project. The campaign's `context["sequence"]`
   (ADR-037) is preserved exactly as before: the explicit sequence save
   does not touch the protocol.
4. **The UFE recovers the plate.** Opening a plate from a visit
   restores the saved state in order: the stretch first (the image
   is as you left it), then the recipe and the sequence. The
   restore is tolerant: a state saved without a sequence (or with
   `None`) restores what is there; with no plate loaded it is a no-op.
5. **A click on a measurement brings the plate back.** Every point row
   in the visit window is clickable: with a plate, the UFE opens on
   that plate with its saved state restored (the Measure tab, ready);
   without a plate (hand-entered, pasted, saved before this decision,
   plate no longer available, or the UFE disabled), a plain notice in
   the status bar (not an error, nothing to lose). `file_id` is the
   single source of truth for origin: reports (CSV, AAVSO EFF), the
   attention dashboard and the vigils keep reading `photometry_points`
   (ADR-045's surface is unchanged).
6. **Two resets from the UFE's Measure tab.** "Reset state…"
   *without* confirmation (the editor returns to its defaults *and*
   `meta["ufe"]` is dropped from the plate; its points are not
   touched) and "Reset points…" *with* confirmation (the plate's
   points are deleted, and the project page refreshes: light curve and
   visits). No project, no buttons: same rule as "Save…".

**Consequences.** A single contact point for state between the editor
and the app (the dialog's `set_reset_hooks` / `notify_reset_*` hooks,
with the editor knowing nothing about projects): the UFE remains a pure
editing window. The v11 migration is additive and `ON DELETE SET NULL`:
deleting a plate never deletes measurements, it orphans them, which
is the situation that already existed (a point without a registration).
By design, the plate state contains nothing session-scoped (subtract,
the blink reference plate): reopening a plate always gives a coherent
result.
