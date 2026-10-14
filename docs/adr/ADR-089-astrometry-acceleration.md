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

**Lo medido** (60 tomas de 2048²; CPU = 16 hilos):

| Etapa | CPU | GPU | Ganancia |
| --- | --- | --- | --- |
| Registro de la secuencia (bucle) | 10,5 s | 4,4 s (bloques) | x2,4 |
| `_warp_batch` (frame completo) | 1,28 s | 0,75 s | x1,7 |
| `combine` sigma (recorte 3 iter) | 5,56 s | 1,05 s | x5,3 |
| `stack_group` sigma, extremo a extremo | 7,06 s | 2,55 s | x2,8 |
| Correlación de fase (una toma) | 320 ms | 9,3 ms | x34 |

El warp del GPU está limitado por la lectura de las tomas y el viaje por PCIe, no
por el kernel; el combine es donde gana. El registro no lo toca esta revisión (su
coste está en `source_image` y `detect_stars`, también limitados por memoria y
candidatos a un kernel propio más adelante).

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

**What was measured** (60 frames of 2048²; CPU = 16 threads):

| Stage | CPU | GPU | Gain |
| --- | --- | --- | --- |
| Sequence registration (loop) | 10.5 s | 4.4 s (chunks) | x2.4 |
| `_warp_batch` (whole frame) | 1.28 s | 0.75 s | x1.7 |
| `combine` sigma (clip, 3 iter) | 5.56 s | 1.05 s | x5.3 |
| `stack_group` sigma, end to end | 7.06 s | 2.55 s | x2.8 |
| Phase correlation (one frame) | 320 ms | 9.3 ms | x34 |

The GPU warp is bound by reading the frames and the PCIe trip, not by the kernel;
the combine is where it wins. The registration is untouched by this revision (its
cost is in `source_image` and `detect_stars`, also memory-bound and candidates for
a kernel of their own later).

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
