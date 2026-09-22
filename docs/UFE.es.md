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
* **Pestañas**: una por funcionalidad. Las fases D, E y F del plan las
  llenarán con Anotar, Blink y Comparación; añadir una funcionalidad
  nueva es añadir una pestaña.
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
