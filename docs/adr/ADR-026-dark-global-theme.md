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

**Enmienda (2026-10-03, el icono sigue la paleta).** El icono de la
aplicación (`assets/appicon.svg`: una pluma dibujando la cola de un cometa
hacia una estrella de cuatro puntas sobre una teja azul noche) estaba
pintado en **oro y ámbar** (`#ecc15f`, `#dfa04f`, `#c98d7e`, `#c4755a`,
`#d69b63`, `#f5dc8f`, `#fff5cf`, `#f3dd98`, `#f7e0a0`, `#fff3c9`), fuera de
la paleta de esta ADR, y el desajuste se veía en el héroe de Bienvenida,
donde el logo queda justo al lado de la marca en azul.

1. **Mismo dibujo, paleta fría**: la pluma y la estrella toman el acento
   (`#6ab0ff`) con sus escalones (`#8fc4ff`, `#a9d1ff`, `#5f9ee8`,
   `#4484ef`, `#dcebff`), la cola del cometa va del azul profundo al pálido
   y las estrellitas pasan al blanco azulado (`#d8e6ff`). La teja
   (`#1b2134` → `#0e1119`) ya era de la familia del tema.
2. **La estrella conserva el núcleo casi blanco** (`#f4f9ff`): a 16 px el
   oro destaca más que el azul sobre una teja oscura, y sin ese núcleo el
   icono se leía como una mancha.
3. **Regeneradas las diez medidas** (`appicon-{16,24,32,48,64,128,256,512}`,
   `.ico` de siete tamaños y `.icns`) rasterizando con **QtSvg**, el mismo
   motor que dibuja el logo en la app, y montando los contenedores con
   Pillow.
4. **Guarda**: `tests/unit/test_theme.py` comprueba que **todos** los
   colores del icono son neutros o del lado frío del círculo (tono
   190-285°). Los tonos cálidos son de los OBJETOS (`KIND_COLORS`), no del
   logo.

**Enmienda (2026-10-09, los glifos de navegación de Qt se recolorean).**
El diálogo de ficheros (`QFileDialog`) mostraba sus botones de navegación
(atrás, adelante, subir) casi invisibles: dibujados en negro sobre el cromo
oscuro. La causa no era el QSS ni la paleta: **Fusion pinta las flechas
estándar en un color oscuro fijo que ignora la paleta**. Medido, el mismo
`SP_FileDialogBack` da luminosidad media **12,9** con la paleta oscura y con
la clara; los iconos de carpeta y de vista lista/detalle ya eran claros
(122 y 156) y no se tocan. El diálogo usa `SP_FileDialogBack` (atrás),
`SP_ArrowRight` (adelante) y `SP_FileDialogToParent` (subir).

1. **`apply_theme` envuelve Fusion en un `QProxyStyle`** (`_dark_glyph_style`)
   que solo sobreescribe `standardIcon()` para recolorear esos glifos a
   `C_TEXT`, con `QPainter` en `CompositionMode_SourceIn` (conserva el alfa y
   pinta un mapa por cada tamaño disponible). El resto se delega en Fusion
   sin cambios.
2. **La variante deshabilitada la genera Qt desde la paleta**, así que el
   recoloreo también la arregla: medido, 237 en normal y 204 en deshabilitado
   (atrás y adelante abren deshabilitados).
3. **Fuera de alcance**: el mismo defecto oscurece otros pixmaps estándar
   (controles multimedia, botones de barra de título y de extensión de
   toolbar). No afloran hoy en la app (dibujamos nuestros propios play y
   pausa y no estilizamos la barra de título del sistema), así que no se
   recolorean.
4. **Guarda**: `tests/unit/test_theme.py` comprueba que los glifos de
   navegación (normal y deshabilitado) son claros y, de punta a punta, que
   los tres botones del `QFileDialog` tienen icono legible.

**Enmienda (2026-10-09, el padding global recortaba glifos pequeños).** Dos
botones se veían como cajas vacías: el `✕` que cierra el cajón de proyectos
(arriba a la derecha del cajón, `main_window._build_drawer`) y la `☆` de
favorito del masthead del proyecto (`projects_tab.ui`). Los dos son
`QPushButton` de ancho fijo pequeño (28 y 36 px); con el padding global
`6px 16px` no les queda rect de contenido y el glifo se recorta entero. Es la
misma familia que ya documenta `test_theme.py` para los botones compactos, y
que ya llevaban el `×` de quitar fila y el `✕` de paso.

1. **`compact="true"`** en los dos (el `✕` en código, la `☆` en el `.ui`): el
   padding baja a `2px 6px` y el glifo vuelve.
