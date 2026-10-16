# ADR-080: El reporte MPC completo (cabecera de envío) y su envío al MPC

**Estado / Status**: Accepted · **Fecha / Date**: 2026-10-11

## Español

**Contexto**: el reporte que NightScribe generaba eran **solo las líneas de
datos**, sin la cabecera de observación. Comparado con un reporte real
(`A11HPKO/Report.txt`) faltaba todo lo que el MPC exige: `COD`, `CON`, `OBS`,
`MEA`, `TEL`, `NET`, `NUM`, `ACK`, `AC2` y el terminador `----- end -----`.
El MPC lo dice sin rodeos: «Observation batches that do not include an
observational header will not be recognized» (ObsDetails.html). Además:

- La **designación estaba mal colocada y truncada**: se escribían 5 caracteres
  del empaquetado en las columnas 1-5 (el campo del NÚMERO) en vez de las
  6-12 (provisional/temporal). `A11HPKO` salía como `A11HP`; `2021 EQ3`, como
  `K21E0`.
- ADES PSV iba sin el `obsContext` (`# version`, `# observatory`, `# submitter`,
  `# telescope`, `# observers`, `# measurers`, `# comment`) y usaba la columna
  no estándar `objid` en vez de `permID`/`provID`/`trkSub`.
- El **envío era mudo**: «Send to the MPC block» volcaba el texto en la caja de
  pegado de la visita, sin pedir nada.
- No había **email de contacto**, que el MPC necesita para el `AC2`.

**Decisión**: cinco cambios.

1. **El reporte es una sumisión completa.** `core/mpc_astrometry.py` emite la
   cabecera (MPC 1992: `COD/CON/OBS/MEA/TEL/NET/COM/ACK/AC2/NUM` + `----- end
   -----`; ADES: el `obsContext`), construida desde un `ReportContext` leído de
   los ajustes. El `TEL` se **construye** con la apertura, el tipo de telescopio
   y la relación focal (derivable de la focal y la apertura) más el tipo de
   cámara como detector; el texto libre, si está, se usa tal cual.
2. **La designación va en su columna.** Número empaquetado en 1-5, provisional
   o temporal (NEOCP/PCCP) en 6-12, sin truncar; en ADES, `permID`/`provID`/
   `trkSub`. El validador (`core/mpc_report.py`) aprende a **saltar** las líneas
   de cabecera (`COD…AC2`, `----- end -----`, `#`/`!`) y a contar solo medidas.
3. **Tres formatos**: MPC 1992, ADES PSV y ADES XML, en el orden de preferencia
   del MPC. Los tres llevan la cabecera.
4. **El reporte vive en su propia ventana** no modal (`UfeReportDialog`),
   abierta por el botón «Report…» de la pestaña Astrometría, con el selector de
   formato y las acciones **Copiar**, **Guardar en fichero…** y **Enviar al
   MPC…**. El grupo inline desaparece.
5. **El envío nunca es mudo** (`MpcSendDialog`): pide el **email de acuse**, el
   **texto de acuse**, el **objetivo** (NEOCP/PCCP/NEW NEO/…) y el **modo**
   (Normal/Test), y hace POST al endpoint propio del MPC desde un nuevo
   `core/sources/mpc_submit.py`, mostrando la respuesta del servidor (el CurlID
   o los errores). **Sin email de contacto el envío se bloquea** y el diálogo lo
   dice.

   | Formato | Endpoint real | Endpoint de prueba | Campos |
   |---|---|---|---|
   | MPC 1992 | `/submit_obs` | `/submit_obs_test` | `source` (el AC2 va en la cabecera) |
   | ADES PSV | `/submit_psv` | `/submit_psv_test` | `source`, `ack`, `ac2`, `obj_type` |
   | ADES XML | `/submit_xml` | `/submit_xml_test` | `source`, `ack`, `ac2`, `obj_type` |

**Consecuencias**: la config gana `observer_email`, `telescope_type`,
`telescope_focal_ratio` y `mpc_report_comment`; `ReportContext` y las nuevas
funciones viven en `core/mpc_astrometry.py`; `mpc_report.validate` salta
cabeceras; aparece `core/sources/mpc_submit.py` (el único sitio donde se hace un
POST; los `requests` siguen viviendo solo en `core/sources/`, AGENTS). Se
**reabre ADR-022**: el usuario sigue siendo quien decide, pero la app ya no se
limita a preparar el texto, lo **envía** por él, con Test como ensayo.

