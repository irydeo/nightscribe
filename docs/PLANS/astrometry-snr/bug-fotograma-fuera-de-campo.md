# Arreglo: el fotograma que no contiene la observación

**Estado**: hecho. **Origen**: un run real del autor que abortó con un error
de scipy.

## El síntoma

En una visita real, la pestaña Astrometría no medía la fotometría y el
proceso se caía con este mensaje:

```
ValueError: Expected homogeneous transformation matrix with shape (2, 2)
for image shape (0,), but bottom row was not equal to [0, 1]
```

El mensaje apunta a la matriz. **La matriz estaba bien**: el problema era la
imagen.

## La cadena de causas

1. `track_stack._source_box()` calcula la región del fotograma que necesita
   la caja de salida. Si esa región cae **entera fuera** del sensor,
   recortaba el borde bajo a cero y luego forzaba el alto a «al menos un
   píxel más», así que devolvía una caja **justo fuera** del marco en vez de
   decir que no había nada.
2. `calibration.read_image(path, box)` con esa caja degenerada devolvía un
   array **1-D vacío**, `shape (0,)`. Comprobado sobre un fotograma real:
   `(0,0,0,0)`, `(5,5,5,5)`, `(2048,2048,2048,2048)` y `(2100,2100,2200,2200)`
   devuelven `(0,)`; en cambio `(0,0,0,10)` devuelve `(10,0)`, que sí es
   2-D.
3. `scipy.ndimage.affine_transform` recibe entonces una imagen **1-D**, con
   lo que `input.ndim + 1 == 2 == matrix.shape[1]`, y entra en la rama de
   **matriz homogénea**: nuestra matriz es la rotación 2×2, cuya fila
   inferior no es `[0, 1]`, y la rechaza. De ahí el «for image shape (0,)»:
   **la imagen es 1-D**, y por eso el mensaje engaña.

Y como el reventón ocurre en `stack_groups`, **antes** de la medida, el run
se abortaba entero: de ahí que tampoco hubiera fotometría. Una sola causa
para los dos síntomas.

**Por qué apareció justo ahora**: P0 hizo usables los fotogramas del segundo
run, que están a 884 px. Para esos fotogramas la caja de una observación
puede caer fuera del sensor, y el motor leía fuera. Antes esos fotogramas se
tiraban, así que el fallo era **inalcanzable**.

Reproducido con las tomas reales: en `..._215408_...`, con la caja de
1024 px, la región fuente salía en `y = 2057..2058` de un sensor de 2048 →
lectura vacía → error.

## El arreglo (cinco piezas)

1. **`_source_box` devuelve `None` cuando la caja no corta al fotograma**, y
   `_warp_to_box` devuelve entonces un marco **inválido** (ceros y máscara
   falsa) **sin leer nada de disco**. Un test lo demuestra pasando una ruta
   que no existe: si algo intentara leer, el test fallaría con un error de
   fichero en vez de dar una respuesta.
2. **`calibration.read_image` nunca devuelve 1-D**: una caja degenerada da
   un array 2-D vacío. Es defensivo y mata la clase entera de fallo: una
   «imagen» 1-D nunca es legítima.
3. **El motor EXCLUYE los fotogramas que no contienen el objeto**
   (`track_stack.inside_frame`), y lo cuenta: un fotograma registrado pero
   cuyo objeto cae fuera del sensor tiene cielo donde debería estar el
   objeto, así que apilarlo solo añade ruido justo donde se mide. El
   informe lo dice en palabras («N tomas no contienen el objeto y se han
   dejado fuera»).
4. **`_frame_noise` mide sobre 1 píxel de cada 4×4** (ver abajo).
5. **Comentario en el código con el mensaje engañoso de scipy**, para que el
   siguiente que lo vea no busque en la matriz.

## El 4×4, medido

El ruido de cada fotograma lo estima la MAD escalada, y la MAD es una
estadística **robusta de un campo estacionario**: su mediana la fijan las
muestras, no su número, así que submuestrear es legítimo mientras queden
suficientes. La tabla es de un fotograma real de 2048×2048:

| Muestreo | Valor | Tiempo | Error | Velocidad |
| --- | --- | --- | --- | --- |
| frame entero (4,2 M px) | 332,10 ADU | 94,6 ms | referencia | 1× |
| 1 de cada 2×2 (1,0 M) | 332,10 ADU | 22,9 ms | 0,00 % | 4,1× |
| **1 de cada 4×4 (262 k)** | **332,10 ADU** | **4,6 ms** | **0,00 %** | **20,5×** |
| 1 de cada 8×8 (65 k) | 332,10 ADU | 1,3 ms | 0,00 % | 71,0× |

Se elige **4×4**: da el mismo número al último dígito y 262 k muestras
sobran para una mediana. En el motor, con el `asarray` y el recorte
incluidos, son **6,9 ms** por toma, o sea **1,0 s por visita de 139 tomas
frente a 13,2 s**: doce segundos que no se gastan. El 8×8 sería aún más
rápido pero ya no compra nada, y el 2×2 deja la ganancia en la mesa.

Lo mismo vale para el umbral de `psf_elongation` (P2), que usa `sky_sigma`
sobre el anillo: allí son unos cientos de píxeles, no un problema.

## Verificación

**Tests** (sin red):

- `_source_box` dice `None` con la caja entera fuera, y devuelve una caja
  **dentro** del sensor cuando el solape es parcial;
- `_warp_to_box` con una ruta inexistente y la caja fuera devuelve un marco
  todo ceros y una máscara toda falsa, sin leer y sin reventar;
- un fotograma cuyo objeto cae fuera del sensor se queda fuera del apilado
  (`n_frames` baja en uno) y `_indices` lo excluye;
- un fotograma sin posición de objeto sigue quedando fuera (la regla
  anterior no se pierde);
- `_frame_noise` sigue dando el mismo número.

**Sobre los datos reales**: el mismo guion que reventaba ahora completa los
tres tamaños de caja (frame completo, 1024 y 512) sin error, y cuenta los
fotogramas fuera del campo.

## Lo que este arreglo NO cambia

La ganancia de P0. En el caso real el objeto está en los dos campos (el
observador apuntaba a él en las dos tandas), así que `inside_frame` no
excluye ninguno y el apilado usa las 139 tomas. El filtro solo actúa cuando
el objeto **no** está en el fotograma, que es cuando apilarlo sería un
error.
