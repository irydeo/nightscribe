# Plan: orquestación de EXOTIC para tránsitos de exoplanetas

*Plan de trabajo detallado. Sustituye el objetivo científico de la fase 7 de
`docs/PLANS/series-photometry.md`.*

- **Rama sugerida**: `feat/exotic-orchestration` (desde `main` con el trabajo de
  series ya fusionado).
- **Decisión de partida**: **opción A**: para el flujo científico de tránsitos,
  NightScribe **orquesta EXOTIC** (lo ejecuta como herramienta externa y lee su
  salida) en lugar de intentar igualar su reducción con numpy puro. Cambia la
  reapertura de **ADR-015**: la vía numpy deja de ser «la primera» y pasa a
  **previsualización**; la vía EXOTIC pasa a **principal**.
- **Estado previo relevante**: el motor de serie (`core/series_measure.py`), el
  ajuste de tránsito numpy (`core/transit_fit.py`, paridad de modelo D27 cerrada
  <1e-5 vs batman) y el handoff `inits.json` (`core/exotic.py`) ya existen.
  La compuerta end-to-end con EXOTIC de la fase 7 quedó **abierta por precisión
  del dato**: nuestra reducción sobre los 142 FITS de MicroObservatory (sin WCS,
  frames que se trasladan y rotan, saturados) no llega a los milimagns.
- **Regla de estilo**: español con «:», «,» y «;»; la semirraya «–» solo para
  rangos numéricos. Código e identificadores en inglés (AGENTS.md).

---

## 1. Objetivo y alcance

Objetivo: que un proyecto de **tránsito** pueda, desde la app, generar el
`inits.json` de la visita, ejecutar EXOTIC en un entorno Python ≤3.10 externo
que el usuario instale, e **importar de vuelta** la curva y los parámetros
ajustados (T_mid, Rp/Rs, errores) al proyecto, cerrando el ciclo sin copiar
código de EXOTIC.

Dentro del alcance:

- Preparación/validación del entorno EXOTIC (Ajustes + worker).
- `inits.json` completo para la visita (tomas, objetivo y comparaciones).
- Ejecución headless de EXOTIC con log, cancelación y timeout.
- Importación del resultado (curva + parámetros + figuras) al proyecto.
- UI: botón, semáforo, estado; la vía numpy queda como previsualización.
- Redefinición de la compuerta D27/D38 y actualización de ADR-015 y del plan.
- Documentación de usuario y tests (con EXOTIC simulado).

Fuera del alcance:

- Empaquetar EXOTIC dentro del instalador de Windows (lo instala el usuario).
- Copiar o portar código de EXOTIC.
- Sustituir la vía numpy (se conserva como previsualización y para quien no
  tenga EXOTIC).

---

## 2. Fase 0 · Verificaciones (antes de código)

Cada una con fallback decidido; se cierran con EXOTIC real instalado en un venv
`python3.10` (en esta máquina existe `/usr/bin/python3.10`).

1. **Invocación headless**: cómo se corre EXOTIC sin GUI leyendo `inits.json`.
   Candidatos a probar: `python -m exotic` (con el `inits.json` presente en el
   directorio de trabajo), un runner propio que importe su API
   (`from exotic import ...`) con el `inits.json`, y las variables de entorno /
   flags que eviten el asistente. *Fallback*: si EXOTIC exige interacción,
   detectar los prompts y alimentarlos por `stdin`, o dejar la ejecución como
   documentada manual y limitar la orquestación a generar inits + importar la
   carpeta de salida que el usuario produzca a mano.
2. **Salidas de EXOTIC**: localizar y fijar la estructura de su carpeta de
   salida (curva normalizada, `FinalLightCurve_*.csv`, log con T_mid/Rp/Rs y
   sus incertidumbres, PNG). *Fallback*: parsear solo lo que exista (curva y
   log) y dejar el resto como documental.
3. **Entorno**: `python3.10 -m venv` + `pip install exotic`; comprobar que el
   import funciona y su versión. *Fallback*: usar un intérprete que el usuario
   ya tenga (`exotic_python_path`).
