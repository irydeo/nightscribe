# Plan: calidad de las secuencias fotométricas (alineación, errores, período)

*Plan de trabajo con todo lujo de detalles / Detailed working plan.*

- **Alcance**: igualar la calidad de las **secuencias fotométricas** a la de las imágenes
  individuales, y cerrar el análisis con la búsqueda de período, el plegado y el informe.
- **Origen**: revisión de la observación real de **V0526 Per** del grupo ObSN
  (`~/Develop/astronomy/Series-Juan-Luis/V526PER Y MÁS (serie)/`, 244 frames, informe de
  FotoDif como referencia).
- **Decisiones cerradas con el autor**: **numpy puro, sin dependencias nuevas**;
  alcance **A + B + C + D** completo; el análisis de período se abre **desde la pestaña
  Análisis (ventana de la visita) y desde el editor FITS unificado**; se incluye un
  **recorte real del dataset como fixture de regresión** en el repositorio.
- **Estilo**: este documento sigue las reglas de la casa (escribimos con «:», «,» y «;»; la
  semirraya «–» solo para rangos numéricos, nunca como raya).

---

## 1. Diagnóstico: por qué los resultados eran desastrosos

La causa raíz es única y está medida: **los frames derivan y el motor mide a coordenadas fijas**.

| Evidencia sobre el dataset real | Dato |
|---|---|
| Deriva medida rastreando estrellas | `(+84, −21)` px = **134"** en 2.9 h (0.35 px/frame), **traslación pura** (todas las estrellas se mueven igual) |
| Escala real del campo | 1.55"/px, sensor 1663×1252 → 43' × 32' |
| Flujo de la estrella objetivo toda la noche | **constante** (~20 000 ADU pico); cielo 4800 → 3800 ADU (extinción normal, noche fotométrica) |
| Apertura usada (run 8) | r = 6 px: el núcleo sale de la apertura al frame **~17**; el flujo medido decae desde el ~29 y es inservible tras el ~60 |
| Run 8 en la base de datos | 244 puntos, mag 9.3–17.4, `err` = 0.5, flags `unusable` / `few_comps` / `guide_jump` |

`SeriesConfig.align` vale `"off"` y **no hay ningún control en la GUI**: `_series_config`
(`gui/ufe_measure_tab.py:819`) nunca pasa `align` y `_series_config_dict` no lo persiste. El
módulo `core/register.py` existe (D44) pero es inalcanzable desde la aplicación.

**La receta de medida sí es buena.** Alineando por traslación y midiendo con el propio motor
(`photometry.measure_plate` con WCS por frame):

- curva diferencial del objetivo contra el informe de FotoDif: **correlación 0.875** y
  **residuo 0.012 mag**;
- estrella de control: **rms 0.005 mag** (el informe da ±0.008);
- amplitud plegada recuperada: 0.079 mag (el informe: ~0.09).

No hay que reescribir la fotometría: hay que arreglar la alineación y el análisis.

### 1.1 Defectos localizados en el código

1. `series_measure.py:1057-1070`: el remapeo del centroide a la placa de referencia
   (`register.src_to_ref_point`) vive **dentro** de `if warped_mask is not None`, rama que solo
   se ejecuta en `warp` / `similarity`. En `"coords"` nunca se remapea y `_guide_jump` compara
   píxeles de la fuente contra la referencia: `guide_jump` en **todos** los frames.
2. `register.estimate_transform`: búsqueda ciega de ángulo (180+ FFTs), **4.6 s/frame**
   (244 frames = 19 min) y **frágil**. Frames 1 → 241 devuelve `angle = −166°`,
   `dx,dy = (−104, +249)` con `quality = 43.8` > `QUALITY_MIN = 8`: acepta un transform absurdo
   **en silencio**. El *score* `peak/std` no discrimina (0°: 43.0; −166°: 47.1). El fondo del
   cielo (gradiente y viñeteo) domina la FFT.
3. Los tests unitarios usan campos sintéticos con fondo plano y deriva ≤ 12 px, con una
   aserción laxa: pasan mientras los datos reales fallan.
4. `PlateConfig` nunca recibe `fwhm` en la serie: el `chk_seeing` («la apertura sigue el
   seeing») no llega al motor de serie.
