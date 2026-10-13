# ADR-077: Identidad NEOCP: la referencia por su nombre confirmado, el listado de residuos y el aviso de renombrado

**Estado / Status**: Accepted · **Fecha / Date**: 2026-10-10

## Español

**Contexto**: sobre un track & stack real de 450 fotogramas de un objeto
observado en el NEOCP (designación temporal `A11HPKO`) el chequeo delegado en
Find_Orb no producía nada: la interfaz decía «The check is not available:
Find_Orb produced no residuals». El objeto SÍ era bueno: se confirmó como
`2026 TQ8` entre la visita y la comprobación, y su MPEC es `MPEC 2026-T201`. La
cadena de causas, reproducida con el binario real y los datos reales:

1. **La referencia se pedía solo al endpoint de objetos confirmados.**
   `core/findorb.check` llamaba a `mpc_obs.observations_80(desig)`, que para una
   designación temporal del NEOCP responde **HTTP 500**: el objeto todavía no
   existe en la base de confirmados. No había camino al endpoint del NEOCP.
2. **Sin «los demás», Find_Orb no tiene nada que ajustar.** Con solo nuestra
   línea, `fo` escribe `Processing 0 objects` y su `total.json` queda
   **truncado** (`"objects": {` y nada más): no es JSON válido, y el parser lo
   trataba como «no hay residuos».
3. **El mensaje confundía tres causas distintas**: no hay binario, no hay
   observaciones de referencia, o no se ha podido ajustar. El usuario no podía
   saber cuál era.
4. **No se veía el listado.** El veredicto era una línea de texto; no había la
   tabla de observaciones publicadas con la nuestra dentro y su error, que es lo
   que el observador reconoce de Find_Orb (y de Tycho-Tracker).
5. **La identidad se perdía al confirmarse el objeto.** Nada avisaba de que el
   objeto visitado como `A11HPKO` ya era `2026 TQ8`, ni de que las observaciones
   propias podían estar ya en la circular.

**Medido (2026-10-10, `fo` real, datos reales)**: alimentando a Find_Orb las 36
observaciones publicadas de `2026 TQ8` más nuestro punto real de Z41
(`RA 33.359775°, Dec 35.418595°`, MJD 61322.9159536548), el ajuste da **36
residuos** y **nuestro residuo es dRA −0.20″ / dDec +0.11″**, dentro de la nube
(mediana de los demás ≈ −0.03 / −0.02): **el chequeo pasa**. El fallo nunca fue
de la medida, era de identidad.

**Decisión**: cinco cambios.

1. **Estrategia de referencia** (`core/sources/mpc_obs.reference_80`), en este
   orden: (1) el endpoint de confirmados; (2) el del NEOCP por `trksub`
   (`neocp_observations_80`); (3) si el objeto dejó el NEOCP, resolver la
   designación temporal a la confirmada leyendo la lista rodante «Previous NEOCP
   Objects» del MPC (`resolve_neocp_alias`) y volver a pedir por el nombre nuevo.
   Una respuesta vacía es una respuesta («aún no hay observaciones publicadas»),
   nunca un error. La página del MPC es la única fuente del mapeo `A11HPKO →
   2026 TQ8`: ni NEOfixer ni la API de designaciones del MPC conocen el `trksub`.
2. **Estados honestos y distintos** en `CheckReport`: `available=False` (sin
   binario), `no_reference=True` (sin observaciones publicadas) y `no_fit=True`
   (se ejecutó, pero el arco de referencia es demasiado corto para ajustar una
   órbita). El parser detecta el `total.json` truncado (el caso de 0 objetos) y lo
   trata como «no ajustó», no como «no hay residuos».
