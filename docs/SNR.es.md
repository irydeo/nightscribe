# Cómo NightScribe sube el SNR del objeto débil

> Las técnicas, los filtros y las decisiones que hacen que un objeto débil
> emerja del ruido, explicadas **a tres niveles**: para el observador que
> usa la app, para el astrónomo que quiere las cuentas, y para quien
> mantiene el código.
>
> El plan de la campaña y los resultados fase a fase viven en
> `docs/PLANS/astrometry-snr/`. Aquí está el **qué y el porqué**, no el
> diario de obra.

---

# 1. Para el observador

## De qué va esto

Un NEO débil no aparece en una toma suelta: su señal es del orden del ruido
del cielo. Lo que lo hace aparecer es **sumar muchas tomas** a lo largo de
su movimiento, y todo lo de esta lista existe para que esa suma llegue más
lejos. En tus datos de 2025 UR, con 3 s de exposición, la señal del objeto
en **una** toma es unas 2 veces el ruido; con 30 tomas apiladas es unas 11
veces, y el MPC pide 20 para aceptar una observación. La diferencia entre
«lo veo» y «lo puedo enviar» está exactamente ahí.

## Las seis cosas que la app hace por ti

**1. No pierde tomas.** Si tu visita mezcla dos tandas de observación (una
pausa, un re-apuntado), la app lo detecta, ajusta la pequeña rotación del
campo entre ellas y **apila las dos**. Antes se quedaba con la primera y
tiraba la segunda sin que te enteraras. En tu visita de 140 tomas: de 78 a
**139 usables**, y el SNR del apilado subió **×1,48**. Lo que sí deja fuera,
lo dice y dice **por qué**: «muy pocas estrellas» (una nube) o «sus
estrellas no concuerdan con el ajuste» (una estela de satélite), y también
«estas tomas no contienen el objeto» cuando el campo de la segunda tanda
apunta a otro sitio.

**2. Pesa cada toma por su ruido.** El método **Ponderada (1/σ²)** es el
mismo recorte de siempre y después cada toma cuenta según el ruido de **su**
cielo. En una noche estable sale lo mismo que el recorte sigma; en una noche
con nubes finas o Luna es lo que evita que una toma mala arrastre la media.
Es opt-in porque, medido, en una noche buena no cambia nada.

**3. Mide con el filtro adaptado.** Además de la medida por apertura, la app
te dice lo que leería el **filtro adaptado**, que pesa cada píxel por la
forma esperada de la estrella en vez de sumar un círculo. Medido sobre tus
tomas: **1,55 a 1,63× más SNR** que la apertura. El reporte sigue usando la
magnitud de la apertura (es la que valida el validador del MPC); el filtro
se enseña al lado.

**4. Te dice si el objeto sale estelado.** Si el objeto se ha movido durante
la exposición, sale alargado, y la app te lo dice con un número: «el objeto
sale con una estela de 2,4 px según PA 245°». Eso se arregla en la próxima
noche acortando la exposición, y es la mejora más barata que existe. Por
debajo de 1,5 px el objeto se llama redondo, porque una estrella redonda
puede leer hasta ahí solo por el ruido.

**5. Te dice hasta dónde has llegado.** Al terminar el run, la **magnitud
límite a 5σ** de esa noche, medida con tus propias estrellas, y los
**residuos de la solución** con la peor celda de una rejilla 4×4 (donde se
ve una escala mal o un chip inclinado). Y si el campo **no** está limitado
por el cielo (Luna, exposición corta, comparsas saturadas), la app te avisa
de que esa cifra no se debe citar.

**6. Puede construirte un flat de las propias tomas.** Si no tienes flats
(lo normal), la casilla de la pestaña Calibración construye un
**pseudo-flat**: las motas y el viñeteado están fijos en el fotograma y
sobreviven a un percentil bajo entre tomas, mientras que las estrellas se
mueven y no. Necesita que la secuencia esté dithered, y si no lo está te
avisa. Un flat de verdad siempre gana.

