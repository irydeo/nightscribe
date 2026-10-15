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

**Revisión (2026-10-14): sitio 500 cuando no hay código MPC.** NEOfixer
**rechaza** un `site` vacío («Parameter 'site' should be of type string with a
length between 3 and 32 characters»), así que un observador que solo fijó
coordenadas (sin código MPC) no recibía **ningún** NEO, en silencio. La
planificación usa ahora `site_code(cfg)`: el código MPC si existe, y si no
**500** (el sitio geocéntrico del MPC). Las posiciones son geocéntricas, lo que
es honesto para planificar, y la visibilidad de la noche se sigue calculando
contra la lat/lon reales del observador. El 500 **nunca** se escribe en la
configuración, para que `is_configured()` siga siendo honesto, y no se usa en un
reporte ni en un contexto de astrometría (esos exigen el código real).

**Revision (2026-10-14): site 500 when there is no MPC code.** NEOfixer
**rejects** an empty `site` ("Parameter 'site' should be of type string with a
length between 3 and 32 characters"), so an observer who only set coordinates
(no MPC code) got **no** NEOs at all, in silence. Planning now uses
`site_code(cfg)`: the MPC code when it exists, and **500** (the MPC's geocentric
site) otherwise. The positions are geocentric, which is honest for planning, and
the night's visibility is still computed against the observer's real lat/lon.
The 500 is **never** written to the config, so `is_configured()` stays honest,
and it is not used in a report or an astrometry context (those need the real
code).
