# NightScribe — Diseño de producto

*[English version](DESIGN.md)*

## Visión

**Planifica tu noche, entiende cada objeto, cuenta tu ciencia.**

NightScribe es una aplicación de escritorio para observatorios astronómicos amateur que
cierra el círculo: te dice *qué merece la pena observar esta noche*, explica *por qué
importa cada objeto* en lenguaje claro, y convierte tu observación en *contenido bilingüe
listo para publicar* en redes sociales.

El diferencial: las herramientas actuales muestran tablas crudas o gráficos anticuados.
NightScribe **traduce, explica y dibuja bonito** — riguroso pero humano.

## Usuarios objetivo

- Observatorios amateur con código MPC que reportan astrometría (NEOs, cometas, PCCP).
- Astrónomos amateur que siguen supernovas, cometas y tránsitos de exoplanetas.
- Cualquiera que quiera contenido astronómico atractivo y con datos sin dedicar horas.

La configuración por defecto usa la estación MPC **Z41** (Observatorio Irydeo) como
ejemplo; todo es configurable para que cualquier observatorio lo adopte.

## Las vistas

*(UX v3, ADR-019: la app se reorganiza alrededor de los **Proyectos**; pestañas:
Esta noche · Proyectos · Sistema solar · Historial. Explora/Post/Blink pasan a ser
paneles contextuales abiertos desde un proyecto, con acceso ad-hoc en Herramientas.
Flujos guiados por tipo en WORKFLOWS.es.md.)*

### 1. Esta noche — la vista principal

No es una tabla: es una **recomendación** (ver ADR-017 para el rediseño v2, ADR-019
para v3).

 - **Banda «Ahora mismo»**: objetivos sobre el horizonte en este instante, con
   altitud y azimut en vivo, ordenados por score. Además de la ventana, cada tarjeta
   muestra el **rango de observación seguro** (ADR-020): chip verde
   «⊕ HH:MM–HH:MM · ≤ HH:MM» (ventana del plan + último inicio posible) u
   **chip rojo «⚠ no cabe»** cuando la sesión planificada no encaja antes de que el
   objeto cruse el horizonte — nunca se fuerza el equipo.
- **Top 3 unificado** con medallas y la frase generada «por qué esta noche»
  (en el idioma de la interfaz).
 - Listado completo: ordenable pulsando cabeceras, **columnas dinámicas según el
   filtro de tipo** (NEOs muestran NObs/MOID/prioridad NEOfixer; supernovas
   muestran tipo/galaxia/fecha de descubrimiento...), más panel de detalle con
   acciones por objetivo (Explorar / Post / Observado).
  - Punto de entrada a **Explorar** (UX v3, fase E): la fila, el doble clic en la
    tabla y el botón de la tarjeta (🔭 Explorar / ▶ Continuar según si hay proyecto
    `active`) abren siempre el diálogo *Explorar* pre-rellenado. Dentro, la pestaña
    *Detalles* ofrece un **CTA único** a ancho completo: «Continuar proyecto»
    (verde) si hay un activo para el objeto, «Crear proyecto» (naranja) si no;
    se retiran la pareja de botones y el antiguo botón de post. El proyecto ya no se
    crea desde la tarjeta, sino desde el diálogo.

### Estructura de la interfaz

Barra de menú (Archivo / Vista / Herramientas / Ayuda); **Configuración vive en un
diálogo modal** (Herramientas → Configuración…); cambio de idioma en Vista.
Pestañas (UX v3, ADR-019): Esta noche · Proyectos · Sistema solar · Historial. La
interfaz muestra un solo idioma cada vez; solo los posts generados son bilingües.

### 2. Proyectos — el flujo guiado (UX v3, ADR-019)

Cada objetivo puede convertirse en un **proyecto**: un flujo guiado y persistente por
 tipo de objeto (Plan → Captura → Procesado → Publicar) que lleva todo el
contexto — sin volver a preguntar nombres, coordenadas o imágenes. Las secuencias de
captura y las efemérides se exportan como ficheros para software externo (NINA,
CCDciel, TheSkyX, Cartes du Ciel — ADR-021); la astrometría medida fuera se pega de
vuelta, se valida y se empaqueta para el reporte al MPC (ADR-022). Restricciones que
respeta el planificador: horizonte local real, Luna, viabilidad de la sesión y escala
de placa de la cámara (ADR-020).

### 3. Explora

Escribe cualquier identificador (`2021EQ3`, `29P`, `SN2023ixf`, `HD 209458 b`, `sol`) y
obtén la **ficha explicada del objeto**:

- Familia orbital con contexto (Apollo, Aten, troyano, cometa de la familia de Júpiter,
  Oort...).
