# ADR-091: OpenCL «de serie»: el backend portable de la ruta GPU

**Estado / Status**: Accepted · **Fecha / Date**: 2026-10-14

## Español

**Contexto**: el ADR-089 dejó OpenCL fuera «por ahora» y aisló la ruta GPU en un
módulo para que añadirlo fuera incremental el día que se exportara o que la
búsqueda a ciegas entrara en el motor. Ese día es hoy, y con una medida que
cambia el tono: OpenCL **no es más lento** que CuPy. Medido en la misma máquina
(RTX 3090, 60 tomas de 2048²) con kernels escritos a mano
(`tools/bench/bench_opencl.py`), el warp va a 0,34× el tiempo de CuPy, el
`mean` a 0,79× y el `median` a 0,32×, porque un kernel a propósito (un bilineal
y una selección por píxel) le gana a la llamada general de biblioteca. Y OpenCL
corre en **NVIDIA, AMD e Intel**, mientras que CuPy solo existe en NVIDIA: es el
único backend que la app puede **repartir de serie**.

**Decisión**:

1. **`core/gpu.py` pasa a ser una fachada**: elige backend y despacha; el código
   CuPy se mueve a **`core/gpu_cuda.py`** y el nuevo es **`core/gpu_opencl.py`**.
   La superficie pública es la misma en los dos (`available`, `device_name`,
   `warp_batch`, `stack_ram`, `combine`, `frame_stars`) y cada punto de entrada
   contesta `None` cuando no puede servir la llamada, que es el contrato que
   `track_stack` ya esperaba (si no, se queda con numpy).
2. **Dos ajustes, no uno**: `astrometry_gpu` (el interruptor del observador,
   apagado por defecto) y `astrometry_gpu_backend` (`auto` | `cuda` | `opencl`,
   por defecto `auto`). `auto` prefiere CUDA, que en esta máquina es lo más
   rápido, y cae a OpenCL. El segundo existe para poder compararlos y para una
   máquina que tenga los dos.
3. **OpenCL cubre el warp y el combine** (los dos kernels limitados por ancho de
   banda de memoria, el 90 % del tiempo), con los cinco métodos de la app
   (`sum`/`mean`/`median`/`sigma`/`weighted`) y el **mismo recorte sigma** que
   `track_stack._sigma_clip_keep`, paso a paso: centro por mediana, escala MAD,
   `iterations` pasadas, el veto **acumulativo** y el centro moviéndose a la
   media de los supervivientes. Un NaN es el «no hay dato aquí» de la app, así
   que cada método lo salta igual que la ruta numpy.
4. **El registro (`frame_stars`) también se porta**: la imagen fuente (la
   mediana por bloques y el fondo) y la detección de estrellas (decimación, la
   MAD global del ruido y los máximos locales), espejo línea a línea de
   `register.source_image` y `register.detect_stars`. El coste de la estimación
   en la CPU son **dos medianas** (medido en un frame de 2048²: 101 ms de 170),
   y OpenCL no tiene mediana, así que las dos son un **radix select** sobre el
   patrón de bits ordenable del float (8 pasadas de 8 bits, un histograma por
   pasada). El voto, el emparejamiento y el ajuste **siguen en la CPU** (igual
   que en el backend CUDA): las listas de estrellas son cortas y un viaje al
   dispositivo por cada una no paga.
5. **La paridad se fija con un test** (`tests/unit/test_gpu_opencl.py`) que se
   salta sin pyopencl (el caso normal y el CI): el warp y el combine coinciden
   con la ruta numpy dentro del redondeo de float32, el mask del warp es
   **idéntico** (bit a bit) y la fachada llega de verdad al módulo cuando se le
   pide `opencl`.
6. **pyopencl viaja con la app**: es una dependencia **normal**
   (`dependencies`/`requirements.txt`, los paquetes Linux y el spec de
   PyInstaller), no un extra que el observador instala a mano. CuPy **sí** sigue
   siendo manual. La distinción es la del ADR-089: la **aceleración** nunca es
   un requisito (apagada por defecto y, sin dispositivo OpenCL o sin el ICD
   loader, `available()` es False y el camino numpy corre exactamente igual),
   pero el **binding** que hace posible el backend portable se reparte.
7. **El registro corre en `float` por defecto**, con el camino `double` a una
   línea (`gpu_opencl._FORCE_WIDE`, y un test lo ejercita para que no sea código
   muerto): medido, la lista de estrellas del `float` es la **misma** que la de
   la CPU (posiciones a 1,35e-7 px, picos a 2,4e-4 ADU) y el `double` es **bit a
   bit**, pero el `double` es **2,6× más lento** en una tarjeta de consumo (la
   3090 hace fp64 a 1/64 de fp32 y además duplica cada transferencia). La
   paridad que se fija es la del `float`, y con la cifra delante.

