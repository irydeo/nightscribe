# ADR-021: Capture-sequence and ephemeris exports

**Estado / Status**: Accepted · **Fecha / Date**: 2026-08-24

## Español

**Contexto**: el flujo de proyecto (ADR-019) exige llevar el plan al software externo:
secuencias de captura para **NINA** y **CCDciel**, y efemérides de NEOs al planetario
(**TheSkyX**, **Cartes du Ciel**) para apuntar. DESIGN.md declaraba «control de
telescopios» fuera de alcance — pero **generar ficheros no es controlar**: no habrá
drivers, ni slew, ni comunicación en tiempo real (eso sigue siendo del proyecto hermano
`saas`).

**Decisión**:

1. **Perfil de cámara en config** (un solo perfil en v1): `pixel_um`, `focal_mm` →
   escala de placa derivada (″/px). Nuevo grupo «Cámara» en Settings.
2. **`core/exposure.py` — calculadora de exposición.** Para NEOs: exposición máxima por
   toma sin traza a partir de la velocidad aparente (`rate` de NEOfixer/Horizons) y la
   escala de placa; duración total de sesión = N × (exposición + overhead configurable
   `overhead_s`); alimenta la viabilidad de sesión de ADR-020 («inicio seguro hasta
   HH:MM»). Exposiciones por defecto por tipo de objeto en config.
3. **`core/sequence.py` — exportadores de captura**: **NINA** (JSON de secuencia
   nativo), **CCDciel** (fichero de plan) y **CSV genérico** legible por cualquier otro
   software. Contenido: nombre, coords J2000, N tomas × exposición, filtro, tiempos.
4. **Efemérides NEO para planetario**: CSV a paso configurable como base + formatos
   **TheSkyX** y **Cartes du Ciel**. Los formatos exactos se fijan **contra una
   importación real** en las instalaciones del usuario durante la fase 5 (no se
   especifican a ciegas). ~~Para objetos sin confirmar (sin elementos orbitales) la
   efeméride NEOfixer/Horizons es la única vía — se exporta la tabla, no elementos.~~
   **Actualizado por ADR-023**: desde 2026-08-25 los objetos NEOCP usan la órbita
    preliminar de NEOfixer `/orbit/` propagada localmente — se exportan efemérides
    completas marcadas como preliminares.
    **Actualizado 2026-09-08**: el export principal de órbita es ahora el **informe
    orbital MPC/Find_Orb** (`export_fo_report`, formato universal — elementos,
    perihelio, P/Q, vector de estado J2000, MOIDs de los 8 planetas, Tisserand,
    velocidad de encuentro, diámetro y pie de elementos estilo MPC). Importable por
    **TheSkyX, Stellarium, Cartes du Ciel y cualquier lector**; es el traspaso de
    órbita canónico. La **tabla de posiciones CSV** (RA/Dec, distancia, alt/az a
    lo largo de la noche) queda como opción secundaria de **seguimiento/puntería**,
    no como registro de órbita. Sin Find_Orb local: todos los campos son fórmulas
    puras sobre los elementos de NEOfixer. Nuevas capacidades: **parallax
    topocéntrica** en la posición (`kepler_ra_dec` con lat/lon/altura de config;
    ~86″ para Sar2911) y **frescor de datos** (`force` en `db.http_get` re-consulta
    JPL SBDB/NEOfixer en vez de usar la caché, tras mejora del MPC).
    **Actualizado 2026-09-08**: el diálogo de export del proyecto ofrece ahora
    **dos formatos** (sin CSV): (a) **Elementos MPC (MPOrbit)** —
    `export_mpc_elements`, una línea de **202 caracteres** en el «Export Format for
    Minor-Planet Orbits» del MPC (designación empaquetada, H/G, época empaquetada,
    M/ω/Ω/i, e, n, a, U, referencia de última observación, arco y RMS), firmada como
    NightScribe y **byte-idéntica** a la línea que escribe Find_Orb (verificada
    contra `docs/Sar2911-sample-ephemerids.txt`), importable por cualquier planetario
    o lector de órbitas; y (b) el **informe legible** `export_fo_report` (elementos,
    perihelio, P/Q, vector de estado J2000, MOIDs, Tisserand, velocidad de encuentro,
    diámetro y pie de elementos estilo MPC). La **tabla de posiciones CSV** (RA/Dec,
    distancia, alt/az) desaparece del diálogo — sigue disponible en
    `ephemeris.export_csv` a nivel de módulo —: el MPOrbit es el traspaso canónico y
    el informe el documento legible de seguimiento.
5. Los ficheros generados se registran en `project_files` (ADR-019).
   **Actualizado 2026-09-06**: el formato **CCDciel ya es real** — `export_ccdciel`
   escribe listas `.targets` (CONFIG Version="5") fijadas contra la exportación real
   del usuario (`docs/ccdciel_sequence_sample.targets`): pasos **Light + Dark + Bias**
(nº de oscuros/exposición/bias configurables en la pestaña Plan del proyecto — el
    paso Captura se fundió en el Plan por la revisión 2026-09-06 de ADR-019 —, por
    defecto 25 oscuros + 100 bias), ventana rise/set por defecto que CCDciel recalcula
    con su configuración del observatorio y `StartTime`/`EndTime` informativos desde la
    ventana segura del plan. NINA y CSV siguen siendo best-effort (validación pendiente
    contra la versión real del usuario).
    **Actualizado 2026-09-06**: además del fichero, el plan se **entrega en vivo** a
    CCDciel vía JSON-RPC (`Capture_set*`, `Wheel_setfilter`, `Capture_start`) — ver
    ADR-030.

