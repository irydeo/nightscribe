# Plan: fotometría de secuencias, detrend, ajuste de tránsito y ExoClock

*Plan de trabajo con todo lujo de detalles / Detailed working plan.*

- **Rama**: `plan/series-photometry` (creada desde `main` actualizado a `origin/main` 909ef1f).
- **Alcance**: piezas **T1–T8** de `docs/PRECISION.es.md` (apéndice B, líneas 202–241), más los
  apéndices separables (ASTAP, modo en vivo, API ExoClock) y la documentación de usuario.
- **Estado**: decisiones cerradas en conversación con el autor; la **fase 0** las convierte en
  ADRs firmados antes de escribir código (la nota de `PRECISION.es.md:204` exige firmar la
  reapertura de ADR-015 con el usuario).
- **Estilo**: este documento sigue las reglas de la casa (escribimos con «:», «,» y «;»; la
  semirraya «–» solo para rangos numéricos, nunca como raya).

---

## 1. Contexto: qué hay y qué falta

Hoy NightScribe mide **una placa** con calidad de investigación (pestaña Fotometría del Editor
FITS unificado: ZP con color, cielo en gradiente, apertura por FWHM, saturación real, error
total, semáforo, sustracción de huésped; ver `docs/PRECISION.es.md` piezas H1–H7 y
`docs/PLANS/ufe-photometry.md`). Los puntos ya se guardan por visita (`core/followup.py`) y la
curva de luz del proyecto ya se dibuja y plega (`core/lightcurve_data.build_payload`).

Lo que falta es **medir una secuencia como una secuencia**: normalizar cada frame con su propio
punto cero, sacar el detrend honesto, guardar el resultado como curva con flags y errores
honestos, y de ahí al ajuste de tránsito, a ExoClock y al modo en vivo. Eso es T1–T8.

La decisión maestra está firmada en este ciclo: **se reabre ADR-015**; NightScribe hace su
detrend, su ajuste y su profundidad en numpy puro (sin scipy, sin astropy, ADR-004), tomando a
EXOTIC como espejo de calidad sin copiar su código; el handoff con `inits.json` (ADR-004/015)
queda intacto como vía experta para el stack pesado.

---

## 2. Registro de decisiones (D1–D39)

### Maestras

- **D1 · Reabrir ADR-015 de verdad.** NightScribe calcula su detrend, su ajuste de tránsito y su
  profundidad en numpy puro. *Por qué*: T1–T8 exigen curvas y ajustes dentro de la app; EXOTIC
  (astropy, Python ≤3.10, ultranest) es inviable en nuestro PyInstaller con Py3.12 (ADR-004).
- **D2 · EXOTIC como espejo de calidad, no como código.** Adoptamos su *método* (detrend
  `a1·exp(a2·X)`, bounds de parámetros, sigma-clip por ventanas, errores OOT, diagnósticos) con
  fórmulas citadas (Zellem et al. 2020); **no se copia ni una línea** (licencia Caltech/JPL).
  El stack pesado (muestreo anidado, limb darkening LDTk, ajustes multi-noche, fotometría PSF) se
  queda detrás del handoff a EXOTIC.
- **D3 · Alcance por fases.** Núcleo T1–T8 = fases 0–8. Apéndices separables que no bloquean al
  núcleo: **9** ASTAP, **10** modo en vivo, **11** API ExoClock. El barrido
  apertura×anillo×comp (práctica de EXOTIC) entra **por defecto apagado**; la salida AAVSO
  `#TYPE=EXOPLANET` se **documenta** pero no se construye.
- **D4 · Orden de fases 0–12 con dos compuertas.** Fase 7: paridad con EXOTIC sobre su dataset;
  fase 11: petición a ExoClock, con permiso explícito del autor. Cada fase termina con la app
  funcionando y una salida limpia.
- **D5 · ADRs de este plan.** Revisión de **ADR-015** (exigida por `PRECISION.es.md:204`) y
  nuevos **ADR-048** (fotometría de series), **ADR-049** (ExoClock), **ADR-050** (modo en vivo y
  agrupación de tomas cortas), **ADR-051** (solver local ASTAP). El registro arranca en 048
  porque ADR-047 ya existe.

### Entrada, interfaz y semántica de corrida

- **D6 · La acción por lotes vive en la pestaña Fotometría del UFE**, con un **`LightCurveChart`
  compacto embebido** en esa misma pestaña (no una ventana nueva). *Por qué*: el usuario ya
  está midiendo la placa ahí; la serie es «más de lo mismo», no otro sitio.
- **D7 · Auto-guardado con «Deshacer esta corrida»**, en vez de previsualizar-y-confirmar: cada
  punto se guarda a medida que los frames completan, y una sola acción revierte la corrida
  entera. Los frames con gate **se marcan, nunca se borran**; la curva detrendada se pinta
  **siempre** junto a la cruda.
- **D8 · Las imágenes de la serie salen siempre de la visita/sección** (nunca diálogo de
  carpeta). El UFE abierto ad-hoc (imagen suelta) **esconde** el botón de serie, con la misma
  regla que `btn_save_project`. *Por qué*: la serie necesita un contexto de proyecto para sus
  puntos, su undo y su análisis.
- **D9 · `run_id` persistido y presupuesto de rendimiento.** El «deshacer» sobrevive a
  reinicios; el estado «serie incompleta» (corrida cancelada o a medias) es visible; presupuesto
  **<0,5 s por frame** y UI responsive con una serie de 142 frames (el dataset real de EXOTIC).

