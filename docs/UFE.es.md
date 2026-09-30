# Editor FITS unificado (UFE)

*[English version](UFE.md)*

El **Editor FITS unificado** es el punto único de NightScribe para ver y
trabajar imágenes FITS (ADR-044). En la interfaz se llama **«NightScribe
Image Workbench»** (sin traducir: es ya el espacio de trabajo de
procesamiento, no solo un editor) y se abre desde el menú
**Herramientas → NightScribe Image Workbench…**; «UFE» queda como
codename interno en código y documentación.

**Convivencia y ajuste por defecto**: los diálogos clásicos (blink,
carta de comparación, FITS anotado) siguen existiendo para comparar y
revisar, pero por defecto los flujos abren el UFE: en **Ajustes →
Desarrollo** puedes volver a los clásicos como predeterminados
(`ufe_default`). Desde un proyecto, el UFE abre con la placa cargada, la
pestaña correcta en escena y **todo lo que el proyecto sabe del objeto
ya puesto**: nombre, coordenadas y magnitud en la línea bajo la barra y
en el título, y cada pestaña con sus campos precargados (Blink: nombre y
coordenadas; Fotometría: objetivo, magnitud y B−V si la ficha lo trae;
Anotar: etiqueta, marcador en la posición del objeto y visitas extra).
Lo que escribe (copias anotadas, GIF/PNG del blink, CSV/PNG de la
secuencia) se registra en el proyecto igual que con los clásicos. Sin
placa propia, la pestaña Fotometría (modo Secuencia) descarga el campo
del survey (DSS2/PS1) como FITS con WCS y trabaja sobre él directamente.

## La ventana

```
| [Abrir][Exportar][Resolver] | [Fit][100 %][Zoom ▾] 100 % | [Vista ▾] | Imagen|Curva |
|───────────────────┬────────────────────────────────────────┬──────────────|
|  visita / serie   |                                        |  pestaña     |
|  (plegable)       |   IMAGEN  (o la curva)                 |  ────────    |
|                   |   · el objeto, sobre la placa          |  primario    |
|                   |                                        |  [Ajustes▸]  |
|───────────────────┴────────────────────────────────────────┴──────────────|
| Histograma ▸  (plegado: 24 px; abierto: ~110, dos filas de controles)    |
|──────────────────────────────────────────────────────────────────────────|
| ⓘ estado: una línea, altura fija, nunca crece                            |
```

El marco de la ventana ocupa lo que NECESITA y el área de trabajo se queda
con el resto: la placa es para lo que existe la ventana. La barra superior
es estable (antes medía 25 px en una ventana baja y 69 en una alta: el
`layoutStretch` del Designer no lo aplica el cargador), y la tira del
histograma es compacta y se pliega recordando cómo la dejaste. El nombre,
la posición y la magnitud del objeto se pintan SOBRE la placa (y viajan al
PNG exportado), no en una fila propia.

El bloque de serie del panel izquierdo conserva lo que se toca al medir
(el navegador de tomas, la agrupación de tomas, **Medir la secuencia**, el
modo en vivo y el progreso) y deja el resto detrás de dos puertas:
**Gráfico y calidad…** abre la ventana propia del gráfico (no modal: escala,
barras de error, agrupación, media, anómalos y exclusiones) y **Serie ▾**
guarda las acciones ocasionales (deshacer, ExoClock, las figuras de la
noche, guardar el gráfico, período y fase, la guía). Antes ese mismo panel
mostraba una treintena de controles apilados.

* **Imagen**: ocupa la mayor parte de la ventana. La rueda hace zoom
  anclado al cursor; arrastrar desplaza; doble clic vuelve al ajuste.
  Al pasar el cursor, un globo muestra el píxel, su valor DN y las
  coordenadas RA/Dec si la placa trae WCS. En las pestañas que marcan
  (Fotometría, Anotar) el cursor se vuelve una cruz con retícula de
  hueco central que **se pega al centroide de la fuente** bajo el ratón:
  el clic nace centrado. La detección es local y robusta (ve fuentes
  débiles incluso sobre el brillo de una galaxia) y el alcance del
  «pegado» está acotado a 9 px de placa: la retícula nunca salta a una
  estrella brillante lejana.
* **Pestañas**: una por funcionalidad. **Blink**, **Fotometría**
  y **Anotar** están disponibles (abajo). Solo la pestaña
  visible responde a los clics sobre la imagen.

## Blink

La pestaña **Blink** parpadea tu placa contra la referencia PanSTARRS
DR1 g (supernovas y transitorios; la placa es la que cargaste con
«Cargar FITS…»):

