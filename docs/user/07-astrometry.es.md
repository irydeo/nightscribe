# 07. Astrometría

La astrometría de cuerpos menores (asteroides, NEOs, cometas) vive en la
pestaña **Astrometría** del editor FITS, y su motor es el *track & stack*:
apilar tus frames **siguiendo el movimiento del objeto**, no el de las
estrellas.

## Antes de nada: resolver la placa

Todo lo astrométrico necesita una **solución de placa** (la WCS: qué punto
del cielo es cada píxel). En **Configuración… → Medida → Solver de placa** eliges:

- **Auto** (recomendado): prueba primero **ASTAP** local (rápido, sin red,
  gratis) y cae a **nova.astrometry.net** si no lo tienes o no resuelve.
- ASTAP solo, o nova solo, si lo prefieres.

Con *Save the solved WCS into the FITS header* (activado por defecto), la
solución se escribe en la cabecera del FITS (sin tocar los píxeles) y
cualquier otro programa la verá.

> **¿Por qué ASTAP primero?** Porque resuelve en segundos en tu máquina, sin
> subir nada a internet ni depender de la cola de un servicio ajeno. Nova es
> el respaldo: más lento y con clave de API, pero ciega de verdad (no
> necesita saber dónde apuntabas). La combinación cubre el 99% de los casos
> sin que tengas que decidir.

## El track & stack

**Apilar la secuencia** ejecuta el pipeline completo: resuelve la referencia,
registra los frames entre sí, barre la velocidad del objeto (que llega de
Horizons al empezar), detecta, apila cada observación, mide y comprueba.
Mientras corre, el mismo botón es Cancel.

La decisión clave es **Observaciones**: en cuántas observaciones (puntos de
medida) divides la secuencia. Cada observación es un grupo contiguo de
frames con su propio instante de media exposición (T_mid).

> **¿Por qué importa el número de observaciones?** Porque la SNR crece con
> la raíz cuadrada de los frames: pedir más observaciones *reparte* la señal
> y cada una llega menos lejos. Junto al selector verás la SNR que se espera
> para cada observación con el reparto actual. Tres observaciones sólidas
> valen más al MPC que seis débiles; la regla práctica es: las justas para
> ver el movimiento, no más.

> **¿Por qué T_mid y no el inicio de la exposición?** Porque la posición del
> objeto durante la toma es la media de su recorrido, y su mejor estimador es
> el instante central. Reportar el arranque introduce un sesgo de media
> exposición, que en un NEO rápido (5″/min) son decenas de segundos de arco
> de error sistemático. El MPC espera T_mid; NightScribe lo calcula por ti.

### Las opciones del stack, y su motivación

- **Método** (cómo se combinan los frames): la **media con sigma-clip** es
  el defecto porque llega un cuarto de magnitud más profundo que la mediana
  (una mediana es 1,25 veces más ruidosa que una media) y, a diferencia de
  la media simple, rechaza los trazos de satélites y rayos cósmicos.
  **Weighted** es el mismo clip pero pesando cada frame por el ruido de su
  cielo: en una noche estable no cambia nada, y es lo que salva una noche
  con cirros finos o Luna. Usa la **mediana** solo cuando haya que rechazar
  algo a toda costa y el clip no pueda.
- **Remuestreo**: el **bilineal** (defecto) da una imagen visiblemente más
  limpia *sin coste en profundidad* (medido por inyección de fuentes, no
  asumido). El **cúbico** conserva una PSF marginalmente más afilada con una
  imagen más granulada: úsalo si persigues detalle en un campo muy poblado.
  Ojo: una imagen más suave no es más profunda; la profundidad la decide el
  método de arriba y los frames que entran.
- **Campo**: cuánto cielo cubre el stack final de cada observación. El frame
  entero conserva las comparadas alrededor; una ventana menor es más rápida
  y ligera. El barrido de velocidad siempre trabaja sobre el recorte del
  rastro del objeto, diga lo que diga esto.
- **Aplicar la calibración**: aplica la receta de la pestaña Calibración a
  cada frame al leerlo. Sin ella, el polvo del tren óptico y el viñeteo se
  cuelan al stack y, como el objeto y las comparadas no caen en el mismo
  sitio, solo el viñeteo ya vale un error sistemático de una décima de
  magnitud en el brillo.
