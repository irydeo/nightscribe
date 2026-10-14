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
4. **El registro (`frame_stars`) NO se porta**: la mediana por bloques y la
   búsqueda de estrellas son otra bestia, y un medio-puerto que moviera un
   centroide en silencio sería **peor que no portarlo**. En una máquina
   solo-OpenCL el registro se queda en la CPU (la app lo dice en la nota del
   run, que nombra el dispositivo) y las dos etapas caras siguen en el
   dispositivo.
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

**Lo medido** (RTX 3090, 60 tomas de 2048², `tools/bench/bench_opencl.py`; el
`stack_group` sigma de la app, frame completo):

| Etapa | CuPy (CUDA) | OpenCL | OpenCL / CuPy |
| --- | --- | --- | --- |
| Warp bilineal por toma | 12,4 ms | **4,2 ms** | **0,34×** |
| Combine `mean` | 1,7 ms | 1,4 ms | 0,79× |
| Combine `median` | 203,2 ms | **64,3 ms** | **0,32×** |

| `stack_group` sigma, 60 × 2048² | Tiempo |
| --- | --- |
| CPU (16 hilos) | 8462 ms |
| CUDA (CuPy) | 2168 ms |
| **OpenCL** | **1400 ms** |

Es decir: OpenCL no es el premio de consolación, es **más rápido que el camino
CuPy actual** de punta a punta (1400 ms contra 2168 ms), porque sus kernels
están escritos para el trabajo que hacen. La lección del ADR-089 se repite: lo
que decide es el **ancho de banda**, y ahí un kernel a propósito le gana a una
biblioteca general.

Y lo que **falta**, medido para no engañarse: la estimación del registro por
toma de 2048² cuesta 170,4 ms en CPU y 21,3 ms en CUDA (0,12×). En una máquina
solo-OpenCL esa etapa **sigue en CPU**: es el hueco honesto de este backend, y
está escrito en el módulo en vez de tapado.

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

**Nota (2026-10-14): el registro en una máquina solo-OpenCL, medido.** El punto
4 deja la estimación por toma en CPU. Medido en un frame real de 2048², esa
etapa es 170,4 ms en CPU; en una visita de decenas de tomas eso domina el tiempo
del registro, y es el motivo por el que el backend CUDA sigue existiendo y por
el que `auto` lo prefiere cuando está. El día que la mediana por bloques y la
búsqueda de estrellas se porten a OpenCL, este ADR se actualiza con la cifra.

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
4. **The registration (`frame_stars`) is NOT ported**: the block median and the
   star search are a different beast, and a half-port that quietly moved a
   centroid would be **worse than no port**. On an OpenCL-only machine the
   registration stays on the CPU (the app says so in the run's note, which names
   the device) and the two expensive stages stay on the device.
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

**What was measured** (RTX 3090, 60 frames of 2048²,
`tools/bench/bench_opencl.py`; the app's `stack_group` sigma, whole frame):

| Stage | CuPy (CUDA) | OpenCL | OpenCL / CuPy |
| --- | --- | --- | --- |
| Per-frame bilinear warp | 12.4 ms | **4.2 ms** | **0.34x** |
| `mean` combine | 1.7 ms | 1.4 ms | 0.79x |
| `median` combine | 203.2 ms | **64.3 ms** | **0.32x** |

| `stack_group` sigma, 60 x 2048² | Time |
| --- | --- |
| CPU (16 threads) | 8462 ms |
| CUDA (CuPy) | 2168 ms |
| **OpenCL** | **1400 ms** |

That is: OpenCL is not the consolation prize, it is **faster than the current
CuPy path** end to end (1400 ms against 2168 ms), because its kernels are
written for the work they do. ADR-089's lesson repeats: what decides is
**bandwidth**, and there a purpose-built kernel beats a general library.

And what is **missing**, measured so as not to fool ourselves: the per-frame
registration estimate of a 2048² frame costs 170.4 ms on the CPU and 21.3 ms on
CUDA (0.12x). On an OpenCL-only machine that stage **stays on the CPU**: it is
this backend's honest gap, and it is written in the module instead of hidden.

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

**Note (2026-10-14): the registration on an OpenCL-only machine, measured.**
Point 4 leaves the per-frame estimate on the CPU. Measured on a real 2048²
frame, that stage is 170.4 ms on the CPU; in a visit of dozens of frames it
dominates the registration's time, and that is why the CUDA backend still
exists and why `auto` prefers it when present. The day the block median and the
star search are ported to OpenCL, this ADR is updated with the figure.
