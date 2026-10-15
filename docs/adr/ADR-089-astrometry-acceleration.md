# ADR-089: Aceleración del apilado: registro en paralelo y backend GPU opcional

**Estado / Status**: Accepted · **Fecha / Date**: 2026-10-14

## Español

**Contexto**: la campaña de velocidad de ADR-062 (`docs/PLANS/astrometry-perf/`)
bajó el tiempo de pared del track & stack y **descartó el GPU**: tras paralelizar
el CPU x5-10, la ganancia marginal de una GPU era x1,5-2 a cambio de una
dependencia y empaquetado, y el suelo que no acelera (FITS, ASTAP, Find_Orb) ya
era el 30-40 %. Esta revisión **reabre esa parte** con medidas nuevas sobre una
máquina distinta (Ryzen 9 5950X de 16 núcleos contra una RTX 3090, 60 tomas de
2048²) y con una pregunta mejor: ¿dónde está el cuello de verdad? La respuesta
cambia la decisión:

- El **registro iba en serie**, frame a frame, y son ~25 s de una visita de 140.
  Paralelizarlo escala **solo x2,4** porque la etapa está **limitada por ancho de
  banda de memoria**, no por núcleos: incluso un `median` de numpy puro escala
  x4,6 sobre 16 hilos. Más hilos no dan más.
- El **warp y el combine** están limitados por lo mismo, y ahí el GPU sí marca la
  diferencia: su ancho de banda es un orden de magnitud mayor que el de la CPU.

Es decir: el GPU no se descarta por ser poco útil, se descarta (en 2026-10-05) por
no ser **la palanca del momento**. Con el CPU ya paralelizado, es la palanca que
queda.

**Decisión**:

1. **El registro recorre la secuencia en bloques** (`track_stack.register_sequence`):
   la estimación de cada frame es **independiente** (lee sus propios píxeles y los
   empareja contra la MISMA referencia), así que un bloque de frames se estima a
   la vez. La **puerta de confianza y el fallback siguen en serie y en orden**, de
   modo que la regla «hereda el transform de la anterior» significa lo mismo que
   cuando el bucle era de uno en uno. El bloque se siembra con el transform del
   bloque anterior, y eso es solo una **pista**: `estimate_transform` empareja con
   3 px de tolerancia y rechaza la semilla que no explique las estrellas, así que
   un re-apuntado dentro del bloque cuesta un voto, nunca una respuesta mala.
2. **El warp y el combine ganan una ruta GPU OPCIONAL** (`core/gpu.py`):
   **apagada por defecto**, **sin dependencia dura** (CuPy no entra en
   `requirements.txt`), y **ausente** en una máquina sin CuPy, sin tarjeta o con
   el driver roto, donde el camino numpy corre exactamente como antes. El
   interruptor es `astrometry_gpu` (Ajustes → Astrometría → Work).
3. **La paridad CPU/GPU se fija con un test** (`tests/unit/test_gpu.py`, se salta
   sin GPU): no puede ser bit a bit porque el GPU reduce en otro orden, así que se
   fija una tolerancia en ADU, medida en menos de un tercio de ADU sobre un cielo
   de mil (el `median` y el warp coinciden exactos; el `sigma` difiere 0,29 ADU
   como máximo).
4. **La ruta CPU sigue siendo la probada y el defecto.** El GPU es una carretera
   más rápida al mismo resultado, nunca un resultado distinto.
5. **La imagen fuente y las estrellas del registro van al dispositivo**
   (`gpu.frame_stars`): son el COSTE ENTERO de una estimación por toma y ahora
   las dos pagan (medido en un frame real de 2008²: 199 ms en CPU contra 18,4 ms
   en GPU, **x10,8**). La pieza que lo desbloqueó fue la **mediana por bloques**:
   el dispositivo recorría 3844 bloques uno a uno (693 ms) para un frame que no
   divide por el bloque, que es el caso real (2008 % 32 = 24). Ahora los bloques
   se **dispersan** en un array acolchado (NaN donde un bloque es una fila o
   columna más corta) y UN `nanmedian` los reduce: **4,2 ms, paridad max 0**,
   porque los bordes salen del linspace TRUNCADO, igual que en el CPU. La
   paridad del registro es **exacta** (las mismas 186/207 tomas y el mismo rms
   mediano).