3. **El listado de residuos** viaja en el `CheckReport` (`residuals`): instante,
   estación, dirección observada, `dRA`/`dDec` y magnitud, con una marca `ours`
   por fila. Lo nuestro se identifica **por el instante que enviamos** (el
   `JD`), luego por nuestra estación, y solo si no hay nada, por la primera línea
   (la nuestra va primera en el fichero). La interfaz lo pinta en una tabla
   **en un diálogo no modal**, que se abre con un botón del bloque del chequeo
   («Observaciones publicadas…»), con nuestras filas resaltadas: el bloque es una
   columna de 380 px y la tabla ancha no cabe ahí sin empujar el resto del panel,
   y así el observador puede dejar el listado abierto mientras trabaja. El run lo
   persiste para que un run reabierto muestre el mismo listado.
4. **El aviso de renombrado**, muy visible, en tres sitios: el bloque del
   chequeo, la ficha del proyecto y la cabecera de la visita. Dice el nombre
   nuevo, la circular que lo publicó y, cuando nuestra estación ya aparece entre
   las observaciones publicadas, que **nuestros datos están en esa circular**. La
   ficha y la visita lo leen del contexto del proyecto (lo escribe la búsqueda de
   alias, cacheada y en segundo plano); no vuelven a tocar la red al pintar.
5. **Re-chequeo ligero y designación a mano**: un campo con la designación
   (pre-rellenado con el nombre que el objeto tiene AHORA) y un botón «Recomprobar»
   que repite el chequeo sobre los puntos YA medidos, **sin re-apilar** los
   fotogramas: solo la ida y vuelta al MPC y Find_Orb. Es la puerta para un objeto
   que se confirmó después de que la lista rodante lo olvidara.

**Consecuencias**: `CheckReport` gana `residuals`, `reference`, `resolved_desig`,
`mpec`, `mpec_url`, `confirmed_at`, `ours_published`, `n_obs` y `no_fit`; el
resumen persistido del run los lleva; el contexto del proyecto gana `confirmed`.
Nada de esto toca la medida: el listado y el aviso son información, y el veredicto
sigue comparando nuestro residuo con la dispersión robusta de los demás (ADR-062).
El scraping de la lista del MPC va por `core/db.py` (cacheado, TTL 6 h), como toda
consulta de red.

**Alternativas**: (a) pedir siempre al endpoint del NEOCP, descartado: un objeto
confirmado no está allí; (b) no mostrar el listado y quedarse con la línea de
veredicto, descartado: el observador pidió ver su error junto al de los demás; (c)
re-apilar para re-chequear, descartado por coste (450 fotogramas por cada
designación que se prueba); (d) inventar un veredicto cuando no hay referencia,
descartado: sin nadie con quien comparar no se bloquea y se dice por qué
(ADR-062, D29); (e) resolver el alias con la API de designaciones del MPC,
descartado: no conoce los `trksub` del NEOCP.

## English

**Context**: on a real track & stack of 450 frames of an object observed on the
NEOCP (temporary designation `A11HPKO`) the Find_Orb-delegated check produced
nothing: the interface said "The check is not available: Find_Orb produced no
residuals". The object WAS good: it was confirmed as `2026 TQ8` between the visit
and the check, and its MPEC is `MPEC 2026-T201`. The chain of causes, reproduced
with the real binary and the real data:

1. **The reference was fetched only from the confirmed-object endpoint.**
   `core/findorb.check` called `mpc_obs.observations_80(desig)`, which answers
   **HTTP 500** for a NEOCP temporary designation: the object does not exist yet
   in the confirmed database. There was no path to the NEOCP endpoint.
2. **Without "the others", Find_Orb has nothing to fit.** With our line alone,
   `fo` writes `Processing 0 objects` and its `total.json` is left **truncated**
   (`"objects": {` and nothing else): not valid JSON, and the parser read it as
   "no residuals".
3. **The message conflated three different causes**: no binary, no reference
   observations, or a fit that did not converge. The user could not tell which.
4. **The listing was not shown.** The verdict was one line of text; there was no
   table of the published observations with ours among them and their error,
   which is what the observer recognises from Find_Orb (and from Tycho-Tracker).
5. **The identity was lost when the object was confirmed.** Nothing warned that
   the object visited as `A11HPKO` was now `2026 TQ8`, nor that the observer's own
   observations might already be in the circular.

