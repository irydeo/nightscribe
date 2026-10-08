# 05. Captura

## CCDciel: del plan al telescopio

Si tu observatorio se controla con [CCDciel](https://www.ap-i.net/ccdciel/),
NightScribe puede entregarle el plan de captura directamente, sin exportar
ficheros ni reescribir coordenadas.

Configuración, una sola vez, en **Herramientas → Configuración… → Integraciones**:
host y puerto del equipo donde corre CCDciel (por defecto el 3277) y si
quieres que conecte solo. Una condición: **CCDciel tiene que estar abierto**;
NightScribe habla con su servidor JSON-RPC, no con los drivers.

Desde el paso **Captura** de un proyecto:

- **Conectar CCDciel** muestra el estado del observatorio (montura, rueda de
  filtros, cámara) en el panel.
- **Enviar plan** prepara en CCDciel el nombre del objeto, la exposición, el
  número de tomas y el filtro (la lista se lee de tu rueda; si no responde,
  se usa la lista clásica L/R/G/B/Ha/OIII/SII).
- El apuntado convierte las coordenadas J2000 del plan a **aparentes** antes
  de enviarlas, y puede hacer *goto* con ajuste astrométrico si tu flujo en
  CCDciel lo tiene configurado.

> **¿Por qué coordenadas aparentes y no J2000?** Porque la montura apunta al
> cielo de *ahora*, no al del año 2000. Precesión, nutación y aberración
> mueven la posición aparente de una estrella decenas de segundos de arco:
> más que el campo de muchas cámaras. NightScribe hace la conversión por ti
> para que el objeto caiga en el chip, no fuera de él.

## Calibración: bias, darks y flats

La pestaña **Calibración** del editor FITS gestiona una **biblioteca de
masters** y la receta de cada visita.

La biblioteca se indexa, no se copia: señalas tus FITS maestros y la app lee
de sus cabeceras lo que los hace válidos (cámara, ganancia, temperatura,
exposición, filtro). Al indexar declaras qué *es* cada fichero:

- **Bias**: el offset electrónico de lectura (exposición cero).
- **Dark**: corriente térmica, a la misma exposición que las luces. *Un dark
  ya incluye el bias*, así que con dark no hace falta bias aparte.
- **Dark de flats**: a la exposición de los flats.
- **Flat**: por filtro, normalizado.

> **¿Por qué calibrar?** Porque tu sensor miente de tres maneras conocidas y
> repetibles: añade un pedestal electrónico a cada píxel (bias), acumula
> carga térmica con el tiempo (dark) y multiplica la luz por la sombra del
> polvo y el viñeteo (flat). Restar bias+dark y dividir por el flat no es
> estética: es lo que convierte ADU en fotones comparables de una esquina a
> otra del chip y de una noche a otra. Sin eso, la fotometría del capítulo 06
> mide el polvo de tu tren óptico, no la estrella.

> **¿Por qué el flat es por filtro?** Porque las sombras del polvo cambian de
> escala con la óptica y la rueda, y la respuesta del sensor cambia con el
> color. Un flat de V no corrige un R: la sombra de la misma mota cae en otro
> sitio si la rueda aparca distinto.

**La receta de la visita**: al abrir el editor desde una visita, la app
resuelve qué master de la biblioteca usa cada pieza, leyendo la cabecera del
primer frame, y avisa de lo que falte (Avisos). **Calibrar la visita**
aplica la receta a todos los frames; la calibración trabaja en memoria y
solo escribe copias FITS si marcas la exportación.

**Si no tienes flat para un filtro**: la opción *Build a flat from the
frames* construye un pseudo-flat apilando las propias luces (el polvo y el
viñeteo están fijos en el frame; las estrellas se mueven entre tomas y
desaparecen en el percentil bajo). Úsalo como lo que es: un parche honesto
que nunca se antepone a un flat real. Puedes abrirlo con **Ver el flat** y
juzgarlo: un flat con una estrella dentro no es un flat.

> **¿Por qué funciona el pseudo-flat?** Porque en una serie con *dithering*
> (pequeños desplazamientos entre tomas) lo único que no se mueve es lo que
> pertenece al instrumento: polvo, viñeteo, píxeles calientes. Un percentil
> bajo sobre muchas tomas conserva lo fijo y rechaza lo que se movió. Si tu
> campo es estático (sin dithering), la app enmascara las estrellas antes de
> apilar, por la misma razón.

Siguiente: [06. Fotometría](06-photometry.es.md).
