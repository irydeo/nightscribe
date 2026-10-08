# P5b: la calibración, dentro de la astrometría

**Estado**: hecho. **Origen**: el autor preguntó por qué el pseudo-flat no se
veía por ningún lado. Tenía razón, y el motivo era un hueco de verdad.

## El hueco

El pseudo-flat (P5) existía en la pestaña **Calibration** del editor, con su
casilla, opt-in y apagada por defecto. Pero **la astrometría no calibraba**:
`TrackStackWorker` y todo el camino del track & stack leían las tomas con
`calibration.read_image`, en crudo, y la pestaña Astrometría no tenía ni un
control de calibración. O sea:

- la biblioteca de masters no llegaba al apilado del objeto débil;
- el pseudo-flat tampoco;
- y la pestaña Calibration solo producía **copias exportadas**, que la
  astrometría no lee (lee los originales de la visita).

Contradecía lo que dice ADR-061 con sus propias palabras: «el apilado de
objetos débiles (track & stack) no funciona sin calibrar».

## Por qué importa, medido

Construido el pseudo-flat de la visita real de 2025 UR y mirada su parte
suave (la que no son motas):

| | valor |
| --- | --- |
| Flat en el centro | 1,033 |
| Flat en las esquinas | 0,953 |
| **Error sistemático si el objeto y las comparsas caen en zonas distintas** | **0,087 mag** |

Y eso es solo el viñeteado: el máximo del flat es 1,590 (una mota), así que
un objeto que caiga **sobre** una mota se va mucho más. Al MPC le importa la
décima de magnitud.

## El arreglo

1. **`calibration.FrameCalibrator`**: un **cargador** que calibra al leer.
   El motor lee cada toma muchas veces y en trozos (el registro quiere el
   fotograma entero, el barrido quiere una caja por candidato), así que
   escribir copias calibradas costaría gigabytes de I/O por visita; aplicar
   la receta mientras se leen los píxeles cuesta una división y mantiene la
   promesa de ADR-061 (calibración en memoria). La receta se resuelve del
   header de **cada** toma y se **cachea** por (cámara, ganancia, exposición,
   filtro, temperatura redondeada a la tolerancia): una visita es una
   consulta y no ciento cuarenta.
2. **`track_stack.read_pixels`**: cierra las **dos convenciones** de cargador
   (array, o array y cabecera) en un sitio y no en cada llamada.
3. **La astrometría lo usa**: el `loader` llega al registro, al apilado base,
   al barrido, a los grupos, a las pilas de estrellas, a las ventanas de las
   comparsas y a la medida astrométrica.
4. **La casilla donde se necesita**: en la pestaña **Astrometría**,
   «Calibrate the frames», opt-in y apagada por defecto, con su tooltip
   diciendo la receta de dónde sale, que un flat de verdad siempre gana y
   que el pseudo-flat necesita dither.
5. **El ajuste visible**: `calib_pseudo_flat` era un ajuste sin interfaz (la
   regla de la casa dice que ningún ajuste sea invisible). Ahora tiene su
   casilla en **Ajustes → Calibración**, junto a la biblioteca de masters, y
   es el valor por defecto, no el interruptor: la astrometría tiene el suyo
   para poder calibrar **una** ejecución sin cambiar lo que hace la app.
6. **La nota del run lo dice**: «Calibradas 139 tomas (dark/bias: …, flat:
   …)» o «(ningún master ha encajado)», con los avisos del pseudo-flat.
   Una magnitud no sale nunca sin saber con qué se midió.

## Medido con el instrumento (P4)

La misma inyección (12.000 ADU, movimiento 1,5 px/toma a PA 90°) sobre las 30
primeras tomas de 2025 UR, con y sin calibración:

| | ¿Detectado? | SNR | Flujo medido | Error de posición |
| --- | --- | --- | --- | --- |
| Sin calibrar | sí | 32,9 | 12.183 ADU | 0,42 px |
| **Con el pseudo-flat** | sí | **34,0** | **11.415 ADU** | 0,42 px |

**Razón de flujo 0,9370 → 0,0707 mag** de corrección sistemática, que es
justo lo que prometía el viñeteado medido (0,087 mag en el peor caso; el
objeto de la inyección cae cerca del centro, donde la corrección es menor).
El SNR sube algo porque el flat aplana el fondo. El pseudo-flat se construye
en **3 s** para 30 tomas (12 s para 140).

Y una mentira que salió en el resumen y se arregló: la receta avisaba «no
flat for this filter» **mientras** el pseudo-flat se estaba aplicando. Ese
aviso ahora se retira cuando el pseudo-flat lo sustituye: repetirlo al lado
sería mentir en la misma línea.

## El fallo que apareció por el camino

Al escribir el test de la inyección con otra semilla, la detección se cayó en
silencio. La causa, medida: **`_roundness` usaba `np.median`** (no
`nanmedian`) sobre el apilado, y el apilado lleva **NaN** donde un fotograma
no cubrió la caja (el borde del footprint, que existe **siempre que la
secuencia está dithered**). Un solo NaN de 16.384 volvía la redondez NaN, y
`_score` descartaba el candidato entero: **una detección fallando en
silencio**, justo en la condición que queremos (dither).

Arreglado con dos ayudantes, `_local_sky` y `_local_sigma`, que ignoran los
NaN y por los que pasa **todo** el cielo del módulo (`_score`, `detect` y
`_roundness`), con su test de regresión: un apilado con NaN sigue siendo
puntuable y detectable.
