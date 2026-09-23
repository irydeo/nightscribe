# Fotometría de precisión en NightScribe: cómo se consigue

*[English version](PRECISION.md)*

Este documento responde a una pregunta: **qué separa una medida de
0,05 mag de una de 0,005 mag**. Sirve a dos lectores: al observador, que
quiere entender los conceptos y sacar el máximo de su equipo (primera
parte, sin matemáticas); y a una IA o desarrollador que extienda la
implementación (apéndice técnico, al final). Casi todo lo descrito ya
existe en NightScribe (fases G y H, 2026-09-23); la fase I (misma fecha)
añadió el centroide de precisión y la sugerencia de aperturas
(`suggest_apertures` + botón en Medir); la fase I.5 subió el centroide
al **filtro adaptado gaussiano** (`gaussian_centroid`: plantilla del
seeing en malla de 0,1 px con refinado parabólico, ~0,01 px con señal
decente, guardas honestas con débiles) con la **retícula que se pega al
centroide** al pasar el ratón; solo el régimen de tránsitos de
exoplanetas queda pendiente de una decisión (ADR-015).

Documentación del proceso fotométrico base:
[PHOTOMETRY.es.md](PHOTOMETRY.es.md). Este documento es su continuación
de calidad.

---

## Parte I: para el observador

### 1. Los dos presupuestos de error

Toda medida fotométrica arrastra dos errores de naturaleza distinta, y
confundirlos es la fuente de casi todas las decepciones:

* **El ruido** es el temblor de la aguja. Fotones que llegan al azar,
  cielo que brilla, electrónica que zumbía. Baja acumulando fotones:
  más exposición, más apertura de telescopio, o promediando medidas.
  Es honesto y predecible.
* **Los sistemáticos** son una báscula mal tarada. No tiemblan: mienten
  siempre en la misma dirección. La óptica que ilumina un poco menos las
  esquinas (flat mal corregido), un filtro que no responde exactamente
  como el estándar, una comparación que resulta ser variable. **Ningún
  promedio los arregla**: solo se combaten calibrando contra pesas
  conocidas (las estrellas de comparación) y cuidando la técnica.

La fotometría de precisión es, sobre todo, la caza sistemática de los
sistemáticos.

### 2. La escalera de calidad

De lo gratis a lo heroico; cada peldaño «compra» una mejora típica, y
casi todos viven ya en el Editor FITS (pestaña Medir, fase H):

| Peldaño | Dónde vive | Qué compra |
|---|---|---|
| Placa bien reducida (bias, darks, **flats**) | tú, al apilar | un campo plano: sin esto, 1–5 % de error según la posición |
| Comparaciones de color parecido al objetivo | tú, pestaña Comparar | quita la mayor parte del término de color |
| Apertura que sigue al seeing de la noche | pestaña Medir (H3) | SNR óptima y consistencia noche a noche |
| Cielo bien estimado (mediana robusta o plano) | pestaña Medir (H2a) | la SN deja de medirse «con galaxia incluida» |
| Nivel de saturación real de tu cámara | pestaña Medir (H4: tarjeta SATURATE o ajuste `ccd_saturate`) | ninguna estrella cortada se cuela como buena |
| Término de color ajustado con las comps | pestaña Medir (H1) | la respuesta de tu equipo deja de sesgar el cero |
| Sustracción de la galaxia huésped (SNe) | pestaña Medir (H2b) | en núcleos galácticos: de 0,05–0,15 a 0,03–0,05 mag |
| Normalización por frame + detrending (series) | pendiente (ADR-015) | el requisito de los tránsitos: 0,001–0,005 mag relativo |

### 3. Tres escenarios, cifras honestas

* **Variable en buena noche, placa reducida**: el flujo de series da
  Δmag con 0,02–0,05 mag de precisión total; la pestaña Medir (apertura
  adaptativa, término de color y la check vigilando) lo deja en
  **0,01–0,02 mag**. A partir de ahí manda la calibración del color, y
  bajar más exige medir los coeficientes de transformación propios de tu
  cámara sobre campos estándar (otra liga, anotada como v2).