6. **El warp y el combine se FUSIONAN en una sola pasada** (`gpu.stack_ram`): la
   pila deformada se construye y se reduce en el dispositivo, así que solo suben
   los fotogramas y baja una imagen. Es lo que quita el viaje de ida y vuelta de
   la pila entera (medido: `stack_group` sigma de x2,8 a **x4,0**).
   **El barrido de velocidad se queda en la CPU**: su recorte es pequeño y sus
   regiones ya están en RAM, y el coste por candidato de un viaje al dispositivo
   no compensa (medido: x0,9 a 2048², x0,6 a 1024²). El GPU paga donde el
   trabajo es grande y continuo, no en muchas re-apiladas pequeñas de los mismos
   píxeles.

**Lo medido** (207 tomas REALES de 2008², la visita 2025 FG18; CPU = 16 hilos):

| Etapa | CPU | GPU | Ganancia |
| --- | --- | --- | --- |
| Registro de la secuencia | 54,3 s | 7,7 s | **x7,1** |
| Pila base (recorte de la traza, 142²) | 0,7 s | 0,6 s | x1,2 |
| Barrido de velocidad (25 candidatos) | 2,3 s | 2,3 s | x1,0 (CPU) |
| Pilas por observación (2, frame completo) | 20,8 s | 4,5 s | **x4,6** |
| Medida (stack + por frame) | 4,5 s | 4,1 s | x1,1 |
| **Total de las etapas medidas** | **83,3 s** | **19,6 s** | **x4,25** |

Y el detalle por kernel, sobre el frame real de 2008²: la imagen fuente y las
estrellas del registro **x10,8** (199 → 18,4 ms); y en el banco sintético de
2048², el `stack_group` fusionado x4,0 (7,9 → 2,0 s) y la correlación de fase
x34 (320 → 9,3 ms).

El registro baja de 54,3 s a **7,7 s** con la mediana por bloques en un solo
kernel, y las pilas por observación, que son a frame completo, van a **x4,6**.
**El barrido se queda en la CPU** (x1,0): su recorte es pequeño y sus regiones ya
están en RAM.

**Alternativas**:

- **Procesos en vez de hilos** para el registro: descartado. Windows no tiene
  fork, y el proyecto ya eligió hilos por eso (`core/parallel.py`).
- **OpenCL en vez de CUDA**: descartado **por ahora**. OpenCL es más portable
  (AMD, Intel, Apple Silicon: es lo que usa Tycho-Tracker), pero en NVIDIA rinde
  por debajo de CUDA y añade complejidad y dependencia del driver. El backend está
  aislado en un módulo para que añadir OpenCL sea incremental el día que se
  exporte o que la búsqueda a ciegas entre en el motor.
- **CuPy como dependencia dura**: descartado. La app tiene que instalar y correr
  igual en una máquina sin GPU.

**Consecuencias**: nuevo módulo `core/gpu.py`; un test que se salta sin GPU; un
ajuste nuevo (`astrometry_gpu`, apagado por defecto); el registro reescrito en
bloques; y el banco `benchmarks/track_stack_bench.py` gana la ruta GPU. ADR-062
**no se revoca**: el tracking directo y el alcance siguen igual, y esta es una
ruta de velocidad, no un requisito del algoritmo.

**Nota (2026-10-14): el clip de CPU, medido y no tocado.** Con el GPU encendido
el recorte sigma corre en el dispositivo, así que esta palanca es para quien no
tenga tarjeta. El recorte es **median-bound** (un solo `nanmedian` de
(60, 2048²) cuesta ~2,2 s y hay cuatro por recorte), y se probaron dos vías:

- **Ordenar una copia transpuesta** (eje de muestras contiguo): el `sort` en sí
  es x5 más rápido, pero la copia añade un cubo entero de tráfico y el recorte
  corre sobre **columnas en paralelo**, donde ese tráfico contiende entre los
  hilos. Medido en (60, 2048²): el recorte serial 14120 → 12249 ms (x1,15) pero
  el `combine` paralelo 5213 → 5987 ms (**x0,87**). **Rechazado**, y queda
  escrito en el comentario de `outliers.nanmedian_axis0`.
