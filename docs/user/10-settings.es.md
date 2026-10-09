# 10. Ajustes

Todo lo configurable en NightScribe vive en **Herramientas → Ajustes…**.
El diálogo es un raíl de seis categorías a la izquierda (un icono en cada
una: pasa el ratón para leer el nombre), una página a la derecha y un
**buscador** arriba: escribe una palabra (el nombre de un
campo o la primera línea de su ayuda) y solo queda en pantalla lo que
coincide, en todas las páginas. Cada campo lleva su ayuda justo debajo, y
los mandos raros se esconden tras una sección **avanzada** que se abre con
un clic, para que el camino común sea corto.

Nada de aquí es obligatorio salvo el sitio; cada integración que falte
simplemente deja su función en silencio.

## Observatorio

Dónde y quién eres.

- **Código MPC**, nombre, coordenadas y altura del observatorio (**Resolver
  coordenadas** desde el código, **Elegir en el mapa…**, o a mano). Es la
  identidad de tus informes MPC: si envías astrometría, usa el código.
- **Código AAVSO**: tu código de observador; se escribe en el traspaso a
  EXOTIC de los proyectos de tránsito.

## Equipo

Con qué observas.

- **Telescopio y límites**: la **apertura** y la **magnitud límite**. El
  puntaje de Tonight los lee para no sugerir lo inalcanzable. Sé honesto
  con la magnitud límite; el comando `inject` (capítulo 09) te da el número
  medido.
- **Cámara**: manda el **preset**, que rellena el tamaño de píxel y un
  perfil de partida de una vez. Elegir un preset carga **los datos de esa
  cámara** (full well, ruido de lectura, corriente de oscuridad, linealidad)
  por encima del perfil; la ganancia del sistema nunca se toca, porque es
  tuya. El tamaño de píxel y la focal se devuelven
  como la **escala de placa** (arcosegundos por píxel), que es lo que usan
  de verdad el consejo de exposición de NEOs, la fotometría y el informe
  MPC. El perfil medido (full well, ganancia del sistema, ruido de lectura,
  corriente de oscuridad, linealidad, exposición máxima de trabajo) está a
  un clic.

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
  la **lista de vigilias** de variables y el interruptor del **canal
  AAVSO**) y la **carpeta de proyectos**.

## Medida

Todo lo que convierte una noche de tomas en números: fotometría,
calibración y astrometría juntas, para que quien mide no salte de página.

- **Fotometría**: el método con el que arranca una placa *nueva* (el filtro
  adaptado). Una placa ya medida conserva su receta; el interruptor de la
  placa vive en la pestaña Fotometría, junto a la medida (capítulo 06).
- **Masters de calibración**: la biblioteca de bias, dark y flat contra la
  que la pestaña Calibración del editor resuelve su receta. Los ficheros se
  enlazan, nunca se copian ni se mueven.
- **Astrometría**: la compuerta de detección, el listón de envío al MPC, el
  barrido de velocidades, el chequeo contra otras estaciones (con
  **Find_Orb**) y los hilos de trabajo.
- **Solver de placa**: *Auto* prueba ASTAP local y cae a
  nova.astrometry.net; también puedes forzar uno. **Binario ASTAP**: ruta
  al ejecutable (vacío = buscar `astap` en el PATH), con **Test** para
  comprobarlo. **Guardar la WCS resuelta en la cabecera FITS** (activado
  por defecto) deja la placa resuelta para cualquier programa, sin tocar
  los píxeles.
- **EXOTIC (reducción de tránsitos)**: ruta a un **Python ≤ 3.10** y al
  **entorno EXOTIC**. **Preparar entorno** crea uno privado e instala
  EXOTIC dentro (necesita red la primera vez); **Test** comprueba que
  importa y dice su versión.
- **Avanzado**: el techo de saturación, el residual del flat y las
  tolerancias de astrometría. Tienen valores por defecto sensatos; tócalos
  solo si sabes por qué.

## Integraciones

El mundo exterior: un servidor de captura y las claves opcionales.

- **CCDciel**: host, puerto (3277 por defecto) y auto-conexión. El control
  solo funciona mientras CCDciel está abierto (capítulo 05).
- **NEOfixer**, **Astrometry.net**, **bot TNS**, **token de API de AAVSO**:
  claves opcionales para, respectivamente, el reporte a la comunidad, la
  resolución a ciegas de placas sin WCS, las imágenes de descubrimiento de
  transitorios y la fotometría de la comunidad que alimenta las vigilias de
  estrellas brillantes (capítulo 04).
- **Modelo de lenguaje (IA, opcional)**: para redactar el post y el asistente
  (capítulos 08 y 11). El endpoint es compatible con OpenAI: sirve un
  servicio de la nube (OpenRouter, Groq, Google AI Studio) o uno local
  (Ollama, LM Studio). Eliges el servicio conocido, pegas la clave y escribes
  el modelo, o pulsas **Listar modelos** y eliges el que el endpoint te dé
  (con sus nombres exactos si es local); **Probar conexión** comprueba que los
  tres encajan. Está apagado por defecto y nada sale de tu equipo hasta que lo
  usas.

## Interfaz

Cómo se ve y cómo habla la app.

- **Idioma**: español, inglés o el del sistema; se aplica al reiniciar.
- **Cielo animado en la Bienvenida**: unas estrellas titilan y la pantalla
  se funde una vez; la Luna se dibuja con su fase real de esta noche en
  cualquier caso. Se aplica al momento.
- **Barra superior solo con iconos** (editor FITS): los botones de acción
  muestran glifos compactos en vez de sus etiquetas. Se aplica al momento.
- **Cartas y anotaciones**: tu nombre (**Observador**), quién midió la placa
  (**Medidor**; vacío = el observador), las líneas de **telescopio** y
  **cámara**, la forma y el color de la marca del objeto, y las dos capas
  de metadatos (la banda de la placa en el editor, las cajas de esquina de
  las demás cartas).

> **¿Por qué hay tanto "opcional", sin pedir cuenta en ningún sitio?** Porque
> el observatorio es tuyo y los datos también: NightScribe funciona del todo
> sin una sola clave, y cada integración que falta degrada con elegancia (la
> función se queda callada) en vez de bloquearte. Las claves abren puertas;
> no levantan muros.
