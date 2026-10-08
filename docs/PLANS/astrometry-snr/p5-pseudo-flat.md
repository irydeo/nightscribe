# P5: el pseudo-flat

**Estado**: hecho.

## Por qué

La mayoría de los observadores no tiene flats, y ADR-061 solo podía avisar
«falta el flat de este filtro» y dejar el viñeteado y las motas del tren
óptico dentro de la toma. Un flat sintético hecho de las propias tomas
arregla eso sin pedirle nada más al observador.

## La física: el dither es el truco

El polvo del tren óptico y el viñeteado del sensor están **fijos en el
fotograma**, así que sobreviven a cualquier estadístico que se tome entre
tomas. Las estrellas **se mueven** de una toma a otra, así que un
**percentil bajo** entre las tomas las quita, y el suavizado se lleva lo que
quede de sus bultos. Lo que sale es un mapa multiplicativo del tren,
normalizado a mediana uno, que es exactamente lo que es un flat.

## Los tres parámetros, y por qué esos

| Parámetro | Valor | Por qué |
| --- | --- | --- |
| **Percentil** | 33 % | El cielo y las estrellas solo **añaden** luz: un percentil bajo se sesga lejos de ellos, y lo que quede de sesgo lo divide la renormalización final. Tycho usa el mismo 33 %. |
| **Ventana** | 41 px | Tiene que ser **mucho mayor** que la PSF (medida en 2025 UR: 4,6 px) para promediar los bultos de las estrellas, y **mucho menor** que el viñeteado (cientos de píxeles). 41 px está en ese hueco con margen por los dos lados. |
| **Pasadas** | 3 | Tres filtros de caja aproximan bien una gaussiana (el teorema central hace el trabajo) y cada uno es O(1) por píxel, así que el flat entero son segundos. Un filtro de **mediana** de 41 px sobre 2048² serían minutos. |

## Cómo se construye

1. El **estadístico de orden por píxel** sobre las tomas, en **franjas de
   filas** (64 filas × 139 tomas × 2048 px × 4 B = 73 MB por franja): el
   percentil necesita todas las tomas a la vez, así que se hace por bandas y
   no se apila la visita entera en memoria.
2. El **suavizado**: tres pasadas de `uniform_filter` de 41 px.
3. La **normalización** por la mediana del propio flat.
4. La **comprobación**: se mide cuánta estructura de pequeña escala ha
   sobrevivido al suavizado (`residual_pct`). Si las tomas **no** estaban
   dithered, las estrellas sobreviven al percentil y el flat las lleva
   encima; entonces se **avisa**, y el aviso sale del propio flat y no de
   que alguien se acuerde de decir si la secuencia estaba dithered.

## El rendimiento, medido

El estadístico de orden se toma con una **partición** (`np.partition`) y no
con `np.percentile`: el percentil ordena (o interpola) toda la banda, y lo
que se quiere aquí es **un** elemento de la lista ordenada, que la partición
da en O(n) en vez de O(n log n).

| | Tiempo (visita real de 140 tomas de 2048²) | Resultado |
| --- | --- | --- |
| `np.nanpercentile` | 197 s | mediana 4460 ADU, residual 1,341 % |
| **`np.partition`** | **12 s** | mediana 4461 ADU, residual 1,342 % |

**16× más rápido y el mismo flat.** (La mediana y el residual son los
mismos al último dígito, que es lo que permite decir «el mismo flat» y no
«uno parecido».)

El orden bajo es además lo que hace **inocua** una toma con NaN: la
partición deja los NaN al final del orden, y el percentil 33 de 140 tomas
está muy lejos de ellos.

## Cuándo se usa, y cuándo no

- **Un flat de verdad siempre gana**: mide la respuesta del tren, mientras
  que un pseudo-flat mide la respuesta por la forma del cielo. La biblioteca
  manda; el pseudo-flat es el respaldo, y la línea de la receta dice cuál se
  usó (`pseudo-flat`).
- Es **opt-in** (casilla en la pestaña Calibración, ajuste
  `calib_pseudo_flat`, apagado por defecto).
- Necesita **dither**: sin él, el aviso lo dice.

## Verificación

**Tests** (sin red, `tests/unit/test_calibration_pseudo_flat.py`): con un
viñeteado y dos motas conocidas y estrellas que ditherean, el flat recupera
la forma a menos del 3 % (normalizando, porque la escala absoluta de un flat
es arbitraria: `calibrate` divide por él); una secuencia **estática** sale
con más residual y con aviso, y la dithered no; un flat de biblioteca gana
siempre al pseudo-flat; aplicarlo aplana de verdad la toma (el borde cae a
menos de un tercio del desnivel que tenía); un conjunto vacío no construye
nada; y una cancelación devuelve nada con su motivo.

**Sobre los datos reales** (2025 UR, 140 tomas): 12 s, mediana 4461 ADU,
residual **1,342 %** (por debajo del umbral del 2 %), así que el flat se
acepta y no avisa; el flat va de 0,588 a 1,590 con mediana 1,000, que es un
viñeteado del 41 % en las esquinas más las motas. El dither de esa visita
(440 px de dispersión entre las dos tandas) es lo que lo hace posible.