**7. Calibra las tomas antes de apilarlas.** La casilla **Calibrar las
tomas** de la pestaña Astrometría aplica la receta (los masters de la pestaña
Calibración: dark/bias y flat) a cada toma **según se lee**, así que el
apilado nunca necesita copias calibradas en disco. Importa más de lo que
parece: sin flat, el objeto y las comparsas caen en zonas distintas del
viñeteado, y **medido en una visita real eso vale 0,087 mag** de error
sistemático en la magnitud. Si no tienes flat, la app construye uno de las
propias tomas (necesita dither, y te lo dice); un flat de verdad siempre
gana.

## Lo que puedes hacer tú, que es lo que más gana

- **Más tomas, no más exposición.** El SNR va con la raíz del número de
  tomas: doblar las tomas sube el SNR un 41 %. Doblar la exposición, en
  cambio, estela el objeto si se mueve.
- **Deja que la app te diga la exposición máxima.** La ficha del objeto ya
  calcula la exposición antes de que el objeto deje estela.
- **Dither.** Mover un poco el telescopio entre tomas no solo quita el
  patrón fijo del sensor: es lo que hace posible el pseudo-flat.
- **No tires la segunda tanda.** Si paras y vuelves a apuntar, es una visita
  distinta para el MPC pero la app las apila juntas y lo agradece.

## Lo que la app NO hace, y por qué

**No mete un denoiser de IA en la medida.** Existen herramientas de
reducción de ruido con redes neuronales, muy buenas para que una foto quede
bonita, y hay una de pago con línea de comandos. **No entran aquí**: un
filtro así **correlaciona el ruido**, así que la dispersión que midiéramos
después saldría optimista y las incertidumbres que se envían al MPC
dejarían de ser ciertas; y puede **mover el centroide**, que es de lo que
vive la astrometría. El suelo de SNR 20 del MPC existe justo para que no se
cuelen detecciones marginales, y subir el SNR con un denoiser es
exactamente lo que ese suelo quiere evitar. La decisión está escrita en
ADR-063; si algún día entra, será solo para presentación y lo juzgará el
instrumento de inyección-recuperación.

---

# 2. Para el astrónomo

## El problema, en una línea

Para una fuente limitada por el cielo, la señal es `F` y el ruido de la
medida es `σ·√N_ef`, donde `N_ef` es el número efectivo de píxeles que se
suman. Subir el SNR es, por tanto, **sumar más señal** (más tomas) o
**bajar `N_ef` sin perder señal** (pesar mejor). Todas las técnicas de abajo
son una de las dos cosas.

## T1. Apilar las dos tandas de una visita

El SNR crece con `√N`. Recuperar 62 tomas de 140 no es cosmética: es
`√(139/78) = 1,34` en el mejor caso. **Medido** sobre el apilado de
estrellas de 2025 UR: **1.826 → 2.702 (×1,48)**.

El registro es una traslación más una rotación rígida sobre el centro. La
puerta de calidad dejó de ser un píxel absoluto y pasó a ser una **fracción
del FWHM medido** (0,25, con suelo en 0,5 px), porque lo que importa es
cuánto ensancha el apilado la desalineación, y eso es una razón: 0,8 px es
inocuo sobre 5,4 px de seeing y mucho sobre 1,2 px.

Y una regla de honestidad: **un fotograma que no contiene el objeto no se
apila**. Registrado no es lo mismo que útil, y un campo desplazado solo
añade ruido donde se mide.

## T2. Co-adición por 1/σ²

Combinar `N` medidas independientes de la misma señal con ruidos `σ_i`
distintos tiene un óptimo de manual: la media ponderada por el inverso de la
varianza, porque minimiza la varianza del resultado.

    σ²_combinada = 1 / Σ(1/σ_i²)      frente a     σ²_media = Σσ_i² / N²

**Medido** en las dos visitas: la dispersión del ruido entre tomas es del
4,0 % en 2025 UR (ganancia 1,003×) y del 11,0 % en 2026 PY9 (ganancia
1,022×). Es decir, **casi nada en estas dos noches**, y eso se publica tal
cual. Con el modelo de la propia medida de 2025 UR, si una décima parte de
las tomas saliera con el triple de ruido (nubes finas), la ganancia sería
del **28 %**: es un seguro para la noche que se rompe, no una bala de plata.

Y tiene un segundo papel: el `σ_i` por fotograma es el **modelo de ruido**
que necesita el filtro adaptado.

## T3. El filtro adaptado

