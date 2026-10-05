# Campaña de velocidad del track & stack

> Continuación de `docs/PLANS/astrometry-minor-planets/` y
> `docs/PLANS/astrometry-snr/`. Aquellas cerraron el bucle y subieron la
> señal; esta baja el **tiempo de pared** del apilado sin tocar el
> resultado. GPU descartada a propósito (ver el final).

## Por qué

El track & stack de una visita real (140 tomas de 2048²) tardaba del orden
de cinco a seis minutos, y la mayor parte no era física: era trabajo
repetido y un solo hilo. El motor corría en **un** hilo de los 32 de la
máquina, releía la ROI del barrido 25 veces y usaba `nanmedian` para la
combinación por defecto.

## Qué se hizo

Cinco palancas, todas de algoritmo o de hilos, **sin ninguna dependencia
nueva**:

1. **El barrido lee la ROI una vez (F1).** Los 25 candidatos mueven el
   objeto unos píxeles, así que cada fotograma se lee UNA vez, en la unión
   de las regiones que todos los candidatos necesitan, y cada candidato
   recorta su caja de RAM. Los desplazamientos base, los minutos
   transcurridos y la escala se calculan una vez, no 25. El plan D12 ya lo
   pedía; faltaba.
2. **La combinación usa una mediana por ordenación con centinela (F2).**
   `outliers.nanmedian_axis0` mete los no válidos al final como `+inf` y
   los ignora con el recuento: el MISMO número que `nanmedian`, x4,8 más
   rápido. Es la fuente única de la mediana que ignora lo que no está.
3. **El registro deja de repetir trabajo (F3).** La `source_image` de la
   referencia se construía en cada fotograma; ahora se construye una vez y
   viaja. Y el fondo por bloques pasa de un bucle Python a una sola
   mediana en C cuando el frame divide por el bloque.
4. **El combine se paraleliza por columnas (F4).** La reducción es por
   píxel, así que cortar la imagen no cambia un solo píxel: el clip
   sigma, que camina el cubo varias veces, se reparte entre los hilos.
5. **El número de hilos se CALCULA (F4).** `core/parallel.py` lo saca de
   los núcleos que el proceso puede usar de verdad (afinidad incluida) y
   lo acota por la memoria que una tarea necesita. Windows y Linux, sin
   rama por SO. El ajuste `astrometry_threads` (0 = automático) permite
   caparlo a mano.

## Lo que se midió

Máquina: Ryzen 9 5950X (16 núcleos / 32 hilos). `benchmarks/track_stack_bench.py`.

| Etapa | Antes | Después | Ganancia |
| --- | --- | --- | --- |
| `estimate_transform` (2048²) | 360 ms | **204 ms** (ref_src cacheada) | x1,8 |
| `register._background` (2048²) | 131 ms | **74 ms** (vectorizado) | x1,8 |
| Mediana por eje 0 (60, 512, 512) | ~750 ms | **136 ms** (centinela) | x5,5 |
| Barrido completo (60 x 1024²) | 6348 ms (1 hilo) | **1272 ms** (auto) | **x5,0** |
| `stack_group` sigma, frame completo (60 x 1024²) | 10143 ms (1 hilo) | **2716 ms** (auto) | **x3,7** |
| `combine` sigma (60, 512, 512) | 957 ms | **298 ms** (auto) | **x3,2** |

Sobre 140 fotogramas el registro pasa de ~50 s a ~29 s solo con F3, y el
barrido y los stacks finales bajan por F1 y F4. Los números viven también
en los comentarios del código.

## Lo que queda apuntado

- **El combine sigma sigue siendo el cuello** del stack final (x6,5 el
  `median`, x40 el `mean`). Bajar las iteraciones por defecto de 3 a 2 es
  la palanca siguiente, y hay que medir cuántos píxeles cambia antes de
  tocarla.
- **El stack final a frame completo** por defecto (140 deformaciones de
  4 MP). Un defecto más contenido, o compartir la deformación entre el
  stack del objeto y el del las estrellas (solo difieren en una
  traslación), recortaría más.
- **Abrir el FITS una vez por fotograma** en las ventanas de comparsas.

## GPU: por qué no

Se midió y se descartó. La deformación y la combinación son lo único que
una GPU acelera de verdad, y tras paralelizar el CPU x5-10 esas etapas, la
ganancia marginal de una GPU es x1,5-2 a cambio de una dependencia (OpenCL
o CuPy), kernels por dispositivo y empaquetado del runtime. El suelo que no
acelera (lectura de FITS, ASTAP, Find_Orb) ya es el 30-40 % del run. Decisión
en ADR-062.