### Motor

- **D10 · `measure_plate`, la receta única.** La receta de la placa única se extrae de
  `gui/ufe_measure_tab.py` a `core/photometry.measure_plate(...)`; placa única y serie la
  comparten. *Por qué*: dos recetas distintas significan dos precisiones distintas.
- **D11 · Motor agnóstico por parámetros, sin ramas `if kind`.** `SeriesConfig` con
  `zp_mode="catalog"|"relative"`, `detrend_policy="off"|"airmass"|"auto"`, `host_ref` opcional
  y `comp_set` opcional; los tipos (tránsito, variable, SN, HADS) solo cambian esos parámetros y
  las reglas de la capa de análisis.
- **D12 · Validación del motor con pruebas sintéticas de semilla.** Tres pruebas ancla: (a) dip
  de **0,01 mag** recuperado a **±0,001 mag**; (b) seno puro de **0,3 mag en 2 h** sin
  distorsionar por el detrend; (c) SN con gradiente de galaxia recuperado al **1 %** en modo
  `relative`. Más la serie de dos noches del D34.
- **D13 · Detrend `a1·exp(a2·X)` con `a1` analítico; guardado sin columnas nuevas.** Los
  coeficientes y el resumen viven en el panel de resumen, en la columna `notes` del CSV y en la
  meta de la serie; **no se añaden columnas a la base para el detrend** (solo `mag_raw` y
  `flags`, ver D18).
- **D14 · Error honesto por punto, con el centilleo sobre el span del grupo.** Ecuación CCD
  (ganancia/RON) + centilleo (Young 1967, con los parámetros del sitio) + término ZP/color; con
  agrupación, el centilleo se integra sobre la extensión temporal del grupo (D19). El panel y
  el CSV distinguen **error interno** de **error total**; el total nunca baja del interno.
- **D15 · Ensemble ponderado con veto MAD por frame (T2).** Media ponderada por el error de
  cada comp, con veto de la comp outlier en cada frame; sin dispersión de color, la pendiente se
  reporta indeterminada y no rompe nada (regla H1).
- **D16 · Convención temporal única.** Por defecto, instante a **media exposición**; para ExoClock
  se exporta el **arranque** de la exposición (D30); `BJD_TDB` se calcula bajo demanda con tabla
  de bumeranes embebida + corrección heliocéntrica, con el sesgo residual (<0,02 s) **medido y
  documentado**.
- **D17 · Sin astrometría por frame.** La serie se siembra desde la placa de referencia (WCS si
  hay, o un clic del usuario), sigue al objetivo por centroide local y marca `guide_jump` cuando
  el salto es grande (reanclaje); la anotación de puntos degrada con «sin WCS» en vez de mentir.
- **D18 · Migración v12 mínima.** Solo `mag_raw REAL` y `flags TEXT` en la tabla de puntos, más
  los helpers de escritura en lote (`add_points`, `delete_points(db, ids)`) en
  `core/followup.py`/`core/db.py`. Nada más cambia de esquema.

### Serie, cadencia y honestidad

- **D19 · Agrupación en el dominio de la medida, nunca apilado de píxeles.** Se mide cada
  sub-toma y se combinan los **flujos** con pesos `1/σ²` y veto MAD (≥2 tomas válidas); el error
  del grupo incluye el centilleo sobre su span; el tiempo efectivo es la media ponderada de los
  medios de sus miembros; para ExoClock, arranque = media − integración total/2, documentado en
  el `ExoClock_info.txt`. *Por qué*: apilar en píxel destroza la fotometría de precisión y el
  modelo de error (práctica CMOS/sCMOS del Gsense 400 y de la literatura del autor: QHY42Pro).
- **D20 · Guardia de cadencia: aviso, no bloqueo.** Reglas por tipo (tránsitos: ≥3 puntos por
  ingress con la ventana recomendada de `core/transits.py`; HADS: `POINTS_PER_CYCLE=12` y
  `CADENCE_CAP_S=900` de `core/hads.py`; variables: criterio de Nyquist). Si se rompe el ingress,
  el aviso pasa a **rojo**; `group_n=1` por defecto para tránsitos y variables (agrupar ahí es
  un riesgo, no una ganancia). Las reglas viven en la capa de análisis, no en el motor.
- **D21 · En vivo y agrupación componen.** El driver en vivo cierra un punto cuando el grupo se
  completa (N tomas o T segundos); los ficheros en vivo **no necesitan estar resueltos**
  astrométricamente.
- **D22 · Guardas de honestidad.** Puntos en modo `relative` quedan **bloqueados** para el
  export AAVSO EFF; la cabecera del CSV lleva el `mode`; el panel dice en lenguaje llano qué es
  cada columna.
- **D23 · Modo en vivo barato.** Sondeo de carpeta ~2 s, chequeo de estabilidad de tamaño antes
  de leer, commits de SQLite agrupados (5 frames o 10 s), `notify_points` por lote, y **un solo
  motor**: el mismo `measure_series` del D10/D11, sin «otro motor para en vivo».
- **D24 · No reimplementar el plegado.** El análisis periódico se alimenta con
  `lightcurve_data.build_payload(source="measure")`; NightScribe ya pliega y esquematiza bien,
  así que la serie solo aporta puntos.
