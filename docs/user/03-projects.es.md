# 03. Proyectos

Un **proyecto** es la unidad de trabajo de NightScribe: un objeto concreto
que quieres observar, con su carpeta, sus visitas, sus medidas y su
resultado. Todo lo que haces con él (capturas, curvas de luz, reportes,
posts) cuelga del proyecto, así que semanas después puedes retomarlo sin
reconstruir nada.

## Crear un proyecto

Tres caminos, y todos llevan a la vista **Esta noche** (capítulo 02):

- **+ NUEVO PROYECTO**, en la cabecera de la ventana.
- **Crea un proyecto desde los objetivos de esta noche**, en el panel de
  noche de **Mis proyectos**.
- **+ Nuevo proyecto…**, en la lista de proyectos.

Desde la vista Esta noche eliges el objetivo (una tarjeta de las sugeridas,
una fila de la tabla, o la barra de búsqueda con **Crear a mano…** para lo
que no esté en catálogo, como una variable de tu programa propio). El
proyecto nace con todo lo que la app ya sabe: coordenadas, ventana de
visibilidad, magnitud y plan de exposición.

## Los cuatro pasos

Cada proyecto se recorre en cuatro pasos guiados; la app te dice cuál toca y
el botón **Ir →** te lleva a la herramienta exacta:

1. **Ficha**: qué es el objeto y por qué importa. Parámetros orbitales y
   físicos traducidos a lenguaje claro, visibilidad desde tu sitio y
   recomendaciones de observación (exposición máxima antes de que un NEO se
   mueva, por ejemplo).
2. **Captura**: lanzar las tomas (directamente sobre CCDciel, capítulo 05) o
   registrar las que ya hiciste.
3. **Análisis**: aquí viven las **visitas** (cada noche de observación es una
   visita) y sus recursos: las placas FITS, la fotometría, la astrometría, la
   carta de comparación. Los capítulos 06 y 07 entran en detalle.
4. **Publicación**: el borrador bilingüe del post y los gráficos
   (capítulo 08).

Cuando un paso está completo, **✔ Marcar hecho** lo marca y el proyecto avanza.

> **¿Por qué pasos y no un cajón de herramientas?** Porque el orden importa:
> medir fotometría antes de calibrar da números bonitos y falsos. Los pasos
> no te encierran (puedes abrir cualquier herramienta cuando quieras), pero
> hacen difícil saltarse la física por accidente.

## La lista de proyectos

En **Mis proyectos** tienes búsqueda, filtros por tipo/etiqueta/campaña y
tres vistas: **Activos**, **Terminados** y **Archivados**. Dos detalles que
usarás a diario:

- **☆ Favoritos**: fija arriba lo que estás siguiendo de cerca.
- **«Te necesita»**: el panel de entrada resume qué proyectos te necesitan y
  por qué («llevas 5 días sin medir esta variable y su período es de 0,3
  días», «esta SN se está apagando: última foto útil esta semana»).

> **¿Por qué un panel de «atención»?** Porque el seguimiento científico es un
> problema de cadencia, no de memoria: una curva de luz con huecos en el sitio
> equivocado pierde el período o el máximo. El panel calcula en local, sin
> red, qué proyecto pierde valor por cada día que pasa, y te lo pone delante
> antes de que decidas la noche.

## Los tipos de objetivo, en una frase

- **NEO**: asteroide o cometa cercano a la Tierra; el valor está en la
  astrometría para su órbita (capítulo 07).
- **PCCP**: candidato de la página de confirmación del MPC; tu medida puede
  ser la que lo confirme.
- **Cometa**: seguimiento de actividad y magnitud real frente a la predicha.
- **Supernova**: curva de luz contra las plantillas de su tipo y blink de
  confirmación contra la imagen de referencia.
- **Tránsito de exoplaneta**: curva del tránsito; NightScribe prepara el
  pase a EXOTIC y el envío a ExoClock.
- **Variable** (incluidas las **HADS**, δ Scuti de alta amplitud): series
  fotométricas, búsqueda de período y curva plegada.
- **Alerta**: objetivos de ocasión (outbursts, llamadas de la AAVSO).

## El diario de observación

**Herramientas → Diario de observación…** muestra tu historial por noches: qué
observaste, cuántas tomas, con qué filtro, y qué salió de ello. Se construye
solo a partir de tus proyectos y visitas: la noche que capturaste algo
grande queda escrita aunque se te olvide apuntarla.

Siguiente: [04. Campañas y vigilias](04-campaigns.es.md).
