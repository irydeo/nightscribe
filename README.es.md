# NightScribe

*[English version](README.md)*

**Planifica tu noche, entiende cada objeto, cuenta tu ciencia.**

NightScribe es una aplicación de escritorio (GUI Qt6 + CLI) para observatorios
astronómicos amateur, construida alrededor de tres misiones:

1. **Planificar la noche** — los mejores objetivos visibles desde *tu*
   observatorio, bajo *tus* restricciones reales.
2. **Entender cada objeto** — parámetros orbitales y físicos traducidos a
   explicaciones precisas y divulgativas.
3. **Contar tu ciencia** — posts bilingües (ES/EN), tuits y gráficos listos
   para redes sociales.

Todo empieza con una sugerencia y termina como un resultado publicado: cada
objetivo elegido se convierte en un **proyecto** que te guía por
planificar → capturar → procesar → publicar sin volver a preguntarte nada.

## Esta noche — planifica la noche

Una única respuesta ordenada a *«¿qué puedo hacer esta noche?»*, mezclando
ocho tipos de objetivos:

- **NEOs** — lista de NEOfixer para tu sitio: score, prioridad, coste en
  minutos, velocidad aparente, incertidumbre, indicadores
  NEOCP/impacto/radar/NHATS y elementos orbitales preliminares (con sigmas)
  para los NEOCP aún sin confirmar.
- **Cometas** — magnitudes en vivo de COBS, fechas de perihelio, indicadores
  de actividad.
- **PCCP** — la página de confirmación de posibles cometas del MPC, con su
  comet-score.
- **Supernovas** — los descubrimientos recientes de Rochester Astronomy.
- **Tránsitos de exoplanetas** — prioridades de ExoClock (ESA Ariel) y deriva
  O-C.
- **Alertas de aproximación** — próximos acercamientos de ESA NEOCC
  (distancia, tamaño, magnitud máxima).
- **Estrellas HADS y variables** — el catálogo de δ Scuti de gran amplitud
  (P. Wils) y las predicciones de extremos del VSX, casadas con tu noche.
- **Deberes de campaña y canal AAVSO** — miembros de campañas que tocan por
  cadencia, tus vigilias de variables, y las alertas del foro/campañas activas
  de la AAVSO, cuando la estrella está arriba.

Cada objetivo recibe un **score unificado 0–100** a partir de cuatro familias
ponderadas: prioridad científica (0–35), observabilidad desde tu sitio (0–30),
urgencia (0–20) y gancho divulgativo (0–15) — más retroalimentación de tu
propio historial (observado-pero-no-publicado recibe un empujón; lo publicado
recientemente pierde novedad). El Top-N garantiza **diversidad de tipos**: una
noche con un NEO, un cometa y un tránsito vale más que tres NEOs. Cada
elección llega con una frase de **«por qué esta noche»**, en español e inglés.

El planificador respeta tus restricciones reales:

- **Magnitud límite** — política híbrida: corte duro para SN/cometas/
  tránsitos, aviso suave `⚠` para NEOs/PCCPs (las predicciones pueden fallar;
  se marcan y atenúan, nunca se descartan).
- **Horizonte local** — tu fichero `.hrz` de TheSkyX (o pares «az alt») más un
  margen de seguridad; altitud mínima plana como respaldo.
- **Luna** — aviso y penalización de score por separación/iluminación, nunca
  un filtro duro.
- **Viabilidad de sesión** — la ventana debe cubrir la sesión; la tarjeta te
  dice *«inicio seguro hasta las HH:MM»*.
- **Escala de placa** — píxel de cámara + focal fijan la exposición máxima sin
  traza para los NEOs rápidos.

Los chips de eventos del cielo en la cabecera de Esta noche (luna llena, una
oposición, un tránsito de sombra en Júpiter…) saltan directos al calendario
del cielo. Un clic en cualquier objetivo **crea su proyecto**.

## Proyectos — del objetivo al resultado publicado

