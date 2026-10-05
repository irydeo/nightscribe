# ADR-062: Astrometría por track & stack y validación (reabre ADR-022)

**Estado / Status**: Accepted · **Fecha / Date**: 2026-10-04

## Español

**Contexto**: ADR-022 decidió que NightScribe **no hace astrometría**: el usuario
mide con su software externo y pega el resultado, y la app solo valida y
empaqueta. El plan de astrometría de cuerpos menores (`docs/PLANS/astrometry-minor-planets/`)
invierte esa decisión para los objetos **con efemérides**, porque el valor está en
cerrar el bucle dentro de la app: calibrar, apilar guiando el movimiento, medir y
reportar. El referente del ramo es **Tycho-Tracker**, la herramienta que el MPC
documenta para el apilado de objetos débiles (synthetic tracking).

**Decisión**:

1. **Alcance**: solo **tracking directo** (NEO, cometa, PCCP con elementos). La
   búsqueda a ciegas (grid search) queda fuera, con el hueco previsto en el
   motor.
2. **Pipeline**: calibración (ADR-061) → ingesta con `T_mid` (media exposición) →
   solve del primer frame con ASTAP y **WCS compuesto** por registro para el
   resto → apilado guiado por la **posición efemérica de cada frame** (Horizons) →
   barrido de velocidad → detección → medida → validación → reporte.
3. **Medida doble**: centroide sobre el stack final y medida por frame, con el
   **mismo** centroide (photutils) para que la comparación tenga sentido. Si
   difieren más de 0,5″ o 3σ, el punto se marca y se avisa; nunca se elige una
   vía en silencio. La posición reportada por defecto es la del stack.
4. **Barrido de fine-tuning**: micro-cuadrícula 5×5 (±5 %) alrededor de la
   velocidad teórica, con score **SNR × redondez** (segundos momentos). Se hace
   **una vez** sobre la secuencia y se aplica a todos los grupos.
5. **Dos umbrales, no uno**: la puerta de **detección** (3,5σ, configurable)
   decide si hay algo y si se barre; el listón de **envío** es **SNR ≥ 20 por
   observación** (configurable), que es la recomendación explícita del MPC. Por
   debajo, no se genera el reporte y se explica por qué.
6. **Varias observaciones por secuencia**: el usuario dice cuántas quiere y el
   software reparte la secuencia en grupos contiguos de igual número de frames.
   Cada grupo es una observación con su `T_mid` y su `q_g` propios (la posición
   efemérica **de su instante**, no la del primero). El reporte lleva N líneas.
7. **Validación en tres piezas**: secuencia centrada en el objeto (GIF/montaje
   con las N observaciones), aviso de **dithering** (el ruido de patrón se apila
   y fabrica detecciones fantasma) y **chequeo contra otros observadores**.
8. **El chequeo se delega en Find_Orb**: NightScribe baja las observaciones del
   objeto (MPC Observations API, o NEOCP si no está confirmado), escribe el
   fichero con las nuestras y las de los demás, y lanza el `fo` **excluyendo las
   nuestras del ajuste** (leave-one-out). Decide sobre los residuos que Find_Orb
   devuelve: normaliza con nuestra incertidumbre y la dispersión robusta de los
   demás (ventana ±30 días, excluyendo nuestro código de observatorio) y bloquea
   si es outlier, con opción de forzar. **El chequeo filtra, no demuestra** (el
   propio MPC avisa de que en un arco corto una observación errónea encaja
   igual), y **sin referencia no bloquea**.
9. **Find_Orb es externo y se instala guiado** (patrón de ADR-052): en
   Linux/macOS, micromamba privado + `findorb` de conda-forge; en Windows, los
   binarios de Project Pluto. **No se empaqueta en el instalador** (GPLv2 con una
   cláusula extra de uso comercial, y el peso de las efemérides DE430t). Sin
   Find_Orb, el chequeo **no está disponible** y se dice. El botón **Instalar…**
   de Ajustes (`core/findorb_install.py`) recorre el camino en el orden que
   ahorra más trabajo: si `fo` ya está en el PATH apunta la ruta y lo dice (el
   caso habitual), si hay **micromamba/mamba/conda** ofrece el comando exacto
   (entorno privado con `-p`, dentro de una carpeta elegida por el observador) y
   lo ejecuta con su log a la vista, y si no hay gestor **da la guía** y se
   para: descargar y ejecutar un binario de internet no es una decisión que la
   app tome por el usuario.
10. **Reporte**: ADES PSV y MPC 80 columnas, con `T_mid`, magnitud calibrada
    **solo si hay comparsas** (si no se omite) e incertidumbres `rmsRA`/`rmsDec`
    propagadas. Se valida con el validador de ADR-022 (ida y vuelta).
