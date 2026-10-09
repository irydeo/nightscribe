# 08. Contarlo

La última misión de NightScribe es que tu observación no se quede en el
disco duro: genera los borradores para contarla, en español y en inglés, con
los datos reales de tu sesión.

## El borrador

En el paso **Publicación** de un proyecto, **Generar** enriquece el objeto (sus
datos orbitales, físicos y de contexto) y construye tres piezas:

- **ES**: el post en español, con el gancho divulgativo, los hechos clave en
  viñetas y los hashtags (incluido tu código MPC, si lo tienes).
- **EN**: el mismo post en inglés.
- **X**: la versión corta para la red del pajarito, dentro del límite de
  caracteres.

Cada pieza tiene su botón **Copiar**; eliges la carpeta de salida con
**Examinar…** si quieres guardarlas en fichero junto a los gráficos. El borrador
se escribe en la propia página, sin ventanas que abrir; mientras trabaja, una
barra de progreso te dice que sigue, porque una generación con IA puede tardar
un par de minutos con un modelo que «piensa».

> **¿Por qué un borrador y no un post publicable?** Porque la voz es tuya.
> NightScribe pone los datos correctos (la distancia, el tamaño, la frase de
> «por qué importa») para que tú no tengas que buscarlos, pero el tono, la
> foto y el remate final son los de tu observatorio. Edita sin miedo: el
> borrador se regenera cuando quieras.

## Escribir con IA (opcional, experimental)

Si configuras un modelo de lenguaje en **Ajustes → Integraciones** (un servicio
compatible con OpenAI, en la nube o en tu propia máquina), el paso Publicación
gana dos botones. Es una parte **experimental** de la app: depende de un modelo
externo que tú conectas y puede cambiar; la plantilla de siempre es la
respuesta estable:

- **Redactar con IA…**: redacta el borrador a partir de **todo** lo que la app
  sabe del proyecto: el objeto con sus parámetros explicados, la noche
  planificada, tus visitas, las magnitudes medidas y el veredicto de la campaña.
- **Qué se enviará…**: muestra la ficha exacta que leería el modelo, para que
  veas qué saldría de tu equipo antes de que salga.

La IA solo frasea: no mide, no clasifica y no inventa ninguna cifra. Todo lo que
dice sale del dossier, y lo que no está no lo menciona. El borrador sigue siendo
tuyo: revísalo antes de publicar.

> **¿Por qué apagada por defecto?** Porque la app funciona igual sin ella: la
> plantilla de siempre sigue ahí y no necesita red. Con la IA apagada, los
> botones de IA quedan deshabilitados y el post lo escribe la plantilla. Con un
> servidor local (por ejemplo Ollama) nada sale de tu equipo; con uno en la
> nube, el coste y la privacidad son los de ese servicio.

## Los gráficos

Junto al texto, NightScribe genera los PNG listos para adjuntar: la órbita,
la carta del cielo, la vista de la noche, la curva de luz (con las
plantillas de supernova de fondo cuando aplica), el blink de confirmación o
la animación del movimiento de un NEO. Siguen el idioma de la interfaz.

> **¿Por qué el blink es la «prueba de fuego»?** Porque en divulgación de
> transitorios la credibilidad lo es todo: una animación donde tu objeto se
> mueve (o parpadea) contra el fondo fijo de estrellas demuestra en dos
> segundos que hay algo ahí, sin una sola ecuación. Es la imagen que convierte
> un «lo he visto» en un «míralo».

Y con esto, el ciclo se cierra: del objetivo de la tarde al post de la
mañana siguiente. El apéndice [09. La línea de comandos](09-cli.es.md)
resume cómo hacer todo esto sin abrir la ventana.
