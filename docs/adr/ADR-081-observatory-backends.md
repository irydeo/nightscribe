# ADR-081: Backends de observatorio: CCDciel y NINA/PINS (Stop goto y filtros reales)

**Estado / Status**: Accepted · **Fecha / Date**: 2026-10-13

## Español

**Contexto**: ADR-030 integró CCDciel (JSON-RPC) y dejó «controlar telescopios» con una
sola puerta. El paso **Captura** de cada proyecto ya apunta el telescopio, hace un goto
astrométrico, prepara el plan y lanza la captura. Tres cosas quedaban mal o a medias:

1. **No había forma de parar un goto.** Es el riesgo de seguridad más serio de manejar
   una montura: si un slew se va a un sitio equivocado, el observador necesita pararlo
   ya, no esperar a que termine. Ni CCDciel ni NINA se pueden dar por seguros sin esto.
2. **La integración era sólo CCDciel.** NINA (Windows) y PINS (Linux), su versión para
   Linux, hablan el plugin comunitario **Advanced API v2** (christian-photo/ninaAPI),
   una API REST en `http://host:1888/v2/api`. El observador debe poder elegir uno u otro.
3. **Los filtros del plan estaban hardcodeados.** El combo **Filter** de la tarjeta
   «Exposure plan» ofrecía `L/R/G/B/Ha/OIII/SII` siempre, aunque la rueda real tuviera
   otros nombres. El combo «Filter on wheel» del bloque del observatorio sí se rellenaba
   de la rueda, así que las dos listas podían discrepar, y «Send plan» podía preparar un
   índice de filtro que no correspondía con lo que el observador creía.

**Decisión**:

1. **Stop goto (seguridad), en los dos backends.** Un botón **Stop goto** en la fila de
   apuntado, **deshabilitado** por defecto, que **se arma en el instante** en que se
   pulsa *Point telescope* o *Astrometric Goto* y se desarma cuando el goto termina o
   falla. Llama a `abort_motion()`: en CCDciel, `Telescope_abortmotion` («Stop any
   telescope movement»); en NINA, `GET /equipment/mount/slew/stop`. Detalle crítico: el
   botón corre en **su propio worker**, nunca por `_ccd_run`: el goto ocupa el único slot
   de worker mientras mueve, y un paro que se encola detrás de lo que está parando no es
   un paro. Para solo el movimiento de la montura, no una captura en curso (decisión de
   alcance).
2. **Una abstracción de backend, uno u otro.** `core/sources/observatory.py` define
   `ObservatoryError` (base común) y `make_client(cfg)`, que devuelve `ccdciel.Client` o
   `nina.Client` según `observatory_backend`. Los dos clientes exponen **la misma
   superficie** (`ping`, `dashboard`, `filters`, `slewing`, `tracking`, `slew_target`,
   `astrometry_goto`, `set_filter`, `push_plan`, `staged_plan`, `start_capture`,
   `abort_motion`) y la GUI no ramifica por backend: `CcdcielWorker` se generaliza a
   `ObservatoryWorker` y captura `ObservatoryError`. La selección vive en **Ajustes →
   Integrations** (combo «Observatory software» + host/puerto de cada uno); `config.py`
   gana `observatory_backend` (`"ccdciel"` por defecto), `nina_host`
   (`127.0.0.1`), `nina_port` (`1888`) y `nina_auto_connect`; `db.SOURCE_TTL["nina"] = 60`
   con la misma razón que CCDciel. Cambiar de backend al guardar Ajustes **desconecta**
   el que estaba, para no manejar el programa equivocado con los botones correctos.
3. **Los filtros son los de la rueda, en los dos sitios.** `_ccd_filter_choices()` es la
   única fuente: devuelve los nombres reales que dio la rueda al conectar
   (`Wheel_GetfiltersName` en CCDciel, `AvailableFilters` en NINA) y solo cae a la lista
   clásica cuando no hay conexión. El combo del plan y el del bloque del observatorio se
   rellenan de ahí; al conectar, el del plan se refresca conservando la elección si la
   rueda todavía la tiene; al desconectar, vuelve a la lista clásica.