11. **Persistencia**: tablas nuevas `astrometry_runs`, `astrometry_points` y
    `astrometry_frames` (migración v17), con **Undo por ejecución**. El stack se
    guarda como fichero del proyecto.
12. **Disciplina de memoria**: mmap + lectura por `section` de la ROI
    (`BSCALE`/`BZERO` a mano), float32 en frames y float64 en acumuladores, ROI
    cacheada para el barrido, franjas solo para el stack final a frame completo, y
    liberación explícita por grupo.
13. **Liberar espacio** (opt-in, nunca automático): mover los originales usados a
    `procesados` dentro del proyecto (recuperable) y borrar aparte los calibrados
    exportados, con manifiesto en la base de datos.
14. **El brillo se mide sobre los apilados, no sobre las tomas**: el objeto en
    **su** apilado, donde su luz está concentrada, y las comparsas en un
    **segundo apilado** de las mismas tomas alineado en las estrellas, porque en
    el apilado del objeto son trazos y un trazo no calibra nada. Es la receta de
    Tycho-Tracker, y se implementa reutilizando la receta de placa que ya
    existía (`photometry.measure_plate`, con `comp_image`, una llamada por
    observación): el punto cero, el término de color, el error y el veredicto de
    la estrella de control no se escriben de nuevo. La receta (aperturas, método
    de cielo, centroide, color) es la de la pestaña Fotometría, leída **en vivo**
    y mostrada antes de lanzar: un solo editor en la app. Cuesta una pasada más
    de apilado, así que es opcional y, sin ella, la ejecución reporta solo
    posiciones y lo dice. Medido en 2025 UR (60 tomas, dos observaciones):
    **17,92 G** contra los 18,0 que el MPC publicó esa misma noche.
15. **Lectura y corrección de las ejecuciones**: la pestaña **Análisis** del
    proyecto lista las ejecuciones (fecha, observaciones, movimiento,
    magnitud, comprobación, estado) con la magnitud diciendo **quién la
    escribió** (`mag_auto` frente a `mag_source`, migración v18): la ejecución
    escribe la suya como automática, y el observador puede **enviar** al
    reporte la que midió a mano en la pestaña Fotometría, que pasa a ser la
    efectiva mientras la automática se conserva al lado. Desde la lista se
    abre la visita en el editor o se deshace una ejecución entera. Una
    ejecución **sin detección** también se lista: «se buscó y no había nada»
    es un dato, y la noche siguiente necesita saberlo.

**Reapertura de ADR-022**: NightScribe **ahora sí genera medidas**, acotado a
objetos conocidos, con el usuario como revisor y remitente. El validador y el
empaquetado de ADR-022 **se conservan** y pasan a ser la puerta del reporte
generado.

**Alternativas**: seguir sin generar medidas (rechazado por el autor: el valor
está en cerrar el bucle); reimplementar el ajuste de órbitas para el chequeo
(rechazado: Find_Orb está probado y es lo que usa la comunidad); empaquetar
Find_Orb en el instalador (rechazado por licencia y peso).

**Consecuencias**: migraciones v16 y v17; nuevos módulos `core/calibration.py`,
`core/track_stack.py`, `core/astrometry.py`, `core/findorb.py`,
`core/findorb_env.py`, `core/mpc_astrometry.py` y `core/sources/mpc_obs.py`; dos
pestañas nuevas en el UFE; y el bloque MPC de la visita gana un camino generado.
La validación real se hace contra Tycho-Tracker sobre el mismo set (residual
< 0,3″, y < 0,1″ en el caso bueno), además de la secuencia sintética para el
motor.

## English

**Context**: ADR-022 decided that NightScribe **does no astrometry**: the user
measures with external software and pastes the result, and the app only validates
and packages. The minor-planet astrometry plan
(`docs/PLANS/astrometry-minor-planets/`) reverses that decision for objects **with
ephemerides**, because the value lies in closing the loop inside the app:
calibrate, stack following the motion, measure and report. The field's reference is
**Tycho-Tracker**, the tool the MPC documents for stacking faint objects
(synthetic tracking).

**Decision**:

1. **Scope**: **direct tracking only** (NEO, comet, PCCP with elements). Blind
   search (grid search) is out, with a hook left in the engine.
2. **Pipeline**: calibration (ADR-061) → ingestion with `T_mid` (mid-exposure) →
   first-frame solve with ASTAP and **composed WCS** by registration for the rest
   → stacking guided by the **ephemeris position of each frame** (Horizons) →
   velocity sweep → detection → measurement → validation → report.
3. **Double measurement**: centroid on the final stack and per-frame measurement,
   with the **same** centroid (photutils) so the comparison is meaningful. If they
   differ by more than 0.5″ or 3σ, the point is flagged and a warning is shown; a
   path is never chosen silently. The reported position defaults to the stack one.
