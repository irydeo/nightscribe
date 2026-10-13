# ADR-085: Re-selección manual del centroide (re-medir sin re-apilar)

**Estado / Status**: Accepted · **Fecha / Date**: 2026-10-13

**Ver / See**: ADR-062 (astrometría), ADR-065 (modo manual), ADR-077 (residuos), ADR-058 (ninguna cifra sin explicación).

## Español

**Contexto**: cuando una medición sale mal respecto a sus residuos, la causa
más común es el **centroide**: un vecino brillante lo arrastra, o el objeto cayó
sobre un píxel malo. Hasta ahora la única puerta era el **modo manual** (ADR-065),
que vuelve a ejecutar el pipeline (resolver + registrar los fotogramas) con una
marca; es correcto para un objeto por debajo de la puerta, pero para corregir un
punto ya medido es desproporcionado. El observador quería el gesto de
Tycho-Tracker: seleccionar el centroide a mano, que se recalcule al instante y
que se vea el error nuevo, **sin re-apilar**.

**Decisión**: re-medir SOLO el stack point de una observación desde una marca
humana, sobre el stack que ya está guardado.

1. **La marca la pone el ojo.** El clic derecho en la tabla de observaciones o
   sobre la imagen abre un menú; «Ajustar el centroide…» enseña el **stack de
   ESA observación** (no el base) y el clic se ajusta al **centroide gaussiano**
   local (la MISMA rutina que la medida, `core/astrometry.centroid`), afínable
   con «Volver al medido».
2. **Sin re-apilar.** Se re-mide con `astrometry.measure_stack(stack, xy, wcs,
   …)`: un centroide sobre la imagen combinada y la conversión con su WCS (que
   el stack lleva en su cabecera). La parte cara (registrar N fotogramas) no se
   toca.
3. **Solo el stack point.** El punto por frame (el otro lado del doble chequeo)
   se deja como está; la columna de separación se actualiza sola.
4. **Se firma.** El punto queda con `centroid_source='manual'` y el aviso «centroide
   re-seleccionado a mano»; el listón del MPC sigue aplicando.
5. **El chequeo se repite solo.** Al aceptar, se re-lanza el chequeo (el mismo
   `_auto_recheck` con debounce que ya usaba la exclusión): el observador ve el
   error nuevo sin pedirlo.
6. **Se dice qué arregla.** El diálogo avisa de que esto corrige el **centroide**,
   no un **registro** malo (para eso, re-apilar).

**Consecuencias**: `astrometry_points` gana `centroid_source` (migración v20);
`astrometry_store.set_manual_centroid`; un menú contextual **único** sobre la
tabla y la imagen (un solo constructor, para que no diverjan); un selector de
centroide propio (`gui/ufe_centroid_dialog.py`); y el gancho de host
`set_manual_centroid`. La fotometría (`mag`, `band`, `mag_err`) se conserva al
re-medir la posición.

**Alternativas**: (a) reutilizar el modo manual, descartado: re-ejecuta el
pipeline entero; (b) medir a mano sin re-chequear, descartado: el observador
quiere ver el error nuevo; (c) ajustar también el punto por frame, descartado:
no es lo que falla y duplica el coste.

## English

**Context**: when a measurement looks wrong against its residuals, the usual
cause is the **centroid**: a bright neighbour drags it, or the object landed on
a bad pixel. Until now the only door was **manual mode** (ADR-065), which re-runs
the pipeline (resolve + register the frames) from a mark; correct for an object
below the gate, but disproportionate to fix an already measured point. The
observer wanted the Tycho-Tracker gesture: select the centroid by hand, have it
recomputed at once and see the new error, **without re-stacking**.

**Decision**: re-measure ONLY one observation's stack point from a human mark,
on the stack that is already saved.

1. **The eye places the mark.** Right-clicking the points table or the image
   opens a menu; "Adjust the centroid…" shows **that observation's** stack (not
   the base one) and the click snaps to the local **gaussian centroid** (the
   SAME routine the measurement uses, `core/astrometry.centroid`), refineable
   with "Back to the measured one".
