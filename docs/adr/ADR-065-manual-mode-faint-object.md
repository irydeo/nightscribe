# ADR-065: Modo manual para objetos por debajo de la puerta de detección

**Estado / Status**: Accepted · **Fecha / Date**: 2026-10-06

**Ver / See**: ADR-062 (track & stack, D10), ADR-064 (cascada de efemérides),
ADR-044 (el editor y sus diálogos), ADR-058 (ninguna cifra sin explicación).

## Español

**Contexto.** El apilado decide si hay objeto con una **puerta de detección**
(D10): mide la SNR en una apertura de 4 px sobre el stack de toda la secuencia
y, por debajo de `astrometry_snr_sigma` (3,5σ por defecto), **no barre, no
apila por observación y no mide**: mide ruido y quedarse con el máximo es cómo
se fabrica un falso positivo. Es la decisión correcta por defecto, pero deja
fuera un caso real: un objeto **muy débil** que un ojo humano sí distingue con
un buen estirado. Medido en 2026 PY9: la puerta no disparó y el run terminó
con «no detectado», tirando el stack base que ya estaba construido.

El observador pidió un **modo manual**: forzar el stack con la efeméride
conocida, marcar el objeto y medir desde esa marca.

**Decisión.**

1. **El stack base no se tira.** Cuando la puerta no dispara, el payload del
   run conserva el stack de toda la secuencia y su geometría (el recorte, el
   punto de la efeméride, la WCS de referencia). Sin eso no hay nada que
   enseñar ni sobre lo que marcar. (Desde la segunda revisión se conserva
   SIEMPRE, no solo cuando la puerta no dispara.)
2. **Una marca humana sustituye a la puerta, no la baja.** El modo manual vive
   en su propio diálogo no modal (como el centro manual de Fotometría): la
   pestaña guarda solo la casilla, el diálogo enseña el stack, arma la marca,
   la afina y mide. La casilla está **siempre visible**; cuándo se habilita lo
   deciden las revisiones del 2026-10-06 (primero solo tras un «no detectado»,
   y después con cualquier visita armada: ver la segunda revisión).
3. **La marca se afina**: el clic se ajusta al **centroide gaussiano** de la
   fuente local más cercana (el mismo ajuste que usa el retículo de Medir) y
   se puede **ajustar a mano en pasos de 0,1 px** con las flechas, como el
   centro manual de Fotometría y el nudge del blink.
4. **Desde la marca**: se vuelve a ejecutar el pipeline con la marca como
   punto de referencia en la rejilla, y el **mismo offset** (el error de la
   predicción, constante a lo largo de la visita) se lleva al punto efemérico
   de cada observación. Se **salta la puerta** (la marca ES la detección) y
   **no se ejecuta el barrido de velocidad**: sobre una fuente por debajo del
   umbral el score del barrido es ruido. La velocidad es la de la efeméride.
5. **Se dice, no se esconde.** La nota del run da la SNR **en la marca** y
   avisa de que la detección es manual; los puntos llevan su aviso; el listón
   de envío del MPC sigue aplicando y el observador puede forzar el reporte
   con el «Forzar» que ya existe. La marca la firma el observador.
6. **Lo que NO hace**: no baja la puerta para todos los runs, no convierte una
   marca en una detección automática, y no evita el barrido por defecto en un
   run normal. Es una puerta que abre una persona, para un objeto concreto.

**Consecuencias.** `TrackStackWorker` gana `manual_ref`; `core/track_stack.py`
gana `manual_reference` (la aritmética pura del offset); el editor gana
`gui/ufe_manual_stack_dialog.py` + `ui/ufe_manual_stack_dialog.ui` y la
casilla `chk_manual` en la pestaña de Astrometría. El coste de la segunda
pasada es volver a resolver (ASTAP cacheado) y registrar: es una acción
deliberada del observador, no el camino normal.

**Revisión (2026-10-06): la marca se ve, la cruz medida no se pierde y el run
se reabre.** Cuatro cosas que la primera versión dejaba a medias, todas pedidas
tras usarla sobre un objeto real:

1. **La cruz de la marca.** Al marcar, la pestaña dibuja una **cruz corta**
   (`mark_cross_items`, cuatro brazos con sombra) sobre el centroide marcado,
   para que se vea DÓNDE cae mientras se afina con las flechas. Tiene su
   interruptor en el diálogo (**«Mostrar la cruz en la marca»**, activado por
   defecto): una cruz sobre un objeto de magnitud 19 es una cruz sobre el
   objeto, y el observador decide.
2. **La cruz de la posición medida no se pierde.** Antes era una superposición
   en píxeles del stack que se caía al cargar otra imagen de la serie y al
   pasar a Fotometría. Ahora está **anclada al cielo** (la RA/Dec del punto) y
   se coloca con la **WCS de la placa abierta** (`_draw_marks`), así que vuelve
   con cada placa de la visita y al volver a la pestaña. Sin WCS solo habla el
   propio stack de la observación, en sus píxeles; en cualquier otra placa la
   cruz se va en vez de mentir.
3. **El run se reabre y se ve entero.** Al terminar, la pestaña **escribe todas
   las pilas** de la ejecución (antes solo la que el observador abría), y el
   resumen escalar del run (detección, barrido, brillo, registro, calibración,
   veredicto) viaja en el `cfg_json` del run, sin migración de esquema. El host
   lo devuelve con `_ufe_astrometry_result` y la pestaña repinta notas, tabla,
   visor, tira y blink desde lo guardado (`_restore_result`): nada se recalcula
   y nada se inventa. El «Deshacer» sigue apuntando al run restaurado. La tabla
   marca la magnitud **escrita a mano** cuando el punto guardado trae
   `mag_source='manual'`: la cifra efectiva no se presenta como la del run.
4. **Un run «no detectado» se reabre como lo que fue.** Sus notas vuelven (el
   límite de magnitud de la noche), pero la puerta manual queda **cerrada y con
   su motivo**: el modo manual necesita el stack base, que es un intermedio que
   no se guarda. Se dice, no se abre una puerta sobre nada.

**Consecuencias (revisión).** El host gana `_astrometry_summary` (el resumen
JSON-safe, con los escalares de numpy desempaquetados) y
`_ufe_astrometry_result`; el editor gana `set_astrometry_result_hook` /
`astrometry_result`; la pestaña gana `_restore_result`, `_restored_payload`,
`_save_group_stack` y `_draw_marks`. El coste de escribir todas las pilas es un
fichero por observación (el mismo que ya se escribía para la primera, ahora
para todas): es el precio de un resultado que se puede reabrir en vez de
recalcular.

**Revisión (2026-10-07): el stack del conjunto es de SU ejecución.** El fichero
donde se coloca la marca se llamaba `<objeto>_base.fits` para todo el proyecto, y cada
pasada lo sobrescribía: reabrir un run antiguo marcaba sobre el stack de la más reciente
(otra imagen, otra WCS, otro `box_all`). Ahora el nombre lleva el id del run
(`<objeto>_base_r<id>.fits`); un run escrito antes de este cambio cae al nombre compartido
que tenga en disco, y el modo manual sigue diciendo sobre qué placa se está marcando.

## English

**Context.** Stacking decides whether there is an object with a **detection
gate** (D10): it measures the SNR in a 4 px aperture on the whole-sequence
stack and, below `astrometry_snr_sigma` (3.5σ by default), **does not sweep,
does not stack per observation and does not measure**: it would be measuring
noise, and keeping the maximum is how a false positive is manufactured. That
is the right default, but it leaves out a real case: a **very faint** object a
human eye can still tell apart with a good stretch. Measured on 2026 PY9: the
gate did not fire and the run ended as "not detected", throwing away the base
stack that had already been built.

The observer asked for a **manual mode**: force the stack with the known
ephemeris, mark the object and measure from that mark.

**Decision.**

1. **The base stack is not thrown away.** When the gate does not fire, the
   run's payload keeps the whole-sequence stack and its geometry (the cutout,
   the ephemeris point, the reference WCS). Without it there is nothing to
   show and nothing to mark on. (From the second revision it is kept ALWAYS,
   not only when the gate does not fire.)
