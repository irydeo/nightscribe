# NightScribe: desarrollar

*[English version](DEVELOPING.md)*

Este es el camino corto para quien mantiene el proyecto: cómo ejecutarlo y las
tres recetas que más salen (una fuente de datos nueva, un tipo de objetivo
nuevo, una pestaña nueva del editor). Las reglas están en
[`AGENTS.md`](../AGENTS.md); las decisiones, en
[`docs/adr/`](adr/README.md).

## Ejecutarlo

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python -m pytest tests/unit -n auto --dist loadfile   # rápido, sin red
.venv/bin/python -m pytest tests/functional                     # con red
.venv/bin/python -m nightscribe gui
```

La suite unitaria es offline a propósito: una llamada a `requests` lanza, y el
fallback propio de la fuente tiene que gestionarlo. Además acota sus propios
pools de hilos (el combine), así que `-n auto` es seguro incluso en una máquina
con muchos núcleos.

## Las reglas que son tests

Algunas reglas de la casa las sostiene un test, para que una PR falle a voces
en vez de en silencio: `test_help_texts.py` (una ayuda no nombra el caso
concreto), `test_em_dash.py` (ni en la guía ni en las cadenas de la interfaz),
`test_import_boundaries.py` (`requests` solo en `core/sources/`, nada de SQLite
en la GUI), `test_docs_links.py` (todo enlace de la documentación resuelve, el
índice de ADR está completo), `test_site_build.py` (la web commiteada es la que
produce el generador), `test_i18n.py` (los dos catálogos completos y en
sincronía) y `test_kinds_contract.py` (cada tipo tiene color, chip, análisis,
campos de contexto y hashtags).

## Receta: una fuente de datos nueva

1. **Un módulo por fuente**, `nightscribe/core/sources/<nombre>.py`. Expone una
   función `fetch(...)`/cliente pequeña y nunca llama a `requests` directamente:
   pasa por la caché, `db.http_get(key, "<fuente>", fetch)`, así que el TTL y el
   comportamiento offline no son su problema.
2. **Registra el TTL** en `core/db.py` (`SOURCE_TTL`). Elígelo por cada cuánto
   cambia de verdad lo de arriba (un atlas estático son 30 días, una lista de
   descubrimientos son horas).
3. **Conéctala**: `core/planner.py` si alimenta Esta noche (añade una etapa a la
   lista `stages` y una fase a `PHASES`), `core/enrich.py` si es contexto para la
   ficha del objeto.
4. **Documéntala** en `docs/DATA_SOURCES.md` (el endpoint, qué da, el TTL, si
   necesita clave) y añádela a la lista de fuentes del cuadro **Acerca de**.
5. **Pruébala**: un test unitario con la fuente simulada (la suite es offline) y
   un test funcional que pegue al endpoint real.

## Receta: un tipo de objetivo nuevo

Un tipo es un id de texto escrito a mano en muchos sitios, así que esto es una
cacería. Empieza en `core/kinds.py` (la lista canónica `KINDS`, más `ANALYSIS` y
`_CONTEXT_FIELDS`), y luego:

- `gui/theme.py`: `KIND_COLORS` y `KIND_LABELS` (el chip);
- `core/planner.py`: un constructor y su fase;
- `core/suggest.py`: cómo puntúa y su «por qué esta noche»;
- `core/narrative.py`: el gancho y los hashtags;
- `gui/overview.py`: las filas de la ficha del objeto para el tipo;
- `core/project.py`: `VALID_KINDS` si puede ser un proyecto.

`test_kinds_contract.py` falla hasta que los mapas cubren el id nuevo, que es la
red de seguridad barata; las cadenas de `if` las tienes que encontrar tú. Añade
los tests del tipo y, si trae una fuente, su entrada en `DATA_SOURCES.md`.

## Receta: una pestaña nueva del editor (UFE)

Las pestañas del editor FITS unificado siguen el ADR-005: la interfaz es un
fichero de Designer, el código la cablea.

1. **La estructura** en `nightscribe/gui/ui/ufe_<nombre>_tab.ui`: cada texto y
   tooltip vive aquí, con `<class>` = la clase propietaria y `objectName` = el
   atributo de Python.
2. **La pestaña** en `nightscribe/gui/ufe_<nombre>_tab.py`: carga el `.ui` con
   `ui_loader.load_ui`, cablea las señales, rellena los datos. Los widgets
   propios (un canvas, un histograma) nunca entran al `.ui`: un `QWidget` de
   relleno más `replaceWidget`.
3. **Toda cadena visible por `self.tr()`**, y ejecuta `tools/i18n.py` (nunca un
   `lrelease` crudo).
4. **Regístrala** en `gui/ufe_dialog.py` (la barra de pestañas y el estado
   compartido, `gui/ufe_state.py`).
5. **Pruébala** offscreen: monta la pestaña sobre una placa temporal y comprueba
   lo que muestra y lo que escribe.

## Commitear

Código, comentarios y mensajes de commit en inglés; un asunto por commit; los
tests en verde; la documentación (los dos idiomas) al día. Si cambias una
decisión, actualiza o supera su ADR.
