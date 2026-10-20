# NightScribe

*[English version](README.md)*

**Planifica tu noche, entiende cada objeto, cuenta tu ciencia.**

NightScribe es la herramienta de trabajo de un observatorio astronómico
amateur: reúne en un solo sitio el ciclo completo de una observación, desde
elegir qué mirar esta noche según tu cielo y tu equipo, hasta entender el
objeto, capturar y reducir las imágenes y contar lo que has encontrado.

## ¿Qué es NightScribe?

Cuatro misiones, un solo bucle:

1. **Planificar la noche**: los mejores objetivos visibles desde *tu*
   observatorio, bajo *tus* restricciones reales, ordenados y explicados.
2. **Entender cada objeto**: parámetros orbitales y físicos traducidos a
   explicaciones precisas y divulgativas, en español e inglés.
3. **Capturar y reducir**: maneja tu montura y tu cámara por CCDciel o
   NINA/PINS, y calibra, apila y mide tus propias tomas: fotometría
   (variables, exoplanetas, supernovas) y astrometría de cuerpos menores
   lista para el MPC, sin salir de la ventana.
4. **Contarlo**: un borrador bilingüe (ES/EN) y los gráficos de la noche,
   redactados con los datos reales de tu sesión.

Cada objetivo elegido se convierte en un **proyecto**: una entidad persistente
con su propia carpeta, que te guía por **Ficha → Captura → Análisis →
Publicación** sin volver a preguntarte nada que ya sepa (coordenadas, ventana,
magnitud, plan de exposición). Semanas después, el proyecto sigue ahí:
revisitas, curva de luz, resultado final.

## Qué puedes seguir

Ocho tipos de objetivos comparten la misma lista cada noche, y el Sol y el
cielo ponen el contexto. Cada uno tiene su capítulo en la
[guía de usuario](docs/user/README.es.md): qué es, por qué importa esta noche
y cómo se mide.

- **NEOs, confirmados y sin confirmar**: una lista específica de tu sitio con
  score, prioridad y coste en minutos de telescopio, la exposición sin traza
  que permite tu cámara, el track & stack en la app y el reporte MPC
  contrastado con lo que publicaron otras estaciones.
- **Cometas**: magnitudes observadas en vivo, fechas de perihelio y
  actividad.
- **Candidatos a cometa (PCCP)**: objetos reportados como asteroides que
  podrían ser cometas. Llegar primero importa.
- **Supernovas**: los descubrimientos recientes, un blink de confirmación
  contra una referencia de survey, seguimiento multi-noche frente a las
  plantillas típicas de cada tipo y la exportación.
- **Tránsitos de exoplanetas**: los tránsitos de esta noche con su deriva
  O-C, si el tránsito entero cabe en tu noche y el handoff a EXOTIC.
- **Aproximaciones cercanas**: los acercamientos de ESA NEOCC con distancia
  de paso, tamaño y magnitud máxima.
- **Estrellas HADS**: variables δ Scuti de gran amplitud que varían en una
  sola sesión, con prioridades por color y la curva plegada por fase.
- **Estrellas variables y deberes**: tus campañas por cadencia, las estrellas
  cerca de un extremo predicho, tus vigilias chequeadas a diario contra ZTF y
  la fotometría comunitaria de la AAVSO, y la búsqueda de período.
- **El Sol y el cielo**: el estado del Sol, los eventos de las lunas de
  Júpiter para tu sitio y un calendario del cielo de 60 días calculado en
  local.

## Qué necesitas

