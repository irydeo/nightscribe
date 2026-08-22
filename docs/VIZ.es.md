# NightScribe — Guía de estilo visual (viz/)

*[English version](VIZ.md)*

Un solo render, dos salidas: todo lo que hay en `nightscribe/viz/` dibuja sobre un
lienzo matplotlib embebido en la GUI **y** exporta PNG listos para adjuntar a los
posts. El estilo se define una sola vez en `viz/style.py`.

## Estilo

- Fondo oscuro espacial (familia #0b0d17), paleta de acento consistente, tipografía
  sans-serif clara, rejilla sutil, marca de agua opcional «NightScribe · <nombre del
  observatorio>».
- Formatos de exportación: 1080×1080 px (cuadrado Instagram), 1200×630 px (tarjeta
  Facebook/X). DPI fijo para que el texto sea legible en móviles.
- Los tests renderizan con el backend `Agg` (sin pantalla).

## Vistas

### `orbit_view.py` — carta cenital de la eclíptica

- Órbitas de Mercurio→Marte (→Júpiter para troyanos / cometas de largo período),
  planetas en su posición **actual** (Schlyter), órbita del objeto resaltada, su
  posición actual y una traza de ±N días.
- Recuadro de aproximación cercana: zoom centrado en la Tierra con la **órbita de la
  Luna** dibujada y el paso etiquetado en distancias lunares — «para relativizar».
- Cometas: marcador de cola antisolar en el recuadro de zoom.

### `families_view.py` — «dónde vive»

Bandas radiales de las familias del sistema solar (NEOs, cinturón principal, troyanos,
centauros, TNOs) con el marcador **«tú estás aquí»** del objeto.

### `sky_view.py` — curva de altitud nocturna

Altitud frente a tiempo para el objetivo a lo largo de la noche, fases de crepúsculo
sombreadas, altitud de la Luna superpuesta. Los tránsitos de exoplanetas dibujan las
ventanas de ingress/egress (`transit_view.py` añade una curva de luz teórica simple
para los posts).

### `sun_panel.py` — el Sol hoy

Última imagen SDO (canal seleccionable) + nuestro propio mapa de regiones activas
trazado desde coordenadas NOAA (nuestro «Raben» sin problemas de copyright).

### `sn_view.py` — campo de la supernova

Cutout de referencia (DESI Legacy Survey / DSS vía hips2fits) con crosshair en la
posición de la SN; lado a lado o GIF blink animado cuando el usuario aporta la imagen
del observatorio.

### `blink_view.py` — blink de supernovas (ADR-018)

Pareja alineada (FITS del usuario + cutout PanSTARRS DR1 g casado en
centro/escala/rotación vía hips2fits) renderizada para blinking: frames con estirado
por percentiles y la SN marcada en su posición catalogada, exportados como GIF
animado (modos blink y fade) y como PNG lado a lado para posts. Los rótulos son
monolingües (idioma de la UI) y nombran al observatorio configurado; los exports
pueden hacer zoom sobre la SN (`crop_zoom`), el tamaño de la marca es ajustable, el
fondo del survey se puede igualar con `auto_gain` (por mediana) y la cadencia del
blink es configurable. El mismo estirado y zoom alimenta la pestaña de blink en vivo
de la GUI.

## Reglas

- Nada de imágenes de terceros con copyright en las exportaciones: solo material de
  dominio público (SDO) o de servicio público (Legacy Survey / CDS) con crédito, o
  renders propios.
- Ninguna función de viz hace red; reciben el dict de datos y devuelven/exportan la
  figura.
