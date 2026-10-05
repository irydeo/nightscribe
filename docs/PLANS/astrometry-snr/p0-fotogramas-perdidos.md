# P0: los fotogramas que se quedan en el suelo

**Estado**: hecho.

## El síntoma

En una visita de 140 tomas de **2025 UR** (Observatorio Irydeo), la
pestaña Astrometría decía:

> «Sequence stacked: 2 observations measured. **62 frames could not be
> aligned and were left out.**»

Dos observaciones de 39 tomas cada una, con 62 fotogramas tirados. Y el
propio código lo tenía apuntado: `track_stack.usable()` explicaba que
apilar mal esos fotogramas «arrastró el SNR base de 15,8 a 11,4 en una
noche con dos tandas cuyo apuntado saltó un campo entero (63 de 140 tomas
fallaron y entraron torcidas)». O sea: primero se descubrió que entraban
torcidas, se dejaron fuera, y ahí se quedó el asunto. La mitad de la noche
en la papelera.

## El diagnóstico, medido

Los nombres de los ficheros ya lo decían: `C452X51-2` (78 tomas, de
21:40:07 a 21:46:51) y `C452X51-3` (62 tomas, de 21:51:41 a 21:57:02). Dos
tandas, con cinco minutos de salto en medio.

Al registrar los 140 fotogramas contra el primero, la frontera era limpia:
las 78 primeras encajaban con **rms 0,25 a 0,45 px**, y las 62 siguientes
daban **rms 1,2 a 1,8 px** y se rechazaban. Pero el desplazamiento que
encontraban era **coherente** (dx ≈ −819, dy ≈ +335, es decir 884 px, y
27 estrellas emparejadas): la segunda tanda **sí encaja**, lo que no
encajaba era el modelo.

La causa era doble:

1. **El campo está rotado 0,12°.** Con traslación sola quedan 1,5 px de
   residuo; con un ajuste rígido (rotación sobre el centro más traslación)
   bajan a **0,80 px**. `register_sequence` se llamaba con
   `allow_rotation=False`, así que la rotación nunca se intentaba.
2. **La puerta de calidad era absoluta**: 0,75 px (`register.MAX_RMS_PX`),
   y 0,80 px no la pasa. Por 0,05 px se tiraban 62 tomas.

Y un tercer hallazgo, al revisar el resultado: una toma de la primera
tanda (21:42:08, con el p99 saltando de 5.400 a 12.816 ADU: una nube o una
estela) **no encaja con ninguna hipótesis**, y su reintento de rotación se
aceptó con **solo 2 estrellas** y −106° por el atajo de calidad. Eso es un
fotograma torcido apilándose, que es justo lo que la puerta existe para
evitar.

## El arreglo

1. **La puerta sigue al seeing, no a un número fijo** (`register.rms_limit`):
   el residuo se juzga como **fracción del FWHM** (0,25, con suelo en
   0,5 px), porque lo que importa es cuánto ensancha el apilado, y eso es
   una razón. En 2025 UR el FWHM medido es **5,4 px**, así que la puerta es
   1,35 px, y 0,80 px pasa con holgura. El valor absoluto queda como
   respaldo cuando el que llama no conoce la PSF.
2. **Segundo intento con rotación** (`register_sequence`): la traslación se
   prueba primero (es el caso común y el más rápido); si no pasa la puerta,
   o si pasa pero el propio estimador dice que no explicó las estrellas
   (`ROTATE_TRIGGER_PX`, 0,7 px), se reintenta con ajuste rígido. La
   rotación solo gana si quita un cuarto del residuo, así que una rotación
   espuria no entra.
3. **Dos salvaguardas en el reintento**: las estrellas tienen que
   **certificarlo** (`trusted(..., require_stars=True)`: el atajo de
   correlación dice «es el mismo cielo», nunca «este es el mapeo»), y el
   ángulo no puede pasar de `MAX_STEP_DEG` (15°, una constante que estaba
   escrita desde el principio y **no se usaba en ningún sitio**).
4. **El informe dice qué pasó** (`track_stack.registration_report`): cuántas
   tomas volvieron, cuántas se salvaron por rotación, **por qué** fallaron
   las que fallaron, y si la visita es en realidad **varias tandas**, con el
   salto, el hueco de tiempo y la rotación. La pestaña lo cuenta en palabras
   en vez de un número seco.

## Verificación

**Test unitario** (`tests/unit/test_track_stack_register.py`, sin red):
sintéticos con dos tandas desplazadas y rotadas, la puerta contra el FWHM,
el atajo de correlación que no certifica una rotación, el informe que
encuentra las dos tandas con su desplazamiento y su ángulo, una sola tanda
que es un solo bloque, y una toma imposible que se cae con su motivo.

**Sobre los datos reales** (2025 UR, 140 tomas):

| | antes | después |
| --- | --- | --- |
| Tomas usables | 78 de 140 | **139 de 140** |
| Fuera | 62 | 1 (la toma con nube, con su motivo) |
| Salvadas por rotación | 0 | 47 |
| rms mediano | 0,40 px | 0,46 px |
| Tandas detectadas | no se decía | **2** (77 + 62, salto 884 px, hueco 289 s, −0,118°) |
| SNR de una estrella en el apilado | **1.826** | **2.702 (×1,48)** |

El SNR se midió apilando sobre las estrellas la misma región en los dos
casos (una estrella no saturada en la zona común a las dos tandas, caja de
64×64 px, apertura de 6 px, ruido por MAD de la corona). La ganancia
supera a √(139/77) = 1,34 porque la segunda tanda tenía algo mejor de cielo.

**Un dato que aparece al medirlo**: las dos tandas **solo se solapan en
parte** (884 px de 2048). El objeto está en las dos, porque el observador
apuntaba a él, pero las comparsas que caigan fuera de la zona común no se
pueden medir en la mitad de las tomas. El apilado de estrellas lo tolera
(cada ventana se recorta en la toma que toca), pero conviene saberlo al
elegir la secuencia.

## Lo que NO se hizo

- **Partir la visita en dos.** Era el plan inicial («la visita parece dos
  runs, ofrécele partirla»), pero con el registro arreglado las dos tandas
  se apilan juntas y no hace falta: la app informa de la estructura y sigue.
  Partir la visita sigue siendo posible a mano y sigue teniendo sentido
  cuando las dos tandas son de noches distintas.
- **Aceptar la rotación siempre** (`allow_rotation=True` de entrada): el
  reintento dirigido mantiene el caso común en una sola pasada y deja el
  barrido de ángulos (caro) solo para los fotogramas que lo necesitan.
