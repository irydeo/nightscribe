# P3: diagnóstico de la noche

**Estado**: hecho.

## Las dos preguntas

Después de un run, el observador pregunta dos cosas que hasta ahora nadie
contestaba: **¿hasta dónde he llegado esta noche?** y **¿es buena mi
solución en todo el campo, o solo en el centro?**. Las dos se responden con
las estrellas de **ese** stack, no con una tabla.

## 1. La magnitud límite

Para una fuente limitada por el cielo, la señal-ruido cae como una potencia
de la magnitud:

    log10(SNR) = a + b · mag          con b ≈ −0,4

porque una magnitud es un factor `10^0,4 = 2,512` en flujo y el ruido no
sabe lo brillante que es la estrella. Ajustando esa recta a las estrellas
**medidas en el stack** y resolviéndola para SNR = 5 sale la magnitud límite
de esa noche, con el cielo, el seeing, la exposición y la apertura dentro de
los dos números.

Y el **pendiente es una comprobación**, no un adorno: un campo con Luna,
con una exposición muy corta o con comparsas saturadas sale lejos de −0,4, y
entonces la cifra **no se cita**; el informe dice «no está limitada por el
cielo, no te fíes de ella» en vez de dar un número que nadie debería usar.

**El ajuste es Theil-Sen** (la mediana de las pendientes de todos los pares
de estrellas, y la mediana de las ordenadas al origen que implica), y no
mínimos cuadrados con recorte. La razón está medida: con siete puntos y una
comparsa saturada, el recorte **no reparó** el ajuste (la recta arrastrada
infla la MAD contra la que se recorta) y la magnitud límite se iba 0,5 mag;
la mediana de 21 pares no la mueve una estrella. Además no hay umbral que
elegir, que con cinco puntos es una corazonada disfrazada de parámetro.

## 2. La rejilla de residuales

Una solución puede ser buena en el centro y mala en las esquinas
(distorsión, una escala equivocada, el chip inclinado), y **un número para
toda la placa esconde justo eso**. La mediana del residual por celda de una
rejilla 4×4 dice **dónde** de un vistazo, y la dispersión entre celdas dice
si la solución es uniforme. Tycho dibuja el mismo mapa por la misma razón.

La **mediana** por celda y no la media: un emparejamiento malo o un rayo
cósmico no puede pintar una esquina de rojo él solo. Y una celda sin
estrellas queda **vacía**, nunca a cero: un cero se leería como «solución
perfecta» donde no se ha medido nada.

## Qué se hizo

1. `photometry.measure_point` devuelve ahora **`sigma_pp` y `snr`**, medidos
   sobre el mismo anillo que ya usaba para el cielo (una MAD robusta de unos
   cientos de píxeles). Es lo que faltaba para poder hablar del SNR de una
   comparsa, y `measure_matched` (P2) lo reutiliza, así que las dos medidas
   comparten denominador.
2. `photometry.limiting_magnitude(pairs)`: Theil-Sen sobre
   `(magnitud, SNR)`, con el pendiente comprobado contra la física.
3. `photometry.quality_grid(points, shape, n=4)`: la mediana por celda, la
   mediana global, la peor celda y la dispersión.
4. **En el motor**, los dos se construyen con las **mismas comparsas** que
   el punto cero (nada se mide dos veces): su `(magnitud de catálogo, SNR)`
   para el límite, y su posición medida contra la de catálogo para la
   rejilla. La separación se calcula con el ángulo pequeño (un segundo de
   AR son `cos(dec)` segundos en el cielo), que en estos campos es exacto
   muy por debajo de los residuales que se juzgan.
5. **En la pestaña**, la nota del run dice las dos cosas en palabras.

## Verificación

**Tests** (sin red, `tests/unit/test_photometry_diagnostics.py`): el límite
sale donde lo pone el cielo con un juego limpio; con siete estrellas, un
15 % de ruido y una comparsa saturada (×40) el resultado sigue a 0,35 mag y
la saturada queda marcada; un campo que no está limitado por el cielo sale
**marcado** (pendiente −0,6); con menos de cuatro estrellas no hay medida; y
en la rejilla, una esquina mala se señala (mediana 0,2″, peor celda 1,5″),
una solución uniforme no tiene dispersión, una celda vacía es `None` y no
cero, y con un solo punto no se juzga.

**Sobre los datos reales** (2025 UR, apilado de 139 tomas, 14 estrellas
medidas entre el brillo y el límite):

| | medido | la física dice |
| --- | --- | --- |
| Pendiente de log10(SNR) contra magnitud | **−0,394** | −0,400 |
| ¿Limitada por el cielo? | sí | (no aplica) |

Un 1,5 % de acuerdo con la ley, que es la comprobación de que el ajuste mide
lo que dice medir. (La magnitud límite de esa medida sale en magnitudes
**instrumentales**, porque la prueba no consulta catálogo; en el motor se
usan las de catálogo de las comparsas y sale la real.)

## Lo que no se hizo

- **Pintar la rejilla** como mapa de calor en la pestaña: hoy se dice el
  peor caso en palabras. El dato está (`cells`) y el sitio natural sería el
  visor de la imagen, donde las celdas caen sobre la placa; queda apuntado.
- **Usar el límite para decidir** automáticamente cuántas tomas tomar: el
  número se enseña, la decisión sigue siendo del observador.
