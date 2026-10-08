# Fotometría de precisión en NightScribe: cómo se consigue

*[English version](PRECISION.md)*

Este documento responde a una pregunta: **qué separa una medida de
0,05 mag de una de 0,005 mag**. Sirve a dos lectores: al observador, que
quiere entender los conceptos y sacar el máximo de su equipo (primera
parte, sin matemáticas); y a una IA o desarrollador que extienda la
implementación (apéndice técnico, al final). Casi todo lo descrito ya
existe en NightScribe (fases G y H, 2026-09-23); la fase I (misma fecha)
añadió el centroide de precisión y la sugerencia de aperturas
(`suggest_apertures` + botón Sugerir en la sección Medir, justo bajo
las tres aperturas); la fase I.5 subió el centroide
al **filtro adaptado gaussiano** (`gaussian_centroid`: plantilla del
seeing en malla de 0,1 px con refinado parabólico, ~0,01 px con señal
decente, guardas honestas con débiles) con la **retícula que se pega al
centroide** al pasar el ratón; el régimen de tránsitos de exoplanetas
arranca con la reapertura firmada de ADR-015 (2026-09-27), dirigida por
`docs/PLANS/series-photometry.md` (piezas T1–T8, trece fases).

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
casi todos viven ya en el Editor FITS (pestaña Fotometría, fase H):

| Peldaño | Dónde vive | Qué compra |
|---|---|---|
| Placa bien reducida (bias, darks, **flats**) | tú, al apilar | un campo plano: sin esto, 1–5 % de error según la posición |
| Comparaciones de color parecido al objetivo | tú, pestaña Fotometría | quita la mayor parte del término de color |
| Apertura que sigue al seeing de la noche | pestaña Fotometría (H3) | SNR óptima y consistencia noche a noche |
| Cielo bien estimado (mediana robusta o plano) | pestaña Fotometría (H2a) | la SN deja de medirse «con galaxia incluida» |
| Nivel de saturación real de tu cámara | pestaña Fotometría (H4: tarjeta SATURATE o ajuste `ccd_saturate`) | ninguna estrella cortada se cuela como buena |
| **Ganancia real** de tu cámara (medida en tus propias tomas) | pestaña Fotometría + Ajustes (2026-10-08, ADR-072) | el término de fotones de la barra de error: sin ella, el error se queda en la dispersión de las comparadas |
| Término de color ajustado con las comps | pestaña Fotometría (H1) | la respuesta de tu equipo deja de sesgar el cero |
| Sustracción de la galaxia huésped (SNe) | pestaña Fotometría (H2b) | en núcleos galácticos: de 0,05–0,15 a 0,03–0,05 mag |
| Normalización por frame + detrending (series) | en curso (ADR-015 rev. + ADR-048; plan `docs/PLANS/series-photometry.md`) | el requisito de los tránsitos: 0,001–0,005 mag relativo |

### 3. Tres escenarios, cifras honestas

* **Variable en buena noche, placa reducida**: el flujo de series da
  Δmag con 0,02–0,05 mag de precisión total; la pestaña Fotometría (apertura
  adaptativa, término de color y la check vigilando) lo deja en
  **0,01–0,02 mag**. A partir de ahí manda la calibración del color, y
  bajar más exige medir los coeficientes de transformación propios de tu
  cámara sobre campos estándar (otra liga, anotada como v2).
* **Supernova pegada a un núcleo galáctico**: el enemigo no es el ruido,
  es la galaxia. La pestaña Fotometría hace las dos cosas: el cielo por plano
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
  (ADR-015 original); desde la reapertura firmada (2026-09-27) se hace
  dentro, con EXOTIC como espejo de calidad: es la obra mayor del plan
  `docs/PLANS/series-photometry.md`.

### 4. Cuándo fiarse de un número

