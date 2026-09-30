# SEQUENCES · Fotometría de secuencias

*Qué es la serie fotométrica de NightScribe, cómo se mide desde la visita y
cómo leer la curva que sale. Documento de usuario.*

La parte de prácticas de observación está en [PHOTOMETRY.es.md](PHOTOMETRY.es.md)
y los números de calidad en [PRECISION.es.md](PRECISION.es.md); este documento
es el «cómo se trabaja».

---

## 1. Qué es una serie

Una **serie** es la medición de **muchas tomas del mismo objeto**, una detrás
de otra, como un solo conjunto:

- cada toma se mide con la **misma receta** que una placa suelta (centroide,
  apertura, cielo, guards) y con su **propio punto cero** (las comparaciones de
  esa misma toma);
- la curva es la **magnitud (o el flujo relativo) frente al tiempo**, con sus
  errores;
- las **puertas de calidad** marcan lo que no cuadra, pero **nunca borran un
  punto**: el observador decide.

El motor es el mismo para todos los tipos; el tipo solo elige los parámetros y
el aviso de cadencia.

## 2. Tipos de serie

| Tipo | Se lee con | Aviso de cadencia |
|---|---|---|
| **Tránsito de exoplaneta** | T_mid y profundidad | puntos por ingress (rojo si se pierde) |
| **Variable** | fase y periodo (plegado) | Nyquist |
| **HADS** | 12 puntos por ciclo | tope AAVSO de 15 min |
| **Supernova** | noches y ascenso | ninguna propia (la que pida el seguimiento) |

El motor es agnóstico: validar un tipo es elegir parámetros y checklist, no
escribir código nuevo.

## 3. Desde dónde se trabaja

**Siempre desde una visita del proyecto.** El flujo es:

```
Ficha del proyecto : Captura : Análisis (visita) : Publicación
```

En la ventana de la visita están sus ficheros (tomas FITS) y la acción
**«Medir la secuencia…»**, que abre el editor en la primera toma con el bloque
de serie armado. No hay diálogo de carpeta suelta: sin visita no hay serie, ni
Undo, ni análisis, ni agregación. El panel **a la izquierda de la imagen**
(visible solo con la visita armada) lleva el **navegador de tomas** (anterior /
siguiente, `toma i/N`, «primera toma»: la toma abierta es la referencia), el
bloque **Serie fotométrica** (la curva se ve en grande con **un clic**) y, en
proyectos de tránsito, el bloque **EXOTIC**. Si la primera toma no tiene WCS, se
resuelve sola con el solver configurado antes de empezar.

Para llegar con ficheros desde un listado, usa **«Añadir ficheros a la
visita»** (selección múltiple) en la propia ventana de la visita.

## 4. Flujo paso a paso

1. **Prepara la secuencia de comparación** en la pestaña Fotometría del editor
   (mitad superior, «Construir la secuencia…»). La serie usa esas comparaciones
   en cada toma.
2. **Mide el objetivo** una vez (un clic) para que la serie sepa dónde medir;
   o abre el editor desde la ficha con coordenadas, que se colocan solas.
3. Pulsa **«Medir la secuencia»**. Se abre una **ejecución** (con su `run_id`),
   se ve el progreso por toma y la curva se dibuja al terminar.
4. Revisa la **curva** (cruda y, si pediste detrend, también detrendada), los
   **puntos marcados** (rombos) y el **panel de resumen** (puntos, flags,
   coeficientes y avisos de cadencia y multinoche).
5. Si algo salió mal, **«Deshacer esta ejecución»** borra solo los puntos de esa
   ejecución, sin tocar el resto de la visita.
6. Para enviar un tránsito a ExoClock, pulsa **«ExoClock…»** (ver la sección 10).

## 5. Mandos y defaults

Los mandos del día a día están en la pestaña: **banda**, **aperturas** y, en el
bloque de la serie, **agrupar tomas** (`group_n`). El resto vive en
**Avanzado…** (una ventana pequeña, no modal):

