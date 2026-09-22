# Editor FITS unificado (UFE)

*[English version](UFE.md)*

El **Editor FITS unificado** es el punto único de NightScribe para ver y
trabajar imágenes FITS (ADR-044). Se abre desde el menú **Herramientas →
Editor FITS…** y convive con los diálogos clásicos (blink, carta de
comparación, FITS anotados), que siguen disponibles donde siempre.

## La ventana

```
| Cargar · Invertir · Exportar PNG · Fit 50 100 200 400 · %           |
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
  coordenadas RA/Dec si la placa trae WCS.
* **Pestañas**: una por funcionalidad. **Blink**, **Comparar** y
  **Anotar** están disponibles (abajo). Solo la pestaña visible responde
  a los clics sobre la imagen.

## Blink

La pestaña **Blink** parpadea tu placa contra la referencia PanSTARRS
DR1 g (supernovas y transitorios; la placa es la que cargaste con
«Cargar FITS…»):

* Escribe el nombre de la SN (o marca «Coordenadas manuales» y da
  RA/Dec) y pulsa **Preparar pareja**: resuelve el objetivo, descarga la
  referencia con la geometría de tu placa y arranca el blink en vivo.
* El **estiramiento es el común** (la tira de histograma manda también
  sobre el blink); **Balance** multiplica la referencia para igualar el
  fondo de cielo (botón Auto); **Ajuste ref** desplaza la referencia a
  sub-píxel si el registro no es perfecto.
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
  bandas) y **Exportar carta PNG…** guarda exactamente lo que ves:
  placa, anillos, rótulos y la flecha de norte / barra de escala.

Para entender cómo se mide después la fotometría con estas secuencias:
[docs/PHOTOMETRY.es.md](PHOTOMETRY.es.md).
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
