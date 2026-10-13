# ADR-083: La receta de captura (dither, autofocus, cámara) y por qué esos números

**Estado / Status**: Accepted · **Fecha / Date**: 2026-10-13

## Español

**Contexto**: el paso Captura ya decide el número de tomas, la exposición y el
filtro, y exporta la secuencia; ADR-081 añadió el control en vivo del
observatorio. Faltaba lo que de verdad separa una captura buena de una mediocre:
**cada cuánto se reenfoca y si se hace dithering**, más los ajustes de cámara
(ganancia, offset, binning). El observador lo pidió con una condición: los
valores recomendados no pueden salir «porque sí»; tienen que estar **apoyados y
razonados**, porque de ellos depende la calidad (máxima relación señal/ruido,
mejor FWHM). Y el tipo de objeto cambia la respuesta: no es lo mismo seguir un
NEO, una supernova o un tránsito.

**Decisión**:

1. **Una tarjeta «Capture options»** en el paso Captura, guardada en el `plan`
   del proyecto, con: dithering (on/off, cada N tomas, amplitud en px,
   asentamiento), autofocus (on/off, cada T minutos, por ΔT °C, al cambiar de
   filtro), retardo entre tomas y de arranque, y ganancia/offset/binning.
2. **Los valores por defecto los propone `core/capture_recipe.py`**, que decide
   por el tipo de objeto y la física, no por una tabla fija:
   - **Dithering**: los píxeles calientes y el **ruido de patrón fijo** están
     quietos en el sensor; mover el campo hace que caigan en píxeles distintos
     y el recorte sigma (o la mediana) los elimina. Sin dither se suman y dejan
     *walking noise*. Amplitud **5–15 px** (más, 10–20, con cámara de color o
     escala de placa gruesa, donde un desplazamiento pequeño cruza menos
     píxeles); frecuencia **cada 1–3 tomas** (el coste es el asentado del
     guiado). **NEO/cometa/PCCP/alerta**: sin dither explícito, porque el objeto
     ya se mueve respecto a las estrellas y el campo cambia solo. **Tránsito /
     HADS / variable**: sin dither durante el run, porque los huecos rompen la
     curva; antes del run.
   - **Autofocus**: el tubo se contrae al enfriarse y cada filtro tiene su punto
     de foco, así que el foco se va. Una estrella desenfocada tiene mayor
     **FWHM**: la misma luz en más píxeles da menos pico y peor SNR en una
     apertura fija, y el centroide se vuelve menos fiable. Cadencia por **ΔT
     ≈ 1 °C**, cada **30–60 min**, tras cambio de filtro y meridian flip.
     **Tránsito / HADS**: reenfocar **solo antes del run**, nunca a mitad.
   - **Cámara**: ganancia y offset del perfil (0 = dejar la cámara como está);
     binning el del perfil (un 2×2 cambia la escala de placa y la pista del
     solver, así que es decisión del observador, y el veredicto de muestreo ya
     dice cuándo el sensor está sobremuestreado).
3. **La sub-exposición no se duplica**: ya tiene sus tablas en
   `core/exposure.py` (regímenes de SN y tránsito) con la misma filosofía de
   «punto de partida, se afina con una toma de prueba». La receta **apunta al
   criterio** (`explain.SUBEXPOSURE`): el cielo por píxel debe superar unas
   diez veces el cuadrado del ruido de lectura (en electrones, con la ganancia)
   y el pico no puede pasar el techo de linealidad (ADR-066); la buena es la
   menor de las dos, y la profundidad sale de sumar muchas (SNR ∝ √(N·t)).
4. **Las definiciones viven en `core/explain.py`** (dos densidades, ADR-058):
   `DITHER`, `AUTOFOCUS`, `SUBEXPOSURE`. La tarjeta las enseña en un ⓘ y el
   observador puede sobrescribir cualquier valor.
5. **Dónde aterrizan**:
   - **Secuencia exportada** (la vía fuerte): CCDciel `.targets` escribe
     `Dither`/`DitherCount`/`Autofocus`/`AutofocusCount`/`AutofocusStart`/
     `AutofocusTemp`/`Delay` y `Gain`/`Offset`/`Binning` por paso; el JSON de
     NINA los lleva en `Metadata.Capture`.
   - **En vivo**: CCDciel `Capture_setdither`, `Camera_SetGain/SetOffset`,
     `Capture_setbinning`; NINA `set-binning` y `capture?gain=`. La **cadencia
     de autofocus no está en la API** de ninguno de los dos: vive en la
     secuencia.
   - **Cargar la secuencia nativa en remoto** (CCDciel `Sequence_start`, NINA
     `/sequence/load`+`/sequence/start`) queda **pendiente de validar** contra
     instancias reales; no se finge.