4. **«Send plan» = preparar y verificar, no disparar a ciegas.** El significado es el
   mismo que en ADR-030 (preparar la captura; *Start capture* la lanza), pero ahora deja
   rastro: `staged_plan()` **lee de vuelta** lo que el programa tiene de verdad y el panel
   lo pinta bajo la fila («Preparado: objeto · N × exp s · filtro»). En CCDciel se lee con
   `Capture_getobjectname/exposure/count/frametype` y `Wheel_getfilter`; en NINA, que no
   tiene un «staging» persistente, se recuerda en el cliente y se marca
   `persistent=False`, con el aviso de que el número de frames es informativo.
5. **Lo que NINA no hace igual, dicho en voz alta.** El snapshot de NINA
   (`/equipment/camera/capture`) toma **una** exposición y no admite un contador de
   frames: *Start capture* dispara una toma con la exposición y el nombre del objeto
   preparados, y el panel dice que el número de frames es solo información. No se finge
   un contador que el programa no va a usar.
6. **El goto astrométrico de NINA** es su instrucción **Center**
   (`/equipment/mount/slew?center=true&waitForResult=true`): apunta, resuelve la placa y
   corrige, con la llamada abierta hasta que termina (por eso ese endpoint usa un tope de
   240 s y no los 6 s del resto). NINA toma coordenadas **J2000 directamente**, así que no
   hay conversión `J2000_to_Apparent` como en CCDciel.
7. **Conectar solo alcanza la API.** Conectar/desconectar montura y cámara es decisión de
   CCDciel/NINA, no de NightScribe, igual que en ADR-030.

**Limitaciones (a propósito)**:

- **NINA no respeta el número de frames**: su snapshot es de una exposición. El plan se
  muestra completo, pero solo la exposición y el objeto llegan a la toma.
- **NINA no tiene «staging» persistente en el servidor**: *Send plan* fija el filtro de la
  rueda y el resto lo guarda NightScribe; no hay un estado en NINA que leer de vuelta.
- **El goto astrométrico de NINA exige un plate solver configurado en NINA**; sin él, la
  instrucción Center falla y el error se muestra tal cual.
- **PINS comparte la misma Advanced API v2**: un solo cliente para NINA y PINS, solo
  cambian host y puerto. La validación es contra la especificación v2 documentada; queda
  pendiente fijarla contra una instancia real (misma filosofía que ADR-021).
- **Stop goto solo para el movimiento de la montura**, no para una captura en curso.
- **`Sequence_start` de CCDciel sigue fuera de alcance** (ADR-030, sin cambios): «Send
  plan» prepara el módulo Capture, no carga una secuencia.
- **Un backend a la vez**: no se hablan los dos programas en la misma sesión.

**Consecuencias**: `core/sources/observatory.py` y `core/sources/nina.py` nuevos;
`ccdciel.py` gana `abort_motion`/`staged_plan` y `CCDcielError` pasa a derivar de
`ObservatoryError`; `CcdcielWorker` → `ObservatoryWorker` (alias conservado);
`config.py`/`settings_spec.py`/`settings_dialog.ui` ganan el backend y los campos NINA;
`main_window.py` gana el botón Stop goto, la etiqueta de lo preparado y
`_ccd_filter_choices`; `db.py` gana la fuente `nina`; i18n ES/EN ampliada (~22 cadenas);
tests unitarios del cliente NINA con HTTP falso, del selector, del armado del Stop y de
la lista de filtros del plan; funcional con `skip` si no hay servidor. Guía de usuario,
README, `docs/DATA_SOURCES`, `docs/UI_EXPORTS` y la web actualizados.

## English

**Context**: ADR-030 integrated CCDciel (JSON-RPC) and gave telescope control a single
door. Each project's **Capture** step already points the telescope, does an astrometric
goto, stages the plan and starts the capture. Three things were wrong or half-done:

1. **There was no way to stop a goto.** It is the most serious safety risk of driving a
   mount: if a slew heads somewhere wrong, the observer needs it halted now, not after it
   finishes. Neither CCDciel nor NINA can be called safe without this.
2. **The integration was CCDciel only.** NINA (Windows) and PINS (Linux), its Linux
   build, speak the community plugin **Advanced API v2** (christian-photo/ninaAPI), a REST
   API at `http://host:1888/v2/api`. The observer must be able to pick one or the other.
