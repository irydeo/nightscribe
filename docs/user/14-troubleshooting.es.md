# 14. Cuando algo va mal

Casi ninguna noche falla nada. Este capítulo es para las que sí: qué
significa cada fallo, qué hace NightScribe por su cuenta y qué te queda a ti.

## Primera parada: el registro

**Ayuda → Abrir el registro…** abre el fichero que la aplicación escribe
mientras funciona. Si apareció un diálogo y se desvaneció, o un paso falló
sin decir por qué, la respuesta está casi siempre ahí. Cuando reportes un
problema, adjunta ese fichero.

El fichero no crece sin límite: rota por tamaño, así que la carpeta guarda el
registro actual y unos pocos anteriores (unos pocos megabytes como mucho) y
nunca hay que limpiarlo a mano.

## No hay red

NightScribe funciona sin conexión para todo lo que no necesita datos en vivo:
el Sol y la Luna, los crepúsculos, el calendario del cielo, toda la reducción
(calibración, apilado, fotometría, astrometría) y tus proyectos guardados. Lo
que deja de funcionar es la parte que trae listas frescas: los objetivos de
esta noche, las efemérides, los recortes de los surveys.

- Si **Esta noche** vuelve vacía, lo dice. El estado vacío distingue los dos
  casos: *ninguna fuente respondió* (un problema de red, revisa la conexión)
  y *ninguno de tus tipos habilitados está visible esta noche* (las fuentes
  respondieron; prueba a habilitar más tipos en el filtro).
- Las fuentes que fallan degradan con elegancia y quedan como aviso en el
  registro; la app nunca se cae porque una web esté caída.
- Todo lo ya descargado se cachea con su propia ventana de frescura, así que
  una lista que cargaste hace una hora sigue sirviendo.

## La placa no se resuelve

Resolver encuentra las estrellas de tu imagen y calcula hacia dónde apunta.
Necesita un solver:

- **Configuración → Integraciones → Solver**: `auto` prueba primero un
  **ASTAP** local y cae a **Astrometry.net** (que necesita una clave gratuita
  y red);
- si no tienes solver local, ponlo en `astrometry` y asegúrate de rellenar la
  clave;
- una placa con muy pocas estrellas, mucha estela o un objetivo equivocado
  puede con cualquier solver. El error nombra la toma, y el registro tiene el
  detalle.

## La placa no tiene WCS

El editor FITS y la astrometría necesitan una placa resuelta (una WCS: el
mapa de píxeles a cielo). Si tu cámara no escribió ninguna, el editor dice
**Carga una imagen FITS o abre una visita**, y el botón **Resolver** de la
visita (y el resuelto por lotes) es la puerta: resuelve el frame de
referencia y los demás le siguen.

## El MPC rechaza el informe

El informe tiene que cuadrar con el formato que acepta el Minor Planet
Center, y las observaciones tienen que ser buenas. La app construye el informe
con tus medidas y lo comprueba mientras lo construye: el formato (80 columnas
o ADES PSV), las fechas, los códigos y la relación señal/ruido de cada
observación. Donde mides, además te dice qué observaciones no recomienda enviar
(la decisión sigue siendo tuya). Si el MPC rechaza un informe, su mensaje
nombra la línea; corrige la medida y vuelve a construir el informe. El capítulo
de astrometría (07) recorre todo el camino.

## EXOTIC no está configurado

La reducción de tránsitos corre en **EXOTIC**, un programa externo que
necesita un Python propio (3.10 a 3.12). El bloque de tránsito del editor
dice si encontró uno; sin él aún puedes exportar el handoff (`inits.json`),
ejecutar EXOTIC tú mismo e importar su salida de vuelta. No se pierde nada:
el handoff es siempre tuyo.

La salida más corta es el entorno **ya preparado para descomprimir** que el
proyecto publica en su propia release,
[`exotic-env`](https://github.com/irydeo/nightscribe/releases/tag/exotic-env)
(capítulo 06): descarga el zip de tu plataforma, descomprímelo donde quieras y
apunta **Configuración → Medida → Avanzado → EXOTIC** al intérprete que lleva
dentro.

Dos cosas que ahorran tiempo cuando algo va mal:

- Si la app dice que el intérprete que apuntaste **ya no está**, ese campo
  guardaba la ruta de algo que se borró o que está en un disco sin montar.
  Vacíalo: la app busca otro y te dice cuál encontró.
- El intérprete tiene que estar **fuera** de la carpeta del entorno. Apuntar
  a un Python que vive dentro se rechaza, con el motivo: reconstruir el
  entorno borraría el intérprete a mitad de la construcción.

## La app no arranca

- Lánzala una vez desde un terminal (`nightscribe gui`). El traceback, si lo
  hay, va a la consola y al fichero de registro.
- El registro vive en el directorio de datos de tu usuario; **Ayuda → Abrir
  el registro…** lo muestra, y la ruta está impresa en la cabecera del
  fichero.
- Un home de solo lectura o un disco lleno pueden impedir que la app escriba
  su base de datos. El mensaje dice cuál.

## El paquete se instaló pero apt dijo «Permiso denegado»

Instalar el `.deb` desde tu carpeta de descargas puede imprimir una línea así:

> La descarga se realiza sin aislamiento como root dado que el archivo «...»
> no pudo accederlo el usuario «_apt». - pkgAcquire::Run (13: Permiso denegado)

Es una nota del propio apt, **no un error**: apt lee un paquete local a través
de su usuario sin privilegios `_apt`, y cuando ese usuario no alcanza el
fichero (la carpeta o el fichero no son legibles por cualquiera) lo lee como
**root y sin aislamiento**, y lo dice. La instalación termina bien.

Si prefieres no verlo, copia antes el fichero a un sitio que cualquiera pueda
leer:

```bash
cp ~/Descargas/nightscribe_*.deb /tmp/ && sudo apt install /tmp/nightscribe_*.deb
```

El paquete no tiene nada malo: la nota es sobre **dónde está el fichero**, no
sobre lo que lleva dentro.

## Reportar un problema

El gestor de incidencias del repositorio es el sitio. Incluye: qué estabas
haciendo, qué esperabas, qué pasó y el fichero de registro. El cuadro
**Acerca de** nombra la versión exacta y las fuentes de datos, que es lo
primero que necesita un informe de fallo.

Volver al [índice](README.es.md).