- **D25 · Sin concesiones de calidad ni de facilidad.** El flujo por defecto **es** el de máxima
  precisión; todo default está citado en el código, cubierto por tests con semilla y
  configurable: parámetros del **sitio** en Configuración (ADR-028) y parámetros de
  **placa/serie** en el `UfeAdvancedDialog` existente (ampliado, nunca un diálogo nuevo). Cada
  control muestra su default, su tooltip con unidades y razón, y un «restaurar default».

### Solucionador y ajuste

- **D26 · ASTAP como solver local.** `core/sources/astap.py` con el contrato de
  `core/sources/astrometry.py` (`solve(path, progress) -> cards|None`), dispatcher `core/solve.py`
  con `solver=auto|astap|astrometry` y `astap_path`; WCS **en memoria** vía el lado `-wcs`
  parseado con `fits_io.read_header` (nunca mutar el FITS del usuario); `-update` opcional y solo
  desde el botón Solve del UFE; hints `-fov` (de `pixel_um`/`focal_mm`), `-ra`, `-spd`; caché por
  hash+backend; mensajes de fallo bilingües.
- **D27 · Limb darkening cuadrático (Claret)** con paridad de modelo <1e-5 frente a
  `pylightcurve` en modo cuadrático; la diferencia del no lineal queda absorbida por la
  tolerancia fin a fin (T_mid 3σ, Rp/Rs 5 %); se revisa solo si aparecen residuos de ingress en
  el dataset de validación.
- **D28 · Validación de las σ contra EXOTIC.** Si la desviación de nuestros parámetros se sale
  >20 % de la del posterior de EXOTIC, se cambia a **bootstrap paramétrico**.
- **D29 · La combinación de comps la arbitra el dato.** Implementadas las dos (ponderada, la del
  T2, por defecto; y suma de flujos, la de EXOTIC/AIJ); gana la de **menor dispersión OOT** en el
  dataset; la perdedora se documenta como alternativa.

### ExoClock

- **D30 · Export con formato HOPS, envío manual.** Archivo de **3 columnas** (JD_UTC de arranque
  de exposición, flujo relativo, error) + `ExoClock_info.txt` con el Comments prefilled (planeta,
  formato de tiempo, sello, filtro, exposición, autocalificación del observador); el botón
  **abre `https://exoclock.space/upload/` en el navegador** del usuario; al confirmar, outcome
  `reported_exoclock` (`core/project.py`). **Sin credenciales guardadas y sin scraping** de
  `/upload/` (lo prohíbe robots.txt). *Por qué*: no hay API pública de subida (verificado
  2026-09-27: `/api/` responde 404, solo hay endpoint de lectura `database/planets_json`, y el
  paquete oficial `exoclock` de PyPI es solo lectura).
- **D31 · Checklist previo con semáforo.** Antes de exportar: baseline ≥1 h a cada lado, ≥3
  puntos por ingress, sin flags rojos, dip coherente con la efemérides. **No bloquea**: es un
  consejo honesto, no un muro.
- **D32 · La API de ExoClock es la compuerta de la fase 11.** Solo se construye si existe un
  endpoint público documentado y el autor da permiso explícito; en caso contrario la fase 11 se
  cierra documentando el envío manual de la fase 8.

### Disciplina y reuso

- **D33 · Nada ya cubierto se reimplementa.** Plegado (D24), export CSV/EFF
  (`core/photometry_export.py`), quicklook (`core/series.py`), payloads de Análisis
  (`core/lightcurve_data.py`) y handoff EXOTIC se usan tal cual; el plan solo añade encima.
- **D34 · Multinoche: detrend local por noche, señal global.** Coeficientes `a1_n·exp(a2_n·X)`
  por noche (reparto de `glc_fitter` de EXOTIC: parámetros locales por curva, globales
  compartidos), con fallback a `a1` solo (escala) en noches cortas o con rango de masa de aire
  insuficiente, **dicho en el panel** («noche sin rango de aire para el detrend; solo escala»).
- **D35 · Multinoche: consistencia entre noches.** Set de comps fijo desde la noche de
  referencia (VSX + ventana de brillo), desviaciones **marcadas** y nunca silenciosas; chequeo de
  ZP por noche vs. catálogo (aviso si una noche se desplaza); **guardia de banda**: si mezclan
  filtros, no se combinan en una sola curva de magnitudes, se pintan por noche con su aviso.
- **D36 · Multinoche: una corrida por noche, agrega Análisis.** Cada noche es una corrida con su
  `run_id` y su Undo independiente; la agregación por objetivo la hace la vista Análisis (ya
  existe vía `fu["points"]`); **binning solo de visualización** (el `time_bin` de EXOTIC, nunca
  altera datos) para series de miles de puntos; entrada de listados con acción «Añadir ficheros
  a la visita» (selección múltiple; **no** diálogo de carpeta: la regla D8 se mantiene).
- **D37 · Documento de usuario `SEQUENCES`.** Nueva pareja `docs/SEQUENCES.es.md` +
  `docs/SEQUENCES.md` (el «qué es y cómo se trabaja»; `PHOTOMETRY` sigue siendo las prácticas y
  `PRECISION` los números). Bilingüe, progresivo por fases (5, 8, 10, 12), con botón «?» en el
  bloque de serie que lo abre en el visor de docs (que descubre los `.md` solo).
- **D38 · Compuertas con umbrales fijos.** Los umbrales de la fase 7 (y de la 11) se escriben
  **antes** de medir y **no se relajan para que un test pase**; si algo no pasa, se reporta y se
  actúa según el plan (vía handoff / cerrar apéndice), nunca ajustando el umbral hacia abajo.
