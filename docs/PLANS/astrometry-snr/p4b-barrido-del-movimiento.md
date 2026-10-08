# P4b: el barrido del movimiento, medido

**Estado**: hecho.

## Qué pregunta

El barrido de velocidad es lo que decide si un objeto real se encuentra: el
pipeline lo busca en una rejilla alrededor de la velocidad que dice la
efeméride. Hasta ahora eso era una afirmación («el barrido funciona»). El
instrumento de P4 se amplía para convertirla en dos números: **el error en
velocidad** (arcsec/min) y **el error en ángulo de posición** (grados),
inyectando una fuente que se mueve a una velocidad y un rumbo **conocidos** y
leyendo lo que el barrido elige.

## El fallo que apareció al medirlo, y era del instrumento

La primera medida decía que el barrido **no corregía nada**: con una
efeméride un 15 % equivocada se quedaba en la semilla aunque la verdad
estuviera a 5″/min, y con la semilla exacta elegía un candidato un 4,3 % más
rápido.

La causa era **mía**: `inject_sequence` movía la fuente un paso fijo **por
fotograma**, y la cadencia real es irregular (en la visita de 2025 UR va de
4 a 6 s entre tomas). Un paso fijo por fotograma **no es una recta en el
cielo**, así que el barrido, que ajusta una recta, estaba siendo juzgado
contra un movimiento que nadie había hecho.

Arreglado: la posición se calcula **por tiempo** (`rate_px_min`, píxeles por
minuto), y con eso la medida cambió de signo:

| inyectado | PA | verdad | hallado | error | PA err |
| --- | --- | --- | --- | --- | --- |
| 6 px/min | 90 | 11,83″/min | 11,83 | **+0,00** | 0,00° |
| 12 px/min | 0 | 23,68″/min | 24,27 | +0,59 | 4,50° |
| 17 px/min | 45 | 33,65″/min | 33,65 | **+0,00** | 0,00° |

Es decir: **el barrido encuentra la velocidad inyectada**, y cuando se
desvía lo hace en un paso de su propia rejilla.

## Hasta dónde corrige una efeméride equivocada

La pregunta que de verdad importa, porque la efeméride nunca es perfecta. Se
inyecta la verdad y se le da a la cadena una efeméride equivocada por un
factor (afecta a la colocación del objeto **y** a la semilla del barrido,
que es lo que pasa de verdad):

| factor de la semilla | semilla | verdad | hallado | error vs verdad |
| --- | --- | --- | --- | --- |
| 1,00 | 23,83 | 23,83 | 24,43 | +0,60 |
| 1,03 | 24,55 | 23,83 | 24,55 | +0,71 |
| 1,08 | 25,74 | 23,83 | 25,09 | +1,26 |
| **1,20** | 28,60 | 23,83 | **28,60** | **+4,77** |

Lo que dice la tabla:

- la rejilla es **±5 %** (5 pasos por eje), así que su resolución es de
  ~2,5 % en velocidad y unos pocos grados en PA;
- dentro de esa rejilla el barrido encuentra la verdad con un sesgo leve
  hacia velocidades **más rápidas** (de +0,6 a +1,3″/min en estas pruebas);
- **fuera de la rejilla no puede**: con la semilla un 20 % equivocada se
  queda en la semilla, porque la verdad no está entre sus candidatos. Es la
  respuesta honesta, y dice algo que el observador tiene que saber: la
  efeméride tiene que ser decente, el barrido **afina**, no rescata.

## Lo que se añadió

- `injection.sky_motion(motion, t_mid_jd)`: la velocidad y el PA de un
  movimiento, en **la misma convención que la semilla del barrido** (0° hacia
  +dec, 90° hacia +RA, sobre una línea base de dos minutos). Está escrita en
  el módulo y no importada porque la del barrido vive en el worker del GUI y
  el instrumento es núcleo: si las dos discrepasen, la verdad inyectada y la
  velocidad hallada dejarían de ser comparables, que es justo lo que esta
  pieza comprueba.
- `injection.pa_difference(a, b)`: la diferencia circular de dos ángulos de
  posición (359 y 1 están a dos grados, y restarlos daría 358).
- `recover(..., sweep=True)`: corre también el barrido, sobre la secuencia
  entera y en el recorte que contiene la estela, igual que la ejecución del
  observador.
- `motion_recovery(...)`: inyecta, mide y devuelve los dos errores.
- `motion_recovery(..., seed_factor=1.0)`: cuánto se equivoca la efeméride
  que se le da a la cadena.

## Verificación

**Tests** (sin red): la diferencia de PA es circular; el barrido encuentra el
movimiento inyectado dentro de la rejilla; y `sky_motion` mide el movimiento
inyectado en la convención del cielo (con la trampa escrita: un movimiento
en +y de **píxeles** es **norte**, o sea PA 0, no 90: las dos convenciones
son distintas a propósito y el test es donde se encuentran).
