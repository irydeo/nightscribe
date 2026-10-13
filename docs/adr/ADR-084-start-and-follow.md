# ADR-084: Start and follow (run dirigido de N observaciones de un objeto que se mueve)

**Estado / Status**: Accepted · **Fecha / Date**: 2026-10-13

## Español

**Contexto**: un objeto que se mueve se sale del campo de la cámara. La receta
de captura (ADR-083) ya acota el número de tomas de UNA observación al cruce
del campo, pero quien quiera integrar más tiene que re-apuntar a mano cada vez:
esperar a que el objeto llegue al borde, volver a centrarlo, disparar otra
tanda. En una noche larga con un NEO rápido eso es decenas de veces, y cada
descuido deja media serie sin el objeto. El nombre de la técnica es el que usa
el software comercial: CCDciel lo llama «recenter» («Automatically recenter a
target that drifts during a sequence») y el disparador de NINA es «Center After
Drift». La diferencia es que aquí el re-centrado es sobre la **efemérides
actualizada** del objeto, no sobre unas coordenadas fijas, porque el objeto se
mueve de verdad (en vigilancia espacial, un «stare-and-repoint»).

**Decisión**: un run dirigido, `core/follow.py` + un worker de GUI, con estas
piezas.

1. **Plan puro** (`follow.plan_run`): a partir de «N observaciones» devuelve
   el número de tomas por observación (el **cruce del campo** que ya calcula
   `core/capture_recipe`), la exposición, el tiempo por toma (lectura/descarga
   + asentamiento, `exposure.frame_overhead_s`), el coste de cada re-centrado
   (`follow_s`, config, por defecto 60 s: slew + resolución + corrección +
   asentamiento), el total y si cabe en la **ventana de visibilidad**. Avisa de
   `no_window`, `does_not_fit`, `not_moving` (un objeto fijo no cruza el campo)
   y `no_crossing` (sin preset de cámara o sin velocidad no se pudo acotar).
   El número se acota a 1..500 (un error de tecleo no parkea la montura una
   semana).
2. **Bucle** (`follow.FollowRun`), con TODOS los efectos inyectados
   (resolver la posición, centrar, empujar el plan, disparar, leer si captura,
   parar, cancelar, reloj y sueño), igual que `core/live.py`. Para cada
   observación: resolver la posición **actual** → centrar con el goto
   astrométrico → empujar el plan de esa tanda → capturar → esperar el fin
   (sondeo de `capturing` con la duración prevista como respaldo) → siguiente.
   Paradas honestas: N alcanzado, cancelación, o fallo (sin posición).
3. **Detección del borde en bucle ABIERTO**: conocemos la velocidad y el campo,
   así que cuando la tanda termina el objeto está, por construcción, cerca del
   borde. Resolver cada fotograma para medir el desplazamiento real es una
   mejora posterior, más pesada.
4. **GUI**: botón **«Iniciar y seguir…»** en el paso Capture (solo objetos en
   movimiento y con conexión). Pide el número de observaciones, muestra los
   números y el total antes de empezar (y si no cabe en la ventana), y el botón
   pasa a **«Parar seguimiento»** mientras corre. Un `FollowWorker` (QThread)
   lleva el bucle fuera del hilo de la GUI; mientras corre se **pausa el sondeo
   del panel** (`_ccd_timer`) para que dos workers no hablen al mismo servidor a
   la vez.
5. **Observaciones separadas**: cada re-centrado abre una **tanda**; el hueco
   temporal del re-centrado hace que el agrupado por tiempo del editor FITS las
   separe solas, sin tocar el OBJNAME (que debe seguir limpio para el MPC), así
   que más adelante se podrán tratar como observaciones distintas.

**Consecuencias**: nuevo `core/follow.py`, `FollowWorker` en
`gui/workers.py`, un botón y sus slots en `gui/main_window.py`, la clave
`follow_s` en `config.py` y `explain.FOLLOW` (ADR-058). El goto
astrométrico necesita un solver configurado; sin él, el bucle no puede centrar.
**NINA/PINS** limita: su captura es un *snapshot* de un fotograma (ADR-081), así
que hoy cada «observación» sería 1 toma salvo cargar la secuencia nativa; en
**CCDciel** el recuento se respeta y el bucle funciona completo. Un meridian
flip a mitad de bucle se re-centra después; no se fuerza.

**Alternativas**: (a) resolver cada fotograma y medir el desplazamiento real
(bucle cerrado), descartado por coste: el bucle abierto por tiempo usa lo que ya
calculamos y no pesa; (b) dejar que la montura siga a la tasa del objeto
(«non-sidereal tracking»), descartado como sustituto: muchos monturas amateur no
la soportan y la tasa de un NEO cambia rápido; (c) exportar una secuencia con N
re-apuntados al software y dejarlo a él, descartado: ni CCDciel ni NINA
re-centran sobre una efemérides que se actualiza sola, y perdemos el control del
presupuesto y del Stop.

## English