| Mando | Default | Qué hace |
|---|---|---|
| Cielo | mediana | mediana plana o plano inclinado (núcleos de galaxia) |
| Sigma-clip | sí | dos rondas de 2,5σ en el anillo de cielo |
| Apertura por seeing | sí | `r = 1,35 · FWHM` medida en las comparaciones; en serie, el FWHM de **cada toma** |
| Término de color | sí | ajusta ZP y pendiente con el B−V de las comps |
| Restar galaxia huésped | no | referencia PS1 alineada, escalada por las comps |
| **Alinear tomas** | **automático** | ver más abajo; `off` sólo si las tomas ya están alineadas |
| **Agrupar tomas** (`group_n`) | 1 | combina N tomas por punto en el dominio de la medida; nunca apila píxeles; también hay un control rápido en el bloque de serie |
| **Detrend** | apagado (variable/HADS: masa de aire) | `airmass` quita el mínimo; `auto` añade FWHM/cielo/x-y solo si mejora |
| **Barrido de apertura por noche (T3)** | no | elige la k en [1,0, 2,0]·FWHM con menos dispersión de la check |
| **Techo de saturación** | 0 = auto | valor absoluto en ADU; 0 usa la tarjeta SATURATE o Ajustes |

Cada control tiene su tooltip con unidades y razón, y hay **«Restaurar
valores»**.

### 5.1 Alinear las tomas (importante)

**Las tomas de una visita casi nunca caen en los mismos píxeles.** El telescopio
deriva (desalineación polar, refracción, guiado), y una toma puede llevar un
dithering. Si el motor mide siempre donde decía la placa de referencia, la estrella
**sale de la apertura**: en la serie real de V0526 Per (244 tomas de 40 s) el campo
se movió 134" en 2,9 h y la curva pasó de 13,4 a 17,4 magnitudes, con errores de
0,5 mag. Eso ya no pasa: `align="auto"` viene encendido y hace esto:

1. quita el cielo de cada toma (medianas por bloques) para no confundir el viñeteo
   con la señal;
2. **las estrellas votan la transformación**: para cada rotación candidata, cada par
   de estrellas propone una traslación y gana la que más pares independientes
   confirman; primero se prueba una **traslación pura** y sólo si no basta se ajusta
   la rotación;
3. mide cada toma **en su rejilla nativa** con la WCS compuesta (`coords`), así que
   la PSF **nunca se remuestrea**;
4. **verifica** la transformación con las estrellas que ha emparejado: la calidad es
   el número de pares y su rms en píxeles, no un número mágico de correlación.

Si una toma no se puede verificar, **hereda la alineación anterior y se marca**
(`align_failed`): nunca se mide con una suposición. El panel de resumen lo cuenta
todo en lenguaje llano: cuántas tomas se alinearon, cuánto se movió la imagen (px y
minutos de arco), el residuo de las estrellas y las tomas sin verificar.

Alinear cuesta unos 0,15 s por toma (un 2 % del total) y se puede apagar en
**Avanzado… → Alinear tomas** si tus tomas ya vienen alineadas (por ejemplo, si
todas traen WCS propia).

### 5.2 Las comparaciones: el punto cero se ata por estrella

El valor de catálogo de una comparada puede estar equivocado (en estrellas muy rojas
el V derivado de Gaia se desvía hasta 0,9 mag) y, además, con la deriva una comp
**entra y sale del marco** o se satura. La mediana de las que quedan saltaba de una
toma a otra; ahora cada comparada mide su **propio nivel** sobre la serie completa y
el punto cero deja de depender de cuáles estaban presentes. La estrella de
**chequeo nunca entra en el punto cero** (es el monitor). El panel te avisa si las
comparadas no coinciden entre sí y de las que no han entrado en casi ningún frame:
eso suele querer decir que hay que rehacer la secuencia con estrellas más cercanas
al objetivo y de brillo parecido.

Y la secuencia que la app propone ya no sale del catálogo a ciegas: cada candidata se
**mide en tu propia placa** y se descarta con su motivo (saturada, por encima de la
linealidad de la cámara, fuera del rectángulo real del sensor, o demasiado débil).
El campo es el rectángulo del sensor, no un cuadrado, y lleva un anillo de seguridad
para que la deriva de la noche no se lleve una comp del borde.

