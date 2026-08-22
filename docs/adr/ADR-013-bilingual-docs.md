# ADR-013: Bilingual documentation (ES/EN), English-only code

**Estado / Status**: Accepted · **Fecha / Date**: 2026-08-21

## Español

**Contexto**: el autor es hispanohablante, el software se publica para la comunidad
internacional, y la documentación debe servir a personas y a IAs.

**Decisión**: **código siempre en inglés**; documentación en **español e inglés**:
ficheros gemelos `NOMBRE.md` (EN) / `NOMBRE.es.md` (ES) con enlaces cruzados para los
documentos largos; `AGENTS.md` y los ADRs llevan ambas secciones en el mismo fichero
para no desincronizar decisiones. El contenido generado (posts, frases) se produce
siempre en ambos idiomas.

**Alternativas**: todo en inglés (barrera para el autor y su comunidad local);
documentación solo en español (cierra la puerta internacional); un solo fichero
bilingüe para todo (difícil de leer en documentos largos).

**Consecuencias**: doble mantenimiento documental asumido; las plantillas de posts
viven en `narrative.py`/`post.py` en ambos idiomas por diseño.

## English

**Context**: the author is a Spanish speaker, the software is published for the
international community, and the documentation must serve humans and AIs.

**Decision**: **code is always English**; documentation in **Spanish and English**:
twin files `NAME.md` (EN) / `NAME.es.md` (ES) with cross-links for long documents;
`AGENTS.md` and ADRs carry both sections in the same file so decisions never drift.
Generated content (posts, phrases) is always produced in both languages.

**Alternatives**: all English (barrier for the author and his local community);
Spanish-only docs (closes the international door); one bilingual file for everything
(hard to read in long documents).

**Consequences**: double documentation maintenance accepted; post templates live in
`narrative.py`/`post.py` in both languages by design.
