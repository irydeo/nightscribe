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
| Apertura por seeing | sí | `r = 1,35 · FWHM` medida en las comparaciones |
| Término de color | sí | ajusta ZP y pendiente con el B−V de las comps |
| Restar galaxia huésped | no | referencia PS1 alineada, escalada por las comps |
| **Agrupar tomas** (`group_n`) | 1 | combina N tomas por punto en el dominio de la medida; nunca apila píxeles; también hay un control rápido en el bloque de serie |
| **Detrend** | apagado | `airmass` quita el mínimo; `auto` añade FWHM/cielo/x-y solo si mejora |
| **Barrido de apertura por noche (T3)** | no | elige la k en [1,0, 2,0]·FWHM con menos dispersión de la check |
| **Techo de saturación** | 0 = auto | valor absoluto en ADU; 0 usa la tarjeta SATURATE o Ajustes |

Cada control tiene su tooltip con unidades y razón, y hay **«Restaurar
valores»**.

El **perfil de cámara** (Ajustes → Perfil de cámara fotométrica) fija el
**full well, la corriente de oscuridad y el límite de linealidad / tope de
exposición por ganancia** (mídelos; hay un valor sugerido). En un sCMOS muy
sensible (QHY42Pro/GSENSE400) la receta es **exposiciones de 5–10 s y agrupar**
(`group_n`) para bajar el centelleo sin saturar ni ahogar en fondo; los IMX
modernos y los CCD admiten exposiciones largas. El **límite de linealidad** es
lo que decide qué estrellas valen como comp/check.

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

## 8. Cuándo NO hace falta serie

Un **punto suelto** (por ejemplo una SN entre otras observaciones) es una
acción de **una sola placa**: mide con la pestaña Fotometría y guarda el punto;
el motor de serie solo arranca con dos o más tomas.

## 9. Modo en vivo

**Opcional y apagado por defecto.** Activa **«En vivo (vigilar la carpeta)»** en
el bloque de serie: un vigilante ligero observa la carpeta de la visita, detecta
las tomas nuevas (espera a que el fichero deje de crecer, nunca lee uno a
medias), las mide con el mismo motor y actualiza la curva cada pocas tomas. Los
ficheros en vivo **no necesitan astrometría**: la placa de referencia siembra
el objetivo y las comparaciones.

## 10. ExoClock (envío manual)

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

## 11. Reducción externa con EXOTIC

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

## 12. Solución de problemas

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

## 13. Glosario y enlaces

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