**Consecuencias**: DESIGN.md actualiza su «fuera de alcance»: control de telescopios
sigue fuera; **exportar ficheros está dentro**. Tests unitarios de cada exportador
(validación estructural del JSON NINA, líneas del plan CCDciel, columnas CSV).

## English

**Context**: the project flow (ADR-019) requires carrying the plan to external
software: capture sequences for **NINA** and **CCDciel**, and NEO ephemerides to the
planetarium (**TheSkyX**, **Cartes du Ciel**) for pointing. DESIGN.md declared
"telescope control" out of scope — but **generating files is not controlling**: no
drivers, no slewing, no real-time communication (that remains the sibling project
`saas`).

**Decision**:

1. **Camera profile in config** (single profile in v1): `pixel_um`, `focal_mm` →
   derived plate scale (″/px). New "Camera" group in Settings.
2. **`core/exposure.py` — exposure calculator.** For NEOs: maximum per-frame exposure
   without trailing, from apparent rate (`rate` from NEOfixer/Horizons) and plate
   scale; total session duration = N × (exposure + configurable `overhead_s`); feeds
   the session feasibility of ADR-020 ("safe start until HH:MM"). Default exposures per
   object kind in config.
3. **`core/sequence.py` — capture exporters**: **NINA** (native sequence JSON),
   **CCDciel** (plan file) and **generic CSV** readable by any other software.
   Contents: name, J2000 coords, N frames × exposure, filter, times.
4. **NEO ephemerides for planetariums**: configurable-step CSV as the base +
   **TheSkyX** and **Cartes du Ciel** formats. Exact formats are fixed **against a real
   import** in the user's installations during phase 5 (not specified blindly).
   **Updated 2026-09-06**: the **CCDciel format is now real** — `export_ccdciel`
   writes `.targets` lists (CONFIG Version="5") fixed against the user's actual
export (`docs/ccdciel_sequence_sample.targets`): **Light + Dark + Bias** steps
    (dark count/exposure and bias count configurable in the project's Plan tab — the
    Capture step merged into Plan by ADR-019's 2026-09-06 review —, default 25 darks +
    100 bias), the default rise/set window that CCDciel recomputes
    from its own observatory settings, and informative `StartTime`/`EndTime` from the
    plan's safe window. NINA and CSV remain best-effort (validation pending against
    the user's real version).
    **Updated 2026-09-06**: besides the file, the plan is now **delivered live** to
    CCDciel over JSON-RPC (`Capture_set*`, `Wheel_setfilter`, `Capture_start`) — see
    ADR-030.
    **Updated 2026-09-08**: the primary orbit export is now the **MPC/Find_Orb orbit
    report** (`export_fo_report`, universal format — elements, perihelion, P/Q, J2000
    state vector, MOIDs of all 8 planets, Tisserand, encounter speed, diameter and an
    MPC element footer). Importable by **TheSkyX, Stellarium, Cartes du Ciel and any
    reader**; the canonical orbit handover. The **position CSV** (RA/Dec, distance,
    alt/az over the night) remains the secondary **tracking/pointing** option, not an
    orbit record. Without a local Find_Orb: every field is a pure formula over the
    NEOfixer elements. New capabilities: **topocentric parallax** in the position
    (`kepler_ra_dec` with lat/lon/height from config; ~86″ for Sar2911) and **data
    freshness** (`force` in `db.http_get` re-queries JPL SBDB/NEOfixer instead of the
    cache, after the MPC improves the orbit).
    **Updated 2026-09-08**: the project export dialog now offers **two formats** (no
    CSV): (a) **MPC elements (MPOrbit)** — `export_mpc_elements`, a single
    **202-character** line in the Minor Planet *Center*'s "Export Format for
    Minor-Planet Orbits" (packed designation, H/G, packed epoch, mean anomaly,
    perihelion/node/inclination, eccentricity, mean motion, semi-major axis,
    uncertainty, last-observation reference, arc and RMS), signed "NightScr" and
    **byte-identical** to the Find_Orb line (verified against
    `docs/Sar2911-sample-ephemerids.txt`), importable by any planetarium or orbit
    reader; and (b) the **readable report** `export_fo_report` (elements, perihelion,
    P/Q, J2000 state vector, MOIDs, Tisserand, encounter speed, diameter and an MPC
    element footer). The **position CSV** (RA/Dec, distance, alt/az) is gone from the
    dialog — still available as `ephemeris.export_csv` at module level —: MPOrbit is
    the canonical handover and the report the readable follow-up document.
    ~~For unconfirmed objects (no orbital elements) the NEOfixer/Horizons ephemeris is
    the only route — the table is exported, not elements.~~ **Updated by ADR-023**:
   since 2026-08-25 NEOCP objects use the preliminary NEOfixer `/orbit/` solution
   propagated locally — full ephemerides are exported, flagged as preliminary.
5. Generated files are registered in `project_files` (ADR-019).

**Consequences**: DESIGN.md updates its "out of scope": telescope control stays out;
**exporting files is in**. Unit tests per exporter (structural validation of the NINA
JSON, CCDciel plan lines, CSV columns).