2. **No re-stacking.** It re-measures with `astrometry.measure_stack(stack, xy,
   wcs, …)`: one centroid on the combined image and the conversion with its WCS
   (which the stack carries in its header). The expensive part (registering N
   frames) is untouched.
3. **Only the stack point.** The per-frame point (the other half of the double
   check) is left alone; the separation column updates itself.
4. **It is signed.** The point gets `centroid_source='manual'` and the
   "centroid re-selected by hand" notice; the MPC floor still applies.
5. **The check re-runs by itself.** On accept, the check is fired again (the
   same debounced `_auto_recheck` the exclusion already used): the observer sees
   the new error without asking.
6. **It says what it fixes.** The dialog warns that this corrects the
   **centroid**, not a bad **registration** (for that, re-stack).

**Consequences**: `astrometry_points` gains `centroid_source` (migration v20);
`astrometry_store.set_manual_centroid`; ONE context menu over the table and the
image (a single builder, so they never drift); its own centroid picker
(`gui/ufe_centroid_dialog.py`); and the host hook `set_manual_centroid`. The
photometry (`mag`, `band`, `mag_err`) is preserved when the position is
re-measured.

**Alternatives**: (a) reusing manual mode, rejected: it re-runs the whole
pipeline; (b) measuring by hand without re-checking, rejected: the observer wants
to see the new error; (c) adjusting the per-frame point too, rejected: it is not
what failed and it doubles the cost.

**Review (2026-10-13, the picker renders the stack, and the error toggle reaches the band)**: two fixes after real use. (1) The picker's preview used `np.percentile`, but a stack is full of **NaNs** (the pixels the cutout did not cover) and a plain percentile answers NaN, so the whole image went black (reported: "the centroid window is all black"). It now uses the app's own NaN-safe engine (`core/stretch.auto_limits` + `apply_stretch` + `to_uint8`), with a gamma of 0.5 so a faint object shows; NaNs stay black, which is correct. (2) The "Show/Hide photometric error" toggle only hid the table's "±" column, while the observer was looking at the **band over the image** ("Mag: X ± Y (V)"): it now drops the error from `_measured_from_header` (the band's source) and repaints the view, so the ± appears and disappears in the band AND in the column.

**Revisión (2026-10-13, el selector pinta el stack y el conmutador llega a la banda)**: dos arreglos tras el uso real. (1) La vista previa del selector usaba `np.percentile`, pero un stack está lleno de **NaN** (los píxeles que el recorte no cubrió) y un percentil normal devuelve NaN, así que toda la imagen salía negra (reportado: «la ventana del centroide está toda negra»). Ahora usa el motor NaN-safe de la app (`core/stretch.auto_limits` + `apply_stretch` + `to_uint8`), con gamma 0.5 para que un objeto tenue se vea; los NaN quedan negros, que es lo correcto. (2) El conmutador «Mostrar/ocultar el error fotométrico» solo escondía la columna «±» de la tabla, mientras el observador miraba la **banda sobre la imagen** («Mag: X ± Y (V)»): ahora quita el error de `_measured_from_header` (la fuente de la banda) y repinta la vista, así que el ± aparece y desaparece en la banda Y en la columna.

**Review (2026-10-13, the adjust lives on the editor's stage, not in a bare window)**: the bespoke picker was unusable (no zoom, no stretch: "the window is all black and has nothing where the image should be"). It is **removed**. "Adjust the centroid…" now arms a **one-click mode on the editor's own stage** (the shared image view): the observation's stack is shown there (`_show_group`), the observer zooms, stretches and reads the histogram with the SAME controls the editor already has, and the click is converted (`scene_to_data`) and snapped to the local centroid (`_snap_centroid`, the pick reticle's own routine) before `_recentroid` re-measures. The mode disarms itself on the first click. No new window, no second image pipeline: the tool the observer already knows IS the tool.

