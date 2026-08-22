# ADR-012: PCCP via MPC tabular page scraping

**Estado / Status**: Accepted · **Fecha / Date**: 2026-08-21

## Español

**Contexto**: la página PCCP del MPC (*Possible Comet Confirmation Page*) lista
candidatos a cometa que necesitan confirmación — oro divulgativo y científico para un
observatorio que reporta al MPC. No existe endpoint JSON público.

**Decisión**: parsear `https://www.minorplanetcenter.net/iau/NEO/pccp_tabular.html`
con lxml en `core/sources/pccp.py` (columnas: designación temporal, score, RA/Dec, V,
arco, notas...). Los candidatos entran en la lista unificada de «Esta noche» con bonus
de urgencia alto. El NEOCP queda cubierto vía NEOfixer (flag `neocp`), sin duplicar
fuentes.

**Alternativas**: ignorar PCCP (pierde una pata del observatorio); API no pública del
MPC (no existe para PCCP).

**Consecuencias**: scraping frágil por naturaleza → parser defensivo con fixture HTML
en tests y degradación elegante si el MPC cambia el formato.

## English

**Context**: the MPC's PCCP (*Possible Comet Confirmation Page*) lists candidate
comets awaiting confirmation — outreach and scientific gold for an observatory that
reports to the MPC. No public JSON endpoint exists.

**Decision**: parse `https://www.minorplanetcenter.net/iau/NEO/pccp_tabular.html`
with lxml in `core/sources/pccp.py` (columns: temporary designation, score, RA/Dec,
V, arc, notes...). Candidates join the unified "Tonight" list with a high urgency
bonus. NEOCP is covered via NEOfixer (`neocp` flag), without duplicating sources.

**Alternatives**: ignore PCCP (loses an observatory pillar); non-public MPC API
(none exists for PCCP).

**Consequences**: scraping is inherently fragile → defensive parser with an HTML
fixture in tests and graceful degradation if the MPC changes the format.
