# Fase 7: interfaz (pestañas, workers, Ajustes e i18n)

> Fase del plan maestro [`PLAN.md`](PLAN.md). Decisiones: D4, D15, D22, D24,
> D25, D26, D27, D28 y las reglas de interfaz de la casa (ADR-005, ADR-014,
> ADR-058).

## Por qué

Los motores de las fases 1 a 6 no son un producto hasta que el observador los
puede usar desde su visita, con progreso, cancelación, avisos en lenguaje llano
y cada cifra explicada. Esta fase conecta todo al Editor FITS unificado y a la
ventana de la visita, y deja la biblioteca de masters administrable desde
Ajustes.

## Implementación

### 7.1 Pestaña Calibración

- `gui/ufe_calibration_tab.py` + `gui/ui/ufe_calibration_tab.ui` (estructura,
  textos y tooltips en Designer; el código cablea).
- Contenido: resumen de la receta para la toma o la visita (qué master usaría
  para cada pieza, o qué falta), botón «Calibrar» (toma actual / toda la
  visita), casilla de export de calibrados (`calib_export`), y la lista de
  avisos (sin flat, sin dark, master fuera de tolerancia).
- Se engancha con `gui/ufe_dialog.py::add_feature_tab` (ADR-044/053).

### 7.2 Pestaña Track & Stack

- `gui/ufe_trackstack_tab.py` + `gui/ui/ufe_trackstack_tab.ui`.
- Contenido, de arriba abajo:
  1. **Objeto y efeméride**: nombre del proyecto, rate y PA, ventana. Solo
     lectura (viene del proyecto y de Horizons).
  2. **Número de observaciones**: un `QSpinBox` de 1 a N, con la **tabla de
     SNR previsto por grupo** (`preview_groups`) que se recalcula al cambiarlo
     (D22). Si algún grupo baja del umbral de envío, se ve antes de apilar.
  3. **Apilado**: método (suma/media/mediana/sigma), margen del recorte, umbral
     de detección; botón «Apilar la secuencia», barra de progreso y cancelar.
     Aviso de dithering (D27) y del control de calidad del WCS si salen.
  4. **Barrido**: resultado del fine-tuning (rejilla de score, módulo y PA
     elegidos) con su explicación.
  5. **Visor por grupo**: el stack de cada observación en el visor del UFE
     (`gui/ufe_state.py`, `core/stretch.py`), con la posición medida marcada.
  6. **Secuencia centrada**: el GIF/montaje de la fase 5, embebido o abierto en
     su visor.
  7. **Medida**: por grupo, las dos vías (stack y frames), la diferencia, los
     flags, la magnitud (o por qué falta) y el rmsRA/rmsDec con su desglose.
  8. **Chequeo**: residual propio, dispersión de los demás, número de
     observatorios, veredicto (ok / outlier / sin referencia / no disponible)
     y botón de forzar cuando bloquee (D25, D29). Si Find_Orb no está
     configurado, se dice y se ofrece un enlace a Ajustes; el fichero de
     observaciones queda accesible para usarlo a mano.
  9. **Reporte**: elección de formato (ADES PSV / 80 col) y de vía
     (`stack`/`frames`), botón «Generar», y «Enviar al bloque MPC de la
     visita», que rellena la caja de pegado y deja que el validador de ADR-022
     haga su trabajo.
  10. Botón «?» que abre `docs/ASTROMETRY.es.md` en el visor de docs.
- Se engancha con `add_feature_tab`; se abre desde la visita.

### 7.3 Workers (`gui/workers.py`)

- `CalibrationWorker(QThread)`: calibra la visita, señales de progreso,
  cancelación y sin dejar hilo colgado.
- `TrackStackWorker(QThread)`: etapas (solve, registro, apilado base,
  detección, barrido, apilado por grupo, medida, chequeo), con progreso por
  etapa y cancelación. Sigue el patrón de `SeriesWorker` (ADR-048).

### 7.4 Enganche al host (`gui/main_window.py`, `gui/widgets/visits_panel.py`)

- `_ufe_open` gana los hooks de la pestaña nueva; un
  `_ufe_astrometry_context(pid, session_id)` arma el contexto (frames de la
  visita, objeto del proyecto, sitio) igual que `_ufe_series_context`.
- `VisitWindow` gana el botón «Astrometría de la secuencia» (abre la pestaña
  con la visita) y su bloque MPC existente recibe el reporte generado.
- El historial de la ficha (D28) se pinta en `gui/widgets/object_hero.py` y en
  el panel de objeto, con tooltips de `core/explain.py`.

### 7.5 Ajustes

- `gui/ui/settings_dialog.ui` (cargado en `main_window.py` con
  `_load_ui("settings_dialog")`) gana la **biblioteca de masters** dentro de la
  pestaña «Site & equipment» (los masters son equipo) o en una pestaña
  «Calibración» propia: alta (elegir fichero y metadatos), listado por
  cámara/filtro/tipo, borrado, y los parámetros del matching
  (`calib_temp_tol_c`). En la misma zona se configura **Find_Orb**
  (`findorb_path`, `findorb_run`), apuntando al **no interactivo** (`fo` en
  Linux/macOS, `fo64.exe` en Windows), con un botón de «probar» como el de
  ASTAP y un enlace a la sección de Find_Orb de `docs/ASTROMETRY`.

### 7.6 Cadenas nuevas (tabla ES/EN)

Todas pasan por `self.tr()` y se traducen con `lupdate`/`lrelease` (ADR-014).
Las principales:

| ES | EN |
|---|---|
| Número de observaciones | Number of observations |
| SNR previsto por observación | Expected SNR per observation |
| Apilar la secuencia | Stack the sequence |
| La secuencia no está dithered: el ruido de patrón puede apilarse | The sequence is not dithered: pattern noise may stack up |
| Barrido de velocidad | Velocity sweep |
| Secuencia centrada en el objeto | Sequence centred on the object |
| Medida sobre el stack | Measurement on the stack |
| Medida por frame | Per-frame measurement |
| Las dos medidas no coinciden | The two measurements disagree |
| Chequeo contra otros observadores | Check against other observers |
| Sin otras observaciones para comparar | No other observations to compare with |
| El chequeo filtra, no demuestra | The check filters, it does not prove |
| SNR insuficiente para enviar (mínimo %1) | SNR too low to submit (minimum %1) |
| Observatorios distintos | Distinct observatories |
| Última observación | Last observation |
| Generar reporte ADES | Generate ADES report |
| Generar reporte de 80 columnas | Generate 80-column report |
| Enviar al bloque MPC de la visita | Send to the visit's MPC block |
| Deshacer esta ejecución | Undo this run |
| Liberar espacio de la visita | Free up visit space |

## Tests

- `tests/unit/test_ufe_trackstack_tab.py`: señales, tabla de SNR previsto al
  cambiar el número de observaciones, aviso de dithering, bloqueo del chequeo
  y forzado, botón de reporte deshabilitado con SNR bajo, sin dejar widgets
  huérfanos (offscreen).
- `tests/unit/test_ufe_calibration_tab.py`: receta resuelta, avisos, export.
- `tests/unit/test_object_history.py` (ampliado): la ficha pinta las tres
  cifras.
- i18n sin `unfinished`.

## Salida limpia

El flujo completo en la GUI: visita → calibrar → elegir observaciones → apilar
→ barrido → secuencia centrada → medida → chequeo → reporte → bloque MPC.
Legacy intacto y suite verde.

## Hecho cuando

Se puede recorrer el flujo de punta a punta con una secuencia sintética desde
la GUI, los avisos se leen en lenguaje llano, y ninguna cifra aparece sin su
explicación.
