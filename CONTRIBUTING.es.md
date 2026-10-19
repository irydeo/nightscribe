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

**Una ayuda no nombra el caso concreto** (AGENTS.md, regla permanente): un tooltip o un
texto de ayuda explica POR QUÉ y, como mucho, el ORDEN DE MAGNITUD («pierde alrededor de
un cuarto de magnitud»); nunca cita la visita, la fecha, el objeto ni el número de tomas
del que salió la medida, ni pone un ejemplo con nombre propio. Las cifras exactas viven
en el ADR y en los comentarios del código, que es donde se pueden revisar.
`tests/unit/test_help_texts.py` recorre cada tooltip, etiqueta y cadena `tr()` y falla
ante un caso concreto; si una cadena va legítimamente de las vigilias (cuya lista ES
T CrB y R CrB), el test lo dice con sus propias palabras.

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
degradación elegante) y regístrala en un ADR. Para las tres recetas que más salen (una
fuente nueva, un tipo de objetivo nuevo, una pestaña nueva del editor), mira
`docs/DEVELOPING.md`.

## Release

La versión sale del tag de git: `setuptools-scm` lo lee, así que etiquetar
`v0.1.0` hace que el paquete construido y el propio `--version` de la app
digan `0.1.0`. No hay nada que editar a mano.

1. Mueve las entradas de `[Sin publicar]` de `CHANGELOG.es.md` (y su gemelo
   inglés) bajo la nueva versión, con la fecha de hoy.
2. Comprueba que el clasificador `Development Status` de `pyproject.toml`
   sigue cuadrando con el hito (`3 - Alpha`, `4 - Beta`, `5 -
   Production/Stable`).
3. Llévalo a `main`: el workflow `preview.yml` construye los artefactos
   (instalador y zip portable de Windows, `.deb`, `.rpm`) y los publica como la
   pre-release rodante, después de que pase la suite unitaria.
4. Etiqueta y sube: `git tag -a v0.1.0 -m "NightScribe 0.1.0"` y luego
   `git push origin v0.1.0`. El tag dispara `release.yml`, que construye los
   mismos cuatro artefactos **sin** el sufijo `-preview` y los publica como una
   release **estable** de GitHub, marcada como la última, con las notas tomadas
   de la sección `[0.1.0]` de `CHANGELOG.md`.
5. Verifícalo: `gh release view v0.1.0` lista los cuatro ficheros, y la
   pre-release rodante `preview-*` se queda como la de desarrollo.

### Parchear una versión ya publicada

Cuando el fallo está en la versión que la gente tiene instalada, la rama de
mantenimiento manda (ADR-093): el orden se invierte, porque lo que se construye
es la línea publicada y no `main`.

1. Crea la rama desde el tag de la release que vas a mantener (o desde `main`,
   que en ese momento es el mismo commit): `git switch -c release/v0.1.x v0.1.0`.
   Nace una vez por línea de versión y vive mientras esa línea sea la publicada.
2. Haz el arreglo **en la rama**, con su test, y añade la sección
   `## [0.1.1] - <fecha>` a los dos `CHANGELOG` (arriba de `[0.1.0]`, debajo de
   `[Sin publicar]`).
3. Verifica que el test nuevo **falla sin el arreglo** y pasa con él, y que la
   suite entera sigue verde.
4. Etiqueta desde la rama: `git tag -a v0.1.1 -m "NightScribe 0.1.1"` y
   `git push origin v0.1.1`. `release.yml` construye y publica la release
   estable, igual que en el camino normal.
5. **Adelanta el arreglo a `main` el mismo día** (`git cherry-pick <commit>`),
   para que el tronco no se quede con el fallo. El único fichero que choca es el
   `CHANGELOG`, así que hazlo pronto: mientras el `[Sin publicar]` de `main`
   esté intacto, entra limpio.
6. La rama se queda para el siguiente parche de la misma línea y se congela o se
   borra cuando salga la siguiente menor.

## Pull requests

Un asunto por PR, tests en verde, documentación actualizada (ambos idiomas).