### 5.3 Ganancia y ruido de lectura: o el error no es el del CCD

Sin ganancia, el error de un punto es la dispersión de las comparadas, no la ecuación
del CCD (en la serie de V0526 Per, 0.17 mag en lugar de 0.005). Los dos campos están
en **Ajustes → perfil de cámara**: el ruido de lectura se precarga del preset (es un
dato de datasheet) y la ganancia no, porque depende de la unidad y del ajuste. Si no
la pones, el motor **la mide en tus propias tomas** (dos tomas a la misma exposición
bastan) y lo dice en el panel, con su incertidumbre y su origen; nunca la escribe en
Ajustes por su cuenta.

### 5.4 La escala de la gráfica

El eje de magnitud sigue el **núcleo** de la curva (mediana ± 6 sigmas robustas), no
el mínimo y el máximo, así un punto anómalo no aplasta el resto; los que caen fuera
siguen en la gráfica anclados al borde. La rueda acerca, el botón izquierdo arrastra
y **Ajustar** vuelve al panel. Los botones **Robusta**, **Errores** y **Ocultar
marcados** están sobre la curva del bloque de serie: «Errores» dibuja el error de
fotones de cada punto y la **banda** del sistemático de calibración (el punto cero es
de toda la noche: como banda, nunca como una barra por punto).

**Marcados: dos clases.** Una bandera de **dato** (saturado, rayo cósmico,
desenfoque, nube, toma sin alinear) sale como rombo hueco. Un **aviso** de
calibración (pocas comparsas, punto cero prestado) es el marcador normal con un borde
ámbar tenue: la curva no está mal, su calibración se apoya en pocas estrellas.

**El color de cada punto es un código** (botón **Colores de calidad**, activado por
defecto): **verde** cuando el punto está limpio (error hasta 0,05, más de tres
comparsas sosteniendo el punto cero), **naranja** cuando es usable pero no limpio
(comparsas escasas, un error hasta 0,15) y **rojo** cuando sus datos están en duda.
La **forma** sigue diciendo qué decisión se tomó; el color dice cuán buena es la
medida. Apagado, vuelven los colores de filtro. La banda de la placa y el panel de la
medida llevan el mismo código, con los mismos umbrales: mira
[la guía del editor](UFE.es.md).

### 5.5 El desenfoque no es una nube

Si la FWHM de una toma se sale del rango robusto de su noche, el punto se marca
**`seeing`** (desenfoque, un rastro o un satélite en el núcleo) y no `cloud`: una
nube mueve el cielo y el punto cero **sin** cambiar la PSF, un desenfoque cambia la
PSF y deja el cielo quieto. Con «la apertura sigue el seeing» encendida (por
defecto), los radios que eliges son los de la FWHM de referencia y cada toma los
escala por la suya, así que el flujo que se iba fuera de la apertura vuelve: en la
serie real, la toma desenfocada pasa de desviarse 0.049 a 0.017 mag.

El **perfil de cámara** (Ajustes → Perfil de cámara fotométrica) fija el
**full well, la corriente de oscuridad y el límite de linealidad / tope de
exposición por ganancia** (mídelos; hay un valor sugerido). En un sCMOS muy
sensible (QHY42Pro/GSENSE400) la receta es **exposiciones de 5–10 s y agrupar**
(`group_n`) para bajar el centelleo sin saturar ni ahogar en fondo; los IMX
modernos y los CCD admiten exposiciones largas. El **límite de linealidad** es
lo que decide qué estrellas valen como comp/check.

### 5.6 Los dos PNG, y qué necesitan las figuras de la noche

La puerta **Serie ▾** del bloque de serie lleva dos exportaciones:

* **Guardar la carta en la visita (PNG)…** escribe la curva **tal como la ves** (la
  ventana a la que has acercado, los puntos que has seleccionado o excluido, el rango
  fijo): lo que está en pantalla es lo que va al fichero. Funciona también con la
  curva de la visita, la que se carga del proyecto sin volver a medir nada.
