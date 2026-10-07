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

- Cada master se da de alta desde la **pestaña Calibración** del editor (o
  desde Ajustes → Calibración). Se indexa por cámara, ganancia, temperatura,
  exposición y filtro, que es lo que hace válido un master. Un **flat no
  tiene que compartir la ganancia** de las tomas: se normaliza antes de
  aplicarlo, así que la ganancia solo escala su nivel entero, nunca su forma
  (medido: los flats del propio autor se tomaron a ganancia 3 y las tomas a
  ganancia 5, y exigir la misma ganancia hacía perder el flat).
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

1. **Abre la pestaña Astrometría** desde la visita y pulsa el botón grande:
   **Stack the sequence**. Al entrar verás tres cosas y nada más: el objeto con
   sus tomas y su ventana, el botón (pintado en el **color del tipo de
   objeto**, con su glifo) y una línea que dice **qué va a hacer** con los
   valores actuales («8 tomas · 1 observación · brillo con G 5.0/9.0/14.0 ·
   calibración: dark + flat · comprobación con otros observadores»). Todo lo
   demás vive en **tarjetas** con título (un grupo con borde, para que al
   desplegarlo se vea dónde acaba): las **decisiones** («Cuántas
   observaciones» y «Ajustes del apilado») están siempre y arrancan cerradas;
   y el **resultado** aparece con la ejecución, abierto, en sus propias
   tarjetas («Lo que encontró la ejecución», «Las observaciones», «Medición
   por observación», «Marca manual», «Comprobación con otros observadores» y
   «Reporte»). Las acciones ocasionales (la figura de parpadeo, deshacer la
   ejecución) están detrás del menú **⋯** de la cabecera. Nada ha
   desaparecido: está a un clic, y el defecto es lo que la mayoría de las
   noches quiere. Fuera de las tarjetas solo quedan el objeto, el botón, su
   subtítulo y la barra de progreso con su línea de estado.

   La velocidad aparente y el ángulo de posición los trae Horizons al arrancar
   y quedan en las notas del run. La calibración (la receta de la pestaña
   Calibración: dark/bias y flat) se aplica a cada toma **según se lee**, sin
   copias en disco, y **se enciende sola cuando la biblioteca tiene un master
   que casa** con esa cámara y ese filtro: con un objeto débil importa para la
   magnitud, porque sin flat el objeto y las comparsas caen en zonas distintas
   del viñeteado y eso vale **0,087 mag** medidos en una visita real. En cuanto
   la tocas, tu elección manda. Si no tienes flat, la app construye uno de las
   propias tomas (necesita dither y te avisa).
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
   El apilado usa **todos los núcleos que puede**: el número de hilos se
   calcula solo, a partir del procesador y de la memoria que cada tarea
   necesita, así que no hay que configurar nada. Medido en un equipo de 16
   núcleos con 60 tomas de 1024²: el barrido bajó de 6,3 s a **1,3 s** (×5,0),
   el apilado final de 10,1 s a **2,7 s** (×3,7) y la combinación de 957 ms a
   **298 ms** (×3,2). Si quieres capar los hilos (por ejemplo, porque estés
   usando el equipo para otra cosa), el ajuste **`astrometry_threads`** lo
   permite: 0 es automático.
   Además de las pilas de cada observación, la app guarda en el proyecto la
   pila de **toda la secuencia** (`<objeto>_base.fits`): todas las tomas
   combinadas con el objeto congelado, la imagen más profunda de la visita. Es
   la que usa el modo manual para marcar y la que puedes abrir en la pestaña
   Fotometría para mirar el campo. Lleva su propia cabecera (WCS del recorte,
   fecha, exposición, filtro, movimiento y magnitud con su origen y la
   detección que se hizo sobre ella), así que al reabrirla la banda dice lo
   mismo que el día del run.
