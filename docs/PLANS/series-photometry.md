# Plan: fotometría de secuencias, detrend, ajuste de tránsito y ExoClock

*Plan de trabajo con todo lujo de detalles / Detailed working plan.*

- **Rama**: `plan/series-photometry` (creada desde `main` actualizado a `origin/main` 909ef1f).
- **Alcance**: piezas **T1–T8** de `docs/PRECISION.es.md` (apéndice B, líneas 202–241), más los
  apéndices separables (ASTAP, modo en vivo, API ExoClock) y la documentación de usuario.
- **Estado**: decisiones cerradas en conversación con el autor; la **fase 0** las convierte en
  ADRs firmados antes de escribir código (la nota de decisión del apéndice B de `PRECISION`
  exige firmar la reapertura de ADR-015 con el usuario).
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
EXOTIC como espejo de calidad y dejando su handoff como vía experta (D30). El estándar es el de
la sección «Validación» del apéndice B de `PRECISION`: una serie sintética con dip conocido de
0,01 mag recuperado a ±0,001 mag y, con datos reales, una profundidad dentro del 10 % con el rms
de la check acorde al modelo de ruido.

---

## 2. Decisiones firmadas con el autor

Se firman aquí y se convierten en ADRs en la fase 0 (D1, D2 con la reabertura de ADR-015;
D6, D7, D8, D9, D10, D11, D14, D15, D16, D17, D18, D19, D20, D21, D24, D25, D26, D27, D33,
D35, D36, D37, D38, D39; las fases 9, 10 y 11 viven en ADR-051, ADR-050 y ADR-049
respectivamente; D22, D23, D28, D29, D30, D31, D32, D40, D41, D42 y D43 quedan como decisiones
de implementación).

### Núcleo T1–T8

- **D1 · T1/T2 juntas: punto cero y comps por frame.** Cada frame se mide con su ZP propio y sus
  comps propias (ZP por frame, nunca fijo); cuando las comps útiles de un frame son <3, el
  fallback es un ZP interpolado de los frames vecinos de la propia ejecución (T2); nunca un ZP
  global fijado.
- **D2 · ADR-015 se reabre.** La vía numpy puro de NightScribe pasa a ser la primera de las dos;
  el handoff EXOTIC se conserva como la segunda (experta). El plan se rige por la sección
  «Validación» del apéndice B de `PRECISION` con umbrales fijos antes de codear (D38).
- **D3 · Medible y comparable.** NightScribe reporta **T_mid y la profundidad** con errores
  honestos: la curva son puntos con error total (D12), la profundidad de un tránsito conocido
  dentro del 10 % de la referencia, y **T_mid del ajuste de tránsito** (fase 7). La ejecución
  EXOTIC real del usuario sigue siendo la referencia de paridad de la fase 7.
- **D4 · Sin astropy.** `BJD_TDB` de EXOTIC no puede copiarse; NightScribe usa su propia
  `core/coords.py` / `ephem_minor.py` (schlyter) para BJD_TDB/TDB y HJD (D1).
- **D5 · Checklist por tipo, no genérico.** Transito: baseline y puntos por ingress;
  HADS: 12 puntos + tope de cadencia; variable: Nyquist + huecos. Un punto suelto sin serie solo
  avisa en la vista de Análisis (jamás calcula una profundidad por tipo: un punto suelto no es
  por sí un tránsito, D11).
- **D6 · Undo por ejecución, no por visita.** «Deshacer esta ejecución» borra los puntos de ese
  `run_id` (D9), sin tocar el resto de la visita.
- **D7 · Flags de calidad visibles y persistidos.** Cada punto guarda sus flags (T7) y la curva
  los pinta (forma/color distinto); en CSV/EFF van a `notes`/`comments` (D13). **Nunca se borra
  un punto por flag**.
- **D8 · Se trabaja desde la visita.** El flujo es: visita → ficheros de la visita → «Medir la
  secuencia». Sin visita no hay serie (regla D8 de la casa); desde un listado se llega con
  «Añadir ficheros a la visita» (D36), nunca con diálogo de carpeta suelto.
- **D9 · `run_id` de ejecución.** Cada «Medir» es una ejecución con su id; los puntos de la serie
  llevan ese id (junto a `session_id` de la visita) para Undo, auditoría y multinoche (D36).
- **D10 · Reuso del motor de placa.** T1 reutiliza el bloque `_measure`/`_calibrate_and_fill`
  de `gui/ufe_measure_tab.py` (y su extracción en `measure_plate` de la fase 1) para cada frame;
  no se escribe un segundo motor.
- **D11 · Motor agnóstico, tipos por parámetros.** Un solo `core/series_measure.py` paramétrico
  (tipo, forma esperada, cadencia, flags): un tránsito se lee con **T_mid + profundidad**; una
  variable con fase y periodo (plegado), no un único T_mid; una SN con noches y ascenso; HADS
  hereda sus flags H6 (D5). El tipo solo elige parámetros y checklist, no otro código (D39).
- **D12 · Errores honestos.** El error total ≥ el interno **siempre**; el semáforo H6 dispara
  con ruido de fondo simulado; la dispersión de la curva no esconde la incertidumbre.
  **Pruebas ancla** (semilla fija): (a) el dip de 0,01 mag del tránsito de referencia (rango
  típico de dips: 0,005–0,030 mag) se recupera dentro de ±0,001 mag **con** y **sin** detrend;
  (b) una curva con seno artificial de 0,3 mag / 2 h entra intacta (el detrend no la distorsiona);
  (c) la mediana de comps resiste una comp corrupta inyectada (ensemble + MAD, T2); (d) un punto
  con flag en rojo no mueve la mediana del conjunto; (e) una SN sobre el gradiente de su galaxia
  se recupera al 1 % en modo `relative` (la validación que también firma ADR-048).