| | |
|---|---|
| **Obligatorio** | Linux o Windows · Python 3.11+ (recomendado 3.12) *o* el instalador autónomo (sin Python) · ~500 MB de disco · conexión a internet para los datos en vivo (todo lo demás funciona offline) |
| **Recomendado** | Tu **código de observatorio MPC** (tres caracteres, los que tenga asignados tu estación): el asistente inicial resuelve tus coordenadas automáticamente y desbloquea la lista de NEOs específica de tu sitio · tu **fichero de horizonte local** (`.hrz` de TheSkyX o simples pares «az alt») · la apertura de tu telescopio y el píxel/focal de tu cámara |
| **Opcional** | **CCDciel o NINA/PINS** en ejecución local, si quieres que la app maneje montura y cámara (la integración con el observatorio; un backend a la vez) · cinco claves API gratuitas, cada una desbloquea un extra (reporte NEOfixer, resolución ciega Astrometry.net, atlas de contaminación lumínica, bot de TNS, token AAVSO) · el **asistente** opcional (un modelo que configures) · **EXOTIC** (la reducción de tránsitos), la única herramienta externa que instalas a mano, y el proyecto la publica lista para descomprimir: **Find_Orb** viaja dentro de los instaladores y de los paquetes Linux; ver *Integraciones opcionales* |

Sin cuentas, sin registros, sin telemetría: NightScribe corre en tu ordenador
y solo habla con los servicios públicos de datos listados más abajo.

## Tus primeros cinco minutos

