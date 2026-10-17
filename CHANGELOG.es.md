# Registro de cambios

Aquí se documentan los cambios notables de NightScribe. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto usa
[Versionado Semántico](https://semver.org/lang/es/).

## [Sin publicar]

## [0.1.0] - 2026-10-15

La primera versión pública. NightScribe cubre todo el ciclo de vida de un
proyecto de observatorio: **planifica la noche, entiende el objeto, captura y
reduce, y cuéntalo**.

### Añadido

- **Planificar la noche**: una lista ordenada y explicada de lo que merece la
  pena observar esta noche desde tu sitio y con tu equipo, entre ocho tipos de
  objetivos (NEOs y candidatos NEOCP, supernovas, cometas, candidatos PCCP,
  tránsitos de exoplanetas, estrellas HADS, variables y deberes, y
  aproximaciones cercanas y alertas), con una puntuación de 0 a 100, una frase
  de «por qué esta noche», el calendario del cielo y el contexto de Sol y Luna.
- **Entender el objeto**: una ficha que traduce los parámetros orbitales y
  físicos a lenguaje claro, con gráficos (órbita, cielo, campo del survey,
  curva de luz) y chips de captura (magnitud, ritmo, exposición máxima sin
  estela, ventana, coordenadas copiables).
- **Capturar y reducir**: maneja CCDciel o NINA/PINS, y su editor FITS
  unificado calibra (biblioteca de masters), apila (track & stack, con
  registro y el modo manual del objeto débil), mide fotometría (secuencias de
  comparación, series, períodos, ajuste de tránsito) y astrometría (centroides
  subpíxel, informes listos para el MPC en ADES o 80 columnas, el chequeo
  contra otras estaciones con Find_Orb, el handoff a ExoClock).
- **Contarlo**: borradores bilingües (ES/EN) de post y tuit con los gráficos
  de la noche.
- **Proyectos, visitas y campañas**: cada objetivo se convierte en un proyecto
  con su propia carpeta y un flujo Ficha, Captura, Análisis, Publicación; cada
  noche es una visita; las campañas y las vigilias de variables llevan su
  propia cadencia.
- **Una interfaz de línea de comandos** para planificar y publicar, bilingüe.
- **El asistente** (opcional, apagado por defecto): responde desde la propia
  guía y los ADRs de la app, offline, a través de un modelo que configures.
- **Una ruta GPU por OpenCL** (encendida por defecto, cae al procesador) para
  el warp y el combine.

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