3. **The plan's filters were hardcoded.** The **Filter** combo of the "Exposure plan" card
   always offered `L/R/G/B/Ha/OIII/SII`, even when the real wheel had other names. The
   "Filter on wheel" combo of the observatory block was filled from the wheel, so the two
   lists could disagree, and "Send plan" could stage a filter index that did not match
   what the observer believed.

**Decision**:

1. **Stop goto (safety), on both backends.** A **Stop goto** button in the pointing row,
   **disabled** by default, **armed the moment** *Point telescope* or *Astrometric Goto*
   is pressed and disarmed when the goto ends or fails. It calls `abort_motion()`: on
   CCDciel, `Telescope_abortmotion` ("Stop any telescope movement"); on NINA,
   `GET /equipment/mount/slew/stop`. Critical detail: the button runs on **its own
   worker**, never through `_ccd_run`: the goto owns the single worker slot while it
   moves, and a stop queued behind the thing it is stopping is no stop. It stops the
   mount's motion only, not a running capture (scope decision).
2. **A backend abstraction, one at a time.** `core/sources/observatory.py` defines
   `ObservatoryError` (the common base) and `make_client(cfg)`, which returns
   `ccdciel.Client` or `nina.Client` per `observatory_backend`. Both clients expose **the
   same surface** (`ping`, `dashboard`, `filters`, `slewing`, `tracking`, `slew_target`,
   `astrometry_goto`, `set_filter`, `push_plan`, `staged_plan`, `start_capture`,
   `abort_motion`) and the GUI does not branch on the backend: `CcdcielWorker` becomes
   `ObservatoryWorker` and catches `ObservatoryError`. The choice lives in **Settings →
   Integrations** ("Observatory software" combo + each one's host/port); `config.py` gains
   `observatory_backend` (default `"ccdciel"`), `nina_host` (`127.0.0.1`), `nina_port`
   (`1888`) and `nina_auto_connect`; `db.SOURCE_TTL["nina"] = 60` for the same reason as
   CCDciel. Changing the backend on save **disconnects** the old one, so the right buttons
   never drive the wrong program.
3. **The filters are the wheel's, in both places.** `_ccd_filter_choices()` is the single
   source: it returns the real names the wheel gave on connect (`Wheel_GetfiltersName` on
   CCDciel, `AvailableFilters` on NINA) and only falls back to the classic list when there
   is no connection. The plan combo and the observatory block combo are filled from it; on
   connect the plan's is refreshed keeping the pick when the wheel still has it; on
   disconnect it goes back to the classic list.
4. **"Send plan" = stage and verify, not fire blindly.** The meaning is the same as in
   ADR-030 (stage the capture; *Start capture* fires it), but now it leaves a trace:
   `staged_plan()` **reads back** what the program really holds and the panel paints it
   under the row ("Staged: object · N × exp s · filter"). On CCDciel it reads with
   `Capture_getobjectname/exposure/count/frametype` and `Wheel_getfilter`; on NINA, which
   has no persistent staging, it is remembered in the client and flagged
   `persistent=False`, with the note that the frame count is information only.
5. **What NINA does not do the same, said out loud.** NINA's snapshot
   (`/equipment/camera/capture`) takes **one** exposure and has no frame count: *Start
   capture* fires one shot with the staged exposure and object name, and the panel says
   the frame count is information only. No counter is faked that the program will not use.
6. **NINA's astrometric goto** is its **Center** instruction
   (`/equipment/mount/slew?center=true&waitForResult=true`): it points, solves the plate
   and corrects, with the call held open until it ends (that is why this endpoint gets a
   240 s ceiling instead of the usual 6 s). NINA takes **J2000 coordinates directly**, so
   there is no `J2000_to_Apparent` conversion as in CCDciel.
7. **Connecting only reaches the API.** Connecting/disconnecting the mount and camera is
   CCDciel's/NINA's decision, not NightScribe's, exactly as in ADR-030.

**Limitations (on purpose)**:

- **NINA does not honour the frame count**: its snapshot is one exposure. The plan is
  shown whole, but only the exposure and the object reach the shot.
- **NINA has no persistent server-side staging**: *Send plan* sets the wheel filter and
  NightScribe holds the rest; there is no NINA state to read back.
- **NINA's astrometric goto needs a plate solver configured in NINA**; without it, the
  Center instruction fails and the error is shown as-is.
- **PINS shares the same Advanced API v2**: one client for NINA and PINS, only host and
  port change. Validation is against the documented v2 spec; pinning it against a real
  instance is pending (same philosophy as ADR-021).
- **Stop goto stops the mount's motion only**, not a running capture.
- **CCDciel's `Sequence_start` stays out of scope** (ADR-030, unchanged): "Send plan"
  stages the Capture module, it does not load a sequence.
- **One backend at a time**: the two programs are not driven in the same session.

**Consequences**: new `core/sources/observatory.py` and `core/sources/nina.py`;
`ccdciel.py` gains `abort_motion`/`staged_plan` and `CCDcielError` now derives from
`ObservatoryError`; `CcdcielWorker` → `ObservatoryWorker` (alias kept);
`config.py`/`settings_spec.py`/`settings_dialog.ui` gain the backend and the NINA fields;
`main_window.py` gains the Stop-goto button, the staged label and `_ccd_filter_choices`;
`db.py` gains the `nina` source; ES/EN i18n extended (~22 strings); unit tests for the
NINA client with a faked HTTP, the selector, the Stop arming and the plan's filter list;
a functional test that **skips** without a server. User guide, README,
`docs/DATA_SOURCES`, `docs/UI_EXPORTS` and the website updated.

**Revision (2026-10-13, one program's fields at a time)**: the Integrations
page no longer shows CCDciel's and NINA/PINS's fields together. The combo
"Observatory software" now gates the two groups (`settings_spec.BACKEND_GROUPS`):
only the chosen program's host, port and auto-connect are visible, and the
search cannot reveal the other one either (the gate is applied inside the
search filter, not beside it).

**Revisión (2026-10-13, los campos de un programa a la vez)**: la página
Integraciones ya no muestra juntos los campos de CCDciel y NINA/PINS. El combo
«Observatory software» gobierna los dos grupos (`settings_spec.BACKEND_GROUPS`):
solo se ven el host, el puerto y el auto-conectar del programa elegido, y el
buscador tampoco puede revelar el otro (la puerta se aplica dentro del filtro
del buscador, no al lado).

**Review (2026-10-13, live capture polish)**: three fixes to the live control.
(1) **"Send plan" no longer stops half-way**: CCDciel's `Capture_setbinning`
wants an **integer** (`"1x1"` is rejected), so the binning is converted; and the
optional setters (binning/gain/offset/dither) are **best-effort** (a rejected one
is reported and the core plan still lands and is read back). (2) The capture
button is **one toggle**: "Start capture" / "Stop capture" (CCDciel `Capture_stop`;
NINA `/equipment/camera/abort-exposure`), driven by the dashboard's capturing
state. (3) gain/offset are the **camera's own settings** (read from the software
when connected), not the system gain in e-/ADU; and the "?" glyph buttons carry
`compact="true"` so their text is not clipped. The autofocus cadence is not a
live setting in either API: it goes in the exported sequence.

**Revisión (2026-10-13, pulido de la captura en vivo)**: tres arreglos del
control en vivo. (1) **«Send plan» ya no se queda a medias**: `Capture_setbinning`
de CCDciel quiere un **entero** (`"1x1"` se rechaza), así que el binning se
convierte; y los setters opcionales (binning/gain/offset/dither) son
**best-effort** (el que falle se avisa y el plan base aterriza y se lee de
vuelta). (2) El botón de captura es **un conmutador**: «Start capture» /
«Stop capture» (CCDciel `Capture_stop`; NINA `/equipment/camera/abort-exposure`),
guiado por el estado de captura del dashboard. (3) gain/offset son los **ajustes
de la propia cámara** (se leen del software si hay conexión), no la ganancia del
sistema en e-/ADU; y los botones «?» llevan `compact="true"` para que no se
recorte el texto. La cadencia de autofocus no es un ajuste en vivo en ninguna
API: va en la secuencia exportada.

**Review (2026-10-13, live capture corrections)**: three corrections against
CCDciel's own source (`pu_scriptengine.pas`). (1) **`Capture_setbinning` wants
the TEXT** (`cmd_Capture_SetBinning` does `Capture.Binning.Text := bin`), so
"1x1" is sent, not an integer (an earlier "fix" to an int was wrong). (2) The
staged read-back adds **`Capture_getbinning` and `Capture_getdither`**, so the
panel shows the binning and dither that really landed (that read-back would
have caught the binning bug at once). (3) **The autofocus cadence cannot be set
live**: CCDciel's Capture module has the "after temperature change / after HFD
change" checkboxes, but its JSON-RPC API exposes no setter for them (only
`Autofocus` = run now); the cadence travels in the exported sequence, and the
"Send plan" tooltip says so.