* **Supernova pegada a un núcleo galáctico**: el enemigo no es el ruido,
  es la galaxia. La pestaña Medir hace las dos cosas: el cielo por plano
  en el anillo ya mejora la medida, y con la **sustracción de la
  huésped** (la referencia PS1 alineada por el blink se resta, escalada
  para que las estrellas desaparezcan y solo quede la SN) se pasa de
  0,05–0,15 a **0,03–0,05 mag**.
* **Tránsito de exoplaneta (Júpiter caliente)**: la señal es 0,01–0,02
  mag de profundidad durante horas. No hace falta exactitud absoluta,
  sino **estabilidad relativa extrema**: cada frame se normaliza con sus
  propias comparaciones (una nube fina no debe fingir un tránsito), el
  ensemble se pondera por su error, la apertura se elige para minimizar
  la dispersión de la check, y la curva se detrenda contra la masa de
  aire mostrando siempre la cruda al lado. Con eso y buenas prácticas,
  un aficionado alcanza 0,001–0,005 mag por punto bineado: suficiente
  para curvas de tránsito publicables. Hoy esa reducción la hace EXOTIC
  (decisión firmada, ADR-015); hacerlo dentro es posible pero es la obra
  mayor que queda.

### 4. Cuándo fiarse de un número

* **La estrella check es el semáforo**: la pestaña Medir la mide como si
  fuera el objetivo y la compara con su valor de catálogo. Si ella se
  mueve, la culpa no es de la variable: la noche, la placa o la
  secuencia no son de fiar. Si solo se mueve el objetivo, eso es
  astrofísica.
* **Saturación con nivel real**: «casi saturada» no existe. El techo
  viene de la tarjeta SATURATE o del ajuste `ccd_saturate`, no estimado
  del propio frame.
* **El error reportado vs. el total**: el panel distingue «interno»
  (fotones) de «total» (más dispersión de las comps, centelleo, color y
  flats). Fiarse del primero como si fuera el segundo es el error más
  común.

### 5. Qué es hoy qué

| Pieza | Estado |
|---|---|
| Centroide sub-píxel, apertura, cielo por mediana, guards | Existe (`core/series.py`) |
| Secuencias de comparación con magnitudes de catálogo (Gaia/APASS, veto VSX) | Existe (pestaña Comparar del Editor FITS) |
| Series Δmag con ensemble automático + quicklook de SN | Existe (`core/series.py`, flujo Seguimiento) |
| Export CSV / AAVSO EFF | Existe (`core/photometry_export.py`) |
| Medida calibrada en una placa (punto cero con las comps) | Existe (pestaña Medir del Editor FITS, fase G) |
| Término de color, cielo en gradiente, apertura por FWHM, saturación real, error total, semáforo check | Existe (fase H, 2026-09-23: `core/photometry.py` + pestaña Medir) |
| Sustracción de galaxia huésped | Existe (fase H: referencia PS1 alineada del blink, escalada por las comps) |
| Serie normalizada por frame + detrending para tránsitos | Falta: piezas T1–T8; decisión ADR-015 por reabrir o acotar |

---

## Apéndice: referencia técnica de la implementación

**Estado**: las piezas H1–H7 están implementadas (2026-09-23) en
`core/photometry.py` y `gui/ufe_measure_tab.py`, con tests en
`tests/unit/test_photometry.py` y `test_ufe_measure_tab.py`; la fase G
(medida calibrada en placa) está en `docs/PLANS/ufe-photometry.md`. Las
piezas T1–T8 (tránsitos) quedan pendientes de la decisión ADR-015. Este
apéndice queda como la especificación de referencia para futuras
extensiones.

