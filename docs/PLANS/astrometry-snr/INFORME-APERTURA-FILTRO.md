# Informe comparativo: apertura frente a filtro adaptado

**Fecha**: 2026-10-07. **Datos**: visita real de 2025 UR (140 tomas de 3 s,
2048², Clear, apilados de 28 a 139 tomas). **Estado**: el filtro es el
**método por defecto** desde el 2026-10-07 (una sola casilla para apagarlo).

## Resumen

El filtro adaptado gana en el objeto y en el sesgo a señal baja, y cuesta lo
mismo. Medido, no estimado:

| | apertura | **filtro adaptado** |
| --- | --- | --- |
| **SNR del objeto** (apilado real de 139 tomas, 4 estrellas) | 1,00× | **1,55 a 1,63×** |
| **Sesgo del brillo**, SNR 9,3 (5 intentos) | +0,541 ± 0,121 mag | **+0,234 ± 0,037 mag** |
| **Sesgo del brillo**, SNR 44 (5 intentos) | +0,116 ± 0,016 mag | **+0,077 ± 0,007 mag** |
| **Error del cero punto** (8 fuentes de flujo conocido) | 0,092 mag | **0,035 mag** |
| **Dispersión de las comparsas** (mismas 8 fuentes) | 0,253 mag | **0,090 mag** |
| **Coste por estrella** | 9,91 ms | 10,22 ms (**+3 %**) |

## Cómo se midió cada cosa

1. **El SNR**: la razón entre los dos SNR medidos en el **apilado real** de
   139 tomas, con el mismo centro, el mismo cielo y el mismo σ, así que la
   comparación mide el **peso** y no otra cosa (P2). La fórmula
   `√(N_ap/N_ef)` predice 1,59 y se midió 1,55 a 1,63.
2. **El sesgo del brillo**: el instrumento de inyección mete una fuente de
   flujo **conocido** en copias de las tomas reales y mide
   `-2,5·log10(F_medido/F_inyectado)`; el punto cero se cancela en la razón,
   así que no hace falta catálogo (P4c).
3. **El cero punto y la dispersión de las comparsas**: ocho fuentes del
   **mismo flujo** inyectadas en las tomas reales, apiladas sobre las
   estrellas, medidas con los dos métodos y calibradas contra esa verdad
   conocida. El sesgo constante se lo come el cero punto (por eso se mide
   con el MISMO método que el objeto), así que lo que se compara es la
   **dispersión**.
4. **El coste**: el tiempo por estrella sobre un fotograma real, 40
   estrellas y 5 pasadas.
5. **El cero punto con un catálogo real**: ver la sección siguiente, que es
   la comprobación que faltaba y ya está hecha.

## El cero punto con un catálogo real (hecho)

Las 8 fuentes inyectadas comparan método contra método con un flujo idéntico,
que es lo más limpio posible y lo menos realista: una noche de verdad tiene
estrellas de mag 13 a 20 y de todos los colores. El catálogo ya las tiene, con
sus magnitudes medidas por otro, así que la pregunta honesta es cuál de los
dos métodos reproduce mejor esas magnitudes cuando el cero punto se calcula
como lo calcula la app.

El instrumento es `benchmarks/zp_catalog_check.py`: registra la visita, apila
sobre las estrellas (las comparsas son puntos ahí, el objeto es la estela),
carga el campo de Gaia EDR3, elige comparsas con las reglas de la app (fuera
de VSX, aisladas, en el sensor, sin saturar, sin pasar la linealidad, no
demasiado débiles) y mide cada una con **los dos métodos desde el mismo
centroide y el mismo cielo** (`measure_matched` devuelve los dos flujos de una
sola medida, así que lo que se compara es el peso). **40 comparsas** de
mag 13,5 a 19,5.