* Escribe el nombre de la SN (o marca «Coordenadas manuales» y da
  RA/Dec) y pulsa **Preparar pareja**: resuelve el objetivo, descarga la
  referencia con la geometría de tu placa y arranca el blink en vivo.
* El **estiramiento es el común** (la tira de histograma manda también
  sobre el blink); **Balance** multiplica la referencia para igualar el
  fondo de cielo (botón Auto); la **Alineación fina** es la cruz de
  flechas que desplaza la referencia a medio píxel si el registro no es
  perfecto, igual que en el diálogo legacy de blink.
* **Blink** (alterna con el intervalo elegido) o **Fundido** (mezcla
  estática con el deslizador); el marcador ámbar marca la posición de la
  SN mapeada por el WCS de tu placa.
* **GIF… / MP4… / PNG…** exportan el par (lado a lado el PNG), con el
  zoom de recorte sobre la SN que elijas.

## Fotometría

La pestaña **Fotometría** hace las dos cosas en el mismo sitio, en dos
mitades apiladas (hay una divisoria que se puede arrastrar): la radio
**Secuencia** de arriba elige qué mitad recibe los clics, y la otra
queda a la vista con sus anillos y rótulos, para poder alternar entre
construir y medir sin perder de vista lo hecho (ADR-044, revisión de
distribución, 2026-09-24).

### Secuencia (mitad superior)

Construye la secuencia fotométrica sobre tu placa (necesita WCS; si
falta, la resuelve sola con el solver configurado, ASTAP o nova):

Con la visita abierta, el panel izquierdo lleva además el **navegador de
tomas** (anterior/siguiente, `toma i/N`, «primera toma»: la toma abierta es la
referencia), **Resolver la visita…** y, en proyectos de tránsito, los botones de
**reducción EXOTIC**. La secuencia ya guardada del proyecto se carga sola al
abrir la visita.

**Resolver la visita…** resuelve de una vez todas las tomas de la visita. Una
visita es un solo campo y el proyecto sabe dónde está, así que cada toma tarda
un momento en vez de un minuto de búsqueda a ciegas: las tomas que ya traen WCS
se saltan, y cada solución se escribe en su propio FITS (necesita «Guardar la
WCS resuelta en el FITS» en Ajustes; con eso apagado el botón lo explica en vez
de dejar soluciones que morirían al cerrar). Si el proyecto no tiene
coordenadas, la primera toma se resuelve a ciegas y las demás siguen su campo.
Una toma que falla no para el lote: se cuenta y se nombra en la línea de estado.
Una placa abierta desde un proyecto se resuelve también con su campo, así que el
botón Resolver de la barra superior responde en un momento.

**Construir la secuencia…** hace toda la cadena de un clic: si la placa no
tiene WCS la resuelve primero (el campo del proyecto apunta al resolutor, así
que es un momento), después consulta el catálogo (el campo) y propone. El
**Proponer secuencia** de la ventana Manual rellena igual el paso que falte,
así que el orden de los botones no hay que recordarlo. Una reconstrucción que
no puede entregar (falla la consulta, no cae nada en esta placa, ninguna
comparsa válida) mantiene la secuencia que ya tenías y dice por qué.

* **Objetivo** y **magnitud del objetivo** precargan lo que el proyecto
  sabe; la magnitud aproximada sirve de guía a la propuesta.
* **Generar campo** consulta el catálogo (Gaia EDR3 o APASS DR9) y las
  variables VSX alrededor del centro de la placa: las estrellas más
  brillantes aparecen rotuladas (casilla «mostrar magnitudes de
  catálogo») y las variables conocidas con anillo rojo (nunca sirven de
  comparación). **DSS2…**, en la misma fila, descarga el campo del
  survey (PS1-g, fallback DSS2-red) como FITS con WCS cuando no tienes
  placa: se trabaja sobre él directamente.
* **Clic** sobre una estrella la añade o quita de la secuencia, como
  Comparación (cian) o Check (rosa, radio «al clicar, añadir como»).
* **Proponer secuencia** elige automáticamente estrellas aisladas y no
  variables de brillo parecido al objetivo.
* **Secuencia (N)…** abre la *tabla* en una ventana pequeña y no modal
  (N son las estrellas que hay ahora mismo, y se actualiza sola):
  renombra, cambia el tipo, **edita la banda y la magnitud a mano** (un
  valor de catálogo dudoso se corrige ahí: la medida usa el valor
  manual) y quita filas, y se puede dejar abierta
  mientras sigues eligiendo estrellas en la placa. La sonda al pasar el
  cursor cuenta catálogo, magnitud y color de cada estrella, también con
  la ventana abierta.
