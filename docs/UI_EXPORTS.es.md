# NightScribe — Botones y exportaciones del proyecto

*[English version](UI_EXPORTS.md)*

Qué hace cada botón de entrega y cada formato de exportación, para quién es y por
qué. La idea: que al pulsar cada botón sepas qué fichero te llevas y a qué
programa lo abres.

## Exportar efeméride (`gui/main_window.py` → `_project_export_ephem`)

El diálogo **«Export ephemeris»** tiene dos formatos y una casilla opcional. Elige
el formato según el destino final del fichero:

| Formato | Fichero | Para quién | Qué es |
|---------|---------|-----------|--------|
| **Elementos MPC (MPOrbit)** (principal) | `<name>_elements.txt` | **Cualquier planetario o lector de órbitas** (formato universal de intercambio de elementos del MPC) | Una **línea de elementos MPOrbit** por objeto (202 caracteres, el «Export Format for Minor-Planet Orbits» del Minor Planet Center): designación empaquetada, H/G, época empaquetada, anomalía media, perihelio/nodo/inclinación, excentricidad, movimiento medio, semieje mayor, incertidumbre, referencia de última observación, arco y RMS — exactamente el diseño que escribe Find_Orb, así que el software que ya lee listas de elementos de Find_Orb la lee sin cambios. Es el **traspaso de órbita canónico**: si quieres la órbita en otro programa, es este. |
| **MPC orbit report** | `<name>_orbit_report.txt` | **Informe legible de seguimiento** y herramientas generales | Informe orbital **legible** al estilo MPC/Find_Orb: elementos keplerianos + sigmas, perihelio, vectores P/Q, vector de estado J2000 (posición AU / velocidad mAU·day⁻¹), MOIDs de los 8 planetas, Tisserand, velocidad de encuentro, diámetro estimado y el pie de elementos estilo MPC. Todo campo es una fórmula pura. |

**Casilla «Force fresh data (bypass cache)»** — re-consulta JPL SBDB / NEOfixer
*ahora*, en vez de usar la órbita que ya está en la caché de SQLite. Úsala después
de que el **MPC haya mejorado la órbita preliminar** (más observaciones, arco más
largo) para que el informe refleje el ajuste más nuevo.

**Sin Find_Orb local**: todos los campos del MPC report son **fórmulas puras** sobre
los elementos que devuelve NEOfixer/SBDB (`core/orbits.py`, `core/ephem_minor.py`,
verificadas contra `docs/Sar2911-sample-ephemerids.txt`). No se ejecuta Find_Orb en
máquina.

**Parallax topocéntrica**: la posición CCD y el CSV de posiciones usan `kepler_ra_dec()` con la
lat/lon/altura del observatorio de config — la posición que ves es la del *sitio*,
no geocéntrica (para Sar2911 a 0,102 AU la corrección es ~86″; para NEOCP típicos
0,1–0,2 AU, ~44–88″). Asegúrate de que el observatorio de Settings es correcto
antes de exportar.

## CCDciel — botones de la pestaña CCD (`gui/main_window.py:1635`)

Requieren CCDciel abierto con su JSON-RPC activo (ADR-030); lecturas cacheadas 60 s.

| Botón | Qué hace | Cuándo usarlo |
|-------|----------|---------------|
| **Point telescope** | Guinda rápida a la **posición recién calculada** del objetivo en movimiento: `J2000_to_Apparent` + `Telescope_slewasync`, **sin plate-solve**. Rápido, pero asume que la efeméride ya es precisa. | Objetivos orbitales bien determinados (planetas, asteroides con órbita firme, objetos con solución de varios arcos). |
| **Astrometric Goto** | Guinda + **captura + plate-solve** y corrección a la posición real del cielo. Absorbe el **error residual de la efeméride**. | **NEOCP** y **órbitas preliminares**: siempre esta vía, porque la efeméride de una órbita de 1–2 arcos lleva errores de varios segundos de arco que el plate-solve anula. |

El resto del panel CCD (conectar, filtrar, empujar plan, arrancar captura) sigue la
lógica de ADR-021 §5 y ADR-030: el plan se **entrega en vivo** vía JSON-RPC
(`Capture_set*`, `Wheel_setfilter`, `Capture_start`) y además se genera el fichero
`.targets` (Light + Dark + Bias).

## Secuencias de captura (`gui/main_window.py` → `_project_export_sequence`)

| Formato | Fichero | Estado |
|---------|---------|--------|
| **CCDciel** | `<name>.targets` (CONFIG Version="5") | **Real** — fijado contra la exportación real del usuario (`docs/ccdciel_sequence_sample.targets`); pasos Light + Dark + Bias, ventana rise/set recalculable por CCDciel. |
| **NINA** | JSON de secuencia nativa | Best-effort; validación pendiente contra la versión real del usuario. |
| **CSV genérico** | `<name>.csv` | Best-effort; tablas de tiempos/exposiciones legibles por cualquier script. |

Toda exportación se **registra en `project_files`** (ADR-019) para poder reabrir la
ruta después del export.