4. **Datos de EXOTIC que falten**: qué campos del `inits.json` son obligatorios
   y cuáles podemos dejar `null` (hoy se dejan varios). *Fallback*: rellenarlos
   a mano en el asistente y documentarlo.

Salida limpia: EXOTIC corre de punta a punta sobre el set de prueba (los 142 FITS
de MicroObservatory o el pre-reducido) desde línea de comandos y produce su
curva y sus parámetros.

### Resultado de la fase 0 (verificado 2026-09-27)

- **Entorno**: `python3.10 -m venv --without-pip <dir>` + `python3.10 -m pip
  --python <dir>/bin/python install exotic` (el `ensurepip` de este sistema está
  roto: `No module named ensurepip`). Queda `exotic` 4.3.1 con astropy, scipy,
  pylightcurve, ultranest, astroalign, LDTk, barycorrpy, etc.
- **Invocación headless**: `<dir>/bin/exotic -red <inits.json> -ov < /dev/null`
  desde el directorio de trabajo. El flag **`-ov/--override`** evita el prompt de
  «tus parámetros vs NASA Archive» (sin él, `check_parameters` pide 1 o 2 y
  revienta con EOFError al no haber terminal). Modos: `-red` (reducción
  completa), `-phot` (solo fotometría), `-pre` (pre-reducido), `-rt` (en vivo).
- **Inits fiables headless**: en `user_info`, **`"Add Comparison Stars from
  AAVSO? (y/n)" = "n"`** con las comparaciones dadas en píxeles
  (`"Comparison Star(s) X & Y Pixel"`); con «y», `vsp_query` a AAVSO devolvió
  HTML y EXOTIC murió con `JSONDecodeError`. `"Plate Solution? (y/n)"` puede
  quedarse en "y". `"Pre-reduced File:"` a `null` en modo `-red`.
- **Red**: NASA Exoplanet Archive, datos LDTk (se cachean tras la primera
  ejecución) y astrometry.net si se pide solución de placa.
- **Salidas** (en `"Directory to Save Plots"`): figura publicable
  `FinalLightCurve_<planeta>_<fecha>.png`/`.pdf` y reporte AAVSO
  `AAVSO_<planeta>_<fecha>.txt` en la raíz; en `temp/`:
  `FinalLightCurve_<...>.csv` (BJD_TDB, Phase, Flux, Uncertainty, Model,
  Airmass), `NormalizedFlux_<...>.txt` (BJD, Norm Flux, Norm Err, AM),
  `FinalParams_<...>.json` (T_mid, Rp/Rs, profundidad, inc, coeficientes de
  masa de aire, duración, apertura/anillo óptimos), `PlateStatus_<...>.csv` y
  varias figuras.
- **Corrida de prueba real** (142 FITS de MicroObservatory, HAT-P-32 b):
  T_mid 2458107.71358 ± 0.00094 BJD_TDB; Rp/Rs 0.1569 ± 0.0034; profundidad
  2.46 %; inc 88.17; duración 0.1303 d. Coincide con la referencia publicada
  (2458107.71406 ± 0.00097; 0.1541 ± 0.0033) a 41 s y 1.8 %.
- **Compuerta redefinida (nuestro `transit_fit` sobre la curva de EXOTIC)**:
  **PASA las cuatro**: T_mid a 0,000023 d (≈2 s, dentro de 3σ), Rp/Rs a 1,2 %
  (dentro de 5 %), σ al 96 % de la de EXOTIC (dentro de 20 %) y profundidad
  (Rp/Rs²) 2,52 % frente a 2,46 % (2,3 %, dentro del 10 %); χ²ᵣ 0,98. Con esto,
  la compuerta de la fase 7 mide ya lo que debe (el ajuste) y queda **cerrada**.
- **Nota para la importación**: usar `temp/FinalLightCurve_*.csv` para los puntos
  y `temp/FinalParams_*.json` para los parámetros; `FinalLightCurve_*.png` como
  figura publicable.

---

## 3. Fase A · Entorno EXOTIC en Ajustes

- **Configuración** (`nightscribe/config.py`): claves nuevas
  `exotic_python_path` ("" = autodetectar `python3.10`/`python3.9`),
  `exotic_install_dir` (ruta del venv, "" = `paths.data_dir()/exotic-venv`).
