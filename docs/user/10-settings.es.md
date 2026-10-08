# 10. Configuración

Todo lo configurable de NightScribe vive en **Herramientas →
Configuración…**. Este capítulo recorre cada sección: qué decide y cuándo
merece tocarla. Nada aquí es obligatorio salvo el sitio; cada integración
ausente simplemente deja su función en silencio.

## Sitio y equipo

- **Código MPC**, nombre, coordenadas y altura del observatorio
  (**Resolver coordenadas** desde el código, **Elegir en el mapa…**, o a
  mano). Es la identidad de tus reportes MPC: si envías astrometría, usa el
  código.
- **Código AAVSO**: tu código de observador; se escribe en el pase a EXOTIC
  de los proyectos de tránsito.
- **Idioma de la interfaz**: español, inglés o el del sistema; se aplica al
  reiniciar.

## Equipo y límites

- **Apertura (pulgadas)** y **magnitud límite**: las lee la puntuación de
  Esta noche para no proponerte lo inalcanzable. Sé honesto con la magnitud
  límite; el comando `inject` (capítulo 09) te da el número medido.

> **¿Por qué medir la magnitud límite en vez de creerse la ficha técnica?**
> Porque el límite real depende de tu cielo, tu cámara, tus exposiciones y tu
> reducción. Una cifra optimista llena la lista de objetivos imposibles; una
> pesimista te esconde noches buenas.

## Cámara (escala de placa)

**Tamaño de píxel**, **distancia focal**, **tipo de cámara** (CCD/CMOS/DSLR)
y **binning**. De píxel y focal sale la escala en segundos de arco por
píxel: la usan el consejo de exposición de los NEO, la fotometría y el
reporte MPC (el tipo de cámara se escribe en él).

## Perfil de cámara fotométrica

**Preset** (rellena el píxel y un perfil de partida), **pozo de
electrones**, **linealidad (ADU)**, **ganancia (e⁻/ADU)**, **ruido de
lectura (e⁻)**, **corriente de oscuridad** y **exposición máxima de
trabajo**.

> **¿Por qué «por unidad y por ganancia»?** Porque la linealidad y la
> exposición máxima no son propiedades del modelo de cámara, sino de tu
> unidad concreta al ajuste de ganancia que uses. El preset da el valor de
> hoja de características como punto de partida; el valor de verdad se mide
> en tus propias tomas (la app lo hace, capítulo 06), y 0 significa
> «desconocido»: la app lo dice en vez de inventárselo.

## Fotometría

- **Medir con el filtro adaptado por defecto**: con qué empieza una placa
  *nueva*. Una placa ya medida guarda su propia receta; el interruptor de la
  placa vive en la pestaña Fotometría, junto a la medida (capítulo 06).

## Anotación de cartas

Tu nombre (**Observador**), quién midió la placa (**Medidor**; vacío = el
observador) y la línea de **telescopio** tal como deben leerse en las cajas
de las cartas que exportes.

## Observación

- **Horizonte local**: fichero de horizonte (TheSkyX `.hrz` o pares «az
  alt») con margen de seguridad. Con él, la planificación deja de proponer
  lo que está detrás de tus obstáculos.
- **Tipos de objeto** visibles en Esta noche, **restricción lunar**,
  **valores de sesión** por defecto, la **lista de vigilias** de variables y
  la **carpeta de proyectos**.

## Solver de placa

**Solver**: *Auto* prueba ASTAP local y cae a nova.astrometry.net; también
puedes forzar uno. **Binario ASTAP**: ruta al ejecutable (vacío = buscar
`astap` en el PATH), con **Test** para comprobarlo. **Guardar la WCS
resuelta en la cabecera del FITS** (activado por defecto) deja la placa
resuelta para cualquier programa, sin tocar los píxeles.

## Find_Orb (chequeo de órbita)

El **Binario de Find_Orb** (el `fo` no interactivo) cruza tus medidas contra
la órbita antes del reporte MPC. **Instalar…** lo resuelve por ti: si `fo` ya
está en el PATH lo usa, y si no, crea un entorno privado con conda-forge sin
tocar nada de tu sistema. Sin él, el chequeo no está disponible y la app lo
dice.

## EXOTIC (reducción de tránsitos)

Ruta a un **Python ≤ 3.10** y al **entorno EXOTIC**. **Preparar entorno**
crea uno privado e instala EXOTIC en él (necesita red la primera vez);
**Test** comprueba que importa y dice su versión. Sin esto, el bloque EXOTIC
de los tránsitos (capítulo 06) no ejecuta, aunque el resto del flujo sigue.

## Integraciones

- **CCDciel**: host, puerto (3277 por defecto) y autoconexión. El control
  solo funciona con CCDciel abierto (capítulo 05).
- **NEOfixer**, **Astrometry.net**, **bot TNS**, **token de API AAVSO**:
  claves opcionales para, respectivamente, los reportes de la comunidad, la
  resolución ciega de placas sin WCS, las imágenes de descubrimiento de
  transitorios y la fotometría de la comunidad que alimenta las vigilias de
  brillantes (capítulo 04).

## Interfaz

- **Cielo animado en Bienvenida**: unas estrellas parpadean y la pantalla
  entra con un fundido; la Luna se dibuja con su fase real de esta noche de
  todas formas. Se aplica al momento.
- **Barra superior solo con iconos** (Editor FITS): los botones de acción
  muestran glifos compactos en vez de su texto. Se aplica al momento.

> **¿Por qué tantas cosas son «opcionales» y no piden cuenta en ningún
> sitio?** Porque el observatorio es tuyo y los datos también: NightScribe
> funciona completo sin una sola clave, y cada integración que falta se
> degrada con elegancia (la función se calla) en vez de bloquearte. Las
> claves abren puertas, no levantan muros.