**Limitaciones (a propósito)**:

- La **sub-exposición no se recalcula** aquí: se apoya en las tablas existentes
  y en el criterio explicado, porque el número exacto depende del cielo de esa
  noche (que se afina con una toma de prueba, como ya dice la app).
- La **cadencia de autofocus** y el **dithering por tomas** solo llegan por la
  secuencia; en vivo, CCDciel acepta el dither y NINA no (su snapshot es de una
  toma).
- El **binning** recomendado es el del perfil: cambiarlo es del observador.
- NINA no admite ganancia por plan salvo en el snapshot (`capture?gain=`); el
  offset no tiene setter directo.

**Referencias**: Howell, *Handbook of CCD Astronomy* (relación señal/ruido,
ruido de lectura, cielo limitado); la guía de fotometría de la AAVSO (cadencia,
defoco, saturación); la documentación de dithering de DeepSkyStacker y
PixInsight (por qué se mueve el campo y cómo lo elimina el recorte); la guía de
astrometría del MPC (que `core/track_stack.py` ya cita para el dither); y las
docs de CCDciel y NINA para las instrucciones de secuencia.

**Consecuencias**: `core/capture_recipe.py` nuevo; `core/explain.py` gana
`DITHER`/`AUTOFOCUS`/`SUBEXPOSURE`; `core/sequence.py` (`make_plan` +
`export_ccdciel`/`export_nina`) escribe las opciones; `ccdciel.py`/`nina.py`
aplican en vivo lo que pueden; `main_window.py` la tarjeta y el guardado en el
plan; tests del motor por tipo, de la secuencia y de la tarjeta; i18n, guía y
web.

## English

**Context**: the Capture step already decides the frame count, exposure and
filter, and exports the sequence; ADR-081 added live observatory control. What
was missing is what really separates a good capture from a mediocre one: **how
often to refocus and whether to dither**, plus the camera settings (gain,
offset, binning). The observer asked for it with one condition: the recommended
values cannot come "just because"; they must be **grounded and reasoned**,
because the quality depends on them (maximum signal-to-noise, best FWHM). And
the object type changes the answer: an NEO, a supernova and a transit are not
the same.

**Decision**:

1. **A "Capture options" card** in the Capture step, stored in the project's
   `plan`, with: dithering (on/off, every N frames, amplitude in px, settle),
   autofocus (on/off, every T minutes, on a ΔT °C, on filter change), inter-frame
   and start delay, and gain/offset/binning.
2. **The defaults are proposed by `core/capture_recipe.py`**, which decides from
   the object type and the physics, not a fixed table:
   - **Dithering**: hot pixels and **fixed-pattern noise** sit still on the
     sensor; moving the field makes them land on different pixels and a sigma
     clip (or the median) drops them. Without dither they add up and leave
     walking noise. Amplitude **5–15 px** (more, 10–20, with a colour camera or
     a coarse plate scale, where a small nudge crosses fewer pixels); cadence
     **every 1–3 frames** (the cost is the guide settle). **NEO/comet/PCCP/
     alert**: no explicit dither, because the object already moves against the
     stars and the field shifts by itself. **Transit / HADS / variable**: no
     dither during the run, because the gaps break the curve; before the run.
   - **Autofocus**: the tube contracts as it cools and every filter has its
     focus point, so focus drifts. A defocused star has a larger **FWHM**: the
     same light over more pixels gives a lower peak and worse SNR in a fixed
     aperture, and the centroid becomes less reliable. Cadence on **ΔT ≈ 1 °C**,
     every **30–60 min**, after a filter change and a meridian flip. **Transit /
     HADS**: refocus **only before the run**, never in the middle.
   - **Camera**: gain and offset from the profile (0 = leave the camera as it
     is); binning from the profile (a 2×2 changes the plate scale and the
     solver's hint, so it is the observer's call, and the sampling verdict
     already says when the sensor is oversampled).