* **Quitar todo** vacía la secuencia y **Exportar CSV…** la escribe
  (columnas fijas + todas las bandas); la **carta PNG** sale por el
  botón común «Exportar PNG…» de la barra superior: placa, anillos,
  rótulos y la flecha de norte / barra de escala, exactamente lo que ves.

### Medir (mitad inferior)

Convierte un clic en una magnitud calibrada de catálogo (fotometría de
apertura diferencial de una placa):

* Necesita la placa con WCS (si falta, la resuelve sola) y una
  secuencia en la mitad superior (si no la hay, un botón «Ir a la
  secuencia» te lleva).
* **Clic** sobre la estrella o la SN: centroide sub-píxel, apertura y
  anillo de cielo visibles en la imagen, y el panel cuenta el resultado
  completo: magnitud instrumental, punto cero con su error y cuántas
  comps se usaron (y por qué se rechazó alguna), y la **magnitud
  calibrada ± error**. La secuencia queda a la vista (anillos y
  etiquetas): mides CON ella a la vista; y cambiar cualquier opción
  (banda, radios, cielo, sigma-clip, término de color, B−V,
  sustracción) recalcula la medida al instante.
* El flujo diario es **Banda** (por defecto V) y los tres **radios de
  apertura** (apertura, anillo interior y exterior): tocar un radio
  re-mide el punto al instante, y tu ajuste manual manda sobre el
  auto-seeing hasta que cargues otra placa (o rearms la casilla).
* **Avanzado…** abre la receta completa en otra ventana pequeña y no
  modal (se puede dejar abierta mientras se mide): modelo de **cielo**
  (mediana plana o plano inclinado para núcleos galácticos),
  **sigma-clip** del cielo (dos pasadas de 2,5 sigma), **apertura que
  sigue al seeing** (FWHM de las comps en tu placa, apertura a 1,35
  veces), **término de color** ajustado con el B−V de las comps y el
  del objetivo, **sustracción de la galaxia huésped** con la referencia
  PS1 alineada (para SNe en núcleos, una descarga por campo), y el botón
  **Sugerir** que propone los radios con la curva de crecimiento del
  objetivo y su entorno, con las razones en lenguaje llano.
* Controles de calidad (fase H, en segundo plano): techo de
  **saturación real** (SATURATE o `ccd_saturate`), **error interno vs.
  total** (fotones + dispersión + centelleo + color + flats) y la
  **estrella check como semáforo** de la medida. Si la cabecera no trae
  ganancia, el panel avisa de que el error es solo la dispersión de las
  comps.
* **CSV…** exporta la medida en una fila, **AAVSO EFF…** en el formato
  de la AAVSO (secuencia en CNAME/CMAG/KNAME/KMAG) y, cuando el editor
  se abrió desde un proyecto, **Guardar en el proyecto** lo registra en
  su curva de luz (fuente «measure», visita asociada). Si la secuencia
  no trae la magnitud del objetivo, se busca en el proyecto (planner,
  VSX, o la última secuencia guardada); y al exportar la secuencia queda
  escrita en el proyecto para la próxima vez. La placa en disco nunca se
  modifica.

Ambas mitades comparten: las **anotaciones al vuelo** (si la placa ya
trae tarjetas ANNOTATE, escritas por NightScribe o AstroImageJ, se
dibujan al cargar con su tamaño en píxeles de placa y rótulos legibles
en cualquier zoom), la **flecha de norte y barra de escala** (botones
«N» y «Escala» de la barra superior, con WCS) y **Resolver
astrometría…** (la resuelve a ciegas con el solver configurado, ASTAP o
Astrometry.net; con un diálogo de progreso y Cancel que corta el solver;
la solución se aplica en memoria y se guarda en el propio FITS de forma
atómica, así la placa queda resuelta para cualquier programa).

Para entender cómo se mide después la fotometría con estas secuencias:
[docs/PHOTOMETRY.es.md](PHOTOMETRY.es.md).

## La banda de la placa y el estilo de marcador (ADR-046)

La placa cuenta lo que sabe en la **banda de la parte alta de la imagen**,
en pantalla y quemada en el PNG exportado, en dos líneas:

* **Línea 1, quién es**: el objeto, la AR/Dec sexagesimal del objetivo y
  su brillo.
* **Línea 2, el contexto**: fecha UT, exposición, filtro, el equipo que
  tomó el frame (de su propia cabecera), la estación MPC, la escala en
  ″/px y el FOV de lo que se ve (las dos últimas solo con la placa
  resuelta).

