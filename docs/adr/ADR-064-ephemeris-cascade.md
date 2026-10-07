# ADR-064: Cascada de efemérides: Horizons, órbita local y NEOfixer

**Estado / Status**: Accepted · **Fecha / Date**: 2026-10-06

**Ver / See**: ADR-021 (efemérides y exportadores), ADR-042 (la serie y el
goto), ADR-062 (track & stack).

## Español

**Contexto.** El apilado de una secuencia necesita saber dónde está el objeto
en cada toma: eso guía el recorte y congela el objeto mientras las estrellas
dejan traza. Hoy esa posición venía de **JPL Horizons**, y solo de ahí. La
noche del 2026-10-05, un apilado de **2026 PY9** abortó con «no ephemeris for
the object»: el log de esa sesión está lleno de `503 Service Temporarily
Unavailable` de JPL. Comprobado después: Horizons **sí** conoce 2026 PY9
(JPL#9, 134 observaciones), la consulta exacta de la app devuelve 1441 filas y
se parsean bien, y la caché local las tiene. El objeto nunca fue el problema:
el problema fue que **una sola caída de un servicio externo tumbaba el run**.

Se encontró además que el respaldo local que ya existía (`sources/sbdb.py` +
`ephem_minor.kepler_ra_dec`, usado por el goto) estaba roto para este uso:

1. `parse_sbdb` **descartaba la época** (`orbit.epoch`), que no es una de las
   filas de elementos. Sin época, `_mean_anomaly` usa «época = instante
   consultado» y **congela la anomalía media**: medido, 82° de error.
2. SBDB se consultaba **sin `full-prec=1`**, así que devolvía tres cifras
   (`a=2.33`), inservibles para propagar.
3. `kepler_ra_dec` **mezclaba marcos**: objeto en eclíptica J2000 y Tierra de
   fecha (`earth_ecliptic_xyz`, Schlyter). Son ~0,4° de precesión; da igual en
   una carta, pero para un recorte de 64 px (96″) es salirse.

**Decisión.**

1. **Una cascada, no un servicio**: la posición sale de la primera fuente que
   responda, en este orden: **JPL Horizons** (con reintentos), **elementos
   SBDB propagados en local** (Kepler de dos cuerpos, J2000), y **NEOfixer**
   para un objeto sin confirmar. El apilado no muere porque un servicio esté
   caído.
2. **Reintentos con backoff solo ante lo transitorio**: 5xx, 429, timeout y
   error de conexión se reintentan (3 intentos, 1 s y 3 s); un 4xx es un error
   nuestro y no se reintenta. Un cuerpo con **cero filas no se cachea**: hoy
   un 200 vacío envenenaba la clave 12 h y respondía «nada» toda la noche.
3. **La designación se normaliza** antes de consultar: Horizons resuelve
   «2026 PY9» y **no** «2026PY9», y ese espacio que falta bastaba para que un
   objeto válido pareciera desconocido. El respaldo de cometas (`DES= …; CAP;`)
   deja de ser el primero para un asteroide, que responde «no matches»: va
   `DES= …;` y luego `CAP;`.
4. **SBDB se arregla**: la época viaja con los elementos y la consulta pide
   `full-prec=1`, con clave de caché versionada (`:fp`) para no reutilizar los
   cuerpos redondeados.
5. **La propagación local es J2000**, el mismo marco que la WCS de la placa:
   `kepler_ra_dec_j2000` (Tierra de fecha precesada a J2000 y oblicuidad fija)
   más la **corrección de tiempo-luz**. El camino de fecha se conserva para
   las cartas, que ya lo usaban.
6. **Procedencia a la vista**: el run dice de dónde salió la efeméride. Si es
   local, avisa de que es dos cuerpos y aproximada.
7. **La precisión del respaldo no contamina la astrometría**: la efeméride
   solo **guía** el recorte y el congelado; la posición que se reporta es el
   **centroide medido** sobre el stack con la WCS de la placa. Por eso, cuando
   la órbita es local, el recorte se **ensancha** (`astrometry_fallback_margin_px`,
   300 px por defecto): el residuo del respaldo (dos cuerpos más una Tierra
   tosca) puede dejar un NEO cercano a un par de minutos de arco, y el objeto
   tiene que caer dentro igualmente.
8. **MPCORB se descarta**: es un catálogo local de órbitas de cientos de MB,
   se actualiza a diario y va **por detrás** en descubrimientos recientes. No
   resuelve el problema real (era la red) y SBDB da la órbita **por objeto**,
   cacheada y más fresca. Si algún día se quiere una efeméride sin red de
   verdad, el punto de entrada es SBDB + VSOP87/DE, no MPCORB; NEODyS/ESA
   (`esa_neo.py`) queda como segunda vía de elementos.
9. **El sellado de tiempo se lee sin el locale**: `strptime("%b")` sigue
   `LC_TIME`, y Qt fija el locale del proceso al del usuario al arrancar. En
   una máquina española «Aug» dejó de casar, **todas** las filas de la
   efeméride se descartaban y un run decía «no ephemeris» con la tabla delante.
   El mes se busca ahora en la tabla inglesa que el propio módulo ya tenía para
   formatear (`ephemeris.parse_horizons_time`), usado por los cuatro sitios que
   parseaban una fecha de Horizons.

**Consecuencias.** `core/sources/horizons.py` gana `_fetch_with_retry`,
`_normalize` y `ephemeris_ex` (con motivo del fallo); `core/db.py` gana
`cache_delete`; `core/sources/sbdb.py` arregla época y precisión;
`core/ephem_minor.py` gana `kepler_ra_dec_j2000` y `earth_ecliptic_xyz_j2000`;
`core/ephemeris.py` gana `motion_from_elements`; `core/track_stack.py` gana
`sequence_motion_solution`; y el ajuste `astrometry_fallback_margin_px`. El
error de un run sin efeméride deja de ser genérico: dice qué falló y qué se
intentó.

## English

**Context.** Stacking a sequence needs to know where the object is in each
frame: that drives the cutout and freezes the object while the stars trail.
That position came from **JPL Horizons**, and only from there. On 2026-10-05 a
**2026 PY9** stack aborted with "no ephemeris for the object": the evening's log
is full of JPL `503 Service Temporarily Unavailable`. Checked afterwards:
Horizons **does** know 2026 PY9 (JPL#9, 134 observations), the app's exact query
returns 1441 rows and parses them, and the local cache holds them. The object
was never the problem: the problem was that **one outage of one external
service killed the run**.

It also turned out that the local fallback that already existed
(`sources/sbdb.py` + `ephem_minor.kepler_ra_dec`, used by goto) was broken for
this use:

1. `parse_sbdb` **dropped the epoch** (`orbit.epoch`), which is not one of the
   element rows. Without it, `_mean_anomaly` uses "epoch = the instant asked
   for" and **freezes the mean anomaly**: measured, 82 deg of error.
2. SBDB was queried **without `full-prec=1`**, so it answered three figures
   (`a=2.33`), useless to propagate.
3. `kepler_ra_dec` **mixed frames**: object in J2000 ecliptic, Earth of date
   (`earth_ecliptic_xyz`, Schlyter). That is ~0.4 deg of precession; fine on a
   chart, but for a 64 px (96") cutout it is falling outside.

**Decision.**

1. **A cascade, not one service**: the position comes from the first source
   that answers, in this order: **JPL Horizons** (with retries), **SBDB
   elements propagated locally** (two-body Kepler, J2000), and **NEOfixer** for
   an unconfirmed object. The stack does not die because a service is down.
2. **Retries with backoff only for the transient**: 5xx, 429, timeout and
   connection errors are retried (3 attempts, 1 s and 3 s); a 4xx is our
   mistake and is not retried. A body with **zero rows is not cached**: a 200
   with no table used to poison the key for 12 h and answer "nothing" all
   evening.
3. **The designation is normalised** before querying: Horizons resolves
   "2026 PY9" and **not** "2026PY9", and that missing space alone made a valid
   object look unknown. The comet fallback (`DES= …; CAP;`) stops being the
   first one for an asteroid, which answers "no matches": `DES= …;` goes
   first, then `CAP;`.
4. **SBDB is fixed**: the epoch travels with the elements and the query asks
   for `full-prec=1`, with a versioned cache key (`:fp`) so the rounded bodies
   are never reused.
5. **The local propagation is J2000**, the same frame as the plate's WCS:
   `kepler_ra_dec_j2000` (of-date Earth precessed to J2000 and a fixed
   obliquity) plus the **light-time** correction. The of-date path stays for
   the charts that already used it.
6. **Provenance on screen**: the run says where the ephemeris came from. If it
   is local, it warns that it is two-body and approximate.
7. **The fallback's accuracy does not contaminate the astrometry**: the
   ephemeris only **guides** the cutout and the freeze; the position that is
   reported is the **centroid measured** on the stack with the plate's WCS. So
   when the orbit is local the cutout is **widened**
   (`astrometry_fallback_margin_px`, 300 px by default): the fallback's
   residual (two-body plus a coarse Earth) can leave a close NEO a couple of
   arcminutes off, and the object still has to fall inside.
8. **MPCORB is rejected**: a local orbit catalogue of hundreds of MB, updated
   daily and **lagging** on recent discoveries. It does not solve the real
   problem (it was the network) and SBDB gives the orbit **per object**, cached
   and fresher. If a truly offline ephemeris is ever wanted, the entry point is
   SBDB + VSOP87/DE, not MPCORB; NEODyS/ESA (`esa_neo.py`) stays as a second
   elements route.
9. **The timestamp is parsed without the locale**: `strptime("%b")` follows
   `LC_TIME`, and Qt sets the process locale to the user's at startup. On a
   Spanish machine "Aug" stopped matching, **every** ephemeris row was dropped
   and a run said "no ephemeris" with the table right there. The month is now
   looked up in the English table the module already owned for formatting
   (`ephemeris.parse_horizons_time`), used by the four places that parsed a
   Horizons date.

**Consequences.** `core/sources/horizons.py` gains `_fetch_with_retry`,
`_normalize` and `ephemeris_ex` (with a failure reason); `core/db.py` gains
`cache_delete`; `core/sources/sbdb.py` fixes epoch and precision;
`core/ephem_minor.py` gains `kepler_ra_dec_j2000` and `earth_ecliptic_xyz_j2000`;
`core/ephemeris.py` gains `motion_from_elements`; `core/track_stack.py` gains
`sequence_motion_solution`; and the setting `astrometry_fallback_margin_px`.
A run with no ephemeris no longer fails generically: it says what failed and
what was tried.

**Revisión (2026-10-06): la cascada también responde al brillo.** Se pidió que la
banda de la placa diga la magnitud del objeto aunque el run no la haya medido,
indicando que es de la efeméride. La pregunta «¿qué dice el cielo de este objeto
esta noche?» tiene dos mitades (dónde está y cuánto brilla) y las responde la MISMA
cascada:

- **Horizons**: una llamada propia con `QUANTITIES='9'` (`horizons.magnitude_rows`),
  separada de la tabla de RA/Dec a propósito: el parser de posición es delicado y
  añadirle una columna renumeraría todos sus campos. La magnitud es el penúltimo
  token de cada fila (después van la superficie o la nuclear) y el **nombre de la
  columna se lee de la respuesta** (`APmag` → V para un asteroide, `T-mag` → T para
  un cometa): inventarlo desde el tipo del objeto sería adivinar. «n.a.» no es un
  cero: la fila vuelve sin cifra. Clave de caché propia (`horizons:mag:...`): una
  entrada escrita antes de esta llamada no tiene columna de magnitud y parsearla
  diría «la efeméride no da magnitud» durante todo el TTL.
- **Orbe local**: `ephem_minor.hg_magnitude_j2000` con el sistema IAU H-G (Bowell
  1989) desde la H y la G que ya vienen con los elementos de SBDB, y la misma
  geometría (r, Δ y ángulo de fase) que el propagador ya calcula. Contrastado con
  Horizons en 2026 PY9: 22.207 frente a 22.208 (0.001 mag).
- **NEOfixer**: sin H publicada, no hay magnitud. Y no pasa nada: la magnitud es
  una comodidad, nunca una condición. Si nadie la da, el run sigue con `mag=None`
  y la banda cae al catálogo, etiquetado.

`core/track_stack.py` gana `sequence_ephemeris` (el diccionario con posición,
magnitud y origen); `sequence_motion_solution` queda como envoltorio para los
llamadores que solo quieren la posición.

**Revision (2026-10-06): the cascade answers about the light too.** Asked for: the
plate's band must show the object's magnitude even when the run did not measure it,
saying that the ephemeris gives it. The question "what does the sky say about this
object tonight?" has two halves (where it is and how bright it is) and the SAME
cascade answers both:

- **Horizons**: a call of its own with `QUANTITIES='9'` (`horizons.magnitude_rows`),
  deliberately apart from the RA/Dec table: the position parser is delicate and
  adding a column to it would renumber every field. The magnitude is the second-to-
  last token of each row (the surface or the nuclear magnitude follow) and the
  **column's name is read from the reply** (`APmag` → V for an asteroid, `T-mag` →
  T for a comet): inventing it from the object's type would be guessing. "n.a." is
  not a zero: the row comes back with no figure. A cache key of its own
  (`horizons:mag:...`): an entry written before this call has no magnitude column
  and parsing it would say "the ephemeris gives no magnitude" for a whole TTL.
- **Local orbit**: `ephem_minor.hg_magnitude_j2000` with the IAU H-G system (Bowell
  1989) from the H and G that come with SBDB's elements, and the same geometry (r,
  Δ and phase angle) the propagator already computes. Cross-checked against
  Horizons on 2026 PY9: 22.207 against 22.208 (0.001 mag).
- **NEOfixer**: with no published H there is no magnitude. That is fine: the
  magnitude is a nicety, never a condition. If nobody gives it, the run goes on
  with `mag=None` and the band falls back to the catalogue, labelled.

`core/track_stack.py` gains `sequence_ephemeris` (the dict with position, magnitude
and source); `sequence_motion_solution` stays as a wrapper for the callers that only
want the position.