- **D13 · Detrend simple, visible, sin columnas nuevas.** `a1·exp(a2·X)+a3` con `a1` analítico
  (la receta de EXOTIC, citada); `a2` libre con bounds `[-1;1]`; la salida son los tres
  coeficientes mostrados en el resumen y en `notes` del CSV; **no** se añaden columnas de
  parámetros al export (los coeficientes del detrend no son una variable física medible: añadir
  su columna sería ruido sobre la señal; regla de oro de T5: la cruda siempre visible).
- **D14 · Sin agrupación por defecto (group_n = 1).** Cada frame es un punto; la agrupación es
  opt-in y documentada (D19).
- **D15 · Tiempo a media exposición.** Cada punto lleva `T_mid = T_inicio + EXPTIME/2` como
  tiempo central, y `mjd`/`hjd` según política (D16); el `EXPTIME` de cada frame sale de
  `project_files.meta` vía `file_id` (ADR-047); la convención se documenta.
- **D16 · HJD/BJD_TDB propio, sin `barycorrpy`.** Se usa el código propio (Schlyter vía
  `ephem_minor.py`) para HJD/BJD_TDB; la tabla de segundos intercalares (UTC→TT) queda embebida
  con fecha de corte documentada (2026-09-27) y actualización manual con cada release. Si falta,
  valores de referencia *golden* + tabla propia, con residual <0,02 s documentado; `barycorrpy`
  es opcional (`importorskip`). El HJD de EXOTIC no puede copiarse (depende de astropy, ADR-004).
- **D17 · Sin astrometría por frame (por defecto).** El objetivo se toma de la referencia (WCS
  de una placa del set, o coords del proyecto); el centroide por frame se usa como señal de
  guiado (flag de salto), no como posición. El costo de la astrometría por frame en 3,000–5,000
  frames no paga el beneficio (D30: el handoff EXOTIC sigue siendo la vía experta). Cuando el
  set no trae WCS ni frames alineados (montura alt-az sin derotador, MicroObservatory),
  `SeriesConfig.align="similarity"` registra cada frame sobre el primero (rotación sobre el
  centro + traslación subpíxel, por Fourier, numpy puro; D44).
- **D18 · Esquema v12 (migración aditiva en `core/db.py`).** En `photometry_points` (la única
  tabla que almacena magnitudes): `mag_raw REAL`, `flags TEXT` y `run_id INTEGER NULL`; el
  `session_id` existente **sigue siendo la visita** y no se reusa como ejecución (es FK a
  `project_sessions` y `db.py` activa `PRAGMA foreign_keys = ON`: un id de ejecución ahí rompería
  la FK y el enlace punto→visita que necesita el multinoche, D36). Tabla nueva
  `measurement_runs(id, session_id, created, cfg_json, status)` con la configuración y el estado
  de la ejecución (`complete`/`incomplete`/`undone`); el Undo borra los puntos del `run_id` y marca
  la ejecución `undone` (auditoría, D9). Las filas legacy se conservan intactas; la vía
  `add_point` (punto suelto del UFE) mantiene el contrato de hoy: escribe con `flags=NULL`,
  `mag_raw=NULL` y `run_id=NULL`; no se toca ninguna otra tabla.
- **D19 · Agrupación (grouping, `group_n`).** Agrupa N frames para suavizar cadencias típicas
  (10–30 s, minutos si acaso); el tiempo es el centro del grupo; default por tipo = 1
  (transito y variable), configurable y documentado (D19 es una decisión de comodidad, no una
  necesidad física).
- **D20 · Cadencia por tipo (guardia en UI y en serie).** Transito: puntos por ingress
  (aviso, y rojo si se rompe); HADS: 12 puntos + tope de cadencia; variable: Nyquist. `group_n`
  no sustituye la cadencia; se avisa con texto llano, no se bloquea.
- **D21 · Modo en vivo = sondeo de carpeta.** No hace la app de «servidor»: un driver ligero
  observa la carpeta de la sesión, detecta FITS nuevo, mide en lote, actualiza la curva; se
  activa manualmente por sesión (ADR-050).
- **D22 · Export de serie = CSV con punto por frame.** El export de serie no genera el
  «punto suelto» de hoy (que sí hace la vía de un solo frame del UFE); la serie exportada es
  una tabla CSV/AAVSO con un punto por frame, con `notes` con flags y coefs.
- **D23 · Un solo punto suelto es una acción de una sola placa.** Medir «un punto suelto»
  (p. ej. una SN entre otras observaciones) usa la misma receta de placa (`measure_plate`) pero
  **sin** serie, sin agrupación y sin detrend: es H3 de `PRECISION`, no T1–T8. El motor de
  serie solo arranca con ≥2 frames y su checklist D20.
- **D24 · Reutilizar lo que ya existe.** La vista de Análisis
  (`main_window._analysis_transit_block`, `_fu_science_blocks`) consume la serie vía
  `lightcurve_data.build_payload` **extendido con el parámetro `source`** (hoy la firma es
  `(fu, sn_type_fallback, hads, variable)`; el parámetro se añade en la fase 6) y la dibuja con
  `lightcurve_widget` existente; el plegado (variables) y la comparación contra lo esperado
  (HADS) ocurren allí, no se reimplementa aquí; igual el punto suelto de hoy (pestaña
  Fotometría del UFE → `photometry_points`).
- **D25 · Facilidad de uso es requisito.** La serie se mide con un botón por visita, con
  defaults sensatos y avisos llanos; los knobs avanzados (aperturas, agrupación, detrend,
  sigma-clip, comp set) viven en el diálogo Avanzado y se pueden abrir sin miedo.