- **Core** (`core/exotic_env.py`, nuevo):
  - `detect_python(cfg)` -> ruta del intérprete ≤3.10 o None.
  - `probe(python_path)` -> `{"ok", "version", "message"}` (corre
    `python -c "import exotic, sys; print(...)"`).
  - `prepare(install_dir, progress, cancel)` -> crea el venv e instala `exotic`
    con `pip`; devuelve `(ok, log)`.
- **GUI**:
  - Ajustes (`gui/ui/settings_dialog.ui` + `on_open_settings` y su guardado en
    `gui/main_window.py`): grupo «EXOTIC» con `edt_exotic_python` (+ Examinar),
    `edt_exotic_install` (+ Examinar), botón **«Preparar entorno»**, botón
    **«Probar»**.
  - `PrepareExoticWorker(QThread)` (en `gui/workers.py`) con `progress(str)`,
    `finished(bool, str)`, cancelable; abre una ventana de log (o el panel de
    estado) mientras instala.
- **Tests** (`tests/unit/test_exotic_env.py`): detección con `which` simulado,
  `probe` con un intérprete falso que imprime una versión, `prepare` con un
  `pip` simulado (monkeypatch de `subprocess.run`), mensajes bilingües.

Salida limpia: con un clic se prepara (o valida) el entorno; con el botón Probar
se sabe si EXOTIC está listo, sin bloquear la UI.

### Resultado de la fase A (2026-09-27)

`core/exotic_env.py` (`detect_python`, `probe`, `prepare`, `venv_python`),
`gui/workers.PrepareExoticWorker` y el grupo «EXOTIC (transit reduction)» en
Ajustes (intérprete, carpeta del entorno, «Preparar entorno», «Probar»), con
las claves `exotic_python_path`/`exotic_install_dir`. `detect_python` es
consciente de Windows (lanza el **lanzador `py -3.10`** y **valida la versión**
≤3.10 en todos los candidatos, descartando el stub de Microsoft Store); `prepare`
intenta **primero un venv normal** y solo si falta pip (el `ensurepip` roto de
Linux) rehace el venv con `--without-pip` y arranca pip por el intérprete base
(`pip --python`). Tests en `tests/unit/test_exotic_env.py` (detección, versión,
lanzador `py`, secuencia de pip, fallo y cancelación) e i18n sin `unfinished`.

---

## 4. Fase B · `inits.json` de la visita

Hoy `core/exotic.make_inits(ctx, d, cfg, plan=None, out_dir=None)` genera el
JSON desde la ficha del proyecto, pero **no** rellena los píxeles del objetivo y
las comparaciones ni apunta a la carpeta de tomas de la visita. Hay que
extenderlo:

- **Nueva función** `core/exotic.make_inits_for_visit(ctx, d, cfg, paths,
  target_xy, comps_xy, plan=None, out_dir=None)`:
  - `"Directory with FITS files"` = carpeta de las tomas de la visita.
  - `"Directory to Save Plots"` = carpeta de trabajo del proyecto.
  - `"Target Star X & Y Pixel"` = `[target_x, target_y]`.
  - `"Comparison Star(s) X & Y Pixel"` = lista con las comps (y `null` para las
    que EXOTIC rellene desde AAVSO si se pide).
  - Reusar `make_inits` para el resto (planeta, sitio, cámara, filtro).
- **Cálculo de píxeles**: desde la placa de referencia (la primera toma con WCS)
  o, sin WCS, desde el resultado de nuestra serie (el objetivo medido y las
  comps de la secuencia). El punto de enganche ya existe:
  `series_measure.SeriesConfig.target_xy` / `comp_set`.
- **Modo pre-reducido**: si el usuario ya tiene una curva, permitir
  `"Pre-reduced File:"` + formato/unidades en `optional_info` (EXOTIC lo acepta).
- **Tests** (`tests/unit/test_exotic.py` ampliado): el JSON lleva los píxeles,
  la carpeta de tomas y las comps; `null` donde falte; estructura idéntica a la
  del sample real de EXOTIC.

Salida limpia: el `inits.json` de una visita es autocontenido y EXOTIC arranca
sin pedir la carpeta ni las coordenadas.