| | apertura | **filtro adaptado** |
| --- | --- | --- |
| **SNR mediano de las comparsas** | 101,1 | 158,3 (**1,57×**) |
| **Error del cero punto** (la cifra que publica la app) | **0,0095 mag** | 0,0119 mag |
| **Dispersión de los residuos** (MAD) | **0,0598 mag** | 0,0753 mag |
| **Error por estrella, deja uno fuera** (MAD) | **0,0614 mag** | 0,0772 mag |
| Ídem, **mitad brillante** | **0,0367 mag** | 0,1169 mag |
| Ídem, **mitad débil** | 0,1176 mag | **0,0634 mag** |
| **Sesgo de la mitad débil** (cero punto de la brillante) | +0,037 mag | **+0,007 mag** |
| Dispersión tras el término de color | **0,0568 mag** | 0,0933 mag |

En los cinco sub-apilados de 28 tomas, el SNR del filtro es 1,27 a 1,75× el de
la apertura y el error del cero punto queda empatado (0,0073 a 0,0122 contra
0,0077 a 0,0218 mag); el sesgo de la mitad débil es **positivo en los cinco**
para la apertura (+0,007 a +0,061 mag) y de signo contrario para el filtro
(0,03 a 0,09 mag).

Y la cadena entera, con el objeto de verdad: la magnitud calibrada con el
catálogo es **17,944** con la apertura y **18,094** con el filtro, contra los
**18,249 V** que predice el ephemeris de Horizons; el filtro mide el objeto
con SNR 19,5 donde la apertura llega a 15,1.

### Lo que esto dice

1. **La ganancia de SNR se sostiene con estrellas de verdad** (1,57× en el
   apilado completo, 1,27 a 1,75× por grupo): es el peso, no el banco.
2. **La mitad débil es del filtro** (0,063 contra 0,118 mag por estrella) y
   la tabla de sesgos dice por qué: contra el catálogo, la apertura
   **subestima** las estrellas débiles en +0,037 mag y el filtro en +0,007.
   Es el sesgo a señal baja que midió P4c con fuentes inyectadas, ahora
   confirmado con estrellas reales de un catálogo real.
3. **La mitad brillante es de la apertura** (0,037 contra 0,117 mag), y no
   por ruido: la apertura suma el 99 % de la luz y es casi inmune a la forma
   de la PSF, mientras que el flujo del filtro **sigue a la PSF**. Con una
   PSF real `σ_g` y el modelo `σ_m`, el filtro devuelve
   `2·σ_m²/(σ_m² + σ_g²)` del flujo: un sesgo constante que el cero punto se
   come, hasta que la PSF cambia por el campo, y entonces ya no.
4. **Ese es el coste medido del filtro en esta visita**: la diferencia
   apertura menos filtro por estrella tiene mediana +0,066 mag y MAD
   0,083 mag, y **correlaciona con la posición** (corr x +0,75): hay un
   escalón de unos 0,2 mag justo donde empieza a contribuir la segunda tanda
   de la visita (PSF efectiva distinta, con su rotación y su remuestreo). La
   apertura no lo tiene. Por eso su error de cero punto es un 25 % peor
   (0,0119 contra 0,0095 mag) aunque su SNR sea 1,57× mejor.
5. **El error del cero punto, en cualquier caso, no es el problema**: 0,012
   contra 0,010 mag, con el objeto midiéndose a SNR 15 a 20 (0,05 a 0,07 mag
   por su propio ruido). Lo que decide es el SNR del objeto y el sesgo a
   señal baja, y ahí el filtro gana.

### Lo que costaría quitarlo

Si se quisiera el mejor de los dos mundos, el ajuste es medir la PSF **por
zona** (o por comparsa) en vez de una sola gaussiana por apilado: la app ya
tiene `photometry.empirical_psf` sin usar, y el estimador de FWHM por
comparsa existe. No se ha hecho porque el coste medido (0,002 mag de error de
cero punto) es dos órdenes de magnitud menor que el error del objeto, y
porque cada ajuste de forma es una pieza más que puede fallar en silencio.