- **D26 · ASTAP como opción local a nova.** Selector auto / ASTAP / nova; fallback a nova si
  falta o falla; no toca el flujo de resolución (la regla nova se mantiene, ADR-051).
- **D27 · Paridad de modelo con EXOTIC (limb darkening).** El modelo de tránsito de la fase 7
  reproduce la curva de EXOTIC con <1e-5 de diferencia sobre el dataset de referencia
  (D27: el modelo de limb darkening de EXOTIC, implementado en numpy, sin `batman`/
  `pylightcurve` en producción; estas son solo referencia de test, `importorskip`).
- **D28 · Errores por bootstrap paramétrico (fallback del ajuste).** Si la covarianza de
  Gauss-Newton/LM no converge o da σ no fiables, se usa bootstrap paramétrico para el σ final;
  siempre mostrando el método usado (D12 honestidad).
- **D29 · Ensemble de comps: arbitraje ponderada vs suma.** Cuando hay >3 comps, NightScribe
  arbitra entre el ensemble ponderado (1/σ²) y la suma simple, eligiendo el de menor dispersión
  OOT en tránsitos o el de menor dispersión de la estrella check en el resto de tipos; si ambas
  son iguales, ponderada; el resultado se muestra en el panel. (Arbitraje T2, D5.)
- **D30 · Handoff EXOTIC sigue siendo la vía experta.** Nada cambia en el flujo de hoy (ADR-015
  actual); el plan añade por encima la vía numpy; el handoff se conserva.
- **D31 · Salida de serie = curva + punto por frame.** La «serie medida» no es un solo número:
  es la tabla de puntos (con flags, errores, coeficientes). El punto suelto se usa si el
  proyecto solo lo pide (D23), pero el flujo es serie → curva → export.
- **D32 · Umbral de profundidad: 10 % de referencia.** La profundidad del tránsito en la
  serie debe estar dentro del 10 % del valor de referencia (la ejecución EXOTIC de HAT-P-32b de
  la verificación 2; con datos propios, un tránsito conocido como HD 209458 b, sección 6); si
  no, se avisa en el semáforo (D12) y se deja el diagnóstico al usuario.

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
- **D36 · Multinoche: una ejecución por noche, agrega Análisis.** Cada noche es una ejecución con su
  `run_id` y su Undo independiente; la agregación por objetivo la hace la vista Análisis (ya
  existe vía `fu["points"]`); **binning solo de visualización** (el `time_bin` de EXOTIC, nunca
  altera datos) para series de decenas de miles de puntos; entrada de listados con acción «Añadir
  ficheros a la visita» (selección múltiple; **no** diálogo de carpeta: la regla D8 se mantiene).
- **D37 · Documento de usuario `SEQUENCES`.** Nueva pareja `docs/SEQUENCES.es.md` +
  `docs/SEQUENCES.md` (el «qué es y cómo se trabaja»; `PHOTOMETRY` sigue siendo las prácticas y
  `PRECISION` los números). El documento incluye la sección de ExoClock (fase 8) y la de en vivo
  (fase 10) desde el principio, progresivo por fases (5, 8, 10, 12), con botón «?» en el bloque
  de serie que lo abre en el visor de docs (que descubre los `.md` solo).
- **D38 · Compuertas con umbrales fijos.** Los umbrales de la fase 7 (y de la 11) se escriben
  **antes** de medir y **no se relajan para que un test pase**; si algo no pasa, se reporta y se
  actúa según el plan (vía handoff / cerrar apéndice), nunca ajustando el umbral hacia abajo.
- **D39 · Validación de tipos en este ciclo.** SN, variables y HADS de seguimiento, y el modo en
  vivo, se validan **ahora**, en este plan (pruebas sintéticas + dataset real), no «más tarde»:
  el motor es agnóstico (D11), así que validar un tipo es validar parámetros, no código nuevo.
- **D40 · Honestidad del modo `relative`.** Los puntos medidos con `zp_mode="relative"` (sin
  catálogo) quedan **bloqueados** para el export AAVSO EFF, que exige magnitud calibrada, con
  aviso en lenguaje llano; la cabecera del CSV declara el modo. ExoClock es la excepción
  natural: su formato es flujo relativo por definición (ADR-049).
- **D41 · Checklist ExoClock con semáforo, sin bloqueo.** Antes de exportar: baseline ≥1 h a
  cada lado, ≥3 puntos por ingress, sin flags rojos, dip coherente con la efeméride. Avisa, no
  bloquea (ADR-049).
- **D42 · API ExoClock = compuerta con permiso.** Solo se construye si existe un endpoint
  público documentado y el autor lo autoriza explícitamente; si no, la fase 11 se cierra
  documentando el envío manual de la fase 8 (ADR-049).
- **D43 · Presupuesto de rendimiento.** <0,5 s por frame y UI responsive con la serie de 142
  frames (el dataset de EXOTIC); es referencia para afinar, no compuerta (D38).
- **D44 · Alineación por frame (opt-in).** Para sets sin WCS ni frames alineados,
  `core/register.py` estima la similitud (rotación sobre el centro + traslación subpíxel) por
  correlación de fase (numpy puro, sin scipy/astropy) y remuestrea cada frame a la rejilla de
  referencia; `SeriesConfig.align="similarity"` lo activa. Por defecto apagado (D17): la serie
  asume frames alineados y resueltos. Nace de la compuerta real de la fase 7 sobre el set
  MicroObservatory de EXOTIC, cuyos frames se trasladan y rotan.

---

## 3. Alcance: núcleo y apéndices

