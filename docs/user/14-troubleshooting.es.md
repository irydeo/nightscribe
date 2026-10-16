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
Center, y las observaciones tienen que ser buenas. Antes de enviar nada, el
bloque **Gestionar informe MPC** lo valida línea a línea: el formato (80
columnas o ADES PSV), las fechas, los códigos y una lista de relación
señal/ruido. Si el MPC rechaza un informe, su mensaje nombra la línea;
corrígela ahí y valida otra vez. El capítulo de astrometría (07) recorre todo
el camino.

## EXOTIC no está configurado

La reducción de tránsitos corre en **EXOTIC**, un programa externo que
necesita Python 3.10 o anterior. El bloque de tránsito del editor dice si
encontró uno; sin él aún puedes exportar el handoff (`inits.json`), ejecutar
EXOTIC tú mismo e importar su salida de vuelta. No se pierde nada: el handoff
es siempre tuyo.

## La app no arranca

- Lánzala una vez desde un terminal (`nightscribe gui`). El traceback, si lo
  hay, va a la consola y al fichero de registro.
- El registro vive en el directorio de datos de tu usuario; **Ayuda → Abrir
  el registro…** lo muestra, y la ruta está impresa en la cabecera del
  fichero.
- Un home de solo lectura o un disco lleno pueden impedir que la app escriba
  su base de datos. El mensaje dice cuál.

## Reportar un problema

El gestor de incidencias del repositorio es el sitio. Incluye: qué estabas
haciendo, qué esperabas, qué pasó y el fichero de registro. El cuadro
**Acerca de** nombra la versión exacta y las fuentes de datos, que es lo
primero que necesita un informe de fallo.

Volver al [índice](README.es.md).