**Measured (2026-10-10, real `fo`, real data)**: feeding Find_Orb the 36 published
observations of `2026 TQ8` plus our real Z41 point (`RA 33.359775°`,
`Dec 35.418595°`, MJD 61322.9159536548), the fit returns **36 residuals** and
**our residual is dRA −0.20″ / dDec +0.11″**, inside the cloud (the others' median
≈ −0.03 / −0.02): **the check passes**. The failure was never the measurement, it
was the identity.

**Decision**: five changes.

1. **Reference strategy** (`core/sources/mpc_obs.reference_80`), in this order:
   (1) the confirmed endpoint; (2) the NEOCP one by `trksub`
   (`neocp_observations_80`); (3) if the object left the NEOCP, resolve the
   temporary designation to the confirmed one by reading the MPC's rolling
   "Previous NEOCP Objects" list (`resolve_neocp_alias`) and fetch again under the
   new name. An empty answer is an answer ("no published observations yet"), never
   an error. The MPC page is the only source of the `A11HPKO → 2026 TQ8` mapping:
   neither NEOfixer nor the MPC designation API knows the `trksub`.
2. **Honest, distinct states** in `CheckReport`: `available=False` (no binary),
   `no_reference=True` (no published observations) and `no_fit=True` (it ran, but
   the reference arc is too short to fit an orbit). The parser detects the
   truncated `total.json` (the 0-object case) and treats it as "could not fit",
   not as "no residuals".
3. **The residual listing** travels in the `CheckReport` (`residuals`): instant,
   station, observed direction, `dRA`/`dDec` and magnitude, with an `ours` flag
   per row. Ours is identified **by the instant we submitted** (the `JD`), then by
   our station, and only failing that by the first line (ours goes first in the
   file). The interface paints it in a table **in a non-modal dialog**, opened by
   a button in the check block ("Published observations…"), our rows highlighted:
   the block is a 380 px column and the wide table does not fit there without
   pushing the rest of the panel out, and this way the observer can keep the
   listing open while working. The run persists it so a reopened run shows the
   same listing.
4. **The rename notice**, very visible, in three places: the check block, the
   project card and the visit header. It states the new name, the circular that
   published it and, when our station already appears among the published
   observations, that **our data is in that circular**. The card and the visit
   read it from the project's context (written by the alias lookup, cached and in
   the background); they never touch the network while painting.
5. **Lightweight re-check and a hand-typed designation**: a field with the
   designation (prefilled with the name the object has NOW) and a "Re-check"
   button that repeats the check on the ALREADY measured points, **without
   re-stacking** the frames: only the MPC round trip and Find_Orb. It is the door
   for an object confirmed after the rolling list forgot it.

**Consequences**: `CheckReport` gains `residuals`, `reference`, `resolved_desig`,
`mpec`, `mpec_url`, `confirmed_at`, `ours_published`, `n_obs` and `no_fit`; the
run's persisted summary carries them; the project's context gains `confirmed`.
None of this touches the measurement: the listing and the notice are information,
and the verdict still compares our residual with the robust scatter of the others
(ADR-062). The scraping of the MPC list goes through `core/db.py` (cached, 6 h
TTL), like every network query.

**Alternatives**: (a) always asking the NEOCP endpoint, rejected: a confirmed
object is not there; (b) not showing the listing and keeping the verdict line,
rejected: the observer asked to see their error next to the others'; (c)
re-stacking to re-check, rejected on cost (450 frames per designation tried); (d)
inventing a verdict when there is no reference, rejected: with nobody to compare
with nothing is blocked and it is said why (ADR-062, D29); (e) resolving the alias
with the MPC designation API, rejected: it does not know the NEOCP `trksub`.

**Review (2026-10-13, the notice does not assume participation, and it fires for any temporary designation)**: two fixes, no change to the measurement.

