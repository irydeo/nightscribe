# 00. Conceptos

Este es el mapa. El resto de la guía se apoya en cinco palabras que NightScribe
repite en cada pantalla: **proyecto**, **visita**, **run**, **serie** y
**reporte**. Están anidadas, una dentro de la siguiente, y saber cuál es cuál
es lo que hace predecibles los botones. Lee este capítulo una vez; los demás
caerán sobre terreno firme.

## La jerarquía de un vistazo

```
proyecto (un objeto que sigues)
└── visita (una noche de observación, con fecha y un nombre opcional)
    ├── run de astrometría     -> reporte MPC
    └── serie fotométrica      -> reporte CSV / AAVSO, curva de luz
reporte / exportación: lo que sale de la app
```

| Palabra | Qué es | Qué cuelga de ella |
|---|---|---|
| **Proyecto** | Un objeto que sigues | Su carpeta, sus visitas, su curva de luz, su resultado |
| **Visita** | Una noche de observación de ese proyecto | Las placas de la noche y todo lo que produjo |
| **Run de astrometría** | Una pasada de track & stack sobre los frames de una visita | Sus puntos medidos, sus apilados, su reporte MPC, su deshacer |
| **Serie fotométrica** | La medida frame a frame de una visita | La curva de la visita y, unida a las demás visitas, la curva de luz del proyecto |
| **Reporte / exportación** | Lo que sale de la app | Reporte MPC, reporte CSV y AAVSO, FITS anotado, gráficos, posts |

> **¿Por qué una jerarquía y no un montón de ficheros?** Porque un proyecto de
> observación es una historia en el tiempo, no una carpeta: el mismo objeto se
> visita noche tras noche, cada noche produce sus placas y sus medidas, y el
> resultado es la unión de todas. La jerarquía es lo que permite a la app
> reconstruir la historia (qué noche, qué pasada, qué curva) sin que tú
> recuerdes nombres de fichero.

## Proyecto

Un **proyecto** es un objeto que sigues, con su carpeta, sus visitas, sus
medidas y su resultado. Todo lo que haces con ese objeto (capturas, curva de
luz, reportes, posts) cuelga del proyecto, así que semanas después lo retomas
sin reconstruir nada. El capítulo [03. Proyectos](03-projects.es.md) enseña a
crearlos; aquí basta con saber que el proyecto es la caja más ancha.

## Visita

Una **visita** es una noche de observación de ese proyecto. Todo lo
que produjo la noche cuelga de la visita: las placas FITS, la fotometría
importada, las efemérides, los reportes, los gráficos, las notas. Mantener la
noche como su propia caja es lo que permite a la app enseñarte «qué salió de
una noche concreta» sin que ordenes ficheros a mano.

Una visita tiene una **fecha**, que es su carpeta y su clave de orden, y, desde
el 2026-10-16, un **nombre** propio opcional. La fecha sigue siendo la
identidad; el nombre es para el observador. Es útil cuando trabajas el mismo
proyecto dos veces en un día, o cuando una sesión se alarga pasada la
medianoche y la fecha del calendario no es la que tú llamarías esa noche.

## Run de astrometría

Un **run de astrometría** es una ejecución de track & stack sobre los frames de
una visita. Tiene sus propios puntos medidos, sus propios ficheros
apilados, su reporte y su deshacer, así que un run es un resultado
autocontenido y no un borrador.

Una visita puede tener varios runs: varias pasadas en una noche, cada una con
su apilado. El botón **Medir la posición…** de la propia visita abre el
último, así que lo normal es un clic. Cuando la visita ya tiene un run, abrir
ese run muestra su reporte MPC ya reconstruido a partir de sus medidas
(2026-10-16): reabres una noche para enviarla, no para medirla otra vez. El
capítulo [07. Astrometría](07-astrometry.es.md) entra en detalle.

## Serie fotométrica

La **serie fotométrica** es el equivalente para los objetos que varían.
**Medir la secuencia** mide todos los frames de la visita frame a frame, con un
cero de punto por frame, flags de calidad y un deshacer por run. La serie se
convierte en la curva de la visita y, unida a las demás visitas, en la curva de
luz del proyecto. El capítulo [06. Fotometría](06-photometry.es.md) entra en
detalle.

## Reporte y exportación

Un **reporte o exportación** es lo que sale de la app: el reporte MPC de un
run, el reporte CSV y AAVSO de una serie, el FITS anotado, los gráficos y los
posts. Nada sale por su cuenta; cada uno es un gesto deliberado, y la app te
enseña la figura o el texto antes de que salga. El capítulo
[08. Contarlo](08-posts.es.md) cubre el último de ellos.

## Dentro de un proyecto: las carpetas

Dos carpetas de orden viven dentro de un proyecto, y existen para que el disco
no mienta:

- `prcd/`: los frames de un run con éxito, apartados para devolver disco.
  Nunca se borran y los puedes traer de vuelta cuando quieras. Antes se llamaba
  `procesados/`; renombrada el 2026-10-16.
- `dscrd/`: los frames que sacas de una noche. Mover un frame ahí es un
  movimiento real, y el registro lo sigue, así que no se pierde nada. Antes se
  llamaba `descartados/`; renombrada el 2026-10-16.

## La biblioteca de masters de calibración

La calibración usa una **biblioteca de masters** que se indexa, no se copia
(capítulo [05. Captura](05-capture.es.md)): señalas tus FITS maestros y la app
lee de sus cabeceras lo que los hace válidos (cámara, ganancia, temperatura,
exposición, filtro). La regla de propiedad es sencilla: un master pertenece a
un proyecto, pero los reutilizables (bias, flat) se pueden compartir con todos
los proyectos, y el master de otro proyecto se puede usar sin copiarlo. Así un
buen flat sirve para todo el observatorio.

## El editor FITS unificado

El **editor FITS** (**Herramientas → NightScribe Image Workbench**) es la
puerta única a todo el trabajo con FITS. **Fotometría** y **Astrometría** son
sus pestañas, y **Blink**, **Calibración** y **Anotar** se abren como ventanas
sobre la misma placa, con el mismo zoom y el mismo estirado. Abrirlo desde una
visita ya trae los frames de esa visita. Una placa que lleva astrometría se
abre **con el norte arriba** por defecto, como muestran el cielo las cartas y
las pantallas de adquisición; el interruptor de Configuración lo puede
desactivar.

## Por dónde seguir

Las cinco palabras abren el resto de la guía:

- [03. Proyectos](03-projects.es.md): el proyecto completo, de la ficha a la
  publicación.
- [05. Captura](05-capture.es.md): los frames de la visita y la biblioteca de
  masters.
- [06. Fotometría](06-photometry.es.md): la serie, la curva de luz y los
  períodos.
- [07. Astrometría](07-astrometry.es.md): el run, el apilado y el reporte MPC.
- [08. Contarlo](08-posts.es.md): los posts y los gráficos.
- [13. Entender un objeto](13-object-card.es.md): qué significa cada tipo y
  cada cifra. Las taxonomías y las magnitudes se explican una sola vez, en la
  ficha del objeto; ningún capítulo las repite.

Siguiente: [01. Primeros pasos](01-getting-started.es.md).