| Bloque | Fases | Qué incluye | Si hay que recortar |
|---|---|---|---|
| **Núcleo T1–T8** | 0–8 | ADRs, `measure_plate`, motor, detrend, migración v12, worker+UI, visitas/multinoche, ajuste de tránsito, ExoClock manual | **No se recorta**: es lo que firma PRECISION |
| Apéndice A | 9 | Solver local ASTAP | Se aplaza al final |
| Apéndice B | 10 | Modo en vivo | Se aplaza |
| Apéndice C | 11 | API ExoClock | Depende de permiso y de endpoint (D42) |
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
- **Por qué**: la nota de decisión del apéndice B de `PRECISION` exige firmar la reapertura de
  ADR-015 antes de código; los
  ADRs nuevos fijan el marco (48 serie, 49 ExoClock, 50 en vivo+agrupación, 51 ASTAP) para que
  las fases siguientes no reabran discusiones.
- **Implementación**: revisión de `docs/adr/ADR-015-exoplanets.md` (estado: reabierto; la vía
  numpy pasa a ser la primera, el handoff queda como vía experta); cuatro ADRs nuevos en
  `docs/adr/` y entrada en `docs/adr/README.md`; este documento ya está escrito
  (`docs/PLANS/series-photometry.md`, con su **PUNTO DE ENTRADA** en la sección 7); la fila de
  T1–T8 de la tabla «Qué es hoy qué» de `docs/PRECISION.es.md` y su par inglés ya quedó
  actualizada («En curso: piezas T1–T8…»), solo hay que verificarla; cerrar el checklist de la
  sección 5 con el resultado de cada verificación y su fallback ya elegido.
- **Tests**: revisión de enlaces de docs y del ADR README (hoy no hay test automático de
  enlaces; si se quiere, se añade uno simple que recorra los `.md`); ningún código se toca.
- **Salida limpia**: ADR-015 revisado y firmado por el autor; los 4 ADRs nuevos (048–051)
  publicados; checklist cerrado; el plan no deja preguntas abiertas antes de la fase 1.

### Fase 1 · `measure_plate`: extraer la receta de la placa

- **Decisiones**: D10, D25.
- **Por qué**: la receta completa de medida vive hoy en la GUI
  (`gui/ufe_measure_tab.py`: bloque `_measure`/`_calibrate_and_fill`, y el área de export
  CSV/EFF en `_export`). La serie necesita llamarla sin GUI y sin duplicarla; dos recetas
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
  frame con ensemble (T1–T2, reutilizando `measure_plate`), ensemble ponderado
  con veto MAD por frame (T2), puertas por frame (T7: saturación, `guide_jump` por centroide
  sobre la placa de referencia, cósmico sigma-clip local, ZP outlier/nube; **marcado, nunca
  borrado**), error total por punto (T4, con `scintillation_mag` sobre el span), instante a
  media exposición y `mjd`/`hjd` con la convención del D16. Sin astrometría por frame (D17).
  Progreso y cancelación al estilo de `SequenceWorker` en `gui/workers.py`.
- **Tests**: `tests/unit/test_series_measure.py` con las anclas del D12 que no necesitan detrend
  ((a) sin detrend, (c), (d) y (e)) y semillas fijas; referencia de rendimiento (142 frames
  sintéticos <0,5 s/frame; referencial para afinar, no compuerta: D43); test de cancelación
  (estado «serie incompleta», persistido en `measurement_runs.status`, D18).
- **Salida limpia**: motor usable desde tests y CLI; la GUI todavía no expone la acción.

### Fase 3 · T3 y T5: apertura óptima y detrend honesto

- **Decisiones**: D13, D25, D34.
- **Por qué**: T3 (apertura por noche) y T5 (detrend) son donde la curva se ganan o se pierde el
  rms; y el detrend mal construido se come señal (la regla de oro de T5 de `PRECISION`).
- **Implementación**: barrido de `k ∈ [1,0; 2,0]·FWHM` por noche eligiendo el que minimiza el
  rms de la check (con FWHM por frame, para que las defensas de guiado no rompan la curva);
  `detrend_series(...)` con `a1·exp(a2·X)+a3` y `a1` **analítico** (EXOTIC), política por capas:
  `off` (curva cruda), `airmass` (mínimo honesto), `auto` (añade FWHM/cielo/x-y solo si el rms
  del residuo baja al menos un 10 %; umbral fijo, mostrado en el panel). En multinoche,
  coeficientes por noche con fallback
  `a1`-solo (D34). Salida en tres sitios: panel de resumen, columna `notes` del CSV, meta de la
  serie (D13: sin columnas nuevas). La pestaña pinta **cruda + detrendada** con la leyenda
  explicando que el detrend puede comerse señal.
- **Tests**: las anclas (a) **con** detrend y (b) del D12 (el dip no se mueve con el detrend; el
  seno no se distorsiona), la prueba A/B de dos noches con transparencia desplazada un 3 %
  (plana con detrend por noche, salta sin él) y el fallback de noche corta.
- **Salida limpia**: curva cruda y detrendada con coeficientes a la vista; nada de magia.

### Fase 4 · Migración v12

- **Decisiones**: D18, D7 (flags persistidos), D9 (`run_id`).
- **Por qué**: los puntos de serie necesitan su crudo (`mag_raw`) y sus puertas (`flags`)
  **sin** tocar el resto del esquema ni romper el flujo de puntos existentes de las visitas.
- **Implementación**: en `core/db.py` (`_migrate`, tras la v11): `mag_raw REAL`, `flags TEXT` y
  `run_id INTEGER NULL` en `photometry_points`, más la tabla nueva `measurement_runs(id,
  session_id, created, cfg_json, status)` (D18); helpers `add_points(db, rows)` en lote y
  `delete_points(db, ids)` en `core/followup.py` (junto a `add_point`, `list_points`,
  `delete_points_for_file`), más `create_run`/`set_run_status` para la tabla de ejecuciones; la
  migración es idempotente y avisa si el esquema viene de otra versión conocida.
