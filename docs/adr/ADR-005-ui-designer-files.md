# ADR-005: Qt Designer .ui files loaded at runtime

**Estado / Status**: Accepted · **Fecha / Date**: 2026-08-21

## Español

**Contexto**: el autor quiere interfaces editables con Qt Designer (familiar desde
`saas`) y mantenibles por personas.

**Decisión**: la GUI se construye con ficheros **`.ui` de Qt Designer** cargados en
runtime con `uic.loadUi` / `QUiLoader`. Se incluye `gui/ui/build.sh` (estilo saas)
para compilar a `.py` con `pyside6-uic` quien lo prefiera.

**Alternativas**: UI en código puro (sin Designer); compilar `.ui`→`.py` siempre
(paso extra de build como en saas).

**Consecuencias**: edición visual sin tocar código; sin paso de compilación
obligatorio; los `.ui` ya marcan sus textos como traducibles (i18n, ADR-014).

## English

**Context**: the author wants interfaces editable with Qt Designer (familiar from
`saas`) and maintainable by humans.

**Decision**: the GUI is built with **Qt Designer `.ui` files** loaded at runtime via
`uic.loadUi` / `QUiLoader`. `gui/ui/build.sh` (saas style) is included for those who
prefer compiling to `.py` with `pyside6-uic`.

**Alternatives**: code-only UI (no Designer); always compile `.ui`→`.py` (extra build
step as in saas).

**Consequences**: visual editing without touching code; no mandatory compile step;
`.ui` texts are translatable out of the box (i18n, ADR-014).
