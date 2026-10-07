# Informe comparativo: apertura frente a filtro adaptado

**Fecha**: 2026-10-07. **Datos**: visita real de 2025 UR (140 tomas de 3 s,
2048², Clear, apilados de 30 a 139 tomas). **Estado**: el filtro está
disponible y **apagado por defecto**.

## Resumen

El filtro adaptado gana en las tres cosas que importan y cuesta lo mismo.
Medido, no estimado:

| | apertura | **filtro adaptado** |
| --- | --- | --- |
| **SNR del objeto** (apilado real de 139 tomas, 4 estrellas) | 1,00× | **1,55 a 1,63×** |
| **Sesgo del brillo**, SNR 9,3 (5 intentos) | +0,541 ± 0,121 mag | **+0,234 ± 0,037 mag** |
| **Sesgo del brillo**, SNR 44 (5 intentos) | +0,116 ± 0,016 mag | **+0,077 ± 0,007 mag** |
| **Error del cero punto** (8 fuentes de flujo conocido) | 0,092 mag | **0,035 mag** |
| **Dispersión de las comparsas** (mismas 8 fuentes) | 0,253 mag | **0,090 mag** |
| **Coste por estrella** | 9,91 ms | 10,22 ms (**+3 %**) |

## Cómo se midió cada cosa

1. **El SNR**: la razón entre los dos SNR medidos en el **apilado real** de
   139 tomas, con el mismo centro, el mismo cielo y el mismo σ, así que la
   comparación mide el **peso** y no otra cosa (P2). La fórmula
   `√(N_ap/N_ef)` predice 1,59 y se midió 1,55 a 1,63.
2. **El sesgo del brillo**: el instrumento de inyección mete una fuente de
   flujo **conocido** en copias de las tomas reales y mide
   `-2,5·log10(F_medido/F_inyectado)`; el punto cero se cancela en la razón,
   así que no hace falta catálogo (P4c).
3. **El cero punto y la dispersión de las comparsas**: ocho fuentes del
   **mismo flujo** inyectadas en las tomas reales, apiladas sobre las
   estrellas, medidas con los dos métodos y calibradas contra esa verdad
   conocida. El sesgo constante se lo come el cero punto (por eso se mide
   con el MISMO método que el objeto), así que lo que se compara es la
   **dispersión**.
4. **El coste**: el tiempo por estrella sobre un fotograma real, 40
   estrellas y 5 pasadas.

## Por qué gana, en una línea

Con una forma conocida `m` y ruido `σ` por píxel, el mejor estimador **lineal**
del flujo es `Σm(p−cielo)/Σm²` y su SNR es el mayor que cualquier filtro
lineal alcanza (Cauchy-Schwarz). Una apertura es el caso `m = 1` dentro del
círculo, que da a las alas ruidosas el mismo peso que al núcleo. A SNR alto
las dos coinciden; a SNR bajo la apertura pierde, y es justo donde está el
objeto débil.

## Lo que NO se ha medido, y por qué importa

- **El cero punto con un catálogo real**: las 8 fuentes inyectadas dan la
  comparación honesta entre métodos, pero no dicen cómo se comporta el cero
  punto con las comparsas de verdad (brillos distintos, colores distintos).
  Eso pide una noche con red y catálogo, y es la comprobación que falta
  antes de mover la magnitud del reporte.
- **La PSF empírica**: el filtro se construye con una **gaussiana** del
  seeing medido. En este apilado la gaussiana y el perfil empírico coinciden
  (P2), pero en un campo con coma o con estrellas muy saturadas podría no
  ser así, y entonces la forma del filtro sería el siguiente ajuste.
- **El efecto de la estela**: un objeto estelado se filtra con una PSF de
  línea (P2), y esa comparación no se ha medido contra la apertura.

## La decisión

**El filtro queda como opción, apagado por defecto.** El motivo no es la
duda sobre los números (son claros) sino la naturaleza del cambio: mueve la
magnitud que se publica, y eso es una decisión del autor, no un ajuste de
implementación. Lo que hay montado:

- casilla **«Filtro adaptado»** en los ajustes avanzados de la pestaña
  Fotometría, con el porqué medido en su tooltip;
- el flag viaja en la **receta**, así que se guarda con la placa y se
  restaura con ella;
- el **cero punto se mide con el mismo método que el objeto**, siempre: la
  mezcla (objeto con filtro, comparsas con apertura) metería la diferencia
  entre los dos métodos directamente en la magnitud, y el código lo impide
  por construcción (un solo despachador dentro de `measure_plate`);
- el valor de la apertura **se conserva al lado** cuando se mide con el
  filtro, para que la auditoría tenga las dos.

Cuando la comprobación pendiente (el cero punto con catálogo real) esté
hecha, girar el valor por defecto es una línea.