- **Tests**: `tests/unit/test_db_v12.py`: migración desde v11 y desde esquema limpio, idempotencia,
  escritura en lote + `delete_points` por `run_id` (el «deshacer» de una ejecución sin tocar otras)
  y puntos legacy con su `session_id` de visita intacto.
- **Salida limpia**: bases existentes actualizan sin pérdida; los flujos de puntos de hoy no se
  enteran.

### Fase 5 · Worker + interfaz de la serie

- **Decisiones**: D6, D7, D8, D9, D20 (guardia en la UI), D25, D37 (mitad del documento
  `SEQUENCES`).
- **Por qué**: sin este punto, el motor no es un producto; el usuario debe poder medir la serie
  de su visita con progreso, semáforo, flags explicados y «Deshacer esta ejecución» a un clic.
- **Implementación**:
  - `gui/workers.py`: `SeriesWorker` (patrón `SequenceWorker`: QThread, señales de progreso,
    cancelación, `notify_points` por lote hacia `ufe_dialog.set_point_hook`/`notify_point`,
    extendidos para aceptar batch y `run_id`).
  - `gui/ui/ufe_measure_tab.ui` (ADR-005): bloque de secuencia (botón «Medir la secuencia»,
    contador de frames, control de agrupación con su texto de cadencia, progreso, botón
    «Deshacer esta ejecución», botón «?»). El botón se oculta si la pestaña no tiene visita (D8).
  - `LightCurveChart` compacto embebido en la pestaña (placeholder `QWidget` +
    `replaceWidget`): cruda + detrendada, puntos con flag en color y forma distintos
    (hay que extender `lightcurve_widget._point_style`: hoy solo distingue
    survey/quicklook/manual por `source`; verificación 6 cerrada),
    leyenda por noche en multinoche, decimación de visualización (D36).
  - `gui/ufe_advanced_dialog.py` + `.ui` ampliados con los knobs de serie (aperturas, `group_n`,
    política de detrend, ventana de sigma-clip, techo de saturación), cada uno con default
    visible, tooltip con unidades y razón, y «restaurar default» (D25). Los knobs de **sitio**
    (ganancia, RON, diámetro, altura, centilleo) van a Configuración (ADR-028), que ya tiene
    `edt_astrometry_key` como referencia de dónde vive.
  - Textos con `tr()`; el botón «?» abre `SEQUENCES` en el visor de docs (D37).
- **Tests**: `tests/unit/test_ufe_measure_tab.py` ampliado (señales, ocultación del botón sin
  visita, undo), test offscreen del worker con serie sintética, test de que la serie cancelada
  deja el estado «incompleta», test de que el export EFF bloquea puntos en modo `relative` con
  aviso llano (D40), i18n sin `unfinished`.
- **Salida limpia**: flujo completo en la GUI: visita → Medir → progreso → curva → flags →
  deshacer; app funcional y legacy intacto.

### Fase 6 · Visitas, proyecto y multinoche

- **Decisiones**: D20, D24, D35, D36, D8 (entrada de listados).
- **Por qué**: es donde las tres misiones de uso (tránsito, variable, SN multinoche) se
  conectan al análisis existente; sin esta fase, la serie sería un adorno sin análisis.
- **Implementación**:
  - `gui/widgets/visits_panel.py`: acción nueva «Medir la secuencia» en la ventana de la visita
    (handler nuevo, p. ej. `_on_measure_series_clicked`; el `_on_measure_clicked` actual abre
    una medida suelta y no se toca), que arranca la serie de la visita (no de una carpeta), y la
    nueva acción «Añadir ficheros a la visita» (selección múltiple) para
    llegar ahí desde un listado (D36).
  - Cada noche = una ejecución con su `run_id` y su Undo; en la curva, línea/leyenda por noche.
  - Análisis (`main_window._analysis_transit_block`, `_fu_science_blocks`,
    `_fu_export_report`): la serie entra en el plegado (variables) y la comparación contra el
    esperado (HADS/SN) vía `lightcurve_data.build_payload`, extendido en esta fase con el
    parámetro `source` (`source="measure"`), **sin reimplementar nada** más (D24/D33).
  - Guardia de cadencia (D20) al crear la serie: aviso con las reglas del tipo (tránsito: puntos
    por ingress; HADS: 12 puntos y tope de cadencia; variable: Nyquist); rojo si se rompe el
    ingress; `group_n=1` por defecto en tránsitos y variables.
  - Multinoche: chequeo de ZP por noche y guardia de banda (D35) en el panel de resumen.
- **Tests**: serie sintética de dos noches (agregación, undo por ejecución sin tocar la otra,
  aviso de banda mezclada, aviso de ZP desplazado), test de `build_payload(source="measure")`
  con plegado de una variable sintética, test de la guardia de cadencia (aviso y rojo).
- **Salida limpia**: la curva medida vive en el proyecto, se analiza como las demás y el flujo
  de visitas no cambia de comportamiento.

### Fase 7 · Ajuste de tránsito (COMPUERTA)

> **⚠ PENDIENTE (para retomar cuando lo indique el autor): mejorar la fotometría real de la
> fase 7.** La compuerta EXOTIC queda **abierta** por precisión del dato (σ por punto de
> decenas de mmag frente a un tránsito de 26 mmag), no por el motor de ajuste. Trabajo acordado
> para después: aperturas/PSF adaptadas, blend del binario, tratamiento de saturación y
> precisión del registro; ver el «Resultado» al final de esta fase.

- **Decisiones**: D1, D2, D27, D28, D29, D38.
- **Por qué**: T5+T7 dan la curva; el usuario de tránsitos necesita T_mid, profundidad y
  errores, dentro de la app, con la calidad de EXOTIC y sin su stack.
