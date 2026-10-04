# Fase 9: liberar espacio (mover originales a `procesados`)

> Fase del plan maestro [`PLAN.md`](PLAN.md). Decisión: D21.

## Por qué

Una visita de track & stack son cientos de FITS de 16 MP. Una vez apilados,
medidos, validados y reportados, los originales ya no hacen falta para seguir
trabajando, pero borrarlos es destructivo: son datos del observador y viven en
su carpeta de captura, no en una copia de NightScribe (`project.add_file` guarda
la ruta, no copia). La respuesta es **ofrecer** liberar espacio moviéndolos a
una carpeta `procesados` del proyecto (recuperable) y dejar un manifiesto para
que la ejecución siga siendo auditable.

## Implementación

### 9.1 Destino y movimiento

- Destino: `project.storage_dir(p) / "procesados" / <visita>/`.
- Se **mueve**, no se borra. Al ser un `move`, si la carpeta de captura está en
  otro disco (`shutil.move` copia y luego borra) hay que:
  - comprobar el **espacio libre** en el destino antes de empezar;
  - mostrar **progreso** y permitir **cancelar**;
  - no dejar el fichero a medias (copiar a un temporal y `os.replace`, como ya
    hace `wcs_store`).
- **Solo los frames usados en un run con éxito**: la lista sale del manifiesto
  `astrometry_frames` del run. Nada que no se haya procesado se toca.
- **Cerrar los handles de mmap antes de mover** (D32): en Windows un fichero
  mapeado en memoria no se puede renombrar ni borrar, así que la liberación de
  espacio empieza por cerrar los `fits.open(..., memmap=True)` de esos frames y
  soltar los arrays; si no, el movimiento falla con un error de fichero en uso.

### 9.2 Cuándo se ofrece

- Justo al terminar un run con éxito, cuando el stack, el GIF, la medida y el
  reporte ya están guardados y validados (D21). Si el usuario dice que no, no
  se le vuelve a preguntar en ese run.
- También queda disponible como acción «Liberar espacio» en la visita, para
  hacerlo más tarde.

### 9.3 Qué se puede borrar (dos casillas)

- **Originales**: se mueven a `procesados` (recuperables).
- **Calibrados exportados**: segundo borrado independiente. Son derivados y
  reproducibles desde los originales, así que se pueden **borrar
  directamente**; no hace falta conservarlos en `procesados`.

### 9.4 Registro coherente

- Las filas de `project_files` de los frames movidos **actualizan su `path`** al
  nuevo destino y se marcan `meta["archived"] = true`. La lista de recursos de
  la visita sigue siendo veraz y los muestra como «en procesados», no como
  rutas rotas.
- El manifiesto `astrometry_frames` guarda, por fichero, `path` original,
  `size`, `filter`, `exptime_s`, `date_obs`, `archived` y `moved_to`. El run
  sigue siendo auditable y reproducible en su configuración aunque el FITS ya
  no esté en su sitio.
- **Restaurar**: al ser un movimiento, se ofrece mover de vuelta a la ruta
  original (que el manifiesto conoce) y limpiar `archived`.

### 9.5 Confirmación

Antes de tocar nada, un diálogo con: número de ficheros, espacio que se libera
y destino. Nada se mueve sin que el usuario lo vea.

## Tests

`tests/unit/test_free_space.py`:

- **A9, mover y restaurar**: tras mover, los ficheros están en `procesados`,
  las rutas de `project_files` apuntan al nuevo sitio y `archived` es True;
  restaurar lo devuelve todo.
- **Cruce de disco**: se simula el caso copiar + borrar (destino en otro
  sistema de ficheros) y se comprueba que no queda un fichero a medias si se
  cancela.
- **Manifiesto**: sobrevive al movimiento y conserva tamaño y metadatos.
- **Solo lo procesado**: un fichero de la visita que no entró en el run no se
  toca.
- **Sin éxito, sin oferta**: un run `not_detected` o `incomplete` no ofrece
  liberar espacio.
- **Calibrados**: borrar los calibrados exportados no afecta a los originales
  ni al manifiesto.
- **Handles cerrados**: mover un frame que estaba mapeado en memoria funciona
  porque el handle se cerró antes; se prueba el caso de fallo (handle abierto)
  para documentar el error.

## Salida limpia

Al terminar un run con éxito, el usuario puede liberar espacio moviendo los
originales a `procesados` y borrando los calibrados, con el registro coherente,
el manifiesto escrito y la opción de restaurar.

## Hecho cuando

A9 pasa, la visita sigue navegable tras el movimiento, y nada se mueve sin
confirmación.