* **La estrella check es el semáforo**: la pestaña Fotometría la mide como si
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
| Secuencias de comparación con magnitudes de catálogo (Gaia/APASS, veto VSX) | Existe (mitad Secuencia de la pestaña Fotometría del Editor FITS) |
| Series Δmag con ensemble automático + quicklook de SN | Existe (`core/series.py`, flujo Seguimiento) |
| Export CSV / AAVSO EFF | Existe (`core/photometry_export.py`) |
| Medida calibrada en una placa (punto cero con las comps) | Existe (mitad Medir de la pestaña Fotometría del Editor FITS, fase G) |
| Término de color, cielo en gradiente, apertura por FWHM, saturación real, error total, semáforo check | Existe (fase H, 2026-09-23: `core/photometry.py` + pestaña Fotometría) |
| Sustracción de galaxia huésped | Existe (fase H: referencia PS1 alineada del blink, escalada por las comps) |
| Serie normalizada por frame + detrending para tránsitos | Hecho (2026-09-27): T1–T7 y el ajuste (T8) en `core/series_measure.py`, `core/transit_fit.py` y `core/exoclock_export.py`; paridad de modelo D27 cerrada (<1e-5 vs batman) y compuerta EXOTIC end-to-end abierta por la fotometría real. Ver `docs/SEQUENCES.es.md` y `docs/PLANS/series-photometry.md` |

### 6. Qué limita de verdad una serie débil (medido)

Con exposición corta el límite normalmente no es el programa, y conviene saber
contra cuál de los dos estás peleando. Medido en la propia serie de 1 s del
autor (2025 FG18, telescopio de 0,43 m):

* la dispersión diferencial entre dos estrellas a **6 minutos de arco es 19
  mmag**, y entre dos a **30 minutos de arco es 38 mmag**;
* ese crecimiento con la separación es la firma de **ruido correlacionado**:
  el centelleo y la transparencia atmosférica mueven manchas enteras de cielo
  a la vez, así que dos estrellas cercanas ven la misma atmósfera y dos
  lejanas no;
* el propio modelo de centelleo de la app (Young, 1967) predice **131 mmag**
  para 0,43 m y 1 s, del mismo orden que lo medido.

Dos consecuencias, y la segunda es la importante:

1. **Ningún algoritmo arregla esto.** El motor se midió contra uno basado en
   photutils sobre estos mismos datos (ADR-067): misma precisión en medida
   individual, y en la serie un 1,8 % de mediana de mejora, con un conjunto al
   9,7 %. La atmósfera no estaba en la diferencia.
2. **Lo que sí lo arregla** es recoger más luz por unidad de tiempo: más
   exposición (el centelleo cae como 1/sqrt(2t)), más apertura (como
   D^(-2/3)), menos masa de aire, o agrupar la serie en el tiempo, que cambia
   cadencia por precisión. Un tránsito que necesita 1 mmag por punto agrupado
   pide la exposición más larga que no emborrone el ingreso.

La forma práctica de leer tu propio límite: mide dos estrellas de brillo
parecido a distintas separaciones y compara su dispersión. Si crece con la
distancia, estás limitado por la atmósfera; si no, estás limitado por fotones y
lo que falta es exposición o apertura.

---

## Apéndice: referencia técnica de la implementación