- **Implementación**: `core/transit_fit.py`:
  - Modelo: tránsito cuadrático con limb darkening de Claret (D27), efemérides de
    `core/transits.py` como semilla (T0 + n·P), parámetros `rprs`, `tmid`, `a/R*` (o duración
    equivalente) y baseline local. Los coeficientes de limb darkening (u1, u2) salen de una
    rejilla de Claret embebida, interpolada con los parámetros estelares de la ficha del
    planeta (NASA Archive, ya en caché vía el handoff de `core/exotic.py`), editables a mano;
    el panel declara siempre su origen.
  - Ajuste: Gauss-Newton/LM en numpy con jacobiano analítico (sin scipy), bounds como en EXOTIC:
    `rprs ∈ [0; 1,25·prior]`, `tmid ± 25σ` con tope `±P/4`, `a2 ∈ [-1; 1]`; sigma-clip de 25–30
    min por `lstsq` deslizante; errores desde la dispersión OOT (no de la covarianza interna
    sola); diagnósticos: `quality` (χ² reducido), duración **medida vs esperada**, y parámetros
    con sus σ.
  - Detrend conjunto `a1·exp(a2·X)` durante el ajuste (el mismo del D13, reutilizado).
  - Entrada desde Análisis (`_analysis_transit_block`), para proyectos de tipo tránsito; para
    SN y variables el motor no se toca (D11).
  - **Compuerta**: paridad con EXOTIC sobre su dataset real (ver verificación 2): **T_mid dentro
    de 3σ combinados** (cuadratura de la σ de EXOTIC y la nuestra), **Rp/Rs dentro de 5 %**,
    **σ de parámetros dentro de 20 %** (si no, D28:
    bootstrap paramétrico), profundidad de la muestra conocida dentro del 10 %
    (D32) y rms de la check acorde al modelo de ruido. Umbrales fijados en el
    ADR-015 revisado **antes** de medir (D38).
- **Tests**: `tests/unit/test_transit_fit.py` con el dataset sintético de semilla, la paridad de
  modelo D27 (<1e-5 vs `pylightcurve` o, si no instala, vs `batman`, verificación 3) y la suite
  funcional con datos reales; los umbrales se escriben como constantes citadas.
- **Salida limpia (o compuerta cerrada)**: si la paridad pasa, la fase 8 arranca sobre ese
  ajuste; si no, se reporta el resultado, **no se relaja el umbral** (D38), y el ajuste sigue la
  vía handoff a EXOTIC mientras se diagnostica. En ningún caso queda la app rota.
- **Resultado (2026-09-27)**: la **paridad de modelo D27 pasa** (numpy vs `batman` en modo
  cuadrático, <1e-5; de hecho ~1e-9) y el ajuste recupera tránsitos sintéticos. La **compuerta
  end-to-end con EXOTIC no pasa**: el set MicroObservatory (142 FITS, sin WCS) se traslada y rota
  entre frames; con la alineación nueva (D44/`core/register.py`) la serie sale completa
  (142/142) pero la fotometría diferencial queda ruidosa: σ ≈ 40–180 mmag según la configuración,
  con saturados a 4095 ADU y sin flats. El mejor ajuste (sin binar) da Rp/Rs = 0,186 (21 % alto)
  y T_mid 439 s antes de la referencia; binar agrava la señal sistemática. El límite es el dato,
  no el ajuste: con una profundidad de 26 mmag y σ por punto de decenas de mmag, ninguna
  implementación alcanza el 5 % en Rp/Rs ni el 3σ en T_mid. **No se relajan los umbrales**;
  la compuerta queda **abierta** y el handoff a EXOTIC sigue siendo la vía experta. Diagnóstico
  apuntado: apertura/PSF y blend del binario, flats inexistentes en el set y precisión de la
  alineación, antes que el motor de ajuste (que es correcto).

### Fase 8 · ExoClock

- **Decisiones**: D30, D31, D37 (sección ExoClock de `SEQUENCES`).
- **Por qué**: el usuario mide tránsitos para enviarlos a ExoClock, y hoy el camino termina en
  un CSV genérico; además, EXOTIC **no** sube a ExoClock, así que este puente es nuestro valor
  añadido.
- **Implementación**: `core/exoclock_export.py`:
  - Archivo de 3 columnas (JD_UTC de **arranque** de exposición, flujo relativo, error), con la
    media de los comps en el denominador (convención HOPS) y, con agrupación, arranque = media −
    integración total/2 (D19). El arranque de cada punto es su `mjd` (media exposición, D15) −
    EXPTIME/2, con el EXPTIME de `project_files.meta` vía `file_id` (ADR-047); un punto sin
    EXPTIME bloquea el export con aviso llano.
  - `ExoClock_info.txt`: Planeta, Time format JD_UTC, Time stamp Exposure start, Flux format
    Flux, Filter, Exposure time, Comments prefilled (autocalificación honesta y, si procede, la
    nota de agrupación).
  - Checklist con semáforo (D41) antes del botón; botón que genera ambos ficheros y abre
    `https://exoclock.space/upload/` en el navegador; al confirmar en la app, outcome
    `reported_exoclock` en el proyecto (`core/project.py:62`, ya existe el estado).
  - Sin credenciales, sin scraping, sin peticiones (la fase 11 mira si algún día hay API: D42).
- **Tests**: `tests/unit/test_exoclock_export.py`: número de columnas y de filas, JD de arranque
  con y sin agrupación, contenido del `info.txt`, campo Comments no vacío, outcome del proyecto,
  y que un punto sin EXPTIME bloquea el export con aviso (D15).
- **Salida limpia**: el usuario puede preparar y enviar su observación a ExoClock a mano, con el
  checklist avisándole si va a mandar algo flojo.

