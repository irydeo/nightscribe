# ADR-007: Code style — saas headers and human voice

**Estado / Status**: Accepted · **Fecha / Date**: 2026-08-21

## Español

**Contexto**: el código debe ser fácil de mantener por personas y no parecer generado
por IA.

**Decisión**: todos los `.py` llevan la cabecera histórica de `saas` (autor, año,
GPL v3); comentarios cortos en inglés con `# @args:` / `# @return:` sobre cada método;
logging en vez de prints; funciones cortas; TODOs como `# TODO:`; sin docstrings
robóticos ni sobre-ingeniería.

**Alternativas**: docstrings estilo Google/Numpy en todo (más formal, menos "humano");
sin cabeceras (pierde la identidad del autor).

**Consecuencias**: estilo consistente con `saas`; la regla está fijada en
`AGENTS.md` y `CONTRIBUTING`.

## English

**Context**: the code must be easy for humans to maintain and must not look
AI-generated.

**Decision**: every `.py` carries the historical `saas` header (author, year,
GPL v3); short English comments with `# @args:` / `# @return:` above each method;
logging instead of prints; short functions; TODOs as `# TODO:`; no robotic docstrings
or over-engineering.

**Alternatives**: Google/Numpy docstrings everywhere (more formal, less "human");
no headers (loses the author's identity).

**Consequences**: style consistent with `saas`; the rule is pinned in `AGENTS.md`
and `CONTRIBUTING`.
