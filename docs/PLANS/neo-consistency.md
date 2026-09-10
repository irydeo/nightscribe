# Plan — Track C: NEO/cometa/asteroide, consistencia con el resto de flujos

> **Abierto (2026-09-09)** — hijo C de
> [project-concept-v2.md](project-concept-v2.md) (leer primero el padre).
> Un subplan = un commit. **Se ejecuta después del track B** (reutiliza su
> motor de series).
> **Enmendado 2026-09-09 (post-entrevista)**: lo que el observador conserva de
> una noche NEO queda explícito (FITS + **imágenes anotadas de Tycho** +
> reporte MPC → C0 los registra los tres), y la animación de movimiento sube de
> «extra bonito» a **prueba de fuego**: es como se verifica que el objeto es
> *ese* (y además divulga).

**rama**: `feature/neo-consistency` (nace de `feature/object-card` al día, tras cerrar el track B; mergea de vuelta a `feature/object-card`)
**fecha**: 2026-09-09 · **autor**: FJC (con la IA)

## Objetivo

El flujo NEO/cometa actual **es suficiente** funcionalmente (exposición
anti-traza, efemérides TheSkyX/CdC, reporte MPC ADR-022, goto fresco ADR-030).
Este track **no lo rediseña**: solo lo hace **consistente** con lo que ganan las
supernovas en el track B — registrar en el proyecto lo que el observador
realmente conserva de la sesión y ofrecer la **animación del movimiento** como
herramienta de verificación y divulgación.

## Contexto clave (exploración 2026-09-09)

- Flujo NEO hoy: Plan con cap anti-traza (`exposure.max_exposure_no_trail`,
  solo `neo`/`pccp`, `main_window.py` L1554-1566) → Captura (exports
  `sequence.py` + efemérides `ephemeris.py`, MPOrbit/Find_Orb ADR-021) →
  Procesado: pegar medidas MPC 80-col/ADES y empaquetar (`mpc_report.py`,
  ADR-022) → Publicar. El paso Process NEO **no registra ningún fichero de la
  sesión**.
- Lo que el observador conserva hoy de una noche NEO (entrevista): **los FITS**,
  **una o varias imágenes anotadas generadas por Tycho** (con la info del NEO)
  y **el reporte MPC empaquetado** (este último ya se registra).
- Motor de series del track B (`core/series.py`, B5): carga FITS + WCS por
  frame + afín de alineación (B6) — el 90% de la animación NEO.
- Posición en el instante de cada frame: `core/ephemeris.py::position_at`
  (Horizons 2 min, fallbacks SBDB/Kepler y NEOfixer; ADR-030) + `DATE-OBS` del
  header (B1, `core/fits_meta.py`).
- `project_files` acepta `kind='fits'`/`'chart'`; tras A4 la lista es visible.

## Análisis de consistencia (C0, ejecutado 2026-09-10)

Qué tiene la supernova tras el track B que el NEO/cometa no tenía:

| Pieza (SN, track B) | ¿Aplica a NEO/cometa/asteroide? |
|---|---|
| Registro de los productos de la sesión (apilados FITS por visita, visibles en Detalles vía `project_files`) | **Sí** — el observador conserva los FITS de la noche, las **imágenes anotadas de Tycho** y el reporte MPC (entrevista). El paso Process NEO no registraba nada → C0 lo añade. |
| Animación (evolución fotométrica, B6) | **Sí, pero otro eje**: en NEO lo que se mueve es la **posición** — la animación de movimiento es la «prueba de fuego» de que el objeto es *ese* → C1. |
| Curva de luz / quick-look fotométrico (B4/B5) | **No en v1** — la fotometría de asteroides (rotación) sigue fuera (padre, T1); posible v2 si el motor de series madura. |
| Cadencia con memoria (B11) | **No** — un NEO/PCCP es «una noche o pocas»; no hay revisita rutinaria. La revisita NEO real es la del track de seguimiento de NEOfixer, externa. |
| FITS anotado propio (B10) | **No en v1** — el observador ya genera las anotadas con Tycho; C0 las registra (`kind='image'`) en vez de generarlas. |

Huecos menores detectados (alimentan C2): ninguno — las etiquetas de
fecha/hora entre flujos ya son consistentes (mismo patrón `DATE-OBS` → MJD de
`core/fits_meta.py` y época visible de ADR-030), y las efemérides exportadas
ya se registran en `project_files` (`kind='ephemeris'`) desde la fase 5.

## Subplanes

### C0 — Análisis de consistencia + registro de los productos de la sesión
- Revisión documentada (sección corta en este archivo al ejecutarse): qué tiene
  SN tras el track B que NEO no — registro de imágenes, animación, curva — y
  qué aplica a NEO/cometa/asteroide (la curva fotométrica **no** aplica en v1).
- Paso Process NEO/cometa: registrar **los tres productos reales de la sesión**
  (entrevista): FITS (multi-selección, metadatos auto vía `core/fits_meta.py`),
  **imágenes anotadas de Tycho** (`kind='image'`) y el reporte MPC (ya
  registrado). Persistido en `project_steps.data` + `project_files`.

**Tests**: offscreen — registro de los tres tipos con `fits_meta` fake, lista
visible (patrón A4), persistencia.

### C1 — Animación de movimiento: la prueba de fuego (GIF/MP4)
Sobre el motor de B5/B6: frames alineados a las **estrellas** (afín por WCS);
el recorte **sigue la posición predicha** del objeto en el instante de cada
frame (`DATE-OBS` → `ephemeris.position_at`), con **marcador sobre la posición
predicha** y etiqueta de fecha/hora + tasa/PA previstos. Doble propósito
(entrevista):
- **Verificación («la prueba de fuego»)**: si hay un punto moviéndose justo
  bajo el marcador a la tasa prevista, es *ese* objeto — la comprobación visual
  definitiva antes de medir para el MPC.
- **Divulgación**: el clásico «movie» de NEO para el post.
Registrado en `project_files`. Frame sin WCS → se salta con aviso (igual que B6).

**Tests**: interpolación de posición a `DATE-OBS` (mock de `position_at`),
afín correcto, marcador en la posición predicha, GIF/MP4 con frames sintéticos,
salto de frame sin WCS.

### C2 — Ajustes derivados del análisis
Lo que C0 documente como huecos menores (p. ej. consistencia de etiquetas de
fecha/hora entre flujos, registro de efemérides usadas en la captura). Si C0 no
levanta nada, este subplan se cierra como «sin cambios» con la nota en el
documento.

**Tests**: los que dicte C0.

## Orden de ejecución

C0 → C1 → C2
(C1 depende de B5/B6 ya cerrados y del registro de C0.)

## Fuera de alcance

- Curva de luz de asteroides (rotación) — la fotometría sigue fuera (padre, T1);
  posible v2 si el motor de series madura.
- Rediseño del flujo de medida MPC (ya validado, ADR-022).
- Secuencias multi-filtro en el plan NEO (sin necesidad detectada; la
  capacidad la trae B8 y queda disponible si se quiere).

## Riesgos conocidos

- `position_at` sin red cae a SBDB/Kepler o NEOfixer preliminar: el marcador
  puede desviarse en NEOs de movimiento rápido — se muestra la fuente de la
  efeméride junto al frame (ya hay patrón de etiqueta de época, ADR-030). Si el
  marcador no cae sobre el objeto, la «prueba de fuego» falla aunque el objeto
  sea correcto: el aviso de fuente de efeméride es obligatorio.
- Cometas con cola extensa: el recorte centrado en el núcleo puede cortar la
  cola; zoom configurable como en el blink.
