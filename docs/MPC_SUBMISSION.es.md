# Envío al MPC: cómo NightScribe manda un reporte de astrometría

*Referencia para quien mantiene el reporte y el envío: qué lleva cada formato,
qué dan los ajustes, qué pide el diálogo y qué hace la app con ello. La guía de
usuario es `docs/user/07-astrometry.es.md`; la decisión que hay detrás es
ADR-080.*

---

## 1. De dónde sale

En la pestaña Astrometría, **Gestionar reporte MPC** abre la ventana del reporte
(`UfeReportDialog`, no modal). La pestaña se queda solo con el botón y la nota;
la ventana tiene el selector de formato, el reporte y las acciones. **Enviar al
MPC…** abre el diálogo de envío (`MpcSendDialog`), que pide las cuatro opciones
y hace el POST del lote.

El reporte se reconstruye cada vez desde los puntos medidos del run más la
cabecera construida de los ajustes, así que el texto no puede discrepar de lo
que se midió.

## 2. Los tres formatos

| Formato | Qué emite |
|---|---|
| **ADES XML** (preferido del MPC) | `<ades version="2017"><obsBlock><obsContext>…</obsContext><obsData><optical>…` |
| **ADES PSV** | el `obsContext` (bloques `#`/`!`) + fila de cabecera + una fila con barras por observación |
| **MPC 1992** (80 columnas) | las líneas de cabecera + una línea de 80 caracteres por observación + `----- end -----` |

Los tres los construye `core/mpc_astrometry.generate(points, fmt, obs_code,
designation, cfg, context, submission, kind)` y pasan por
`core.mpc_report.validate` (el mismo juez que un reporte pegado) antes de salir;
el XML lo juzga el esquema propio del MPC al enviarse.

## 3. La cabecera MPC 1992

La emite `mpc_astrometry.mpc80_header(ctx, submission, n_obs)`, en el orden que
lee el MPC:

```
COD <obs_code>
CON <observer>            (otra línea CON [<email>] si hay email)
OBS <observer>
MEA <measurer>            (si está vacío, cae al observer)
TEL <telescope>           (construido, o el texto libre del observador)
NET <nombre del catálogo> (Gaia3E -> "Gaia EDR 3", ...)
COM <comment>             (opcional)
ACK <obj_type> <ack>      (la palabra clave se antepone si falta)
AC2 <email>
NUM <n observaciones>
<líneas de datos>
----- end -----
```

Sin la cabecera el MPC ignora el lote («Observation batches that do not include
an observational header will not be recognized», ObsDetails.html).

La **designación** va en su columna: el número empaquetado en 1-5, el
provisional empaquetado o la temporal (NEOCP/PCCP) en 6-12, el detector en la
columna 15. La **precisión** es la normal del MPC (5 decimales de día, 2 de
segundo de RA, 1 de arco de Dec, 1 décima de magnitud), que es lo que deja el
espacio separador entre campos; la opción de precisión extra no se usa porque el
MPC no deja a la mayoría de observatorios emplearla.

## 4. El contexto ADES

Lo emite `mpc_astrometry.ades_psv_context(ctx)` para PSV y su `obsContext`
equivalente para XML:

```
# version=2017
# observatory      ! mpcCode <code>   ! name <nombre del observatorio>
# submitter        ! name <observer>
# telescope        ! aperture <m>   ! fRatio <f/>   ! design <tipo>   ! detector <CCD|CMO>
# observers        ! name <observer>
# measurers        ! name <measurer>
# comment          ! line <comment>   (opcional)
```

ADES mantiene los datos personales FUERA del documento: el email **no** está
aquí, viaja en el formulario de envío (`ac2`). La columna de identificador es
`permID`/`provID`/`trkSub` (nunca el antiguo `objid`): un número va en `permID`,
un provisional en `provID`, una etiqueta temporal en `trkSub`.

## 5. Los ajustes que lee

`mpc_astrometry.report_context(cfg)` construye un `ReportContext` desde los
Ajustes (página Observatorio):

| Ajuste | Campo de la cabecera |
|---|---|
| `mpc_code` | COD, y la columna `stn` |
| `observer_name` | CON, OBS, el submitter/observers ADES |
| `measurer_name` | MEA, los measurers ADES (vacío -> el observer) |
| `observer_email` | AC2 (y CON `[email]`) |
| `telescope_desc` | TEL tal cual cuando está puesto |
| `telescope_type` + `telescope_focal_ratio` + `aperture_inches` | la línea TEL construida |
| `camera_type` | el detector (`CCD`/`CMO`) |
| `astrometry_astcat` | NET, y el `astCat` ADES |
| `mpc_report_comment` | COM |

La línea del telescopio se construye como `"<apertura>-m f/<relación> <tipo>"` y,
para el TEL de MPC 1992, `" + <detector>"`; la relación focal se deriva de la
focal y la apertura cuando el observador no la fija. El mismo constructor
(`ReportContext.tel_body()`) alimenta la banda de la imagen, así que la banda y
el reporte no pueden discrepar.

