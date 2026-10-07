# Informe de la campaña SNR

**Fecha**: 2026-10-05. **Rama**: `feature/astrometry-minor-planets`.
**Estado**: todas las fases hechas (B0, P0, P1, P2, P3, P4, P5, P6).
**Tests**: 2.887 en verde, i18n al 100 % (2.446 cadenas).

Este informe cierra la campaña: qué se hizo, **qué se midió**, qué no salió
como se esperaba, y qué queda. Las fichas por fase están al lado, y la
explicación de las técnicas a tres niveles está en `docs/SNR.es.md`.

---

## 1. Resumen en una tabla

| Fase | Qué | Resultado medido |
| --- | --- | --- |
| **B0** | Arreglo: el fotograma que no contiene la observación | El run ya no aborta; 4×4 en el ruido: 94,6 → 6,9 ms por toma |
| **P0** | Recuperar la segunda tanda de una visita | **78 → 139 tomas usables de 140**, y el SNR del apilado **×1,48** |
| **P1** | Co-adición por 1/σ² | Ganancia 1,003× (2025 UR) y 1,022× (2026 PY9); 28 % en el modelo con nubes |
| **P2** | Filtro adaptado y estela | **1,55 a 1,63× el SNR de la apertura**; la fórmula predice 1,59 |
| **P2b** | El filtro contra un **catálogo real** | 1,57× el SNR con 40 comparsas de Gaia; cero punto 0,0119 contra 0,0095 mag; **el filtro es el método por defecto** |
| **P3** | Diagnóstico de la noche | Pendiente **−0,394** frente al −0,400 de la física |
| **P4** | Inyección y recuperación | Puerta entre mag ≈19,9 y ≈20,9; posición a **0,14 px**; control sin inyección SNR 0 |
| **P5** | Pseudo-flat | 12 s por visita de 140 tomas; residual 1,342 % |
| **P6** | Decisión sobre nxt | ADR-063: no entra en la medida |

---

## 2. B0: el fallo que paró todo

**Síntoma**: un run real abortado con

```
ValueError: Expected homogeneous transformation matrix with shape (2, 2)
for image shape (0,), but bottom row was not equal to [0, 1]
```

y, como el reventón ocurre antes de medir, la fotometría no se calculaba.
**Una causa, dos síntomas.**

**La cadena**, que el mensaje esconde:

1. `_source_box()` devolvía una caja **justo fuera** del fotograma cuando la
   región pedida caía entera fuera (recortaba un borde y forzaba el otro).
2. `read_image` con esa caja devolvía un array **1-D vacío**.
3. scipy, al ver una imagen 1-D, tomaba la **rotación 2×2 por una matriz
   homogénea** y la rechazaba. El «for image shape (0,)» era la imagen, no
   la matriz.

**Por qué apareció ahora**: P0 hizo usables los fotogramas del segundo run
(a 884 px), y para ellos la caja puede caer fuera del sensor. Antes se
tiraban y el fallo era inalcanzable.

**El arreglo**, cinco piezas: `_source_box` dice `None` sin solape y
`_warp_to_box` devuelve un marco inválido **sin leer** (probado con una ruta
inexistente); la lectura nunca devuelve 1-D; el motor **excluye y cuenta**
los fotogramas que no contienen el objeto; `_frame_noise` pasa al 4×4; y el
comentario con el mensaje engañoso.

**El 4×4, medido** (fotograma real de 2048²):

| Muestreo | Valor | Tiempo | Error |
| --- | --- | --- | --- |
| entero (4,2 M px) | 332,10 ADU | 94,6 ms | referencia |
| 1 de cada 4×4 (262 k) | 332,10 ADU | 4,6 ms | **0,00 %** |

En el motor, con el recorte incluido: **6,9 ms por toma**, o sea 1,0 s por
visita de 139 tomas en vez de 13,2 s.

---

## 3. P0: los fotogramas que se quedaban en el suelo

**Antes**: 78 de 140 tomas usables; 62 fuera con un «no se pudieron alinear»
sin más.

**Diagnóstico medido**: las dos tandas están a **884 px** y el campo está
**girado 0,118°**. Con traslación sola el residuo es 1,5 px; con ajuste
rígido, **0,80 px**. Y la puerta de calidad era un absoluto de **0,75 px**:
62 tomas tiradas por 0,05 px.

**Arreglo**: la puerta pasa a ser **fracción del FWHM medido** (0,25, suelo
0,5 px; el FWHM de esa noche es 5,4 px, luego la puerta es 1,35 px); un
**segundo intento con rotación**, con las estrellas **certificándola** y el
ángulo limitado a 15° (una constante que estaba escrita y no se usaba); y un
informe que dice cuántas volvieron, cómo, por qué fallaron las que fallaron
y si la visita es **varias tandas**.