### Resultado de la fase B (2026-09-27)

`core/exotic.make_inits_for_visit(ctx, d, cfg, paths, target_xy, comps_xy,
plan, out_dir, pre_reduced)`: apunta «Directory with FITS files» a la carpeta de
las tomas, rellena objetivo y comparaciones en píxeles con la **forma de cadena
del sample de EXOTIC** (`"[424, 286]"`, lista de 10 con `[]` de relleno), pone
`"Add Comparison Stars from AAVSO?" = "n"` (headless, fase 0) y
`"Plate Solution?" = "n"` (corrección 2026-09-30: ver abajo), y admite `out_dir`
y una curva pre-reducida. Tests en `tests/unit/test_exotic.py`.

**Corrección (2026-09-30)**: la fase B dejó `"Plate Solution?" = "y"` porque la
fase 0 lo validó así. En uso real eso manda a EXOTIC a **subir la primera toma a
nova.astrometry.net y sondear la cola pública antes de mirar la WCS del FITS**
(`exotic.py:671-684`): unos 4 min por corrida con 10 reintentos por etapa y
esperas de 4 a 37 s, y fallando más veces de las que acertaba. El síntoma era el
spinner «Thinking | ...» durante minutos, que el observador lee como un cuelgue
(caso real: proyecto HAT-P-32 b, `exotic_run.log` con 1542 líneas de spinner y
`exotic.log` acabando en `GET /api/submissions/...`). Ahora es `"n"`:
EXOTIC usa la WCS que ya traiga el FITS o, si no hay, alinea con astroalign y
saca escala y masa de aire de la cabecera y del inits. Se pierden el chequeo VSX
de las comparadas y el reencuadre del píxel del objetivo (informativos). El
`run` además drena y sale si EXOTIC muere dejando el tubo abierto, marca
`timed_out` y el diálogo de progreso traduce «Finding transformation i of N».