**Lo medido** (RTX 3090, `tools/bench/bench_opencl.py`; el `stack_group` sigma
de la app, 60 tomas de 2048², frame completo):

| Etapa | CuPy (CUDA) | OpenCL | OpenCL / CuPy |
| --- | --- | --- | --- |
| Warp bilineal por toma | 10,7 ms | **4,0 ms** | **0,37×** |
| Combine `mean` | 1,5 ms | 1,3 ms | 0,86× |
| Combine `median` | 202,4 ms | **64,7 ms** | **0,32×** |

| `stack_group` sigma, 60 × 2048² | Tiempo |
| --- | --- |
| CPU (16 hilos) | 8811 ms |
| CUDA (CuPy) | 2075 ms |
| **OpenCL** | **1446 ms** |

Y el **registro** (la imagen fuente y las estrellas de una toma de 2048², la
etapa que este ADR añade):

| Registro (imagen fuente + estrellas, 2048²) | Tiempo | vs CPU |
| --- | --- | --- |
| CPU (16 hilos) | 168,1 ms | x1,0 |
| **OpenCL** | **12,5 ms** | **x13,4** |
| CUDA (CuPy) | 21,2 ms | x7,9 |

Es decir: OpenCL no es el premio de consolación, es **más rápido que el camino
CuPy actual** en las dos etapas (1446 ms contra 2075 ms el apilado, y 12,5 ms
contra 21,2 ms el registro), porque sus kernels están escritos para el trabajo
que hacen: un warp a propósito, una selección por píxel para la mediana del
combine, un quickselect para la mediana del bloque y un radix select para la
MAD global. La lección del ADR-089 se repite: lo que decide es el **ancho de
banda** (y en la mediana global, no ordenar lo que solo hay que seleccionar).

**Alternativas**:

- **OpenCL como único backend** (sustituir CuPy): descartado. En NVIDIA CUDA
  sigue estando y el orden `auto` lo prefiere; OpenCL es el que se **reparte**,
  no el que sustituye. Y el backend CUDA ya tiene su paridad fijada por el test
  del ADR-089, que no se toca.
- **pyopencl como extra opcional** (`[optional-dependencies]`): descartado por
  el observador. «OpenCL de serie» significa que el observador no lo instala; el
  precio es que el binding entra en la lista de dependencias, y se acepta porque
  el **camino GPU sigue apagado por defecto** y sin dispositivo la app corre
  igual (la regla «sin dependencia dura» del ADR-089 era sobre CuPy y sobre no
  *necesitar* la GPU, y eso se mantiene).
- **Portar también el registro a OpenCL**: descartado de momento (punto 4). Es
  incremental: el módulo ya tiene el sitio y el contrato (`frame_stars` → None),
  así que portarlo más adelante no toca a nadie más.

**Consecuencias**: `core/gpu.py` deja de ser el backend y pasa a ser la
fachada; nacen `core/gpu_cuda.py` y `core/gpu_opencl.py`; un ajuste nuevo
(`astrometry_gpu_backend`) con su combo en Ajustes → Astrometría → Work; un test
nuevo que se salta sin pyopencl; pyopencl entra en `dependencies`,
`requirements.txt`, los paquetes Linux (`.deb`/`.rpm`/PKGBUILD) y el spec de
PyInstaller; y `tools/bench/bench_opencl.py` queda como el instrumento que mide
los dos backends contra los mismos datos. ADR-089 **no se revoca**: su punto 2
(una ruta GPU opcional, apagada por defecto) sigue vigente, y su alternativa
«OpenCL por ahora» es justo la que este ADR convierte en decisión.

**Nota (2026-10-14): las dos medianas, que son el registro entero.** El punto 4
se apoya en una medida: de los 170 ms de la estimación por toma, **101 son dos
medianas** (la del bloque de 32×32, 56 ms, y la MAD global sobre ~2,1 M valores,
45 ms) y el resto es paralelo y barato. Por eso el port no es «mover píxeles»:
es implementar dos selecciones EXACTAS. La del bloque es un quickselect por
bloque en memoria local, con un work-group de UN work-item (`__local` es por
work-group, y un grupo mayor compartiría el buffer y se pisaría); la global es
un radix select sobre el patrón de bits ordenable del float. Medido en la 3090:
la del bloque **4,4 ms contra 56 (x12,6)** y las dos globales **3,6 ms contra
45 (x12,5)**.

