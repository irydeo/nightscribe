# ADR-079: Los catálogos de traducción se cargan desde memoria y se recompilan atómicamente

**Estado / Status**: Accepted · **Fecha / Date**: 2026-10-11

## Español

**Contexto**: el 2026-10-10 la GUI se cayó con un core dump (SIGSEGV) a las
17:29:36. La traza de Python señalaba un `self.tr()` anodino, el de los chips del
cielo en `main_window._skyevent_chips`, llamado al salir del editor hacia
Proyectos. En C++ el fallo estaba **dentro de `QTranslator::translate`**: la
instrucción que revienta lee una longitud y el último byte de un mensaje dentro
de los datos del `.qm`. Los once hilos de trabajo estaban dormidos; solo cayó el
de la GUI.

La causa se reprodujo en aislamiento:

1. **`QTranslator` MAPEA el `.qm` en memoria** cuando se carga por nombre: el
   fichero aparece en `/proc/self/maps` como `r--p`.
2. La app llevaba **abierta desde antes de las 16:45**; a las **17:11:58** yo
   ejecuté `pyside6-lupdate` + `lrelease` para añadir las cadenas nuevas. El
   `lrelease` **reescribe el `.qm` en su sitio** (trunca y escribe), y al ser el
   fichero nuevo más grande, el mapeo vivo de la app (del tamaño viejo) quedó
   corto. La primera traducción de un mensaje cuyo dato cae más allá del mapeo
   se salió de él y reventó (reproducido: mapear una copia, truncarla y traducir
   una cadena tardía da SIGBUS).
3. Además, al escribir el arreglo, apareció un segundo detalle: **`QTranslator.load(bytes)`
   NO copia el buffer**, guarda un puntero dentro de él. Pasar un `bytes`
   temporal hace que se libere al terminar la llamada y que el traductor lea
   memoria liberada (SIGSEGV en `installTranslator`). Mantener el buffer vivo lo
   arregla.

**Decisión**: dos capas, y un script para no volver a pisarlo.

1. **La app carga el `.qm` DESDE MEMORIA** (`nightscribe/gui/app.load_translator`):
   lee los bytes y llama a `QTranslator.load(data)`, guardando el buffer en el
   propio traductor (`_ns_catalogue`) para que viva tanto como el catálogo. Así
   el fichero **no se mapea** (no aparece en `/proc/self/maps`) y reescribirlo en
   disco no puede afectar a una sesión abierta. Se factoriza en `load_translator`
   para poder probarlo y para aceptar el idioma explícito.
2. **La recompilación es ATÓMICA** (`tools/i18n.py`): `lupdate` con la misma lista
   de fuentes de siempre y luego `lrelease <ts> -qm <temporal>` seguido de un
   `os.replace` sobre el destino (mismo directorio: rename atómico). Cualquier
   app que tuviera el `.qm` viejo mapeado sigue apuntando al inodo antiguo, cuyas
   páginas son válidas; nunca ve un fichero a medio escribir.
3. **Documentado**: `CONTRIBUTING.md` / `.es.md` apuntan al script y avisan de no
   usar el `lrelease` crudo con la app abierta.

**Consecuencias**: `QTranslator` deja de ser un punto de caída por recompilar
traducciones; el idioma de la GUI se sigue resolviendo igual (configurado o el
del sistema, ADR-014). El catálogo se mantiene en RAM (unas decenas de KB) en
lugar de mapeado, un coste despreciable. El test
`tests/unit/test_i18n.py::test_the_app_loads_its_catalogue_from_memory_not_mapped`
lo vigila en un subproceso (Linux): el `.qm` de la app no debe aparecer en los
mapas.

**Alternativas**: (a) no recompilar nunca con la app abierta, descartado como
única defensa: depende de la disciplina y el fallo es un core dump, no un aviso;
(b) copiar el `.qm` a un fichero privado al arrancar y cargar esa copia por
nombre, descartado: crea un fichero que hay que limpiar y sigue mapeando, solo
mueve el problema; (c) cargar por nombre y aceptar el mapeo, descartado: es
exactamente el fallo medido.

## English

**Context**: on 2026-10-10 the GUI dumped core (SIGSEGV) at 17:29:36. The Python
trace pointed at an innocuous `self.tr()`, the one for the sky-event chips in
`main_window._skyevent_chips`, called when leaving the editor towards Projects.
In C++ the fault was **inside `QTranslator::translate`**: the crashing instruction
reads a length and the last byte of a message within the `.qm` data. All eleven
worker threads were asleep; only the GUI thread died.

The cause was reproduced in isolation:

1. **`QTranslator` MEMORY-MAPS the `.qm`** when it is loaded by name: the file
   shows up in `/proc/self/maps` as `r--p`.
2. The app had been **open since before 16:45**; at **17:11:58** I ran
   `pyside6-lupdate` + `lrelease` to add the new strings. `lrelease` **rewrites
   the `.qm` in place** (truncate and write), and since the new file is larger,
   the app's live mapping (of the old size) came up short. The first translation
   of a message whose data lies beyond the mapping walked off it and crashed
   (reproduced: map a copy, truncate it, translate a late string, get SIGBUS).
3. While writing the fix, a second detail surfaced: **`QTranslator.load(bytes)`
   does NOT copy the buffer**, it keeps a pointer into it. Passing a temporary
   `bytes` frees it when the call returns and the translator reads freed memory
   (SIGSEGV in `installTranslator`). Keeping the buffer alive fixes it.

**Decision**: two layers, and a script so it is not stepped on again.

1. **The app loads the `.qm` FROM MEMORY** (`nightscribe/gui/app.load_translator`):
   it reads the bytes and calls `QTranslator.load(data)`, holding the buffer on
   the translator itself (`_ns_catalogue`) so it lives as long as the catalogue.
   The file is then **not mapped** (it does not appear in `/proc/self/maps`) and
   rewriting it on disk cannot touch an open session. It is factored into
   `load_translator` so it can be tested and so it accepts an explicit language.
2. **The rebuild is ATOMIC** (`tools/i18n.py`): `lupdate` with the same source
   list as always, then `lrelease <ts> -qm <temp>` followed by an `os.replace`
   over the target (same directory: an atomic rename). Any app that had the old
   `.qm` mapped keeps pointing at the old inode, whose pages are valid; it never
   sees a half-written file.
3. **Documented**: `CONTRIBUTING.md` / `.es.md` point at the script and warn
   against the raw `lrelease` with the app open.

**Consequences**: `QTranslator` stops being a crash point when translations are
rebuilt; the GUI language is still resolved the same way (configured or the
system one, ADR-014). The catalogue is kept in RAM (a few tens of KB) instead of
mapped, a negligible cost. The test
`tests/unit/test_i18n.py::test_the_app_loads_its_catalogue_from_memory_not_mapped`
watches it in a child process (Linux): the app's `.qm` must not appear in the
maps.

**Alternatives**: (a) never rebuild with the app open, rejected as the only
defence: it depends on discipline and the failure is a core dump, not a warning;
(b) copy the `.qm` to a private file at startup and load that copy by name,
rejected: it creates a file to clean up and still maps, it only moves the
problem; (c) load by name and accept the mapping, rejected: it is exactly the
measured failure.