**Segunda corrección (2026-09-30, misma fecha)**: la fase B dejó **todas las
incertidumbres en `null`**. EXOTIC las sustituye por 1 (`exotic.py:1996-2002`),
y en el ajuste final eso no se nota (su tope de ±0,25 P manda), pero en la
**búsqueda de apertura/comparada** (`fit_lightcurve`, término 25σ) deja el
tiempo de tránsito **clavado**: medido sobre el set de HAT-P-32 b, 3 valores
distintos de `tmid` en 3809 ajustes de la búsqueda frente a **1289** con las
incertidumbres del archivo, y el T_mid final pasó de 2458107.7125 ± 0,0019 a
**2458107.7146 ± 0,0011** (de 1σ a 0,5σ de lo publicado), con la dispersión de
0,71 % a 0,61 %. Ahora el `inits.json` las lleva (y Rp/Rs y a/Rs **propagadas**
desde `pl_radj`/`st_rad` y `pl_orbsmax`/`st_rad`), más el argumento del
periastro (sin él EXOTIC modela `omega = 0` con e = 0,159) y la fecha de
observación tomada de la **cabecera de las tomas**. La caché de la fuente sube a
`exoplanet_archive:v3` porque las filas anteriores no traen esas columnas.
Queda **abierto** que la calidad fotométrica (Rp/Rs 0,1612 ± 0,0037 frente a
0,1541 ± 0,0033 publicada) no alcanza la de la corrida de la fase 0 (0,1569 ±
0,0034): apunta a las comparadas que se entregan (en el set de prueba las #2,
#3 y #4 se salen del borde al derivar el campo), no a las incertidumbres.

---

## 5. Fase C · Ejecución headless

- **Core** (`core/exotic_run.py`, nuevo):
  - `run(python_path, work_dir, inits_path, progress, cancel, timeout_s)`:
    lanza EXOTIC como subproceso en `work_dir`, captura stdout/stderr en un log
    (`work_dir/exotic_run.log`), cancela con `terminate()` y respeta `timeout`.
    Devuelve `{"ok", "returncode", "log_path", "out_dir"}`.
  - `find_outputs(out_dir)` -> dict con rutas de curva/parámetros/PNG si
    existen (según la fase 0).
- **GUI** (`gui/workers.py`): `ExoticRunWorker(QThread)` con `progress(str)`,
  `finished(dict)`, `failed(str)`, cancelable. Log visible en una ventana no
  modal o en el bloque de análisis.
- **Tests** (`tests/unit/test_exotic_run.py`): con un EXOTIC simulado (script
  que escribe un log y una curva falsa) comprobar: éxito, fallo (returncode≠0),
  timeout y cancelación sin dejar proceso colgado.

Salida limpia: EXOTIC corre desde la app con log, cancelación y timeout; el
usuario ve avanzar (o parar) el proceso.

### Resultado de la fase C (2026-09-27)

`core/exotic_run.py` (`run` y `find_outputs`) y `gui/workers.ExoticRunWorker`:
corre `exotic -red <inits.json> -ov` con `stdin` cerrado (un prompt falla en
seco, no cuelga), fusiona stdout/stderr en `exotic_run.log`, y comprueba
cancelación y timeout con un hilo lector (una EXOTIC muda no congela la app);
`find_outputs` localiza `FinalLightCurve_*.csv`, `FinalParams_*.json`,
`NormalizedFlux_*.txt`, `FinalLightCurve_*.png` y `AAVSO_*.txt`. La ejecución usa
el **intérprete del usuario** (`python -c "…main()…" -red inits.json -ov`), no el
script de consola, para que valga cualquier instalación de EXOTIC. Tests en
`tests/unit/test_exotic_run.py` (éxito y salidas, fallo, cancelación y timeout).

---

## 6. Fase D · Importación del resultado

- **Core** (`core/exotic_import.py`, nuevo):
  - `load_result(out_dir)` -> `{"points": [{mjd, mag|flux, err, filter}],
    "tmid", "tmid_err", "rprs", "rprs_err", "depth", "log_path", "figures"}`.
  - Parser tolerante: curva normalizada (CSV/txt) a puntos; parámetros del log o
    del JSON de EXOTIC si lo hubiera; figuras como rutas.
- **Persistencia**: los puntos entran al proyecto como curva con
  `source="exotic"` (helpers `followup.add_points`/`create_run` ya existen;
  una ejecución `run` con `cfg_json` apuntando al `inits.json` y al log). Los
  parámetros se guardan en el contexto del proyecto y en un reporte
  (`project.add_file(kind="report")`).
- **Curva**: `lightcurve_data.build_payload` ya consume los puntos; el widget
  los pinta. `lightcurve_widget.source_label` gana `"exotic"` -> «EXOTIC».
- **Tests** (`tests/unit/test_exotic_import.py`): un directorio de salida
  sintético produce los puntos y los parámetros; un directorio incompleto no
  revienta (avisa).

Salida limpia: tras correr EXOTIC, la curva y el ajuste aparecen en el
proyecto, listos para ExoClock y para el post.

### Resultado de la fase D (2026-09-27)

`core/exotic_import.py`: `load_curve` (CSV de EXOTIC -> puntos con `mjd`/`mag`/
`err`/`flux`/`airmass` y `source="exotic"`), `load_params` (JSON con cadenas
`valor +/- incertidumbre` -> T_mid, Rp/Rs, profundidad en fracción, inclinación
y duración), `load_result` (localiza curva, parámetros, figura y reporte AAVSO)
y `persist` (una ejecución con `source="exotic"` y sus puntos vía `followup`).
Parser tolerante: sin carpeta o formato raro devuelve vacío y avisa, no revienta.
Tests en `tests/unit/test_exotic_import.py`.

---

## 7. Fase E · UI y estado (la numpy como previsualización)

- **Bloque de tránsito en Análisis** (`gui/main_window.py`,
  `_analysis_transit_block`, ~línea 4260): junto al actual
  «Exportar a EXOTIC (inits.json)…» (~4296) añadir **«Reducir y ajustar con
  EXOTIC…»** que:
  1. genera el `inits.json` de la visita (fase B),
  2. comprueba el entorno (fase A) y, si falta, guía a Ajustes,
  3. corre EXOTIC (fase C) con log,
  4. importa el resultado (fase D) y muestra la curva y T_mid/Rp/Rs.
- **Semáforo**: comparar el resultado importado con lo esperado (profundidad,
  O-C) en lenguaje llano; avisa, no bloquea.
- **Previsualización numpy**: mantener el botón actual de la serie
  («Medir la secuencia») y el ajuste numpy como «vista previa rápida», etiquetado
  como tal; sus puntos van con `source="measure"` y no sustituyen a los de
  EXOTIC.
- **Config**: `exotic_python_path`/`exotic_install_dir` (fase A); nada de
  credenciales.
- **i18n**: todas las cadenas nuevas con `self.tr()` y `.ui`; `lupdate` +
  traducción sin `unfinished`.

Salida limpia: el flujo de tránsito se cierra con EXOTIC desde la app, y la vía
numpy sigue disponible como previsualización clara.

### Resultado de la fase E (2026-09-27)

Bloque de tránsito (Análisis) gana **«Reducir y ajustar con EXOTIC…»**: recoge
los datos del planeta (worker), resuelve el entorno preparado en Ajustes
(guía a Ajustes si falta), toma las tomas de la última visita con FITS, calcula
los píxeles de objetivo y comparaciones desde la WCS de la primera toma y la
secuencia del proyecto, escribe el `inits.json` de la visita y corre EXOTIC con
el log en la barra de estado. Al terminar, importa la curva y los parámetros
(`exotic_import.load_result` + `persist`), informa de T_mid y Rp/Rs y refresca el
proyecto. El botón de exportar el `inits.json` se conserva como vía manual. Las
cadenas nuevas pasan por `tr()` y el i18n queda sin `unfinished`.

**Fallback sin WCS (2026-09-28)**: si la primera toma no tiene WCS (o el proyecto
no tiene secuencia), la app pide a mano el píxel del objetivo y los de las
comparaciones en vez de abortar, de modo que un set sin resolver (una ejecución
de MicroObservatory, una sesión en vivo) también se puede reducir.

---

## 8. Fase F · Compuerta redefinida y ADRs

- **ADR-015**: actualizar la reapertura (2026-09-27) para reflejar la opción A:
  EXOTIC orquestado = vía principal del flujo científico; numpy = previsualización;
  se conserva el handoff. Firmar con el autor.
- **ADR nuevo** (p. ej. ADR-052): «Orquestación de EXOTIC: ejecución externa e
  importación de resultado», con la decisión, alternativas (portar código,
  numpy puro) y consecuencias (entorno externo, Windows, licencia).
- **`docs/PLANS/series-photometry.md`**: reescribir el «Resultado» de la fase 7
  (la compuerta end-to-end la cubre ahora EXOTIC; la vía numpy se valida **contra
  la curva reducida por EXOTIC** para medir el ajuste, no la reducción) y quitar
  el marcador de «pendiente» de fotometría real, sustituyéndolo por este plan.
- **Compuerta**: nuestra `transit_fit` ajusta la curva reducida por EXOTIC y
  debe caer dentro de T_mid 3σ, Rp/Rs 5 %, σ 20 % y profundidad 10 % de los
  parámetros de EXOTIC. Esa sí mide el ajuste; se escribe con umbrales fijos
  antes de medir (D38).
- **Tests**: `tests/functional/` con la curva reducida real como fixture
  opcional (si no está, se salta); constantes de umbral citadas.

Salida limpia: la decisión queda firmada y documentada; la compuerta mide lo que
debe medir (el ajuste).

### Resultado de la fase F (2026-09-27)

ADR-015 gana la **actualización de la opción A** (orquestación de EXOTIC; numpy
como previsualización) en ambos idiomas, y nace **ADR-052** (orquestación:
ejecución externa headless e importación) con su entrada en `docs/adr/README.md`
y el rango de ADRs de `AGENTS.md` hasta 052. La compuerta redefinida se midió en
la fase 0 (nuestro `transit_fit` sobre la curva de EXOTIC: las cuatro pruebas
pasan). No se copió código de EXOTIC.

---

## 9. Fase G · Documentación de usuario, i18n y WORKFLOWS

- **`docs/SEQUENCES.es.md`/`.md`**: nueva sección «Reducción externa con EXOTIC»
  (preparar el entorno, correr, importar, y cuándo usar la previsualización
  numpy). Actualizar la sección de ExoClock para encadenar con el flujo EXOTIC.
- **`docs/WORKFLOWS.es.md`/`.md`**: enlazar el flujo de tránsito con EXOTIC
  orquestado.
- **`docs/PRECISION.es.md`/`.md`**: matizar la fila T1–T8 y la compuerta.
- **`AGENTS.md`**: añadir `exotic_env.py`, `exotic_run.py`, `exotic_import.py`
  a la estructura de `core/`.
- **i18n**: `pyside6-lupdate` + traducción; `tests/unit/test_i18n.py` verde.

Salida limpia: la funcionalidad y su documentación cierran en ambos idiomas.

### Resultado de la fase G (2026-09-27)

`docs/SEQUENCES.es.md`/`.md` ganan la sección «Reducción externa con EXOTIC» (y
el glosario/enlaces citan ADR-052); `docs/WORKFLOWS.es.md`/`.md` enlazan el cierre
de tránsito con EXOTIC; `AGENTS.md` lista los módulos `exotic_env.py`,
`exotic_run.py` e `exotic_import.py` y su rango de ADRs llega a 052; el i18n de
la GUI queda sin `unfinished`. El plan de orquestación queda completo
(fases 0 y A–G), con la compuerta redefinida pasando.

---

## 10. Riesgos y mitigaciones

- **EXOTIC interactivo**: es el mayor riesgo. Mitigación: fase 0 lo fija; si no
  es domesticable headless, se degrada a «generar inits + importar la carpeta que
  el usuario produzca a mano».
- **Peso/dependencias en Windows**: el entorno EXOTIC lo instala el usuario; no
  entra en el instalador. Documentado.
- **Red en la primera ejecución de EXOTIC** (Gaia/astrometry): avisar en la UI;
  no hay scraping ni credenciales nuestras.
- **Licencia**: no se copia código; se ejecuta EXOTIC y se lee su salida.
- **Formato de salida de EXOTIC cambiante**: parser tolerante + test con fixture
  y `importorskip`/skip si no está.
- **Windows sin python3.10**: la orquestación es opcional; sin entorno, el flujo
  numpy sigue.

---

## 11. Puntos de enganche (referencia rápida)

- `core/exotic.py`: `make_inits`, `export_inits`, `suggested_name`
  (a extender con la variante de visita).
- `core/series_measure.py`: `SeriesConfig.target_xy`, `comp_set`, `measure_series`
  (fuente de píxeles sin WCS y previsualización).
- `core/transit_fit.py`: `fit_transit`, `gate_report` (la compuerta redefinida).
- `core/followup.py`: `create_run`, `add_points`, `list_points`.
- `core/lightcurve_data.py`: `build_payload`; `gui/widgets/lightcurve_widget.py`:
  `source_label` (añadir `"exotic"`).
- `gui/main_window.py`: `_analysis_transit_block` (~4260),
  `_transit_export_exotic` (~5140), `on_open_settings` (carga/guarda).
- `gui/workers.py`: patrón de workers con `progress`/`finished`/`failed`.
- `gui/ui/settings_dialog.ui`, `gui/ui/ufe_measure_tab.ui`: estructura (ADR-005).

---

## 12. Criterios de aceptación

1. En un proyecto de tránsito, un botón prepara/valida el entorno EXOTIC y otro
   corre EXOTIC con log, cancelación y timeout.
2. El `inits.json` de la visita es autocontenido (tomas, objetivo y comps).
3. EXOTIC corre de punta a punta sobre el set de prueba y su curva y parámetros
   se importan al proyecto.
4. Nuestra `transit_fit` sobre la curva de EXOTIC pasa la compuerta (T_mid 3σ,
   Rp/Rs 5 %, σ 20 %, profundidad 10 %) o, si no, se reporta sin relajar
   umbrales; en ningún caso la app queda rota.
5. La vía numpy se conserva como previsualización, claramente etiquetada.
6. ADR-015 actualizado y ADR nuevo firmados; `SEQUENCES` y `WORKFLOWS` enlazan el
   flujo; i18n sin `unfinished`; suite unitaria verde en cada fase.
7. Sin código de EXOTIC copiado; sin credenciales guardadas; sin scraping.
