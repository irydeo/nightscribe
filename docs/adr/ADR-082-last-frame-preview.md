# ADR-082: La última toma en la ventana (por HTTP, en remoto también)

**Estado / Status**: Accepted · **Fecha / Date**: 2026-10-13

## Español

**Contexto**: con ADR-081 el paso Captura ya apunta el telescopio, prepara el
plan y lanza la captura. El círculo quedaba abierto en el último tramo: el
observador lanzaba la toma y **no veía nada** hasta abrir el FITS a mano.
Cerrarlo significa mostrar, en la propia ventana, la última toma, y poder
abrirla en el taller de imagen con un clic. La primera versión de este ADR lo
resolvió **vigilando una carpeta en disco**; el observador hizo notar el fallo:
NINA, PINS o CCDciel pueden correr en **otra máquina**, y entonces esa carpeta
no existe para NightScribe. Revisado contra las dos APIs, el camino correcto es
**HTTP**, y las dos lo ofrecen.

**Decisión**:

1. **La imagen llega por HTTP, no por una carpeta.** Los dos programas sirven
   la última imagen por red, en local y en remoto, así que no hay carpeta que
   montar ni ajuste que configurar:
   - **CCDciel**: su servidor web, en el **mismo host:puerto** del JSON-RPC
     (3277), sirve `fullimage.jpg` (la última imagen) y `scrimage.jpg` (la de
     pantalla); el handler está en `pu_main.TCPgetimage` y la ruta en
     `cu_tcpserver.ProcessHttp`. Se pide `GET http://host:3277/fullimage.jpg`.
   - **NINA/PINS**: la Advanced API v2 sirve la imagen en
     `GET /v2/api/image/{index}?stream=true&resize=true&size=200x200` (PNG); el
     índice sale de `/image-history?count=true` y el pie, de
     `/image-history?index=N`.
2. **Se elimina el ajuste «Capture folder»** y todo lo que colgaba de él
   (`core/capture_watch.py`, `capture_dir()`, el campo en Ajustes): era
   justamente lo que no encajaba en remoto.
3. **Se refresca solo cuando hay algo nuevo y mientras se captura.** Tras
   *Start capture* se sondea cada ~2 s (en un worker: la red nunca en el hilo
   de la GUI) y se para unos tics después de que el dashboard diga que la
   captura terminó (`Capture_running` en CCDciel, `IsExposing` en NINA). La
   miniatura se repinta solo cuando los bytes cambian; un error de red
   transitorio no borra lo que ya se veía.
4. **Abrir en el editor, según lo que cada programa pueda dar**:
   - **NINA/PINS**: `GET /image/{index}?raw_fits=true` devuelve el FITS en
     base64; se baja a un temporal y se abre en el editor. Funciona en remoto.
     Es el único punto que toca base64, y el plugin avisa de que ese flag puede
     retirarse; queda aislado aquí.
   - **CCDciel**: su HTTP solo sirve JPEG, así que el FITS se abre desde la
     ruta de `Capture_getLastfilename` **cuando NightScribe puede verla** (misma
     máquina o carpeta montada). Si no existe, el botón lo dice en vez de
     fingir.
5. **La miniatura es la imagen del propio programa** (su estirado), porque es
   una mirada rápida, no un gráfico; el FITS real es el que se abre en el
   editor para medir. Así no se duplica el motor de estirado ni se depende del
   base64 para el preview.

**Limitaciones (a propósito)**:

- **CCDciel no entrega el FITS por HTTP**: solo la imagen JPEG. Abrir el FITS
  en remoto exige que su carpeta sea visible desde NightScribe.
- La miniatura de CCDciel es su render (no el nuestro): sirve para ver que la
  toma llegó y cómo está, no para medirla.
- **NINA/PINS**: `raw_fits` depende de un flag que el plugin puede retirar; si
  desaparece, la miniatura seguirá funcionando y abrir el FITS en remoto no.
- Muestra **una** toma (la última), no una tira de la serie, y **no adjunta**
  nada a la visita: es una mirada, no un archivado.

