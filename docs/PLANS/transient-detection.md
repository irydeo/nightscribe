# Plan de implementación: detección de transitorios en placa (cross-match + restada de imágenes) (2026-09-24)

> **ESTADO: PENDIENTE DE EMPEZAR (2026-09-24).** Diseñado con el usuario
> en la sesión `ses_f2d8740f5ffeE506aVIlGgrpup`; decisiones D1–D8 ya
> firmadas. Dos fases deliberadas: la **Fase 1** es el MVP por cross-match
> astrométrico (utilizable sin física de PSF, ya aporta valor) y la
> **Fase 2** es la restada diferencial real (emparejamiento de PSF,
> normalización, residuo + mapa de error). La GUI lo coloca en una
> **pestaña "Detect" del UFE**, insertada entre Comparar y Medir (D1),
> más el badge en el dashboard "Necesita tu atención" (ADR-038) y la
> integración con el proyecto.
>
> **Documento vivo**: se actualiza al cierre de cada bloque (tachamos lo
> hecho, añadimos hallazgos). La documentación para el usuario entrará
> en `docs/TRANSIENTS.es.md` / `docs/TRANSIENTS.md` al cerrar la Fase 3.
>
> **Rama**: `feature/transient-detection` (creada 2026-09-24 desde
> `main` en `0cc72e3`).
>
> **Reglas del proyecto que atañen a cada bloque** (recordatorio, no son
> opcionales): cabecera en todo `.py` nuevo; identificador y comentarios
> en inglés, voz humana con `# @args:` / `# @return:`; toda cadena
> visible pasa por `self.tr()` (CONTRIBUTING.es.md); toda la red pasa por
> `core/db.py` (caché TTL) y solo dentro de `core/sources/`; sin astropy
> (ADR-004): numpy puro, las FFTs con `numpy.fft`; tests unitarios sin
> red (placas sintéticas de gaussianas, semilla fija, el patrón de
> `tests/unit/test_photometry.py`); tests funcionales con red; cada
> bloque cierra con su test verde antes de pasar al siguiente.

## Contexto cerrado (no re-explorar en la siguiente sesión)

- **UFE completo** (ADR-044, plan hermano `unified-fits-editor.md`):
  `gui/ufe_dialog.py` monta las pestañas Blink / Comparar / Medir /
  Anotar con `tabs.addTab`; el estado de la placa viaja por
  `gui/ufe_state.py`; la vista es `gui/widgets/ufe_image_view.py` (zoom,
  centrado, norte/escala); `core/stretch.py` da percentiles, estirados y
  downsample 2×2.
- **Primitivas que ya existen y hay que reutilizar, no reescribir**:
  `core/wcs.py` (TAN mínimo, pixel 0-based → cielo); `core/fits_io.py`
  (FITS numpy, sin astropy); `core/photometry.py` (medida con guardas de
  borde/saturación/meseta, ZP mediana+MAD, error CCD con ganancia/RON,
  y desde el último merge el centroide anclado al pico local robusto
  `local_sources`); `core/series.py` (aperturas) si tocara.
- **Fuentes de red ya construidas** (todas vía `core/db.py` con TTL):
  `sources/vizier.py` (cones Gaia EDR3, TTL 30 d); `sources/surveys.py`
  (ZTF vía ALeRCE, TTL 30 d, con el patrón de
  `fetch_points_detailed` que reporta ok/empty/error); `sources/tns.py`;
  `sources/simbad.py`; `sources/cutouts.py` (DESI Legacy JPEG + CDS
  hips2fits con PS1 g / DSS2 red, TTL 30 d); las estrellas de VSX viven
  en `core/vigils.py` (catálogo core).
- **Reglas de GUI**: i18n con `pyside6-lupdate` sobre los nuevos
  `gui/*.py` (CONTRIBUTING.es.md); workers en QThread con el patrón de
  `gui/workers.py`; el dashboard de atención (`core/attention.py`,
  ADR-038) tiene tres niveles de prominencia y el patrón de bloques
  existentes.
