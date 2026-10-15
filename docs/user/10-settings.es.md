# 10. Ajustes

Todo lo configurable en NightScribe vive en **Herramientas → Ajustes…**.
El diálogo es un raíl de seis categorías con nombre a la izquierda, una
página a la derecha y un **buscador** arriba: escribe una palabra (el
nombre de un campo o la primera línea de su ayuda, como "gain", "moon" o
"api key") y solo queda en pantalla lo que coincide, en todas las páginas.
Cada campo lleva su ayuda justo debajo. Cada grupo muestra su **título en
una barra** que lo separa claramente.

Los ajustes comunes están siempre a la vista; los de experto viven tras una
única puerta **Advanced** al pie de su página, cerrada por defecto, para
que la página se lea corta y terminada. No se ha quitado nada: abre la
puerta con un clic, o simplemente busca; una coincidencia detrás de una
puerta la abre sola, y al vaciar la caja la puerta vuelve al estado en que
la dejaste.

Nada de aquí es obligatorio salvo el sitio; cada integración que falte
simplemente deja su función en silencio.

## Observatorio

Dónde y quién eres. Se configura una vez; todo se calcula desde aquí.

- **Sitio**: **código MPC**, nombre, coordenadas y altura del observatorio
  (**Resolver coordenadas** desde el código, **Elegir en el mapa…**, o a
  mano). Es la identidad de tus informes MPC: si envías astrometría, usa el
  código. **Código AAVSO**: tu código de observador; se escribe en el
  traspaso a EXOTIC de los proyectos de tránsito. **Brillo de cielo**
  (mag/arcsec²): cuán brillante es tu cielo cenital; fija la sub-exposición
  sugerida (capítulo 05). **Consultar** la rellena desde el atlas de
  contaminación lumínica si tienes la clave (Integraciones), o léela del
  mapa que abre el botón en tu sitio.
- **Observador e informes**: cómo se firman tus medidas. Tu nombre
  (**Observador**), quién midió la placa (**Medidor**; vacío = el
  observador), el **email de contacto** (sin él la sumisión al MPC no se
  puede enviar), las líneas de **telescopio** y **cámara** (texto libre, o
  construidas desde la apertura, el tipo y la relación focal) y un
  **comentario de informe** opcional. La cabecera del informe MPC y las
  cajas de las cartas leen de aquí.

## Equipo

Con qué observas.

- **Telescopio y límites**: la **apertura** y la **magnitud límite**. El
  puntaje de Tonight los lee para no sugerir lo inalcanzable. Sé honesto
  con la magnitud límite; el comando `inject` (capítulo 09) te da el número
  medido.
- **Cámara**: manda el **preset**, que rellena el tamaño de píxel y un
  perfil de partida de una vez. Elegir un preset carga **los datos de esa
  cámara** (full well, ruido de lectura, corriente de oscuridad, lectura y
  descarga, linealidad) por encima del perfil; la ganancia del sistema nunca
  se toca, porque es tuya. El tamaño de píxel y la focal se devuelven
  como la **escala de placa** (arcosegundos por píxel), que es lo que usan
  de verdad el consejo de exposición de NEOs, la fotometría y el informe
  MPC.
- **Cámara: perfil medido** (tras la puerta **Advanced**): la física del
  sensor a tu ganancia (full well, ganancia del sistema, ruido de lectura,
  corriente de oscuridad, lectura y descarga, linealidad, exposición máxima
  de trabajo), con la acción **Medir ganancia…**. El preset ya rellena
  valores de partida y 0 significa "desconocido"; mide los tuyos antes de
  fiarte de una barra de error. La **lectura y descarga** es el **único
  overhead por toma** de la app (el preset la rellena según el sensor, por
  tipo y tamaño; un CCD lee en segundos): dimensiona una secuencia y acota
  la serie de un objeto rápido, así que una descarga lenta significa menos
  tomas antes de que el objeto salga del campo. Súbela si tu montura también
  necesita asentarse entre tomas.