- **D39 · Validación de tipos en este ciclo.** SN, variables y HADS de seguimiento, y el modo en
  vivo, se validan **ahora**, en este plan (pruebas sintéticas + dataset real), no «más tarde»:
  el motor es agnóstico (D11), así que validar un tipo es validar parámetros, no código nuevo.

---

## 3. Alcance: núcleo y apéndices

| Bloque | Fases | Qué incluye | Si hay que recortar |
|---|---|---|---|
| **Núcleo T1–T8** | 0–8 | ADRs, `measure_plate`, motor, detrend, migración v12, worker+UI, visitas/multinoche, ajuste de tránsito, ExoClock manual | **No se recorta**: es lo que firma PRECISION |
| Apéndice A | 9 | Solver local ASTAP | Se aplaza al final |
| Apéndice B | 10 | Modo en vivo | Se aplaza |
| Apéndice C | 11 | API ExoClock | Depende de permiso y de endpoint (D32) |
| Por defecto apagado | 3/7 | Barrido apertura×anillo×comp estilo EXOTIC | Entra desactivado; se enciende desde Avanzado |
| Documentado, no construido | 8/12 | Salida AAVSO `#TYPE=EXOPLANET` | Solo doc |

Orden de recorte si aprieta (del primero al último): barrido ap×anillo×comp, acción «Añadir
ficheros a la visita», API ExoClock, modo en vivo, ASTAP.

---

## 4. Las 13 fases

Cada fase declara: **decisión**, **por qué**, **implementación conceptual** (ficheros y puntos
de enganche reales), **tests** y **salida limpia**. Regla transversal: una fase = la app
funcionando + suite verde (`.venv/bin/python -m pytest tests/unit`) + i18n sin `unfinished`.

### Fase 0 · Documentos y decisiones firmadas

- **Decisiones**: D1, D2, D5, D38; y el checklist de verificaciones de la sección 5.
- **Por qué**: `PRECISION.es.md:204` exige firmar la reapertura de ADR-015 antes de código; los
  ADRs nuevos fijan el marco (48 serie, 49 ExoClock, 50 en vivo+agrupación, 51 ASTAP) para que
  las fases siguientes no reabran discusiones.
- **Implementación**: revisión de `docs/adr/ADR-015-exoplanets.md` (estado: reabierto; la vía
  numpy pasa a ser la primera, el handoff queda como vía experta); cuatro ADRs nuevos en
  `docs/adr/` y entrada en `docs/adr/README.md`; este documento ya está escrito
  (`docs/PLANS/series-photometry.md`, con su **PUNTO DE ENTRADA** en la sección 7); actualizar
  `docs/PRECISION.es.md:115` y su par inglés (la fila «Falta: piezas T1–T8; decisión ADR-015…»
  pasa a «en curso, ver PLANS/series-photometry»); cerrar el checklist de la sección 5 con el
  resultado de cada verificación y su fallback ya elegido.
- **Tests**: comprobación de enlaces de docs y ADR README; ningún código se toca.
- **Salida limpia**: ADR-015 firmado por el autor; 5 ADRs publicados; checklist cerrado; el
  plan no deja preguntas abiertas antes de la fase 1.

### Fase 1 · `measure_plate`: extraer la receta de la placa

- **Decisiones**: D10, D25.
- **Por qué**: la receta completa de medida vive hoy en la GUI
  (`gui/ufe_measure_tab.py`: bloque `_measure`/`_calibrate_and_fill`, y el área de export EFF en
  `_measure` de la pestaña). La serie necesita llamarla sin GUI y sin duplicarla; dos recetas
  serían dos precisiones.
- **Implementación**: extraer a `core/photometry.measure_plate(image, cfg) -> PlateResult`
  (dataclass: flujo del objetivo, comps con errores, FWHM, cielo, flags, ZP±err, término de
  color, error interno/total, Δ de la check); la pestaña pasa a ser una fachada que llama a esa
  función y pinta; los parámetros de placa salen de un `PlateConfig` con los mismos defaults de
  hoy (los citados en H3: `r_ap = 1,35·FWHM`, `flat_resid_mag=0,007`, etc.).
- **Tests**: `tests/unit/test_photometry.py` y `test_ufe_measure_tab.py` siguen verdes sin
  cambios de comportamiento; test nuevo de contrato (mismas entradas → mismas salidas que antes,
  comparando con la referencia congelada de una placa sintética de semilla fija).
- **Salida limpia**: GUI idéntica, motor extraído y testeable sin Qt.

### Fase 2 · Motor de serie (`core/series_measure.py`)

- **Decisiones**: D11, D14, D15, D17, D20 (reglas viven fuera), D33, D35 (motor acepta
  `comp_set` fijo).
- **Por qué**: es el corazón T1/T2/T4/T6/T7; agnóstico por parámetros (D11) para que SN,
  variables y HADS entren sin código propio (D39).
- **Implementación**: `SeriesConfig` (frozen dataclass: `zp_mode`, `detrend_policy`, `host_ref`,
  `comp_set`, aperturas, techo de saturación, parámetros de sitio, `group_n`) y
  `measure_series(paths, cfg, progress, cancel) -> SeriesResult` con un punto por frame: ZP por
  frame desde las comps de **esa** imagen (T1, reutilizando `measure_plate`), ensemble ponderado
  con veto MAD por frame (T2), puertas por frame (T7: saturación, `guide_jump` por centroide
  sobre la placa de referencia, cósmico sigma-clip local, ZP outlier/nube; **marcado, nunca
  borrado**), error total por punto (T4, con `scintillation_mag` sobre el span), instante a
  media exposición y `mjd`/`hjd` con la convención del D16. Sin astrometría por frame (D17).
  Progreso y cancelación al estilo de `SequenceWorker` en `gui/workers.py`.
