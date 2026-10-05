# Astrometría de cuerpos menores: guía de uso

> Las técnicas que suben la señal frente al ruido (apilar las dos tandas,
> pesar por 1/σ², el filtro adaptado, la estela, el diagnóstico y el
> pseudo-flat) están explicadas a tres niveles, observador, astrónomo y
> desarrollador, en `docs/SNR.es.md`.

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

1. **Abre la pestaña Astrometría** desde la visita. Arriba verás el objeto, sus
   tomas y la ventana de la visita; la velocidad aparente y el ángulo de
   posición los trae Horizons al arrancar y quedan en las notas del run.

   La pestaña está ordenada por lo que haces cada noche: el objeto, las
   **observaciones** con su SNR previsto en una línea, el botón de **apilar**,
   el **resultado** (la tira, el visor y la tabla de medidas) y el **reporte**.
   Lo que se toca de vez en cuando vive **plegado** en bloques con título
   («Ajustes del apilado», «SNR previsto por observación», «Comprobación con
   Find_Orb», «Texto del reporte»), y las acciones ocasionales (la figura de
   parpadeo, deshacer la ejecución) detrás del menú **⋯** de la cabecera.
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
   la mediana), mediana (rápido, para probar), media, suma, o **ponderada
   (1/σ²)**. La media y la suma dan la misma señal salvo la escala. La
   ponderada es el mismo recorte sigma, y después cada toma cuenta según el
   ruido de **su** cielo: en una noche estable sale lo mismo que el
   sigma-clipped (medido: un 0,3 % en 2025 UR y un 2,2 % en 2026 PY9), y es
   lo que salva una noche con nubes finas o Luna, donde una toma con el
   triple de ruido arrastraría la media entera (modelado sobre esas mismas
   tomas: hasta un 28 %). El apilado final de cada
   observación cubre por defecto el **fotograma completo**, que es lo que
   necesita la fotometría (comparsas alrededor); si vas justo de memoria o
   de tiempo puedes reducirlo a 1024, 512 o 256 px, y el barrido de
   velocidad seguirá trabajando sobre el recorte de la estela del objeto.
   Si la visita mezcla **dos tandas** (una pausa, un re-apuntado), la app
   lo dice en el resultado: «la visita parece 2 tandas: la segunda está a
   884 px y empieza 5 min después», con la rotación del campo. Esas tomas
   **se apilan igual**: el registro ajusta la pequeña rotación del campo
   (hasta 15°) y recupera los fotogramas que antes se tiraban. Las que de
   verdad no encajan (una nube, una estela de satélite) se dejan fuera
   **con su motivo**, nunca en silencio. Medido en una visita de 2025 UR:
   recuperar la segunda tanda subió el SNR del apilado de estrellas de
   **1.826 a 2.702 (×1,48)**.
4. **Barrido de velocidad.** La efeméride y la montura tienen pequeñas
   derivas reales, así que alrededor de la velocidad teórica se prueban 25
   combinaciones (±5 %) y se elige la que da un objeto más brillante **y**
   más redondo. Es el *fine-tuning*.
5. **Secuencia centrada.** Se monta un GIF o un montaje con las N
   observaciones, todas centradas en el objeto: si está en todas, la
   detección es sólida; si en alguna no, se ve. En la pestaña tienes además
   una **tira de miniaturas** con las N observaciones al mismo estirado:
   pinchar una la lleva a la vista principal para trabajar sobre ella.
6. **Medida.** El objeto se mide dos veces: sobre el stack final y frame a
   frame. Las dos usan el mismo centroide, así que su comparación dice algo.
   Si difieren más de 0,5″ o 3σ, el punto se marca.
7. **Brillo.** La magnitud se mide sobre los **apilados**, no sobre las tomas:
   en una toma suelta un NEO débil apenas tiene señal (SNR 2) y su apertura
   acaba persiguiendo el ruido. El objeto se mide en **su** apilado, donde su
   luz está concentrada, y las estrellas de comparación en un **segundo
   apilado** de las mismas tomas alineado en las estrellas, porque en el
   apilado del objeto son trazos y un trazo no calibra nada. Es la receta de
   Tycho-Tracker, y cuesta una pasada más de apilado: puedes apagarla con la
   casilla **«Medir el brillo»**, y entonces la ejecución solo reporta
   posiciones y lo dice. Se hace **una medida por observación**, que es lo que
   publica el MPC. Las comparsas salen de la secuencia que tengas guardada en
   el proyecto; si no hay, la app propone una automáticamente y lo dice, porque
   una propuesta automática es un punto de partida, no tu elección. Los ajustes
   (aperturas, método de cielo, centroide, término de color) son **los de la
   pestaña Fotometría**: se editan allí y ningún otro sitio, y la línea de esta
   pestaña te dice, antes de lanzar, con qué se va a medir.
   La ejecución te dice además **la forma del objeto** en su apilado: si
   sale **estelado** (por ejemplo 2,4 px según PA 245°) es que la exposición
   fue larga para ese movimiento, y acortarla es la mejora más barata que
   existe. Y te dice cuánto leería el **filtro adaptado** (pesar cada píxel
   por la forma esperada en vez de sumar un círculo): medido sobre un
   apilado real de 139 tomas, **1,55 a 1,63× el SNR de la apertura**. El
   reporte sigue usando la magnitud de la apertura, que es la que valida el
   validador; el filtro se enseña al lado.