**El color de cada dato dice cuánto fiarse**, y ahí está la gracia de la
banda:

* la **posición** en tinta cuando la coloca la propia solución de esta
  placa, y apagada con un `cat` cuando solo es la del catálogo (placa sin
  resolver);
* la **magnitud** en verde cuando se midió aquí y sus números aguantan
  (error, número de comparsas, estrella de chequeo, núcleo recortado), en
  rojo cuando dicen «mira esto antes de reportarlo», y apagada con un
  `cat` cuando solo es el valor del proyecto o del catálogo, que no es una
  medida de esta placa;
* lo demás (fecha, exposición, filtro, equipo, estación, escala, FOV) en
  el color discreto: es contexto, no un juicio.

La banda nunca corta una palabra: si la ventana es estrecha suelta campos
enteros (el FOV primero, la fecha la última) y, en el extremo, se va la
línea de contexto y queda solo el nombre de la placa. El botón **«Datos»**
de la barra superior la apaga (Ajustes → Sitio y equipo → «Banda de la
placa» fija el valor por defecto), y la rosa de los vientos y la barra de
escala conservan sus esquinas clásicas. El **GIF/MP4 del blink** y la
**carta de secuencia** mantienen sus propias cajas de metadatos, con su
conmutador («Otras cartas» en el mismo grupo de Ajustes).

En el mismo grupo de Ajustes, **Marcador del objeto** elige la estética
de la marca del objeto: anillo con ticks (clásica) o cruz a todo el
campo con caja (se aplica en Fotometría, Anotar, Blink y la carta de
secuencia).

## Anotar

La pestaña **Anotar** guarda copias FITS anotadas compatibles con
AstroImageJ (el archivo original nunca se modifica):

* **Clic** sobre la imagen coloca el marcador; **dx/dy + Ajustar** lo
  mueven a décimas de píxel; tamaño y color a elegir.
* **Etiqueta** y **notas** viajan en las tarjetas ANNOTATE y NS_NOTES;
  RA/Dec, escala y PA de norte se escriben desde el WCS de la placa
  (NS_RA, NS_DEC, NS_SCALE, NS_NORTH).
* **Anotar también (visitas)**: una lista de placas extra recibe la
  misma anotación; el marcador aterriza en cada una a través de su
  propio WCS.
* **Guardar copia anotada…** escribe la copia elegida y, junto a cada
  visita, su `<nombre>_annotated.fits`.
* **Histograma**: 256 bins en escala logarítmica sobre la imagen de
  pantalla. Las zonas sombreadas son lo que el estiramiento descarta.

## Estiramiento fino

Pensado para objetos sutiles (supernovas pegadas a núcleos galácticos):

* **Tiradores** azul (negro) y naranja (blanco) sobre el histograma, al
  estilo de AstroImageJ; un clic simple mueve el tirador más cercano.
* **Negro / Blanco** en DN absolutos con paso fino adaptado al rango de
  la placa; nunca se cruzan (el blanco queda siempre por encima).
* **Gamma**: menor que 1 levanta los tonos medios; mayor los hunde.
* **Auto**: vuelve a los percentiles 1 / 99.5.
* **Invertir**: cambia negro por blanco; los objetos débiles resaltan
  sobre el cielo.
* **Mantener estiramiento al cargar**: la siguiente placa conserva tus
  valores de negro, blanco, gamma e invertir en vez de los percentiles
  automáticos. Es lo que quieres al repasar una serie de tomas de la
  misma cámara.

## Zoom

Los presets **Fit / 50 / 100 / 200 / 400** fijan la escala absoluta: 100
es un píxel de placa por píxel de pantalla, y a 200/400 se inspeccionan
los píxeles reales sin interpolar. El zoom sobrevive al redimensionar la
ventana y se puede desplazar la vista un 25 % más allá del borde de la
placa.

## Teclado

| Tecla | Acción |
|---|---|
| `F` | Ajustar la placa a la ventana |
| `1` | Zoom 100 % (1:1) |
| `+` / `-` | Zoom en pasos de rueda |
| Flechas | Desplazar un cuarto de ventana |
| `Ctrl+O` | Cargar FITS… |
| `Ctrl+E` | Exportar PNG… |

## Exportar

**Exportar PNG…** guarda exactamente lo que se ve en pantalla (con la
marca de agua de NightScribe), listo para adjuntar. Las exportaciones de
datos (FITS anotado, cartas) usan siempre el archivo original, nunca la
imagen de pantalla.