- Cada parámetro orbital/físico traducido, en dos niveles (básico / profundo).
- Evaluación de riesgo honesta (MOID, PHA, escala de Turín) sin alarmismo.
- Tamaño estimado desde H y clase espectral, con comparaciones cotidianas.
- Cometas: brillo esperado desde M1/K1, ventana de perihelio, historia de su origen.
- Supernovas: galaxia anfitriona, distancia, «la luz salió hace X millones de años»,
  imagen de referencia del campo con crosshair.
- Exoplanetas: tipo, «su año dura X días», temperatura de equilibrio, estrella anfitriona.

### 4. Post

- Borradores en **español e inglés** más un tuit de 280 caracteres; siempre ambos idiomas
  independientemente del idioma de la interfaz (la audiencia es bilingüe).
- Gráficos PNG listos para adjuntar (órbita, curva de altitud nocturna, ventana de
  tránsito, antes/después de SN), renderizados con el mismo código que los dibuja en la GUI.
- Botones de copiar; el CLI escribe `post_ES.md`, `post_EN.md`, `tuit.txt` y los PNG.
- Imagen propia opcional de la observación → lado a lado o GIF blink animado
  (survey de referencia vs. imagen del observatorio).

### 5. Sistema solar ahora

- **Sol**: última imagen SDO (dominio público) en varias longitudes de onda, mapa propio
  de regiones activas a partir de coordenadas NOAA, número de manchas y tendencia
  (NOAA + SILSO), fulguraciones GOES, viento solar (DSCOVR), Kp → «¿auroras esta noche?»
- **Luna**: fase, iluminación, distancia actual en km (la vara de medir de nuestros posts).
- **Planetas esta noche**: cuáles son visibles desde tu sitio tras el ocaso, con magnitudes.
- Recursos externos como enlaces (mapas Raben, SolarMonitor, SIDC, universemonitor) —
  nunca incrustados, por copyright.

### 6. Configuración

- Asistente de primer arranque: introduce tu **código de observatorio MPC** → coordenadas
  resueltas automáticamente (ObsCodes del MPC) — o localización manual completa
  (lat/lon/altitud).
- Nombre del observatorio (firma los posts), apertura del telescopio (filtra la
  factibilidad de tránsitos), idioma de la interfaz (Sistema / Español / English),
  clave API de NEOfixer (opcional), credenciales TNS (opcional, solo para ver imágenes
  de descubrimiento dentro de la app).

## Principios UX (seña de identidad)

- **Flujo guiado, no paneles técnicos**: abres la app y la noche ya está sugerida.
- Cero campos obligatorios; valores por defecto sensatos (mag < 18, altitud > 30°).
- Tooltips en todas partes; errores en lenguaje humano; progreso en la barra de estado.
- Tema nativo claro/oscuro, compatible con HiDPI (Qt6).
- Todo a dos clics: sugerir → observar → publicar.

## Tipos de objeto y sus historias

| Tipo | Fuentes | La historia que contamos |
|---|---|---|
| NEO | NEOfixer, SBDB, Horizons, CAD, ESA NEOCC | distancia en distancias lunares, tamaño vs. objetos cotidianos, próxima aproximación, por qué tu astrometría importa |
| Cometa | COBS, SBDB (M1/K1), Horizons | origen (Oort / familia de Júpiter), brillo esperado, outbursts, ventana de perihelio, cola antisolar |
| Candidato PCCP | Página PCCP del MPC | «score 85/100 en la página de posibles cometas del MPC: tu imagen podría confirmar el descubrimiento» |
| Supernova / transitorio | Rochester, SIMBAD, cutouts | galaxia anfitriona + distancia, «la luz salió hace X millones de años», blink antes/después |
| Tránsito de exoplaneta | ExoClock, NASA Exoplanet Archive | «esta noche un planeta eclipsa su estrella un 1,5% durante 3 h; tu curva de luz ayuda a la misión Ariel de la ESA» |
| Sol | SDO, NOAA/GOES/DSCOVR, SILSO | estado del ciclo solar, regiones activas, fulguraciones, posibilidad de auroras |

## Fuera de alcance

- Control de telescopios (eso lo hace el proyecto hermano `saas`). **Exportar
  secuencias de captura y efemérides como ficheros** para software externo (NINA,
  CCDciel, planetarios) **sí está dentro** del alcance — es generación de ficheros, no
  control (ADR-021).
- Publicación automática en las APIs de Meta/X (copiar y pegar, por decisión de
  diseño; el reporte al MPC también se empaqueta para que lo envíe el usuario,
  ADR-022).
- Visualización 3D de órbitas (2D cenital por diseño; quizás más adelante).
