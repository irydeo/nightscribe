# ADR-000: Use Architecture Decision Records

**Estado / Status**: Accepted · **Fecha / Date**: 2026-08-21

## Español

**Contexto**: NightScribe debe ser mantenible por personas y otras IAs; las decisiones
de diseño se olvidan si no se escriben.

**Decisión**: cada decisión de arquitectura/diseño se documenta como un ADR numerado en
`docs/adr/`, bilingüe (ES/EN), con formato: Contexto · Decisión · Alternativas ·
Consecuencias. Los ADRs aceptados no se reescriben; se sustituyen por uno nuevo que los
referencia.

**Consecuencias**: cualquier colaborador puede entender el *porqué* del código en
minutos. Cambiar una decisión exige actualizar o crear el ADR correspondiente.

## English

**Context**: NightScribe must be maintainable by humans and other AIs; design decisions
are forgotten unless written down.

**Decision**: every architecture/design decision is documented as a numbered ADR in
`docs/adr/`, bilingual (ES/EN), format: Context · Decision · Alternatives ·
Consequences. Accepted ADRs are not rewritten; a new superseding ADR references them.

**Consequences**: any contributor can understand the *why* of the code in minutes.
Changing a decision requires updating or creating the matching ADR.
