# Cómo contribuir a NightScribe

*[English version](CONTRIBUTING.md)*

¡Gracias por tu interés! Estas reglas mantienen el proyecto mantenible por personas.

## Estilo de código (obligatorio)

1. **El código siempre en inglés**: identificadores, comentarios, cabeceras.
2. Todo `.py` empieza con la cabecera del proyecto (cópiala de cualquier módulo
   existente, ajusta el nombre). Ver `AGENTS.md`.
3. Voz humana: comentarios cortos `# @args:` / `# @return:` sobre cada método;
   TODOs como `# TODO:`; nada de docstrings robóticos ni sobre-ingeniería.
4. Funciones cortas, dependencias mínimas, sin magia.
5. Toda cadena visible en la GUI pasa por `self.tr()` — nunca escribas español ni
   inglés a fuego en la interfaz.
6. Todo acceso a red pasa por la caché de `core/db.py`; `requests` solo se importa
   dentro de `core/sources/`.

## Traducciones (GUI)

```bash
pyside6-lupdate nightscribe/gui -ts nightscribe/gui/i18n/nightscribe_es.ts \
    nightscribe/gui/i18n/nightscribe_en.ts
pyside6-linguist nightscribe/gui/i18n/nightscribe_es.ts    # traduce
pyside6-lrelease nightscribe/gui/i18n/nightscribe_*.ts     # compila .qm
```

El inglés es el idioma base del código; el español es una traducción. Los tests
fallan si queda alguna cadena `unfinished`.

## Tests

```bash
.venv/bin/pytest tests/unit          # sin red, deben pasar siempre
.venv/bin/pytest tests/functional    # con red, extremo a extremo por funcionalidad
```

Toda funcionalidad nueva llega con tests unitarios (los fixtures con respuestas
reales viven en `tests/fixtures/`) y, si toca una fuente o una función visible, un
test funcional.

## Decisiones de diseño

Lee primero `docs/adr/`. Para cambiar una decisión, actualiza o reemplaza el ADR. Para
añadir una fuente de datos, sigue `docs/DATA_SOURCES.md` (un módulo por fuente, TTL,
degradación elegante) y regístrala en un ADR.

## Pull requests

Un asunto por PR, tests en verde, documentación actualizada (ambos idiomas).
