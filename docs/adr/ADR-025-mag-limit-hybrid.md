# ADR-025: Limiting magnitude — hard cut where measured, soft warning where predicted

**Estado / Status**: Accepted · **Fecha / Date**: 2026-08-25

## Español

**Contexto**: con `limit_mag = 20` la app presentaba objetivos de magnitud 21
(sin que nada lo advirtiera). El análisis del 2026-08-25 lo explicó: las familias
cortan de forma **dura** según convenga — SN (`rochester.latest_sne`) y cometas
(`cobs.active_comets`) descartan `mag > limit_mag` porque su brillo es una medida
real — pero NEO (NEOfixer) y PCCP (scraping MPC) no aplican ese corte, y el
puntuador solo los penalizaba levemente
(`clamp((limit - mag)/4*6, 0, 6)`). El resultado: el planificador era
inconsistente con el limitador de magnitud que el usuario configuró para su
equipo.

**Decisión**: aplicar una política **híbrida**, consistente con la naturaleza
de cada magnitud:

1. **Familias con magnitud medida (SN, cometas, exoplanetas)**: filtro **duro**
   donde ya existe (`rochester.py`, `cobs.py`, `transits.py`). Un objetivo cuyo
   brillo real supera la limitación del equipo no lo vamos a proponer.

2. **Familias con magnitud prevista (NEO, PCCP)**: filtro **suave** —
   `suggest.beyond_limit(t, cfg) -> (is_beyond, delta_mags)` decide si la
   magnitud prevista supera el límite y en cuántas. `suggest._observability`
   aplica una penalización extra `clamp((mag - limit) / 2 * 3, 0, 3)` que
   hunde al objetivo por debajo de otros más alcanzables, pero **sin
   descartarlo**: un NEO de 21 mags puede ser un NEOCP que necesita cada
   medida.

3. **Aviso visible en los tres puntos de contacto**:
   - GUI: etiqueta ámbar `⚠ mag >20` en la tarjeta, con tooltip bilingüe
     que explica el motivo (ADR-025).
   - CLI `tonight`: sufijo `▲ mag>20` en cada objetivo que la padece, y una
     línea resumen al final (`2 objetivos por encima de la magnitud límite`).
   - `top_n` no modifica su orden: el score decide — la etiqueta solo avisa.

La traducción de las cadenas nuevas pasa por Qt Linguist
(ADR-014); en ES: *"Magnitud prevista por encima de tu magnitud límite en
{delta} mags. Sigue puntuándose por su prioridad científica, pero necesitará
una exposición más larga que un objetivo brillante y fácil."*

**Consecuencias**:

- El planificador respeta la magnitud límite de forma **explicable**:
  el usuario sabe si un objetivo está fuera de alcance y por qué, y puede
  decidir si igual lo intenta.
- La penalización extra es acotada (−3 pts al llegar a +2 mags sobre el
  límite) para no hacer inviable la lista por un solo objeto de 21 mags.
- El aviso es idempotente: llamar a `beyond_limit` dos veces devuelve el
  mismo resultado; en `top_n` se llama una vez por objetivo.
- Tests: `tests/unit/test_suggest.py` valida el helper, la penalización
  acotada, y que un NEO de 21 mags sobrevive a `top_n` con 2 objetivos
  ambos fuera de límite.

**Escopado**: el aviso en la GUI/CLI usa la etiqueta `⚠`/`▲` ya establecida
por la restricción lunar (ADR-020). No se añade un canal de notificación
independiente — el propio diseño "soft" de ADR-020 ya justifica la
coherencia.

## English

**Context**: with `limit_mag = 20` the app presented 21-mag targets and never
warned about it. The 2026-08-25 analysis explained it: families cut
**hard** where appropriate — SNe (`rochester.latest_sne`) and comets
(`cobs.active_comets`) drop `mag > limit_mag` because their brightness is
measured — while NEOs (NEOfixer) and PCCPs (MPC scraping) apply no such cut,
and the scorer barely penalized them
(`clamp((limit - mag)/4*6, 0, 6)`). Result: the planner was not consistent
with the equipment's limiting magnitude the user had configured.

**Decision**: apply a **hybrid** policy, consistent with the nature of each
magnitude:

1. **Measured-magnitude families (SNe, comets, exoplanets)**: keep the
   existing **hard** cut in `rochester.py`, `cobs.py`, `transits.py`. A
   target whose real brightness exceeds the setup is not one we should
   propose.

2. **Predicted-magnitude families (NEOs, PCCPs)**: **soft** filter —
   `suggest.beyond_limit(t, cfg) -> (is_beyond, delta_mags)` decides whether
   the predicted magnitude exceeds the limit, and by how much.
   `suggest._observability` applies an extra penalty
   `clamp((mag - limit) / 2 * 3, 0, 3)` that sinks the target below easier
   ones, **without dropping it**: a 21-mag NEO can still be a NEOCP that
   needs every measurement.

3. **A visible warning at the three touchpoints**:
   - GUI: an amber `⚠ mag >20` chip on the card, with a bilingual tooltip
     explaining the reason (ADR-025).
   - CLI `tonight`: a `▲ mag>20` suffix on each affected target, plus a
     summary line at the end
     (`2 targets beyond the mag 20 limit`).
   - `top_n` ordering is unchanged: the score decides — the chip only warns.

The new strings go through Qt Linguist (ADR-014); the ES translation is:
*"Magnitud prevista por encima de tu magnitud límite en {delta} mags.
Sigue puntuándose por su prioridad científica, pero necesitará una exposición
más larga que un objetivo brillante y fácil."*

**Consequences**:

- The planner honours the limiting magnitude **explainably**: the user
  knows when a target is out of reach and why, and can still decide to
  try it.
- The extra penalty is capped (−3 pts at +2 mags above the limit) so a
  single 21-mag object cannot make the list unworkable.
- The warning is idempotent: calling `beyond_limit` twice returns the same
  result; in `top_n` it is called once per target.
- Tests: `tests/unit/test_suggest.py` covers the helper, the capped
  penalty, and that a 21-mag NEO survives `top_n` with both targets beyond
  the limit.

**Scope note**: the GUI/CLI warning reuses the `⚠`/`▲` glyph already
established by the Moon constraint (ADR-020). No separate notification
channel is added — the "soft" design of ADR-020 already justifies shared
style.
