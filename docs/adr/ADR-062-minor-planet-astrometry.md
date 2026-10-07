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
16. **Ningún fotograma se tira en silencio**: la puerta de registro se juzga
    como **fracción del FWHM medido** (0,25, con suelo en 0,5 px), no contra
    un píxel fijo, porque lo que importa es cuánto ensancha el apilado, y eso
    es una razón; y una traslación que no explica las estrellas se reintenta
    con **rotación** (hasta 15°, y con las estrellas certificándola: el atajo
    de correlación dice «es el mismo cielo», nunca «este es el mapeo»). El
    informe dice cuántas tomas volvieron, cómo, **por qué** fallaron las que
    fallaron y si la visita es en realidad **varias tandas**, con su salto y
    su hueco de tiempo. Medido en 2025 UR: de 78 a 139 tomas usables de 140,
    y el SNR del apilado de estrellas de 1.826 a 2.702 (×1,48).
    **Y un fotograma que no contiene el objeto se deja fuera y se cuenta**
    (`track_stack.inside_frame`): registrado no es lo mismo que útil, y
    apilar un campo desplazado añade ruido justo donde se mide. Recuperar
    las dos tandas hizo visible un fallo que antes era inalcanzable: la
    región fuente de una caja podía caer entera fuera del sensor,
    `calibration.read_image` devolvía un array 1-D vacío y scipy tomaba la
    rotación 2×2 por una matriz homogénea («Expected homogeneous
    transformation matrix with shape (2, 2) for image shape (0,)»). Ahora
    `_source_box` dice que no hay solape, `_warp_to_box` devuelve un marco
    inválido **sin leer**, y la lectura nunca devuelve 1-D.
17. **Co-adición ponderada por 1/σ²**, como método **opcional** además de
    suma/media/mediana/sigma (el defecto no cambia: la medida dice que en
    una noche estable no compensa). El ruido de cada toma se mide de su
    propio cielo (MAD escalada) **durante el registro**, que ya lee los
    píxeles, y el peso es el inverso de su varianza, que es la combinación
    lineal óptima de medidas con ruido distinto. El método nuevo es **el
    mismo recorte sigma y después la media ponderada de las supervivientes**
    (el recorte se comparte, así que ambos rechazan los mismos píxeles), y
    sin pesos es idéntico al sigma-clipped probado. Medido: en 2025 UR el
    ruido entre tomas varía un 4 % (ganancia 1,003×) y en 2026 PY9 un 11 %
    (ganancia 1,022×); con una décima parte de las tomas al triple de ruido
    la ganancia sería del 28 %. Es un seguro para la noche que se rompe, y
    además es el modelo de ruido que el filtro adaptado necesita.
18. **Medida por filtro adaptado y la estela, como segunda opinión medida**:
    con una forma `m` conocida (que suma uno) y ruido `σ` por píxel, el mejor
    estimador lineal del flujo es `Σ(m(p−cielo))/Σ(m²)` y su SNR es el mayor
    que cualquier filtro lineal alcanza (Cauchy-Schwarz); una apertura es el
    caso `m = 1`, que da a las alas el peso del núcleo. El filtro usa el
    **mismo centroide, el mismo cielo y el mismo σ** que la apertura, para
    que la comparación mida el filtro y no otra cosa, y la forma sale del
    **propio apilado del objeto** (el FWHM, de las estrellas, que en ese
    apilado son trazos), de modo que un objeto estelado se filtra con la
    línea que es. La estela se invierte de los momentos segundos
    (`σ_largo² = σ² + L²/12`) con **ventana de 2 FWHM y umbral a 1σ**,
    medidos: con 4 FWHM una estrella redonda reportaba 1,56 px. Medido en
    el apilado real de 139 tomas de 2025 UR: el filtro alcanza **1,55 a
    1,63×** el SNR de la apertura, y `√(n_ap/n_eff)` predice 1,59×. Contra un
    **catálogo real** (40 comparsas de Gaia EDR3, mag 13,5 a 19,5) el SNR es
    **1,57×** y el error del cero punto **0,0119 contra 0,0095 mag**, con la
    apertura **subestimando** la mitad débil en +0,037 mag y el filtro en
    +0,007: el filtro gana donde está el objeto débil. Desde el 2026-10-07 es
    el **método por defecto** (una sola casilla para apagarlo), y su coste
    medido se dice también: **su flujo sigue a la forma de la PSF**, así que
    donde la forma cambia por el campo (una visita con dos tandas, un campo
    con coma) lleva un sesgo de posición que la apertura no tiene (0,2 mag de
    escalón entre las dos tandas). El reporte **dice qué método midió** y
    guarda el valor de la apertura al lado; la estela se dice en palabras
    para acortar la exposición siguiente.
