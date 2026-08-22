# ADR-010: matplotlib as the single render engine (GUI + PNG)

**Estado / Status**: Accepted · **Fecha / Date**: 2026-08-21

## Español

**Contexto**: queremos visualizaciones bonitas dentro de la GUI **y** PNGs listos para
redes, sin duplicar trabajo de render.

**Decisión**: **matplotlib** como motor único (`FigureCanvasQTAgg` embebido en
PySide6; backend `Agg` para export y tests). Estilo centralizado en `viz/style.py`.

**Alternativas**: QPainter propio (más código, sin export trivial); Plotly/web
(dependencia pesada y HTML, no nativa); dos motores distintos (mantenimiento doble).

**Consecuencias**: un solo código por gráfico; tests de imagen con `Agg`; estilo
consistente GUI/redes. matplotlib se instala en el `.venv`.

## English

**Context**: we want beautiful visualizations inside the GUI **and** PNGs ready for
social media, without duplicating render work.

**Decision**: **matplotlib** as the single engine (`FigureCanvasQTAgg` embedded in
PySide6; `Agg` backend for export and tests). Centralised style in `viz/style.py`.

**Alternatives**: custom QPainter (more code, no trivial export); Plotly/web (heavy
dependency, HTML, not native); two different engines (double maintenance).

**Consequences**: one code path per chart; image tests with `Agg`; consistent style
across GUI/social. matplotlib is installed in the `.venv`.