**Revisión (2026-10-13, correcciones de la captura en vivo)**: tres correcciones
contra el código de CCDciel (`pu_scriptengine.pas`). (1) **`Capture_setbinning`
quiere el TEXTO** (`cmd_Capture_SetBinning` hace `Capture.Binning.Text := bin`),
así que se envía "1x1", no un entero (un «arreglo» anterior a entero era
erróneo). (2) La lectura de vuelta añade **`Capture_getbinning` y
`Capture_getdither`**, para que el panel muestre el binning y el dither que de
verdad aterrizaron. (3) **La cadencia de autofocus no se puede fijar en vivo**:
el módulo Capture de CCDciel tiene los checkboxes «tras cambio de temperatura /
de HFD», pero su API JSON-RPC no expone setter para ellos (solo `Autofocus` =
enfocar ahora); la cadencia viaja en la secuencia, y el tooltip de «Send plan»
lo dice.

**Review (2026-10-13, the wheel filter cannot lose the plan)**: "Send plan" moved the wheel in the GUI BEFORE `push_plan`, so a refused slot (`Wheel_setfilter: Failed!`, seen in the log) raised and the whole plan was lost: CCDciel received neither the object nor the exposure nor the count ("Send plan receives nothing"). The filter is now a **best-effort setter inside `push_plan`** (`filter_index`), like binning/gain/offset/dither, and the GUI does **not** invent a slot: if the plan's filter is not in the wheel, the filter is left as it is and the read-back says so. NINA applies the filter in `start_capture`, also best-effort.