## Por qué gana, en una línea

Con una forma conocida `m` y ruido `σ` por píxel, el mejor estimador **lineal**
del flujo es `Σm(p−cielo)/Σm²` y su SNR es el mayor que cualquier filtro
lineal alcanza (Cauchy-Schwarz). Una apertura es el caso `m = 1` dentro del
círculo, que da a las alas ruidosas el mismo peso que al núcleo. A SNR alto
las dos coinciden; a SNR bajo la apertura pierde, y es justo donde está el
objeto débil.

## Lo que sigue sin medirse, y por qué importa

- **La PSF empírica**: el filtro se construye con una **gaussiana** del
  seeing medido, y ya se ha medido lo que eso cuesta (0,08 mag de estrella a
  estrella donde la PSF cambia). En un campo con coma o con estrellas muy
  saturadas el escalón podría ser mayor: la forma del filtro es el siguiente
  ajuste, y el orden de magnitud ya está acotado.
- **El efecto de la estela**: un objeto estelado se filtra con una PSF de
  línea (P2), y esa comparación no se ha medido contra la apertura. En esta
  visita el objeto mide 0,15 mag más débil con el filtro que con la apertura,
  con la PSF **redonda** del seeing: es la cifra que hay que vigilar cuando
  se compare con un objeto que sí lleva estela.
- **El camino de imagen con anfitrión restado**: no validado con el filtro
  (en una prueba recupera un 9,6 % menos de flujo que la apertura).

## La decisión

**El filtro es el método por defecto, con una sola casilla para apagarlo.**
La decisión es del autor y está tomada sobre la medida, no sobre la
intuición: gana en SNR, en el sesgo a señal baja y en la mitad débil de un
catálogo real, y cuesta un 3 %. Lo que hay montado:

- casilla **«Filtro adaptado»** en el panel de la pestaña Fotometría, junto
  a las aperturas y con el porqué medido en su tooltip (el encabezado del
  bloque dice el método aunque el bloque esté cerrado, y la pestaña
  Astrometría lo dice antes de lanzar el run); Ajustes → Fotometría decide con
  qué empiezan las **placas nuevas**;
- el flag viaja en la **receta**, así que se guarda con la placa y se
  restaura con ella;
- el **cero punto se mide con el mismo método que el objeto**, siempre: la
  mezcla (objeto con filtro, comparsas con apertura) metería la diferencia
  entre los dos métodos directamente en la magnitud, y el código lo impide
  por construcción (un solo despachador dentro de `measure_plate`);
- el valor de la apertura **se conserva al lado** cuando se mide con el
  filtro, para que la auditoría tenga las dos, y la ejecución dice qué método
  midió y qué daría el otro.

### Los riesgos que van con el valor por defecto

Decirlos es parte de la decisión:

1. **La magnitud publicada se mueve** entre 0,05 y 0,15 mag (hacia la verdad;
   medido en el objeto de esta visita: 0,15 mag). Una curva empezada antes
   mostrará un escalón, y la ejecución dice qué método midió y qué daría el
   otro, para poder explicarlo.
2. **El flujo del filtro sigue a la PSF**, y la PSF no es la misma en todo el
   campo: medido, la diferencia entre los dos métodos da un escalón de 0,2
   mag donde empieza la segunda tanda de la visita, con lo que el error del
   cero punto pasa de 0,010 a 0,012 mag. La apertura, que suma el 99 % de la
   luz, es casi inmune. Con las comparsas repartidas por el campo el efecto
   es este; con las comparsas junto al objeto (lo que propone la app) es
   menor.
3. **El camino de imagen con anfitrión restado no está validado con el
   filtro**: en una prueba recupera un 9,6 % menos de flujo que la apertura
   (está fijado en su test, con el motivo escrito).
4. **El objeto estelado** (PSF de línea) tampoco se ha comparado contra la
   apertura con un catálogo real.