- **Tests**: `tests/unit/test_series_measure.py` con las tres pruebas ancla del D12 y semillas
  fijas; test de rendimiento (142 frames sintéticos <0,5 s/frame); test de cancelación (estado
  «serie incompleta»).
- **Salida limpia**: motor usable desde tests y CLI; la GUI todavía no expone la acción.

### Fase 3 · T3 y T5: apertura óptima y detrend honesto

- **Decisiones**: D13, D25, D34.
- **Por qué**: T3 (apertura por noche) y T5 (detrend) son donde la curva se ganan o se pierde el
  rms; y el detrend mal construido se come señal (advertencia literal de `PRECISION:226`).
- **Implementación**: barrido de `k ∈ [1,0; 2,0]·FWHM` por noche eligiendo el que minimiza el
  rms de la check (con FWHM por frame, para que las defensas de guiado no rompan la curva);
  `detrend_series(...)` con `a1·exp(a2·X)` y `a1` **analítico** (EXOTIC), política por capas:
  `off` (curva cruda), `airmass` (mínimo honesto), `auto` (añade FWHM/cielo/x-y solo si el
  residuo baja con umbral de mejora citado). En multinoche, coeficientes por noche con fallback
  `a1`-solo (D34). Salida en tres sitios: panel de resumen, columna `notes` del CSV, meta de la
  serie (D13: sin columnas nuevas). La pestaña pinta **cruda + detrendada** con la leyenda
  explicando que el detrend puede comerse señal.
- **Tests**: las tres anclas del D12 (el dip no debe moverse con el detrend; el seno no debe
  distorsionarse), la prueba A/B de dos noches con transparencia desplazada un 3 % (plana con
  detrend por noche, salta sin él) y el fallback de noche corta.
- **Salida limpia**: curva cruda y detrendada con coeficientes a la vista; nada de magia.

### Fase 4 · Migración v12

- **Decisiones**: D18, D7 (flags persistidos), D9 (`run_id`).
- **Por qué**: los puntos de serie necesitan su crudo (`mag_raw`) y sus puertas (`flags`)
  **sin** tocar el resto del esquema ni romper el flujo de puntos existentes de las visitas.
- **Implementación**: en `core/db.py` (`_migrate`, tras la v11): `mag_raw REAL`, `flags TEXT`,
  y guardar `run_id` en la fila (hoy la columna de sesión ya existe en el patrón de visitas; si
  no, se reutiliza `session_id` con el id de corrida); helpers `add_points(db, rows)` en lote y
  `delete_points(db, ids)` en `core/followup.py` (junto a `add_point`, `list_points`,
  `delete_points_for_file`); la migración es idempotente y avisa si el esquema viene de otra
  versión conocida.
- **Tests**: `tests/unit/test_db_v12.py`: migración desde v11 y desde esquema limpio, idempotencia,
  escritura en lote + `delete_points` por `run_id` (el «deshacer» de una corrida sin tocar otras).
- **Salida limpia**: bases existentes actualizan sin pérdida; los flujos de puntos de hoy no se
  enteran.

### Fase 5 · Worker + interfaz de la serie

- **Decisiones**: D6, D7, D8, D9, D20 (guardia en la UI), D25, D37 (mitad del documento
  `SEQUENCES`).
- **Por qué**: sin este punto, el motor no es un producto; el usuario debe poder medir la serie
  de su visita con progreso, semáforo, flags explicados y «Deshacer esta corrida» a un clic.
- **Implementación**:
  - `gui/workers.py`: `SeriesWorker` (patrón `SequenceWorker`: QThread, señales de progreso,
    cancelación, `notify_points` por lote hacia `ufe_dialog.set_point_hook`/`notify_point`,
    extendidos para aceptar batch y `run_id`).
  - `gui/ui/ufe_measure_tab.ui` (ADR-005): bloque de secuencia (botón «Medir la secuencia»,
    contador de frames, control de agrupación con su texto de cadencia, progreso, botón
    «Deshacer esta corrida», botón «?»). El botón se oculta si la pestaña no tiene visita (D8).
  - `LightCurveChart` compacto embebido en la pestaña (placeholder `QWidget` +
    `replaceWidget`): cruda + detrendada, puntos con flag en color y forma distintos
    (extender `lightcurve_widget._point_style` si aún no soporta tres series, verificación 6),
    leyenda por noche en multinoche, decimación de visualización (D36).
  - `gui/ufe_advanced_dialog.py` + `.ui` ampliados con los knobs de serie (aperturas, `group_n`,
    política de detrend, ventana de sigma-clip, techo de saturación), cada uno con default
    visible, tooltip con unidades y razón, y «restaurar default» (D25). Los knobs de **sitio**
    (ganancia, RON, diámetro, altura, centilleo) van a Configuración (ADR-028), que ya tiene
    `edt_astrometry_key` como referencia de dónde vive.
  - Textos con `tr()`; el botón «?» abre `SEQUENCES` en el visor de docs (D37).
