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

**Review (2026-10-14, the run groups its frames, puts the guider back, says where it is and stops at once)**: four gaps a real run (ZTF10Gh) exposed.

1. **The frames were not grouped.** The ADR claimed the re-point's time gap would separate the observations "on its own", but nothing implemented it: the editor split the frames into an EQUAL number of groups from a manual count, so the observer had to guess N and the split could not match. Now the run **records a manifest** (one entry per observation: the frame count and its wall-clock window) and **copies each observation's frames into its own subfolder** (inside the capture folder when NightScribe can see it, inside the project otherwise). The editor groups by the subfolders first, then by the manifest (by count, no clock to reconcile between two machines), then by the re-point gap, and the manual count last. The count is **prefilled** from the rule that won and the tooltip says which one it was; typing another number takes over, because a grouping is a **suggestion, not a cage** (forcing a number on a sequence the observer knows was wrong).
2. **The guider was left stopped.** A slew (the astrometric goto) stops the guider and the run never put it back, so every observation after the first was captured unguided. The loop now has a **guide step** before each capture: connect the guider when the backend lets us (CCDciel; NINA manages its own), start it **using the stored calibration** (a fresh calibration is a separate, opt-in command: "calibrate only if needed"), and wait until it reports guiding. A guide failure is **said** and the run goes on (short exposures are often usable unguided). Two Settings checkboxes (put the guider back, calibrate first) drive it.
3. **No feedback.** The run only wrote one line to the status bar. It now has a **progress bar and a line** in the Capture step: which observation (i of N), which frame (c of f), the remaining exposure and the percentage of the whole run, from CCDciel's `status`→`capture` section (current/total, remaining, HFD, drift) and NINA's `IsExposing`.
4. **Stop looked dead.** The button toggled and set a cancel flag, but the loop only read it between steps, and a step can be a blocking astrometric goto of up to two minutes. The goto is now **cancellable**: CCDciel's async job is polled with the flag (and the mount aborted on cancel), and NINA's blocking call runs in a helper thread so a Stop can abort the slew and unblock it. Stop also stops the capture at once.

**Consequences**: `core/follow.FollowRun` gains `guide`, `capture_progress`, `group_observation` and a `manifest`; `core/follow` gains the grouping helpers (`group_by_folder`, `group_by_manifest`, `group_by_gaps`, `resolve_groups`); `gui/workers.FollowWorker` gains the cancellable center, the guide step and the subfolder copy; `gui/main_window` gains the progress area and stores the manifest in the project context (`follow_runs`); both clients gain `guider_state`/`guider_connect`/`guider_start`/`guider_stop`, `capture_dir` and `capture_progress`; `config` gains `follow_guide` and `follow_calibrate`; the editor groups by the run's manifest (`TrackStackWorker(groups=...)`).

**Revisión (2026-10-14, el run agrupa sus tomas, repone el guiado, dice por dónde va y para al momento)**: cuatro huecos que destapó un run real (ZTF10Gh).

1. **Las tomas no se agrupaban.** El ADR decía que el hueco temporal del re-apuntado separaría las observaciones «solo», pero nada lo implementaba: el editor partía las tomas en un número IGUAL de grupos a partir de un recuento a mano, así que el observador tenía que adivinar N y el reparto no podía cuadrar. Ahora el run **registra un manifiesto** (una entrada por observación: el número de tomas y su ventana de reloj) y **copia las tomas de cada observación a su propia subcarpeta** (dentro de la carpeta de captura cuando NightScribe la ve, dentro del proyecto si no). El editor agrupa por las subcarpetas primero, luego por el manifiesto (por número, sin relojes de dos máquinas que casar), luego por el hueco del re-apuntado, y el recuento a mano al final. El contador se **precarga** con la regla que ganó y el tooltip dice cuál fue; si escribes otro número, gana el tuyo, porque una agrupación es una **sugerencia, no una jaula** (imponer un número en una secuencia que el observador conoce era un error).
2. **El guiado se quedaba parado.** Un slew (el goto astrométrico) corta el guiado y el run nunca lo reponía, así que cada observación después de la primera se capturaba sin guiar. El bucle tiene ahora un **paso de guiado** antes de cada captura: conecta el guiado cuando el backend lo permite (CCDciel; NINA gestiona el suyo), lo arranca **con la calibración guardada** (calibrar de nuevo es un comando aparte y opcional: «calibrar solo si hace falta») y espera a que diga que guía. Un fallo del guiado se **dice** y el run sigue (las exposiciones cortas suelen servir sin guiar). Dos casillas en Configuración (repone el guiado, calibra primero) lo gobiernan.
3. **Sin feedback.** El run solo escribía una línea en la barra de estado. Ahora tiene una **barra de progreso y una línea** en el paso Captura: qué observación (i de N), qué toma (c de f), la exposición restante y el porcentaje del run completo, desde la sección `capture` del `status` de CCDciel (current/total, restante, HFD, drift) y el `IsExposing` de NINA.
4. **El Stop parecía muerto.** El botón alternaba y ponía el flag de cancelación, pero el bucle solo lo leía entre pasos, y un paso puede ser un goto astrométrico bloqueante de hasta dos minutos. El goto es ahora **cancelable**: el trabajo asíncrono de CCDciel se sondea con el flag (y la montura se aborta al cancelar), y la llamada bloqueante de NINA corre en un hilo auxiliar para que un Stop pueda abortar el slew y desbloquearla. El Stop además para la captura al momento.

**Consecuencias**: `core/follow.FollowRun` gana `guide`, `capture_progress`, `group_observation` y un `manifest`; `core/follow` gana los ayudantes de agrupación (`group_by_folder`, `group_by_manifest`, `group_by_gaps`, `resolve_groups`); `gui/workers.FollowWorker` gana el centrado cancelable, el paso de guiado y la copia a subcarpetas; `gui/main_window` gana el área de progreso y guarda el manifiesto en el contexto del proyecto (`follow_runs`); los dos clientes ganan `guider_state`/`guider_connect`/`guider_start`/`guider_stop`, `capture_dir` y `capture_progress`; `config` gana `follow_guide` y `follow_calibrate`; el editor agrupa por el manifiesto del run (`TrackStackWorker(groups=...)`).
