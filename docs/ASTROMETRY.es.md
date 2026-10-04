# Astrometría de cuerpos menores: guía de uso

*Cómo medir un asteroide débil con NightScribe y enviarlo al MPC.*

---

## 1. Qué es y para qué sirve

Un asteroide débil que se mueve no se puede fotografiar bien: con tomas
cortas hay mucho ruido, y con tomas largas deja un trazo. La solución es
apilar: se toma una secuencia de tomas cortas, se calcula cuánto se ha
movido el objeto entre ellas y se desplazan digitalmente **en sentido
contrario** antes de combinarlas. El asteroide se queda quieto en un punto
(donde su luz se suma) y las estrellas se convierten en trazos que el
algoritmo rechaza.

NightScribe hace ese trabajo de principio a fin: calibra, apila guiando el
movimiento con la efeméride, mide la posición por dos vías, la contrasta
con lo que ven otros observatorios y genera el reporte para el Minor
Planet Center. El referente del ramo es Tycho-Tracker, y el chequeo de
calidad se apoya en Find_Orb, la misma herramienta que usa la comunidad.

## 2. Antes de empezar: la calibración

Un objeto débil no emerge si la imagen trae el patrón térmico del sensor y
las motas del tren óptico. NightScribe usa una **biblioteca de masters**
(bias, dark, flat) que tú construyes fuera; la app solo los apunta.

- En **Ajustes** se da de alta cada master. Se indexa por cámara, ganancia,
  temperatura, exposición y filtro, que es lo que hace válido un master.
- Para el light se prefiere un **dark a su misma exposición** (ya incluye el
  bias; restar además el bias sería restarlo dos veces). Si no hay dark, se
  resta el bias y la app avisa de que la corriente térmica queda.
- El **flat** se corrige por filtro, con su propio dark-flat restado y
  normalizado, para que la división no cambie el brillo de la toma.

Si falta una pieza, la app lo dice en lenguaje llano; nunca falla en
silencio ni inventa una calibración.

## 3. El flujo, paso a paso

Todo empieza en una **visita** (una noche de un proyecto NEO, cometa o
PCCP). Sin visita no hay serie: es la regla de la casa.

1. **Abre la pestaña Astrometría** desde la visita. Arriba verás el objeto
   y su efeméride (velocidad aparente y ángulo de posición).
2. **Elige cuántas observaciones quieres.** El MPC prefiere varias medidas
   repartidas en el tiempo antes que una sola. Dices un número y el
   software reparte la secuencia en grupos contiguos iguales. La tabla
   muestra el **SNR previsto de cada grupo**: como el SNR crece con la raíz
   del número de tomas, pedir más observaciones reparte la señal, y conviene
   verlo antes de aceptar.
3. **Apila.** La app resuelve el primer frame, alinea el resto por las
   estrellas y desplaza cada frame para que el objeto caiga siempre en el
   mismo punto. Puedes elegir el método de combinación: **sigma-clipped**
   (el estándar profesional: casi toda la señal de la media y la limpieza de
   la mediana), mediana (rápido, para probar), media o suma. La media y la
   suma dan la misma señal salvo la escala.
4. **Barrido de velocidad.** La efeméride y la montura tienen pequeñas
   derivas reales, así que alrededor de la velocidad teórica se prueban 25
   combinaciones (±5 %) y se elige la que da un objeto más brillante **y**
   más redondo. Es el *fine-tuning*.
5. **Secuencia centrada.** Se monta un GIF o un montaje con las N
   observaciones, todas centradas en el objeto: si está en todas, la
   detección es sólida; si en alguna no, se ve.
6. **Medida.** El objeto se mide dos veces: sobre el stack final y frame a
   frame. Las dos usan el mismo centroide, así que su comparación dice algo.
   Si difieren más de 0,5″ o 3σ, el punto se marca.
7. **Chequeo.** NightScribe baja las observaciones publicadas del objeto (o
   del NEOCP si no está confirmado), las pasa por **Find_Orb** junto con las
   tuyas (excluyendo las tuyas del ajuste) y compara tu residuo con la nube
   de los demás. Si estás fuera de la nube, bloquea el reporte por defecto.