**Revisión (2026-10-13, el ajuste vive en el escenario del editor, no en una ventana pelada)**: el selector propio era inservible (sin zoom, sin estirado: «la ventana está toda negra y no tiene nada donde debería estar la imagen»). Se **elimina**. «Ajustar el centroide…» arma ahora un **modo de un clic sobre el escenario del propio editor** (la vista compartida): el stack de la observación se muestra allí (`_show_group`), el observador hace zoom, estira y lee el histograma con los MISMOS controles que el editor ya tiene, y el clic se convierte (`scene_to_data`) y se ajusta al centroide local (`_snap_centroid`, la rutina del propio retículo) antes de que `_recentroid` re-mida. El modo se desarma solo con el primer clic. Sin ventana nueva, sin un segundo pipeline de imagen: la herramienta que el observador ya conoce ES la herramienta.

**Review (2026-10-13, the WCS is read as PC+CDELT, and the view is not thrown away)**: two more fixes. (1) `astrometry.pixel_scale_arcsec` read `wcs.wcs.cd` directly, but astropy reads a stack written with CD back as **PC+CDELT**, so the property raises ("No cd is present") and the re-measure crashed. It now falls back to `wcs.pixel_scale_matrix`, which answers both forms. (2) Arming the adjust called `_show_group`, which reloaded the stack and reset the observer's **zoom and stretch** even when the observation was already on stage. Now, if the observation is already shown nothing is reloaded (the view stays exactly as it was); if another one has to come on stage, the stretch is kept (`state.keep_stretch`) and the zoom factor restored (`fit_to_factor`).

**Revisión (2026-10-13, el WCS se lee como PC+CDELT y la vista no se tira)**: dos arreglos más. (1) `astrometry.pixel_scale_arcsec` leía `wcs.wcs.cd` directamente, pero astropy lee un stack escrito con CD como **PC+CDELT**, así que la propiedad lanza («No cd is present») y la re-medida reventaba. Ahora cae a `wcs.pixel_scale_matrix`, que responde a las dos formas. (2) Armar el ajuste llamaba a `_show_group`, que recargaba el stack y reseteaba el **zoom y el estirado** del observador aunque la observación ya estuviera en el escenario. Ahora, si la observación ya está mostrada no se recarga nada (la vista queda igual); si hay que mostrar otra, se conserva el estirado (`state.keep_stretch`) y se restaura el factor de zoom (`fit_to_factor`).