> **¿Por qué medir la magnitud límite en vez de fiarse de la ficha?** Porque
> el límite real depende de tu cielo, tu cámara, tus exposiciones y tu
> reducción. Una cifra optimista llena la lista de objetivos imposibles; una
> pesimista te esconde buenas noches.

> **¿Por qué "por unidad y por ganancia"?** Porque la linealidad y la
> exposición máxima no son propiedades del modelo de cámara, sino de tu
> unidad concreta con la ganancia que usas. El preset da el valor de la
> ficha como punto de partida; el valor verdadero se mide en tus propias
> tomas (la app lo hace, capítulo 06), y 0 significa "desconocido": la app
> lo dice en vez de inventarse algo.

> **Tu propia cámara.** El catálogo de presets es un fichero de datos. Si tu
> cámara no está, añádela (o corrige una) en `<config>/cameras.toml`, junto a
> `nightscribe.json`: una `[[camera]]` con un `key` nuevo la añade, el mismo
> `key` corrige una empaquetada, y `hide = ["key"]` quita una. Ajustes relee
> el fichero al abrirse, así que no hace falta reiniciar; si hay un error,
> Ajustes → Cámara te lo dice y sigue con el catálogo empaquetado.

## Observación

Cómo se planifica y filtra la noche.

- **Horizonte local**: un fichero de horizonte (TheSkyX `.hrz` o pares
  "az alt") con un margen de seguridad. Con él, el planificador deja de
  sugerir lo que se esconde tras tus obstáculos.
- Los **tipos de objeto** que salen en Tonight, el filtro de **tránsitos**,
  la restricción de **Luna**, los valores por defecto de la **sesión** (con
  la **lista de vigilias** de variables, el interruptor del **canal
  AAVSO** y el manejo del **guiado** en un follow run: si el autoguiado se
  reanuda antes de cada observación del run y si se recalibra al arrancar;
  el paso Captura los lee cuando el run empieza) y la **carpeta de
  proyectos**.

## Medida

Todo lo que convierte una noche de tomas en números. Los tres grupos que
ves primero (fotometría, solver, masters) cubren una noche normal; el
resto está a un clic tras la puerta **Advanced**.

- **Fotometría**: el método con el que arranca una placa *nueva* (el filtro
  adaptado). Una placa ya medida conserva su receta; el interruptor de la
  placa vive en la pestaña Fotometría, junto a la medida (capítulo 06).
- **Masters de calibración**: la biblioteca de bias, dark y flat contra la
  que la pestaña Calibración del editor resuelve su receta, y la política de
  la calibración (modelar el viñeteo cuando falta un flat real, y la
  tolerancia de temperatura del dark). Los ficheros se enlazan, nunca se
  copian ni se mueven, y se añaden **por ficheros o por carpeta**: cada toma
  se clasifica por su propia cabecera (`IMAGETYP`), así que tú no dices cuál
  es dark y cuál flat. Son **tres tipos, no cuatro**: un «dark de los flats»
  es un dark, y lo que lo hace válido es su exposición. La app también puede
  **construir los masters** desde una carpeta de tomas: las agrupa por su
  clave, las combina con la mediana y escribe el master en la carpeta de la
  biblioteca. Cada master tiene **dueño**: los que construye un proyecto son
  suyos, un bias o un flat se pueden **compartir** con todos, y un proyecto
  puede **usar** el de otro sin copiarlo. La tabla dice de quién es cada fila
  («Compartido» cuando es de todos) y desde aquí cambias de quién es. La
  biblioteca está solo aquí; la pestaña Calibración del editor la **lee** y
  te enlaza de vuelta a esta página.
- **Solver de placa**: *Auto* prueba ASTAP local y cae a
  nova.astrometry.net; también puedes forzar uno. **Binario ASTAP**: ruta
  al ejecutable (vacío = buscar `astap` en el PATH), con **Test** para
  comprobarlo. **Guardar la WCS resuelta en la cabecera FITS** (activado
  por defecto) deja la placa resuelta para cualquier programa, sin tocar
  los píxeles.
