# P1: co-adición con pesos y normalización

**Estado**: hecho.

## Por qué

Apilar N tomas de la misma señal con ruidos distintos tiene una respuesta
óptima, y no es la media: es la **media ponderada por 1/σ²**. La razón es
de manual: al combinar medidas independientes de un mismo valor, la que
menos ruido tiene debe pesar más, y el peso que minimiza la varianza del
resultado es justo el inverso de su varianza. La media a peso igual es el
caso particular en que todas las tomas son igual de ruidosas.

En una noche estable eso es lo mismo, y no hay nada que ganar. En una noche
con nubes finas, Luna o transparencia variable, una toma con el triple de
ruido **arrastra la media entera**, y la ponderada la deja en su sitio. Y
hay una segunda razón, de miras largas: el filtro adaptado de P2 necesita
un modelo de ruido por fotograma, y ese modelo es exactamente este σ.

## Qué se hizo

1. **El ruido de cada toma se mide** (`track_stack._frame_noise`): la MAD
   escalada de la toma entera. Es un estimador robusto, así que no le
   afectan las estrellas ni el objeto, que son una fracción pequeña de los
   píxeles. Se mide **en el registro**, porque ahí ya se leen los píxeles
   enteros: cuesta cero I/O extra.
2. **El peso es 1/σ²** (`track_stack.frame_weights`). Una toma cuyo ruido
   no se pudo medir recibe la mediana de las demás: es una toma real, solo
   una sin medir.
3. **Método nuevo `weighted`** en `combine`, que es **el mismo recorte
   sigma de siempre y después la media ponderada de las supervivientes**.
   El recorte se extrajo a `_sigma_clip_keep`, compartido: el recorte y el
   sigma-clipped **rechazan exactamente los mismos píxeles**, y lo único
   que cambia entre los dos métodos es cómo se promedian. Sin pesos, el
   método nuevo es **idéntico** al sigma-clipped probado (hay un test que
   lo fija), así que degrada hacia lo conocido, nunca hacia algo nuevo.
4. **Los pesos son propiedad del fotograma, no de una franja**: se calculan
   una vez y las dos rutas (RAM y streaming) usan los mismos, que es lo que
   mantiene el test que fija que ambas coinciden.
5. **En la interfaz**, el método se elige en el combo, con su explicación:
   «Ponderada (1/σ²)», y el tooltip dice qué es y cuándo importa.

## Verificación

**Test unitario** (sin red): sin pesos el método nuevo es el
sigma-clipped; con cuatro tomas limpias y una con quince veces el ruido, la
ponderada cae **seis veces más cerca** de la verdad que la media a peso
igual (treinta realizaciones, para que sea una estadística y no una
moneda); los pesos son el inverso de la varianza, con la mediana de
rescate para la toma sin medir; el ruido de una toma se mide del cielo; y
las dos rutas coinciden con pesos distintos por fotograma.

**Sobre los datos reales**, midiendo el σ de las 140 tomas de 2025 UR y de
las 247 de 2026 PY9:

| Visita | σ por toma (min / mediana / max) | Dispersión | Ganancia de la ponderada |
| --- | --- | --- | --- |
| 2025 UR | 284,7 / 308,4 / 379,5 ADU | 4,0 % | **1,003×** |
| 2026 PY9 | 545,6 / 593,0 / 925,1 ADU | 11,0 % | **1,022×** |

Es decir: **en estas dos noches, casi nada** (0,3 % y 2,2 %), y eso es un
resultado honesto que hay que decir en voz alta. La ponderada es un
**seguro**, no una bala de plata: en una noche ya estable no se nota, y su
valor aparece cuando la noche se rompe. Con el modelo de la propia medida
de 2025 UR, si una décima parte de las tomas hubiera salido con el triple
de ruido, la ganancia sería del **28 %** (σ del apilado 34,9 a 27,3 ADU):
justo el caso de las nubes finas que no se ven en la pantalla.

Por eso el método **no es el de por defecto**: el defecto sigue siendo el
sigma-clipped, y la ponderada se elige cuando la noche lo pide.

## Lo que no se hizo

- **Normalizar el nivel de fondo** por fotograma, como hace Tycho para el
  tracker. Aquí no hace falta para la medida: el pipeline resta el cielo
  **local** de cada apertura, así que un fondo distinto por toma no sesga
  el flujo. Lo que sí cambia entre tomas es el **ruido**, y eso es lo que
  se pondera. La frase de Tycho («normalizar va bien para detectar, no para
  fotometría sensible») apunta al mismo sitio: lo que se toca es el peso,
  no el nivel.
- **Cambiar el método por defecto**: se elige midiendo, y la medida dice
  que en una noche estable no compensa cambiar lo que ya está probado.