8. **Chequeo.** NightScribe baja las observaciones publicadas del objeto (o
   del NEOCP si no está confirmado), las pasa por **Find_Orb** junto con las
   tuyas (excluyendo las tuyas del ajuste) y compara tu residuo con la nube
   de los demás. Si estás fuera de la nube, bloquea el reporte por defecto.
9. **Reporte.** Se genera en **ADES PSV** y en **MPC 80 columnas**, se valida
   con el mismo validador de siempre y se envía al bloque MPC de la visita.
   El envío lo haces tú.
   Al terminar, la app te dice además **hasta dónde has llegado**: la
   **magnitud límite** a 5σ de esa noche, medida con tus propias estrellas
   (y avisando si el campo no está limitado por el cielo, en cuyo caso la
   cifra no se debe citar), y los **residuos de la solución**, con la peor
   celda de una rejilla 4×4, que es donde se ve una escala mal o un chip
   inclinado.
10. **Léelas después.** En la pestaña **Análisis** del proyecto, el bloque
    **Ejecuciones de astrometría** lista cada pasada: la fecha, cuántas
    observaciones midió, el movimiento que resolvió, el brillo, la
    comprobación y el estado. La magnitud dice **quién la escribió**:
    *automática* (la propia ejecución) o *a mano* (una medida que hiciste en
    la pestaña Fotometría y enviaste al reporte con **«Usar para el
    reporte»**; la de la ejecución se conserva al lado, para la auditoría).
    Desde ahí puedes **abrir la visita en el editor** o **deshacer** una
    ejecución entera (sus posiciones se van; la fila queda marcada como
    deshecha). Una ejecución **sin detección** también se lista: «se buscó y
    no había nada» es un dato, y la noche siguiente necesita saberlo.

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
- **Brillo**: la magnitud del objeto medida sobre los apilados contra las
  comparsas, con su banda (Gaia G cuando las comparsas son de Gaia, que es
  lo normal con filtro Clear). Viene con el número de comparsas y de
  observaciones que la sostienen, y con su error. El apilado de estrellas
  trae además una **estrella de control**: si ella se sale de su valor de
  catálogo, la noche no se comportó y lo dice.
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
- **El brillo de un objeto débil es exigente**: sale del apilado, así que ya no
  sufre el ruido de una toma suelta, pero depende de que el campo tenga
  comparsas de brillo parecido y de que el cielo del apilado del objeto no
  esté cruzado por el trazo de una estrella brillante. La pestaña te dice con
  qué aperturas y qué cielo se va a medir antes de lanzar: si algo no cuadra,
  ese es el sitio donde mirar.

## 6. Find_Orb: instalación y configuración

El chequeo se apoya en Find_Orb, que NightScribe **no** distribuye: solo
detecta tu copia y la ejecuta. Necesita el ejecutable **no interactivo**
(`fo` en Linux/macOS, `fo64.exe` en Windows).

- **Linux/macOS**: `micromamba install -c conda-forge findorb` (trae `fo`,
  `find_orb` y las efemérides DE430t). O compilar del código fuente.
- **Windows**: `find_c64.zip` y `fo64.exe` de Project Pluto, en la misma
  carpeta.
- En **Ajustes**, apunta el campo Find_Orb al `fo` y pulsa «Probar». El botón
  **«Instalar…»** te lo hace: primero mira si `fo` ya está en el PATH (el caso
  habitual: lo instalaste y la app no lo sabía) y apunta la ruta a él; si no
  está, busca **micromamba**, **mamba** o **conda**, crea un entorno **privado**
  con el paquete de conda-forge `findorb` (dentro de la carpeta que elijas, sin
  tocar nada de tu instalación) y te va enseñando lo que hace. Si no encuentra
  ningún gestor, te dice qué instalar y qué escribir: la app **no** se descarga
  un gestor de paquetes por su cuenta.

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
- **«N tomas no contienen el objeto y se han dejado fuera»**: la visita
  mezcla dos tandas y en la segunda el campo apunta a otro sitio, así que el
  objeto cae fuera del sensor en esas tomas. Se dejan fuera **a propósito**:
  apilarlas añadiría ruido justo donde se mide el objeto. Si son muchas y no
  esperabas dos tandas, revisa que la efeméride sea la del objeto correcto.
- **«N tomas no se han podido alinear»**: el resultado dice **por qué**.
  *Muy pocas estrellas* suele ser una nube, niebla o una exposición
  demasiado corta en esa toma; *sus estrellas no concuerdan con el ajuste*
  suele ser una estela de satélite, un avión o un salto de guiado. Si el
  mensaje añade que **la visita parece varias tandas**, es que hubo una
  pausa o un re-apuntado: esas tomas se apilan igual, y solo conviene
  partir la visita si las tandas son de noches distintas. Y recuerda que
  las tandas solo se solapan en parte: las comparsas fuera de la zona
  común no se pueden medir en todas las tomas.
- **Residuos grandes en todos**: la órbita puede ser mala; mira la dispersión
  de los demás antes de culpar a tu medida.