**Revisión (2026-10-13, el filtro de la rueda no puede perder el plan)**: «Send plan» movía la rueda en la GUI ANTES de `push_plan`, así que una ranura rechazada (`Wheel_setfilter: Failed!`, visto en el log) lanzaba y se perdía el plan entero: CCDciel no recibía ni el objeto ni la exposición ni el recuento («Send plan no recibe nada»). El filtro es ahora un **setter best-effort dentro de `push_plan`** (`filter_index`), como binning/gain/offset/dither, y la GUI **no** inventa una ranura: si el filtro del plan no está en la rueda, el filtro se deja como está y la lectura de vuelta lo dice. NINA aplica el filtro en `start_capture`, también best-effort.

**Revisión (2026-10-17, NINA/PINS se dice que está en pruebas)**: CCDciel es
hoy el backend **completo**; el de NINA/PINS funciona pero le quedan cosas (la
lista está en el capítulo 05 de la guía: snapshot de una exposición, sin
staging persistente, goto astrométrico que exige un solver en NINA). El
observador tiene que leerlo **antes** de elegir, no después del primer fallo:
lo dice la ayuda del ajuste (**Ajustes → Integraciones**), la línea de la
consola del observatorio cuando ese backend está seleccionado, la guía (con la
**0.2** como horizonte y el gestor de incidencias para lo que falte) y las
notas de la versión. El resto está previsto para la **0.2**.

**Review (2026-10-17, NINA/PINS is said to be in test)**: CCDciel is the
**complete** backend today; NINA/PINS works but still has gaps (the list is in
chapter 05 of the guide: a one-exposure snapshot, no persistent staging, an
astrometric goto that needs a solver configured in NINA). The observer has to
read it **before** choosing, not after the first failure: the setting's own help
(**Tools → Settings → Integrations**), the observatory console's line when that
backend is selected, the guide (with **0.2** as the horizon and the issue
tracker for whatever is missing) and the release notes all say it. The rest is
planned for **0.2**.
