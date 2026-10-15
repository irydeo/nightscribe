# 12. La tarjeta gráfica

Las dos etapas más pesadas de un **track & stack** pueden correr en tu **tarjeta
gráfica** en vez de en el procesador: el **registro** (dónde cae cada toma y
qué estrellas tiene) y el **apilado** (deformar cada toma sobre la referencia y
combinarlas). Está **encendida por defecto** y no cambia lo que se mide: el
resultado es el mismo, y una máquina sin tarjeta corre en el procesador
exactamente como corría.

## Qué acelera

- **El registro.** La estimación por toma son dos medianas sobre el frame
  entero (el fondo por bloques y el ruido), y una tarjeta es un orden de
  magnitud más rápida en ellas.
- **El apilado.** El warp (deformar cada toma sobre la referencia) y el combine
  (reducir las tomas a una imagen). El combine ahora sostiene **cualquier
  número de tomas**, así que el apilado de toda la secuencia de una visita larga
  también se queda en la tarjeta, no solo los apilados cortos por observación.

> **¿Por qué es más rápida una tarjeta aquí?** Las dos etapas leen y escriben
> arrays del tamaño de un frame, así que lo que decide es el **ancho de banda de
> memoria**, y el de una tarjeta es un orden de magnitud mayor que el del
> procesador. No es otro algoritmo: es el mismo sobre hardware hecho para mover
> píxeles.

## Encenderla y apagarla

El interruptor está en **Ajustes → Medición → Trabajo** (tras la puerta **Avanzado**):
**Deformar y combinar en la GPU**, con un selector de **Backend** al lado. Viene
**encendido**, y en una máquina sin tarjeta no hace nada: la app se da cuenta y
corre en el procesador.

La nota del propio run dice **qué dispositivo** hizo el trabajo, así que una
reducción nunca tiene que adivinarlo. La propia fila muestra la **tarjeta que ve
ahora mismo** (o que no se encontró ninguna), así lo sabes antes de lanzar. Para
forzar el procesador, desmarca el interruptor.

## El backend: OpenCL por defecto

- **OpenCL** (el defecto) corre en **NVIDIA, AMD e Intel** y no necesita nada
  instalado a mano: viaja con la app.
- **Auto** prueba CUDA primero y cae a OpenCL.
- **CUDA** es solo NVIDIA y se instala a mano (abajo).

> **¿Por qué OpenCL y no CUDA por defecto?** Porque OpenCL es el que la app
> puede repartir, así que funciona de fábrica en cualquier tarjeta, y está
> medido que no es más lento que CUDA en la misma máquina. CUDA se queda para
> quien lo quiera.

## Activar CUDA a mano (NVIDIA)

CUDA no se reparte: es una instalación manual para una tarjeta NVIDIA.

1. Instala CuPy con el wheel que case con tu runtime de CUDA: `cupy-cuda12x`
   para CUDA 12.x, `cupy-cuda11x` para CUDA 11.x. (El sufijo sigue la versión
   mayor del toolkit de CUDA que te dé el driver.)
2. Comprueba que importa: `python -c "import cupy; print(cupy.__version__)"`.
3. En **Ajustes → Medición → Trabajo** (tras la puerta **Avanzado**), pon el **Backend** en
   **CUDA** y arranca el run otra vez.

> **Una instalación empaquetada no admite CUDA.** Los builds de Windows y macOS
> llevan su propio Python, así que un `pip install` dentro de ellos no es
> posible: ahí **OpenCL** es el único backend. CUDA es para correr desde el
> código, o para los paquetes de Linux, que usan el Python del sistema.

## Qué cambia y qué no

- El **método**, las banderas y las medidas son los mismos.
- El apilado es la misma imagen **hasta una fracción de ADU** (los dos caminos
  están fijados por un test para coincidir).
- El **camino del procesador es siempre la referencia** y el respaldo:
  cualquier problema con la tarjeta y el run sigue en el procesador.

## Cuándo paga y cuándo no

Paga donde el trabajo es grande y continuo: la estimación por toma y los
apilados de **frame completo** o de **muchas tomas**. No paga en recortes
pequeños, y el **barrido de velocidad se queda en el procesador a propósito**
(su ventana es pequeña, y releerla para cada candidato cuesta más de lo que
ahorra).