**Alternativas**: (a) quedarse en las líneas de datos y que el usuario pegue la
cabecera a mano, descartado: el MPC ignora el lote y la cabecera es
obligatoria; (b) dejar el reporte inline, descartado: la columna de 380 px no
da para un reporte con cabecera y varias filas; (c) enviar en silencio al pulsar
un botón, descartado: el MPC archiva las medidas para siempre y el observador
debe ver y elegir el objetivo, el acuse y el modo antes de enviar; (d) construir
el `TEL` solo del texto libre, descartado: el observador pidió construirlo de
los campos que ya tiene.

**Revisión 2026-10-13**: el diálogo de envío se abría con la caja vacía y sin
explicación, y eso se lee como roto. Ahora lleva encima del registro una línea de
resumen (cuántas observaciones, el formato, el destino y el modo) y un texto de
marcador en la caja que dice qué aparecerá ahí al pulsar Send. Y el destino por
defecto que promete el manual (NEOCP si el proyecto está en el NEOCP,
Unclassified si no) por fin se aplica: la condición antigua pedía además un combo
vacío, y `set_targets` ya lo había rellenado, así que nunca entraba.

## English

**Context**: the report NightScribe generated was **the data lines only**, with
no observation header. Compared with a real report (`A11HPKO/Report.txt`)
everything the MPC demands was missing: `COD`, `CON`, `OBS`, `MEA`, `TEL`,
`NET`, `NUM`, `ACK`, `AC2` and the `----- end -----` terminator. The MPC says
it plainly: "Observation batches that do not include an observational header
will not be recognized" (ObsDetails.html). Besides:

- The **designation was misplaced and truncated**: 5 packed characters were
  written in columns 1-5 (the NUMBER field) instead of 6-12
  (provisional/temporary). `A11HPKO` came out as `A11HP`; `2021 EQ3`, as
  `K21E0`.
- ADES PSV went without the `obsContext` (`# version`, `# observatory`,
  `# submitter`, `# telescope`, `# observers`, `# measurers`, `# comment`) and
  used the non-standard `objid` column instead of `permID`/`provID`/`trkSub`.
- Sending was **silent**: "Send to the MPC block" dumped the text into the
  visit's paste box, asking nothing.
- There was no **contact email**, which the MPC needs for the `AC2`.

**Decision**: five changes.

1. **The report is a full submission.** `core/mpc_astrometry.py` emits the
   header (MPC 1992: `COD/CON/OBS/MEA/TEL/NET/COM/ACK/AC2/NUM` + `----- end
   -----`; ADES: the `obsContext`), built from a `ReportContext` read from the
   settings. The `TEL` is **built** from the aperture, the telescope type and
   the focal ratio (derivable from the focal length and the aperture) plus the
   camera type as the detector; the free text, when present, is used verbatim.
2. **The designation goes in its column.** Packed number in 1-5, provisional or
   temporary (NEOCP/PCCP) in 6-12, never truncated; in ADES,
   `permID`/`provID`/`trkSub`. The validator (`core/mpc_report.py`) learns to
   **skip** the header lines (`COD…AC2`, `----- end -----`, `#`/`!`) and to
   count only measurements.
3. **Three formats**: MPC 1992, ADES PSV and ADES XML, in the MPC's preference
   order. All three carry the header.
4. **The report lives in its own** non-modal window (`UfeReportDialog`), opened
   by the Astrometry tab's "Report…" button, with the format selector and the
   **Copy**, **Save to file…** and **Send to MPC…** actions. The inline group
   goes away.
5. **Sending is never silent** (`MpcSendDialog`): it asks for the **ACK email**,
   the **ACK text**, the **target** (NEOCP/PCCP/NEW NEO/…) and the **mode**
   (Normal/Test), and POSTs to the MPC's own endpoint from a new
   `core/sources/mpc_submit.py`, showing the server's answer (the CurlID or the
   errors). **Without a contact email the send is blocked** and the dialog says
   so.

   | Format | Real endpoint | Test endpoint | Fields |
   |---|---|---|---|
   | MPC 1992 | `/submit_obs` | `/submit_obs_test` | `source` (AC2 is in the header) |
   | ADES PSV | `/submit_psv` | `/submit_psv_test` | `source`, `ack`, `ac2`, `obj_type` |
   | ADES XML | `/submit_xml` | `/submit_xml_test` | `source`, `ack`, `ac2`, `obj_type` |