| | antes | después |
| --- | --- | --- |
| Tomas usables | 78 de 140 | **139 de 140** |
| Fuera | 62 | 1 (una nube, con su motivo) |
| Salvadas por rotación | 0 | 47 |
| Tandas detectadas | no se decía | **2** (77 + 62, 884 px, 289 s, −0,118°) |
| **SNR de una estrella en el apilado** | **1.826** | **2.702 (×1,48)** |

Y un dato que salió al medirlo: las dos tandas **solo se solapan en parte**
(884 px de 2048), así que las comparsas fuera de la zona común no se pueden
medir en todas las tomas.

---

## 4. P1: co-adición por 1/σ²

El σ de cada toma se mide **en el registro** (que ya lee los píxeles) y el
método nuevo es **el mismo recorte sigma y después la media ponderada de las
supervivientes**: el recorte se comparte, así que ambos rechazan los mismos
píxeles, y sin pesos es idéntico al sigma-clipped probado.

| Visita | σ por toma (min/mediana/max) | Dispersión | Ganancia |
| --- | --- | --- | --- |
| 2025 UR | 284,7 / 308,4 / 379,5 ADU | 4,0 % | **1,003×** |
| 2026 PY9 | 545,6 / 593,0 / 925,1 ADU | 11,0 % | **1,022×** |

**Es casi nada en estas dos noches**, y eso se publica tal cual. Con una
décima parte de las tomas al triple de ruido la ganancia sería del **28 %**:
es un seguro para la noche que se rompe. Por eso **el método por defecto no
cambia**.

---

## 5. P2: el filtro adaptado y la estela

Con una forma `m` conocida y ruido blanco `σ`, el mejor estimador lineal del
flujo es `A = Σm(p−cielo)/Σm²` y su SNR es el mayor que cualquier filtro
lineal alcanza (Cauchy-Schwarz). El área efectiva es `N_ef = 1/Σm²`.

**Medido** en el apilado real de 139 tomas (FWHM 4,63 px, apertura r = 6,3,
`N_ap = 203`, `N_ef = 80`):

| Pico | SNR apertura | SNR filtro | Ganancia |
| --- | --- | --- | --- |
| 19.744 | 1.088 | 1.771 | **1,63×** |
| 15.792 | 1.227 | 1.909 | **1,56×** |
| 15.552 | 995 | 1.565 | **1,57×** |
| 14.560 | 923 | 1.497 | **1,62×** |

y `√(203/80) = 1,59` es lo que predice la fórmula: **teoría y medida
coinciden**. El Monte Carlo (200 realizaciones) confirma que la ganancia cae
sobre `√(N_ap/N_ef)` con un 5 % de margen y que el flujo del filtro tiene
menos dispersión que el de la apertura.

**La estela**: de los segundos momentos y `σ_largo² = σ² + L²/12` sale la
longitud en píxeles y el ángulo de posición. La ventana y el umbral son
**medidos**: con 4 FWHM una estrella redonda y brillante reportaba **1,56 px
de estela**, de ahí la ventana de 2 FWHM, el umbral de 1σ y
`TRAIL_MIN_PX = 1,5`.

**El reporte sigue usando la magnitud de la apertura**; el filtro es una
segunda opinión medida, no un sustituto silencioso.

---

## 6. P3: el diagnóstico de la noche

**Magnitud límite**: de `log10(SNR) = a + b·mag` con `b ≈ −0,4`, resuelta
para SNR 5. El ajuste es **Theil-Sen** (mediana de las pendientes de los
pares): con mínimos cuadrados y recorte, una comparsa saturada se llevaba el
límite **0,5 mag**; la mediana de 21 pares no la mueve. Y el pendiente es la
**comprobación**:

| | medido | la física dice |
| --- | --- | --- |
| Pendiente (14 estrellas, apilado real) | **−0,394** | −0,400 |

**Calidad de la solución**: la mediana del residual por celda de una rejilla
4×4, con las celdas sin estrellas **vacías** (nunca a cero).

---

## 7. P4: el instrumento (inyección y recuperación)

Mete una fuente de flujo **conocido**, en un sitio conocido, moviéndose a una
velocidad conocida, en **copias** de las tomas reales; corre la cadena real
encima; y compara con la verdad. La verdad viaja **en la cabecera** de cada
copia y los originales **solo se leen** (hay un test que compara mtime y
tamaño).

**Medido** sobre las 30 primeras tomas de 2025 UR (3 s cada una, movimiento
inyectado 1,5 px/toma a PA 90°):

| Flujo | Mag equivalente | ¿Detectado? | SNR | Error de posición |
| --- | --- | --- | --- | --- |
| 12.000 ADU | 17,93 | sí | 32,9 | 0,14 px |
| 5.000 ADU | 18,88 | sí | 13,2 | 0,14 px |
| 2.000 ADU | 19,87 | sí | 5,6 | 0,14 px |
| 800 ADU | 20,87 | no | 1,7 | (no aplica) |
| 400 ADU | 21,62 | no | 0,5 | (no aplica) |
| **sin inyección** | (no aplica) | **no** | **0,0** | (no aplica) |

