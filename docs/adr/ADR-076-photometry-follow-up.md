# ADR-076: Photometry follow-up: weak zero points, what the band reports, re-measuring the stack

**Estado / Status**: Accepted · **Fecha / Date**: 2026-10-10

## Español

**Contexto**: sobre un track & stack real de un NEO débil (450 fotogramas, 4 s,
magnitud medida 19.32 con un **error de 1.36 mag**) salieron cuatro cosas que el
observador no podía entender ni corregir desde la interfaz, más una sobre el PA:

1. **El error de 1.36 mag no tenía explicación**: el punto cero se apoyaba en
   **3 comparsas** (los QC del propio run decían «fewer than four stars»), pero
   nada decía por qué la secuencia de ocho del proyecto se había quedado en
   tres. `core/photometry` ya cuenta los descartes por placa (fuera de la placa,
   saturadas, no lineales, sin flujo positivo, sin valor de catálogo), pero el
   resumen del run no los llevaba y la nota solo daba el número.
2. **No se podía elegir qué brillo reporta la banda**: `chart_annotate.build_band`
   prefiere la medida si existe y la colorea por su error (rojo con error
   > 0.15, o sea el caso). El stack ya guarda `NS_MAGSR` (`measured` |
   `ephemeris`), pero no había ningún control para cambiarlo: el único override
   era escribir una magnitud a mano.
3. **La receta fotométrica no se podía aplicar tras el stack**: la pestaña
   Fotometría se niega a medir un track & stack (en el stack del objeto las
   estrellas son trazas; en el de estrellas el objeto es una traza), y remite a
   la pestaña Astrometría, pero la receta se capturaba **en el momento del run**:
   cambiar aperturas, cielo o comparsas obligaba a re-apilar los 450 fotogramas.
4. **Dos marcas azules parecían un error**: el track & stack trae su propia
   posición medida (la cruz del run y el círculo `ANNOTATE`), y encima se pintaba
   la marca del objeto del proyecto (una cruz de marco completo, en las
   coordenadas del plan, no en las medidas). Las dos, del mismo color porque el
   color de marca es el del tipo de objeto (NEO = azul), y a pocos arcmin de
   distancia: parecía un fallo.
5. **El PA**: se mide en dos sitios. El **barrido de velocidad** busca rate y PA
   (`sweep.best.pa`, guardado en `astrometry_runs.pa_deg` y en la cabecera
   `NS_PA`); si su ganador no supera al propio seed de la efeméride por más de
   tres veces la dispersión del grid, el run **conserva el de la efeméride** y lo
   marca `NS_MOT=eph` (la banda lo pinta como predicción). Y la **forma del
   objeto** mide el PA de su traza (`photometry.psf_elongation`, en
   `trail_pa_deg`), que sale en las notas. En el run medido, la traza real era
   **PA 151.2°** mientras el stack se apiló con el **PA de la efeméride 148.9°**
   (≈2.3° de diferencia), y por eso el objeto salía alargado **9.7 px** en su
   propio stack: **sí medimos el PA (el de la traza), pero no lo realimentamos**
   para corregir el apilado. El reporte MPC (80 columnas y ADES) no lleva PA: el
   formato no tiene campo para el movimiento.

**Decisión**: cuatro cambios, y el PA documentado con su propuesta.

1. **Diagnóstico de comparsas**: el run **suma** `res.skipped` de cada
   observación y lo lleva al resumen (`comps_skipped`, `n_comps_requested`), y la
   nota lo dice en lenguaje llano: «el punto cero se apoya en N de M comparsas
   (…), así que el error es la consecuencia honesta: revisa la secuencia». Con
   menos de cuatro comparsas la advertencia es explícita: un error grande deja de
   parecer un fallo y pasa a ser un dato con causa.
2. **`report_mag` en la receta** (pestaña Fotometría, sección «The photometry
   recipe»): **medida** o **efeméride**. Es parte de la receta porque decide lo
   que un lector ve sobre la imagen; el track & stack lo escribe en la cabecera
   del propio stack (`NS_MAGSR`), de modo que una medida que no merece publicarse
   (punto cero sobre muy pocas comparsas, objeto con traza) se sustituye por la
   cifra etiquetada `(eph)` **sin ocultar la medida**, que se conserva en el run
   y en el punto de astrometría. La elección se guarda y se restaura con la placa
   (ADR-047) y viaja en el resumen persistido del run.
