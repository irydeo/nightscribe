# Registro de cambios

Aquí se documentan los cambios notables de NightScribe. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto usa
[Versionado Semántico](https://semver.org/lang/es/).

## [Sin publicar]

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