- **Menos iteraciones**: bajar de 3 a 2 (el defecto actual) es **x1,40** en el
  `combine` (5245 → 3750 ms) y cambia la imagen menos de 1 ADU en el caso
  sintético, pero el defecto de 3 no tiene una medida publicada y la profundidad
  es territorio de **ADR-068**; cambiarlo pide el banco de inyección, no un
  atajo. Queda como decisión **medida y no adoptada**.
- La escala por **media y desviación** en vez de MAD es x1,95 pero deja de ser
  robusta, que es justo para lo que existe el recorte. Descartado.

**Nota (2026-10-14): medir por frame y las ventanas de comparsas, medido.** El
punto 4 pedía paralelizar las dos, y **ninguna de las dos gana**:

- **`measure_frames` en paralelo**: los frames son independientes y la
  combinación no depende del orden, pero el trabajo por frame es una caja
  pequeña y un centroide pequeño y el coste de los hilos se lo come. Medido en
  120 × 1024²: 2824 ms en serie contra 5043 ms a 16 hilos (**x0,56**).
  **Rechazado**, y escrito en el comentario de `measure_frames`.
- **Ventanas de comparsas en paralelo**: cada `stack_group` ya usa los núcleos,
  así que el bucle exterior solo los sobre-suscribe (**x1,08**). **Rechazado**.
- **El lever real es leer cada frame UNA vez**: cada comparsa relee los MISMOS
  ficheros y la lectura es el coste entero de la etapa (medido: 120 lecturas de
  caja 118 ms contra 120 lecturas del frame entero 283 ms, y un juego de doce
  comparsas paga las lecturas doce veces). Un caché acotado que lee cada frame
  una vez y sirve todas las cajas desde memoria baja las ventanas de **2954 a
  699 ms (x4,2)**, con paridad exacta (probada, con `BZERO`/`BSCALE`).

**Nota (2026-10-14): el barrido de velocidad, medido sobre 539 tomas reales.**
El barrido usaba el recorte del TRAZO (para un objeto a 17″/min, 1084²) y lo
re-apilaba entero para cada uno de los 25 candidatos: medido, **207 s**. Pero el
score del barrido solo lee el entorno de `q` (apertura r=4, anillo r=8–12,
redondez r=4), así que basta una ventana alrededor de `q`: **128²**. Con ella el
barrido baja a **6,1 s (x34)**, con el MISMO rate, PA y score.

Para que el score fuera exacto hubo que arreglar una dependencia escondida: la
**redondez** tomaba su cielo de TODO el recorte (`_local_sky(stack, ~win)`), así
que el mismo objeto puntuaba distinto según el tamaño de la caja (medido: 46,1
en el trazo contra 47,2 en 128², que habría movido la puerta de significancia).
Ahora el cielo sale de un **anillo fijo** alrededor de la fuente
(`_ROUNDNESS_SKY_PX`), y el score es idéntico en cualquier tamaño (medido: 46,93
en 64², 128², 256² y 495²).

**Nota (2026-10-14): el tope de RAM del apilado, medido.** El presupuesto que
decide RAM o franjas es una constante FIJA (`MEMORY_BUDGET_BYTES`, 2 GiB). Se
probó a derivarlo de la memoria libre (media de la RAM disponible, con suelo y
techo, como hace el número de hilos) para no mandar a franjas una pila de 4,2 GiB
en una máquina de 125 GB, y **se rechazó al medirlo**: las franjas son MÁS
RÁPIDAS. Medido en una visita de 539 tomas, una pila a frame completo de 270
tomas (4,2 GiB): CPU 37,8 s en franjas contra 42,5 s en RAM; GPU 11,2 s en
franjas contra una caída por falta de memoria en RAM (los intermedios del
recorte son ~5× la pila, así que 4,5 GiB de pila piden ~20 GiB de dispositivo).
El tope fijo fuerza la ruta buena.