**Nota (2026-10-14): dos detalles que costaron un ulp cada uno, medidos.** La
paridad bit a bit del `double` no salió sola. (a) El compilador contraía
`a*b + c` en un `fma`, que se salta el redondeo del producto y movía el fondo
1,1e-13 en un cielo de mil; se apaga con `#pragma OPENCL FP_CONTRACT OFF`, que
es lo que la CPU hace sin querer. (b) La media 2×2 de la decimación de numpy
suma `(a+b)+(c+d)` y no de izquierda a derecha, y eso movía el pico 9,1e-13; el
kernel suma fila a fila y luego las filas. Con las dos, el `frame_stars` del
`double` es **bit a bit** en los cuatro tamaños probados (2048², el 2008² que no
divide por el bloque, 512² y 128²).

## English

**Context**: ADR-089 left OpenCL out "for now" and isolated the GPU path in one
module so that adding it would be incremental the day it was exported or the
blind search entered the engine. That day is today, and with a measurement that
changes the tone: OpenCL is **not slower** than CuPy. Measured on the same
machine (RTX 3090, 60 frames of 2048²) with hand-written kernels
(`tools/bench/bench_opencl.py`), the warp runs at 0.34x CuPy's time, the `mean`
at 0.79x and the `median` at 0.32x, because a purpose-built kernel (a bilinear
and a per-pixel selection) beats a general library call. And OpenCL runs on
**NVIDIA, AMD and Intel**, while CuPy only exists on NVIDIA: it is the only
backend the app can **ship**.

**Decision**:

1. **`core/gpu.py` becomes a facade**: it picks a backend and dispatches; the
   CuPy code moves to **`core/gpu_cuda.py`** and the new one is
   **`core/gpu_opencl.py`**. The public surface is the same in both
   (`available`, `device_name`, `warp_batch`, `stack_ram`, `combine`,
   `frame_stars`) and every entry point answers `None` when it cannot serve the
   call, which is the contract `track_stack` already expected (otherwise it
   keeps numpy).
2. **Two settings, not one**: `astrometry_gpu` (the observer's switch, off by
   default) and `astrometry_gpu_backend` (`auto` | `cuda` | `opencl`, `auto` by
   default). `auto` prefers CUDA, which is the fastest on this machine, and
   falls back to OpenCL. The second exists to compare them and for a machine
   that has both.
3. **OpenCL covers the warp and the combine** (the two memory-bandwidth-bound
   kernels, the 90 % of the time), with the app's five methods
   (`sum`/`mean`/`median`/`sigma`/`weighted`) and the **same sigma clip** as
   `track_stack._sigma_clip_keep`, step for step: median centre, MAD scale,
   `iterations` passes, the **cumulative** rejection and the centre moving to
   the mean of the survivors. A NaN is the app's "no data here", so every method
   skips it exactly as the numpy path does.
4. **The registration (`frame_stars`) is ported too**: the source image (the
   block median and the background) and the star detection (decimation, the
   noise's global MAD and the local maxima), a line-by-line mirror of
   `register.source_image` and `register.detect_stars`. The estimate's cost on
   the CPU is **two medians** (measured on a 2048² frame: 101 ms of 170), and
   OpenCL has no median, so both are a **radix select** on the sortable bit
   pattern of the float (8 passes of 8 bits, one histogram per pass). The vote,
   the pairing and the fit **stay on the CPU** (as in the CUDA backend): the
   star lists are short and a trip to the device per one does not pay.
5. **The parity is pinned by a test** (`tests/unit/test_gpu_opencl.py`) that
   skips without pyopencl (the normal case and the CI): the warp and the combine
   agree with the numpy path to within float32 rounding, the warp's mask is
   **identical** (bit for bit) and the facade really reaches the module when
   asked for `opencl`.
6. **pyopencl travels with the app**: it is a **normal** dependency
   (`dependencies`/`requirements.txt`, the Linux packages and the PyInstaller
   spec), not an extra the observer installs by hand. CuPy **is** still manual.
   The distinction is ADR-089's: the **acceleration** is never a requirement
   (off by default and, with no OpenCL device or no ICD loader, `available()` is
   False and the numpy path runs exactly the same), but the **binding** that
   makes the portable backend possible is shipped.
7. **The registration runs in `float` by default**, with the `double` path one
   line away (`gpu_opencl._FORCE_WIDE`, and a test exercises it so it is not
   dead code): measured, the float star list is the **same** as the CPU's
   (positions to 1.35e-7 px, peaks to 2.4e-4 ADU) and the double one is **bit
   for bit**, but the double is **2.6x slower** on a consumer card (an RTX 3090
   does fp64 at 1/64 of fp32 AND doubles every transfer). The parity that is
   pinned is the float one, with the figure in front of it.

**What was measured** (RTX 3090, `tools/bench/bench_opencl.py`; the app's
`stack_group` sigma, 60 frames of 2048², whole frame):

| Stage | CuPy (CUDA) | OpenCL | OpenCL / CuPy |
| --- | --- | --- | --- |
| Per-frame bilinear warp | 10.7 ms | **4.0 ms** | **0.37x** |
| `mean` combine | 1.5 ms | 1.3 ms | 0.86x |
| `median` combine | 202.4 ms | **64.7 ms** | **0.32x** |

| `stack_group` sigma, 60 x 2048² | Time |
| --- | --- |
| CPU (16 threads) | 8811 ms |
| CUDA (CuPy) | 2075 ms |
| **OpenCL** | **1446 ms** |

And the **registration** (the source image and the stars of a 2048² frame, the
stage this ADR adds):

| Registration (source image + stars, 2048²) | Time | vs CPU |
| --- | --- | --- |
| CPU (16 threads) | 168.1 ms | x1.0 |
| **OpenCL** | **12.5 ms** | **x13.4** |
| CUDA (CuPy) | 21.2 ms | x7.9 |

That is: OpenCL is not the consolation prize, it is **faster than the current
CuPy path** on both stages (1446 ms against 2075 ms for the stacking, and
12.5 ms against 21.2 ms for the registration), because its kernels are written
for the work they do: a purpose-built warp, a per-pixel selection for the
combine's median, a quickselect for the block median and a radix select for the
global MAD. ADR-089's lesson repeats: what decides is **bandwidth** (and, for
the global median, not sorting what only needs selecting).