- **Tests**: `tests/unit/test_ufe_measure_tab.py` ampliado (señales, ocultación del botón sin
  visita, undo), test offscreen del worker con serie sintética, test de que la serie cancelada
  deja el estado «incompleta», i18n sin `unfinished`.
- **Salida limpia**: flujo completo en la GUI: visita → Medir → progreso → curva → flags →
  deshacer; app funcional y legacy intacto.

### Fase 6 · Visitas, proyecto y multinoche

- **Decisiones**: D20, D24, D35, D36, D8 (entrada de listados).
- **Por qué**: es donde las tres misiones de uso (tránsito, variable, SN multinoche) se
  conectan al análisis existente; sin esta fase, la serie sería un adorno sin análisis.
- **Implementación**:
  - `gui/widgets/visits_panel.py` (`_on_measure_clicked`): arranca la serie de la visita (no
    de una carpeta), y la nueva acción «Añadir ficheros a la visita» (selección múltiple) para
    llegar ahí desde un listado (D36).
  - Cada noche = una corrida con su `run_id` y su Undo; en la curva, línea/leyenda por noche.
  - Análisis (`main_window._analysis_transit_block`, `_fu_science_blocks`,
    `_fu_export_report`): alimentar `lightcurve_data.build_payload` con `source="measure"` para
    que la curva medida entre en el plegado de variables/HADS y en la vista de SN **sin
    reimplementar nada** (D24/D33).
  - Guardia de cadencia (D20) al crear la serie: aviso con las reglas del tipo (tránsito: puntos
    por ingress; HADS: 12 puntos y tope de cadencia; variable: Nyquist); rojo si se rompe el
    ingress; `group_n=1` por defecto en tránsitos y variables.
  - Multinoche: chequeo de ZP por noche y guardia de banda (D35) en el panel de resumen.
- **Tests**: serie sintética de dos noches (agregación, undo por corrida sin tocar la otra,
  aviso de banda mezclada, aviso de ZP desplazado), test de `build_payload(source="measure")`
  con plegado de una variable sintética, test de la guardia de cadencia (aviso y rojo).
- **Salida limpia**: la curva medida vive en el proyecto, se analiza como las demás y el flujo
  de visitas no cambia de comportamiento.

### Fase 7 · Ajuste de tránsito (COMPUERTA)

- **Decisiones**: D1, D2, D27, D28, D29, D38.
- **Por qué**: T5+T7 dan la curva; el usuario de tránsitos necesita T_mid, profundidad y
  errores, dentro de la app, con la calidad de EXOTIC y sin su stack.
- **Implementación**: `core/transit_fit.py`:
  - Modelo: tránsito cuadrático con limb darkening de Claret (D27), efemérides de
    `core/transits.py` como semilla (T0 + n·P), parámetros `rprs`, `tmid`, `a/R*` (o duración
    equivalente) y baseline local.
  - Ajuste: Gauss-Newton/LM en numpy con jacobiano analítico (sin scipy), bounds como en EXOTIC:
    `rprs ∈ [0; 1,25·prior]`, `tmid ± 25σ` con tope `±P/4`, `a2 ∈ [-1; 1]`; sigma-clip de 25–30
    min por `lstsq` deslizante; errores desde la dispersión OOT (no de la covarianza interna
    sola); diagnósticos: `quality` (χ² reducido), duración **medida vs esperada**, y parámetros
    con sus σ.
  - Detrend conjunto `a1·exp(a2·X)` durante el ajuste (el mismo del D13, reutilizado).
  - Entrada desde Análisis (`_analysis_transit_block`), para proyectos de tipo tránsito; para
    SN y variables el motor no se toca (D11).
  - **Compuerta**: paridad con EXOTIC sobre su dataset real (ver verificación 2): **T_mid dentro
    de 3σ** de EXOTIC, **Rp/Rs dentro de 5 %**, **σ de parámetros dentro de 20 %** (si no, D28:
    bootstrap paramétrico), profundidad de la muestra conocida dentro del 10 %
    (`PRECISION:237–240`) y rms de la check acorde al modelo de ruido. Umbrales fijados en el
    ADR-015 revisado **antes** de medir (D38).
- **Tests**: `tests/unit/test_transit_fit.py` con el dataset sintético de semilla, la paridad de
  modelo D27 (<1e-5 vs `pylightcurve` o, si no instala, vs `batman`, verificación 3) y la suite
  funcional con datos reales; los umbrales se escriben como constantes citadas.
- **Salida limpia (o compuerta cerrada)**: si la paridad pasa, la fase 8 arranca sobre ese
  ajuste; si no, se reporta el resultado, **no se relaja el umbral** (D38), y el ajuste sigue la
  vía handoff a EXOTIC mientras se diagnostica. En ningún caso queda la app rota.

### Fase 8 · ExoClock

- **Decisiones**: D30, D31, D37 (sección ExoClock de `SEQUENCES`).
- **Por qué**: el usuario mide tránsitos para enviarlos a ExoClock, y hoy el camino termina en
  un CSV genérico; además, EXOTIC **no** sube a ExoClock, así que este puente es nuestro valor
  añadido.