**Consequences**: the config gains `observer_email`, `telescope_type`,
`telescope_focal_ratio` and `mpc_report_comment`; `ReportContext` and the new
functions live in `core/mpc_astrometry.py`; `mpc_report.validate` skips headers;
`core/sources/mpc_submit.py` appears (the only place a POST is made; `requests`
still live only in `core/sources/`, AGENTS). **ADR-022 is reopened**: the user
is still the one who decides, but the app no longer just prepares the text, it
**sends** it for them, with Test as a rehearsal.

**Alternatives**: (a) keeping the data lines and letting the user paste the
header by hand, rejected: the MPC ignores the batch and the header is
mandatory; (b) leaving the report inline, rejected: the 380 px column cannot
hold a report with a header and several rows; (c) sending silently on a button
click, rejected: the MPC archives measurements forever and the observer must see
and choose the target, the ACK and the mode before sending; (d) building the
`TEL` from the free text alone, rejected: the observer asked for it to be built
from the fields they already have.

**Revision 2026-10-13**: the send dialog opened with an empty box and no
explanation, which reads as broken. It now carries a summary line above the log
(how many observations, the format, the target and the mode) and a placeholder in
the box saying what will appear there on Send. And the default target the manual
promises (NEOCP when the project is on the NEOCP, Unclassified otherwise) now
really applies: the old condition also asked for an empty combo, and
`set_targets` had already filled it, so it never entered.

**Revision 2026-10-14 (the report is editable)**: the report box was read-only and `_on_mpc_submit` rebuilt the report with the ACK/target right before sending, so an edit would have been lost anyway. The observer asked to be able to fix the built report before it goes to the MPC (a designation, a line). The box is now editable, with a **Regenerate** button that rebuilds it from the measurements and clears the edit. A `textChanged` marks the report "edited"; when it is edited, `_on_mpc_submit` sends **exactly that text** and does NOT rebuild it, and the send dialog disables the acknowledgement-text and target fields with a notice, because those only reach the report when it is regenerated. An unedited report keeps the old flow (rebuilt with the ACK/target).

**Revision 2026-10-16 (the flow is written once and the visit reuses it)**: the report's behaviour (open, fill, copy, save, register and send) lived inside the Astrometry tab, and the visit had its own paste box with its own validator: two paths that could drift apart. It now lives in `gui/mpc_report_controller.py` (`MpcReportController`), which owns the two windows and everything after the text; each owner (the tab, the visit) only supplies the builder of the text, because the points and the designation are theirs. The visit stops pasting anything: its MPC block is a **button** that opens the SAME report window plus one **status line**, and the report is rebuilt from the visit's own astrometry run (`_visit_mpc_report`). On save, the file is registered to the visit (its measurements are its product) and a warning shows if the report's first measurement disagrees with the visit's date, as before. The dead `set_mpc_send_hook`/`send_to_mpc_block` hook is removed: it dumped text into a box that no longer exists.

**Revisión 2026-10-14 (el reporte es editable)**: la caja del reporte era de sólo lectura y `_on_mpc_submit` regeneraba el reporte con el ACK/target justo antes de enviar, así que una edición se habría perdido igual. El observador pidió poder corregir el reporte construido antes de que salga al MPC (una designación, una línea). La caja es ahora editable, con un botón **Regenerar** que la reconstruye desde las medidas y limpia la edición. Un `textChanged` marca el reporte como «editado»; cuando lo está, `_on_mpc_submit` envía **exactamente ese texto** y NO lo regenera, y el diálogo de envío desactiva los campos de texto de acuse y objetivo con un aviso, porque sólo llegan al reporte al regenerarlo. Un reporte sin editar mantiene el flujo anterior (se regenera con el ACK/target).

**Revisión 2026-10-16 (el flujo se escribe una vez y la visita lo reutiliza)**: el comportamiento del reporte (abrir, rellenar, copiar, guardar, registrar y enviar) vivía dentro de la pestaña Astrometría, y la visita tenía su propia caja de pegado con su propio validador: dos caminos que podían divergir. Ahora vive en `gui/mpc_report_controller.py` (`MpcReportController`), que posee las dos ventanas y todo lo que ocurre después del texto; cada dueño (la pestaña, la visita) aporta solo el constructor del texto, porque los puntos y la designación son suyos. La visita deja de pegar nada: su bloque MPC es un **botón** que abre la MISMA ventana de reporte y una **línea de estado**, y el reporte se reconstruye desde el propio run de astrometría de la visita (`_visit_mpc_report`). Al guardar, el fichero se registra en la visita (sus medidas son su producto) y se avisa si la primera medida del reporte no cuadra con la fecha de la visita, como antes. Se retira el gancho muerto `set_mpc_send_hook`/`send_to_mpc_block`, que volcaba texto en una caja que ya no existe.