* **Condiciones de la noche (PNG)…** escribe las dos figuras que explican la noche,
  la **masa de aire** y la **posición** medida (la deriva), y las abre. Se hacen de
  campos que viajan CON cada punto (masa de aire, x, y, fwhm, cielo), así que una
  curva leída de la base puede dibujar su noche meses después. Un punto medido antes
  de que la app los guardara no tiene masa de aire que dibujar, y el botón lo dice
  exactamente en vez de callarse: vuelve a medir la serie y las figuras están.

## 6. Cuándo fiarse

- **La cruda siempre está visible** junto a la detrendada: el detrend puede
  comerse señal, y verlo es la única defensa.
- **Errores honestos**: el error total nunca es menor que el interno (fotones);
  incluye el punto cero, el centelleo y el residuo de flats. Si falta la
  ganancia, el panel lo dice.
- **Puntos marcados** (rombo): saturación, salto de guiado, rayo cósmico, nube
  o punto cero desplazado. No se borran; se pueden desestimar al analizar.
- **Semáforo**: el aviso de cadencia y el de multinoche (banda mezclada, punto
  cero desplazado) hablan en lenguaje llano; en rojo, el ingress de un tránsito
  se pierde.

## 7. Multinoche

Cada noche es **una ejecución** con su `run_id` y su Undo. La curva del proyecto
las agrega. El detrend se ajusta **por noche** (coeficientes locales), con
fallback a solo escala en noches cortas o sin rango de aire. Si mezclas
filtros, la guardia de banda avisa: no se combinan en una sola curva de
magnitudes. Un punto cero desplazado se **marca**, nunca se calla.

### 7.1 Una serie de varias noches, en UNA pasada

Una variable que sigues toda la campaña se mide **de una vez**, no noche a
noche. En el bloque de serie, junto al contador de tomas, está el selector
**«this visit» / «all visits»**: solo aparece si el proyecto tiene más de una
visita con tomas.

Con **«all visits»** el motor recibe las tomas de **todas las visitas** (en
orden de tiempo) y las mide como una sola serie. El resultado se archiva
**una ejecución por visita**, porque una visita es una noche y cada punto
pertenece a la noche en que se tomó: así la curva de cada visita es la suya y
la del proyecto es la unión de las noches, una pasada por noche, que es lo que
necesita el plegado del período. Las noches no se mezclan en la calibración:
el punto cero, el detrend y el control de calidad son **por noche**, como
siempre.

La pasada entera es **una sola cosa** para deshacer: el botón Undo quita las
noches de esa pasada de un clic (las ejecuciones quedan marcadas como
deshechas, el rastro no se calla). En la puerta **Serie ▾ → Pasadas de esta
visita…** cada noche de una pasada dice a cuál pertenece («parte de una pasada
de 3 noches»).

El **modo en vivo** sigue siendo de una visita: vigila la carpeta de hoy. Con
«all visits» se apaga y lo dice, porque vigilar varias carpetas a la vez es
otra cosa. Y **descartar la curva** también es por visita: con «all visits» se
deshabilita y dice que abras la visita cuya curva quieres deshacer.

### 7.2 Una visita es UNA curva (y las demás pasadas siguen ahí)

**Un fotograma, una medida.** Una curva nunca enseña el mismo fotograma dos
veces: enseña su medida **más reciente**. Si vuelves a medir la noche entera,
la pasada nueva sustituye a la vieja; si mides solo una parte, el resto se
queda como estaba y la noche sigue siendo **una** curva. Medido en tu propia
base: las 244 tomas de la visita 18 estaban medidas otra vez como visitas 20
(35 tomas) y 21 (3), todas dentro de las 244, así que la unión tenía 282
puntos con 38 duplicados a dos niveles; ahora son 244.

La **curva de la visita** es la pasada que la visita muestra (la puerta de
pasadas): esa pasada manda en SUS fotogramas, y los que no cubre se rellenan
con su medida más reciente. La **curva del proyecto** es la unión objetiva:
un punto por fotograma, su medida más reciente, sin que la elección de una
visita cambie lo que ve otra. Por eso la gráfica de una visita puede enseñar
una pasada y la del proyecto el conjunto: la primera es la vista de trabajo
(«¿qué pasada estoy mirando?»), la segunda es la ciencia.