5. Ganancia y RON vacíos en Ajustes (`ccd_gain = None`) → `ccd_flux_error` devuelve `None` →
   el error total es casi solo la dispersión del ensemble: de ahí los `err = 0.5` «honestos»
   pero inútiles.
6. Comps: 9 estrellas, todas brillantes (V 11.4–12.7 frente al objetivo 12.3), y las del
   este y norte desaparecen con la deriva; su V derivada de Gaia dispersa 0.38 mag. Se mide en
   banda V unos datos cuyo nombre es «Rcal» y sin tarjeta `FILTER`.
7. **No existe periodograma**: solo se puede plegar con un período de catálogo
   (`lightcurve_view.fold_period_d`). Sin LS, sin PDM, sin FAP, sin el gráfico tipo informe.

### 1.2 Honestidad sobre la línea base

Con **una sola noche (~1 ciclo)** el período no se puede fijar: un Lomb–Scargle sobre esta
serie da 0.153 d y el informe 0.12695 d. El propio autor lo resuelve sumando ASASSN
(«...WITH ASASSN»). NightScribe ya tiene el canal AAVSO con token (`sources/aavso.py`, hoy solo
la última magnitud) y el contexto ZTF/ALeRCE (`sources/surveys.py`, que satura en V ≈ 12.3).
Sumar la fotometría de la comunidad es, por tanto, la vía natural para cerrar el período.

---

## 2. Fase A · Alineación real, por defecto y honesta

**A1 · `core/register.py` reescrito como cascada (no búsqueda ciega)**

- `_source_image(data)`: se resta el fondo (mediana por bloques, reescalada) y se recorta a
  ≥ 0. Es lo que hoy envenena la FFT: el gradiente de cielo y el viñeteo dominan la correlación.
- `estimate_translation(ref, src)`: correlación de fase con ventana de Hann sobre la imagen de
  fuentes y refinado subpíxel por parábola. Medido: **0.024 s** y 0.08 px, contra 4.6 s de hoy.
- `detect_stars(data)`: máximos locales vectorizados sobre la imagen de fuentes decimada ×2,
  refinados a subpíxel; devuelve `[x, y, pico]` y descarta saturados y bordes.
- `estimate_transform(ref, src, guess=None, ref_stars=None)`: (1) traslación siempre, por
  correlación de fase; (2) detección y emparejamiento de estrellas con ese desplazamiento;
  (3) **solo si** el residuo físico supera el umbral se ajusta la rigidez (rotación) con
  lstsq + sigma-clip; (4) si el ajuste con ángulo no mejora el residuo al menos un 25 %, se
  prefiere **ángulo 0** (navaja de Occam: mata el fallo de los `-166°`).
- **Calidad física**: `{n_matched, rms_px, angle_deg, shift_px, scale}`; se jubila `peak/std`.
  `trusted(tr)` exige `n_matched ≥ 6` y `rms_px ≤ 0.3`.
- Un frame que no pasa **hereda el transform del anterior** y se marca `align_failed`: nunca un
  mal transform en silencio.
- Encadenado frame a frame (no todo contra el frame 1): resuelve la multinoche con repunteo sin
  transformadas gigantes.

**A2 · `series_measure.py`: el remapeo que falta**

Sacar el remapeo del centroide fuera de `if warped_mask is not None`. Se guarda
`frame["ref_xy"]` para el gate de guiado y se mantiene `res.col/row` nativo para el FWHM y la
apertura. `_group_centroid` prefiere `ref_xy` cuando existe.

**A3 · Por defecto y visible**

`SeriesConfig.align = "auto"` (`off` / `auto` / `translation` / `similarity`), combo nuevo en
`gui/ufe_advanced_dialog` (`.ui` + código, ADR-005) con texto llano, persistido en `cfg_json`.
`sweep_aperture` con WCS por frame.

**A4 · Diagnóstico en lenguaje llano**