**Consecuencias**: se borra `core/capture_watch.py` (+ test) y el ajuste
`capture_folder` (config, `settings_spec`, `.ui`, botones y ayuda);
`ccdciel.py` gana `last_frame_name()` y `last_frame_preview()` (JPEG por HTTP) y
`nina.py` `last_frame_preview()` (PNG por stream) e `image_fits_bytes()`;
`workers.py` gana `CapturePreviewWorker` y `CaptureFitsWorker`; `main_window.py`
la miniatura, su temporizador y el botón de abrir en el editor; tests de los dos
clientes y del preview; guía, README y web.

## English

**Context**: with ADR-081 the Capture step already points the telescope, stages
the plan and starts the capture. The loop stayed open on the last leg: the
observer fired the shot and **saw nothing** until opening the FITS by hand.
Closing it means showing, in the window itself, the last frame, and being able
to open it in the image workbench with one click. The first version of this ADR
solved it by **watching a folder on disk**; the observer pointed out the flaw:
NINA, PINS or CCDciel may run on **another machine**, and then that folder does
not exist for NightScribe. Re-checked against both APIs, the right path is
**HTTP**, and both offer it.

**Decision**:

1. **The image comes over HTTP, not from a folder.** Both programs serve the
   last image over the network, local and remote, so there is no folder to
   mount and no setting to configure:
   - **CCDciel**: its web server, on the **same host:port** as the JSON-RPC
     (3277), serves `fullimage.jpg` (the last image) and `scrimage.jpg` (the
     on-screen one); the handler is `pu_main.TCPgetimage` and the route is
     `cu_tcpserver.ProcessHttp`. Fetch `GET http://host:3277/fullimage.jpg`.
   - **NINA/PINS**: the Advanced API v2 serves the image at
     `GET /v2/api/image/{index}?stream=true&resize=true&size=200x200` (PNG); the
     index comes from `/image-history?count=true` and the caption from
     `/image-history?index=N`.
2. **The "Capture folder" setting is removed**, and everything hanging off it
   (`core/capture_watch.py`, `capture_dir()`, the Settings field): it was
   exactly what did not fit remote work.
3. **It refreshes only when there is something new, and only while capturing.**
   After *Start capture* it polls every ~2 s (on a worker: the network never on
   the GUI thread) and stops a few ticks after the dashboard says the capture
   ended (`Capture_running` on CCDciel, `IsExposing` on NINA). The thumbnail is
   repainted only when the bytes change; a transient network error does not
   clear what was already shown.
4. **Open in the editor, per what each program can give**:
   - **NINA/PINS**: `GET /image/{index}?raw_fits=true` returns the FITS as
     base64; it is downloaded to a temp file and opened in the editor. Works
     remote. It is the only place base64 is touched, and the plugin warns that
     flag may be withdrawn; it stays isolated here.
   - **CCDciel**: its HTTP only serves JPEG, so the FITS is opened from the
     `Capture_getLastfilename` path **when NightScribe can see it** (same
     machine or a mounted folder). If it does not exist, the button says so
     instead of faking.
5. **The thumbnail is the program's own image** (its stretch), because it is a
   quick look, not a chart; the real FITS is what opens in the editor to
   measure. This avoids duplicating the stretch engine and does not depend on
   base64 for the preview.

**Limitations (on purpose)**:

- **CCDciel does not deliver the FITS over HTTP**: only the JPEG image. Opening
  the FITS remotely requires its folder to be visible from NightScribe.
- CCDciel's thumbnail is its render (not ours): good to see the frame arrived
  and how it looks, not to measure it.
- **NINA/PINS**: `raw_fits` depends on a flag the plugin may withdraw; if it
  goes, the thumbnail keeps working and opening the FITS remotely does not.
- It shows **one** frame (the last), not a strip of the series, and **attaches**
  nothing to the visit: it is a look, not a filing.

**Consequences**: `core/capture_watch.py` (+ test) and the `capture_folder`
setting (config, `settings_spec`, `.ui`, buttons and help) are removed;
`ccdciel.py` gains `last_frame_name()` and `last_frame_preview()` (JPEG over
HTTP) and `nina.py` `last_frame_preview()` (PNG over stream) and
`image_fits_bytes()`; `workers.py` gains `CapturePreviewWorker` and
`CaptureFitsWorker`; `main_window.py` the thumbnail, its timer and the
open-in-editor button; tests for both clients and the preview; guide, README and
website.
