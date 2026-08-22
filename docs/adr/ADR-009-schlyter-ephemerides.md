# ADR-009: Schlyter low-precision ephemerides for Sun/Moon/planets

**Estado / Status**: Accepted · **Fecha / Date**: 2026-08-21

## Español

**Contexto**: las visualizaciones y la planificación necesitan posiciones de Sol, Luna
y planetas (fase lunar, crepúsculos, planetas visibles, posiciones en los diagramas).
Horizons lo daría, pero exige una llamada de red por cuerpo.

**Decisión**: implementar los algoritmos clásicos de baja precisión de **Paul
Schlyter** (stjarnhimlen.se) en `core/ephem_minor.py`: math puro, offline, precisión
de arcminutos (sobra para gráficos y planificación). Cuerpos menores: propagación
kepleriana desde elementos SBDB.

**Alternativas**: Horizons para todo (lento, online); VSOP87/ELP completo
(sobre-ingeniería); skyfield (ver ADR-004).

**Consecuencias**: diagramas y crepúsculos instantáneos y testeables; precisión
documentada en el código; si se necesita precisión de arcosegundos, Horizons sigue
disponible como fuente.

## English

**Context**: visualizations and planning need Sun, Moon and planet positions (moon
phase, twilights, visible planets, diagram placements). Horizons would provide them,
but it costs one network call per body.

**Decision**: implement Paul **Schlyter's** classic low-precision algorithms
(stjarnhimlen.se) in `core/ephem_minor.py`: pure math, offline, arcminute accuracy
(plenty for charts and planning). Minor bodies: Kepler propagation from SBDB elements.

**Alternatives**: Horizons for everything (slow, online); full VSOP87/ELP
(over-engineering); skyfield (see ADR-004).

**Consequences**: instant, testable charts and twilights; accuracy documented in
code; if arcsecond precision is ever needed, Horizons remains available.
