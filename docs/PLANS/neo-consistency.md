# Plan — Track C: NEO/cometa/asteroide, consistencia con el resto de flujos

> **Abierto (2026-09-09)** — hijo C de
> [project-concept-v2.md](project-concept-v2.md) (leer primero el padre).
> Un subplan = un commit. **Se ejecuta después del track B** (reutiliza su
> motor de series).

**rama**: `feature/neo-consistency` (nace de `feature/object-card` al día, tras cerrar el track B; mergea de vuelta a `feature/object-card`)
**fecha**: 2026-09-09 · **autor**: FJC (con la IA)

## Objetivo

El flujo NEO/cometa actual **es suficiente** funcionalmente (exposición
anti-traza, efemérides TheSkyX/CdC, reporte MPC ADR-022, goto fresco ADR-030).
Este track **no lo rediseña**: solo lo hace **consistente** con lo que ganan las
supernovas en el track B — registrar las imágenes de la sesión en el proyecto y
ofrecer la **animación del movimiento** propio del objeto, el equivalente NEO de
la animación de evolución de SN.

## Contexto clave (exploración 2026-09-09)

- Flujo NEO hoy: Plan con cap anti-traza (`exposure.max_exposure_no_trail`,
  solo `neo`/`pccp`, `main_window.py` L1554-1566) → Captura (exports
  `sequence.py` + efemérides `ephemeris.py`, MPOrbit/Find_Orb ADR-021) →
  Procesado: pegar medidas MPC 80-col/ADES y empaquetar (`mpc_report.py`,
  ADR-022) → Publicar. El paso Process NEO **no registra ningún FITS**.
- Motor de series del track B (`core/series.py`, B5): carga FITS + WCS por
  frame + afín de alineación (B6) — el 90% de la animación NEO.
- Posición en el instante de cada frame: `core/ephemeris.py::position_at`
  (Horizons 2 min, fallbacks SBDB/Kepler y NEOfixer; ADR-030) + `DATE-OBS` del
  header (B1, `core/fits_meta.py`).
- `project_files` acepta `kind='fits'`/`'chart'`; tras A4 la lista es visible.

## Subplanes

### C0 — Análisis de consistencia + registro de FITS
- Revisión documentada (sección corta en este archivo al ejecutarse): qué tiene
  SN tras el track B que NEO no — registro de imágenes, animación, curva — y
  qué aplica a NEO/cometa/asteroide (la curva fotométrica **no** aplica en v1).
- Paso Process NEO/cometa: campo «FITS de la sesión» (multi-selección),
  metadatos auto vía `core/fits_meta.py`, rutas registradas en `project_files`
  (`kind='fits'`). Persistido en `project_steps.data`.

**Tests**: offscreen — registro de FITS con `fits_meta` fake, lista visible
(patrón A4), persistencia.

### C1 — Animación de movimiento (GIF/MP4)
Sobre el motor de B5/B6: frames alineados a las **estrellas** (afín por WCS);
el recorte **sigue la posición predicha** del objeto en el instante de cada
frame (`DATE-OBS` → `ephemeris.position_at`), con marcador sobre el objetivo y
etiqueta de fecha/hora. Resultado: estrellas fijas, NEO/cometa moviéndose —
el clásico «movie» de NEO. Registrado en `project_files`. Frame sin WCS → se
salta con aviso (igual que B6).

**Tests**: interpolación de posición a `DATE-OBS` (mock de `position_at`),
afín correcto, GIF/MP4 con frames sintéticos, salto de frame sin WCS.

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
  efeméride junto al frame (ya hay patrón de etiqueta de época, ADR-030).
- Cometas con cola extensa: el recorte centrado en el núcleo puede cortar la
  cola; zoom configurable como en el blink.
