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
# recompila los catálogos: lupdate + lrelease ATÓMICO (ver más abajo)
.venv/bin/python tools/i18n.py
pyside6-linguist nightscribe/gui/i18n/nightscribe_es.ts    # traduce
.venv/bin/python tools/i18n.py --release-only              # recompila .qm
```

`tools/i18n.py` ejecuta `lupdate` con la misma lista de fuentes que antes
(los `.py` de `gui/` y `gui/widgets/`, `core/kinds.py`, `core/db.py` y los
`.ui`) y luego compila cada `.qm` **atómicamente**: escribe a un temporal en la
misma carpeta y lo renombra sobre el destino. Nunca lo hagas con el comando
crudo de `lrelease` mientras la app está abierta: `QTranslator` **mapea el
`.qm` en memoria**, y reescribirlo en su sitio invalida el mapeo de una sesión
abierta, que se cae en la siguiente traducción (fue un core dump real de la GUI,
2026-10-10). La app, además, carga el `.qm` **desde memoria** (sin mmap), así que
una recompilación ya no puede tumbarla; el rename atómico protege a cualquier
otra app que lo tenga mapeado.

El inglés es el idioma base del código; el español es una traducción. Los tests
fallan si queda alguna cadena `unfinished`.

## Empaquetado

```bash
# Windows: Inno Setup sobre el onedir de PyInstaller (el workflow hace ambos)
pyinstaller installer/nightscribe.spec --clean --noconfirm

# Linux (.deb): Python del sistema, Find_Orb dentro (ADR-087)
sh tools/fetch_findorb.sh findorb-payload
.venv/bin/python tools/build_deb.py --version 0.1.0 --findorb findorb-payload

# Linux (.rpm): installer/rpm/nightscribe.spec   (rpmbuild -bb)
# Arch:         installer/arch/PKGBUILD
```

Los tres paquetes de Linux usan el Python y el Qt de la DISTRO (ADR-087):
`.deb` para Debian 13+ / Ubuntu 25.10+, `.rpm` para Fedora 42+ / openSUSE
Tumbleweed y un PKGBUILD para Arch. Find_Orb viaja dentro (programa separado,
agregación legal para esta app GPLv3 no comercial); la efeméride DE430t no, se
descarga desde Ajustes. Las distros sin PySide6 empaquetado (Ubuntu 24.04 LTS)
son instalación manual documentada.

## Tests

```bash
.venv/bin/python -m pytest tests/unit      # sin red, deben pasar siempre
.venv/bin/python -m pytest tests/functional  # con red, extremo a extremo por funcionalidad
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