- **Convenio de tests** (visto en `tests/unit/test_photometry.py`):
  gaussianas sintéticas, fondo plano, ruido con `np.random.default_rng(42)`,
  umbrales ajustados; los tests de i18n son parte de la suite y no se
  saltean.

## Decisiones firmadas (D1–D8)

- **D1. La herramienta vive como pestaña "Detect" en el UFE**, insertada
  **tras Comparar y antes de Medir** (orden final: Blink, Comparar,
  Detect, Medir, Anotar). Justificación: el input es la placa; la pestaña
  reutiliza `ufe_state`, la astrometría común y la vista de imagen. El
  diálogo independiente en Herramientas se descarta: la herramienta
  necesita la placa y UFE es el único sitio GUI que la tiene.
- **D2. El cross-match descarta contra TODOS los catálogos con cliente
  propio**: Gaia EDR3 (`vizier`), ZTF/ALeRCE (`surveys`), TNS (`tns`),
  SIMBAD (`simbad`) y las estrellas del catálogo VSX core
  (`vigils` cada estrella del catálogo VSX core). Cada candidato lleva
  la etiqueta de la fuente que lo reconoció, no un descartón.
- **D3. El CSV exportado es completo**: RA, Dec, S/N, magnitud (solo si
  la placa tiene ZP calibrada), estado (`new | ztf | tns | vsx | simbad
  | gaia`) y confirmación (`pendiente | confirmado`).
- **D4. Confirmación doble**: un candidato es "confirmado" cuando
  aparece en dos placas; las dos placas **no tienen que ser
  consecutivas** ni de noches distintas obligatoriamente. Mientras no
  pase una segunda placa queda "pendiente".
- **D5. Numpy puro** (ADR-004): la convolución del emparejamiento de PSF
  va por `numpy.fft` (rfft2/irfft2). El kernel emparejador es una
  gaussiana 3×3 o 5×5, ajustada por mínimos cuadrados sobre estrellas no
  saturadas.
- **D6. Referencia de la Fase 2**: automática **PS1 g/r vía hips2fits**
  (CDS, ya usado en `cutouts`; límite de cobertura dec ≥ −30 documentado
  allí) o un **FITS local del usuario** (placa limpia de la víspera,
  preferida cuando el filtro difiere de PS1). Ambas llegan a través de
  `sources/` con TTL y pasan por `db.py`.
- **D7. Los candidatos persisten** en una tabla nueva `detect_candidates`
  de `core/db.py`, de modo que el dashboard "Necesita tu atención"
  (ADR-038) pueda mostrar los pendientes y el UFE pueda retomar una
  sesión interrumpida.
- **D8. Honestidad sobre dithering**: la restada solo funciona en el
  campo exacto que cubre la referencia. Si el centro de la placa y el de
  la referencia difieren más de la mitad del FOV de la referencia, la
  pestaña avisa en lenguaje llano y **no ofrece el modo restada**
  (cross-match sigue disponible, sin más).

## Fase 0: cimientos (docs + ADR)

- **C0.1** Redactar `docs/adr/ADR-045-transient-detection.md`
  (bilingüe, formato de ADR-000 a ADR-044): el problema, por qué es
  viable con material amateur, qué NO es (un survey de cielo amplio),
  las dos fases, las limitaciones (seeing, dither, saturación,
  cobertura de campo, límites de PS1), la decisión frente a alternativas
  (manual con el blink, servicios externos, pipelines completos tipo
  SuperCruncher), la referencia a ADR-004 para numpy puro.
  _Cierre: ADR revisado y firmado por el usuario._
- **C0.2** Actualizar el índice de `docs/adr/README.md` con ADR-045.
  _Cierre: índice consistente._

## Fase 1: MVP cross-match (utilizable sin física de PSF)

Objeto de la fase: "pego una placa en el UFE, salgo con una lista de
fuentes nueva no en los catálogos" + etiquetas ZTF/TNS/VSX/SIMBAD.

