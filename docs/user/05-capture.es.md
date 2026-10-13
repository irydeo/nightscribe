# 05. Captura

## Manejar tu observatorio: CCDciel o NINA/PINS

NightScribe puede entregar el plan de captura a tu software de observatorio y
apuntar el telescopio directamente, sin exportar ficheros ni reescribir
coordenadas. Hay dos programas soportados, y eliges uno en **Herramientas →
Configuración… → Integraciones**:

- **CCDciel** ([ap-i.net/ccdciel](https://www.ap-i.net/ccdciel/)) por su
  servidor JSON-RPC (host y puerto, por defecto el 3277).
- **NINA** (Windows) o **PINS** (Linux), su versión para Linux, por el plugin
  comunitario **Advanced API v2** (host y puerto, por defecto el 1888).

De uno en uno: el paso Captura maneja el programa que elijas, y cambiar la
elección desconecta el otro. En ambos casos, una condición: el programa tiene
que estar **abierto** (y, para NINA/PINS, su plugin Advanced API instalado y
activo); NightScribe habla con su API, no con los drivers.

Desde el paso **Captura** de un proyecto:

- **Conectar CCDciel** / **Conectar NINA / PINS** muestra el estado del
  observatorio (montura, rueda de filtros, cámara) en el panel.
- **Apuntar telescopio** hace un slew a la posición recién calculada del
  objetivo.
- **Goto astrométrico** hace slew, resuelve la placa y corrige a la posición
  real del cielo: la vía fiable para una órbita preliminar.
- **Detener goto** para el movimiento del telescopio **ahora mismo**. Se arma
  en el instante en que pulsas cualquiera de los dos botones de apuntado y se
  desarma cuando el apuntado termina: úsalo si la montura se va a un sitio
  equivocado.
- **Enviar plan** prepara el plan (objeto, tomas × exposición, filtro, binning,
  ganancia, offset, dither) en el software y **lo lee de vuelta** (incluidos el
  binning y el dither que de verdad tiene), así que el panel muestra lo que
  aterrizó. Un ajuste opcional rechazado se avisa sin abortar el plan.
- **Iniciar captura** lo lanza, y **el mismo botón la para** mientras el run
  está en marcha («Parar captura»): para la **cámara**, no la montura (eso es
  Detener goto).
- La lista de filtros de la tarjeta **Exposure plan** es la que tiene tu rueda
  de verdad (se lee del programa al conectar); solo cuando no hay nada
  conectado aparece la lista clásica L/R/G/B/Ha/OIII/SII.

> **Qué viaja en vivo y qué va en la secuencia.** «Enviar plan» puede fijar en
> vivo el objeto, la exposición, el nº de tomas, el filtro, el binning, la
> ganancia, el offset y el contador de dither (CCDciel) o un snapshot de una
> toma (NINA). La **cadencia de autofocus** no es un ajuste en vivo en ninguno de
> los dos programas: viaja con la **secuencia exportada** (`.targets` de CCDciel,
> la secuencia nativa de NINA).

> **¿Por qué coordenadas aparentes y no J2000?** Porque una montura apunta al
> cielo de *ahora*, no al del año 2000. Precesión, nutación y aberración mueven
> la posición aparente de una estrella decenas de segundos de arco: más que el
> campo de muchas cámaras. Con CCDciel, NightScribe hace la conversión por ti
> para que el objeto caiga en el chip, no fuera de él. NINA/PINS toman J2000
> directamente, así que ahí las coordenadas del plan van tal cual.

### La última toma, en la ventana

Al pulsar **Iniciar captura**, aparece una vista previa de la última toma bajo
la fila de captura, con su nombre de fichero, filtro, exposición y fecha, y un
botón para **abrirla en el editor**. Se refresca según llegan tomas nuevas y se
para cuando termina el run. La imagen llega por red desde el propio programa
(`fullimage.jpg` de CCDciel, el stream de imágenes de NINA/PINS), así que
funciona con el observatorio en otra máquina y no necesita carpeta ni ajuste.
Con NINA/PINS el FITS se descarga y se abre en el taller; con CCDciel, que por
red solo sirve una imagen, el FITS se abre cuando NightScribe puede ver el
fichero en disco (misma máquina o carpeta montada).

### Dither y autofocus, con el porqué

En **Capture options** (un bloque plegado del paso Captura) ajustas el
**dithering** (cada N tomas, cuántos píxeles) y el **autofocus** (cada ciertos
minutos o al cambiar la temperatura), más ganancia, offset, binning y los
retardos. La app propone los valores para tu objeto y explica cada uno al pasar
el ratón por el ⓘ; puedes sobrescribir cualquiera. El razonamiento, en corto:

- El **dither** mueve el campo unos píxeles entre tomas para que los píxeles
  calientes y el ruido de patrón fijo caigan en píxeles distintos y el apilado
  los elimine. Un objeto que se mueve (un NEO, un cometa) ya desplaza el campo
  solo, así que no lleva dither; un tránsito o una HADS no pueden permitirse el
  hueco, así que se hace antes del run, no durante.
- El **autofocus** mantiene las estrellas pequeñas según se enfría el tubo y
  cambia el filtro: una estrella desenfocada reparte su luz y pierde relación
  señal/ruido. En fotometría de cadencia rápida se hace solo antes del run.

Los valores viajan con la secuencia exportada (`.targets` de CCDciel, JSON de
NINA) y, donde la API lo permite, se aplican en vivo; la cadencia completa de
autofocus vive en el fichero de secuencia.

### Valores sugeridos, y por qué

Cuando un proyecto todavía no tiene plan, los bloques **Exposure plan** y
**Capture options and calibration** se abren con los valores que la app cree
mejores para tu objeto, tu cámara, tu telescopio y tu cielo: tomas, exposición,
dither, autofocus, ganancia, offset, binning. Son solo un punto de partida:
cambia cualquiera y pasa a ser tuyo (la app nunca pisa un valor que hayas
tocado). El botón **Fijar los valores sugeridos** los vuelve a aplicar, y el
**?** junto a cada bloque abre un diálogo que explica, con los números que usó,
por qué cada valor es el que es.

La exposición es la delicada: sale del brillo del objeto y luego se **acorta**
para una cámara que satura antes (poco full well, o píxeles grandes con focal
corta), respeta los límites de tu cámara y el tope sin traza de un objeto en
movimiento, y se comprueba contra tu cielo y tu ruido de lectura. Una sCMOS
sensible que satura en segundos recibe tomas cortas; un objeto tenue en un cielo
oscuro, más largas.

El **número de tomas** es el otro delicado: la app llena la ventana de
visibilidad de tu objeto, pero nunca pasa del momento en que cruza el campo de
la cámara. Un objeto en movimiento arranca centrado (el goto lo deja así), de
modo que le queda media altura del lado corto del sensor antes de llegar al
borde; la serie se corta ahí, porque después cada toma es una imagen sin el
objeto. El cruce sale del tamaño del sensor, tu focal y la velocidad aparente
del objeto, y el tiempo por toma entre el que se divide incluye la **lectura y
descarga** de la cámara (su propio número, en el perfil de cámara) más el
asentamiento de la montura: una descarga lenta significa menos tomas. Si el
campo o la velocidad no se conocen, la app dice que no puede acotar el número
en vez de aparentar.

Tu **brillo de cielo** (Ajustes → Observatorio) alimenta esa comprobación. Con
una clave de contaminación lumínica (Ajustes → Integraciones, de
lightpollutionmap.info), **Consultar** la rellena desde el atlas; sin clave,
léela del mapa (el botón lo abre en tu sitio). Es el valor cenital y un modelo,
así que tómalo como un buen punto de partida, no como una promesa.

### Iniciar y seguir: N observaciones sin re-apuntar a mano

Un objeto rápido se sale del campo: captúralo sin más y la mitad de la serie
acaba sin él. **Iniciar y seguir…** (en el paso Captura, para un objeto en
movimiento y con conexión) pide un **número de observaciones** y lleva el run
entero: cada observación captura tantas tomas como caben antes de que el objeto
llegue al borde del campo (el mismo cruce por el que se acota el recuento),
luego el telescopio vuelve a apuntar a la **posición nueva** del objeto y empieza
la siguiente. La app sigue al objeto por el cielo, observación a observación, y
sacas el máximo de cada una sin tocar la montura a mano.

Antes de empezar muestra los números: observaciones, tomas por observación,
exposición, el coste del re-apuntado y el total, y si cabe en la ventana de
visibilidad del objeto. Usa **tus** números del paso Plan (los campos **Frames**
y **Exposure**), no una sugerencia nueva; si tu número de tomas es más de las
que caben antes de que el objeto llegue al borde del campo, lo dice y lo respeta
igual. Mientras corre, el botón pasa a **Parar seguimiento** y el panel dice por
qué observación va. El software comercial usa la palabra *recenter* para cada
paso (CCDciel) y *Center After Drift* (NINA); la diferencia es que aquí cada
paso apunta a la **efemérides actualizada** del objeto, no a coordenadas fijas,
porque el objeto se mueve de verdad.

Dos cosas que hay que saber: necesita un **solver de placa** (el centrado es un
goto astrométrico), y con **NINA/PINS** cada observación es **un fotograma** (su
captura es un snapshot de una toma) salvo que cargues la secuencia nativa; con
CCDciel se respeta el recuento. Cada re-apuntado abre una tanda nueva, así que el
editor FITS puede tratarlas como observaciones separadas.

### Lo que NINA / PINS todavía no hace

- Su captura de tipo snapshot toma **una exposición**, así que **Iniciar
  captura dispara una toma**, no todo el número de frames del plan: el panel
  avisa de que el número de tomas es solo informativo. CCDciel sí respeta el
  número.
- NINA **no tiene un estado persistente**: **Enviar plan** fija el filtro de la
  rueda y el resto lo recuerda NightScribe, en vez de un estado que se pueda
  leer de vuelta dentro de NINA.
- El goto astrométrico necesita un **plate solver configurado en NINA**; sin
  él, el apuntado falla y el error se muestra tal cual.
- **PINS usa el mismo plugin y los mismos ajustes que NINA**; solo cambian host
  y puerto.

## Calibración: bias, darks y flats

La pestaña **Calibración** del editor FITS gestiona una **biblioteca de
masters** y la receta de cada visita.

La biblioteca se indexa, no se copia: señalas tus FITS maestros y la app lee
de sus cabeceras lo que los hace válidos (cámara, ganancia, temperatura,
exposición, filtro). Al indexar declaras qué *es* cada fichero:

- **Bias**: el offset electrónico de lectura (exposición cero).
- **Dark**: corriente térmica, a la misma exposición que las luces. *Un dark
  ya incluye el bias*, así que con dark no hace falta bias aparte.
- **Dark de flats**: a la exposición de los flats.
- **Flat**: por filtro, normalizado.

> **¿Por qué calibrar?** Porque tu sensor miente de tres maneras conocidas y
> repetibles: añade un pedestal electrónico a cada píxel (bias), acumula
> carga térmica con el tiempo (dark) y multiplica la luz por la sombra del
> polvo y el viñeteo (flat). Restar bias+dark y dividir por el flat no es
> estética: es lo que convierte ADU en fotones comparables de una esquina a
> otra del chip y de una noche a otra. Sin eso, la fotometría del capítulo 06
> mide el polvo de tu tren óptico, no la estrella.

> **¿Por qué el flat es por filtro?** Porque las sombras del polvo cambian de
> escala con la óptica y la rueda, y la respuesta del sensor cambia con el
> color. Un flat de V no corrige un R: la sombra de la misma mota cae en otro
> sitio si la rueda aparca distinto.

**La receta de la visita**: al abrir el editor desde una visita, la app
resuelve qué master de la biblioteca usa cada pieza, leyendo la cabecera del
primer frame, y avisa de lo que falte (Avisos). **Calibrar la visita**
aplica la receta a todos los frames; la calibración trabaja en memoria y
solo escribe copias FITS si marcas la exportación.

**Si no tienes flat para un filtro**: la opción *Build a flat from the
frames* construye un pseudo-flat apilando las propias luces (el polvo y el
viñeteo están fijos en el frame; las estrellas se mueven entre tomas y
desaparecen en el percentil bajo). Úsalo como lo que es: un parche honesto
que nunca se antepone a un flat real. Puedes abrirlo con **Ver el flat** y
juzgarlo: un flat con una estrella dentro no es un flat.

> **¿Por qué funciona el pseudo-flat?** Porque en una serie con *dithering*
> (pequeños desplazamientos entre tomas) lo único que no se mueve es lo que
> pertenece al instrumento: polvo, viñeteo, píxeles calientes. Un percentil
> bajo sobre muchas tomas conserva lo fijo y rechaza lo que se movió. Si tu
> campo es estático (sin dithering), la app enmascara las estrellas antes de
> apilar, por la misma razón.

Siguiente: [06. Fotometría](06-photometry.es.md).
