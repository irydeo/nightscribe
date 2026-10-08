# P4: inyección y recuperación (el instrumento)

**Estado**: hecho.

## Por qué

Todo lo demás de esta campaña es una **afirmación**: «el filtro adaptado
gana 1,6×», «la segunda tanda vale la pena apilarla». Este módulo es el
**instrumento** que mide la afirmación de punta a punta: mete una fuente de
flujo **conocido**, en un sitio **conocido**, moviéndose a una velocidad
**conocida**, en copias de las tomas reales, corre la cadena real encima, y
pregunta si ha vuelto y a cuánto ha caído de la verdad.

Dos cosas lo hacen honesto:

- **la verdad viaja en el fichero**: cada copia lleva `NS_INJ`, `NS_INJX` y
  `NS_INJY` en la cabecera, así que una recuperación se puede verificar a
  partir de las copias, meses después, sin fiarse de una variable que vivió
  en la sesión de alguien;
- **los datos del observador no se tocan**: la inyección escribe ficheros
  nuevos en su propia carpeta; los originales solo se leen. Hay un test que
  compara mtime y tamaño antes y después.

## Qué mide, y qué no

- Mide la **detección** (¿la puerta lo ve?), la **posición** (cuánto cae de
  la verdad) y el **SNR** de la fuente apilada.
- **No** mide la magnitud (necesita el catálogo de las comparsas) ni la
  **resolución de placa** (la WCS de referencia se le da hecha; el solve es
  un paso aparte y ya validado, ADR-051).

Así que una curva de completitud de aquí responde a «hasta dónde llega este
pipeline con estas tomas y este movimiento», que es la pregunta que el
observador tiene de verdad.

## El algoritmo

1. `inject_sequence(paths, flux_adu, rate_px, pa_deg, psf_fwhm, ...)`: lee
   cada toma, le suma una **gaussiana normalizada al flujo total pedido** en
   la posición que le toca de una recta, y escribe una copia en float32 con
   la verdad en la cabecera. La **fase subpíxel es aleatoria por toma**: si
   todas cayeran en la misma fracción de píxel, la recuperación estaría
   midiendo esa fracción y no el pipeline. La fuente que se sale del
   fotograma simplemente deja de inyectarse y la verdad dice en qué tomas
   está.
2. `recover(paths, motion, ref_wcs, ...)`: la cadena real **menos el solve**:
   registrar, colocar el objeto con la efeméride, apilar a lo largo del
   movimiento y preguntar a la puerta de detección. La posición vuelve en la
   **rejilla de referencia** (el origen de la caja se suma, y hay un test
   que fija por qué: sin él se leían 11 px de error donde había 0,14).
3. `completeness(paths, fluxes, ref_wcs, trials, ...)`: el barrido, con la
   **tasa**, el SNR y el error de posición de las que volvieron. El error
   está en la tabla y no solo el recuento porque **una tasa de 1 con el
   error disparado es una detección que no se debe reportar**.
4. `truth_of(paths)`: relee la verdad de las cabeceras.
5. CLI: `nightscribe inject <carpeta> --flujos 2000,5000,12000 --tomas 30
   --movimiento 1.5 --pa 90 --intentos 3`.

## Verificación

**Tests** (sin red, `tests/unit/test_injection.py`): una fuente brillante
vuelve a menos de 1 px de la verdad; una demasiado débil **no** se detecta
(el control: un pipeline que «detecta» esa está fabricando detecciones); la
verdad se relee de los ficheros; el movimiento sigue el ángulo pedido; los
originales no se tocan (mtime y tamaño); la curva va de 1 a 0; y el CLI
corre y devuelve 0.

**Sobre los datos reales** (2025 UR, las **30 primeras tomas**, 3 s cada
una, movimiento inyectado 1,5 px/toma a PA 90°):

| Flujo inyectado | Magnitud equivalente | ¿Detectado? | SNR | Error de posición |
| --- | --- | --- | --- | --- |
| 12.000 ADU | 17,93 | sí | 32,9 | **0,14 px** |
| 5.000 ADU | 18,88 | sí | 13,2 | 0,14 px |
| 2.000 ADU | 19,87 | sí | 5,6 | 0,14 px |
| 800 ADU | 20,87 | **no** | 1,7 | (no aplica) |
| 400 ADU | 21,62 | **no** | 0,5 | (no aplica) |
| **sin inyección** | (no aplica) | **no** | **0,0** | (no aplica) |

La equivalencia en magnitud usa el flujo de una comparsa de mag 17,4 medida
en estas tomas (≈19.500 ADU de flujo total), y es una **equivalencia**, no
una medida: lo que se mide es el flujo, la detección y la posición.

Lo que dice la tabla, con 30 tomas de 3 s:

- la **puerta de detección** (3,5σ) se cruza entre mag ≈19,9 y ≈20,9;
- el **suelo de envío del MPC** (SNR 20) se alcanza alrededor de mag ≈18,5;
- la **posición** se recupera a 0,14 px incluso a SNR 5,6, que es la mitad
  del píxel: el pipeline no solo ve el objeto, lo sitúa;
- y el **control sin inyección da SNR 0**: no hay detección fantasma.

## Lo que no se hizo

- **La magnitud** inyectada (necesita las comparsas y su catálogo): el
  instrumento mide detección y posición, que son las dos preguntas que no
  necesitan catálogo.
- **Barrer el movimiento** (varias velocidades por flujo): hoy se inyecta un
  movimiento y se mide; el barrido de velocidades es la siguiente palanca
  natural del instrumento.
