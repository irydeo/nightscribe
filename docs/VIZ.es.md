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

### SkyChart — carta de visibilidad interactiva (ADR-029)

Widget vectorial en `gui/widgets/sky_widget.py` (sin matplotlib): la misma curva de
altitud que `sky_view.py`, con ventana oscura, banda segura (ADR-020), mejor hora,
horizonte local, la Luna y el tránsito. **Leyenda** abajo-derecha del área de datos
que identifica cada línea (objetivo, Luna, límite de horizonte) con su mismo estilo y
color, sobre un fondo translúcido; textos por `self.tr()` y traducidos ES/EN. La curva
se clampa a 0° al dibujarla (nada bajo el eje Y), pero el tooltip sigue mostrando la
altitud real.

Todos los widgets de gráfico llevan además una **marca de agua** ("NightScribe",
configurable con `set_watermark()`) en la esquina inferior derecha, pintada en el
espacio del *viewport* (se queda anclada al hacer zoom/pan) y también estampada en los
PNG exportados — `gui/widgets/base_chart.py`.

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
- **Encuadre** (todo el barrido ±30 días): el semiextento del marco ajusta el
  arco de aproximación — `span = min(1.9 · max(CA, distancia actual, máximo del
  arco), CA / _PASS_SCENE_MIN)`, suelo `_MIN_SPAN_LD` — de modo que el
  asteroide está **en el lienzo desde que la carta se carga**, a cualquier
  distancia de pase y sin techo de zoom. En sobrevuelos muy próximos el
  guardián `CA / _PASS_SCENE_MIN` (0.30) evita que el pase se hunda en la
  esquina de la Tierra; en órbitas abiertas (e ≥ 1) el arco / punto actual
  encuadran igual.
- **Conjunto Tierra–Luna**: siempre dibujado y siempre legible. Vive en la
  esquina **más lejana al encuentro**; el círculo de 1 LD se dibuja con su
  **centro real en la Tierra**, clampado a una banda de radio legible
  `[_BUNDLE_RADIUS_MIN, _BUNDLE_RADIUS_MAX]` unidades de escena (la Luna
  conserva su dirección eclíptica real, de modo que las distancias fuera de
  banda son *diagramáticas* — la separación se lee en la línea de estado, no
  en el dibujo). Los sobrevuelos por dentro de la órbita lunar ya no lo
  recortan. La traza exterior que no cabe se queda cortada por el borde.
- **Marcador CA** (cerradas): al estar siempre el barrido en el marco, la
  máxima aproximación es *siempre* el clásico diamante + etiqueta
  `CA X.XX LD` (sin PIN de borde).

**Acabado visual (polish):**

- Halos de separación (anillo fino del color del cuerpo, `NoBrush`, pen
  cosmetic) alrededor de Tierra, Luna, punto del objeto y diamante CA — los
  cuerpos siempre se leen separados, aunque se pisen en distancia.
- Etiquetas (Luna / Tierra / CA) **sin caja de fondo**: cada texto se
  dibuja además como un contorno fino de 2 px en color BG
  (`QPainterPathStroker`) que lo separa de la traza y del círculo — el
  lienzo queda limpio, sin placas.
- **Posicionamiento anti-colisión**: cada etiqueta prueba 8 direcciones
  alrededor de su ancla (empezando por la más natural) y elige la primera
  cuyo rect no cruce la traza, ni otro rect, ni un marcador sólido
  (Tierra/Luna/CA), y quede dentro del marco; si ninguna, cae a la
  preferida. Las etiquetas son fijas en el frame (no se mueven con el scrub).
- **Tierra y Luna se separan solas**: la etiqueta de Tierra se lleva el
  lado *opuesto* a la Luna y la de Luna el lado tras su propio marcador
  (ambas del vector de la Luna en escena); cuando los dos marcadores quedan
  juntos, las etiquetas salen por una **escalera de radios**
  (`_PROBE_RADII`) hacia el hueco libre en vez de apretarse.
- La marca "1 LD" **no existe**: el círculo punteado de 1 LD con la Luna en
  su posición real ya es la vara de escala; se clampa a la banda legible al
  estar el conjunto arrinconado.
- Traza geocéntrica discontinua 1.5 px `[8, 5]` (fina a propósito — el punto
  móvil se lee sobre su propia línea a cualquier zoom); círculo de 1 LD
  punteado 1.5 px `[2, 4]` (ambas pens cosméticas: no engrosan con el zoom).

## Reglas

- Nada de imágenes de terceros con copyright en las exportaciones: solo material de
  dominio público (SDO) o de servicio público (Legacy Survey / CDS) con crédito, o
  renders propios.
- Ninguna función de viz hace red; reciben el dict de datos y devuelven/exportan la
  figura.
