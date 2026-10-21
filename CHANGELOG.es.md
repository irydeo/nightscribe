# Registro de cambios

Aquí se documentan los cambios notables de NightScribe. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto usa
[Versionado Semántico](https://semver.org/lang/es/).

## [Sin publicar]

### Corregido

- **La línea «Saved» ya no mueve los botones.** Aparecía en el primer guardado y
  se quedaba, empujando el botón de análisis **77 px** hacia abajo bajo el propio
  cursor del observador, una vez, para siempre. Ahora conserva su sitio y se va
  sola a los dos segundos, que es para lo que sirve una confirmación.

- **El techo de la propia placa es el que manda cuando la placa no es de tu
  cámara.** El límite de linealidad del perfil está escrito en tus ADU, y las ADU
  son propiedad de un instrumento: una placa de Las Cumbres (techo de 248 800
  ADU) caía toma tras toma como «no lineal» y la gráfica salía vacía sin
  explicación. El pozo lleno en electrones es lo que distingue a los dos
  detectores, y el panel ahora dice cuál de los dos casos es.

- **El filtro de la placa se convierte en banda solo cuando de verdad lo es.**
  Una placa cuya tarjeta `FILTER` dice `R` contra una secuencia que lleva `Rc`
  caía a la primera banda de la lista, que es una calibración silenciosamente
  equivocada (el punto cero cuelga entonces de las magnitudes de otra banda). Un
  `R` de Cousins **es** el `Rc` del catálogo; un `rp` de Pan-STARRS **no**, y
  fingir que sí sería inventarla.

- **Una serie que no ha medido nada dice por qué.** Se acabó la gráfica vacía con
  una lista de tomas impoluta al lado: el panel cuenta las marcas, nombra la que
  dominó y dice qué hacer.

### Cambiado

- **El detrend arranca en «auto» para todos los tipos de proyecto menos el
  tránsito.** La extinción es un sistemático que está siempre, y una rotación,
  un estallido o una pulsación no comparten su escala de tiempo, que es lo que
  hace separable la tendencia. Es la política autolimitada: aplica siempre la
  masa de aire y solo añade los términos extra cuando la dispersión baja de
  verdad. Un tránsito conserva la curva cruda a propósito, porque su tendencia
  se resuelve junto al modelo (el propio término de masa de aire de EXOTIC).

### Corregido

- **La masa de aire y el sitio se toman de la placa, no de tus Ajustes.** El
  motor calculaba la altitud del objetivo desde el sitio configurado en Ajustes,
  que es lo correcto para tu observatorio y equivocado para la placa de
  cualquier otro: en una placa de Las Cumbres (un 1 m en McDonald) reducida
  desde un sitio en España, la masa de aire salía **subiendo hasta 5,2 a lo
  largo de la noche** cuando la propia cabecera decía 1,16 a 1,03. Ese número
  alimenta el término de centellea del error, así que el error crecía de 0,05 a
  **0,39 mag** en la noche, y la gráfica lo lee como verde, luego naranja y
  luego rojo. Con las tarjetas de la propia placa esos mismos errores quedan
  planos en 0,03. La misma regla que ya seguía la escala de placa se aplica
  ahora al tiempo: **lo que la placa dice de sí misma manda sobre los Ajustes**,
  y los Ajustes son el respaldo para un equipo que no declara nada. El detrend
  también se beneficia, porque la masa de aire es su regresor: **vuelve a medir
  la serie** para tener los errores corregidos y la tendencia corregida (los
  puntos ya guardados conservan los números viejos, que son el registro de lo
  que se midió).

- **El tamaño del telescopio también se lee de la placa.** Es la entrada de ese
  mismo término de centellea, y un 1 m de Las Cumbres medido con los 10" del
  observador lo dejaba 2,5 veces demasiado grande. Solo se hace caso a una placa
  que diga de verdad el tamaño, porque es la única forma de leerlo sin
  inventarlo: Las Cumbres lo escribe en el propio identificador del telescopio
  (`1m0a`, `0m4c`, `2m0a`), mientras que un nombre como `Cecilia` o `CDK17` no
  dice nada del tamaño, y ahí se quedan los Ajustes del observador: para su
  propio telescopio son la respuesta correcta. Con las dos tarjetas leídas, los
  errores de la serie que se reportó pasaron de 0,05 a 0,39 mag a lo largo de la
  noche (el degradado verde-naranja-rojo) a un **0,016 plano**.

## [0.1.3] - 2026-10-21

### Corregido

- **La lista de tomas del editor enseña ahora lo que la serie dijo de cada
  una.** La curva marcaba una toma cuya medida la serie había descartado y la
  lista de tomas no decía nada, así que un observador con la gráfica vacía y la
  tira de tomas impoluta solo podía concluir que sus datos eran malos: la noche
  en que se reportó, **338 de 379 tomas llevaban marca y la tira no decía
  nada**. Ahora las marca con la misma clasificación que lee la curva
  (`core/series_measure`): una marca de datos (no lineal, nube, seeing, un rayo
  cósmico, una toma que no se pudo alinear) convierte la toma en un problema y
  el filtro «solo problemas» la conserva; una de matiz (pocas comparadas) es una
  nota y nunca esconde una toma. La marca nombra el flag y lo explica en el
  tooltip, y el borde lleva el color que merece la medida: la misma gramática
  que ya comparten la curva y el panel de medida.

## [0.1.2] - 2026-10-20

Arregla lo único que podía llevarse por delante un entorno EXOTIC que funcionaba,
y deja de decir que no hay Python cuando sí lo hay.

### Corregido

- **«Preparar entorno» ya no puede destruir el entorno que ya tenías.** Borraba la
  carpeta de destino *antes* de construir, así que cualquier fallo posterior (sin
  red, sin disco, una cancelación) no dejaba nada; y un caso lo hacía **siempre**:
  la app ofrece como intérprete base el entorno que ella misma construyó, el
  borrado se llevaba ese intérprete a mitad de la construcción y el siguiente
  comando ya no podía ni ejecutarse. Ahora construye en una carpeta hermana y solo
  la pone en su sitio cuando el entorno nuevo funciona, así que una reconstrucción
  fallida es inofensiva.
- **Un intérprete base que vive dentro de la carpeta del entorno se rechaza**, con
  el motivo escrito, en vez de borrarse a mitad de la construcción.
- **La app ya no dice «no se ha encontrado Python» cuando el intérprete
  configurado no está.** Ese mensaje, con un Python perfectamente instalado en la
  máquina, es lo que hacía que un entorno borrado pareciera una configuración
  perdida. Ahora distingue los dos casos («el intérprete que apuntaste ya no está»
  y «no sirve para EXOTIC») y busca otro intérprete por su cuenta.
- El resultado de «Preparar entorno» llega siempre al registro, así que un fallo
  deja rastro en vez de silencio.

### Añadido

- **El entorno de EXOTIC se publica listo para descomprimir.** Ahora lo construye y
  lo publica el proyecto, en su propia release (tag `exotic-env`), como un zip por
  plataforma con un CPython portátil 3.11 y EXOTIC 4.3.1 ya instalado dentro: lo
  descomprimes donde quieras y apuntas Ajustes al intérprete que lleva. Nada que
  instalar, ningún Python que buscar. Las versiones de dentro están fijadas en un
  fichero de bloqueo comprometido en el repositorio, así que el mismo zip es
  siempre la misma pila, y la release solo se reconstruye cuando cambia ese fichero.

### Cambiado

- **EXOTIC acepta Python 3.10 a 3.12**, no solo 3.10 y anteriores. El 3.10 llegó a
  su fin de vida en octubre de 2026, y rechazar el 3.11 y el 3.12 obligaba a buscar
  un intérprete que la app ya podía haber usado. El 3.11 está verificado de punta a
  punta: un `pip install exotic` completo sobre 3.11.2 deja EXOTIC 4.3.1 importable
  con todas las versiones que fija (numpy 1.26.4, astropy 6.1.7, numba 0.59.1). El
  3.13 queda fuera, porque numpy 1.26 no tiene ruedas para él.

## [0.1.1] - 2026-10-19

Arregla la fotometría en las placas **normalizadas** (los masters de 32 bits en
coma flotante con valores de 0 a 1 que exportan PixInsight y Siril por defecto)
y una corrida de track & stack que moría sin decir por qué.

### Corregido

- **Las comparsas ya se encuentran en una placa normalizada.** La validación de
  cada candidata mezclaba unidades: la señal la leía de la placa (0 a 1) y el
  ruido lo calculaba con la ecuación CCD, anclada en electrones por ADU. El
  término del ruido de lectura, que no escala con la placa, aplastaba la señal y
  **todas** las candidatas caían por «SNR 0 en la apertura», así que la
  propuesta devolvía cero estrellas. Medido en una placa real (un NEO de
  magnitud 20,5 con tomas de 10 s): 0 comparsas antes, 8 más la de control
  después.
- **La barra de error vuelve a ser la correcta en esas placas.** El mismo
  desajuste hacía que el error en magnitud de una estrella real saliera de **52
  magnitudes** donde la respuesta honesta es 0,012. Y al medir una **serie**
  sobre las pilas de 2020 de un transitorio, los puntos guardados llevaban
  errores de **228 a 384 magnitudes**: el mismo punto, con el arreglo, sale con
  0,09.
- **Los dos techos vuelven a vigilar en esas placas.** La saturación y el límite
  de linealidad se comparan en ADU, así que en una placa de 0 a 1 nunca se
  disparaban: un pico de 0,9 pasaba por delante de un límite de 53 000 ADU sin
  decir nada.
- **Un objetivo que no se puede medir ya no tumba la corrida del track &
  stack.** La ruta que mide el objetivo en su apilado y las comparsas en otro
  multiplicaba el centroide del objetivo por la escala de la placa, y cuando el
  objetivo no se puede medir ese centroide es `None`: la corrida moría con un
  `TypeError` en vez de decir el motivo, que ya llevaba dentro. Visto con dos
  objetos reales, uno de ellos a cuarenta píxeles del borde del campo.

**Si sigues en la 0.1.0 y das con esto**, la salida provisional es medir sobre
una placa en ADU: los fotogramas individuales, o un master multiplicado por
65 535 para devolverle la escala. La 0.1.1 ya no lo necesita.

## [0.1.0] - 2026-10-18

La primera versión pública. NightScribe acompaña a un proyecto de observatorio
durante todo su ciclo de vida: **planifica la noche, entiende el objeto, captura
y reduce, y cuéntalo**. Es una beta: cuenta con aristas.

### Añadido

**Planificar la noche**
- Una lista ordenada y explicada de lo que merece la pena observar esta noche
  desde tu sitio y con tu equipo, entre ocho tipos de objetivos: NEOs
  (confirmados y candidatos NEOCP), cometas, candidatos a cometa (PCCP),
  supernovas, tránsitos de exoplanetas, aproximaciones cercanas, estrellas HADS,
  y variables y deberes.
- Una puntuación de 0 a 100 con su frase de «por qué esta noche», el horizonte
  local y la magnitud límite, la interferencia de la Luna, la viabilidad de la
  sesión y el coste en minutos de telescopio.
- El Sol y la Luna, un calendario del cielo de 60 días calculado sin red, y los
  eventos de las lunas de Júpiter (tránsitos y sombras) para tu sitio.

**Entender cada objeto**
- Una ficha que traduce los parámetros orbitales y físicos a lenguaje claro, con
  gráficos (órbita, cielo, campo del survey, curva de luz) y chips de captura
  (magnitud, ritmo, exposición máxima sin estela, ventana, coordenadas
  copiables).

**Capturar**
- Maneja CCDciel (completo) o NINA/PINS (en pruebas) y apunta el telescopio:
  envía el plan, arranca y para la captura, y síguela con la última toma
  previsualizada en la ventana.
- Exporta la efeméride (elementos MPC o informe de órbita) y la secuencia de
  captura.

**Reducir, en el editor FITS unificado**
- Calibración: una biblioteca indexada de masters por cámara, ganancia,
  temperatura, exposición y filtro, con receta declarativa y flats
  normalizados.
- Track & stack: resuelve, registra y combina, con la posición por toma, aviso
  de dithering, la secuencia centrada (GIF o montaje) y un modo manual para un
  objeto débil.
- Fotometría: medidas sueltas con guardas, secuencias de comparación con el
  selector de la carta, series con veto de ensemble y puertas de calidad, la
  búsqueda de período (Lomb-Scargle, PDM, FAP por bootstrap) y el ajuste de
  tránsito con el handoff a EXOTIC.
- Astrometría: centroides subpíxel, combinación por toma y del apilado, el
  informe MPC (ADES XML/PSV y 80 columnas), el envío, el chequeo contra otras
  estaciones con Find_Orb y la exportación a ExoClock.
- Liberar espacio: archiva los originales de una visita dentro del proyecto y
  tráelos de vuelta, sin pisar nunca una toma recapturada.

**Proyectos, visitas y campañas**
- Cada objetivo se convierte en un proyecto con su propia carpeta y un flujo
  Ficha, Captura, Análisis, Publicación; cada noche es una visita; las campañas
  y las vigilias de variables llevan su propia cadencia.
- El diario de observación, el panel «necesita tu atención» y el chequeo diario
  de las vigilias contra ZTF y la fotometría de la comunidad AAVSO.

**Contarlo**
- Borradores bilingües (ES/EN) de post y tuit con los gráficos de la noche, a
  partir de los datos reales de la sesión, con un pase de IA opcional.

**Interfaz e idiomas**
- Tres pestañas (Esta noche, Proyectos, Campañas), el editor FITS unificado, la
  interfaz en español e inglés y la guía de usuario sin conexión.

**Línea de comandos**
- Planifica y publica desde la terminal: `tonight`, `explore`, `post`, `solar`,
  `blink`, `history`, `sequence`, `inject`, `project` y `gui`.

**Asistente opcional**
- Apagado por defecto: responde desde la propia guía y los ADRs de la app, sin
  conexión, a través de un modelo que configures.

**Distribución**
- Instalador de Windows (por usuario, sin permisos de administrador) y zip
  portable, un `.deb` para Debian 13+ y Ubuntu 25.10+, un `.rpm` para Fedora 42+
  y openSUSE Tumbleweed y un PKGBUILD para Arch. Find_Orb viaja dentro y la
  documentación viaja con la app.
- Una ruta GPU por OpenCL para el registro y el combine, encendida por defecto,
  que cae al procesador.

### Notas

- Es la primera versión pública, así que es una **beta**: cuenta con aristas.
  Repórtalas en <https://github.com/irydeo/nightscribe/issues>, adjuntando el
  registro (**Ayuda → Abrir el registro**).
- Find_Orb viaja dentro del instalador de Windows y de los paquetes Linux;
  EXOTIC (la reducción de tránsitos) es la única herramienta externa que
  instalas a mano.
- La integración con **NINA/PINS** **no está terminada**: está para probarla y
  para que reportes qué falta o qué falla, y el resto está previsto para la
  **0.2**. CCDciel es el que está completo hoy (el capítulo 05 lista lo que
  NINA/PINS todavía no hace).
- Los binarios de Windows **no están firmados**: el Control inteligente de
  aplicaciones los bloquea sin salida y SmartScreen avisa hasta que se labra
  reputación, así que el instalador puede pedir un *Ejecutar de todas formas*
  explícito o una máquina con el Control inteligente de aplicaciones apagado.
  Los detalles están en docs/user/01-getting-started.