- **Implementación**: `core/exoclock_export.py`:
  - Archivo de 3 columnas (JD_UTC de **arranque** de exposición, flujo relativo, error), con la
    media de los comps en el denominador (convención HOPS) y, con agrupación, arranque = media −
    integración total/2 (D19).
  - `ExoClock_info.txt`: Planeta, Time format JD_UTC, Time stamp Exposure start, Flux format
    Flux, Filter, Exposure time, Comments prefilled (autocalificación honesta y, si procede, la
    nota de agrupación).
  - Checklist con semáforo (D31) antes del botón; botón que genera ambos ficheros y abre
    `https://exoclock.space/upload/` en el navegador; al confirmar en la app, outcome
    `reported_exoclock` en el proyecto (`core/project.py:62`, ya existe el estado).
  - Sin credenciales, sin scraping, sin peticiones (la fase 11 mira si algún día hay API: D32).
- **Tests**: `tests/unit/test_exoclock_export.py`: número de columnas y de filas, JD de arranque
  con y sin agrupación, contenido del `info.txt`, campo Comments no vacío, outcome del proyecto,
  y que **no** se exporten puntos en modo `relative` (D22).
- **Salida limpia**: el usuario puede preparar y enviar su observación a ExoClock a mano, con el
  checklist avisándole si va a mandar algo flojo.

### Fase 9 · ASTAP (apéndice A)

- **Decisiones**: D26.
- **Por qué**: tener un solver local evita la clave de Astrometry.net para series en vivo y
  reduces puntos sin WCS (D17), sin renunciar a nova.
- **Implementación**: `core/sources/astap.py` (`solve(path, progress) -> cards|None`, mismo
  contrato y claves `_WCS_KEYS` que `core/sources/astrometry.py`), `core/solve.py` (dispatcher
  `solver=auto|astap|astrometry`, `astap_path`, caché por hash+backend), ajustes en
  `gui/ui/settings_dialog.ui` (`cmb_solver`, `edt_astap_path` con Examinar, botón «Probar»,
  `chk_astap_update`), WCS en memoria desde el lado `-wcs` parseado con `fits_io.read_header`,
  `-update` opcional y solo desde el botón Solve del UFE (`ufe_dialog._on_solve`), hints `-fov`
  (de `pixel_um`/`focal_mm`), `-ra`, `-spd`; integración con `core/blink.merge_solved_wcs`.
- **Tests**: contrato con un binario simulado (fijo de tarjetas), fallback a nova si ASTAP falla
  o no está, caché (segunda llamada no ejecuta nada), mensajes bilingües.
- **Salida limpia**: sin ASTAP instalado, todo funciona como hoy (auto → nova → aviso).

### Fase 10 · Modo en vivo (apéndice B)

- **Decisiones**: D21, D23, D17 (anotación sin WCS), D19 (agrupación compone).
- **Por qué**: en directo con el telescopio, el usuario quiere ver la curva formarse; y sus
  ficheros aún no están resueltos.
- **Implementación**: driver de sondeo (~2 s) sobre la carpeta de la sesión, chequeo de
  estabilidad de tamaño antes de leer, mismos commits agrupados (5 frames o 10 s) y
  `notify_points` por lote hacia la curva embebida; el driver cierra un punto cuando el grupo se
  completa (N tomas o T segundos); entrada y salida por el mismo worker/curva que la fase 5 (un
  solo motor, D23).
- **Tests**: carpeta sintética que crece (offline), detección de fichero a medias, agrupación en
  vivo, y cancelación sin dejar corrida colgada.
- **Salida limpia**: en vivo apagado por defecto; activarlo es opt-in y no cambia el flujo normal.

### Fase 11 · API ExoClock (compuerta con permiso)

- **Decisiones**: D32, D38.
- **Por qué**: solo si algún día ExoClock publica endpoint de subida (hoy no existe, verificado)
  y el autor lo autoriza, tiene sentido automatizar.
- **Implementación (condicionada)**: si hay endpoint documentado y permiso: cliente en
  `core/sources/exoclock.py` con red solo vía `core/db.py`, credenciales en clave del sistema
  (nunca en la base ni en el repo), reutilizando el export de la fase 8 como payload. Si no:
  se documenta en `SEQUENCES` y en ADR-049 que el envío es manual (salida de fase igualmente
  limpia).
- **Tests**: solo si se construye: contrato con endpoint simulado, sin secretos en tests.
- **Salida limpia**: el plan cierra este apéndice en cualquier caso, con su porqué escrito.

### Fase 12 · Documentación, i18n y WORKFLOWS

- **Decisiones**: D37, y el criterio global C2 de `PRECISION:246`.
- **Por qué**: la facilidad de uso es requisito del plan (D25), y `PRECISION` exige que la doc
  de usuario explique cada pieza con un ejemplo en ambos idiomas.
- **Implementación**:
  - `docs/SEQUENCES.es.md` + `docs/SEQUENCES.md` completos (secciones 1–9: qué es; tipos;
    desde dónde se trabaja; flujo paso a paso; mandos y defaults; cuándo fiarse; multinoche;
    solución de problemas; glosario y enlaces). Las secciones de ExoClock y en vivo se añadieron
    en las fases 8 y 10 (D37 es progresivo).
  - `docs/PHOTOMETRY.es.md`/`.md`: sección **T8** (flats a nivel mmag, dithering, desenfoque
    leve deliberado, cadencia constante, nada saturado).
  - `docs/PRECISION.es.md`/`.md`: T1–T8 pasan a «hecho», fila 115 actualizada, C1–C4 revisados
    (C2 suma `SEQUENCES`).
  - `docs/WORKFLOWS.es.md`/`.md`: enlaza `SEQUENCES` como el «cómo» del flujo de proyecto;
    `docs/adr/README.md` con los ADRs nuevos.
  - i18n: `lupdate` + traducción, sin `unfinished` (ADR-014).