**Review (2026-10-13, the placed centroid is drawn)**: after the re-measure the measured cross stayed on the OLD position (`_recentroid` did not repaint), so there was no way to see where the centroid had landed. Now `_recentroid` remembers the mark (the observation's own stack pixels), calls `_draw_marks` and the stage paints it with the manual mode's own cross (`mark_cross_items`, the accent), on top of the measured cross that also moves to the new sky position. The mark is forgotten when another observation comes on stage or a new adjust is armed.

**Revisión (2026-10-13, el centroide colocado se dibuja)**: tras re-medir, la cruz medida se quedaba en la posición VIEJA (`_recentroid` no repintaba), así que no había forma de ver dónde había quedado el centroide. Ahora `_recentroid` recuerda la marca (los píxeles del stack de esa observación), llama a `_draw_marks` y el escenario la pinta con la cruceta del propio modo manual (`mark_cross_items`, el acento), encima de la cruz medida, que también se mueve a la posición nueva del cielo. La marca se olvida cuando entra otra observación al escenario o se arma un ajuste nuevo.

**Review (2026-10-13, the same crosshair the Photometry tab uses)**: while the adjust is armed, the view turns on its OWN **pick reticle** (`UfeImageView.set_pick_cursor(True)`), the SAME crosshair that follows the mouse and snaps to the source when a comparison star is picked in the Photometry and Compare tabs. It is turned off when the click is consumed. Nothing new is drawn to guide the eye: the reticle the observer already knows is the one that shows where the mark will land.

**Revisión (2026-10-13, la misma cruceta que usa Fotometría)**: mientras el ajuste está armado, el visor enciende su PROPIO **retículo de selección** (`UfeImageView.set_pick_cursor(True)`), la MISMA cruceta que sigue al ratón y engancha a la fuente al elegir una estrella de comparación en Fotometría y Comparación. Se apaga cuando el clic se consume. No se dibuja nada nuevo para guiar la vista: el retículo que el observador ya conoce es el que enseña dónde caerá la marca.

**Review (2026-10-13, the click is the pixel)**: the adjust snapped the click to the nearest local source (`_snap_centroid`), so a star or a hot pixel near the asteroid stole the mark and moved it away from where the observer clicked. In the adjust mode the click is now used **as-is**: the observer's pixel is the centroid to fix, and `measure_stack` only refines WITHIN the window centred there (that is the measurement, not a jump to another source). The pick reticle stays as the crosshair that shows where the mark will land.

**Revisión (2026-10-13, el clic es el píxel)**: el ajuste enganchaba el clic a la fuente local más cercana (`_snap_centroid`), así que una estrella o un píxel caliente junto al asteroide robaba la marca y la movía del sitio donde el observador pinchó. En el modo de ajuste el clic se usa **tal cual**: el píxel del observador es el centroide a fijar, y `measure_stack` solo afina DENTRO de la ventana centrada ahí (eso es la medida, no un salto a otra fuente). El retículo de selección sigue como la cruceta que enseña dónde caerá la marca.

**Review (2026-10-13, it coexists with the manual mark, and the check is not blocked)**: two fixes. (1) The adjust and the **whole-sequence manual mark (ADR-065)** share the stage and the click, so a stale mode stole the click: arming the centroid adjust now **disarms** the manual mark (`chk_manual` unchecked, its dialog closed) and arming the manual mark **cancels** a pending centroid adjust. The two are different tools and the UI says so: the manual mark re-runs the pipeline on the whole sequence (for an object below the gate); the centroid adjust re-measures ONE observation on its saved stack, no re-stack. (2) After a manual centroid mark the re-check could stay at "Checking against other observers…" for ever: `_auto_recheck` deferred while `self._recheck` was not None, and a worker that ended without clearing left it set, so every later check waited. A worker that `isFinished()` is now treated as free, and the designation falls back to the resolved (confirmed) one.

**Revisión (2026-10-13, convive con la marca manual y el chequeo no se bloquea)**: dos arreglos. (1) El ajuste y la **marca manual de toda la secuencia (ADR-065)** comparten escenario y clic, así que un modo obsoleto robaba el clic: armar el ajuste de centroide ahora **desarma** la marca manual (`chk_manual` desmarcado, su diálogo cerrado) y armar la marca manual **cancela** un ajuste de centroide pendiente. Son herramientas distintas y la UI lo dice: la marca manual re-ejecuta el pipeline sobre toda la secuencia (para un objeto bajo la puerta); el ajuste de centroide re-mide UNA observación sobre su stack guardado, sin re-apilar. (2) Tras una marca manual de centroide el re-chequeo podía quedarse en «Checking against other observers…» para siempre: `_auto_recheck` se difería mientras `self._recheck` no fuera None, y un worker que terminaba sin limpiarlo lo dejaba puesto, así que todos los chequeos posteriores esperaban. Un worker que `isFinished()` ahora se trata como libre, y la designación cae a la resuelta (confirmada).

**Review (2026-10-13, auto centroid and the kept stretch)**: two additions. (1) The context menu gains **"Auto centroid"**: the app picks the centroid again, seeded at the point's current position (`_recentroid(..., auto=True)`), signs it `centroid_source='auto'` (dropping the manual mark) and re-checks; it is the counterpart of "Adjust the centroid…". `astrometry_store.set_manual_centroid` gains a `source` argument. (2) Moving from one observation to the next (`_show_group`) now keeps the observer's **stretch** (`state.keep_stretch` around the load): the runs are the same night, camera and sky, so re-deriving the auto limits on every thumbnail threw away the histogram level the observer had just set.

**Revisión (2026-10-13, centroide automático y estirado conservado)**: dos añadidos. (1) El menú contextual gana **«Centroide automático»**: la app elige el centroide otra vez, sembrado en la posición actual del punto (`_recentroid(..., auto=True)`), lo firma `centroid_source='auto'` (quitando la marca manual) y re-chequea; es la contraparte de «Ajustar el centroide…». `astrometry_store.set_manual_centroid` gana un argumento `source`. (2) Pasar de una observación a otra (`_show_group`) ahora conserva el **estirado** del observador (`state.keep_stretch` durante el load): los runs son la misma noche, cámara y cielo, así que re-derivar los límites automáticos en cada miniatura tiraba el nivel del histograma que el observador acababa de poner.