19. **Diagnóstico de la noche con sus propias estrellas**: la **magnitud
    límite** sale de ajustar `log10(SNR) = a + b·mag` sobre las comparsas
    medidas y resolver para SNR = 5, y el **pendiente es la comprobación**
    (la física dice −0,4; medido en 2025 UR: −0,394), así que un campo que
    no está limitado por el cielo se marca en vez de citarse. El ajuste es
    **Theil-Sen** (la mediana de las pendientes de los pares) y no mínimos
    cuadrados con recorte, porque con pocos puntos el recorte no repara una
    recta arrastrada (medido: 0,5 mag de error con una comparsa saturada).
    La **calidad de la solución** es la mediana del residual por celda de
    una rejilla 4×4: un número para toda la placa esconde las esquinas, que
    es donde se ve una escala mal o un chip inclinado, y una celda sin
    estrellas queda vacía, nunca a cero.

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

**Revisión (2026-10-05): el stack dice lo que el run midió.** El stack que el run
guarda lleva en su propia cabecera lo que la banda del editor (ADR-046) necesita para
encabezar la placa: `NS_RATE` / `NS_PA` / `NS_MOT` (el movimiento del barrido de
velocidad, o la predicción de la efeméride marcada `eph`), `NS_MAG` / `NS_MAGER` /
`NS_MAGB` / `NS_MAGNC` / `NS_MAGOK` (la magnitud de esa observación con las señales que
la colorean) y las tarjetas de la toma (`EXPTIME`, `DATE-OBS`, `FILTER`, `INSTRUME`,
`TELESCOP`) junto a `NS_NFRAM`. La posición medida ya viajaba como `NS_RA` / `NS_DEC`
(la anotación). El efecto: reabrir un stack meses después, sin el run en memoria ni la
base de datos, muestra su magnitud, su velocidad y su PA en la banda, con los mismos
colores que la fotometría.

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
16. **No frame is dropped in silence**: the registration gate is judged as a
    FRACTION of the measured FWHM (0.25, floored at 0.5 px), not against a
    fixed pixel figure, because what matters is how much it broadens the
    stack, and that is a ratio; and a translation that does not explain the
    stars is retried with a ROTATION (up to 15 deg, certified by the stars:
    the correlation fallback says "this is the same sky", never "this is the
    mapping"). The report says how many frames came back, how, **why** the
    ones that failed did, and whether the visit is really **several runs**,
    with its offset and its time gap. Measured on 2025 UR: from 78 to 139
    usable frames out of 140, and the star stack's SNR from 1826 to 2702
    (x1.48). **And a frame that does not contain the object is left out and
    counted** (`track_stack.inside_frame`): registered is not the same as
    useful, and stacking a shifted field adds noise exactly where the
    measurement happens. Recovering both runs made a failure visible that
    used to be unreachable: a box's source region could fall entirely off
    the sensor, `calibration.read_image` returned a 1-D empty array and
    scipy took the 2x2 rotation for a homogeneous matrix ("Expected
    homogeneous transformation matrix with shape (2, 2) for image shape
    (0,)"). Now `_source_box` says there is no overlap, `_warp_to_box`
    returns an invalid frame **without reading**, and a read never returns
    1-D.
17. **Inverse-variance (1/sigma^2) co-addition**, as an **optional** method
    beside sum/mean/median/sigma (the default does not change: the
    measurement says a stable night does not pay for it). Each frame's
    noise is measured from its own sky (scaled MAD) **during registration**,
    which already reads the pixels, and the weight is the inverse of its
    variance, the optimal linear combination of measurements with different
    noise. The new method is **the same sigma clip and then the weighted
    average of the survivors** (the clip is shared, so both reject the same
    pixels), and with no weights it is identical to the proven sigma clip.
    Measured: on 2025 UR the frame-to-frame noise varies 4 % (gain 1.003x)
    and on 2026 PY9 11 % (gain 1.022x); with a tenth of the frames at three
    times the noise the gain would be 28 %. It is insurance for the night
    that breaks, and it is also the noise model the matched filter needs.
18. **Matched-filter measurement and the trail, as a measured second
    opinion**: with a known shape `m` (summing to one) and noise `σ` per
    pixel, the best linear estimate of the flux is
    `sum(m(p-sky))/sum(m^2)` and its SNR is the largest any linear filter
    reaches (Cauchy-Schwarz); an aperture is the case `m = 1`, which gives
    the wings the weight of the core. The filter uses the **same centroid,
    the same sky and the same sigma** as the aperture, so the comparison
    measures the filter and nothing else, and the shape comes from the
    **object's own stack** (the FWHM from the stars, which are trails
    there), so a trailed object is filtered with the line it is. The trail
    is inverted from the second moments (`sigma_long^2 = sigma^2 + L^2/12`)
    with a **2-FWHM window and a 1-sigma threshold**, both measured: with
    4 FWHM a round star reported 1.56 px of trail. Measured on the real
    139-frame 2025 UR stack: the filter reaches **1.55 to 1.63x** the
    aperture's SNR, and `sqrt(n_ap/n_eff)` predicts 1.59x. The report
    **still uses the aperture's magnitude**; the filter is reported beside
    it, and the trail is said in words so the next exposure can be
    shortened.
19. **Diagnosing the night with its own stars**: the **limiting magnitude**
    comes from fitting `log10(SNR) = a + b*mag` over the measured
    comparisons and solving for SNR = 5, and the **slope is the check**
    (physics says -0.4; measured on 2025 UR: -0.394), so a field that is
    not sky-limited is flagged instead of quoted. The fit is
    **Theil-Sen** (the median of the pairwise slopes), not least squares
    with a clip, because with few points the clip does not repair a dragged
    line (measured: 0.5 mag off with one saturated comparison). The
    **quality of the solution** is the median residual per cell of a 4x4
    grid: one number for the whole plate hides the corners, which is where
    a wrong scale or a tilted chip shows up, and a cell with no stars is
    left empty, never zero.

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

**Revision (2026-10-05): the stack says what the run measured.** The stack the run
saves carries in its own header what the editor's band (ADR-046) needs to head the
plate: `NS_RATE` / `NS_PA` / `NS_MOT` (the velocity sweep's motion, or the ephemeris'
prediction marked `eph`), `NS_MAG` / `NS_MAGER` / `NS_MAGB` / `NS_MAGNC` / `NS_MAGOK`
(that observation's brightness with the signals that colour it) and the frame's cards
(`EXPTIME`, `DATE-OBS`, `FILTER`, `INSTRUME`, `TELESCOP`) beside `NS_NFRAM`. The
measured position already travelled as `NS_RA` / `NS_DEC` (the annotation). The effect:
reopening a stack months later, with no run in memory and no database, shows its
magnitude, its velocity and its PA in the band, in the same colours as the photometry.

**Revisión (2026-10-05): el apilado usa la máquina que tiene**. La campaña
`docs/PLANS/astrometry-perf/` bajó el tiempo de pared sin tocar el resultado y sin
ninguna dependencia nueva:

- **El barrido lee la ROI UNA vez** (D12 lo pedía): los 25 candidatos mueven el objeto
  unos píxeles, así que cada fotograma se lee en la unión de sus regiones y cada
  candidato recorta de RAM. Los desplazamientos base se calculan una vez.
- **La mediana del clip y del método `median`** es una ordenación con los no válidos al
  final (`+inf`) y el recuento decidiendo el centro: el mismo número, x4,8 más rápido.
- **El registro no repite la `source_image` de la referencia** por fotograma, y el fondo
  por bloques se vectoriza cuando el frame divide por el bloque.
- **El combine se paraleliza por columnas** (la reducción es por píxel, así que el
  resultado es idéntico píxel a píxel) y **los hilos se calculan** en `core/parallel.py`
  desde los núcleos que el proceso puede usar y la memoria que una tarea necesita, en
  Windows y Linux. Ajuste `astrometry_threads` (0 = automático).
- **Medido** (Ryzen 9 5950X, 60 x 1024²): barrido 6348 → 1272 ms (x5,0), `stack_group`
  sigma a frame completo 10143 → 2716 ms (x3,7), combine sigma 957 → 298 ms (x3,2),
  registro 360 → 204 ms por fotograma (x1,8).
- **GPU descartada**, medida y razonada: tras paralelizar el CPU, la ganancia marginal
  de una GPU es x1,5-2 a cambio de una dependencia, kernels por dispositivo y
  empaquetado, y el suelo que no acelera (FITS, ASTAP, Find_Orb) ya es el 30-40 %.
  Queda como decisión escrita, no como deuda implícita.

**Revision (2026-10-05): the stacking uses the machine it has**. The
`docs/PLANS/astrometry-perf/` campaign cut wall-clock time without touching the result
and with no new dependency:

- **The sweep reads the ROI ONCE** (D12 asked for it): the 25 candidates move the object
  a few pixels, so each frame is read into the union of their regions and every candidate
  slices from RAM. The base offsets are computed once.
- **The clip's and the `median` method's median** is a sort with the invalid values
  pushed to the end (`+inf`) and the count picking the middle: the same number, x4.8
  faster.
- **The registration does not rebuild the reference's `source_image`** per frame, and the
  block background is vectorised when the frame divides by the block.
- **The combine is parallelised by columns** (the reduction is per pixel, so the result is
  identical pixel by pixel) and **the threads are computed** in `core/parallel.py` from
  the cores the process may use and the memory one task needs, on Windows and Linux.
  Setting `astrometry_threads` (0 = automatic).
- **Measured** (Ryzen 9 5950X, 60 x 1024²): sweep 6348 → 1272 ms (x5.0), `stack_group`
  sigma full frame 10143 → 2716 ms (x3.7), combine sigma 957 → 298 ms (x3.2),
  registration 360 → 204 ms per frame (x1.8).
- **GPU ruled out**, measured and reasoned: after parallelising the CPU, the marginal
  gain of a GPU is x1.5-2 in exchange for a dependency, per-device kernels and packaging,
  and the floor it cannot accelerate (FITS, ASTAP, Find_Orb) is already 30-40 %. It stays
  a written decision, not an implicit debt.

**Revisión (2026-10-06): el recorte se convierte una vez.** Un stack de
observación es un RECORTE de la rejilla de referencia (`box_around`), y dos
sitios confundían la rejilla con los píxeles del recorte. Con el campo por
defecto (fotograma completo, origen 0,0) el error era invisible; con un recorte
de 512 px, no:

- **El centro del brillo** (`_object_centre`) restaba el origen de la caja al
  centroide medido. El centroide ya está en los píxeles del stack
  (`measure_stack` centra sobre el stack), así que la apertura caía `box[0]`
  píxeles fuera, casi siempre fuera de la imagen: la observación volvía **sin
  magnitud y sin decir por qué**. Ahora el origen solo se resta al punto
  efemérico, que sí vive en la rejilla.
- **La tira** (`_thumbs.set_stacks`) recibía el punto de la efeméride en la
  rejilla y lo usaba para recortar el thumbnail: con un recorte, el panel se
  centraba en un punto que no está en la imagen. Ahora se le pasa el punto en
  los píxeles del stack.

**Revision (2026-10-06): the cutout is converted once.** An observation's stack
is a CUTOUT of the reference grid (`box_around`), and two places confused the
grid with the cutout's pixels. With the default field (whole frame, origin 0,0)
the mistake was invisible; with a 512 px cutout, it was not:

- **The brightness centre** (`_object_centre`) subtracted the box origin from
  the measured centroid. The centroid is already in the stack's pixels
  (`measure_stack` centres on the stack), so the aperture landed `box[0]`
  pixels away, usually off the image: the observation came back **with no
  magnitude and no word about why**. The origin is now subtracted only from the
  ephemeris point, which does live in the grid.
- **The strip** (`_thumbs.set_stacks`) was given the ephemeris point in the
  grid and used it to crop the thumbnail: with a cutout, the panel centred on a
  point that is not in the image. It is now given the point in the stack's own
  pixels.

**Revisión (2026-10-06): el stack base es un producto del run.** El apilado de
toda la secuencia (el objeto congelado, el más profundo de la visita) solo se
conservaba cuando la puerta NO disparaba, y su fichero solo se escribía si el
observador pulsaba «Mostrar» en el modo manual. Se pidió que se guarde y se cargue
con el run, con sus medidas:

- **Siempre en el payload**: `base_stack`, `box_all`, `q_all`, `w0` y `shape` van
  en el resultado de cualquier run, no solo en el «no detectado». Es el recorte de
  la traza del objeto (unos MB), no el fotograma completo.
- **Siempre a disco**: al terminar, la pestaña escribe `<objeto>_base.fits` en el
  proyecto y lo registra en la visita, con las mismas tarjetas que una observación
  (WCS del recorte, `NS_STACK="base"`, `NS_WHOLE`, `NS_RUN`, `NS_NFRAM`, meta del
  fotograma, movimiento y magnitud con su origen) más la **detección hecha sobre
  esa misma imagen** (`NS_FOUND`, `NS_SNR`, `NS_GATE`, `NS_LIMIT`). Escribir todas
  las pilas, y el base, es lo que hace que un run se pueda REABRIR en vez de
  recalcular: el precio es un fichero por producto.
- **Al reabrir**: el resumen del run lleva `box_all` (lo que el modo manual
  necesita para llevar la marca a la rejilla de referencia), `base_rate`/`base_pa`
  y la magnitud de efeméride; el stack base se recarga del proyecto. El fichero se
  llama igual siempre (`<slug>_base.fits`), así que la ruta se recalcula sola.
- **El lector propio de FITS no entiende `HIERARCH`** (ADR-018): toda tarjeta nueva
  tiene 8 caracteres o menos, o la escribe astropy y la pierde la app. Medido: con
  `NS_DETSNR` (9) el lector devolvía la cabecera sin la tarjeta.

**Revision (2026-10-06): the base stack is a product of the run.** The whole-sequence
stack (the object frozen, the deepest of the visit) was kept only when the gate did
NOT fire, and its file was written only if the observer pressed "Show" in the manual
mode. Asked for: it must be saved and loaded with the run, together with its
measurements:

- **Always in the payload**: `base_stack`, `box_all`, `q_all`, `w0` and `shape`
  travel in any run's result, not only in a "not detected" one. It is the object's
  own trail cutout (a few MB), not the whole frame.
- **Always on disk**: when the run ends, the tab writes `<object>_base.fits` into the
  project and registers it on the visit, with the same cards as an observation's
  stack (the cutout's WCS, `NS_STACK="base"`, `NS_WHOLE`, `NS_RUN`, `NS_NFRAM`, the
  frame metadata, the motion and the magnitude with their source) plus **the
  detection made on that very image** (`NS_FOUND`, `NS_SNR`, `NS_GATE`,
  `NS_LIMIT`). Writing every stack, and the base one, is what makes a run
  RESTORABLE instead of recomputed: the price is one file per product.
- **On reopen**: the run's summary carries `box_all` (what the manual mode needs to
  carry the mark to the reference grid), `base_rate`/`base_pa` and the ephemeris'
  magnitude; the base stack is read back from the project. The file always has the
  same name (`<slug>_base.fits`), so the path recomputes itself.
- **The app's own FITS reader does not understand `HIERARCH`** (ADR-018): every new
  card is 8 characters or fewer, or astropy writes it and the app loses it.
  Measured: with `NS_DETSNR` (9) the reader returned the header without the card.

**Revisión (2026-10-06): la velocidad se mide o se predice, nunca se inventa.**
Cuatro defectos medidos sobre las visitas reales del autor (2025 HL5 y 2025
FG18), y lo que se decidió con ellos:

1. **El barrido de velocidad tenía que significar algo.** La rejilla 5×5 cubre
   ±9° de PA en pasos de **4,5°**, así que el «mejor» candidato es siempre un
   punto de la rejilla, y en un objeto débil es el máximo del ruido. Medido: la
   app publicaba PA 33 donde la efeméride (Horizons) dice 41,8 para 2025 HL5, y
   37 donde dice 46,2 para 2025 FG18: exactamente un paso de −9°. Ahora el
   barrido guarda **la semilla** (factor 1.0 y ΔPA 0, que ES la predicción de la
   efeméride, medida sobre los mismos píxeles) y solo se usa su ganador si
   supera a la semilla por **más de 3 veces la dispersión robusta de la propia
   rejilla** (`SweepResult.significant`). Si no, la velocidad que se reporta es
   la efeméride y se dice. Cuando sí es significativo, una **segunda pasada** de
   3×3 alrededor del ganador baja la resolución de ~4,5° a ~0,9° sin leer un solo
   píxel más (los candidatos finos caen dentro de la unión que la pasada gruesa
   ya leyó: medido, las lecturas de disco del barrido no cambian).
2. **La escala del stack entra en los guardas fotométricos.** Los techos
   (saturación, linealidad) son del **sensor**, en ADU de **un** fotograma, y un
   stack `sum` tiene N veces el nivel. Medido en la visita 2025 FG18 (cielo 1552
   ADU, 207 tomas, linealidad de cámara 53 000): el cielo del `sum` solo ya son
   321 000 ADU, seis veces la linealidad, así que **todas** las comparadas se
   rechazaban y el run no daba magnitud. `PlateConfig.stack_scale` multiplica los
   techos antes de compararlos con la placa.
3. **La puerta de detección ya no tira el run a la basura.** Sigue prohibiendo el
   **barrido** (un máximo de ruido es como se fabrica un falso positivo), pero la
   **medida fotométrica se intenta siempre**: la posición es la predicción de la
   efeméride, la magnitud se mide ahí y el punto se marca (`below_gate`), la
   celda de magnitud sale **en rojo** (el mismo rol de `chart_annotate` que usa
   la banda) y la nota dice que la magnitud límite del stack es lo que la noche
   alcanzó de verdad. Un número marcado vale más que ningún número.
4. **Un fotograma ilegible no se lleva la visita por delante.** Medido: la última
   toma de 2025 FG18 es un fichero de 0 bytes (la captura se cortó) y
   `load_sequence` lanzaba, así que la pestaña de Astrometría no llegaba ni a
   armarse. Ahora la toma se deja fuera, se cuenta y se dice: en la línea del
   objeto («N no se pudieron leer») y en la nota del run.

**Revision (2026-10-06): the velocity is measured or predicted, never invented.**
Four defects measured on the author's real visits (2025 HL5 and 2025 FG18), and
what was decided with them:

1. **The velocity sweep had to mean something.** The 5×5 grid spans ±9° of PA in
   steps of **4.5°**, so the "best" candidate is always a grid point, and on a
   faint object it is the noise maximum. Measured: the app published PA 33 where
   the ephemeris (Horizons) says 41.8 for 2025 HL5, and 37 where it says 46.2 for
   2025 FG18: exactly one step of −9°. The sweep now keeps **the seed** (factor
   1.0 and ΔPA 0, which IS the ephemeris' prediction, measured on the same
   pixels) and its winner is only used if it beats the seed by **more than 3
   times the grid's own robust scatter** (`SweepResult.significant`). If not, the
   reported velocity is the ephemeris' and it says so. When it IS significant, a
   **second pass** of 3×3 around the winner takes the resolution from ~4.5° to
   ~0.9° without reading a single extra pixel (the fine candidates fall inside
   the union the coarse pass already read: measured, the sweep's disk reads do
   not change).
2. **The stack's scale enters the photometry guards.** The ceilings (saturation,
   linearity) are the **sensor's**, in ADU of **one** frame, and a `sum` stack
   has N times the level. Measured on the 2025 FG18 visit (sky 1552 ADU, 207
   frames, camera linearity 53 000): the `sum`'s own sky is 321 000 ADU, six
   times the linearity, so **every** comparison star was rejected and the run
   reported no magnitude. `PlateConfig.stack_scale` multiplies the ceilings
   before the plate is compared against them.