3. **The sub-exposure is not duplicated**: it already has its tables in
   `core/exposure.py` (SN and transit regimes) with the same "starting point,
   refined with a test shot" philosophy. The recipe **points at the criterion**
   (`explain.SUBEXPOSURE`): the sky per pixel must beat about ten times the
   square of the read noise (in electrons, from the gain) and the peak cannot
   pass the linearity ceiling (ADR-066); the right one is the lesser of the two,
   and depth comes from adding many (SNR ∝ √(N·t)).
4. **The definitions live in `core/explain.py`** (two densities, ADR-058):
   `DITHER`, `AUTOFOCUS`, `SUBEXPOSURE`. The card shows them in an ⓘ and the
   observer can override any value.
5. **Where they land**:
   - **Exported sequence** (the strong path): CCDciel `.targets` writes
     `Dither`/`DitherCount`/`Autofocus`/`AutofocusCount`/`AutofocusStart`/
     `AutofocusTemp`/`Delay` and `Gain`/`Offset`/`Binning` per step; NINA's JSON
     carries them in `Metadata.Capture`.
   - **Live**: CCDciel `Capture_setdither`, `Camera_SetGain/SetOffset`,
     `Capture_setbinning`; NINA `set-binning` and `capture?gain=`. The
     **autofocus cadence is not in either API**: it lives in the sequence.
   - **Loading the native sequence remotely** (CCDciel `Sequence_start`, NINA
     `/sequence/load`+`/sequence/start`) is **pending validation** against real
     instances; it is not faked.

**Limitations (on purpose)**:

- The **sub-exposure is not recomputed** here: it leans on the existing tables
  and the explained criterion, because the exact number depends on that night's
  sky (refined with a test shot, as the app already says).
- The **autofocus cadence** and **per-frame dithering** only reach the program
  through the sequence; live, CCDciel accepts the dither and NINA does not (its
  snapshot is one frame).
- The **recommended binning** is the profile's: changing it is the observer's.
- NINA has no per-plan gain except on the snapshot (`capture?gain=`); the offset
  has no direct setter.

**References**: Howell, *Handbook of CCD Astronomy* (signal-to-noise, read
noise, sky-limited); the AAVSO photometry guide (cadence, defocus, saturation);
the DeepSkyStacker and PixInsight dithering documentation (why the field moves
and how rejection removes it); the MPC astrometry guidance (which
`core/track_stack.py` already cites for dither); and the CCDciel and NINA docs
for the sequence instructions.

**Consequences**: new `core/capture_recipe.py`; `core/explain.py` gains
`DITHER`/`AUTOFOCUS`/`SUBEXPOSURE`; `core/sequence.py` (`make_plan` +
`export_ccdciel`/`export_nina`) writes the options; `ccdciel.py`/`nina.py` apply
live what they can; `main_window.py` the card and its save into the plan; tests
for the engine by kind, the sequence and the card; i18n, guide and website.

**Revisión (2026-10-13, valores sugeridos y brillo de cielo)**: la receta pasa
a sugerir también la **sub-exposición** y el **nº de tomas**, y los dos bloques
del paso Captura («Exposure plan» y «Capture options and calibration») salen
**pre-rellenados** en un proyecto **sin plan guardado**; en cuanto el observador
cambia algo, sus valores se mantienen (un flag `suggested` lo distingue) y el
botón **«Set suggested values»** los vuelve a aplicar. Un **«?»** por bloque
abre un diálogo con el porqué y **los números usados** (ADR-058). La
sub-exposición sale de la tabla de brillo del objeto, **acortada** (nunca
alargada) por el **techo de linealidad** de la cámara (`min(cam_full_well_e,
cam_linearity_adu × ccd_gain)`, el guardián para las sCMOS de poco full well
tipo QHY42/GSENSE400) y por la **escala de placa** (píxeles grandes o focal
corta saturan antes), respetando el mínimo/máximo de la cámara y el **tope sin
traza**; y se comprueba contra el **ruido de lectura** (cielo ≳ 10×RON²). El
brillo de cielo del sitio entra por un **campo nuevo** (mag/arcsec², editable) y,
si hay **clave opcional de lightpollutionmap.info** (`core/sources/lightpollution.py`,
caché 30 días), se **auto-rellena** desde el atlas (Falchi 2016 / NASA Black
Marble) con la conversión documentada; sin clave, el observador lo lee del mapa
(el botón lo abre centrado en el sitio). Límites: el valor del atlas es
**cenital** y «mejor caso» (VIIRS casi ciego al azul), y la constante de
referencia del techo (`REF_LINEARITY_E`) y la de electrones de cielo quedan en
un único punto para calibrarlas.

