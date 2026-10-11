# ADR-078: El listón del MPC recomienda, no filtra; exclusión manual de una observación

**Estado / Status**: Accepted · **Fecha / Date**: 2026-10-10

## Español

**Contexto**: sobre un track & stack real de `A11HPKO` (proyecto 120, run 67)
con **dos observaciones**, el reporte y el listado de «Published observations»
mostraban **una sola**. El grupo 0 tenía SNR 6,19 y el grupo 1 SNR 3,94, con el
listón configurado en 5. `mpc_astrometry.submittable` **descartaba** la
observación por debajo del listón (D26 de ADR-062): el reporte salía con una
línea y el chequeo mandaba a Find_Orb solo esa, así que el observador no podía
ver la segunda ni decidir sobre ella. La app decidía por él. Lo pidió explícito:
**no decidir en silencio**, mostrar las dos, marcar la mala y avisar de que no
la recomienda, y que **la decisión sea suya**.

**Decisión**: dos cambios.

1. **El listón recomienda, no filtra.** `submittable()` devuelve **todas** las
   observaciones salvo las que el observador excluya, más una lista de avisos
   para las que están por debajo del listón (o sin SNR). El reporte incluye
   todas y la app dice, con todas las letras, que **no recomienda enviar** las
   dudosas. El ajuste pasa a llamarse «listón recomendado del MPC» y su ayuda
   explica que avisa, no descarta.
2. **Exclusión manual y reversible.** La primera columna de la tabla de
   observaciones es un **checkbox**: desmarcarlo deja esa observación fuera del
   reporte y del chequeo, y volver a marcarlo la recupera. La observación se
   **marca** con el flag `user_excluded` en sus `flags` (nunca se borra), el flag
   viaja al `astrometry_points` del run y vuelve al reabrirlo. Al excluir, el
   reporte se regenera y el chequeo se relanza (con un debounce para que una
   ráfaga de clics termine en **un** chequeo).

**Medido (2026-10-10, datos reales de `A11HPKO`)**: con el run 67, el grupo 1
(SNR 3,94) pasa de desaparecer del reporte a aparecer con el aviso «SNR 3,9 por
debajo del listón recomendado de 5; la app no recomienda enviarla», y el
observador puede desmarcarlo para dejarlo fuera. El grupo 0 (SNR 6,19) entra sin
aviso.

**Consecuencias**: `submittable` cambia su contrato a
`(kept, excluded, warnings)`; `generate` devuelve `kept`/`excluded`/`warnings`;
`astrometry_store.set_point_excluded` (y su hook en el host) escriben el flag;
el ajuste `astrometry_submit_snr` cambia de significado, de filtro a
recomendación. La **medida** y el veredicto del chequeo no se tocan: solo cambia
qué observaciones se envían, y quién lo decide.

**Alternativas**: (a) seguir filtrando y añadir un botón para incluir las
descartadas, descartado: el defecto debe ser mostrar todo y que el observador
quite, no al revés; (b) borrar la observación al excluirla, descartado: el run es
un registro de auditoría y la decisión debe poder revertirse; (c) no re-chequear
al excluir, descartado: el listado mostraría un conjunto que ya no se envía.

## English

**Context**: on a real track & stack of `A11HPKO` (project 120, run 67) with
**two observations**, the report and the "Published observations" listing showed
**only one**. Group 0 had SNR 6.19 and group 1 SNR 3.94, with the floor set to 5.
`mpc_astrometry.submittable` **dropped** the observation below the floor (D26 of
ADR-062): the report came out with one line and the check sent only that one to
Find_Orb, so the observer could not see the second one or decide about it. The
app decided for them. They asked for it explicitly: **do not decide in silence**,
show both, mark the bad one and say it is not recommended, and let **the
observer** decide.

**Decision**: two changes.

1. **The floor recommends, it does not filter.** `submittable()` returns **every**
   observation except the ones the observer excluded, plus a list of advisories
   for the ones below the floor (or without SNR). The report includes them all
   and the app says, in so many words, that it **does not recommend sending** the
   doubtful ones. The setting is now called "MPC recommended floor" and its help
   says it warns, it does not drop.
2. **Manual, reversible exclusion.** The first column of the observations table
   is a **checkbox**: unchecking it leaves that observation out of the report and
   the check, and checking it again brings it back. The observation is **flagged**
   with `user_excluded` in its `flags` (never deleted), the flag travels to the
   run's `astrometry_points` and comes back when it is reopened. On exclusion the
   report is rebuilt and the check is re-run (debounced, so a burst of clicks
   ends in **one** check).

**Measured (2026-10-10, real `A11HPKO` data)**: on run 67, group 1 (SNR 3.94)
goes from vanishing from the report to appearing with the advisory "SNR 3.9 is
below the recommended floor of 5; the app does not recommend sending it", and the
observer can uncheck it to leave it out. Group 0 (SNR 6.19) goes in with no
advisory.

**Consequences**: `submittable` changes its contract to
`(kept, excluded, warnings)`; `generate` returns `kept`/`excluded`/`warnings`;
`astrometry_store.set_point_excluded` (and its host hook) write the flag; the
`astrometry_submit_snr` setting changes meaning, from filter to recommendation.
The **measurement** and the check's verdict are untouched: only which
observations are sent changes, and who decides it.

**Alternatives**: (a) keep filtering and add a button to include the dropped
ones, rejected: the default must be to show everything and let the observer
remove, not the other way round; (b) delete the observation on exclusion,
rejected: the run is an audit record and the decision must be reversible; (c) not
re-running the check on exclusion, rejected: the listing would show a set we no
longer submit.
