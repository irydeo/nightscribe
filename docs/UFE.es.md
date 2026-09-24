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
coordenadas; Comparar: objetivo y mag; Anotar: etiqueta, marcador en la
posición del objeto y visitas extra; Medir: B−V si la ficha lo trae).
Lo que escribe (copias anotadas, GIF/PNG del blink, CSV/PNG de la
secuencia) se registra en el proyecto igual que con los clásicos. Sin
placa propia, la pestaña Comparar descarga el campo del survey
(DSS2/PS1) como FITS con WCS y trabaja sobre él directamente.

## La ventana

```
| Cargar · Exportar PNG · Fit 50 100 200 400 · %                      |
|────────────────────────────────────────────|──────────────────────|
|                                            | [Blink][Comparar]    |
|              IMAGEN                        | [Anotar]             |
|                                            | (una pestaña por     |
|                                            |  funcionalidad)      |
|────────────────────────────────────────────|──────────────────────|
| Histograma con tiradores + Negro/Blanco/Gamma + Auto + Invertir     |
```

* **Imagen**: ocupa la mayor parte de la ventana. La rueda hace zoom
  anclado al cursor; arrastrar desplaza; doble clic vuelve al ajuste.
  Al pasar el cursor, un globo muestra el píxel, su valor DN y las
  coordenadas RA/Dec si la placa trae WCS. En las pestañas que marcan
  (Medir, Anotar, Comparar) el cursor se vuelve una cruz con retícula de
  hueco central que **se pega al centroide de la fuente** bajo el ratón:
  el clic nace centrado. La detección es local y robusta (ve fuentes
  débiles incluso sobre el brillo de una galaxia) y el alcance del
  «pegado» está acotado a 9 px de placa: la retícula nunca salta a una
  estrella brillante lejana.
* **Pestañas**: una por funcionalidad. **Blink**, **Comparar**,
  **Medir** y **Anotar** están disponibles (abajo). Solo la pestaña
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

## Comparar

La pestaña **Comparar** construye la secuencia fotométrica sobre tu
placa (necesita WCS; si falta, «Resolver astrometría…» lo consigue):

* **Generar campo** consulta el catálogo (Gaia EDR3 o APASS DR9) y las
  variables VSX alrededor del centro de la placa: las estrellas más
  brillantes aparecen rotuladas y las variables conocidas con anillo
  rojo (nunca sirven de comparación).
* **Clic** sobre una estrella la añade o quita de la secuencia, como
  Comparación (cian) o Check (rosa); **Proponer secuencia** elige
  automáticamente estrellas aisladas y no variables de brillo parecido
  al objetivo (dile su magnitud aproximada).
* La **tabla** renombra, cambia el tipo y quita filas; la sonda al pasar
  el cursor cuenta catálogo, magnitud y color de cada estrella.
* **Exportar CSV…** escribe la secuencia (columnas fijas + todas las
  bandas). La **carta PNG** sale por el botón común "Exportar PNG…" de
  la barra superior: placa, anillos, rótulos y la flecha de norte /
  barra de escala, exactamente lo que ves.

Para entender cómo se mide después la fotometría con estas secuencias:
[docs/PHOTOMETRY.es.md](PHOTOMETRY.es.md).

## Medir

La pestaña **Medir** convierte un clic en una magnitud calibrada de
catálogo (fotometría de apertura diferencial de una placa):

* Necesita la placa con WCS (si falta, «Resolver astrometría…») y una
  secuencia en la pestaña Comparar (si no la hay, la pestaña te guía y
  tiene un botón que te lleva).
* **Clic** sobre la estrella o la SN: centroide sub-píxel, apertura y
  anillo de cielo visibles en la imagen, y el panel cuenta el resultado
  completo: magnitud instrumental, punto cero con su error y cuántas
  comps se usaron (y por qué se rechazó alguna), y la **magnitud
  calibrada ± error**. Al entrar desde Comparar, la secuencia queda
  visible (anillos y etiquetas): mides CON ella a la vista; y cambiar
  cualquier opción (cielo, sigma-clip, término de color, B−V, radios)
  recalcula la medida al instante.
* La banda por defecto es V; las aperturas y el sigma-clip del cielo son
  ajustables. Si la cabecera no trae ganancia, el panel avisa de que el
  error es solo la dispersión de las comps.
* Las aperturas se miden en vivo: tocar un radio re-mide el punto al
  instante, y tu ajuste manual manda sobre el auto-seeing hasta que
  cargues otra placa (o rearms la casilla). Si la secuencia no trae la
  magnitud del objetivo, se busca en el proyecto (planner, VSX, o la
  última secuencia guardada); y al exportar la secuencia queda escrita
  en el proyecto para la próxima vez.
* Controles de calidad (fase H): cielo por mediana o por **plano** en
  núcleos galácticos, **apertura que sigue al seeing** (FWHM medido en
  la placa), **término de color** ajustado con el B−V de las comps y el
  del objetivo, techo de **saturación real** (SATURATE o `ccd_saturate`),
  **error interno vs. total** (fotones + dispersión + centelleo + color
  + flats), la **estrella check como semáforo** de la medida, y la
  **sustracción de la galaxia huésped** con la referencia PS1 del blink
  para SNe en núcleos.
* **CSV…** exporta la medida en una fila y **AAVSO EFF…** en el formato
  de la AAVSO, con la secuencia en CNAME/CMAG/KNAME/KMAG. La placa en
  disco nunca se modifica.
* **Anotaciones al vuelo**: si la placa ya trae tarjetas ANNOTATE
  (escritas por NightScribe o por AstroImageJ), se dibujan al cargar:
  círculos con su tamaño en píxeles de placa y rótulos legibles a
  cualquier zoom.
* **Flecha de norte y barra de escala** (botones «N» y «Escala», con
  WCS): viven en la esquina superior derecha e inferior izquierda, y
  también salen en el PNG exportado.
* **Resolver astrometría…**: si la placa no tiene WCS (o quieres
  repetirlo), la resuelve a ciegas con Astrometry.net (requiere tu clave
  de API en Ajustes). La solución se aplica en memoria a la sesión: el
  archivo en disco nunca se modifica, y la sonda, la flecha de norte, la
  barra de escala y Anotar la usan al instante.

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