8. **Reporte.** Se genera en **ADES PSV** y en **MPC 80 columnas**, se valida
   con el mismo validador de siempre y se envía al bloque MPC de la visita.
   El envío lo haces tú.

## 4. Qué significa cada cifra

- **SNR**: cuántas veces supera la señal del objeto al ruido del fondo. Por
  debajo de 3,5σ la app **no** ejecuta el barrido: barrer sobre ruido y
  quedarse con el máximo es fabricar un falso positivo.
- **SNR de envío**: distinto del anterior. El MPC recomienda **20 o más**
  para enviar y prohíbe las detecciones marginales, así que un grupo por
  debajo del listón no entra en el reporte y se explica por qué.
- **Residual**: cuánto se separa tu medida de lo que predice la órbita, en
  segundos de arco.
- **Dispersión de los demás**: cuánto se separan ellos. Es la escala justa:
  con una órbita mala todos los residuos son grandes, y lo que importa es si
  estás **fuera de la nube**, no a qué distancia estás de cero.
- **rmsRA / rmsDec**: la incertidumbre de tu posición, con su desglose
  (centroide, WCS, tiempo).
- **Magnitud límite**: hasta dónde llegaba la pila. Es útil aunque no haya
  objeto: dice si la noche daba para más.
- **Observatorios distintos y última observación** (en la ficha del objeto):
  muchos y reciente significa objeto vivo y bien determinado; uno solo y
  hace meses, candidato a perderse.

## 5. Cuándo fiarse y cuándo no

- **Dithering**: si la secuencia no se movió, el ruido de patrón del sensor
  se apila y fabrica detecciones fantasma. La app lo avisa (es la causa
  número uno que documenta el MPC). Mueve el telescopio entre tomas.
- **El chequeo filtra, no demuestra**: el propio MPC advierte de que en un
  arco corto una observación errónea encaja igual de bien que una buena. La
  prueba de verdad es un SNR alto y ver el objeto en la secuencia centrada.
- **Sin referencia no bloquea**: si el objeto es un descubrimiento y nadie
  más lo ha visto, el chequeo avisa de que no hay con qué comparar y no
  bloquea; deciden el SNR y la secuencia.
- **Un objeto recuperado tras meses** puede tener la órbita derivada: un
  residuo grande puede ser de la órbita, no tuyo.

## 6. Find_Orb: instalación y configuración

El chequeo se apoya en Find_Orb, que NightScribe **no** distribuye: solo
detecta tu copia y la ejecuta. Necesita el ejecutable **no interactivo**
(`fo` en Linux/macOS, `fo64.exe` en Windows).

- **Linux/macOS**: `micromamba install -c conda-forge findorb` (trae `fo`,
  `find_orb` y las efemérides DE430t). O compilar del código fuente.
- **Windows**: `find_c64.zip` y `fo64.exe` de Project Pluto, en la misma
  carpeta.
- En **Ajustes**, apunta el campo Find_Orb al `fo` y pulsa «Probar».

NightScribe escribe el fichero de observaciones, lanza `fo` en una carpeta
temporal con un entorno propio (`-D`) y un límite de CPU (`-r`), y lee los
residuos de `total.json`. Si Find_Orb no está configurado, el chequeo **no
está disponible** y la app lo dice; nunca finge un veredicto.

## 7. Liberar espacio

Una noche son cientos de FITS. Cuando el stack, la secuencia y el reporte ya
están guardados, la app **ofrece** mover los originales usados a una carpeta
`procesados` dentro del proyecto (no los borra: se pueden restaurar) y borrar
por separado los calibrados exportados. Solo los frames de una ejecución con
éxito, y nada se mueve sin que tú lo confirmes.

## 8. Solución de problemas

- **«No disponible» en el chequeo**: casi siempre apuntaste al `find_orb`
  interactivo en vez del `fo`.
- **El objeto no aparece**: revisa el SNR de cada grupo, prueba menos
  observaciones (más tomas por grupo) y comprueba que la secuencia está
  dithered.
- **Residuos grandes en todos**: la órbita puede ser mala; mira la dispersión
  de los demás antes de culpar a tu medida.