2. **La `☆` (glifo hueco) sube a 18px** en el `.ui`: a 13px su trazo fino se
   leía tenue incluso sin recorte (medido: luminosidad máxima 132 a 13px,
   173 a 18px).
3. **Guarda**: `tests/unit/test_projects_view.py` abre el cajón y comprueba
   por píxeles que el `✕` y la `☆` se pintan (una caja vacía deja el brillo
   máximo en el borde, ~70-115; el glifo supera 130).

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

**Amendment (2026-10-03, the icon follows the palette).** The application
icon (`assets/appicon.svg`: a quill drawing a comet trail into a four-point
star on a night-navy tile) was painted in **gold and amber** (`#ecc15f`,
`#dfa04f`, `#c98d7e`, `#c4755a`, `#d69b63`, `#f5dc8f`, `#fff5cf`,
`#f3dd98`, `#f7e0a0`, `#fff3c9`), off this ADR's palette, and the clash
showed on the Welcome hero, where the logo sits right next to the blue
wordmark.

1. **Same drawing, cold palette**: the quill and the star take the accent
   (`#6ab0ff`) with its steps (`#8fc4ff`, `#a9d1ff`, `#5f9ee8`, `#4484ef`,
   `#dcebff`), the comet trail runs from the deep blue to the pale one, and
   the small stars turn blue-white (`#d8e6ff`). The tile (`#1b2134` →
   `#0e1119`) was already the theme's family.
2. **The star keeps its near-white core** (`#f4f9ff`): at 16 px gold pops
   more than blue on a dark tile, and without that core the icon read as a
   smudge.
3. **All ten rasters regenerated** (`appicon-{16,24,32,48,64,128,256,512}`,
   a seven-size `.ico` and the `.icns`) rasterising with **QtSvg**, the
   very engine that draws the logo in the app, and mounting the containers
   with Pillow.
4. **Guard**: `tests/unit/test_theme.py` checks that **every** colour in
   the icon is neutral or on the cold side of the wheel (hue 190-285°).
   The warm tones belong to the OBJECTS (`KIND_COLORS`), not to the logo.

**Amendment (2026-10-09, Qt's navigation glyphs get recoloured).** The file
dialog (`QFileDialog`) showed its navigation buttons (back, forward, up)
almost invisible: drawn black over the dark chrome. The cause was neither
the QSS nor the palette: **Fusion paints the standard arrows in a fixed dark
colour that ignores the palette**. Measured, the same `SP_FileDialogBack`
gives mean lightness **12.9** with the dark palette and with the light one;
the folder and list/detail icons were already light (122 and 156) and are
left alone. The dialog uses `SP_FileDialogBack` (back), `SP_ArrowRight`
(forward) and `SP_FileDialogToParent` (up).

1. **`apply_theme` wraps Fusion in a `QProxyStyle`** (`_dark_glyph_style`)
   that overrides only `standardIcon()` to recolour those glyphs to `C_TEXT`
   with `QPainter` in `CompositionMode_SourceIn` (keeps the alpha, one map
   per available size). Everything else is delegated to Fusion unchanged.
2. **The disabled variant is generated by Qt from the palette**, so the
   recolour fixes it too: measured, 237 normal and 204 disabled (back and
   forward open disabled).
3. **Out of scope**: the same defect darkens other standard pixmaps (media
   controls, title-bar and toolbar-extension buttons). They do not surface
   in the app today (we draw our own play and pause and do not style the
   system title bar), so they are not recoloured.
4. **Guard**: `tests/unit/test_theme.py` checks the navigation glyphs (normal
   and disabled) are light and, end to end, that the three `QFileDialog`
   buttons carry a legible icon.

**Amendment (2026-10-09, the global padding clipped small glyphs).** Two
buttons drew as empty boxes: the `✕` that closes the project drawer (top
right of the drawer, `main_window._build_drawer`) and the favorite `☆` of
the project masthead (`projects_tab.ui`). Both are small fixed-width
`QPushButton`s (28 and 36 px); with the global `6px 16px` padding they have
no content rect left and the glyph is clipped away. It is the same family
`test_theme.py` already documents for compact buttons, and that the row `×`
and the step `✕` already carried.

1. **`compact="true"`** on both (the `✕` in code, the `☆` in the `.ui`): the
   padding drops to `2px 6px` and the glyph comes back.
2. **The `☆` (a hollow glyph) goes up to 18px** in the `.ui`: at 13px its
   thin stroke read faint even unclipped (measured: max lightness 132 at
   13px, 173 at 18px).
3. **Guard**: `tests/unit/test_projects_view.py` opens the drawer and checks
   by pixels that the `✕` and the `☆` paint (an empty box leaves the peak
   brightness on the border, ~70-115; the glyph clears 130).