**Revisión (2026-10-15): la ruta GPU pasa a estar ENCENDIDA por defecto, con
OpenCL.** El punto 2 la dejaba apagada «porque no es necesaria para llegar a la
respuesta». La razón sigue siendo cierta, pero el coste de tenerla apagada se
midió y es alto: con el combine escalable (ADR-091, nota del 2026-10-15) una
pila base de 539 × 1024² pasa de 6,3 s en CPU a **1,2 s**, y las pilas por
observación y el star stack también. Como OpenCL **viaja con la app** (no hay
nada que instalar), la máquina sin tarjeta no paga nada (el sondeo contesta
`False` y el camino numpy corre igual) y la paridad está fijada por test (misma
respuesta dentro de una fracción de ADU), el defecto pasa a ser **encendido y
con OpenCL**. CUDA sigue siendo una vía **manual** (CuPy, NVIDIA solo) y `auto`
sigue existiendo para quien tenga las dos y quiera compararlas. El punto 4 (la
CPU es la ruta probada y el defecto *de resultado*) no cambia: la GPU es una
carretera más rápida a la MISMA respuesta, y la nota del run dice qué dispositivo
la hizo.

## English

**Context**: ADR-062's speed campaign (`docs/PLANS/astrometry-perf/`) cut the
track & stack wall clock and **ruled the GPU out**: after parallelising the CPU
x5-10, a GPU's marginal gain was x1.5-2 in exchange for a dependency and
packaging, and the floor it cannot accelerate (FITS, ASTAP, Find_Orb) was already
30-40 %. This revision **reopens that part** with new measurements on a different
machine (16-core Ryzen 9 5950X against an RTX 3090, 60 frames of 2048²) and a
better question: where is the bottleneck really? The answer changes the decision:

- The **registration walked the frames one at a time**, and that is ~25 s of a
  140-frame visit. Parallelising it scales **only x2.4**, because the stage is
  **memory-bandwidth-bound**, not core-bound: even a PURE numpy median scales
  x4.6 over 16 threads. More threads buy nothing.
- The **warp and the combine** are bound by the same thing, and there a GPU does
  make the difference: its bandwidth is an order of magnitude above the CPU's.

The GPU was not ruled out for being useless: it was ruled out (on 2026-10-05) for
not being **the lever of the moment**. With the CPU already parallelised, it is
the lever that is left.

**Decision**:

1. **The registration walks the sequence in chunks**
   (`track_stack.register_sequence`): each frame's estimate is **independent** (it
   reads its own pixels and pairs them against the SAME reference), so a chunk of
   frames is estimated at once. The **trust gate and the fallback stay serial and
   in order**, so the "inherits the previous transform" rule means what it did
   when the loop was one frame at a time. The chunk is seeded with the previous
   chunk's transform, and that is a **hint** only: `estimate_transform` pairs with
   a 3 px tolerance and rejects a seed that does not explain the stars, so a
   re-point inside a chunk costs a vote, never a wrong answer.
2. **The warp and the combine gain an OPTIONAL GPU path** (`core/gpu.py`): **off
   by default**, **no hard dependency** (CuPy does not enter `requirements.txt`),
   and **absent** on a machine without CuPy, without a card or with a broken
   driver, where the numpy path runs exactly as before. The switch is
   `astrometry_gpu` (Settings → Astrometry → Work).
3. **The CPU/GPU parity is pinned by a test** (`tests/unit/test_gpu.py`, skipped
   without a GPU): it cannot be bit-identical because a GPU reduces in a different
   order, so the test pins an ADU tolerance, measured under a third of an ADU on a
   sky of a thousand (the `median` and the warp match exactly; the `sigma` differs
   by at most 0.29 ADU).
4. **The CPU path stays the tested one and the default.** The GPU is a faster road
   to the same answer, never a different answer.