Con una forma conocida `m` (normalizada, `Σm = 1`) y ruido blanco `σ` por
píxel, el mejor estimador **lineal** del flujo es

    A = Σ m·(p − cielo) / Σ m²            SNR = A·√(Σm²) / σ

y su SNR es el mayor que **cualquier** filtro lineal alcanza sobre esos
datos (Cauchy-Schwarz: el peso óptimo es proporcional a la forma). Una
apertura es el caso `m = 1` dentro del círculo, que da a las alas ruidosas
el mismo peso que al núcleo: **no** es óptima.

El área efectiva es `N_ef = 1/Σm²`, así que la ganancia sobre una apertura
de área `N_ap` es `√(N_ap/N_ef)`.

**Medido** en el apilado real de 139 tomas de 2025 UR (FWHM 4,63 px,
apertura r = 6,3 px, `N_ap = 203`, `N_ef = 80`):

| Pico de la estrella | SNR apertura | SNR filtro | Ganancia |
| --- | --- | --- | --- |
| 19.744 | 1.088 | 1.771 | 1,63× |
| 15.792 | 1.227 | 1.909 | 1,56× |
| 15.552 | 995 | 1.565 | 1,57× |
| 14.560 | 923 | 1.497 | 1,62× |

y `√(203/80) = 1,59` es lo que predice la fórmula: la teoría y la medida
coinciden.

**Verificación por Monte Carlo** (200 realizaciones): la ganancia medida cae
sobre `√(N_ap/N_ef)` con un 5 % de margen, y el flujo del filtro tiene menos
dispersión que el de la apertura con el mismo ruido.

## T4. La estela

Un segmento uniforme de longitud `L` convolucionado con una PSF redonda de
anchura `σ` da una gaussiana cuyo eje largo lleva

    σ_largo² = σ² + L²/12

(variante de un segmento uniforme), así que de los segundos momentos se
recupera `L = √(12·(σ_largo² − σ_menor²))`, y el ángulo de posición del eje
mayor sale de los autovectores de la covarianza. Con la forma medida, el
filtro adaptado se construye con una **PSF de línea** y filtra el objeto
como la línea que de verdad es.

Los momentos son sensibles a la ventana: con 4 FWHM el ruido de las alas
domina y una estrella **redonda y brillante** reportaba **1,56 px de
estela**. De ahí la ventana de **2 FWHM** y el umbral a **1σ** sobre el
cielo, y de ahí `TRAIL_MIN_PX = 1,5`: por debajo, el objeto se llama
redondo.

## T5. El diagnóstico de la noche

**Magnitud límite.** Para una fuente limitada por el cielo,
`log10(SNR) = a + b·mag` con `b = −0,4` (una magnitud es un factor
`10^0,4 = 2,512` en flujo y el ruido no sabe lo brillante que es la
estrella). Ajustando esa recta a las estrellas medidas y resolviéndola para
SNR = 5 sale la magnitud límite **de esa noche**.

El ajuste es **Theil-Sen** (la mediana de las pendientes de los pares), no
mínimos cuadrados con recorte: con siete puntos y una comparsa saturada el
recorte no repara una recta arrastrada (la recta mala infla la MAD contra la
que se recorta) y el límite se iba **0,5 mag**; la mediana de 21 pares no la
mueve. Además no hay umbral que elegir, que con cinco puntos es una
corazonada disfrazada de parámetro.

**Y el pendiente es la comprobación**: `b` debe salir ≈ −0,4. **Medido** con
14 estrellas del apilado real de 139 tomas: **−0,394**, un 1,5 % de acuerdo
con la ley. Un campo que sale lejos de ahí (Luna, exposición corta,
saturación) se marca y la cifra no se cita.

**Calidad de la solución.** La mediana del residual por celda de una rejilla
4×4: un número para toda la placa esconde las esquinas, que es donde se ve
una escala mal o un chip inclinado. Mediana por celda (un emparejamiento
malo no puede pintar una esquina de rojo él solo) y una celda sin estrellas
queda **vacía**, nunca a cero.

## T6. El pseudo-flat

El polvo y el viñeteado están **fijos** en el fotograma; las estrellas **se
mueven**. Un percentil bajo entre tomas (33 %: el cielo y las estrellas solo
añaden luz) se queda con el tren y se sesga lejos de las estrellas, y el
suavizado (41 px, mucho mayor que la PSF y mucho menor que el viñeteado) se
lleva lo que quede. Normalizado a mediana uno, es un flat multiplicativo.