2. **A human mark replaces the gate; it does not lower it.** Manual mode lives
   in its own non-modal dialog (like the Photometry tab's manual centre): the
   tab keeps only the checkbox, the dialog shows the stack, arms the mark,
   refines it and measures. The checkbox is **always visible**; when it is
   enabled is decided by the 2026-10-06 revisions (first only after a "not
   detected" run, then with any armed visit: see the second revision).
3. **The mark is refined**: the click is snapped to the **gaussian centroid**
   of the nearest local source (the same refinement the Measure reticle uses)
   and can be **nudged by hand in 0.1 px steps** with the arrows, like the
   Photometry manual centre and the blink nudge.
4. **From the mark**: the pipeline runs again with the mark as the reference
   point in the grid, and the **same offset** (the prediction's error, constant
   over the visit) is carried to each observation's ephemeris point. The
   **gate is bypassed** (the mark IS the detection) and the **velocity sweep
   is not run**: over a source below the gate the sweep's score is noise. The
   velocity is the ephemeris'.
5. **It is said, not hidden.** The run's note gives the SNR **at the mark** and
   warns that the detection is manual; the points carry their flag; the MPC
   submission floor still applies and the observer can force the report with
   the "Force" that already exists. The mark is the observer's signature.
6. **What it does NOT do**: it does not lower the gate for every run, it does
   not turn a mark into an automatic detection, and it does not skip the sweep
   by default in a normal run. It is a door a person opens, for one object.

**Consequences.** `TrackStackWorker` gains `manual_ref`; `core/track_stack.py`
gains `manual_reference` (the pure offset arithmetic); the editor gains
`gui/ufe_manual_stack_dialog.py` + `ui/ufe_manual_stack_dialog.ui` and the
`chk_manual` checkbox in the Astrometry tab. The second pass costs solving
(ASTAP is cached) and registering again: it is a deliberate action of the
observer, not the normal path.

**Revision (2026-10-06): the mark is seen, the measured cross is not lost and
the run reopens.** Four things the first version left half-done, all asked for
after using it on a real object:

1. **The mark's cross.** On marking, the tab draws a **short cross**
   (`mark_cross_items`, four arms with a shadow) on the marked centroid, so it
   is clear WHERE it sits while the arrows refine it. It has its switch in the
   dialog (**"Show the cross at the mark"**, on by default): a cross over a
   19th magnitude object is a cross over the object, and the observer decides.
2. **The measured position's cross is not lost.** It used to be a stack-pixel
   overlay that fell off when another image of the series was loaded and when
   the Photometry tab took the stage. It is now **anchored to the sky** (the
   point's RA/Dec) and placed with the **open plate's own WCS** (`_draw_marks`),
   so it comes back on every plate of the visit and on returning to the tab.
   Without a WCS only the observation's own stack can speak, in its pixels; on
   any other plate the cross goes rather than lie.
3. **The run reopens and is shown whole.** When the run ends, the tab **writes
   every stack** of the execution (before, only the one the observer opened),
   and the run's scalar summary (detection, sweep, brightness, registration,
   calibration, verdict) rides in the run's `cfg_json`, with no schema
   migration. The host hands it back through `_ufe_astrometry_result` and the
   tab repaints the notes, the table, the group viewer, the strip and the blink
   from what was saved (`_restore_result`): nothing is recomputed and nothing
   is invented. "Undo" still points at the restored run. The table marks the
   magnitude as **written by hand** when the saved point carries
   `mag_source='manual'`: the effective figure is not presented as the run's.
4. **A "not detected" run reopens as what it was.** Its notes come back (the
   night's limit magnitude), but the manual door stays **closed and with its
   reason**: the manual mode needs the base stack, an intermediate that is not
   kept. It is said, not opened onto nothing.

**Consequences (revision).** The host gains `_astrometry_summary` (the
JSON-safe summary, with numpy scalars unwrapped) and `_ufe_astrometry_result`;
the editor gains `set_astrometry_result_hook` / `astrometry_result`; the tab
gains `_restore_result`, `_restored_payload`, `_save_group_stack` and
`_draw_marks`. Writing every stack costs one file per observation (the same one
that was already written for the first, now for all of them): it is the price
of a result that can be reopened instead of recomputed.

**Revisión (2026-10-06, segunda): el modo manual, siempre disponible.** Se pidió
quitarlo de detrás de la puerta de detección: sirve en cualquier run, aunque sea
para colocar a ojo el centroide de un objeto débil que sí se detectó. Lo que
cambia y lo que no:

1. **La casilla ya no la abre un «no detectado»**: la abre el observador, y
   está disponible con CUALQUIER ejecución (con o sin detección). Espera con el
   resto del resultado hasta que hay una: antes de la primera pasada no existe
   la pila de toda la secuencia sobre la que se marca, así que una puerta ahí
   sería una puerta sobre nada. Sin visita tampoco hay secuencia que apilar, y
   se queda cerrada.
2. **La marca se pone sobre el stack base**, que ahora es un producto del run
   (ADR-062): se construye siempre, se guarda siempre y se recarga al reabrir,
   así que marcar funciona igual recién hecho el run, en un run con detección o
   en una visita reabierta. Sin stack base (un run viejo, anterior a esta
   decisión) el diálogo lo dice: «apila la secuencia primero».
3. **La aritmética no cambia**: la marca es un punto de la rejilla de
   referencia, el offset se lleva a cada observación, la puerta se salta y el
   barrido no se ejecuta. `box_all` viaja en el resumen del run para poder
   convertir la marca en la rejilla cuando el run se reabre.
4. **Se dice, no se esconde**: el modo manual sigue siendo una marca humana.
   El run lo dice en sus **notas** («la posición salió de una MARCA HUMANA…»)
   y **cada punto lleva el aviso** `manual` (la tabla lo escribe con palabras,
   la fila persistida lo guarda y la auditoría del reporte lo lee). Lo que se
   ha quitado es la CONDICIÓN de entrada, no la advertencia.
5. **El run reabierto trae su informe**: el generador es local y determinista,
   así que se reconstruye en su caja (en silencio: el cuadro de notas conserva
   la historia del run, que el informe no debe pisar). No se envía a ninguna
   parte: eso sigue siendo el botón.

**Revision (2026-10-06, second): the manual mode, always available.** Asked for:
take it out from behind the detection gate; it is useful on any run, if only to
place by eye the centroid of a faint object that WAS detected. What changes and
what does not:

1. **A "not detected" run no longer opens the checkbox**: the observer does,
   and it is available with ANY run (with or without a detection). It waits with
   the rest of the result until there is one: before the first pass the
   whole-sequence stack it marks on does not exist, so a door there would open
   onto nothing. With no visit there is no sequence to stack either, and it
   stays closed.
2. **The mark is placed on the base stack**, which is now a product of the run
   (ADR-062): it is always built, always saved and reloaded on reopen, so
   marking works right after the run, on a run that detected the object, and on
   a reopened visit. With no base stack (an old run, from before this decision)
   the dialog says so: "stack the sequence first".
3. **The arithmetic does not change**: the mark is a point in the reference
   grid, the offset is carried to every observation, the gate is bypassed and
   the sweep is not run. `box_all` travels in the run's summary so the mark can
   be converted to the grid when the run is reopened.
4. **It is said, not hidden**: the manual mode is still a human mark. The run
   says it in its **notes** ("the position came from a HUMAN MARK…") and
   **every point carries the `manual` flag** (the table writes it in words,
   the persisted row keeps it and the report's audit reads it). What was
   removed is the ENTRY CONDITION, not the warning.
5. **A reopened run brings its report**: the generator is local and
   deterministic, so it is rebuilt in its box (quietly: the notes box keeps the
   run's own story, which the report must not overwrite). It is not sent
   anywhere: that is still the button.

**Revision (2026-10-07): the whole-sequence stack belongs to ITS run.** The file the mark
is placed on was named `<object>_base.fits` for the whole project, and every pass
overwrote it: reopening an old run marked on the newest pass's stack (another image,
another WCS, another `box_all`). The name now carries the run id
(`<object>_base_r<id>.fits`); a run written before this change falls back to the shared
name it has on disk, and the manual window still says which plate is being marked.
