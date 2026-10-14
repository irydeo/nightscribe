# ADR-087: El tipo orbital oficial del MPC (API de órbitas)

**Estado / Status**: Accepted · **Fecha / Date**: 2026-10-14

**Ver / See**: ADR-058 (explicar los códigos), ADR-077 (identidad NEOCP), ADR-062 (astrometría).

## Español

**Contexto**: al confirmarse `Sar2949` como `2026 TG69`, la ficha del proyecto
lo clasificaba como **Apollo** mientras la página del MPC que el observador
miraba decía **Amor**. Comprobadas las tres fuentes con el mismo objeto y la
misma época:

| Fuente | Tipo |
|---|---|
| Nuestra regla local (`q < 1.017` -> Apollo) | Apollo |
| JPL SBDB (`orbit_code: APO`) | Apollo |
| **API de órbitas del MPC** (`get-orb`, `orbit_type_str`) | Apollo |
| **Página `db_search` del MPC** | Amor |

El MPC se contradice entre su propia API y su página. La regla local coincide
con JPL y con la API, pero el observador compara contra la página, y ahí ve
otra cosa. Nuestra clasificación (`orbits.classify`) es una **aproximación**
(q < 1.017 -> Apollo) que no es la del MPC.

**Decisión**: la familia de un objeto **confirmado** se toma del **tipo oficial
del MPC** cuando está disponible y es una de las familias que nombramos igual.

1. **Nueva fuente** `core/sources/mpc_orbits.py` (`get_orb`), contra la API de
   órbitas del MPC (`get-orb`, GET con cuerpo JSON, igual que `get-obs`; TTL
   24 h por la caché de `core/db`). Devuelve el `orbit_type_str` del bloque
   `categorization`, los elementos del bloque `KEP` (con `q` y `Q` derivados de
   `a` y `e`, que no vienen) y el MOID.
2. **Sólo manda para las familias NEO** que el MPC nombra como nosotros
   (`Atira`, `Aten`, `Apollo`, `Amor`; `orbits.NEO_FAMILIES`). Las demás
   etiquetas del MPC (Mars Crosser, Hungaria, Jupiter Trojan, ...) no casan con
   nuestras claves, así que para ellas se mantiene nuestra clasificación. Si la
   API no conoce el objeto (un NEOCP sin confirmar) o no hay red, se mantiene
   la regla local: la fuente nunca rompe la ficha.
3. **Se dice de quién es el dato** (`family_source`): la fila «Familia» añade
   «Es la clasificación del propio MPC» cuando viene de ahí. Sin esto, el
   observador no puede saber si el tipo es el del MPC o una deducción nuestra
   (regla permanente: ninguna clasificación sin explicación, ADR-058).

**Medido (2026-10-14)**: para `2026 TG69` la API del MPC responde
`orbit_type_str: "Apollo"` con `a = 1.7960`, `e = 0.4426`, `i = 26.61°`,
MOID Tierra = 0.0225 AU. La ficha pasa a mostrar **Apollo, del MPC**, que es lo
que dicen JPL y la propia API (la página `db_search` sigue diciendo Amor: es su
contradicción, no la nuestra). El valor real de esto es que el día que el MPC
reclasifique el objeto, la ficha lo seguirá sin tocar código.

**Consecuencias**: `enrich._enrich_small_body` consulta `mpc_orbits.get_orb` y
deja en el diccionario enriquecido `mpc_orbit_type` y `family_source`;
`orbits.explain_elements` gana `family_source`; `gui/overview._orbit_rows` lo
pasa. Un objeto **sin confirmar** sigue por el camino preliminar (NEOfixer),
donde el MPC no tiene órbita que consultar.

**Revisión (2026-10-14, el tipo se lee de la API de órbitas del MPC)**: el
contexto y la decisión son los de arriba; esta sección fija la fuente.

## English

**Context**: when `Sar2949` was confirmed as `2026 TG69`, the project card
classified it as **Apollo** while the MPC page the observer was looking at said
**Amor**. Checked against the same object and epoch:

| Source | Type |
|---|---|
| Our local rule (`q < 1.017` -> Apollo) | Apollo |
| JPL SBDB (`orbit_code: APO`) | Apollo |
| **MPC Orbits API** (`get-orb`, `orbit_type_str`) | Apollo |
| **MPC `db_search` page** | Amor |

The MPC contradicts itself between its own API and its page. The local rule
agrees with JPL and the API, but the observer compares against the page and
sees something else. Our classification (`orbits.classify`) is an
**approximation** (q < 1.017 -> Apollo), not the MPC's.

**Decision**: the family of a **confirmed** object is taken from the **MPC's
official type** when available and when it is one of the families we name the
same way.

1. **New source** `core/sources/mpc_orbits.py` (`get_orb`), against the MPC
   Orbits API (`get-orb`, a GET with a JSON body, like `get-obs`; 24 h TTL
   through `core/db`). It returns the `orbit_type_str` from the
   `categorization` block, the elements from the `KEP` block (with `q` and `Q`
   derived from `a` and `e`, which are not given) and the MOID.
2. **It only wins for the NEO families** the MPC names as we do (`Atira`,
   `Aten`, `Apollo`, `Amor`; `orbits.NEO_FAMILIES`). The MPC's other labels
   (Mars Crosser, Hungaria, Jupiter Trojan, ...) do not match our keys, so our
   classification stays for them. If the API does not know the object (an
   unconfirmed NEOCP) or there is no network, the local rule stands: the source
   never breaks the card.
3. **Whose value it is, is said** (`family_source`): the "Family" row adds "It
   is the MPC's own classification" when it comes from there. Without it the
   observer cannot tell whether the type is the MPC's or our deduction
   (permanent rule: no classification without an explanation, ADR-058).

**Measured (2026-10-14)**: for `2026 TG69` the MPC API answers
`orbit_type_str: "Apollo"` with `a = 1.7960`, `e = 0.4426`, `i = 26.61°`,
Earth MOID = 0.0225 AU. The card now shows **Apollo, from the MPC**, which is
what JPL and the API say (the `db_search` page still says Amor: that is the
MPC's contradiction, not ours). The real value is that the day the MPC
reclassifies the object, the card follows with no code change.

**Consequences**: `enrich._enrich_small_body` calls `mpc_orbits.get_orb` and
leaves `mpc_orbit_type` and `family_source` in the enriched dict;
`orbits.explain_elements` gains `family_source`; `gui/overview._orbit_rows`
passes it. An **unconfirmed** object keeps the preliminary path (NEOfixer),
where the MPC has no orbit to query.
