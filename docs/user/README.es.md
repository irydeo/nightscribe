# NightScribe: guía de usuario

NightScribe es una aplicación de escritorio para observatorios astronómicos
amateur que cubre el ciclo completo de un proyecto de observación:

1. **Planificar la noche**: te propone los mejores objetivos visibles desde tu
   observatorio esta noche (NEOs, cometas, candidatos del PCCP, supernovas,
   variables, tránsitos de exoplanetas), con una puntuación de 0 a 100 y la
   razón de cada propuesta.
2. **Entender cada objeto**: traduce los parámetros orbitales y físicos a
   explicaciones claras, para que sepas qué estás mirando y por qué importa.
3. **Capturar y reducir**: habla con CCDciel para lanzar tus capturas y, en su
   editor FITS, calibra, apila y mide tus imágenes: fotometría (variables,
   exoplanetas, supernovas) y astrometría de cuerpos menores lista para el MPC.
4. **Contarlo**: genera borradores bilingües (ES/EN) de posts y tuits, con
   gráficos listos para redes sociales.

> **¿Por qué existe NightScribe?** El cuello de botella de un observatorio
> amateur no es el telescopio: es decidir qué observar, reducir los datos sin
> pelearse con cinco programas y dar salida a los resultados. NightScribe une
> esas tres partes en un solo sitio, con criterio científico.

## Cómo leer esta guía

Los capítulos siguen el orden natural de una noche de observación, así que
puedes leerlos de principio a fin o saltar al que necesites:

| Capítulo | Qué encontrarás |
|----------|-----------------|
| [01. Primeros pasos](01-getting-started.es.md) | Instalación, asistente inicial y ajustes del observatorio |
| [02. Planificar la noche](02-tonight.es.md) | La vista Esta noche, la puntuación, el calendario del cielo |
| [03. Proyectos](03-projects.es.md) | Crear y seguir proyectos: de la ficha a la publicación |
| [04. Campañas y vigilias](04-campaigns.es.md) | Campañas de seguimiento y vigilias de variables |
| [05. Captura](05-capture.es.md) | CCDciel, secuencias y calibración de imágenes |
| [06. Fotometría](06-photometry.es.md) | Medir brillo, series, curvas de luz y períodos |
| [07. Astrometría](07-astrometry.es.md) | Posiciones de asteroides y cometas, y el reporte al MPC |
| [08. Contarlo](08-posts.es.md) | Posts, tuits y gráficos |
| [09. La línea de comandos](09-cli.es.md) | Apéndice: todo lo anterior desde el terminal |
| [10. Configuración](10-settings.es.md) | Apéndice de referencia: cada sección de Configuración, qué decide y cuándo tocarla |
| [11. El asistente](11-assistant.es.md) | Preguntar por el objeto, por la app o por el editor |

Convenciones:

- Los nombres de botones, pestañas y menús aparecen **en negrita** y tal cual
  los verás en la aplicación.
- Las cajas **«¿Por qué?»** explican la física o la práctica observacional
  detrás de una opción, para que decidas con criterio. Puedes saltártelas sin
  perder el hilo.
- Los ejemplos de comandos van en `código`.

La guía no pretende ser exhaustiva: pretende que observes antes y mejor. Si
echas algo en falta, abre una incidencia en el repositorio.