- **Medir el brillo** y **Guardar el apilado de estrellas**: la magnitud se mide
  sobre el stack del objeto y sobre un segundo stack alineado a las
  estrellas (en el del objeto son trazos). Sin comparadas en el campo, el
  run reporta solo posiciones y lo dice.

## Leer el resultado

El panel muestra lo que el run encontró: el dithering de la sesión, la
calidad de la WCS compuesta, el barrido de velocidad, la detección y el
brillo. Cada observación se mide **dos veces** con la misma receta de
centroide: sobre el stack y frame a frame. Un desacuerdo mayor de 0,5″ o 3σ
se marca; nunca se resuelve en silencio.

El botón **Re-medir el brillo** vuelve a ejecutar la receta sobre los
**apilados guardados de las observaciones del run** (los del objeto y sus
estrellas) sin re-apilar la visita, y reescribe solo las bandas de los stacks:
la posición y la detección no se tocan. Necesita que el run haya guardado el
**stack de estrellas**. Cuando hay un track & stack abierto, la marca del objeto
del proyecto se apaga: el stack ya trae la posición medida por el run, y dos
marcas (en las coordenadas del plan y en las medidas) se leen como un error.

La **traza** del propio objeto en el stack de toda la secuencia también ayuda:
su longitud y su dirección dan dos movimientos candidatos que siembran el
barrido de velocidad, así que un movimiento que la efeméride acertó a medias se
puede encontrar con la propia luz del objeto. El barrido sigue decidiendo, con
la misma guarda de siempre: solo adopta un candidato que supere a la efeméride
por más que la dispersión de la rejilla.

**Animar o verificar** reproduce los stacks de las observaciones centrados en
el objeto y con un solo estirado: el objeto debe quedarse quieto en el
centro mientras las estrellas se arrastran. Es la prueba de fuego de que la
detección es real. **Guardar animación…** escribe ese mismo bucle como GIF o
MP4, con los niveles que hayas aplicado y la banda de la placa en cada
fotograma, para poder compartir la prueba. **Parpadeo / montaje…** escribe la
figura (GIF o montaje) con el mismo estirado en todos los paneles, para que uno
débil no parezca tan brillante como uno real.

Si el objeto está por debajo del umbral de detección, **Modo manual (objeto
débil)…** te deja marcarlo a mano sobre el stack de toda la secuencia: la
posición es tuya (anclada al centroide, ajustable en pasos de 0,1 px) y la
velocidad es la de la efeméride, sin barrido.

## El chequeo contra lo publicado

Tras el run, NightScribe compara tus puntos con las observaciones ya
publicadas del objeto (la API del MPC, o el NEOCP si aún no está confirmado)
y da un veredicto: si tu punto encaja o destaca.

> **¿Por qué «el chequeo filtra, no prueba»?** Porque ajustar a un arco
> corto no demuestra una detección: demuestra que no la contradices. El
> chequeo está para cazar errores (un objeto mal identificado, una escala
> mal resuelta), no para certificar realidades. Si tu punto destaca, el
> reporte se bloquea por defecto; **Forzar el reporte** lo fuerza dejando
> constancia en la propia nota del reporte.

## El reporte al MPC

**Generar** escribe el reporte con los instantes de media exposición, las
incertidumbres propagadas y la magnitud solo cuando hay comparadas. Toda
observación por debajo del **listón de envío** (SNR ≥ 20, configurable en
Configuración) queda fuera, con su razón.

> **¿Por qué un listón de SNR?** Porque el MPC archiva tus medidas para
> siempre y las usa para órbitas: un punto con SNR 8 tiene una incertidumbre
> de posición que estropea el ajuste de los demás. Mejor no enviar que
> enviar ruido. El listón es tuyo: bájalo si sabes lo que haces, pero el
> defecto es el que la experiencia marca.

- **Formato**: **ADES PSV** es el formato moderno, legible por máquina, que
  el MPC prefiere; el de **80 columnas** es el clásico, legible por todo
  programa. Si dudas: ADES.
- **Enviar al bloque MPC** rellena la caja de pegado de la visita; el
  validador de esa ventana tiene la última palabra antes de guardar.
- Si configuraste **Find_Orb** en Configuración…, la app cruza tus medidas contra
  la órbita que él mismo calcula y te muestra los residuos antes de enviar.
- **Deshacer esta ejecución** quita las observaciones de esta ejecución del proyecto
  (el run queda marcado como deshecho, para el rastro de auditoría); lo
  demás no se toca.

Siguiente: [08. Contarlo](08-posts.es.md).