### Fase 9 · ASTAP (apéndice A)

- **Decisiones**: D26.
- **Por qué**: tener un solver local evita la clave de Astrometry.net para series en vivo y
  reduces puntos sin WCS (D17), sin renunciar a nova.
- **Implementación**: `core/sources/astap.py` (`solve(path, progress) -> cards|None`, mismo
  contrato y claves `_WCS_KEYS` que `core/sources/astrometry.py`), `core/solve.py` (módulo
  nuevo: dispatcher `solver=auto|astap|astrometry`, `astap_path`, caché por hash+backend), ajustes en
  `gui/ui/settings_dialog.ui` (`cmb_solver`, `edt_astap_path` con Examinar, botón «Probar»,
  `chk_astap_update`), WCS en memoria desde el lado `-wcs` parseado con `fits_io.read_header`,
  `-update` opcional y solo desde el botón Solve del UFE (`ufe_dialog._on_solve`), hints `-fov`
  (de `pixel_um`/`focal_mm`), `-ra`, `-spd`; integración con `core/blink.merge_solved_wcs`.
- **Tests**: contrato con un binario simulado (fijo de tarjetas), fallback a nova si ASTAP falla
  o no está, caché (segunda llamada no ejecuta nada), mensajes bilingües.
- **Salida limpia**: sin ASTAP instalado, todo funciona como hoy (auto → nova → aviso).

### Fase 10 · Modo en vivo (apéndice B)

- **Decisiones**: D21, D33 (un solo motor), D17 (anotación sin WCS), D19 (agrupación compone).
- **Por qué**: en directo con el telescopio, el usuario quiere ver la curva formarse; y sus
  ficheros aún no están resueltos.
- **Implementación**: driver de sondeo (~2 s) sobre la carpeta de la sesión, chequeo de
  estabilidad de tamaño antes de leer, mismos commits agrupados (5 frames o 10 s) y
  `notify_points` por lote hacia la curva embebida; el driver cierra un punto cuando el grupo se
  completa (N tomas o T segundos); entrada y salida por el mismo worker/curva que la fase 5 (un
  solo motor, D33).
- **Tests**: carpeta sintética que crece (offline), detección de fichero a medias, agrupación en
  vivo, y cancelación sin dejar ejecución colgada.
- **Salida limpia**: en vivo apagado por defecto; activarlo es opt-in y no cambia el flujo normal.

### Fase 11 · API ExoClock (compuerta con permiso)

- **Decisiones**: D42, D38.
- **Por qué**: solo si algún día ExoClock publica endpoint de subida (hoy no existe, verificado)
  y el autor lo autoriza, tiene sentido automatizar.
- **Implementación (condicionada)**: si hay endpoint documentado y permiso: cliente en
  `core/sources/exoclock.py` con red solo vía `core/db.py`, credenciales en clave del sistema
  (nunca en la base ni en el repo), reutilizando el export de la fase 8 como payload. Si no:
  se documenta en `SEQUENCES` y en ADR-049 que el envío es manual (salida de fase igualmente
  limpia).
- **Tests**: solo si se construye: contrato con endpoint simulado, sin secretos en tests.
- **Salida limpia**: el plan cierra este apéndice en cualquier caso, con su porqué escrito.
- **Resultado (2026-09-27)**: verificado que **no existe** endpoint público de subida
  (`/api/` responde 404; `/upload/` tras login + CSRF y con robots.txt que prohíbe el scraping;
  el paquete `exoclock` de PyPI es solo lectura) y el autor no ha autorizado una API. El
  apéndice se **cierra documentando** el envío manual de la fase 8 (ADR-049 y `SEQUENCES`); no
  se construye cliente alguno. Si algún día aparece endpoint y permiso, la fase 8 sirve de
  payload sin cambios.

### Fase 12 · Documentación, i18n y WORKFLOWS

- **Decisiones**: D37, y el criterio global C2 del apéndice C de `PRECISION`.
- **Por qué**: la facilidad de uso es requisito del plan (D25), y `PRECISION` exige que la doc
  de usuario explique cada pieza con un ejemplo en ambos idiomas.
- **Implementación**:
  - `docs/SEQUENCES.es.md` + `docs/SEQUENCES.md` completos (secciones 1–9: qué es; tipos;
    desde dónde se trabaja; flujo paso a paso; mandos y defaults; cuándo fiarse; multinoche;
    solución de problemas; glosario y enlaces). Las secciones de ExoClock y en vivo se añadieron
    en las fases 8 y 10 (D37 es progresivo).
  - `docs/PHOTOMETRY.es.md`/`.md`: sección **T8** (flats a nivel mmag, dithering, desenfoque
    leve deliberado, cadencia constante, nada saturado).
  - `docs/PRECISION.es.md`/`.md`: T1–T8 pasan a «hecho» en la tabla «Qué es hoy qué», C1–C4
    revisados (C2 suma `SEQUENCES`).
  - `docs/WORKFLOWS.es.md`/`.md`: enlaza `SEQUENCES` como el «cómo» del flujo de proyecto;
    `docs/adr/README.md` con los ADRs nuevos.
  - i18n: `lupdate` + traducción, sin `unfinished` (ADR-014).
- **Tests**: docs sin enlaces rotos (los `.md` locales navegan en el visor), i18n limpio, suite
  completa verde.