- **Advanced**: el techo de saturación y el residual del flat, las
  compuertas y tolerancias de la astrometría (la compuerta de detección, el
  listón de envío al MPC, el barrido de velocidades, el chequeo contra
  otras estaciones, los hilos de trabajo y la **tarjeta gráfica** con su
  **backend**: encendida por defecto, con **OpenCL**; el capítulo 12 cuenta
  qué acelera, cómo instalar CUDA y por qué no cambia el resultado),
  **Find_Orb** (el chequeo de la órbita) y **EXOTIC** (la reducción de
  tránsitos: ruta a un **Python ≤ 3.10** y al entorno; **Preparar entorno**
  crea uno privado e instala EXOTIC dentro, y **Test** comprueba que
  importa). Todos tienen valores por defecto sensatos; tócalos solo si
  sabes por qué.

## Integraciones

El mundo exterior: tu software de observatorio y las claves opcionales.

- **Software del observatorio**: elige **CCDciel** o **NINA / PINS** (de uno en
  uno). Solo se muestran los campos del programa elegido. Cada uno guarda su
  host, su puerto (3277 para CCDciel, 1888 para NINA/PINS) y su auto-conexión.
  El control solo funciona mientras el programa está abierto, y para NINA/PINS
  su plugin Advanced API v2 tiene que estar instalado y activo (capítulo 05).
  Cambiar la elección desconecta el otro programa.
- **NEOfixer**, **Astrometry.net**, **bot TNS**, **token de API de AAVSO**,
  **contaminación lumínica**: claves opcionales para, respectivamente, el reporte
  a la comunidad, la resolución a ciegas de placas sin WCS, las imágenes de
  descubrimiento de transitorios, la fotometría de la comunidad que alimenta las
  vigilias de estrellas brillantes (capítulo 04) y el brillo de cielo del sitio
  (capítulo 05).
- **Modelo de lenguaje (IA, opcional, experimental; tras la puerta
  Advanced)**: para redactar el post y el asistente (capítulos 08 y 11). El
  endpoint es compatible con OpenAI: sirve un servicio de la nube
  (OpenRouter, Groq, Google AI Studio) o uno local (Ollama, LM Studio).
  Eliges el servicio conocido, pegas la clave y escribes el modelo, o pulsas
  **Listar modelos** y eliges el que el endpoint te dé (con sus nombres
  exactos si es local); **Probar conexión** comprueba que los tres encajan.
  Está apagado por defecto: con él apagado, el asistente y los botones de IA
  quedan deshabilitados, y nada sale de tu equipo hasta que lo usas.
- **Informes largos**: con esto activado, la IA escribe un artículo completo
  (español e inglés) con todos los datos del proyecto y las imágenes generadas,
  no solo el post corto. Gasta muchos más tokens, así que un servicio de pago
  cobra más por ello; un servidor local no cuesta nada. Apagado por defecto.

## Interfaz

Cómo se ve y cómo habla la app.

- **Idioma**: español, inglés o el del sistema; se aplica al reiniciar.
- **Cielo animado en la Bienvenida**: unas estrellas titilan y la pantalla
  se funde una vez; la Luna se dibuja con su fase real de esta noche en
  cualquier caso. Se aplica al momento.
- **Barra superior solo con iconos** (editor FITS): los botones de acción
  muestran glifos compactos en vez de sus etiquetas. Se aplica al momento.
- **Cartas y anotaciones**: la forma y el color de la marca del objeto y
  las dos capas de metadatos (la banda de la placa en el editor, las cajas
  de esquina de las demás cartas). Quién las firma (observador, medidor,
  telescopio, cámara) se configura en **Observatorio → Observador e
  informes**.

> **¿Por qué hay tanto "opcional", sin pedir cuenta en ningún sitio?** Porque
> el observatorio es tuyo y los datos también: NightScribe funciona del todo
> sin una sola clave, y cada integración que falta degrada con elegancia (la
> función se queda callada) en vez de bloquearte. Las claves abren puertas;
> no levantan muros.