**Estado**: las piezas H1–H7 están implementadas (2026-09-23) en
`core/photometry.py` y `gui/ufe_measure_tab.py`, con tests en
`tests/unit/test_photometry.py` y `test_ufe_measure_tab.py`; la fase G
(medida calibrada en placa) está en `docs/PLANS/ufe-photometry.md`. Las
piezas T1–T8 (tránsitos) están en curso en `docs/PLANS/series-photometry.md`
(ADR-015 reabierto y firmado el 2026-09-27). Este
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
  (b) **sustracción de huésped**: tomar el par de
  `core/blink.prepare_pair`, **registrar la referencia sobre la rejilla
  del frame como semejanza** (escala + rotación + traslación) con las
  estrellas que comparten (`core/register`: el WCS solo no basta, porque
  los términos SIP se ignoran y, sobre todo, la escala del cutout difiere
  de la real en una fracción de por ciento, dejando un dipolo en cada
  estrella), **excluir los píxeles enmascarados
  del survey** (llegan como NaN: se rellenan para poder remuestrear y se
  vuelven a enmascarar en la diferencia), **igualar la PSF**
  (`core/difference`, ADR-073: la observación es más ancha que el survey,
  así que la referencia se ensancha con la gaussiana diferencia o con un
  kernel óptimo regularizado tipo Alard-Lupton, y gana el que menos residuo
  deja en las estrellas), escalar la referencia por el
  cociente de flujos de las comps presentes en ambas imágenes (las comps
  deben anularse en la diferencia; su residuo medio es el criterio de
  escala), restar, y medir la SN sobre la imagen diferencia. La
  referencia PS1-g no está calibrada al filtro del usuario: el ajuste por
  comps absorbe eso, y la doc debe decirlo. Si el registro no es fiable
  se resta igualmente y el panel lo avisa. Tests: par sintético
  desplazado + hueco NaN; el registro baja el residuo, el hueco no se
  pinta y la medida recupera el flujo del objetivo.
* **H3. Apertura por FWHM**: FWHM medido de las comps brillantes no
  saturadas (momentos de segundo orden tras restar el cielo);
  `r_ap = k·FWHM` con k ∈ [1.2, 1.6] elegido por defecto 1.35; el anillo
  escala en proporción. Test: dos seeing sintéticos dan aperturas
  distintas y la SNR medida mejora respecto a la apertura fija.
* **H4. Saturación real**: techo desde tarjeta `SATURATE` o clave de
  ajustes `ccd_saturate`; fallback al estimador actual con aviso. Test:
  una estrella al 95 % del techo se marca y no se mide.
* **H5. Error total honesto**: ecuación CCD (ganancia/RON resueltos en el
  orden de ADR-072: Ajustes → medida en los frames → **recordada** → cabecera)
  + centelleo
  (Young 1967:
  `σ ∝ D^(−2/3) · X^1.75 · t^(−1/2) · e^(−h/8 km)`; parámetros del sitio
  en Ajustes con defaults razonables) + covarianza del ajuste ZP+color +
  suelo de flat configurable (`flat_resid_mag`, default 0.007). El panel
  distingue «error interno» de «error total» y dice de dónde salió la
  ganancia. Test: el total nunca es menor que el interno; sin ganancia, se
  degrada con aviso.
* **H6. Semáforo check**: medir la check en la misma placa y comparar
  con catálogo; |Δ| > 2,5·σ_total marca la medida como «no fiable» con
  explicación en lenguaje llano. Test: una placa con la nube simulada
  (escala global de flujo) dispara el semáforo.
* **H7. Rechazo de outliers en el ZP**: MAD-clip de residuales (ya citado
  en H1; pieza propia si H1 no se hace). Test: una comp corrupta no mueve
  la mediana.

Todo aterriza en `core/photometry.py` (el módulo de la fase G) y en el
panel de la pestaña Fotometría; nada toca los flujos legacy.

### B. Tránsitos de exoplanetas: piezas T1–T8

**Nota de decisión (leer primero)**: **firmada el 2026-09-27**. ADR-015 se
reabre: la reducción de tránsitos se hace en local (numpy puro; sin scipy ni
astropy por ADR-004), con EXOTIC como espejo de calidad y su handoff con
`inits.json` intacto como vía experta para el stack pesado. T1–T8 viven en
`docs/PLANS/series-photometry.md` (registro D1–D39, trece fases, compuerta de
paridad con EXOTIC en la fase 7, umbrales fijos).

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
2. La doc de usuario (PHOTOMETRY + PRECISION + SEQUENCES, ambos idiomas) explica la
   pieza nueva con un ejemplo; i18n sin `unfinished`.
3. Los flujos legacy (series quicklook, blink, carta legacy, EXOTIC
   handoff) siguen verdes sin tocarlos.
4. El error total reportado nunca es inferior al interno; cuando un dato
   falta (ganancia, saturación, B−V), el panel lo dice en lenguaje llano
   en vez de callar.