3. **The detection gate no longer throws the run away.** It still forbids the
   **sweep** (a noise maximum is how a false positive is manufactured), but the
   **photometric measurement is always attempted**: the position is the
   ephemeris' prediction, the magnitude is measured there and the point is
   flagged (`below_gate`), the magnitude cell comes out **red** (the same
   `chart_annotate` role the band uses) and the note says that the stack's limit
   magnitude is what the night really reached. A marked number is worth more
   than no number.
4. **An unreadable frame does not take the visit down.** Measured: the last frame
   of 2025 FG18 is a 0-byte file (the capture was cut) and `load_sequence` raised,
   so the Astrometry tab never even armed. The frame is now left out, counted and
   said: in the object line ("N could not be read") and in the run's note.

**Revisión (2026-10-06): el reporte dice lo que ha salido, y no se envía
vacío.** Medido en una visita real de 2025 FG18 con **dos observaciones**: el
listón de envío configurado (D26; el MPC **recomienda** 20 y la app trae 10,
que es lo que el autor usó en sus envíos Tycho) dejaba fuera las dos, así que
el generador devolvía **solo la cabecera del formato** y el observador leía
«no genera nada». El motivo sí se decía, pero en dos sitios que no ayudan: la
línea de estado y el grupo «What the run found», que ahora **nace cerrado**
(ADR-038 rev).

