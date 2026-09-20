# ADR-010: matplotlib as the single render engine (PNG/social-media)

**Estado / Status**: Accepted (partially superseded — GUI chart layer by ADR-029) ·
**Fecha / Date**: 2026-08-21 · **Actualización / Update**: 2026-09-03 (Fase 5)

## Español

**Contexto**: queremos visualizaciones bonitas dentro de la GUI **y** PNGs listos para
redes, sin duplicar trabajo de render.

**Decisión**: **matplotlib** como motor único (`FigureCanvasQTAgg` embebido en
PySide6; backend `Agg` para export y tests). Estilo centralizado en `viz/style.py`.

**Alternativas**: QPainter propio (más código, sin export trivial); Plotly/web
(dependencia pesada y HTML, no nativa); dos motores distintos (mantenimiento doble).

**Consecuencias**: un solo código por gráfico; tests de imagen con `Agg`; estilo
consistente GUI/redes. matplotlib se instala en el `.venv`.

### Alcance (2026-09-03, ADR-029)

Esta ADR cubre el **renderizado de salida**: los PNGs de redes generados por
`viz/*` y `core.post.build_charts`. Los **widgets interactivos de la GUI** (órbita,
cielo, …) viven ahora en la capa `gui/widgets/*` (`QGraphicsView` nativos, sin
matplotlib) — ver ADR-029. La exportación de redes se mantiene en matplotlib: es el
único lugar donde se exige "una imagen estática final, lista para publicar".

## English

**Context**: we want beautiful visualizations inside the GUI **and** PNGs ready for
social media, without duplicating render work.

**Decision**: **matplotlib** as the single engine (`FigureCanvasQTAgg` embedded in
PySide6; `Agg` backend for export and tests). Centralised style in `viz/style.py`.

**Alternatives**: custom QPainter (more code, no trivial export); Plotly/web (heavy
dependency, HTML, not native); two different engines (double maintenance).

**Consequences**: one code path per chart; image tests with `Agg`; consistent style
across GUI/social. matplotlib is installed in the `.venv`.

### Scope (2026-09-03, ADR-029)

This ADR covers **output rendering**: the social-media PNGs produced by `viz/*` and
`core.post.build_charts`. The **interactive GUI widgets** (orbit, sky, …) now live in
the `gui/widgets/*` layer (native `QGraphicsView`, no matplotlib) — see ADR-029. Network
export stays in matplotlib: it is the only place where "a final, publish-ready static
image" is required.