Convenciones de la casa: cabecera del proyecto en todo `.py`; código en
inglés con comentarios `# @args:`/`# @return:`; toda cadena visible por
`self.tr()`; red solo desde `core/sources/` vía `core/db.py`; tests
offscreen con `np.random.default_rng(<semilla>)` fija; los diálogos
legacy nunca se tocan; docs en lenguaje natural (la regla de estilo de
siempre: dos puntos, comas y punto y coma; la semirraya solo para rangos
numéricos).

### A. Mejoras de una toma (variables, SNe): piezas A–G

Contexto existente, verificado 2026-09-22 (no re-explorar):

* `core/series.py`: `_centroid(data, x, y, half=5)`,
  `aperture_flux(data, x, y, r_ap, r_ann_in, r_ann_out) ->
  (flux, sky_pp)`, `instrumental_mag`, `_is_unsaturated` (techo estimado:
  percentil 99.9 × 1.5, o `sat_adu` absoluto), `R_AP=6.0`,
  `R_ANN_IN=10.0`, `R_ANN_OUT=15.0`, `_SAT_FRAC=0.85`.
* `core/compstars.py`: estrellas con `bands` (APASS: B, V directas;
  Gaia: G + B, V, Rc, Ic derivados) y `star["bv"]` (directo o estimado,
  `color_origin` lo dice).
* `core/blink.py:prepare_pair` devuelve la referencia PS1-g alineada a
  la geometría de la placa (mismo centro/escala/rotación, hasta
  `WORK_MAX=2048`): es la base de la sustracción.
* `core/phototrans.py`, `core/photometry_export.py` (EFF con
  CNAME/CMAG/KNAME/KMAG).

Las piezas, en orden de impacto por esfuerzo:

* **H1. Término de color**: ajuste ponderado de
  `(V_cat − v_inst) = ZP + k·(B−V)` sobre las comps (≥6 con dispersión de
  color; MAD-clip de residuales antes de citar ZP±err); aplicar con el
  B−V del objetivo (VSX para variables; SN: B−V≈0 asumido con aviso
  visible, o reportar sin transformar). NumPy puro. Test: comps
  sintéticas con pendiente conocida se recuperan; sin dispersión de
  color, la pendiente se reporta como indeterminada y no rompe nada.
* **H2. Cielo en núcleo galáctico**, dos niveles:
  (a) plano ajustado a los píxeles del anillo (tras sigma-clip 2,5σ)
  evaluado en la posición de la estrella, en lugar de la mediana plana;
  (b) **sustracción de huésped**: tomar el par alineado de
  `core/blink.prepare_pair`, escalar la referencia por el cociente de
  flujos de las comps presentes en ambas imágenes (las comps deben
  anularse en la diferencia; su residuo medio es el criterio de escala),
  restar, y medir la SN sobre la imagen diferencia. La referencia PS1-g
  no está calibrada al filtro del usuario: el ajuste por comps absorbe
  eso, y la doc debe decirlo. Tests: galaxia sintética con gradiente +
  SN de flujo conocido; la medida tras sustracción recupera el flujo al
  1 %.
* **H3. Apertura por FWHM**: FWHM medido de las comps brillantes no
  saturadas (momentos de segundo orden tras restar el cielo);
  `r_ap = k·FWHM` con k ∈ [1.2, 1.6] elegido por defecto 1.35; el anillo
  escala en proporción. Test: dos seeing sintéticos dan aperturas
  distintas y la SNR medida mejora respecto a la apertura fija.
* **H4. Saturación real**: techo desde tarjeta `SATURATE` o clave de
  ajustes `ccd_saturate`; fallback al estimador actual con aviso. Test:
  una estrella al 95 % del techo se marca y no se mide.
* **H5. Error total honesto**: ecuación CCD (ganancia/RON por cabecera o
  ajustes, ver D2 del plan G) + centelleo (Young 1967:
  `σ ∝ D^(−2/3) · X^1.75 · t^(−1/2) · e^(−h/8 km)`; parámetros del sitio
  en Ajustes con defaults razonables) + covarianza del ajuste ZP+color +
  suelo de flat configurable (`flat_resid_mag`, default 0.007). El panel
  distingue «error interno» de «error total». Test: el total nunca es
  menor que el interno; sin ganancia, se degrada con aviso.