**Alternatives**:

- **OpenCL as the only backend** (replacing CuPy): rejected. CUDA is still there
  on NVIDIA and the `auto` order prefers it; OpenCL is what gets **shipped**, not
  what replaces it. And the CUDA backend already has its parity pinned by
  ADR-089's test, which is not touched.
- **pyopencl as an optional extra** (`[optional-dependencies]`): rejected by the
  observer. "OpenCL out of the box" means the observer does not install it; the
  price is that the binding enters the dependency list, and it is accepted
  because the **GPU path is still off by default** and without a device the app
  runs the same (ADR-089's "no hard dependency" rule was about CuPy and about
  not *needing* the GPU, and that holds).
- **Porting the registration to OpenCL too**: rejected for now (point 4). It is
  incremental: the module already has the slot and the contract
  (`frame_stars` -> None), so porting it later touches nobody else.

**Consequences**: `core/gpu.py` stops being the backend and becomes the facade;
`core/gpu_cuda.py` and `core/gpu_opencl.py` are born; a new setting
(`astrometry_gpu_backend`) with its combo in Settings -> Astrometry -> Work; a
new test that skips without pyopencl; pyopencl enters `dependencies`,
`requirements.txt`, the Linux packages (`.deb`/`.rpm`/PKGBUILD) and the
PyInstaller spec; and `tools/bench/bench_opencl.py` stays as the instrument that
measures both backends against the same data. ADR-089 is **not revoked**: its
point 2 (an optional GPU path, off by default) still stands, and its
"OpenCL for now" alternative is exactly what this ADR turns into a decision.

**Note (2026-10-14): the two medians, which are the whole registration.**
Point 4 rests on a measurement: of the estimate's 170 ms per frame, **101 are
two medians** (the 32x32 block one, 56 ms, and the global MAD over ~2.1M values,
45 ms) and the rest is parallel and cheap. That is why the port is not "moving
pixels": it is implementing two EXACT selections. The block one is a per-block
quickselect in local memory, with a work-group of ONE work-item (`__local` is
per work-group, and a bigger group would share the buffer and race); the global
one is a radix select on the sortable bit pattern of the float. Measured on the
RTX 3090: the block one **4.4 ms against 56 (x12.6)** and the two global ones
**3.6 ms against 45 (x12.5)**.

**Note (2026-10-14): two details that each cost one ulp, measured.** The double
build's bit-for-bit parity did not come for free. (a) The compiler contracted
`a*b + c` into one `fma`, which skips the product's rounding and moved the
background by 1.1e-13 on a sky of a thousand; it is turned off with
`#pragma OPENCL FP_CONTRACT OFF`, which is what the CPU does without meaning to.
(b) numpy's 2x2 decimation mean sums `(a+b)+(c+d)` and not left to right, which
moved the peak by 9.1e-13; the kernel sums row by row and then the rows. With
both, the double `frame_stars` is **bit for bit** at the four sizes tested
(2048², the 2008² that does not divide by the block, 512² and 128²).