**Revision (2026-10-13, suggested values and sky brightness)**: the recipe now
also suggests the **sub-exposure** and the **frame count**, and the Capture
step's two blocks ("Exposure plan" and "Capture options and calibration") open
**pre-filled** on a project **with no saved plan**; as soon as the observer
changes something, their values are kept (a `suggested` flag tells them apart)
and the **"Set suggested values"** button re-applies them. A **"?"** per block
opens a dialog with the reason and **the numbers used** (ADR-058). The
sub-exposure comes from the object's brightness table, **shortened** (never
lengthened) by the camera's **linearity ceiling** (`min(cam_full_well_e,
cam_linearity_adu × ccd_gain)`, the guard for the low-full-well sCMOS such as
QHY42/GSENSE400) and by the **plate scale** (big pixels or a short focal length
saturate sooner), respecting the camera's minimum/maximum and the
**trail-free cap**; and it is checked against the **read noise** (sky ≳
10×RON²). The site's sky brightness enters through a **new field**
(mag/arcsec², editable) and, with an **optional lightpollutionmap.info key**
(`core/sources/lightpollution.py`, 30-day cache), is **auto-filled** from the
atlas (Falchi 2016 / NASA Black Marble) with the documented conversion; without
a key, the observer reads it off the map (the button opens it centred on the
site). Limits: the atlas value is **zenith** and "best case" (VIIRS nearly blind
to blue), and the ceiling reference constant (`REF_LINEARITY_E`) and the sky
electrons constant live in one place to be calibrated.

**Review (2026-10-13, gain/offset are the camera's, not the system's)**: the
`gain`/`offset` of a plan are the camera's OWN settings (its gain index and
offset), defaulted from what the observatory reports when connected (CCDciel
`Camera_GetGain`/`Camera_GetOffset`; NINA `camera/info` Gain/Offset), and never
the system gain in **e-/ADU** (a photometry quantity, used only for the
linearity ceiling and the read-noise maths). They are sent live only when they
differ from what the camera already has.

**Revisión (2026-10-13, gain/offset son de la cámara, no del sistema)**: el
`gain`/`offset` de un plan son los ajustes PROPIOS de la cámara (su índice de
ganancia y su offset), por defecto los que reporta el observatorio si hay
conexión (CCDciel `Camera_GetGain`/`Camera_GetOffset`; NINA `camera/info`), y
nunca la ganancia del sistema en **e-/ADU** (una cantidad de fotometría, usada
solo para el techo de linealidad y el ruido de lectura). Se envían en vivo solo
si difieren de lo que ya tiene la cámara.

**Review (2026-10-13, the frame count is stable)**: the frame count fills the
object's **visibility span** (`window_start`→`window_end`), not the safe window:
the safe window only lands in the context once a plan is saved, which used to
make the suggested count flip between a default and the cap on each press. The
GUI ensures the span (via `planner.safe_window_for`) before the recipe runs, so
the number is the same every time; with no window at all it is a plain default
(30), and the ceiling is the control's own maximum (999).

**Revisión (2026-10-13, el nº de tomas es estable)**: el nº de tomas llena el
**span de visibilidad** del objeto (`window_start`→`window_end`), no la ventana
segura: la ventana segura solo aparece en el contexto cuando ya se ha guardado un
plan, y eso hacía que el número sugerido oscilara entre un defecto y el tope en
cada pulsación. La GUI asegura el span (vía `planner.safe_window_for`) antes de
que corra la receta, así que el número es el mismo siempre; sin ventana alguna
es un defecto simple (30), y el techo es el máximo del propio control (999).

**Review (2026-10-13, the frame count is bounded by the field, and the download is its own number)**: the frame count used to fill the object's whole visibility span (`_n_frames`), so a fast NEO on a small sensor was offered hundreds of frames it would spend with the object out of the picture. Two changes, no change to the measurement.

1. **The field crossing caps the run.** A moving object (`neo`, `comet`, `pccp`, `alert`) is centred by the goto, so it has **half the short side** of the sensor before it reaches the edge; a margin of 15% (`FIELD_TRAVEL_FRACTION`) absorbs the ephemeris and pointing error, because a frame with the object off the field is a lost frame. The crossing time comes from the camera preset's sensor size and the focal length (`exposure.fov_arcmin`, 206265·sensor_mm/focal_mm) and the object's apparent rate; the frame count is `min(span, crossing)`. The short side is used because the direction of motion is unknown. Three honest states, said instead of pretended: `field` (the crossing binds, with the field, the rate and the crossing time in the "?" dialog), `field_unknown` (the object moves but the field or the rate is unknown: without a camera preset there is no field of view, because the config does not carry the sensor size on its own), and `field_short` (the crossing does not fit even the five-frame floor: the honest count is returned, ≥1).
2. **The readout/download is its own number.** The per-frame time was a single global `overhead_s`; the download is never immediate and depends on the camera and the link, so the camera profile now carries `cam_readout_s` (datasheet `readout_s` in `assets/cameras.toml`, overridable in Settings) and `overhead_s` is re-scoped to the mount **slew/settle**. `exposure.frame_overhead_s(cfg)` = readout + settle is the ONE source for the recipe, `sequence.make_plan`, the window chip and the "?" dialog, so the wall clock and the frame count can never disagree. A camera whose datasheet does not publish a readout time leaves the key empty (the observer sets it); nothing is invented.

**Consequences**: the recipe gains `field_arcmin` and `field_crossing_s`; `explain.FIELD_CROSSING` explains the reasoning (ADR-058); the GUI's NEO hint shows the crossing time next to the trail-free cap. `sequence.make_plan` now derives its per-frame overhead from `cfg` when it is not passed explicitly. The bundled catalogue has the `readout_s` field documented but no values yet: the observer fills their camera's, which is the honest state (a datasheet readout time is mode- and interface-dependent).

**Revisión (2026-10-13, el número de tomas se acota por el campo, y la descarga es su propio número)**: el número de tomas llenaba toda la ventana de visibilidad (`_n_frames`), así que a un NEO rápido en un sensor pequeño se le ofrecían cientos de tomas que pasaría con el objeto fuera del encuadre. Dos cambios, sin tocar la medida.

1. **El cruce del campo acota la serie.** Un objeto en movimiento (`neo`, `comet`, `pccp`, `alert`) lo centra el goto, así que dispone de **media altura del lado corto** del sensor antes de llegar al borde; un margen del 15% (`FIELD_TRAVEL_FRACTION`) absorbe el error de efeméride y de punta, porque una toma con el objeto fuera del campo es una toma perdida. El tiempo de cruce sale del tamaño de sensor del preset y la focal (`exposure.fov_arcmin`, 206265·sensor_mm/focal_mm) y la velocidad aparente del objeto; el número de tomas es `min(span, cruce)`. Se usa el lado corto porque la dirección del movimiento es desconocida. Tres estados honestos, dichos en vez de aparentados: `field` (manda el cruce, con el campo, la velocidad y el tiempo de cruce en el diálogo «?»), `field_unknown` (el objeto se mueve pero no se conoce el campo o la velocidad: sin preset de cámara no hay campo, porque el config no guarda el tamaño del sensor por sí solo) y `field_short` (el cruce no da ni para el mínimo de cinco tomas: se devuelve el número honesto, ≥1).
2. **La lectura/descarga es su propio número.** El tiempo por toma era un único `overhead_s` global; la descarga nunca es inmediata y depende de la cámara y del enlace, así que el perfil de cámara ahora lleva `cam_readout_s` (campo `readout_s` del datasheet en `assets/cameras.toml`, sobrescribible en Ajustes) y `overhead_s` se re-scopa al **slew/asentamiento** de la montura. `exposure.frame_overhead_s(cfg)` = lectura + asentamiento es la ÚNICA fuente para la receta, `sequence.make_plan`, el chip de ventana y el diálogo «?», de modo que el reloj y el número de tomas no pueden discrepar. Una cámara cuyo datasheet no publica tiempo de lectura deja la clave vacía (la pone el observador); no se inventa nada.

**Consecuencias**: la receta gana `field_arcmin` y `field_crossing_s`; `explain.FIELD_CROSSING` explica el razonamiento (ADR-058); la pista de NEO de la GUI muestra el tiempo de cruce junto al tope sin traza. `sequence.make_plan` deriva ahora su overhead por toma de `cfg` cuando no se le pasa explícitamente. El catálogo incluido documenta el campo `readout_s` pero aún sin valores: el observador pone el de su cámara, que es el estado honesto (un tiempo de lectura de datasheet depende del modo y de la interfaz).

**Review (2026-10-13, the defaults stop starving the frame count)**: with the readout split out to its own per-camera number, the per-frame `overhead_s` default of 15 s no longer had a reason to exist (it was the old readout + slew figure), and on short exposures it dominated the count: at a fast object's trail-capped sub-second exposure, 15 s of overhead meant roughly three times fewer frames than the rig really fits. The default is now **5 s** (`config.DEFAULTS["overhead_s"]` and `exposure.DEFAULT_OVERHEAD_S`, with `sequence.make_plan`'s no-config fallback using the same constant), which is the mount SETTLE alone. And the field-crossing margin `FIELD_TRAVEL_FRACTION` goes from 0.85 to **0.95**: the astrometric goto absorbs the pointing error by plate-solving, so the margin only covers the ephemeris uncertainty (a preliminary orbit can still be arcminutes off, which is said in the constant's comment). Measured effect on the author's setup (imx571 + 2000 mm, 30″/min): about 87 → about 230 frames, a change of the same order as the observer's own experience.

**Revisión (2026-10-13, los defectos dejan de matar de hambre al recuento)**: al separar la lectura a su propio número por cámara, el `overhead_s` por defecto de 15 s ya no tenía motivo (era la cifra antigua de lectura + slew) y en exposiciones cortas dominaba el recuento: con la exposición sub-segundo que impone el tope de traza de un objeto rápido, 15 s de overhead significaban unas tres veces menos tomas de las que el equipo realmente admite. El defecto pasa a **5 s** (`config.DEFAULTS["overhead_s"]` y `exposure.DEFAULT_OVERHEAD_S`, con el fallback sin config de `sequence.make_plan` usando la misma constante), que es SOLO el asentamiento de la montura. Y el margen del cruce de campo `FIELD_TRAVEL_FRACTION` pasa de 0.85 a **0.95**: el goto astrométrico absorbe el error de punta resolviendo la placa, así que el margen solo cubre la incertidumbre de efeméride (una órbita preliminar puede estar aún a minutos de arco, y así se dice en el comentario de la constante). Efecto medido en el equipo del autor (imx571 + 2000 mm, 30″/min): de unas 87 a unas 230 tomas, un cambio del orden del que el observador tiene en su experiencia.

**Review (2026-10-13, ONE per-frame overhead: the "Readout + download" field)**: the per-frame time was `cam_readout_s + overhead_s` (a per-camera readout plus a global mount settle). Two numbers for one thing was the complication: the global 5 s settle was too much for a USB3 camera, and it hid where to change it. The settle is retired: `exposure.frame_overhead_s(cfg)` returns **`cam_readout_s` alone** (the "Readout + download" field, config key `cam_readout_s`), with a documented fallback `DEFAULT_READOUT_S = 2.0` for a camera with no preset. The `overhead_s` config key and its Settings field are gone; the recipe, `sequence.make_plan`, the transit/HADS cadences and the window chip all read the one number. The catalogue now carries a `readout_s` per preset, an ESTIMATE by sensor type and size for USB3 (a fast CMOS/sCMOS is download-bound, 0.5-3 s; a CCD is bound by its serial readout, 3-8 s), and the observer raises it in the same field if the mount must also settle. Measured effect on the author's setup (imx571, 2000 mm, 30″/min): the per-frame overhead drops from 5 s to 1.5 s, and the suggested frames rise accordingly.

**Revisión (2026-10-13, UN solo overhead por toma: el campo «Readout + download»)**: el tiempo por toma era `cam_readout_s + overhead_s` (la lectura por cámara más un asentamiento global). Dos números para una sola cosa era la complicación: los 5 s globales eran demasiado para una cámara USB3 y escondían dónde cambiarlo. El asentamiento se retira: `exposure.frame_overhead_s(cfg)` devuelve **solo `cam_readout_s`** (el campo «Readout + download», clave `cam_readout_s`), con un respaldo documentado `DEFAULT_READOUT_S = 2.0` para una cámara sin preset. La clave `overhead_s` y su campo de Ajustes desaparecen; la receta, `sequence.make_plan`, las cadencias de tránsito/HADS y el chip de ventana leen el único número. El catálogo lleva ahora un `readout_s` por preset, una ESTIMACIÓN por tipo y tamaño de sensor para USB3 (un CMOS/sCMOS rápido está dominado por la descarga, 0.5-3 s; un CCD por su lectura en serie, 3-8 s), y el observador lo sube en el mismo campo si la montura necesita además asentarse. Efecto medido en el equipo del autor (imx571, 2000 mm, 30″/min): el overhead por toma baja de 5 s a 1,5 s, y las tomas sugeridas suben en consecuencia.