- **Tests**: docs sin enlaces rotos (los `.md` locales navegan en el visor), i18n limpio, suite
  completa verde.
- **Salida limpia**: fin del plan: T1–T8 completos y documentados en ambos idiomas.

---

## 5. Checklist de verificaciones de la fase 0

Se cierran **antes** de la fase 1, con binarios y datos reales; cada una tiene su fallback
decidido (no abren preguntas nuevas):

1. **ASTAP `-wcs` / `-o` / `-update`**: comprobar con el binario real qué escribe cada opción y
   en qué formato (`-wcs` → fichero `.wcs` con tarjetas estilo astrometry.net de 80 bytes).
   *Fallback si no*: guardar el WCS en memoria directamente desde stdout/log.
2. **Dataset de EXOTIC**: verificar que los números publicados de HAT-P-32b
   (2458107.71406 ± 0,00097; Rp/Rs 0,1541 ± 0,0033) salen del set de 142 FITS
   (`EXOTIC_sampledata`). *Fallback si no*: usar otro dataset de EXOTIC como paridad y dejar
   HAT-P-32b como referencia documental.
3. **`pylightcurve` en Py3.12**: comprobar instalabilidad. *Fallback decidido*: `batman` como
   referencia de paridad de modelo (mismo criterio <1e-5, D27).
4. **`barycorrpy`**: opcional con `importorskip` en tests. *Fallback decidido*:
   `astropy.light_travel_time` no aplica (sin astropy), así que: valores dorados de referencia +
   tabla propia, con el residual <0,02 s documentado (D16).
5. **Tabla de bumeranes**: fijar embebida con su fecha de corte documentada y política de
   actualización (revisión manual con cada release).
6. **`lightcurve_widget._point_style`**: comprobar si ya soporta tres series (cruda, detrendada,
   marcada). *Fallback*: extenderlo en la fase 5 (ya estaba previsto).

---

## 6. Mapeo T1–T8 → fase → aceptación

| Pieza (PRECISION apéndice B) | Fase | Aceptación |
|---|---|---|
| **T1** Serie con punto cero por frame | 1, 2 | Prueba A/B: con ZP por frame una nube fina no deja señal; sin él, la deja |
| **T2** Ensemble ponderado con veto MAD | 2, 7 (arbitraje D29) | Comps sintéticas recuperadas; comp corrupta no mueve la mediana; arbitraje ponderada/suma por menor dispersión OOT |
| **T3** Apertura óptima por noche | 3 | Barrido `k ∈ [1,0; 2,0]·FWHM`: rms de la check mínimo; dos veings dan aperturas distintas |
| **T4** Ruido completo (centilleo + CCD) | 2, 3 | Error total ≥ interno siempre; centilleo incluido sobre el span del grupo |
| **T5** Detrending honesto | 3 | Dip 0,01 mag a ±0,001 mag intacto; seno 0,3 mag/2 h sin distorsionar; cruda siempre visible junto a detrendada |
| **T6** Tiempo a media exposición / HJD | 2 | Convención documentada; ExoClock con arranque (D19); `BJD_TDB` con residual <0,02 s medido |
| **T7** Gates de calidad por frame | 2, 5 | Saturación, salto de guiado, cósmico y nube **marcados** y nunca borrados; semáforo H6 dispara con nube simulada |
| **T8** Prácticas de observación | 5, 8, 10, 12 (doc) | `SEQUENCES` (ambos idiomas) explica defaults, flags y flujo con ejemplos; `PHOTOMETRY` gana la sección de prácticas |
| **Validación global** (`PRECISION:237`) | 7 | Serie sintética con dip 0,01 mag a ±0,001 mag; y con datos reales (p. ej. HD 209458 b) profundidad dentro del 10 % y rms de la check acorde al modelo de ruido |
| **C1** Suite verde con semilla | todas | `pytest tests/unit` verde al cerrar cada fase |
| **C2** Doc de usuario en ambos idiomas | 12 | `PHOTOMETRY` + `PRECISION` + `SEQUENCES`, sin `unfinished` en i18n |
| **C3** Flujos legacy intactos | todas | quicklook, blink, carta legacy y handoff EXOTIC sin tocar y verdes |
| **C4** Honestidad de errores y avisos | todas | total ≥ interno; los datos faltantes se dicen en lenguaje llano, no se callan |

---

## 7. Punto de entrada y siguientes pasos

**Punto de entrada**: rama `plan/series-photometry` → **fase 0**: firmar la revisión de
ADR-015, publicar ADR-048/049/050/051, cerrar el checklist de la sección 5 y actualizar
`PRECISION` línea 115. Nada de código hasta que eso esté firmado.

**Después**: fases 1→12 en orden, con la compuerta de la fase 7 (paridad con EXOTIC, umbrales
fijos: T_mid 3σ, Rp/Rs 5 %, σ 20 %) y la compuerta de la fase 11 (permiso explícito para la
API). Este documento vive solo en la rama de plan; la implementación arranca en una rama propia
de feature desde `main` una vez los ADRs de la fase 0 estén fusionados.

**Criterio de éxito final**: el usuario de un proyecto de tránsito, de una variable HADS o de
una SN en tres noches puede medir su serie desde la visita, leer una curva honesta (cruda y
detrendada, con flags y errores totales), deshacer una corrida mala, ajustar o plegar, exportar
para ExoClock y entender cada paso por la documentación de usuario, sin salir de NightScribe.
