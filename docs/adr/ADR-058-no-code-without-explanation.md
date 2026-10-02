# ADR-058: Ningún código, clasificación o cifra sin explicación / No code, classification or figure without an explanation

**Estado / Status**: Accepted · **Fecha / Date**: 2026-10-02 ·
**ejecutado / executed**: 2026-10-02 (suite unitaria green, i18n 0
unfinished)

**Ver / See**: ADR-057 (la ficha como dossier, que hizo más visible el
problema en las teselas KPI) · ADR-013/ADR-017 (prosa y explicaciones
bilingües) · ADR-031 (la ficha unificada) · ADR-005 (los `.ui`)

## Español

**Contexto.** NightScribe muestra clasificaciones y cifras por todas
partes: tipos de supernova, tipos VSX, clases espectrales, métodos de
descubrimiento, prioridad NEOfixer, magnitudes, profundidades, distancias.
En muchos sitios el dato llegaba solo, como un código: el hook decía «una
supernova de tipo Ia» sin decir qué es una Ia, los bullets de un candidato
decían «Tipo de evento: II» y paraban, la prioridad NEOfixer se repetía
(«Su categoría de prioridad: A.») y las teselas de la ficha (ADR-057)
mostraban «Ia» con un tooltip genérico. La explicación existía en unos
sitios y faltaba en otros, y el conocimiento estaba duplicado entre
`orbits.py` y `narrative.py`. El observador lo resumió así: «decir un tipo
y no explicar nada más es quedarte a medias; y esto deberíamos hacerlo
siempre y con todos los tipos de objetos».

**Decisión** (pactada con el observador, 2026-10-02):

1. **Regla permanente**: ningún código, clasificación ni cifra se enseña a
   secas. Siempre va con qué significa y por qué importa. Queda escrita en
   `AGENTS.md` y protegida por tests.
2. **Un solo hogar**: `core/explain.py` reúne «qué significa este código o
   esta cifra». Ningún módulo duplica ese conocimiento.
3. **Dos densidades**: cada taxonomía devuelve `{"short","long"}`:
   `short` es una frase (hooks, tooltips, tuits) y `long` es una
   mini-ficha (qué es, cómo se reconoce, subtipos, qué nos dice, por qué
   importa al observador). Las cifras llevan solo `short`.
4. **Taxonomías cubiertas**: `sn_type` (Ia, Iax, Ib/c, II, II-P, II-L,
   IIn, SLSN, kilonova, nova, genérico), `variable_type` (decodifica
   **todos** los componentes de un tipo VSX compuesto, p. ej. `NR+ELL`),
   `spectral_class`, `discovery_method`, `neofixer_priority`, `flare_class`.
5. **Cifras cubiertas**: magnitud, tasa aparente, altura, profundidad,
   período, exposición, Luna, distancia, corrimiento al rojo, época, σ,
   ley cometaria M1/K1, tamaño, albedo, índice Kp.
6. **Fallbacks honestos**: un código desconocido nunca deja la cadena
   vacía; devuelve «aún se está clasificando», que es verdad y enseña.
7. **Cableado**: `orbits.explain_*` usa la densidad `long` en las filas de
   tipo y cierra los huecos (prioridad NEOfixer, modos de pulsación en el
   idioma activo, componentes compuestos, método de descubrimiento);
   `narrative.py` usa `short` en los hooks y `long` en los bullets (de
   modo que los posts heredan la mini-ficha); las teselas KPI de
   `overview.py` explican la cifra en su tooltip.
8. **Guardas**: `tests/unit/test_explain.py` exige que cada explicador
   responda para sus códigos conocidos y para uno desconocido, en los dos
   idiomas, con una mini-ficha real; los tests de la ficha y de la prosa
   comprueban que ningún tipo llega sin explicación.

**Consecuencias.** Más texto en la ficha y en los posts: es el precio de
no dejar al lector a medias. Toda clasificación o cifra nueva debe añadir
su entrada en `core/explain.py` y su test; los tooltips de las teselas
crecen, pero el valor visible sigue siendo corto. i18n: las cadenas
nuevas se traducen ES/EN y los `.ts`/`.qm` se regeneran.

## English

**Context.** NightScribe shows classifications and figures everywhere:
supernova types, VSX types, spectral classes, discovery methods, NEOfixer
priority, magnitudes, depths, distances. In many places the datum arrived
alone, as a code: the hook said "a type-Ia supernova" without saying what
an Ia is, a candidate's bullets said "Event type: II" and stopped, the
NEOfixer priority just repeated itself ("Its priority category: A.") and
the card's tiles (ADR-057) showed "Ia" with a generic tooltip. The
explanation existed in some places and was missing in others, and the
knowledge was duplicated between `orbits.py` and `narrative.py`. The
observer summed it up: "naming a type and explaining nothing else leaves
you half done; and we should do this always and for every object type".

**Decision** (agreed with the observer, 2026-10-02):

1. **Permanent rule**: no code, classification or figure is shown bare. It
   always comes with what it means and why it matters. It is written in
   `AGENTS.md` and protected by tests.
2. **One home**: `core/explain.py` gathers "what this code or figure
   means". No module duplicates that knowledge.
3. **Two densities**: every taxonomy returns `{"short","long"}`: `short`
   is one sentence (hooks, tooltips, tweets) and `long` is a mini-dossier
   (what it is, how it is recognised, subtypes, what it tells us, why the
   observer cares). Figures carry only `short`.
4. **Taxonomies covered**: `sn_type` (Ia, Iax, Ib/c, II, II-P, II-L, IIn,
   SLSN, kilonova, nova, generic), `variable_type` (decodes **every**
   component of a composite VSX type, e.g. `NR+ELL`), `spectral_class`,
   `discovery_method`, `neofixer_priority`, `flare_class`.
5. **Figures covered**: magnitude, apparent rate, altitude, depth, period,
   exposure, Moon, distance, redshift, epoch, σ, M1/K1 comet law, size,
   albedo, Kp index.
6. **Honest fallbacks**: an unknown code never leaves the string empty; it
   returns "still being classified", which is true and still teaches.
7. **Wiring**: `orbits.explain_*` uses the `long` density for type rows
   and closes the gaps (NEOfixer priority, pulsation modes in the active
   language, composite components, discovery method); `narrative.py` uses
   `short` in hooks and `long` in bullets (so posts inherit the
   mini-dossier); the KPI tiles in `overview.py` explain the figure in
   their tooltip.
8. **Guards**: `tests/unit/test_explain.py` requires every explainer to
   answer for its known codes and for an unknown one, in both languages,
   with a real mini-dossier; the card and prose tests check that no type
   arrives without its explanation.

**Consequences.** More text on the card and in the posts: that is the
price of not leaving the reader half done. Every new classification or
figure must add its entry in `core/explain.py` and its test; the tile
tooltips grow, but the visible value stays short. i18n: new strings are
translated ES/EN and the `.ts`/`.qm` are regenerated.