Una visita puede tener **varias pasadas**: vuelves a medir la serie con otra
banda, con otra secuencia, o solo para comprobar algo. Cada pasada guarda sus
puntos y no se borra ninguna, pero **la gráfica de la visita dibuja una sola**,
la que la visita tiene marcada. Medir otra vez hace que la nueva pasada sea la
curva (es lo que acabas de medir, y es lo que estabas viendo en vivo); las
anteriores **no se dibujan**, y si se dibujaran todas a la vez verías la curva
duplicada a dos niveles distintos unidos por un zigzag.

Para volver a una pasada anterior: **Serie ▾ → Pasadas de esta visita…**. Ahí
están todas, con su hora, su banda, sus puntos, el tramo de noche que cubren y
su estado, y la que la gráfica muestra marcada en negrita. Dos acciones por
fila:

* **Que sea la curva**: la gráfica dibuja esa pasada. **No se borra nada** y no
  se mide nada otra vez.
* **Deshacer esta pasada**: sus puntos se van, la fila queda marcada como
  deshecha y la gráfica cae a la pasada anterior. Las tomas no se tocan.

Deshacer la última pasada **recupera la anterior**, que es justo lo que
esperas de un Undo. Y el panel de la visita lo dice en voz alta: qué pasada
está dibujando y cuántas más guarda (con sus puntos), para que no haya una
lista de pasadas secreta.

El mismo criterio vale para la curva del **proyecto**: agrega las noches, y de
cada noche toma una sola pasada (la que la visita marca, o la última medida).
Una noche medida cinco veces cuenta una vez.

## 8. Cuándo NO hace falta serie

Un **punto suelto** (por ejemplo una SN entre otras observaciones) es una
acción de **una sola placa**: mide con la pestaña Fotometría y guarda el punto;
el motor de serie solo arranca con dos o más tomas.

## 9. El período: buscarlo, plegarlo y contar lo que no se sabe

Cuando la curva ya está medida, el siguiente paso es saber **cuál es su período**.
Se abre desde dos sitios: el botón **«Período y fase…»** de la ventana de la visita
(pestaña Análisis) y el del bloque de la serie en la pestaña Medir del editor. La
ventana trabaja sobre la curva del **proyecto** (todas las visitas, venga de donde
venga cada punto).

- **Métodos**: Lomb-Scargle generalizado (con media flotante: no hay que centrar
  nada y pondera por el error de cada punto) y **PDM** (minimización de la
  dispersión de fase), que no supone forma y es la contraprueba honesta para una
  eclipsante o una variable de tipo sierra. **«Ambos»** los corre y te dice si
  coinciden.
- **Qué se ve**: el periodograma con el pico marcado y los niveles de **FAP**
  (líneas discontinuas, obtenidos barajando las magnitudes de tus propios datos), y
  la **curva plegada a dos ciclos con un color por noche**, con barras de error y
  media binneada.
- **Lo que la herramienta dice, y es lo importante**:
  - **ciclos cubiertos**: si la línea base no llega a dos ciclos, el período **no
    está fijado**. Una noche de 3 h de una variable de 0,127 d es un ciclo: el
    periodograma enseñará un pico, pero cualquier pico de ahí es tan bueno como un
    alias. La solución es otra noche o fotometría de la comunidad.
  - **FAP**: por debajo de 0,01 es una detección seria; por encima, puede ser ruido.
  - **la ventana espectral**: si tu patrón de observación tiene un pico justo en el
    período encontrado (el clásico alias de un día), el aviso lo dice.
  - **desacuerdo entre métodos**: si Lomb-Scargle y PDM dan períodos distintos, una
    de las dos está viendo un armónico o un alias.
- **Guardar**: el botón «Guardar el período en el proyecto» escribe el período (con
  su método, su FAP y sus ciclos) en el proyecto, y la curva del proyecto se plega
  por él. Sólo se guarda si tú lo pides y sólo si hay período.
- **Exportar**: PNG del informe (como el de PerWin/PhaseWin, con los dos paneles) y
  un CSV con el periodograma completo y la curva plegada.