No sustituye a un flat de verdad: mide la respuesta del tren **por** la
forma del cielo, así que el error de flat es mayor. Es el respaldo honesto, y
la receta dice cuál se usó.

**Cuando las estrellas no se mueven, no hay pseudo-flat.** Con montura
sidereal (el caso normal) la misma estrella cae en el mismo píxel toda la
noche, así que el percentil se la queda y el «flat» divide cada estrella por
sí misma: un flat que lleva las estrellas es peor que ningún flat. Medido en
la visita 2025 FG18 del autor, una comparada sobre una estrella brillante
salía **1,08 mag** desviada. Lo que sí queda de esas tomas es el
**viñeteado**, que es suave y fijo: la app enmascara las fuentes (lo que está
a más de 5σ sobre el percentil suavizado, dilatado 12 px) y ajusta una
superficie de grado 4. Medido contra un master flat real de la misma noche,
la concordancia es del ~3 % (mediana 0,9963; p5–p95 0,954–1,045) y la
estructura fina que no corrige (el polvo) vale 0,6 % = 0,007 mag. La receta
dice `vignette_model` y la nota dice qué es y qué no corrige.

## T7. La calibración, dentro del apilado

Un apilado de tomas sin calibrar conserva el pedestal, la corriente térmica,
las motas y el viñeteado. Para la **posición** importa poco (el centroide es
local), pero para la **magnitud** importa mucho: el cero punto se mide con
las comparsas, y si el objeto cae en una zona con distinta transmisión que
ellas, el error entra directo. Medido en una visita real, la parte suave del
viñeteado vale **0,087 mag**, y una mota bajo el objeto mucho más.

La receta es la de ADR-061 y se aplica **al leer** (`FrameCalibrator`), no en
copias: el motor lee cada toma muchas veces y en trozos, y una copia
calibrada por toma serían gigabytes de I/O. Medido con el instrumento de P4,
la misma inyección con y sin el pseudo-flat: **0,0707 mag** de corrección y
el SNR de 32,9 a 34,0.

## T8. Lo que mide el resultado: inyección y recuperación

Todo lo de arriba son afirmaciones. El instrumento que las mide mete una
fuente de flujo **conocido**, en un sitio conocido, moviéndose a una
velocidad conocida, en **copias** de las tomas reales, corre la cadena real
encima y compara con la verdad.

**Medido** sobre las 30 primeras tomas de 2025 UR (3 s cada una, movimiento
inyectado 1,5 px/toma):

| Flujo | Mag equivalente | ¿Detectado? | SNR | Error de posición |
| --- | --- | --- | --- | --- |
| 12.000 ADU | 17,93 | sí | 32,9 | 0,14 px |
| 5.000 ADU | 18,88 | sí | 13,2 | 0,14 px |
| 2.000 ADU | 19,87 | sí | 5,6 | 0,14 px |
| 800 ADU | 20,87 | no | 1,7 | (no aplica) |
| **sin inyección** | (no aplica) | **no** | **0,0** | (no aplica) |

Con 30 tomas de 3 s: la puerta de detección (3,5σ) se cruza entre mag ≈19,9
y ≈20,9, el suelo de envío (SNR 20) se alcanza hacia mag ≈18,5, y la
posición se recupera a **0,14 px** incluso a SNR 5,6. El control sin
inyección da SNR 0: el pipeline no fabrica detecciones.

---

# 3. Para el desarrollador

## Dónde vive cada cosa

| Qué | Módulo | Entrada principal |
| --- | --- | --- |
| Registro, puerta de calidad, informe | `core/register.py`, `core/track_stack.py` | `register.trusted`, `register_sequence`, `registration_report`, `inside_frame` |
| Co-adición y pesos | `core/track_stack.py` | `combine`, `_sigma_clip_keep`, `frame_weights`, `_frame_noise` |
| PSF y filtro adaptado | `core/photometry.py` | `gaussian_psf`, `empirical_psf`, `measure_matched`, `psf_elongation` |
| Diagnóstico | `core/photometry.py` | `limiting_magnitude`, `quality_grid` |
| Pseudo-flat | `core/calibration.py` | `pseudo_flat`, `calibrate(pseudo_flat=…)` |
| Inyección y recuperación | `core/injection.py` | `inject_sequence`, `recover`, `completeness`, `truth_of` |
| Orquestación | `gui/workers.py` | `TrackStackWorker`, `CalibrationWorker` |
| Lo que ve el observador | `gui/ufe_trackstack_tab.py` | `_register_note`, `_shape_note`, `_diag_note` |