**Context**: a moving object leaves the camera's field. The capture recipe
(ADR-083) already bounds the frame count of ONE observation to the field
crossing, but anyone wanting more integration has to re-point by hand each
time: wait for the object to reach the edge, center it again, fire another
batch. On a long night with a fast NEO that is dozens of times, and every
lapse leaves half a run without the object. The technique's name is the one the
commercial software uses: CCDciel calls it "recenter" ("Automatically recenter
a target that drifts during a sequence") and NINA's trigger is "Center After
Drift". The difference is that here the recenter is onto the object's **updated
ephemeris**, not fixed coordinates, because the object really moves (in space
surveillance, a "stare-and-repoint").

**Decision**: a driven run, `core/follow.py` + a GUI worker, with these
pieces.

1. **Pure plan** (`follow.plan_run`): from "N observations" it returns the
   frames per observation (the **field crossing** `core/capture_recipe` already
   computes), the exposure, the per-frame time (readout/download + settle,
   `exposure.frame_overhead_s`), the cost of each re-center (`follow_s`,
   config, default 60 s: slew + solve + correct + settle), the total and
   whether it fits the **visibility window**. It warns about `no_window`,
   `does_not_fit`, `not_moving` (a fixed object does not cross the field) and
   `no_crossing` (without a camera preset or a rate the size could not be
   bounded). The number is clamped to 1..500 (a typo does not park the mount
   for a week).
2. **Loop** (`follow.FollowRun`), with EVERY effect injected (resolve the
   position, center, push the plan, start, read whether it captures, stop,
   cancel, clock and sleep), exactly like `core/live.py`. For each observation:
   resolve the **current** position → center with the astrometric goto → push
   that batch's plan → capture → wait for the end (poll `capturing` with the
   planned duration as the fallback) → next. Honest stops: N reached, cancel,
   or failure (no position).
3. **Edge detection is OPEN LOOP**: we know the rate and the field, so when a
   batch ends the object is, by construction, near the edge. Solving every
   frame to measure the real offset is a heavier, later refinement.
4. **GUI**: an **"Start and follow…"** button in the Capture step (moving objects
   only, and connected). It asks for the number of observations, shows the
   numbers and the total before starting (and whether it fits the window), and
   the button becomes **"Stop following"** while it runs. A `FollowWorker`
   (QThread) drives the loop off the GUI thread; while it runs the panel's
   **dashboard poll is paused** (`_ccd_timer`) so two workers never talk to the
   same server at once.
5. **Separate observations**: each re-center opens a **batch**; the time gap of
   the re-center makes the FITS editor's time grouping separate them on its
   own, without touching OBJNAME (which must stay clean for the MPC), so they
   can be treated as separate observations later.

**Consequences**: a new `core/follow.py`, a `FollowWorker` in
`gui/workers.py`, a button and its slots in `gui/main_window.py`, the
`follow_s` key in `config.py` and `explain.FOLLOW` (ADR-058). The
astrometric goto needs a configured solver; without it the loop cannot center.
**NINA/PINS** limits: its capture is a one-frame snapshot (ADR-081), so today
each "observation" would be 1 frame unless the native sequence is loaded; in
**CCDciel** the count is honoured and the loop works fully. A meridian flip
mid-loop is re-centered afterwards; it is not forced.

**Alternatives**: (a) solving every frame and measuring the real offset (closed
loop), rejected on cost: the time-based open loop uses what we already compute
and is cheap; (b) letting the mount track at the object's rate ("non-sidereal
tracking"), rejected as a substitute: many amateur mounts do not support it and
an NEO's rate changes fast; (c) exporting a sequence with N re-points to the
software and letting it do it, rejected: neither CCDciel nor NINA re-centers
onto a self-updating ephemeris, and we would lose the budget and the Stop.

**Review (2026-10-13, the run does the observer's numbers)**: `plan_run` used the recipe's suggestion for the frames and the exposure, so a frame count the observer had typed in the Plan step was ignored. It now takes `frames`/`exposure_s` as arguments and the Capture step passes the **Frames** and **Exposure** boxes (the saved plan is the fallback when the step is not built), so the run captures what was asked. When the observer's frame count is more than fits before the object reaches the edge of the field, the number is **honoured** (they may want a longer observation) and the run **says** it (`exceeds_crossing`, with the fitting count), instead of silently clipping it.

**Revisión (2026-10-13, el run hace los números del observador)**: `plan_run` usaba la sugerencia de la receta para las tomas y la exposición, así que un recuento que el observador hubiera escrito en el paso Plan se ignoraba. Ahora recibe `frames`/`exposure_s` como argumentos y el paso Captura le pasa los campos **Frames** y **Exposure** (el plan guardado es el respaldo cuando el paso no está construido), de modo que el run captura lo que se pidió. Cuando el número de tomas del observador es más de las que caben antes de que el objeto llegue al borde del campo, el número se **respeta** (puede querer una observación más larga) y el run lo **dice** (`exceeds_crossing`, con el recuento que cabe), en vez de recortarlo en silencio.