Un proyecto es una entidad persistente (tipo, objeto, estado, foto completa
del contexto) con una **carpeta contenedora** que reúne todo lo que produce,
y tres pasos guiados. La pestaña **Detalles** muestra siempre primero la
tarjeta de presentación del objeto: frase gancho, bullets divulgativos, tabla
de parámetros con explicaciones ES/EN, gráficos (órbita, cielo nocturno,
campo, curva de luz) y los chips de captura (magnitud, velocidad ″/min,
exposición máxima sin traza, ventana, horas sobre el horizonte).

- **Planificar y Capturar** — dimensiona la sesión (N tomas × exposición,
  filtro) y la app comprueba que cabe en la ventana segura. Exporta la
  secuencia para **NINA** (JSON), **CCDciel** (`.targets`) o **CSV**; exporta
  **efemérides** con paso configurable para TheSkyX y Cartes du Ciel. Con
  CCDciel conectado, envía el plan y arranca la captura sin salir de la app.
- **Procesar** — importa el FITS resultante (objetivo y coordenadas ya
  conocidas del contexto). Las supernovas se confirman con el **blink** contra
  PanSTARRS DR1 g — GIF/MP4/PNG antes-y-después con la marca de agua del
  observatorio. La astrometría de NEO/PCCP se pega, se valida (80
  columnas/ADES, código MPC, designación) y se empaqueta en un **informe MPC**
  listo para enviar por correo. La fotometría se exporta como **CSV** y
  **AAVSO EFF**. Los tránsitos pasan a **EXOTIC** con un `inits.json`
  pre-rellenado.
- **Publicar** — el post bilingüe + tuit se redactan con los **datos reales de
  la sesión** (fecha, N×t, filtro), y las marcas de observado/publicado
  realimentan el motor de sugerencias.

## Campañas y variables

- **Campañas** — una campaña es el compromiso compartido de un grupo: objetivo
  científico, protocolo (cadencia, filtros, estrellas de comparación), URLs de
  reporte/datos. Una campaña, muchos proyectos asociados (borrar la campaña
  los libera, no los borra). Un miembro *toca* cuando su última sesión tiene
  `cadence_nights` noches — y aterriza en Esta noche automáticamente. La
  pestaña muestra la salud completa: miembros × cadencia × eventos (⚡ cuando
  una variable salta).
- **Vigilias de variables** — tu lista de vigilancia permanente (vigilia de
  erupción de T CrB, vigilia de caída de R CrB, …), una estrella por línea,
  chequeada contra la última magnitud ZTF; las brillantes leen la fotometría
  comunitaria de la AAVSO con tu token.
- **Motor de variables** — predicciones de extremos del VSX con fechas
  julianas heliocéntricas, un asesor de eventos ante saltos de magnitud, y el
  catálogo híbrido HADS (snapshot local + la hoja viva de P. Wils).

## Observatorio — centro de control CCDciel

La cuarta pestaña maneja tu observatorio **CCDciel** local por JSON-RPC (solo
con CCDciel en ejecución): estado de un vistazo (versión, temperatura del CCD,
seguimiento, movimiento), **Apuntar telescopio** (slew rápido a la posición
recién calculada de un objetivo en movimiento), **Goto astrométrico** (slew +
captura + resolución de placas + corrección — absorbe el error de efemérides,
la vía fiable para NEOCPs) y **captura en vivo** (prepara el plan guardado del
proyecto, arranca la secuencia).

## Sol y calendario del cielo

Desde el menú Herramientas:

- **El Sol ahora** — canales de NASA SDO (corona 193/304/171 Å, manchas,
  magnetograma), mapa de regiones activas de NOAA, SSN / F10.7 / Kp /
  fulguración semanal, un panel PNG con marca de agua para tus redes y un
  borrador bilingüe del post «el cielo hoy».
