# ADR-006: Rule-based suggestion engine with outreach bonus

**Estado / Status**: Accepted · **Fecha / Date**: 2026-08-21

## Español

**Contexto**: «Esta noche» debe sugerir los mejores objetivos de forma atractiva y
simple, mezclando NEOs, supernovas, cometas, PCCP y tránsitos en una sola lista.

**Decisión**: score unificado 0–100 con cuatro familias ponderadas (prioridad
científica, observabilidad, urgencia, **gancho divulgativo**) y frases «por qué esta
noche» por reglas. Detalles en `docs/SCORING.md`.

**Alternativas**: listados separados por tipo (menos simple); machine learning
(opaco, inmantenible aquí); solo score NEOfixer (no cubre SNs/cometas/tránsitos).

**Consecuencias**: reglas explícitas y testeables; el bonus divulgativo es nuestro
diferencial; el historial de posts realimenta el score (anti-repetición).

## English

**Context**: "Tonight" must suggest the best targets in an attractive, simple way,
mixing NEOs, supernovae, comets, PCCP and transits in one list.

**Decision**: unified 0–100 score with four weighted families (scientific priority,
observability, urgency, **outreach hook**) and rule-based "why tonight" phrases.
Details in `docs/SCORING.md`.

**Alternatives**: separate per-type listings (less simple); machine learning (opaque,
unmaintainable here); NEOfixer score only (does not cover SNe/comets/transits).

**Consequences**: explicit, testable rules; the outreach bonus is our differentiator;
post history feeds back into the score (anti-repetition).