- **C1.1 `core/detect.py` — fondo local y picos.** Función:
  `detect_peaks(data, background, wcs, sigma)` → candidatos `(ra, dec,
  peak, sigma, pixel)`. El fondo local es una mediana por celdas
  (downsample 2×2 de `stretch` como base de celdas grandes). Sin red,
  solo numpy.
  _Cierre: test unitario con semilla (seed=42), placa con 5 gaussianas
  + 2 objetos inyectados sobre fondo plano: los 2 inyectados recuperados,
  < N falsos sobre el fondo (N documentado en el test). Suite verde._
- **C1.2 `core/detect.py` — estimación de magnitud (opcional).** Si la
  placa tiene ZP (proveniente del estado UFE o de la pestaña Medir),
  cada candidato lleva `mag`; si no, `mag=None` y el panel solo muestra
  S/N.
  _Cierre: test sintético: el candidato inyectado cae en la magnitud
  esperada a ±0.1 mag, o `mag=None` cuando no hay ZP. Suite verde._
- **C1.3 `core/detect.py` — cross-match.** `cross_match(cands,
  radius_arcsec=3.0)`: llama a `vizier` (Gaia), `surveys` (ZTF), `tns`,
  `simbad`, `vigils` (catálogo VSX core) y anota cada candidato con una
  etiqueta. Precedencia de la etiqueta mostrada: `tns > ztf > vsx >
  simbad > gaia > new`. El fallo de una fuente no bloquea el resto
  (patrón de `surveys.fetch_points_detailed`: ok/empty/error por fuente).
  _Cierre: test unitario con monkeypatch de las fuentes (sin red): cada
  fuente etiqueta correctamente; el fallo de una fuente degrada a la
  etiqueta de las siguientes sin romper. Suite verde._
- **C1.4 `core/detect.py` — persistencia (D7).** `save_candidates` /
  `load_candidates` sobre la tabla `detect_candidates` de `db.py`
  (id, ra, dec, sigma, mag, status, confirmed, plate path, fecha).
  _Cierre: test unitario con db temporal: guardar, leer, actualizar
  estado. Suite verde._
- **C1.5 `gui/ufe_detect_tab.py` — la pestaña.** Controles: umbral S/N
  (default 5), radio de match (default 3"), botón "Detectar" (worker
  QThread, patrón de `gui/workers.py`), tabla de candidatos (estado,
  S/N, mag, confirmación), clic → `ufe_image_view` centra y zoom,
  "Exportar CSV" (D3 completo, patrón de `photometry_export.py`),
  "Abrir en el proyecto" si hay un proyecto activo SN/PCCP (reutilizando
  `core/project.py`). Todas las cadenas por `self.tr()`.
  _Cierre: test offscreen con placa sintética y fuentes mock: la tabla
  muestra 2 pendiente nueva + 1 reconocida ZTF; el CSV exportado tiene
  las columnas D3. Suite verde._
- **C1.6 `gui/ufe_dialog.py` — integración (D1).** Insertar la pestaña
  en `tabs.addTab` tras Comparar, antes de Medir. i18n:
  `pyside6-lupdate nightscribe/gui/*.py nightscribe/gui/widgets/*.py`
  sobre el nuevo archivo; las cadenas nuevas entran en el `.ts`, los
  tests de i18n pasan.
  _Cierre: test offscreen: el UFE arranca con las 5 pestañas en el orden
  Blink / Comparar / Detect / Medir / Anotar; i18n suite verde._
- **C1.7 Dashboard (ADR-038).** Bloque nuevo en `core/attention.py`:
  "Candidato transit X pendiente de confirmación", prominencia
  primaria, clic → UFE con la pestaña Detect abierta. Mantiene el patrón
  de bloques existente (primario / menú ⋯ / bloque colapsado).
  _Cierre: test unitario con estado inyectado (sin placa): el bloque
  aparece cuando hay pendientes, desaparece cuando no. Suite verde._