## 6. El diálogo de envío

`MpcSendDialog` (estructura en `gui/ui/ufe_mpc_send_dialog.ui`) pide:

- **Email de acuse** (AC2): pre-rellenado con `observer_email`; **obligatorio**.
- **Acuse**: un texto corto de acuse; opcional.
- **Objetivo** (`obj_type`): cómo encamina el MPC el lote.
- **Modo**: Normal o Prueba.
- Un **registro** con la respuesta del propio servidor, y **Enviar** / **Cerrar**.

### Objetivo

La palabra clave que el MPC necesita para encaminar el lote (ObsDetails.html).
Viaja en la línea ACK del reporte en MPC 1992 y en el campo `obj_type` en ADES.

| Valor | Significado |
|---|---|
| Unclassified | el objeto ya está clasificado; envío normal, sin palabra clave |
| NEOCP | el objeto está en la página de confirmación de NEOs |
| PCCP | está en la página de confirmación de posibles cometas |
| NEW NEO | candidato a objeto cercano a la Tierra nuevo |
| NEW COMET | candidato a cometa nuevo |
| NEW NATURAL SATELLITE | candidato a satélite natural nuevo |
| NEW TNO / NEW KBO / NEW DISTANT / NEW CENTAUR | candidato a TNO, KBO, objeto distante o centauro nuevo |

Una palabra clave ausente o equivocada puede encaminar mal el lote o impedir que
se procese como esperas. Por defecto es NEOCP cuando el proyecto está en el
NEOCP y Unclassified en los demás casos. La lista vive una sola vez, en
`mpc_submit.TARGETS`.

### Modo

- **Normal**: el endpoint real; el MPC procesa y publica el lote.
- **Prueba**: el endpoint `*_test`, que hace las mismas comprobaciones de formato
  y validez pero **no procesa** el lote (un ensayo).

## 7. Qué pasa internamente al enviar

1. **Compuerta** (`UfeTrackStackTab._refresh_send_gate`): `ReportContext.missing()`
   lista lo que no puede faltar (código de observatorio, observador, telescopio,
   email de contacto); mientras falte algo el diálogo lo dice y **Enviar queda
   deshabilitado**. El email se lee del propio campo del diálogo, no solo de los
   ajustes.
2. **Reconstrucción**: la pestaña fija `self._submission = {"ack", "obj_type"}` y
   llama a `_on_report(quiet=True)`, para que el reporte lleve la línea ACK
   elegida.
3. **Worker**: `workers.MpcSubmitWorker(QThread)` hace el POST fuera del hilo de
   la GUI.
4. **POST** (`core/sources/mpc_submit.submit`):

| Formato | Endpoint real | Endpoint de prueba | Campos del formulario |
|---|---|---|---|
| MPC 1992 | `/submit_obs` | `/submit_obs_test` | solo `source` (el AC2 va en la cabecera) |
| ADES PSV | `/submit_psv` | `/submit_psv_test` | `source`, `ack`, `ac2`, `obj_type` |
| ADES XML | `/submit_xml` | `/submit_xml_test` | `source`, `ack`, `ac2`, `obj_type` |

URL base `https://minorplanetcenter.net`; `source` es un campo de fichero
multipart que lleva el texto del reporte. El endpoint de MPC 1992 toma el lote a
secas.

5. **Respuesta**: `ok = HTTP 200 y sin «error» en los primeros 400 caracteres del
   cuerpo`; el cuerpo (el CurlID o la lista de errores) y la URL se devuelven y
   se escriben en el registro del diálogo.

## 8. Errores y notas de diseño

- La red nunca es un crash: un fallo de petición devuelve
  `"Could not reach the MPC: …"` y se muestra en el registro.
- El email es **información personal**, así que nunca entra en un documento ADES
  (solo en el formulario de envío). La propia página ADES del MPC lo dice.
- Un envío es un **POST** y no se puede cachear, así que **no** pasa por
  `core/db.py`; vive en `core/sources/mpc_submit.py`, el único sitio donde se
  permite importar `requests` (AGENTS). Todo lo demás (la generación del
  reporte) es puro.
- El envío nunca es mudo (ADR-080): el observador ve y elige el email, el acuse,
  el objetivo y el modo antes de que salga nada.

## 9. Referencias

- MPC, *Specifying Observational Details*: `iau/info/ObsDetails.html` (las
  palabras clave de la cabecera y los objetivos).
- MPC, *Format For Optical Astrometric Observations*: `iau/info/OpticalObs.html`
  (las posiciones de campo del formato de 80 columnas).
- MPC, *Information on How to Submit Observations From the Command Line*:
  `iau/info/commandlinesubmissions.html` (los endpoints y los campos).
- MPC, *ADES Data Submission*: `mpcops/documentation/ades/` (el contexto PSV/XML
  y la regla de PII).