`SeriesResult.align_report`: frames alineados, desplazamiento mediano y máximo en px y arcmin,
lista de fallos. Se muestra en el resumen de la serie y va a las notas del CSV: «los frames
derivan 134 px (2.2'): alineación aplicada», «frame N no alineable: se usa el anterior».

**A5 · Rendimiento**: ≤ 0.05 s/frame (traslación) y ≤ 0.3 s/frame (con estrellas); los 244
frames en menos de 60 s.

**Aceptación A**: correlación **≥ 0.8** con el informe de FotoDif; residuo **≤ 0.02 mag**;
check **≤ 0.01 mag**; `unusable` → **0**. (Medido con el prototipo: 0.875 / 0.0119 / 0.005.)

---

## 3. Fase B · Errores y comps

- **B1 · Ganancia**: leer `EGAIN` / `GAIN` / `GAINK` / `CCDGAIN` y `RDNOISE` / `READNOIS` de la
  cabecera; si no hay, decir de dónde sale el error y **nunca** un `err = 0.5 mag` silencioso.
- **B2 · Comps**: contención en el **rectángulo real del sensor** (hoy `fov_arcmin` actúa de
  cuadrado y coloca comps que la deriva barre fuera), ventana de Δmag respecto al objetivo,
  aviso con menos de 4 útiles, banda desde `FILTER` cuando exista.
- **B3 · Apertura**: pasar el FWHM por frame a `PlateConfig` en la serie (el `chk_seeing` hoy
  no llega) o activar T3.
- **B4 · Detrend** por defecto `airmass` para `variable` y `hads` (sin detrend en tránsitos),
  con la curva cruda siempre visible (D11, D13).

---

## 4. Fase C · Período, plegado e informe

- **C1 · `core/periodogram.py`** (numpy puro): Lomb–Scargle generalizado (media flotante,
  Zechmeister) + PDM; rejilla con sobremuestreo y **ventana espectral** para marcar los alias
  de un día; pico, FAP (bootstrap sembrado y cota de Baluev) y ciclos cubiertos.
- **C2 · `viz/phase_view.py` + `gui/phase_dialog.py` + `.ui`**: dos paneles (periodograma con
  los niveles de FAP y el pico, y plegado a 0–2 ciclos con color por noche, barras de error y
  media binnada). Método, rango de frecuencias, «guardar período en el proyecto» y exportación
  PNG/CSV. Entrada desde la ventana de la visita y desde la pestaña Medir del editor.
- **C3 · Honestidad de la línea base y datos de la comunidad**: con menos de 2 ciclos se avisa
  explícitamente y se ofrece sumar fotometría AAVSO, extendiendo `sources/aavso.py` con
  `fetch_lightcurve(name, days, token)` (mismo patrón de token y caché que las vigilias).

---

## 5. Fase D · Verificación

- **D1 · Fixture real** `tests/data/v0526per/`: 8 frames recortados 512² alrededor del
  objetivo, cubriendo toda la deriva, con la WCS de referencia y una secuencia derivada del
  propio recorte (offline, sin catálogo). Aserción: dispersión baja y ningún `unusable`.
- **D2 · Funcional** con el dataset completo (se salta si la carpeta no está): correlación
  ≥ 0.8 y residuo ≤ 0.02.
- **D3 · Sintético realista** (gradiente, viñeteo, 80 px de deriva y 2° de rotación): el caso
  que hoy falla.
- **D4 · Paridad opcional** con autophot / astroalign bajo `importorskip` como referencia,
  nunca como dependencia de producción.
- **D5 · Documentación**: enmienda a ADR-048 (D17 y D44: alineación por defecto, algoritmo,
  métrica de calidad, el remapeo), ADR nuevo de análisis de períodos (bilingüe),
  `PHOTOMETRY` y `SEQUENCES` en ambos idiomas e i18n. ADR-004 se mantiene: sin dependencias
  nuevas.

---

## 6. Orden de trabajo

1. **A1 + A2 + D1**: no se puede validar la alineación sin el fixture. Es la entrega que
   arregla el desastre.
2. **A3 + A4 + A5**: GUI, por defecto y diagnóstico.
3. **B1–B4**: independientes y pequeños.
4. **C1** en paralelo con B; después **C3** y **C2**.
5. **D2–D5** y documentación.

## 7. Riesgos y cómo se acotan

- La rigidez por estrellas es código nuevo: la vía por traslación resuelve el caso real medido
  y la rotación solo entra si la métrica física dice que hace falta.
- Multinoche con repunteo: se resuelve con el encadenado frame a frame, no con una referencia
  única.
- Remuestreo: se mantiene `coords` (la PSF nunca se remuestrea); `warp` queda como vía
  explícita.
- El período con una noche es degenerado: se dice, no se disimula, y se ofrece la vía AAVSO.