Lo que dice la tabla, con 30 tomas de 3 s:

- la **puerta de detección** (3,5σ) se cruza entre mag ≈19,9 y ≈20,9;
- el **suelo de envío del MPC** (SNR 20) se alcanza hacia mag ≈18,5;
- la **posición** se recupera a **0,14 px** incluso a SNR 5,6, que es la mitad
  del píxel;
- y el **control sin inyección da SNR 0**: el pipeline no fabrica
  detecciones.

La equivalencia en magnitud usa el flujo de una comparsa de mag 17,4 medida
en esas tomas (≈19.500 ADU), y es una equivalencia, no una medida.

---

## 8. P5: el pseudo-flat

El polvo y el viñeteado están fijos en el fotograma; las estrellas se mueven.
Un percentil bajo (33 %) entre tomas se queda con el tren y se sesga lejos de
las estrellas, y el suavizado (41 px, tres pasadas de caja) se lleva lo que
queda.

**El rendimiento, medido** (visita real de 140 tomas de 2048²):

| | Tiempo | Resultado |
| --- | --- | --- |
| `np.nanpercentile` | 197 s | mediana 4460 ADU, residual 1,341 % |
| **`np.partition`** | **12 s** | mediana 4461 ADU, residual 1,342 % |

**16× más rápido y el mismo flat.** Y el residuo del 1,342 % está por debajo
del umbral del 2 %, así que el flat se acepta y no avisa; el dither de esa
visita (440 px entre tandas) es lo que lo hace posible.

---

## 9. P6: la decisión sobre el denoiser de IA

**ADR-063**: un denoiser de IA **no entra** en el camino de la medida
(astrometría ni fotometría). Rompe el modelo de error (correlaciona el ruido,
así que las incertidumbres al MPC dejarían de ser ciertas), puede sesgar el
centroide, y el suelo de SNR 20 del MPC existe justo para que no se cuelen
detecciones marginales. Si algún día entra, es **solo para presentación**, y
lo juzga el instrumento de P4 comparando el error de centroide y la tasa de
recuperación.

---

## 10. Lo que no salió como se esperaba

Van escritos porque son la parte útil de un informe:

1. **P1 apenas gana en estas noches** (0,3 % y 2,2 %). Se esperaba más. El
   número dice que la ponderación es un seguro, no una mejora diaria, y por
   eso **no** se ha cambiado el método por defecto.
2. **El filtro adaptado parecía PEOR que la apertura** en la primera medida
   (0,62×). El culpable era el banco de pruebas: un desplazamiento subpíxel
   con el signo cambiado ponía la estrella en la esquina y el apilado salía
   con FWHM 12 px en vez de 4,6. Con el signo bien: 1,6×. **La primera
   medida de una mejora casi siempre mide el banco de pruebas.**
3. **La estela de una estrella redonda** salía de 1,56 px con la ventana de
   4 FWHM: los momentos se iban a buscar ruido a las alas.
4. **El recorte no repara una recta arrastrada** con pocos puntos, y el
   límite se iba 0,5 mag. De ahí Theil-Sen.
5. **El pseudo-flat tardaba 197 s** y resultó que el percentil estaba
   ordenando lo que no hacía falta ordenar.

---

## 11. Lo que queda

- **Barrer el movimiento** en la inyección (varias velocidades por flujo):
  es la palanca natural siguiente del instrumento, y la que diría si el
  barrido de velocidad del pipeline está bien centrado.
- **Pintar la rejilla 4×4** sobre la imagen: el dato está (`cells`), el sitio
  natural es el visor.
- **La PSF del filtro por zona o por comparsa**: el cero punto con catálogo
  real (P2b) midió que el flujo del filtro sigue a la forma de la PSF, y que
  donde esa forma cambia por el campo el filtro lleva un sesgo de posición
  (0,2 mag de escalón entre las dos tandas de una visita) que la apertura no
  tiene. Cuesta 0,002 mag de error de cero punto, así que es un ajuste de
  precisión, no una urgencia.
- **La magnitud en la inyección**: necesita las comparsas y su catálogo; la
  comprobación con un catálogo real (P2b) la sustituye para el caso que
  importa, que es la calibración.
- **La serie sobre un track & stack** (la pieza que quedaba del plan
  anterior): el motor de serie no tiene gancho de imagen pareada.
- **Volver a correr el caso real** con Horizons: es la comprobación que
  cierra B0 y la que enseña, en la nota del run, la estela, la ganancia del
  filtro, la magnitud límite y los residuos.