## Los invariantes que no se pueden romper

1. **Un fotograma que no contiene el objeto no se apila.** `inside_frame` es
   la puerta; `_indices` la aplica. Saltársela mete ruido justo donde se
   mide.
2. **Una lectura nunca es 1-D.** `calibration.read_image` devuelve 2-D
   siempre. Una «imagen» 1-D hace que scipy tome una rotación 2×2 por una
   matriz homogénea y reviente tres capas más arriba con un mensaje que
   culpa a la matriz.
3. **`_source_box` devuelve `None` cuando no hay solape**, y `_warp_to_box`
   devuelve un marco inválido **sin leer**. Nunca una caja «un píxel fuera».
4. **La medida por apertura y la del filtro comparten centroide, cielo y
   σ.** Si no, la comparación mide otra cosa.
5. **El filtro adaptado no sustituye a la apertura en el reporte.** El
   validador de ADR-022 y el MPC esperan la apertura; el filtro es una
   segunda opinión medida.
6. **La verdad de una inyección vive en la cabecera del fichero**, no en una
   variable de sesión.
7. **Un número sin su comprobación no se publica**: el pendiente del límite
   contra −0,4, el residuo del pseudo-flat contra el dither, la ganancia del
   filtro contra `√(N_ap/N_ef)`.

## Los errores que se encontraron midiendo (y que se repiten)

- **La ventana de los momentos.** Con 4 FWHM una estrella redonda y
  brillante reportaba 1,56 px de estela. Ventana de 2 FWHM y umbral 1σ.
- **El signo del desplazamiento subpíxel** en el banco de pruebas: la
  estrella caía a la esquina, el apilado salía con FWHM 12 px en vez de 4,6,
  y la primera medida del filtro adaptado dio **0,62** (parecía peor que la
  apertura) en vez de 1,6. **La primera medida de una mejora casi siempre
  mide el banco de pruebas.**
- **El recorte con pocos puntos** no repara una recta arrastrada: Theil-Sen.
- **`np.percentile` sobre bandas** cuesta 197 s donde `np.partition` cuesta
  12 s, con el mismo resultado.
- **El error de scipy** que culpa a la matriz cuando la imagen es 1-D.

## Cómo se extiende

- **Un método de combinación nuevo**: añadirlo a `METHODS`, implementarlo en
  `_combine_masked` o como función propia, y **usar `_sigma_clip_keep`** si
  recorta: el recorte tiene que rechazar los mismos píxeles en todos los
  métodos. Añadirlo al combo de la pestaña con su `tr()` y su tooltip.
- **Una medida nueva**: `measure_point` da el centroide y el cielo; una
  medida nueva debe **reutilizarlos** y devolver su propio `snr`, como hace
  `measure_matched`, para que las comparaciones sean comparaciones.
- **Un diagnóstico nuevo**: que devuelva `{"ok", "reason", …}` y que el
  `reason` sea un motivo en inglés (el núcleo habla inglés; la interfaz
  traduce), como `limiting_magnitude` y `quality_grid`.
- **Una técnica nueva de SNR**: medirla con
  `nightscribe inject` **antes** de creerla, y anotar el número en el
  comentario del código y en `docs/PLANS/astrometry-snr/`.

## Cómo se verifica

```bash
.venv/bin/python -m pytest tests/unit              # rápido, sin red
.venv/bin/python -m nightscribe inject <carpeta>   # el alcance real
```

Los tests de esta campaña: `test_track_stack_register.py` (la segunda tanda
y el fotograma fuera del campo), `test_track_stack_stack.py` (los pesos y
las dos rutas de apilado), `test_photometry_matched.py` (el filtro contra la
fórmula, Monte Carlo), `test_photometry_diagnostics.py` (el límite y la
rejilla), `test_calibration_pseudo_flat.py` (el pseudo-flat contra un
viñeteado conocido) y `test_injection.py` (el instrumento).
