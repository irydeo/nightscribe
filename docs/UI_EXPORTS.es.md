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

## Control del observatorio — botones del paso Captura (`gui/main_window.py`)

Requieren el software de observatorio abierto con su API activa (ADR-030,
ADR-081); lecturas cacheadas 60 s. Un backend a la vez, elegido en
**Ajustes → Integraciones**: **CCDciel** (JSON-RPC) o **NINA / PINS** (Advanced
API v2).

| Botón | Qué hace | Cuándo usarlo |
|-------|----------|---------------|
| **Point telescope** | Guinda rápida a la **posición recién calculada** del objetivo en movimiento: `J2000_to_Apparent` + `Telescope_slewasync` en CCDciel, `mount/slew` en NINA, **sin plate-solve**. Rápido, pero asume que la efeméride ya es precisa. | Objetivos orbitales bien determinados (planetas, asteroides con órbita firme, objetos con solución de varios arcos). |
| **Astrometric Goto** | Guinda + **captura + plate-solve** y corrección a la posición real del cielo. Absorbe el **error residual de la efeméride**. | **NEOCP** y **órbitas preliminares**: siempre esta vía, porque la efeméride de una órbita de 1–2 arcos lleva errores de varios segundos de arco que el plate-solve anula. |
| **Stop goto** | Para el movimiento del telescopio **ya** (`Telescope_abortmotion` en CCDciel, `mount/slew/stop` en NINA). Se arma en cuanto empieza un apuntado, en su propio worker. | La montura se dirige a un sitio equivocado. Seguridad. |
| **Send plan** | Prepara el plan guardado (objeto, tomas × exposición, filtro, binning, ganancia, offset, dither) y **lo lee de vuelta** (`Capture_getobjectname/exposure/count/frametype/binning/dither` en CCDciel; guardado en el cliente en NINA) para que el panel muestre lo que de verdad tiene. La **cadencia de autofocus NO se aplica en vivo** (la API de CCDciel no la expone): viaja con la secuencia exportada. | Antes de arrancar una captura. |
| **Start / Stop capture** | Lanza la captura preparada, y el mismo botón la para mientras hay un run en marcha (`Capture_start`/`Capture_stop` en CCDciel; snapshot de una toma / `abort-exposure` en NINA). | Con el telescopio apuntado y el plan preparado. |

La lista de filtros del plan es la que tiene la rueda de verdad (se lee al
conectar); la lista clásica L/R/G/B/Ha/OIII/SII es solo el respaldo sin
conexión. Además se generan los ficheros `.targets` / JSON de NINA (Light +
Dark + Bias).

**Última toma** (ADR-082): tras *Iniciar captura*, el paso muestra una miniatura
de la última toma que tiene el programa, pedida por red (`fullimage.jpg` de
CCDciel, el stream de imágenes de NINA), con su nombre, filtro, exposición y
fecha, y **Abrir en el editor** (NINA descarga el FITS; CCDciel abre el fichero
en disco cuando su ruta es accesible). Sin carpeta, funciona en remoto.

**Opciones de captura** (ADR-083): un bloque plegado con dithering, autofocus,
ganancia, offset, binning y retardos. Los valores recomendados salen de
`core/capture_recipe.py` (por tipo de objeto y la física) y el ⓘ explica cada
uno; viajan con la secuencia exportada y, donde la API lo permite, se aplican en
vivo.

**Valores sugeridos** (ADR-083): un proyecto sin plan se abre con las tomas,
exposición, dither, autofocus y cámara sugeridos ya rellenos; los cambios del
observador se mantienen, **Fijar los valores sugeridos** los vuelve a aplicar y
el **?** de cada bloque abre un diálogo con el porqué y los números usados. La
exposición se acorta para una cámara que satura antes (full well / linealidad,
escala de placa) y se comprueba contra el brillo de cielo del sitio y el ruido de
lectura.

## Secuencias de captura (`gui/main_window.py` → `_project_export_sequence`)

| Formato | Fichero | Estado |
|---------|---------|--------|
| **CCDciel** | `<name>.targets` (CONFIG Version="5") | **Real** — fijado contra la exportación real del usuario (`docs/ccdciel_sequence_sample.targets`); pasos Light + Dark + Bias, ventana rise/set recalculable por CCDciel. |
| **NINA** | JSON de secuencia nativa (`SequenceRootContainer`) | Cargable por NINA vía `/sequence/load`; estructura pinada contra el corpus de test de NINA, **pendiente de confirmar contra una NINA/PINS real** (las cadenas `$type` viven en un único sitio). |
| **NINA (resumen del plan)** | `*.plan.json` | Resumen legible del plan (objetivo, exposiciones, opciones); NO es una secuencia cargable. |
| **CSV genérico** | `<name>.csv` | Best-effort; tablas de tiempos/exposiciones legibles por cualquier script. |

Toda exportación se **registra en `project_files`** (ADR-019) para poder reabrir la
ruta después del export. A partir del reubicado (revisión 2026-09-24 de
ADR-019), esa lista se abre desde el botón **«Files (n)»** de la cabecera
del proyecto, en una ventana propia: un doble clic sobre una placa
(`fits`/`image`) la reabre en el **editor FITS unificado** (ADR-044) con
el objeto del proyecto adjunto, y el resto de ficheros se abren con el
sistema (el menú por fila conserva «Open with the system», carpeta y copiar
ruta).