- **Salida limpia**: fin del plan: T1–T8 completos y documentados en ambos idiomas.
- **Resultado (2026-09-27)**: `docs/SEQUENCES.es.md` + `docs/SEQUENCES.md` publicados (12
  secciones, incluida ExoClock y modo en vivo); `PHOTOMETRY` gana la sección 8.1 (T8);
  `PRECISION` marca T1–T8 como hechos (con la compuerta EXOTIC end-to-end abierta y el detalle en
  la fase 7) y C2 suma `SEQUENCES`; `WORKFLOWS` enlaza `SEQUENCES` como el «cómo» del flujo de
  proyecto; i18n sin `unfinished`. Queda **pendiente de retomar** la mejora de la fotometría real
  de la fase 7 (marcada arriba).

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
4. **`barycorrpy`**: opcional con `importorskip` en tests. *Fallback decidido*: valores
   *golden* de referencia + tabla propia, residual <0,02 s documentado (D16).
5. **Tabla de segundos intercalares (UTC→TT)**: fijarla embebida con su fecha de corte
   documentada (2026-09-27) y política de actualización (revisión manual con cada release).
6. **`lightcurve_widget._point_style`**: **verificado 2026-09-27**: hoy solo distingue
   `survey`/`quicklook`/`manual` por `source`; no soporta flags ni tres series. *Fallback
   (elegido)*: extenderlo en la fase 5, como estaba previsto.

---

## 6. Mapeo T1–T8 → fase → aceptación

| Pieza (PRECISION apéndice B) | Fase | Aceptación |
|---|---|---|
| **T1** Serie con punto cero por frame | 1, 2 | Prueba A/B: con ZP por frame una nube fina no deja señal; sin él, la deja |
| **T2** Ensemble ponderado con veto MAD | 2, 7 (arbitraje D29) | Comps sintéticas recuperadas; comp corrupta no mueve la mediana; arbitraje ponderada/suma por menor dispersión OOT (D29); si las comps del frame son <3, fallback al ensemble por frame (D1) |
| **T3** Apertura óptima por noche | 3 | Barrido `k ∈ [1,0; 2,0]·FWHM`: rms de la check mínimo; dos seeings dan aperturas distintas |
| **T4** Ruido completo (centilleo + CCD) | 2, 3 | Error total ≥ interno siempre; centilleo incluido sobre el span del grupo |
| **T5** Detrending honesto | 3 | Dip 0,01 mag a ±0,001 mag intacto; seno 0,3 mag/2 h sin distorsionar (D12); cruda siempre visible junto a detrendada |
| **T6** Tiempo a media exposición / HJD | 2 | Convención documentada; ExoClock con arranque (D19); `BJD_TDB` con residual <0,02 s medido |
| **T7** Gates de calidad por frame | 2, 5 | Saturación, salto de guiado, cósmico y nube **marcados** y nunca borrados; semáforo H6 dispara con nube simulada |
| **T8** Prácticas de observación | 5, 8, 10, 12 (doc) | `SEQUENCES` (ambos idiomas) explica defaults, flags y flujo con ejemplos; `PHOTOMETRY` gana la sección de prácticas |
| **Validación global** (`PRECISION`, apéndice B, «Validación») | 7 | Serie sintética con dip 0,01 mag a ±0,001 mag; y con datos reales (p. ej. HD 209458 b) profundidad dentro del 10 % y rms de la check acorde al modelo de ruido |
| **C1** Suite verde con semilla | todas | `pytest tests/unit` verde al cerrar cada fase |
| **C2** Doc de usuario en ambos idiomas | 12 | `PHOTOMETRY` + `SEQUENCES`; la doc de usuario explica cada pieza con un ejemplo en ambos idiomas (`PRECISION`, criterio C2 del apéndice C), sin `unfinished` en i18n |
| **C3** Flujos legacy intactos | todas | quicklook, blink, carta legacy y handoff EXOTIC sin tocar y verdes |
| **C4** Honestidad de errores y avisos | todas | total ≥ interno; los datos faltantes se dicen en lenguaje llano, no se callan |

---

## 7. Punto de entrada y siguientes pasos

**Punto de entrada**: rama `plan/series-photometry` → **fase 0**: firmar la revisión de
ADR-015, publicar ADR-048/049/050/051, cerrar el checklist de la sección 5 y actualizar
`PRECISION` (la fila de T1–T8 de «Qué es hoy qué»). Nada de código hasta que eso esté firmado.

**Estado al 2026-09-27**: la fase 0 ya está escrita en el árbol de trabajo (ADR-015 revisado y
firmado, ADR-048–051, `docs/adr/README.md`, la fila de T1–T8 de `PRECISION` y `AGENTS.md`
actualizados); queda fusionarla en la rama. La verificación 6 del checklist ya está cerrada
(hay que extender `_point_style`); las verificaciones 1–5 siguen pendientes de binarios y datos
reales. Fases 1–6 implementadas y verdes. La fase 7 tiene el modelo y el ajuste hechos y la
**paridad de modelo D27 cerrada** (<1e-5 vs batman), pero la **compuerta end-to-end con EXOTIC
queda abierta**: el set sin WCS exige alineación por frame (D44) y, aun así, la fotometría
sobre esos frames rota/saturados no alcanza la tolerancia; umbrales sin relajar y handoff
EXOTIC como vía experta (detalle en la fase 7).

**Después**: fases 1→12 en orden, con la compuerta de la fase 7 (paridad con EXOTIC, umbrales
fijos: T_mid 3σ, Rp/Rs 5 %, σ 20 %) y la compuerta de la fase 11 (permiso explícito para la
API). Este documento vive solo en la rama de plan; la implementación arranca en una rama propia
de feature desde `main` una vez los ADRs de la fase 0 estén fusionados.

**Criterio de éxito final**: el usuario de un proyecto de tránsito, de una variable HADS o de
una SN en tres noches puede medir su serie desde la visita, leer una curva honesta (cruda y
detrendada, con flags y errores totales), deshacer una ejecución mala, ajustar o plegar, exportar
para ExoClock y entender cada paso por la documentación de usuario, sin salir de NightScribe.