5. **The registration's source image and stars both go to the device**
   (`gpu.frame_stars`): they are the WHOLE cost of a per-frame estimate and both
   now pay (measured on a real 2008² frame: 199 ms on the CPU against 18.4 ms on
   the device, **x10.8**). What unlocked it was the **block median**: the device
   walked 3844 blocks one kernel at a time (693 ms) for a frame that does not
   divide by the block, which is the real case (2008 % 32 = 24). The blocks are
   now **scattered** into a padded array (NaN where a block is one row or column
   shorter) and ONE `nanmedian` reduces them: **4.2 ms, parity max 0**, because
   the edges come from the TRUNCATED linspace, as on the CPU. The registration's
   parity is **exact** (the same 186/207 frames and the same median rms).
6. **The warp and the combine are FUSED into one pass** (`gpu.stack_ram`): the
   warped stack is built and reduced on the device, so only the frames go up and
   one image comes down. That is what removes the round trip of the whole stack
   (measured: `stack_group` sigma from x2.8 to **x4.0**). **The velocity sweep
   stays on the CPU**: its cutout is small and its regions are already in RAM,
   and the per-candidate cost of a trip to the device does not pay (measured:
   x0.9 at 2048², x0.6 at 1024²). The GPU pays where the work is big and
   continuous, not on many small re-stacks of the same pixels.

**What was measured** (60 frames of 2048²; CPU = 16 threads):

**What was measured** (207 REAL frames of 2008², the 2025 FG18 visit; CPU = 16
threads):

| Stage | CPU | GPU | Gain |
| --- | --- | --- | --- |
| Sequence registration | 54.3 s | 7.7 s | **x7.1** |
| Base stack (trail cutout, 142²) | 0.7 s | 0.6 s | x1.2 |
| Velocity sweep (25 candidates) | 2.3 s | 2.3 s | x1.0 (CPU) |
| Per-observation stacks (2, whole frame) | 20.8 s | 4.5 s | **x4.6** |
| Measurement (stack + per frame) | 4.5 s | 4.1 s | x1.1 |
| **Total of the measured stages** | **83.3 s** | **19.6 s** | **x4.25** |

And the per-kernel detail, on the real 2008² frame: the registration's source
image and stars **x10.8** (199 -> 18.4 ms); and on the synthetic 2048² bench, the
fused `stack_group` x4.0 (7.9 -> 2.0 s) and the phase correlation x34 (320 ->
9.3 ms).

The registration drops from 54.3 s to **7.7 s** with the block median in one
kernel, and the per-observation stacks, which are whole-frame, reach **x4.6**.
**The sweep stays on the CPU** (x1.0): its cutout is small and its regions are
already in RAM.

**Alternatives**:

- **Processes instead of threads** for the registration: rejected. Windows has no
  fork, and the project already chose threads for that reason
  (`core/parallel.py`).
- **OpenCL instead of CUDA**: rejected **for now**. OpenCL is more portable (AMD,
  Intel, Apple Silicon: it is what Tycho-Tracker uses), but on NVIDIA it performs
  below CUDA and adds complexity and driver dependence. The backend is isolated in
  one module so adding OpenCL is incremental the day it is exported or the blind
  search enters the engine.
- **CuPy as a hard dependency**: rejected. The app must install and run the same
  on a machine without a GPU.

**Consequences**: new module `core/gpu.py`; a test that skips without a GPU; a new
setting (`astrometry_gpu`, off by default); the registration rewritten in chunks;
and `benchmarks/track_stack_bench.py` gains the GPU path. ADR-062 is **not
revoked**: the direct tracking and the scope stay the same, and this is a speed
road, not a requirement of the algorithm.

**Note (2026-10-14): the CPU clip, measured and left alone.** With the GPU on,
the sigma clip runs on the device, so this lever is for whoever has no card. The
clip is **median-bound** (a single `nanmedian` of (60, 2048²) costs ~2.2 s and
there are four per clip), and two roads were tried:

- **Sorting a transposed copy** (sample axis contiguous): the sort itself is x5
  faster, but the copy adds a whole cube of traffic and the clip runs on
  **column slices in parallel**, where that traffic contends across the threads.
  Measured on (60, 2048²): the serial clip 14120 -> 12249 ms (x1.15) but the
  parallel combine 5213 -> 5987 ms (**x0.87**). **Rejected**, and written down in
  the comment of `outliers.nanmedian_axis0`.
