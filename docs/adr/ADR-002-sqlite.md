# ADR-002: SQLite for cache and state

**Estado / Status**: Accepted · **Fecha / Date**: 2026-08-21

## Español

**Contexto**: las consultas a fuentes externas son costosas (red, límites de uso) y hay
que persistir listas de objetivos, marcas de «observado», historial de posts y ajustes.

**Decisión**: **SQLite** (stdlib) en el directorio de datos del usuario, con tablas
`http_cache` (TTL por fuente), `targets`, `observations`, `settings`. Acceso único vía
`core/db.py`.

**Alternativas**: ficheros JSON con TTL (demasiado frágiles para estado acumulativo);
servidor externo (contra la filosofía offline-friendly).

**Consecuencias**: cero dependencias nuevas, consultas con SQL real (historial,
anti-repetición), mismo patrón que usaba `saas`. Migraciones con `PRAGMA user_version`.

## English

**Context**: external source queries are expensive (network, rate limits) and we must
persist target lists, "observed" marks, post history and settings.

**Decision**: **SQLite** (stdlib) in the user data dir, with tables `http_cache`
(per-source TTL), `targets`, `observations`, `settings`. Single access point via
`core/db.py`.

**Alternatives**: JSON files with TTL (too fragile for accumulative state); external
server (against the offline-friendly philosophy).

**Consequences**: zero new dependencies, real SQL queries (history, anti-repetition),
same pattern as `saas`. Migrations via `PRAGMA user_version`.
