# 13. Entender un objeto

Planificar te dice *qué* observar. Este capítulo es la otra mitad: *qué
estás mirando*. NightScribe tiene una puerta para cada objeto que conoce, y
la ficha que hay detrás es la misma la abras desde donde la abras.

## Tres formas de abrirla

- el cuadro de la barra superior: **Explorar un objeto…** (escribe un nombre
  y pulsa Intro);
- **Herramientas → Explorar objeto…**;
- doble clic en cualquier fila de la lista **Esta noche**, o el botón de la
  fila.

El nombre se busca en VSX, SIMBAD, JPL SBDB, Horizons, CAD, TNS y el NASA
Exoplanet Archive, así que sirve para un asteroide, un cometa, una supernova,
una variable o una estrella con exoplaneta. Si el objeto no está en ningún
catálogo, la vista **Esta noche** te deja crearlo a mano.

## La ficha

La ficha es una tarjeta de presentación, no un volcado de datos:

- un **gancho** y unos cuantos puntos divulgativos, en español e inglés: la
  frase que dirías en voz alta para explicar por qué este objeto interesa;
- una **tabla de parámetros donde cada fila está explicada**: la familia
  orbital, el MOID (la distancia mínima a la que la órbita llega a la de la
  Tierra, en distancias lunares), el tamaño estimado desde la magnitud
  absoluta, el próximo acercamiento, la fecha de descubrimiento. Es
  multilínea y nada se corta;
- los **gráficos**: la órbita (animada por fecha, con lecturas al pasar el
  ratón), el cielo de la noche con *tu* silueta de horizonte y la ventana
  segura sombreada, el campo del survey y la curva de luz cuando la hay. En
  la app son gráficos vectoriales vivos (zoom, arrastre, hover); los mismos
  motores generan los PNG;
- los **chips de captura**: magnitud actual, ritmo aparente, la exposición
  máxima sin estela con tu cámara, la ventana y las horas por encima del
  horizonte, más coordenadas copiables en decimal y sexagesimal con su época.

> **¿Por qué cada fila viene explicada?** Porque «MOID 0,03 UA» no le dice
> nada a casi nadie, y «puede acercarse a doce distancias lunares» lo dice
> todo. Las cifras son las mismas; solo cambia el lector. Las explicaciones
> viven en un único sitio (`core/explain.py`), así que un tipo, una clase
> espectral o un método de descubrimiento se describen igual aparezcan donde
> aparezcan.

## De la ficha al proyecto

La ficha es un punto de partida, no un callejón: **Crear proyecto** convierte
el objeto en un proyecto y te deja en su ficha, con las coordenadas, la
ventana y la magnitud ya rellenas (capítulo 03). A partir de ahí el flujo es
el de siempre: captura, análisis, publicación.

Siguiente: [14. Cuando algo va mal](14-troubleshooting.es.md).