4. **Fine-tuning sweep**: 5×5 micro-grid (±5 %) around the theoretical velocity,
   with an **SNR × roundness** score (second moments). Done **once** on the
   sequence and applied to all groups.
5. **Two thresholds, not one**: the **detection** gate (3.5σ, configurable)
   decides whether anything is there and whether to sweep; the **submission** bar
   is **SNR ≥ 20 per observation** (configurable), which is the MPC's explicit
   recommendation. Below it, no report is generated and the reason is explained.
6. **Several observations per sequence**: the user says how many and the software
   splits the sequence into contiguous groups of equal frame count. Each group is
   an observation with its own `T_mid` and `q_g` (the ephemeris position **of its
   instant**, not the first frame's). The report carries N lines.
7. **Validation in three pieces**: sequence centred on the object (GIF/montage
   with the N observations), **dithering** warning (pattern noise stacks into
   phantom detections) and **check against other observers**.
8. **The check is delegated to Find_Orb**: NightScribe downloads the object's
   observations (MPC Observations API, or NEOCP if unconfirmed), writes the file
   with ours and the others', and runs `fo` **excluding ours from the fit**
   (leave-one-out). It decides on the residuals Find_Orb returns: normalises by
   our uncertainty and the robust scatter of the others (±30-day window,
   excluding our observatory code) and blocks if it is an outlier, with an option
   to force. **The check filters, it does not prove** (the MPC itself warns that
   on a short arc a wrong observation fits just as well), and **without a
   reference it does not block**.
9. **Find_Orb is external and installed guided** (ADR-052 pattern): the
   Settings **Install…** button walks the shortest road first (point the path
   at an `fo` already on PATH), then offers the exact private-environment
   command when a package manager is present, and otherwise **gives the
   guide** and stops: downloading and running a binary from the internet is
   not a decision the app makes for its user. On
   Linux/macOS, a private micromamba + `findorb` from conda-forge; on Windows, the
   Project Pluto binaries. **Not bundled in the installer** (GPLv2 with an extra
   commercial-use clause, and the DE430t ephemeris weight). Without Find_Orb, the
   check is **not available** and says so.
10. **Report**: ADES PSV and MPC 80-column, with `T_mid`, calibrated magnitude
    **only if comparisons exist** (otherwise omitted) and propagated
    `rmsRA`/`rmsDec`. Validated with the ADR-022 validator (round trip).
11. **Persistence**: new tables `astrometry_runs`, `astrometry_points` and
    `astrometry_frames` (migration v17), with **undo per run**. The stack is saved
    as a project file.
12. **Memory discipline**: mmap + ROI `section` reads (`BSCALE`/`BZERO` by hand),
    float32 frames and float64 accumulators, ROI cached for the sweep, strips only
    for the full-frame final stack, and explicit release per group.
13. **Free space** (opt-in, never automatic): move the used originals to
    `procesados` inside the project (recoverable) and delete the exported
    calibrated copies separately, with a manifest in the database.
14. **The brightness is measured on the stacks, not on the frames**: the object
    on **its** stack, where its light is concentrated, and the comparisons on a
    **second stack** of the same frames aligned on the stars, because on the
    object's stack they are trails and a trail calibrates nothing. The recipe
    (apertures, sky, centroid, colour) is the Photometry tab's, read **live**;
    it costs one more stacking pass, so it is optional.
15. **Reading and correcting the runs**: the project's **Analysis** tab lists
    the runs (date, observations, motion, magnitude, check, state) with the
    magnitude saying **who wrote it** (`mag_auto` against `mag_source`,
    migration v18): the run writes its own as automatic, and the observer can
    **send** the one they measured by hand in the Photometry tab to the report,
    which becomes the effective one while the automatic is kept beside it. From
    the list a visit opens in the editor or a whole run is undone. A run with
    **no detection** is listed too: "we looked and there was nothing" is data.

**Reopening ADR-022**: NightScribe **now does generate measurements**, bounded to
known objects, with the user as reviewer and sender. ADR-022's validator and
packaging **are kept** and become the gate for the generated report.

**Alternatives**: keep not generating measurements (rejected by the author: the
value is in closing the loop); reimplement orbit fitting for the check (rejected:
Find_Orb is proven and is what the community uses); bundle Find_Orb in the
installer (rejected for licence and weight).

**Consequences**: migrations v16 and v17; new modules `core/calibration.py`,
`core/track_stack.py`, `core/astrometry.py`, `core/findorb.py`,
`core/findorb_env.py`, `core/mpc_astrometry.py` and `core/sources/mpc_obs.py`;
two new tabs in the UFE; and the visit's MPC block gains a generated path. Real
validation is done against Tycho-Tracker on the same set (residual < 0.3″, and
< 0.1″ in the good case), plus the synthetic sequence for the engine.