- **Una línea en el grupo del reporte**, junto a la fila de Generar, dice qué
  ha salido: «N de M observaciones están en el reporte» o, cuando no hay
  ninguna, que ninguna supera el listón, **con el número del listón y dónde se
  cambia** (Ajustes → Astrometría), que es lo que faltaba para poder actuar.
- **«Send to the MPC block» exige al menos una observación conservada**: la
  caja lleva la cabecera del formato aunque no haya líneas, así que el texto
  solo bastaba para habilitar el botón y se podía pegar en la visita un reporte
  sin observaciones.
- **El grupo de notas recibe su aviso** (⚠) cuando el reporte deja
  observaciones fuera, para que se encuentre sin abrir todos los grupos.
- El listón **no se toca**: 20 es la recomendación explícita del MPC, la app
  trae 10 y bajarlo o subirlo es una decisión del observador, que ahora lo
  cambia en **Ajustes → Astrometría** (esa pestaña existe desde esta revisión:
  antes estos ajustes solo vivían en el fichero de configuración y el mensaje
  del reporte prometía un sitio que no estaba).

**Revision (2026-10-06): the report says what came out, and an empty one is
never sent.** Measured on a real 2025 FG18 visit with **two observations**: the
configured submission floor (D26; the MPC **recommends** 20 and the app ships
10, which is what the author's own Tycho submissions used) left both out, so the generator
returned **the format's header alone** and the observer read "it generates
nothing". The reason was said, but in two places that do not help: the status
line and the "What the run found" group, which is now **born closed**
(ADR-038 rev).

- **A line in the report's own group**, next to the Generate row, says what came
  out: "N of M observations are in the report" or, when there are none, that
  none clears the floor, **with the floor's number and where it is changed**
  (Settings → Astrometry), which is what was missing to be able to act.
- **"Send to the MPC block" needs at least one kept observation**: the box
  carries the format's header even with no lines, so the text alone enabled the
  button and a report with no observations could be pasted into the visit.
- **The notes group gets its notice** (⚠) when the report leaves observations
  out, so it is found without opening every group.
- The floor is **not** touched: 20 is the MPC's explicit recommendation, the
  app ships 10, and raising or lowering it is the observer's call, which they
  now make in **Settings → Astrometry** (that tab exists since this revision:
  these settings used to live only in the config file and the report's message
  promised a place that was not there).

**Nota (2026-10-06)**: la fotometría del run (objeto en su pila, comparsas en la
pila de estrellas) obedece la regla de **ADR-066**: ninguna comparsa ni la
estrella de control entra en el cero punto si toca la saturación o la
linealidad, y si el perfil de cámara no tiene linealidad el run lo dice en sus
notas en vez de caer al recorte de la placa en silencio.

**Note (2026-10-06)**: the run's photometry (the object on its stack, the
comparisons on the star stack) obeys the rule of **ADR-066**: no comparison and
no check star enters the zero point if it touches the saturation or the
linearity, and if the camera profile has no linearity the run says so in its
notes instead of falling back to the plate's clip in silence.

**Nota (2026-10-07)**: la combinación de fotogramas y lo que decide la
profundidad del apilado se midió entero y vive en **ADR-068**: la media
recortada sigma por defecto (la mediana cuesta 0,26 mag), el orden de
interpolación como mando de aspecto y no de límite, la regla de no apilar un
fotograma no verificado con su razón medida (el seeing, 0,11 mag), y las cartas
`NS_COMB`/`NS_ORDER`/`NS_NUSED`/`NS_LEFT` con las que un stack dice cómo se
hizo.

**Note (2026-10-07)**: the combination of frames and what decides a stack's
depth were measured whole and live in **ADR-068**: the sigma-clipped mean by
default (the median costs 0.26 mag), the interpolation order as a knob for the
look and not for the limit, the rule of not stacking an unverified frame with
its measured reason (the seeing, 0.11 mag), and the
`NS_COMB`/`NS_ORDER`/`NS_NUSED`/`NS_LEFT` cards with which a stack says how it
was made.