* **H6. Semáforo check**: medir la check en la misma placa y comparar
  con catálogo; |Δ| > 2,5·σ_total marca la medida como «no fiable» con
  explicación en lenguaje llano. Test: una placa con la nube simulada
  (escala global de flujo) dispara el semáforo.
* **H7. Rechazo de outliers en el ZP**: MAD-clip de residuales (ya citado
  en H1; pieza propia si H1 no se hace). Test: una comp corrupta no mueve
  la mediana.

Todo aterriza en `core/photometry.py` (el módulo de la fase G) y en el
panel de la pestaña Medir; nada toca los flujos legacy.

### B. Tránsitos de exoplanetas: piezas T1–T8

**Nota de decisión (leer primero)**: ADR-015 firmó que la reducción de
tránsitos es 100 % EXOTIC (handoff con `inits.json`; EXOTIC necesita
astropy y Python ≤3.10, vetados por ADR-004). Implementar T1–T8 exige
reabrir ADR-015 o acotar el trabajo como «series calibradas de alta
precisión» dejando el ajuste de tránsito a EXOTIC. Firmarlo con el
usuario antes de escribir código.

* **T1. Serie con punto cero por frame**: cada imagen se normaliza con
  las comps medidas en ESA imagen (la extinción y las nubes finas dejan
  de fingir señal). Reutiliza `core/series.load_series`/`measure_series`
  cambiando la media global del ensemble por ZP por frame.
* **T2. Ensemble ponderado**: media ponderada por el error de cada comp
  (o suma de flujos, la «superstar» de AIJ), con veto por frame de la
  comp outlier (MAD por frame).
* **T3. Apertura óptima por noche**: barrido de k en [1.0, 2.0]×FWHM
  quedándose con el que minimiza el rms de la check; FWHM por frame
  (ligeras defensas de guiado no rompen la curva).
* **T4. Ruido completo**: H5 + cadencia; el error por punto debe incluir
  centelleo (dominante en exposiciones cortas a secuencia rápida).
* **T5. Detrending honesto**: contra masa de aire como mínimo; opcional
  contra FWHM, cielo, x/y del centroide (residuales de flat). Regla de
  oro: la curva cruda siempre visible junto a la detrendada, y el
  documento de usuario explica que el detrending puede comerse señal.
* **T6. HJD a media exposición**: `hjd_of` ya corrige al Sol; sumar
  EXPTIME/2 al instante de la tarjeta DATE-OBS (convención clara y
  documentada).
* **T7. Gates de calidad por frame**: saturación (H4), salto de guiado
  (centroide desplazado > umbral), rayo cósmico en apertura (sigma-clip
  local), ZP outlier (nube) marcado, no borrado.
* **T8. Prácticas de observación**: sección de la doc de usuario
  (PHOTOMETRY): flats obligatorios a nivel mmag, dithering, desenfoque
  leve deliberado, cadencia constante, nada saturado.

**Validación**: serie sintética con semilla y dip conocido de 0,01 mag
recuperado a ±0,001 mag; y, cuando haya datos reales, un tránsito
conocido (p.ej. HD 209458 b) con profundidad recuperada dentro del 10 %
y rms de la check dentro de lo que predice el modelo de ruido.

### C. Criterios de aceptación globales

1. Cada pieza llega con tests de unidad con semilla y la suite completa
   verde (`.venv/bin/python -m pytest tests/unit`).
2. La doc de usuario (PHOTOMETRY + PRECISION, ambos idiomas) explica la
   pieza nueva con un ejemplo; i18n sin `unfinished`.
3. Los flujos legacy (series quicklook, blink, carta legacy, EXOTIC
   handoff) siguen verdes sin tocarlos.
4. El error total reportado nunca es inferior al interno; cuando un dato
   falta (ganancia, saturación, B−V), el panel lo dice en lenguaje llano
   en vez de callar.