- **C1.8 functional.** Placa real (fixture de `tests/functional` —
  verificar si existe, si no, añadir una pequeña sintética con WCS de
  M51) contra Gaia + TNS reales (red).
  _Cierre: una placa de M51 no produce pendientes "new" sobre estrellas
  conocidas; si hay una fuente TNS en el campo aparece etiquetada.
  Suite funcional verde._
- **M1 — MVP utilizable.** Verificación completa: tests unitarios +
  funcionales verdes, i18n verde, humo del usuario sobre una placa real.
  **A partir de aquí la Fase 2 solo si M1 está verde y el user ha hecho
  humo del MVP.**

## Fase 2: restada de imágenes (DI)

Objeto de la fase: "en un campo pequeño fijo, salgo con 0–3 candidatos
reales con estado de confirmación, exportables".

- **R1.1 `core/difimg.py` — muestreo de la referencia.**
  `resample_reference(data_ref, wcs_ref, wcs_sci)` → referencia muestreada
  sobre la rejilla de la ciencia por interpolación bilineal (numpy
  vectorizado).
  _Cierre: test sintético: un desplazamiento de 0.5 px de la referencia
  queda absorbido sin residual sistemático (residual sobre una imagen
  plana < 0.1% del fondo). Suite verde._
- **R1.2 `core/difimg.py` — kernel ajustado.** `fit_kernel(data_sci,
  data_ref, stars)` → gaussiana 3×3 o 5×5 `(sigma, gain)` por mínimos
  cuadrados sobre 5–10 estrellas no saturadas (selección: no en el
  borde, no saturada por las guardas de `photometry`, S/N > 10);
  convolución con `numpy.fft`. Devuelve kernel + residual por estrella.
  _Cierre: test sintético: referencia FWHM 1.0" y placa FWHM 1.8" →
  sigma ajustada dentro de 10% de la teórica; residual por estrella
  < 5 sigma del fondo. Suite verde._
- **R1.3 `core/difimg.py` — normalización.** Factor global (pocas
  estrellas) o plano de orden 0–1 (estrellas distribuidas), mediana +
  MAD (patrón de `photometry`).
  _Cierre: test sintético: un offset fotométrico del 5% se calibra a
  < 1%. Suite verde._
- **R1.4 `core/difimg.py` — máscara de saturación.** Reutilizar las
  guardas de meseta/techo de `photometry` en ambos lados; el candidato
  queda enmascarado y no entra en la detección.
  _Cierre: test sintético: una fuente saturada → dentro de la máscara,
  nunca candidato. Suite verde._
- **R1.5 `core/difimg.py` — residuo y mapa de error.**
  `resid = sci − kernel*ref`; `err = sqrt(var_sci + var_ref + floor)`
  (error CCD de `photometry`). Detección sobre el residuo usando el
  mapa de error (mismo criterio de C1.1).
  _Cierre: test sintético: una fuente transitoria de 8σ sobre el
  residuo aparece como candidata; las conocidas no. Suite verde._
- **R1.6 `core/difimg.py` — reporte de calidad.** `quality_report(rms)`:
  si el RMS sobre estrellas conocidas es > 3× el fondo → aviso "restada
  mala (seeing/rotación), no confíes en los candidatos" en el panel de
  la pestaña.
  _Cierre: test sintético: un kernel mal ajustado lanza el aviso.
  Suite verde._
- **R1.7 `core/sources/cutouts.py` — referencia FITS.** Extender
  `hips2fits` para devolver FITS (no solo JPEG) de PS1 g/r, TTL 30 d,
  clave `cutouts:ps1g:fits:ra:dec:size`. Verificar la API del parámetro
  de formato en una prueba manual antes de C1.5 (si no lo soporta,
  buscar la opción en la API antes de bloquear la Fase 2; la referencia
  local (D6) sigue disponible).
  _Cierre: functional: el FITS del centro de M101 tiene WCS esperable
  y no es plano. Suite funcional verde._