- **Calendario del cielo** — hoy + 60 días, calculado **100 % en local** (sin
  red): fases lunares verdaderas, perigeo/apogeo, conjunciones Luna–planeta y
  planeta–planeta, oposiciones y máximas elongaciones (como cruces de
  longitud eclíptica), **eclipses probables** (geometría de conos de sombra,
  etiquetados con honestidad) y lluvias de meteoros. Validado contra astropy
  y almanaques.
- **Las lunas de Júpiter esta semana** — tránsitos de los galileanos **y de
  sus sombras** sobre el disco, filtrados para tu sitio (Júpiter arriba y de
  noche), calidad de planificación ±10 min.

## Diario

Tu diario de observación se escribe solo: proyectos creados/cerrados, sesiones
registradas, ficheros producidos, puntos fotométricos, campañas — agrupados
por **noche de observación** (de mediodía a mediodía local) y filtrables por
tipo.

## Explora y Post — entiende y cuenta

- **Explora** cualquier objeto: identidad y datos físicos cruzados desde JPL
  SBDB/Horizons/CAD, SIMBAD, TNS, NASA Exoplanet Archive y más; familia
  orbital, MOID, tamaño desde H, próxima aproximación — cada parámetro
  explicado en lenguaje llano, ES y EN.
- **Post** genera los borradores bilingües + tuit + gráficos PNG listos para
  adjuntar: vista de la órbita, cielo nocturno con *tu* silueta de horizonte,
  panel del Sol, línea de tiempo del tránsito, antes/después de la supernova,
  rastro de movimiento del NEO.

## Necesita tu atención

La app habla primero: la portada de Proyectos lista las 3–5 cosas que piden
acción — un miembro de campaña que toca esta noche, un proyecto de supernova
que pide revisita, una observación nunca publicada — cada una con su razón en
lenguaje llano y un botón que aterriza exactamente donde se actúa.

## Fuentes de datos

NEOfixer · MPC (PCCP, ObsCodes) · JPL SBDB / Horizons / CAD · ESA NEOCC ·
COBS · Rochester Astronomy · SIMBAD · TNS · ExoClock · NASA Exoplanet Archive ·
AAVSO (VSX, alertas del foro, campañas, fotometría comunitaria) · ALeRCE/ZTF ·
catálogo HADS (P. Wils) · NOAA SWPC · SILSO · NASA SDO · Astrometry.net ·
recortes de PanSTARRS DR1 — más tu CCDciel local cuando está conectado.

Toda la red pasa por una caché SQLite con TTL por fuente; que una fuente caiga
nunca rompe el resto (estado en el menú *Fuentes de datos*), y todo excepto los
datos en vivo funciona offline.

## Inicio rápido

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m nightscribe gui        # aplicación de escritorio
.venv/bin/python -m nightscribe tonight    # mejores objetivos de esta noche (CLI)
```

Comandos CLI (`--help` en cada uno para más detalles):

| Comando | Qué hace |
|---|---|
| `gui` | aplicación de escritorio |
| `tonight` | mejores objetivos de esta noche (`--fecha`, `--top`) |
| `explore` | ficha explicada de un objeto |
| `post` | borradores bilingües + tuit (`--png` para gráficos) |
| `solar` | estado del Sol (`--png` para el panel) |
| `blink` | blink de SN: tu FITS vs PanSTARRS (`--video`, `--post`, `--zoom`…) |
| `history` | diario de observación |
| `project` | gestión mínima de proyectos (list/create/advance/close/…) |

Consulta [INSTALL.es.md](INSTALL.es.md) para instrucciones completas por
sistema operativo y el instalador autónomo, y
[CONTRIBUTING.es.md](CONTRIBUTING.es.md) para colaborar.

## Documentación

Diseño, arquitectura, fuentes de datos, scoring, flujos de trabajo y todas las
decisiones (ADRs) están en [`docs/`](docs/) (bilingüe ES/EN).

## Licencia

GPL v3 — (c) 2026 Francisco José Calvo Fernández (Observatorio Irydeo, MPC Z41).
