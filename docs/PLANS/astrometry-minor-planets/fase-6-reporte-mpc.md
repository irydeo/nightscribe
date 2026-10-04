# Fase 6: generadores de reporte MPC (ADES PSV y 80 columnas)

> Fase del plan maestro [`PLAN.md`](PLAN.md). Decisiones: D13, D15, D26 y la
> reapertura de ADR-022.

## Por qué

Hasta hoy NightScribe solo **validaba** lo que el usuario pegaba (ADR-022).
Ahora genera la medida, así que tiene que emitir el formato oficial. Se emiten
los dos: el **80 columnas** clásico, que es lo que produce Tycho-Tracker y lo
que muchos flujos siguen usando, y **ADES PSV**, el estándar moderno, que
además admite incertidumbres (rmsRA, rmsDec) y el catálogo astrométrico. El
validador que ya existe se reutiliza como puerta de ida y vuelta: lo que
generamos tiene que pasar por el mismo juez que lo que el usuario pega a mano.
Y aquí entra el listón de envío: el MPC recomienda SNR ≥ 20 y prohíbe enviar
detecciones marginales, así que la generación está condicionada por el SNR de
cada observación.

## Implementación

### 6.1 `core/mpc_astrometry.py`

- `format_time_mpc80(jd_utc) -> str`: `YYYY MM DD.dddddd` en UTC. El instante es
  **T_mid** del grupo (D13), no el inicio.
- `format_ra_mpc80(ra_deg) -> str`: `HH MM SS.sss`.
- `format_dec_mpc80(dec_deg) -> str`: `sDD MM SS.ss`.
- `band_code(filter_name) -> str`: traduce el filtro a la banda del MPC (V, R,
  B, g, r, i, C para claro, etc.). Tabla explícita y documentada; una banda
  desconocida cae a `C` con aviso, nunca a un valor inventado.
- `pack_designation(name, kind) -> (packed, note)`: empaqueta la designación.
  Se **extiende** `mpc_report._pack_desig` en vez de escribir otra: cubre
  numerado, provisional y cometa. Para **PCCP** (designación provisional sin
  órbita) el empaquetado es best-effort: se emite tal cual y se devuelve una
  `note` para que el usuario confirme (D15). Si no se puede empaquetar con
  garantías, se avisa y no se inventa.
- `to_mpc80(points, obs_code, designation, cfg) -> str`: una línea por
  **observación** (grupo), con los campos en las posiciones que documenta
  `core/mpc_report.py` (`_DESIG`, `_DATE`, `_RA`, `_DEC`, `_MAG`, `_BAND`,
  `_STATION`). Si no hay magnitud, el campo va en blanco.
- `to_ades_psv(points, obs_code, designation, cfg) -> str`: cabecera de campos
  y una fila por observación. Campos: `objid`, `mode` (`CCD`), `stn`,
  `obsTime` (ISO UTC con decimales, T_mid), `ra`, `dec`, `rmsRA`, `rmsDec`,
  `mag`, `band`, `astCat` (del config), `ref`, `subFmt` (`PSV`). Los campos de
  incertidumbre salen de la fase 4; la magnitud solo si existe (si no, la
  columna va vacía).
- `generate(points, fmt, ...) -> GeneratedReport`: devuelve el texto, el
  formato, las observaciones incluidas y el resultado de validación (abajo).

### 6.2 Listón de envío (D26)

- `submittable(points, cfg) -> (kept, dropped, notes)`: filtra las
  observaciones con `snr < astrometry_submit_snr` (20 por defecto). Las que no
  llegan **no entran** en el reporte y se explica por qué en lenguaje llano
  (el MPC recomienda SNR ≥ 20 y prohíbe enviar detecciones marginales o
  ruidosas). Nunca se genera una línea con SNR bajo en silencio.
- Para **NEOCP/PCCP** no se genera por defecto aunque pasen el SNR: se pide
  confirmación explícita, porque un tracklet falso en el NEOCP puede perder el
  objeto.
- El chequeo de la fase 5 también condiciona: si `blocked=True`, no se genera
  salvo que el usuario fuerce, y la nota del forzado queda escrita.

### 6.3 Puerta de ida y vuelta

- `validate_generated(text, obs_code, expected_obj) -> dict`: llama a
  `core.mpc_report.validate` sobre lo generado. Si nuestro propio generador
  produce algo que el validador rechaza, es un fallo del generador, no del
  usuario. Esto se prueba en unitarios y es la garantía de que el formato es
  correcto.

### 6.4 Elección de la vía

El run tiene `report_source` (por defecto `stack`). El generador recibe los
puntos de esa vía; si el usuario eligió `frames`, se emiten esos. Las dos filas
existen en `astrometry_points` (fase 8), así que el reporte se puede regenerar
con la otra vía sin volver a medir.

## Tests

`tests/unit/test_mpc_astrometry.py`:

- **A7, ida y vuelta**: una observación sintética (con y sin magnitud, con y
  sin incertidumbre) genera un 80 col y un ADES PSV que
  `mpc_report.validate` acepta.
- **A7, varias observaciones**: tres grupos generan tres líneas (80 col) o
  tres filas (ADES), cada una con su hora y su posición.
- **A15, umbral**: un grupo con SNR por debajo de 20 no entra y se explica;
  con el umbral bajado a mano, entra.
- **Formato**: las posiciones de campo del 80 col coinciden con las constantes
  de `mpc_report.py`; la fecha es T_mid; RA y Dec van en el sexagesimal
  correcto, incluido Dec negativo.
- **Designación**: numerado, provisional y cometa se empaquetan y el validador
  los reconoce; PCCP devuelve su `note` y no rompe.
- **Banda**: cada filtro conocido mapea a su código; uno desconocido cae a `C`
  con aviso.
- **Sin magnitud**: el 80 col deja el campo en blanco y el validador no se
  queja por ello.
- **Regeneración**: los puntos de la vía `frames` producen un reporte válido
  distinto del de `stack`.

## Salida limpia

El módulo genera los dos formatos desde las observaciones medidas, aplica el
listón de envío, y lo generado pasa por el validador de ADR-022. La GUI todavía
no lo expone.

## Hecho cuando

A7 y A15 pasan en los dos formatos, y ningún caso (sin magnitud, sin
incertidumbre, PCCP, Dec negativa, grupo con SNR bajo) produce un reporte
inválido o una línea silenciada.