- **Fewer iterations**: dropping from 3 to 2 (the current default) is **x1.40**
  on the combine (5245 -> 3750 ms) and changes the image by under 1 ADU in the
  synthetic case, but the default of 3 has no published measurement and depth is
  **ADR-068** territory; changing it asks for the injection bench, not a
  shortcut. It stays a decision **measured and not taken**.
- A **mean-and-standard-deviation** scale instead of MAD is x1.95 but stops being
  robust, which is exactly what the clip exists for. Rejected.

**Note (2026-10-14): measuring per frame and the comps' windows, measured.**
Point 4 asked to parallelise both, and **neither one wins**:

- **`measure_frames` in parallel**: the frames are independent and the
  combination is order-free, but the per-frame work is a small box and a small
  centroid and the thread overhead eats it. Measured on 120 x 1024^2: 2824 ms
  serial against 5043 ms over 16 threads (**x0.56**). **Rejected**, and written
  into the comment of `measure_frames`.
- **Comps' windows in parallel**: each `stack_group` already uses the cores, so
  the outer loop only oversubscribes them (**x1.08**). **Rejected**.
- **The real lever is reading each frame ONCE**: every comp re-reads the SAME
  files and the reads are the whole cost of the stage (measured: 120 box reads
  118 ms against 120 whole-frame reads 283 ms, and a twelve-comp set pays the
  reads twelve times). A bounded cache that reads each frame once and serves
  every box from memory takes the windows from **2954 to 699 ms (x4.2)**, with
  exact parity (tested, with `BZERO`/`BSCALE`).

**Note (2026-10-14): the velocity sweep, measured on 539 real frames.** The
sweep used the TRAIL cutout (1084² for a 17"/min object) and re-stacked all of
it for every one of the 25 candidates: measured, **207 s**. But the sweep's
score only reads q's neighbourhood (an r=4 aperture, an r=8-12 sky annulus and
an r=4 roundness window), so a window around q is enough: **128²**. With it the
sweep drops to **6.1 s (x34)**, with the SAME rate, PA and score.

Making the score exact needed fixing a hidden dependence: the **roundness** took
its sky from the WHOLE box (`_local_sky(stack, ~win)`), so the same source
scored differently depending on how big the box was (measured: 46.1 on the trail
cutout against 47.2 in a 128² window, which would have moved the significance
gate). The sky now comes from a **fixed ring** around the source
(`_ROUNDNESS_SKY_PX`), and the score is identical at every size (measured: 46.93
in 64², 128², 256² and 495²).

**Note (2026-10-14): the stacking's RAM cap, measured.** The budget that decides
RAM or strips is a FIXED constant (`MEMORY_BUDGET_BYTES`, 2 GiB). Deriving it
from the free memory (half the available RAM, with a floor and a ceiling, as the
worker count does) was tried, to stop a 4.2 GiB stack from going to strips on a
125 GB machine, and it was REJECTED by the measurement: the strips are FASTER.
Measured on a 539-frame visit, one 270-frame full-frame stack (4.2 GiB): CPU
37.8 s in strips against 42.5 s in RAM; GPU 11.2 s in strips against an
out-of-memory fallback in RAM (the combine's intermediates are ~5x the stack, so
4.5 GiB of stack asks for ~20 GiB of device). The fixed cap forces the good
path.

**Revision (2026-10-15): the GPU path is ON by default, with OpenCL.** Point 2
left it off "because it is not needed to reach the answer". That reason still
holds, but the cost of leaving it off was measured and it is high: with the
scalable combine (ADR-091, note of 2026-10-15) a 539 x 1024² base stack goes
from 6.3 s on the CPU to **1.2 s**, and the per-observation stacks and the star
stack with it. Since OpenCL **travels with the app** (nothing to install), a
machine with no card pays nothing (the probe answers `False` and the numpy path
runs the same) and the parity is pinned by a test (the same answer within a
fraction of an ADU), the default becomes **on and with OpenCL**. CUDA stays a
**manual** road (CuPy, NVIDIA only) and `auto` still exists for whoever has both
and wants to compare them. Point 4 (the CPU is the tested path and the default
*answer*) does not change: the GPU is a faster road to the SAME answer, and the
run's note says which device did the work.