4. **Barrido de velocidad.** La efeméride y la montura tienen pequeñas
   derivas reales, así que alrededor de la velocidad teórica se prueban 25
   combinaciones (±5 %) y se elige la que da un objeto más brillante **y**
   más redondo. Es el *fine-tuning*, con dos guardas (ADR-062 rev): la
   predicción de la efeméride es **uno de los candidatos**, medido sobre los
   mismos píxeles, y el ganador del barrido solo se usa si la supera por más
   de tres veces la dispersión de la propia rejilla. Cuando la supera, una
   segunda pasada más fina (3×3, sin leer un píxel más) lleva la resolución
   en PA de los 4,5° de la rejilla a unos 0,9°. Medido antes de esto: la app
   publicaba PA 33 donde la efeméride dice 41,8 (2025 HL5) y 37 donde dice
   46,2 (2025 FG18), exactamente un paso de la rejilla. Cuando el barrido no
   mejora a la efeméride, la velocidad y el PA publicados son su predicción y
   la nota lo dice.
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
   existe. Y **mide con el filtro adaptado** (pesar cada píxel por la forma
   esperada en vez de sumar un círculo), que es el **método por defecto**
   desde el 2026-10-07: medido sobre un apilado real de 139 tomas da **1,55 a
   1,63× el SNR de la apertura** y un cero punto **2,6× mejor**, por un 3 %
   más de tiempo. Mueve la magnitud que publicas (0,05 a 0,1 mag, hacia la
   verdad) y tiene caminos sin comprobar; la casilla del panel de Fotometría
   lo apaga y la ejecución dice qué método midió y qué daría el otro.
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
    Al reabrir la visita, la ejecución **se vuelve a mostrar** sin apilar
    nada: las notas, la tabla, el visor, la tira, el blink y el **informe**
    vuelven de lo guardado (el resumen del propio run en la base de datos, sus
    puntos y los ficheros de pila que escribió, uno por observación más la
    pila de toda la secuencia, dentro del proyecto). La línea de estado lo
    dice, y **Apilar** sigue ahí para rehacerla. Un run guardado que no
    encontró nada vuelve con sus notas (hasta dónde llegó la noche), no con
    una columna vacía.
11. **El modo manual, cuando quieras.** La casilla **«Modo manual (objeto
    débil)»** aparece con **cualquier ejecución** (no solo con un «no
    detectado»): sirve para un objeto por debajo de la puerta y también para
    colocar a ojo el centroide de uno que sí se detectó. Abre una ventana pequeña donde marcas el objeto
    sobre la **pila de toda la secuencia**: el clic se ajusta al **centroide
    gaussiano** de la fuente más cercana, una **cruz corta** enseña dónde
    queda la marca (con su propio interruptor) y las flechas la afinan en
    pasos de **0,1 px**. **«Medir en la marca»** vuelve a ejecutar el pipeline
    desde tu marca, llevando su offset (el error de la predicción, constante a
    lo largo de la visita) a cada observación, con la puerta saltada y el
    barrido de velocidad omitido. La nota dice que la posición salió de una
    **marca humana** y la tabla marca el punto como medido desde tu marca: la
    marca es tu firma y viaja con la cifra. La cruz roja de la posición medida
    se queda en la placa: está anclada al cielo, así que sobrevive a cargar
    otra imagen de la serie y a cambiar a la pestaña Fotometría.

## 4. Qué significa cada cifra

- **SNR**: cuántas veces supera la señal del objeto al ruido del fondo. Por
  debajo de 3,5σ la app **no** ejecuta el barrido: barrer sobre ruido y
  quedarse con el máximo es fabricar un falso positivo. Pero **sí mide el
  brillo** (ADR-062 rev), en la posición de la efeméride, y lo marca en
  **rojo** con su nota: un número marcado vale más que ningún número. La
  magnitud de la tabla sale verde cuando la medida es limpia, naranja cuando
  es utilizable pero no limpia (error grande, solo tres comparsas, sin
  estrella de control) y roja cuando no es publicable sin mirarla.
- **SNR de envío**: distinto del anterior. El MPC recomienda **20 o más**
  para enviar y prohíbe las detecciones marginales, así que un grupo por
  debajo del listón no entra en el reporte y se explica por qué. La app trae
  **10** (los envíos Tycho del autor iban a ~16 y fueron aceptados) y se
  cambia en **Ajustes → Astrometría**, junto con el umbral de detección, el
  barrido de velocidad, el margen del recorte, la comprobación y los hilos.
  Cuando **ninguna** observación lo supera, el propio grupo del reporte lo
  dice, con el número del listón y dónde se ajusta, y el botón que envía el
  reporte queda deshabilitado: un reporte sin observaciones no es un reporte.
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
- **La banda de la placa** (la franja de arriba, sobre la imagen) dice de
  dónde sale cada cifra, y por eso **cada número lleva su palabra**: la
  velocidad y el PA van con **`(measured)`** cuando los midió el barrido de
  velocidad y con **`(eph)`** cuando son la predicción de la efeméride; la
  magnitud va con `(measured)` si se midió en esa placa, con `(eph)` si es la
  que predice la efeméride (aparece siempre, aunque el run no haya medido el
  brillo) y con `(cat)` si es la del catálogo o del proyecto. Sobre la pila de
  toda la secuencia la banda añade además la **detección hecha sobre ella**:
  `SNR 1.4 (gate 3.5σ)` y `limit 19.4` (la magnitud límite).

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
