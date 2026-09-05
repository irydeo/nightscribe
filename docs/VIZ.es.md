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

### ApproachChart — vista geocéntrica animada (ADR-029)

Carta vectorial interactiva en `gui/widgets/approach_widget.py` (sin matplotlib).
Muestra cómo se acerca el objeto **visto desde la Tierra**, usando la **Luna como
vara de escala fija** (posición real en la fecha de referencia, no animada).

- Tierra en el origen (punto `ACCENT2`), punto del objeto móvil (`ACCENT`).
- Círculo de 1 LD (`MUTED`) como referencia de escala; Luna en su posición
  real en ese círculo.
- Traza geocéntrica discontinua (`ACCENT`) en una ventana de ±30 días
  alrededor del CA (o la fecha dada si no hay CA, `e ≥ 1`).
- Diamante CA con etiqueta `CA X.XX LD` (solo órbitas cerradas).
- Status: `<fecha> · X.XX LD <tendencia> · CA X.XX LD (<fecha CA>)` o
  `<fecha> · X.XX LD <tendencia> · no return (open orbit)`.
- Play/Pause + slider de scrub + hover sobre la traza (`R = X.XX LD`).
- Export PNG vía `ChartView.export_png` (lo que se ve, zoom incluido).
- Matemática en `core/approach_math.py` (pura, sin matplotlib).
- No sustituye al inset estático de `viz/orbit_view.py` (sigue exportando la
  PNG de redes); es su equivalente vivo en la GUI.

**Acabado visual (polish):**

- Halos de separación (anillo fino del color del cuerpo, `NoBrush`, pen
  cosmetic) alrededor de Tierra, Luna, punto del objeto y diamante CA — los
  cuerpos siempre se leen separados, aunque se pisen en distancia.
- Etiquetas (Tierra / Luna / 1 LD / CA) sobre una **placa de fondo** (BG al
  85 % + borde MUTED) que no se funde con la traza ni con el círculo.
- **Posicionamiento anti-colisión**: cada etiqueta prueba 8 direcciones
  alrededor de su ancla (empezando por la más natural) y elige la primera
  cuyo rect no cruce la traza ni otra placa; si ninguna, cae a la preferida. Las etiquetas son fijas en el frame (no se mueven con el scrub).
- Traza geocéntrica discontinua 2.4 px `[8, 5]`; círculo de 1 LD punteado
  1.5 px `[2, 4]` (ambas pens cosméticas: no engrosan con el zoom).

## Reglas

- Nada de imágenes de terceros con copyright en las exportaciones: solo material de
  dominio público (SDO) o de servicio público (Legacy Survey / CDS) con crédito, o
  renders propios.
- Ninguna función de viz hace red; reciben el dict de datos y devuelven/exportan la
  figura.