- **La curva de la comunidad**: «Añadir la curva de la comunidad…» trae las
  observaciones AAVSO de la estrella (necesita el token de la API en Ajustes) y las
  pliega **con** las tuyas, en gris y huecas, nunca mezcladas. Así una noche deja de
  ser toda la historia, y así se hizo el informe de referencia.
- **Robustez**: «Dejar fuera los puntos marcados» (encendido) evita que un punto cuyo
  dato está en duda guíe el periodograma, y «Descartar atípicos» pliega la curva con
  el período de la primera pasada y quita lo que se sale de su propio bin de fase,
  diciendo cuántos.

Ejemplo real: la serie de **V0526 Per** (244 tomas, 2,9 h) da un pico en 0,134 d con
FAP 0,016 y **1,0 ciclos cubiertos**. El informe del observador, con varias noches y
ASASSN, da 0,12695 d: la herramienta no lo contradice, dice exactamente lo que puede
decir con una noche.

## 10. Modo en vivo

**Opcional y apagado por defecto.** Activa **«En vivo (vigilar la carpeta)»** en
el bloque de serie: un vigilante ligero observa la carpeta de la visita, detecta
las tomas nuevas (espera a que el fichero deje de crecer, nunca lee uno a
medias), las mide con el mismo motor y actualiza la curva cada pocas tomas. Los
ficheros en vivo **no necesitan astrometría**: la placa de referencia siembra
el objetivo y las comparaciones.

## 11. ExoClock (envío manual)

NightScribe **no sube** a ExoClock: prepara los dos ficheros y abre la página de
subida en el navegador.

- **Datos**: texto de **3 columnas**: JD_UTC del **arranque** de la exposición,
  flujo relativo (el objetivo sobre la media de las comparaciones) y su error.
- **`ExoClock_info.txt`**: planeta, formato de tiempo (JD_UTC), sello (Exposure
  start), formato de flujo (Flux), filtro, tiempo de exposición y un campo
  **Comments** relleno con tu autoevaluación.
- Un punto **sin tiempo de exposición** no se puede exportar: el arranque sería
  mentira.
- Antes del botón hay un **checklist** (línea base a cada lado, puntos por
  ingress, sin flags rojos, dip coherente). Avisa, no bloquea.
- Al confirmar, el proyecto registra el outcome **`reported_exoclock`**.

## 12. Reducción externa con EXOTIC

Para un tránsito con pretensión científica, la reducción y el ajuste los hace
**EXOTIC** (NASA/JPL), que NightScribe **orquesta** como herramienta externa (no
lo embebe). Es la vía principal; la serie numpy del bloque de fotometría queda
como **previsualización** rápida.

1. **Prepara el entorno** una vez en **Ajustes → EXOTIC**: indica un intérprete
   **Python ≤ 3.10** (o deja que lo detecte) y pulsa **«Preparar entorno»**; crea
   un entorno privado e instala EXOTIC (necesita red la primera vez). **«Probar»**
   comprueba que importa.
2. En el proyecto de tránsito, **Análisis → «Reducir y ajustar con EXOTIC…»**:
   la app escribe el `inits.json` de la visita (tomas, objetivo y comparaciones
   en píxeles), ejecuta EXOTIC en modo headless con el log a la vista (puedes
   cancelar) e **importa su curva y sus parámetros** (T_mid, Rp/Rs, profundidad,
   inclinación, duración) al proyecto. La curva entra como puntos «exotic» y se
   ve en la gráfica como cualquier otra.
3. Después, sube el resultado a ExoClock con **«ExoClock…»** (o a la AAVSO
   Exoplanet Database).

Sin entorno EXOTIC, el botón manual **«Exportar a EXOTIC (inits.json)…»** sigue
disponible para reducir fuera y volver. La primera ejecución de EXOTIC necesita
red (NASA Archive, datos de limb darkening, astrometry.net).

### Prueba real de punta a punta

Requisitos: un proyecto de tránsito, una visita con las tomas de la noche, una
secuencia de comparación y el entorno EXOTIC preparado.