1. **Instala.** No necesitas Python: todos los ficheros están en la
   [página de Releases](https://github.com/irydeo/nightscribe/releases). Elige
   tu sistema:
   - **Windows**: ejecuta el instalador `NightScribeSetup-*.exe` (por usuario,
     sin permisos de administrador). No está firmado, así que Windows tiene dos
     formas de pararlo: SmartScreen avisa y te deja seguir con *Más información
     → Ejecutar de todas formas*, mientras que el **Control inteligente de
     aplicaciones** (Windows 11, activado por defecto en instalaciones nuevas)
     lo bloquea sin salida. ¿Prefieres no instalar nada? Descomprime el zip
     portable `NightScribe-*-windows-x64.zip` y ejecuta `nightscribe.exe gui`
     (las mismas dos barreras valen para él). Qué hacer con el Control
     inteligente de aplicaciones está en
     [la guía](docs/user/01-getting-started.es.md).
   - **Linux**: instala el `.deb` (Debian, Ubuntu, Mint) con
     `sudo apt install ./nightscribe_*_amd64.deb`, o el `.rpm` (Fedora,
     openSUSE) con `sudo dnf install ./nightscribe-*.x86_64.rpm`, y luego
     ejecuta `nightscribe gui`.

   Los pasos completos por sistema están en [INSTALL.es.md](INSTALL.es.md).
   Ejecutar desde el código fuente es la última opción de allí, para colaborar.

2. **El asistente solo pide una cosa: tu observatorio.** Escribe tu código MPC
   y tus coordenadas se rellenan desde la lista del MPC; o introduce nombre,
   latitud, longitud y altitud a mano.
3. La vista **Esta noche** (desde **+ NUEVO PROYECTO** en la cabecera) calcula
   tu noche por sí sola: descarga las listas de objetivos, las filtra por tu
   sitio y tu equipo, y lo ordena todo.
4. **Haz clic en cualquier objetivo** y verás su ficha completa explicada.
   ¿Te gusta lo que ves? Un botón: **Crear proyecto**.
5. Cuando tengas un minuto, abre **Herramientas → Configuración…**: fichero de
   horizonte, magnitud límite, escala de placa de la cámara, valores de sesión.
   Todo trae valores por defecto sensatos; nada más es obligatorio.

### Desde el código fuente (para colaborar)

NightScribe también se ejecuta desde un clon; el recorrido completo por sistema
está en [INSTALL.es.md](INSTALL.es.md). La versión corta:

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m nightscribe gui
```

## Tutoriales en vídeo

La [lista de tutoriales en YouTube](https://www.youtube.com/playlist?list=PLASv2NZqn7zU)
reúne los recorridos del proyecto. La narración va en español y la interfaz de
la aplicación en inglés; la [guía de usuario](docs/user/README.es.md) es la
referencia escrita.

## Una noche completa (y las semanas siguientes)

La guía recorre [una noche real](docs/user/03-projects.es.md) desde el primer
clic hasta el reporte. La versión corta:

1. **Media tarde.** Un clic en **+ NUEVO PROYECTO** calcula la noche: el mejor
   objetivo primero, un chip que dice cuánto ilumina la Luna y otro que anuncia
   una sombra de las lunas de Júpiter, y una razón de una línea para la fila de
   arriba.
2. **Haces clic en él.** La ficha dice qué es el objeto, a qué velocidad se
   mueve y, porque conoce tu cámara, tu exposición máxima sin traza. Pulsas
   **Crear proyecto**.
3. **Planificar y capturar.** Dimensionas la sesión; la app confirma que cabe
   en la ventana segura. Exportas la efeméride y la secuencia o, con CCDciel o
   NINA/PINS conectados, envías el plan y lanzas la captura sin salir de la
   app.
4. **Análisis.** Al volver abres la visita en el editor: resuelve el fotograma
   de referencia, registra la secuencia y **la apila siguiendo al objeto**,
   mide cada observación y contrasta el resultado con el de las otras
   estaciones. El reporte MPC sale listo para enviar.
5. **Las semanas siguientes.** El diario recuerda esa noche solo, la curva de
   luz crece, el panel te avisa cuando toca revisitar y el borrador bilingüe ya
   está escrito con los datos reales de la sesión.

## De dónde salen los datos

La lista de esta noche y las fichas de objeto se alimentan de servicios
públicos, cada uno con su refresco: **NEOfixer**, el **MPC** (PCCP, códigos de
observatorio, observaciones publicadas), **COBS**, **Rochester Astronomy**,
**ExoClock**, **ESA NEOCC**, el catálogo **HADS**, **AAVSO** (VSX, foro,
campañas y fotometría), **ALeRCE/ZTF**, **JPL** (SBDB, Horizons, CAD),
**SIMBAD**, **TNS**, el **NASA Exoplanet Archive**, **VizieR**, **NOAA SWPC**,
**SILSO**, **NASA SDO** y el **DESI Legacy Survey**.

Todo el acceso a red pasa por una **caché SQLite con TTL por fuente**: repetir
una consulta es instantáneo y gratis para el servicio, y una fuente caída
nunca rompe el resto de la app. Las posiciones del Sol, la Luna y los planetas,
el calendario del cielo y toda la **reducción** (registro, apilado, medida,
períodos) se calculan en local, sin ningún servicio de por medio. La tabla
completa, con lo que da cada fuente y si necesita clave, está en
[docs/DATA_SOURCES.es.md](docs/DATA_SOURCES.es.md).

## Integraciones opcionales

Todo lo siguiente es opcional; cada pieza que falta degrada con elegancia y te
lo dice. Se configuran en **Herramientas → Configuración → Integraciones**.

| Integración | Qué desbloquea |
|---|---|
| **CCDciel** (local, host/puerto) | El paso **Captura** de cada proyecto: estado, apuntar telescopio, goto astrométrico, **Detener goto**, preparar el plan (leído de vuelta) y captura en vivo. Solo con CCDciel en ejecución |
| **NINA / PINS** (local, host/puerto) | El mismo paso **Captura** por el plugin **Advanced API v2**: estado, apuntar telescopio, goto astrométrico (Center), **Detener goto**, rueda de filtros y captura snapshot de una toma. NINA en Windows, PINS en Linux; un backend a la vez |
| **Clave API de NEOfixer** | Reportar `will_observe` / `observed` de vuelta para la coordinación comunitaria |
| **Clave de Astrometry.net** (gratuita) | Resolución ciega de FITS sin WCS en el blink |
| **Credenciales de bot TNS** | Imágenes de descubrimiento dentro de la app (respetando la licencia de cada survey) |
| **Token API de AAVSO** | Fotometría comunitaria para las vigilias de estrellas brillantes |
| **Código de observador AAVSO** | Se rellena en las exportaciones fotométricas y en el handoff a EXOTIC |
| **Clave de contaminación lumínica** (gratuita, lightpollutionmap.info) | El atlas de brillo del cielo de tu sitio: el contexto Bortle que usan las notas de calidad del cielo |
| **Asistente** (opcional, apagado por defecto) | Un panel de chat que responde desde la propia guía y las notas de diseño de la app, offline y sin embeddings. Necesita un modelo que configures; sin él la app no cambia |
| **Find_Orb** (viaja en los instaladores y los paquetes Linux) | El chequeo de tu medida astrométrica contra las observaciones que publicaron otras estaciones, antes del informe MPC. Viaja dentro de NightScribe, así que funciona de serie; desde un árbol de fuentes lo instalas tú, y la app lo dice en vez de fingirlo |
| **EXOTIC** (Python 3.10 a 3.12 externo, o el entorno ya preparado que publica el proyecto) | La reducción de tránsitos: la app escribe el handoff, ejecuta EXOTIC por ti e importa su curva de luz y sus parámetros al proyecto. El entorno ya preparado es un zip que trae su propio Python, así que no hay nada que instalar: lo descomprimes y apuntas Ajustes a su intérprete. Sin él el handoff sigue siendo tuyo para lanzarlo a mano |

## Tus datos son tuyos

Todo lo que NightScribe sabe vive en una base de datos **SQLite** local en el
directorio de datos de tu usuario: la caché HTTP, tus proyectos, sesiones,
fotometría, campañas y ajustes. Cada proyecto tiene su **carpeta contenedora**
(planes, secuencias, informes, gráficos, posts) bajo una raíz que eliges tú y
puedes cambiar más adelante. Sin cuentas, sin nube, sin telemetría. Desinstala
y borra la carpeta: no queda nada en ningún otro sitio.

## Inicio rápido y CLI

Instala primero (ver *Tus primeros cinco minutos*). Luego todo lo que hace la
GUI de **planificación y publicación** tiene su contrapartida en línea de
comandos:

```bash
nightscribe gui        # aplicación de escritorio
nightscribe tonight    # mejores objetivos de esta noche (CLI)
```

`tonight`, `explore`, `post`, `solar`, `blink`, `sequence`, `history`,
`project` e `inject` son el resto (`--help` en cada uno para más detalles), y
el capítulo [09. La línea de comandos](docs/user/09-cli.es.md) tiene la lista
completa. La **reducción** (calibración, track & stack, astrometría,
fotometría, períodos) vive en la GUI.

Consulta [INSTALL.es.md](INSTALL.es.md) para las instrucciones completas por
sistema operativo (primero el instalador autónomo y los paquetes Linux), y
[CONTRIBUTING.es.md](CONTRIBUTING.es.md) para colaborar.

## Documentación

**La [guía de usuario](docs/user/README.es.md)**
([English](docs/user/README.md)) recorre el ciclo completo, del primer arranque
al reporte MPC, en capítulos cortos con el «por qué» de cada opción. Se publica
como web: **<https://irydeo.github.io/nightscribe/>** (**Ayuda → Guía de
usuario (web)**).

Diseño, arquitectura, fuentes de datos, scoring, flujos de trabajo y todas las
decisiones de diseño están en [`docs/`](docs/), en español e inglés.

¿Falta algo, algo está mal o no se entiende? [Abre una incidencia](https://github.com/irydeo/nightscribe/issues).

## Licencia

NightScribe es software libre, publicado bajo la
[GPL v3](https://github.com/irydeo/nightscribe/blob/main/LICENSE): puedes
usarlo, estudiarlo, modificarlo y compartirlo, y lo que transmitas sigue
siendo libre para el siguiente. No hay edición de pago ni función bloqueada.