3. **Re-medir el brillo sin re-apilar**: botón «Re-measure the brightness» en la
   pestaña Astrometría. Un worker (`StackRemeasureWorker`) lee el **par de stacks
   guardados** (el del objeto y el de estrellas), ejecuta la misma
   `photometry.measure_plate` con la receta que la pestaña Fotometría tiene
   **ahora**, pliega la nueva magnitud en el run y **reescribe solo las tarjetas
   de banda** del stack (`NS_MAG`/`NS_MAGSR`/…): los píxeles no se tocan y la
   posición y la detección quedan igual. Requiere que el run haya guardado el
   stack de estrellas (la casilla «keep the star stack»); si no, el botón lo dice
   en vez de fallar.
4. **Las dos marcas**: al cargar una placa que es un track & stack (`NS_STACK`
   presente), la **marca del objeto del proyecto se apaga** (el botón de la barra
   superior la reactiva si el observador la quiere). La posición que cuenta en un
   stack es la que el run midió.
5. **El PA**: se documenta tal cual (se mide y se muestra; el reporte no lo
   lleva). La mejora propuesta, **no implementada aquí**: realimentar el PA
   medido de la traza como semilla de una **segunda pasada** del apilado (o
   apretar el grid de PA y re-medir la traza), con lo que el objeto dejaría de
   salir alargado. Se deja fuera porque no es un cambio acotado: exige una pasada
   de apilado extra y validación contra datos reales, y el barrido ya incluye un
   candidato a ±4.5° que en un objeto de SNR ~9 no se distingue del ruido.

**Consecuencias**: el resumen del run y la nota ganan dos campos
(`n_comps_requested`, `comps_skipped`); la receta gana `report_mag`; el stack
puede reescribir su banda sin re-apilar; y una placa de stack ya no acumula dos
marcas. Nada de esto toca la medida: la astrometría publica su punto y su
magnitud como siempre, y el control de `report_mag` cambia lo que se **muestra**,
no lo que se **mide**.

**Alternativas**: (a) no mostrar la magnitud cuando el error es alto, descartado:
el número es útil con su causa; (b) un conmutador en la banda en vez de en la
receta, descartado: la banda es el resultado, la receta es la decisión; (c)
re-apilar siempre que cambie la receta, descartado por coste (450 fotogramas por
cada retoque); (d) usar el PA de la traza como PA de movimiento, descartado: la
traza es el **residuo** entre el movimiento real y el asumido, no el movimiento.

## English

**Context**: on a real track & stack of a faint NEO (450 frames, 4 s, measured
magnitude 19.32 with a **1.36 mag error**) four things came up that the observer
could neither understand nor fix from the interface, plus one about the PA:

1. **The 1.36 mag error had no explanation**: the zero point rested on **3
   comparison stars** (the run's own QC said "fewer than four stars"), but
   nothing said why the project's eight had become three. `core/photometry`
   already counts the drops per plate (off the plate, saturated, non-linear, no
   positive flux, no catalog value), but the run's summary did not carry them and
   the note only gave the number.
2. **What the band reports could not be chosen**: `chart_annotate.build_band`
   prefers the measurement when there is one and colours it by its error (red
   past 0.15, which was the case). The stack already stores `NS_MAGSR`
   (`measured` | `ephemeris`), but there was no control to change it: the only
   override was typing a magnitude by hand.
3. **The photometry recipe could not be applied after the stack**: the
   Photometry tab refuses to measure a track & stack (on the object's stack the
   stars are trails; on the star stack the object is a trail) and points to the
   Astrometry tab, but the recipe was captured **at run time**: changing the
   apertures, the sky or the comps meant re-stacking the 450 frames.
4. **Two blue marks looked like an error**: a track & stack carries its own
   measured position (the run's cross and the `ANNOTATE` circle), and on top of
   it the project's object mark was painted (a full-frame cross, at the plan's
   coordinates, not the measured ones). Both in the same colour, because the
   mark colour is the object type's own (NEO = blue), a few arcmin apart: it read
   as a bug.
5. **The PA**: it is measured in two places. The **velocity sweep** searches rate
   and PA (`sweep.best.pa`, stored in `astrometry_runs.pa_deg` and the header
   `NS_PA`); when its winner does not beat the ephemeris' own seed by more than
   three times the grid's scatter, the run **keeps the ephemeris'** and marks it
   `NS_MOT=eph` (the band paints it as a prediction). And the **object's shape**
   measures its trail's PA (`photometry.psf_elongation`, in `trail_pa_deg`),
   which the notes print. On the measured run the real trail was **PA 151.2°**
   while the stack was tracked with the **ephemeris' PA 148.9°** (~2.3° apart),
   which is why the object came out trailed **9.7 px** on its own stack: **we do
   measure the PA (the trail's), but we do not feed it back** to correct the
   stacking. The MPC report (80-column and ADES) carries no PA: the format has
   no field for the motion.

**Decision**: four changes, and the PA documented with its proposal.

1. **Comparison-star diagnostics**: the run **sums** each observation's
   `res.skipped` and carries it into the summary (`comps_skipped`,
   `n_comps_requested`), and the note says it in plain language: "the zero point
   rests on N of M comps (…), so the error is the honest consequence: check the
   sequence". Below four comps the warning is explicit: a large error stops
   looking like a bug and becomes a figure with a cause.
2. **`report_mag` in the recipe** (Photometry tab, "The photometry recipe"
   section): **measured** or **ephemeris**. It is part of the recipe because it
   decides what a reader sees over the image; the track & stack writes it into
   the stack's own header (`NS_MAGSR`), so a measurement not worth reporting (a
   zero point on too few comps, a trailed object) is replaced by the labelled
   `(eph)` figure **without hiding the measurement**, which stays in the run and
   in the astrometry point. The choice is saved and restored with the plate
   (ADR-047) and travels in the run's persisted summary.
3. **Re-measuring the brightness without re-stacking**: a "Re-measure the
   brightness" button in the Astrometry tab. A worker (`StackRemeasureWorker`)
   reads the **saved pair of stacks** (the object's and the star's), runs the same
   `photometry.measure_plate` with the recipe the Photometry tab holds **now**,
   folds the new magnitude into the run and **rewrites only the stack's band
   cards** (`NS_MAG`/`NS_MAGSR`/…): the pixels are untouched and the position and
   detection are unchanged. It requires the run to have kept the star stack (the
   "keep the star stack" box); if not, the button says so instead of failing.
4. **The two marks**: when a plate loads that is a track & stack (`NS_STACK`
   present), the **project's object mark is switched off** (the top-bar toggle
   brings it back if the observer wants it). The position that counts on a stack
   is the one the run measured.
5. **The PA**: documented as it is (measured and shown; the report carries none).
   The proposed improvement, **not implemented here**: feed the measured trail PA
   back as the seed of a **second stacking pass** (or tighten the PA grid and
   re-measure the trail), so the object stops coming out trailed. It is left out
   because it is not a bounded change: it needs an extra stacking pass and
   validation against real data, and the sweep already includes a ±4.5° candidate
   that, on an object of SNR ~9, is not distinguishable from the noise.

**Consequences**: the run's summary and note gain two fields
(`n_comps_requested`, `comps_skipped`); the recipe gains `report_mag`; a stack
can rewrite its band without re-stacking; and a stack plate no longer collects
two marks. None of this touches the measurement: the astrometry publishes its
point and its magnitude as always, and `report_mag` changes what is **shown**,
not what is **measured**.

**Alternatives**: (a) hide the magnitude when the error is large, rejected: the
number is useful with its cause; (b) a band switch instead of the recipe,
rejected: the band is the result, the recipe is the decision; (c) always
re-stacking when the recipe changes, rejected on cost (450 frames per tweak);
(d) using the trail's PA as the motion PA, rejected: the trail is the
**residual** between the real motion and the assumed one, not the motion.
