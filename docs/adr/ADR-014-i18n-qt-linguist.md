# ADR-014: UI internationalisation with Qt Linguist

**Estado / Status**: Accepted · **Fecha / Date**: 2026-08-21

## Español

**Contexto**: la interfaz debe poder usarse en español o inglés, configurable por el
usuario.

**Decisión**: sistema nativo Qt: toda cadena visible pasa por `self.tr()`; fuentes en
`gui/i18n/nightscribe_{es,en}.ts` editables con Qt Linguist; compilación a `.qm` con
`pyside6-lrelease`; carga con `QTranslator`. Idioma en Configuración (por defecto el
del SO vía `QLocale`); cambio en caliente vía `retranslateUi()`. Inglés como idioma
base del código.

**Alternativas**: diccionarios Python propios (rompe el flujo Designer/Linguist);
gettext (no idiomático en Qt).

**Consecuencias**: flujo estándar Qt conocido; los `.ui` son traducibles sin esfuerzo;
tests verifican que no quedan cadenas `unfinished`. El contenido generado sigue
siendo bilingüe a la vez (otra capa, ver ADR-013).

## English

**Context**: the interface must be usable in Spanish or English, user-configurable.

**Decision**: native Qt system: every visible string goes through `self.tr()`;
sources in `gui/i18n/nightscribe_{es,en}.ts` editable with Qt Linguist; compiled to
`.qm` with `pyside6-lrelease`; loaded via `QTranslator`. Language in Settings
(default OS locale via `QLocale`); hot-switch via `retranslateUi()`. English is the
code's base language.

**Alternatives**: own Python dictionaries (breaks the Designer/Linguist flow);
gettext (not idiomatic in Qt).

**Consequences**: well-known standard Qt flow; `.ui` files are translatable for free;
tests verify no `unfinished` strings remain. Generated content stays bilingual
at all times (another layer, see ADR-013).