- **R1.8 Detect tab — modo DI.** Radio (D1): "cross-match" |
  "restada". Selección de referencia (PS1 g auto o FITS local del
  usuario), kernel 3×3/5×3, umbral S/N. Vista del residuo en
  `ufe_image_view` (estirado log/percentil). Reporte de calidad (R1.6)
  en el panel.
  _Cierre: test offscreen con fuente mock: cambiar a modo "restada"
  produce un candidato con estado de la etiqueta. Suite verde._
- **R1.9 Confirmación (D4).** Dos estados de candidato en
  `detect_candidates` (`pendiente` / `confirmado`); botón "Confirmar
  en esta placa" en la pestaña (una segunda ejecución con una segunda
  placa promueve el candidato a `confirmado`, radio 2").
  _Cierre: test: dos placas con el mismo objeto inyectado → la segunda
  lo marca confirmado; el objeto solo en placa A se queda pendiente.
  Suite verde._
- **R1.10 functional.** Campo real (M51, M101, o campo con cobertura
  PS1 al sur) contra PS1 real: el número de candidatos pendientes en
  una placa a 5σ es ≤ 3; si hay una SN en el campo que TNS ya reportó,
  aparece etiquetada como "known" y no se convierte en candidato.
  _Cierre: functional verde, resultados documentados en este archivo.
  Suite funcional verde._
- **M2 — DI utilizable.** Verificación completa: tests unitarios +
  funcionales verdes, i18n verde, humo del usuario sobre una placa real
  + PS1 real.

## Fase 3: remates y documentación

- **R3.1** `docs/TRANSIENTS.es.md` (y `.md`): flujo del usuario (qué
  placa, qué campo, cuándo esperar resultados, cómo leer los badges
  `new|ztf|tns|vsx|simbad|gaia` y `pendiente|confirmado`), diagrama de
  los modos basado en el comportamiento real al escribirse.
  _Cierre: doc revisada, lenguaje natural, sin raya larga._
- **R3.2** AGENTS.md: añadir `core/detect.py`, `core/difimg.py`,
  `gui/ufe_detect_tab.py` a la estructura, descripciones cortas en la
  misma voz.
  _Cierre: AGENTS al día._
- **R3.3** Revisión i18n (cadenas vanishes, entradas nuevas) y suite
  verde de i18n.
  _Cierre: i18n suite verde._
- **R3.4** Revisión ADR-045: añadir las notas de lo aprendido (valores
  de RMS reales, límites de cobertura PS1, lecciones del campo real).
  _Cierre: ADR refleja la realidad del código._

## Riesgos abiertos (vigilar en cada fase)

- **hips2fits puede no devolver PS1 r/g en FITS con WCS aceptable**:
  antes de R1.2 verificar la API en un script manual; si no, la vía
  alternativa es la referencia local (D6) y la Fase 2 queda bloqueada
  hasta que no haya una referencia viable (no inventar resample sin
  referencia).
- **Diferencia de seeing > 2×**: el kernel ajustado no da cuenta; el
  aviso (R1.6) debe dispararse. No bajar la honestidad.
- **Campos densos (M51)**: el mapa de error fotométrico es lo que
  separa "muchas fuentes" de "fuentes nuevas". Si el functional C1.8
  satura con falsos positivos, subir el umbral S/N default a 6 y
  documentar.
- **Red vs local**: los tests unitarios nunca tocan la red (monkeypatch
  de fuentes); los funcionales usan un fixture real si existe, si no, un
  sintético con WCS en un campo documentado.

## Arranque de la siguiente sesión

Empezar en **C0.1 (boceto de ADR-045)**. A continuación C0.2 y la Fase 1
en el orden C1.1 → C1.5 → C1.6 → C1.7 → C1.8 → **M1**. La Fase 2 solo
si M1 está verde y el usuario ha hecho humo del MVP. Cada bloque cierra
con su test verde antes del siguiente; no mezclar bloques.
