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
   especifican a ciegas). Para objetos sin confirmar (sin elementos orbitales) la
   efeméride NEOfixer/Horizons es la única vía — se exporta la tabla, no elementos.
5. Los ficheros generados se registran en `project_files` (ADR-019).

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
   import** in the user's installations during phase 5 (not specified blindly). For
   unconfirmed objects (no orbital elements) the NEOfixer/Horizons ephemeris is the
   only route — the table is exported, not elements.
5. Generated files are registered in `project_files` (ADR-019).

**Consequences**: DESIGN.md updates its "out of scope": telescope control stays out;
**exporting files is in**. Unit tests per exporter (structural validation of the NINA
JSON, CCDciel plan lines, CSV columns).
