# ADR-003: NEOfixer as the primary NEO planning source

**Estado / Status**: Accepted · **Fecha / Date**: 2026-08-21

## Español

**Contexto**: planificar NEOs exige saber qué objetos son prioritarios *para tu sitio*.
`saas` usaba la lista de prioridad de ESA NEOCC + astroquery/MPC.

**Decisión**: **NEOfixer** (Univ. of Arizona / Catalina) como fuente primaria:
`targets/?site=<MPC>` da score, prioridad, coste en minutos y efemérides por sitio,
público y en JSON-RPC. ESA NEOCC queda como fuente complementaria (próximas
aproximaciones). El método `report` (con clave del usuario, opcional) cierra el ciclo
de coordinación comunitaria.

**Alternativas**: ESA NEOCC como primaria (sin score por sitio; la lista de prioridad
devolvía cuerpo vacío en la verificación); scraping del servicio web del MPC (frágil).

**Consecuencias**: menos cómputo propio, prioridades científicas reales, integración
con la comunidad. Dependemos de un servicio externo → degradación elegante si cae.

## English

**Context**: NEO planning requires knowing which objects are a priority *for your
site*. `saas` used the ESA NEOCC priority list + astroquery/MPC.

**Decision**: **NEOfixer** (Univ. of Arizona / Catalina) as the primary source:
`targets/?site=<MPC>` provides score, priority, cost in minutes and site-specific
ephemerides, public, JSON-RPC. ESA NEOCC remains complementary (upcoming close
approaches). The `report` method (user key, optional) closes the community
coordination loop.

**Alternatives**: ESA NEOCC as primary (no per-site score; priority list returned an
empty body during verification); scraping the MPC web service (fragile).

**Consequences**: less local computation, real scientific priorities, community
integration. We depend on an external service → graceful degradation if down.