1. **Entorno**: Ajustes → EXOTIC (reducción de tránsitos) → indica un **Python
   ≤ 3.10** → **«Preparar entorno»** → **«Probar»** (debe responder
   `EXOTIC 4.3.x`). Guarda.
2. **Visita**: abre la visita del tránsito y adjunta las tomas («Attach
   files…»). La app necesita la astrometría de la primera toma: si falta, la
   resuelve sola con el solver configurado (ASTAP local o nova, ADR-051) y
   **guarda la WCS en el propio FITS**, así queda resuelta para cualquier
   programa. Ya no se piden píxeles a mano.
3. **Secuencia**: ábrela en el editor (el acceso de Análisis abre la visita
   ahí) y confirma las comparaciones; con el navegador de tomas del panel
   izquierdo puedes recorrer la visita, y **la toma abierta es la referencia**.
4. **Reducir**: en el editor, **«Reduce and fit with EXOTIC…»** del panel
   izquierdo (o Análisis → «Abrir la visita en el editor…»), y sigue el log.
   Puede tardar; no cierres la app (puedes cancelar).
5. **Resultado**: aviso con **T_mid** y **Rp/Rs**; la curva «exotic» aparece en
   la gráfica; quedan el `inits.json` y el reporte en el proyecto, y la figura
   `FinalLightCurve_*.png` en la carpeta de trabajo.
6. **Verificar**: T_mid a 3σ, Rp/Rs al 5 % y profundidad al 10 % frente a la
   referencia. Después, **«ExoClock…»** para subir el tránsito.

La **primera ejecución** de EXOTIC necesita red (NASA Archive, datos de limb
darkening, astrometry.net). Sin entorno EXOTIC, el botón manual **«Exportar a
EXOTIC (inits.json)…»** sigue disponible.

**En Windows (lo más limpio)**: instala **Python 3.10** desde python.org (marca
el *py launcher*) y ejecuta `pip install exotic` en él; luego apunta la app a
ese intérprete (Ajustes → EXOTIC; la app también lo detecta con el lanzador `py
-3.10`). El botón **«Preparar entorno»** es opcional y crea un entorno privado
por ti si lo prefieres. Algunas dependencias de EXOTIC podrían no traer rueda
para Windows; si el `pip install` falla, la app muestra el error y la serie
numpy sigue funcionando.

## 13. Solución de problemas

- **«No hay visita con tomas»**: abre el editor desde una visita; no desde el
  menú Herramientas suelto.
- **«No hay secuencia de comparación»**: constrúyela en la mitad superior de la
  pestaña Fotometría.
- **«Mide el objetivo una vez»**: un clic sobre el objetivo (o abre desde la
  ficha con coordenadas).
- **Tránsito que no cuadra**: revisa saturación de las comps, el techo, y que no
  haya mezcla de filtros; mira la cruda y la detrendada por separado.
- **Frames que se desplazan o rotan y no traen WCS**: la serie se mide en
  coordenadas fijas sobre la placa de referencia; si el campo se mueve mucho,
  los puntos se marcan (`guide_jump`). La alineación por frame está disponible
  como opción avanzada.

## 14. Glosario y enlaces

- **ZP**: punto cero; la diferencia entre la magnitud instrumental y la de
  catálogo de las comparaciones.
- **Ensemble**: el conjunto de comparaciones combinado (media ponderada con
  veto robusto).
- **Detrend**: quitar de la curva una tendencia (masa de aire, etc.); su
  modelo es `a1·exp(a2·X)+a3`.
- **Ingress**: la entrada del tránsito; resolverlo pide varios puntos.
- **Run / ejecución**: una pulsación de «Medir la secuencia», con su Undo.

Enlaces: [PHOTOMETRY.es.md](PHOTOMETRY.es.md) (prácticas),
[PRECISION.es.md](PRECISION.es.md) (calidad y números),
[WORKFLOWS.es.md](WORKFLOWS.es.md) (flujo de proyecto),
ADR-048 (serie), ADR-049 (ExoClock), ADR-050 (en vivo), ADR-051 (solver local),
ADR-052 (orquestación de EXOTIC).
