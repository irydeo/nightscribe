# 04. Campañas y vigilias

Hay dos formas de compromiso a largo plazo en NightScribe, y conviene no
confundirlas: las **campañas** (un compromiso de grupo, con protocolo) y las
**vigilias** (un ojo permanente sobre una estrella concreta).

## Campañas

Una campaña es el compromiso *compartido* de un grupo de observatorios: un
objetivo científico («medir la erupción completa de T CrB»), un protocolo
(cadencia en noches, filtros, estrellas de comparación) y los enlaces donde
se informa y se depositan los datos. Muchos proyectos cuelgan de una
campaña; borrar la campaña no borra los proyectos, solo los libera.

La pestaña **Campañas** muestra la salud de cada campaña de un vistazo:
cuántos proyectos tiene, cuántos van *vencidos* respecto a la cadencia, y un
⚡ cuando algún miembro muestra un evento. Los botones hacen lo que dicen:

- **Nuevo proyecto…**: crea un proyecto nuevo ya vinculado (resuelve el nombre
  contra VSX y SIMBAD; si no está, lo introduces a mano).
- **Vincular proyecto…**: vincula un proyecto que ya existía.
- **Quitar proyecto…**: lo desvincula sin borrar nada.

> **¿Por qué la cadencia es lo único que NightScribe «lee» del protocolo?**
> Porque es lo único que puede comprobar. Si tu campaña pide una medida cada
> 3 noches y un miembro lleva 5 sin observarse, la app lo saca a la lista de
> esta noche (calculado en local, sin red). El resto del protocolo (filtros,
> comparaciones, notas) se guarda como referencia, pero la física de cada
> grupo es demasiado variada para modelarla: tú la lees, la app la recuerda.

## Vigilias

Una vigilia es una alarma sobre una estrella que puede cambiar *cualquier
día*: la lista curada la editas tú en Configuración, y el ejemplo canónico es
**T CrB** (una nova recurrente que puede estallar en cualquier momento) o
**R CrB** (que se desvanece sin avisar).

NightScribe consulta periódicamente la fotometría reciente (ZTF, y la AAVSO
si le diste tu token) y la compara con el nivel basal de cada estrella. Si
algo se sale de lo normal, te avisa.

> **¿Por qué comparar con el basal y no con «la magnitud de catálogo»?**
> Porque estas estrellas no tienen un brillo «de catálogo»: tienen un nivel
> de reposo alrededor del cual oscilan. Lo anómalo no es que T CrB esté en
> magnitud 10; lo anómalo es que se separe de su basal de ~10,5. Una erupción
> se detecta contra la historia de la estrella, no contra una tabla.

> **¿Por qué piden el token de AAVSO para las brillantes?** Por debajo de
> ~11,5 mag, ZTF deja de ser fiable por saturación, así que la vigilancia de
> las brillantes depende de la fotometría de la comunidad AAVSO, cuya API
> exige identificarse. Sin token, esas vigilias se quedan en silencio en vez
> de darte datos dudosos.

Siguiente: [05. Captura](05-capture.es.md).
