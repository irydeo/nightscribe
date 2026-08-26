# ADR-026: Dark global theme — one stylesheet, one palette

**Estado / Status**: Accepted · **Fecha / Date**: 2026-08-25

## Español

**Contexto**: la aplicación no tenía hoja de estilos global. El aspecto oscuro
se aplicaba widget a widget (tarjetas de «Esta noche», tooltip, preview de
blink…) mientras pestañas, menús, tablas, diálogos y barras de estado seguían
usando el tema nativo de la plataforma — sobre un escritorio claro la app se
veía a medias: componentes oscuros flotando sobre cromo claro. Resultado:
inconsistente y difícil de mantener (cada color estaba literal en su módulo).

**Decisión**: una identidad visual central, aplicada una sola vez:

1. **`nightscribe/gui/theme.py`** (nuevo) concentra:
   - Los colores base de la familia (fondo `#0f121c`, base de entrada
     `#12141f`, panel `#171a26`, línea `#232736`, resaltado `#2f4d80`,
     texto `#e8eaf2`/`#8a90a6`, acento `#6ab0ff`, aviso `#cc8844`,
     OK `#66cc99`/`#99bbdd`).
   - `KIND_COLORS` y `KIND_LABELS` (los acentos por tipo de objeto), que
     antes vivían en `main_window.py`. Todos los módulos que los necesiten
     los importan de aquí.
   - `apply_theme(app)`: `app.setStyle("Fusion")` + `QPalette` oscuro +
     stylesheet QSS que estiliza el cromo: ventanas, diálogos, botones,
     menús, pestañas, inputs, tablas, `QGroupBox`, `QToolbar`, `QStatusBar`,
     tooltips y scrollbars.

2. **`app.py`** llama a `apply_theme(app)` una vez, nada más crear el
   `QApplication` y **antes** de instalar traductores y abrir ventanas.

**Consecuencias**:

- Toda la app pinta con la misma paleta; en un escritorio claro o oscuro no
  cambia el cromo de NightScribe.
- Los estilos inline existentes (tarjetas, botones Start/Continue, pane de
  documento blanco del visor de docs) siguen aplicándose sobre el tema
  global y no se rompen — el QSS global solo toca cromo, el contenido
  mantiene sus colores.
- El visor de documentación (`doc_viewer.py`) conserva su página blanca
  deliberada (es un documento, no UI) y su árbol oscuro, sin cambios.
- Cambiar el tema en el futuro = cambiar los hex de `theme.py`; ya no hay
  que cazar literales por módulos.
- Tests: `tests/unit/test_theme.py` (offscreen) valida que `apply_theme`
  establece Fusion, la paleta oscura y el QSS, y que `KIND_COLORS` cubre
  los seis tipos.

**Escopado**: este ADR cubre el tema global (fase A del rediseño de la
pantalla de inicio). El rediseño de la propia pantalla de «Esta noche»
(filas amplias con el «por qué» visible) y la tabla completa son fases
separadas; ver `docs/WORKFLOWS.es.md` para el punto de entrada.

## English

**Context**: the application had no global stylesheet. The dark look was
applied widget by widget (Tonight cards, tooltips, the blink preview…)
while tabs, menus, tables, dialogs and the status bar kept the platform
theme — on a light desktop the app looked half-styled, dark components
floating over light chrome. Inconsistent and hard to maintain (each color
was a literal in its own module).

**Decision**: one central visual identity, applied exactly once:

1. **`nightscribe/gui/theme.py`** (new) holds:
   - the base palette (window `#0f121c`, inputs/base `#12141f`, panel
     `#171a26`, lines `#232736`, highlight `#2f4d80`, text
     `#e8eaf2`/`#8a90a6`, accent `#6ab0ff`, warning `#cc8844`,
     good `#66cc99`/`#99bbdd`);
   - `KIND_COLORS` and `KIND_LABELS` (per-object-type accents), moved out
     of `main_window.py`; any module that needs them imports them from
     here;
   - `apply_theme(app)`: `app.setStyle("Fusion")` + a dark `QPalette` +
     a QSS stylesheet for the chrome: windows, dialogs, buttons, menus,
     tabs, inputs, tables, `QGroupBox`, toolbar, status bar, tooltips and
     scrollbars.

2. **`app.py`** calls `apply_theme(app)` once, right after the
   `QApplication` is created and **before** translators are installed and
   any window opens.

**Consequences**:

- The whole app paints with one palette; a light or dark desktop no longer
  changes NightScribe's chrome.
- Existing inline styles (cards, Start/Continue buttons, the white document
  pane of the docs viewer) still layer on top of the global theme and keep
  working — the global QSS only touches chrome, content keeps its colors.
- The documentation viewer (`doc_viewer.py`) keeps its deliberate white
  page (it is a document, not UI) and its dark tree, unchanged.
- Changing the theme in the future = editing the hex strings in `theme.py`;
  no more hunting for literals across modules.
- Tests: `tests/unit/test_theme.py` (offscreen) verifies that `apply_theme`
  sets the Fusion style, a dark palette and the stylesheet, and that
  `KIND_COLORS` covers all six object kinds.

**Scope**: this ADR covers the global theme only (phase A of the home
screen redesign). The redesign of the «Tonight» screen itself (wider rows
showing the "why tonight" text) and of the full table are separate phases;
see `docs/WORKFLOWS.es.md` for the entry point.
