# 11. El asistente (experimental)

NightScribe puede llevar un asistente para preguntar por el objeto en el que
trabajas, por la propia aplicación o por lo que tienes delante en el editor.
No mide, no clasifica y no decide: solo lee lo que la app ya sabe y lo pone en
palabras. Es una función **experimental**: depende de un modelo de lenguaje que
tú conectas.

## Dónde está

En **Ayuda → Asistente (experimental)**. Si tienes un proyecto abierto, el
asistente puede hablar de él; si no, habla de la app. En el editor de FITS hay
además un botón **?** en la barra: abre el asistente centrado en lo que tienes
cargado.

## Los tres ámbitos

El selector de arriba decide sobre qué responde:

- **Este objeto**: tu proyecto abierto. El asistente lee su ficha: el objeto
  con sus parámetros explicados, la noche planificada, tus visitas, las
  magnitudes medidas y el veredicto de la campaña.
- **La app**: la guía de usuario y los ADR. Preguntas como «¿cómo calibro las
  tomas?» o «¿qué significa el MOID?».
- **El editor**: lo que tienes cargado (la placa, la pestaña, si tiene WCS)
  más la guía. «Quiero hacer la curva de luz, ¿puedo?» se responde con lo que
  hay en pantalla y con los pasos de la guía.

Bajo cada respuesta verás **las fuentes** que se usaron: los campos de la ficha
o los documentos. Si no había nada sobre lo que apoyarse, lo dice; el asistente
no rellena los huecos.

> **¿Por qué es distinto de un chatbot?** Porque solo habla de lo que la app
> tiene delante. No inventa cifras ni clasificaciones y no toca tus datos: si
> algo no está en la ficha o en la guía, responde que no lo sabe. Es un
> compañero que mira tu pantalla, no una fuente de datos.

## Lo que necesitas

Un modelo de lenguaje configurado en **Ajustes → Integraciones** (capítulo 10).
Si la IA está apagada o no hay modelo, el menú y el botón **?** quedan
deshabilitados (con el motivo al pasar el ratón) y no se abre ninguna
ventana. La conversación vive solo en su ventana: al cerrarla se olvida. Nada
se guarda en tu base de datos.