1. **The card and the visit no longer claim participation.** `main_window._paint_confirmation` and `widgets/visits_panel._paint_confirmation` always appended "Your observations of it are in that circular", even when our station was not among the published ones (the check block already did it right, only when `ours_published`). Now the banner says the new name and the MPEC, and adds **"your observations are among them: your data is in that MPEC" only when `confirmed.ours_published` is true**; otherwise it links to the object at the MPC and claims nothing. To make that flag available to the card, `_ufe_astrometry_persist` writes the check's `resolved_desig`/`mpec`/`mpec_url`/`confirmed_at`/`ours_published` into the project context through a new `project.merge_confirmed` (a shallow `update_context` would have let the alias lookup and the check overwrite each other's `confirmed` keys).
2. **The trigger is broader.** The alias lookup used to fire only when the project's context had the planner's `neocp` flag, so a NEO/comet/PCCP project created by hand (or one whose context lost the flag) never got the notice. Now `main_window._could_be_renamed` also fires when the object name still **is** a temporary NEOCP/PCCP designation, recognised by the new `mpc_astrometry.is_temporary_designation` (one letter, two digits, four alphanumerics: `A11HPKO`, `P11ABCD`, `P10x99x`). The lookup stays cached (the rolling list is one page, 6 h TTL), so the extra calls cost nothing on the network. The limitation of the rolling list stands: an object confirmed long ago is not found automatically; the hand-typed designation and **Re-check** remain the door.

**Revisión (2026-10-13, el aviso no presupone participación y salta con cualquier designación temporal)**: dos arreglos, sin tocar la medida.

1. **La ficha y la visita ya no afirman participación.** `main_window._paint_confirmation` y `widgets/visits_panel._paint_confirmation` añadían siempre «Your observations of it are in that circular», aunque nuestra estación no estuviera entre las publicadas (el bloque del chequeo ya lo hacía bien, sólo con `ours_published`). Ahora el aviso dice el nombre nuevo y el MPEC, y añade **«tus observaciones están entre ellas: tus datos están en ese MPEC» sólo cuando `confirmed.ours_published` es cierto**; si no, enlaza con el objeto en el MPC y no afirma nada. Para que ese dato llegue a la ficha, `_ufe_astrometry_persist` escribe `resolved_desig`/`mpec`/`mpec_url`/`confirmed_at`/`ours_published` del chequeo en el contexto del proyecto mediante un nuevo `project.merge_confirmed` (un `update_context` superficial habría dejado que la búsqueda de alias y el chequeo se pisaran las claves de `confirmed`).
2. **El disparo es más amplio.** La búsqueda de alias sólo saltaba con el flag `neocp` que pone el planificador, así que un proyecto NEO/cometa/PCCP creado a mano (o cuyo contexto perdió el flag) nunca recibía el aviso. Ahora `main_window._could_be_renamed` también salta cuando el nombre del objeto **es** una designación temporal del NEOCP/PCCP, reconocida por el nuevo `mpc_astrometry.is_temporary_designation` (una letra, dos dígitos, cuatro alfanuméricos: `A11HPKO`, `P11ABCD`, `P10x99x`). La búsqueda sigue cacheada (la lista rodante es una página, TTL 6 h), así que las llamadas extra no cuestan red. Se mantiene la limitación de la lista rodante: un objeto confirmado hace tiempo no se encuentra solo; la designación a mano y **Recomprobar** siguen siendo la puerta.

**Review (2026-10-13, the listing is a context-menu door too)**: the published listing had one door, the check block's button. The points/image context menu now carries **"Published observations…"**, which opens the SAME non-modal window (`_show_residuals`); it is disabled when there is no listing. No second window, no second table.

**Revisión (2026-10-13, el listado también es puerta del menú contextual)**: el listado de publicadas tenía una sola puerta, el botón del bloque del chequeo. El menú contextual de la tabla/imagen lleva ahora **«Published observations…»**, que abre la MISMA ventana no modal (`_show_residuals`); se deshabilita cuando no hay listado. Sin segunda ventana ni segunda tabla.
