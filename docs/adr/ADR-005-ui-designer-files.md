# ADR-005: Qt Designer .ui files loaded at runtime

**Estado / Status**: Accepted · **Fecha / Date**: 2026-08-21 ·
**rev. 2026-09-25** (cumplimiento restaurado / compliance restored)

## Español

## English

**Contexto**: el autor quiere interfaces editables con Qt Designer (familiar desde
`saas`) y mantenibles por personas.

**Decisión**: la GUI se construye con ficheros **`.ui` de Qt Designer** cargados en
runtime con `uic.loadUi` / `QUiLoader`. Se incluye `gui/ui/build.sh` (estilo saas)
para compilar a `.py` con `pyside6-uic` quien lo prefiera.

**Alternativas**: UI en código puro (sin Designer); compilar `.ui`→`.py` siempre
(paso extra de build como en saas).

**Consecuencias**: edición visual sin tocar código; sin paso de compilación
obligatorio; los `.ui` ya marcan sus textos como traducibles (i18n, ADR-014).

**rev. 2026-09-25 (cumplimiento restaurado).** La era UFE (ADR-044) y las
piezas nacidas con ella se habían construido en código puro, contra esta
decisión. La restauración cubre **todo** lo construido en código: la
familia UFE (diálogo, cuatro pestañas y los dos diálogos auxiliares), el
gestor de visitas (panel, ventana y sus fragmentos por tipo), la ventana
de ficheros del proyecto, los diálogos de campañas (alta/edición y nuevo
proyecto), el diario, el borrador de cielo, el visor de documentación, el
visor de cartas y la ficha de objeto. Quedan en código por diseño: los
interiores de los widgets propios (`gui/widgets/`), los contenidos
dinámicos por dato (filas, chips, tablas por tipo) y los diálogos legacy
congelados (ADR-044). Reglas operativas, en vigor para todo lo nuevo:

- Toda ventana/diálogo/pestaña define su **estructura, textos y
  tooltips** en `gui/ui/<nombre>.ui`, con `<class>` igual a la clase
  Python propietaria (el contexto i18n se conserva y las traducciones se
  reciclan) y cada widget con su `objectName` igual al atributo que el
  código espera. La clase carga el fichero con
  `gui/ui_loader.load_ui()` (hogar único del cargador) y adopta el layout
  raíz con `self.setLayout(self._ui.layout())`, sin envoltorios ni
  márgenes dobles; los alias (`self.btn_x = self._ui.btn_x`) mantienen el
  contrato con el código y los tests.
- El código conserva: el cableado de señales, los ítems de combo con
  `userData`, los textos dinámicos (contadores, formatos con datos) y las
  visibilidades que dependen del estado.
- Los widgets propios (canvas, histograma, filas ricas) **nunca** van al
  `.ui`: un `QWidget` placeholder marca el hueco y el código inserta el
  real (`replaceWidget`), el patrón que `main_window.ui` ya usaba con sus
  páginas de pestaña. Sus interioridades quedan en su clase.
- Los literales no traducibles que un `.ui` recogería (valores de
  `layoutStretch`, glifos como «–», ejemplos tipo «SN 2026xyz») llevan
  `notr="true"` para no ensuciar el catálogo.
- Los diálogos legacy congelados (ADR-044) quedan fuera del saneado.

Dos trampas aprendidas en campo (pagadas con una regresión real: márgenes
a cero y la barra del UFE sin clicks en «Load FITS…»), ya escritas en el
cargador para que no se repitan:

- **`adopt_ui(host, name)`** es el idiom de adopción: carga, deja que el
  layout raíz tome el host y **oculta el husk** (la raíz del `.ui` queda
  como hija visible de 100×30 en (0, 0) si no se oculta: tapa la primera
  fila y se come sus clicks).
- **`drop_in(layout, placeholder, widget)`** para todo placeholder:
  `QLayout.replaceWidget` NO oculta el widget retirado (a diferencia de
  `QSplitter.replaceWidget`, que sí), y visible queda flotando sobre la
  primera fila.
- **Los márgenes son explícitos en cada `.ui`**: `QUiLoader` entrega 0 y
  el código viejo obtenía los del estilo (11 px en diálogos top-level,
  9 px en pestañas/paneles hijos, 9 px en cajas de grupo); los valores
  medidos del árbol pre-migración viven en los ficheros. Todo esto lo
  pincha `tests/unit/test_ui_files.py` (márgenes + `childAt`, el
  hit-test honesto que encontró al culpable).

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

**rev. 2026-09-25 (compliance restored).** The UFE era (ADR-044) and the
pieces born with it had been built in pure code, against this decision.
The restoration covers **everything** that was code-built: the UFE family
(dialog, four tabs and the two auxiliary dialogs), the visits manager
(panel, window and its per-kind fragments), the project files window, the
campaign dialogs (edit and new project), the journal, the sky-post draft,
the documentation viewer, the chart viewer and the object panel. Left in
code by design: the custom widgets' internals (`gui/widgets/`), the
data-driven dynamic content (rows, chips, per-kind tables) and the frozen
legacy dialogs (ADR-044). Operative rules, in force for everything new:

- Every window/dialog/tab defines its **structure, texts and tooltips**
  in `gui/ui/<name>.ui`, with `<class>` equal to the owning Python class
  (the i18n context is preserved and the translations recycle) and every
  widget's `objectName` equal to the attribute the code expects. The
  class loads the file through `gui/ui_loader.load_ui()` (the loader's
  single home) and adopts the root layout with
  `self.setLayout(self._ui.layout())`: no wrappers, no double margins;
  the aliases (`self.btn_x = self._ui.btn_x`) keep the contract with
  code and tests.
- Code keeps: signal wiring, combo items with `userData`, dynamic texts
  (counters, data formats) and state-driven visibility.
- Custom widgets (canvases, the histogram, rich rows) **never** enter a
  .ui: a placeholder QWidget marks the slot and the code inserts the
  real one (`replaceWidget`), the pattern `main_window.ui` always used
  for its tab pages. Their internals stay in their class.
- Non-translatable literals a .ui would collect (layoutStretch values,
  glyphs like "–", samples like "SN 2026xyz") carry `notr="true"` so the
  catalog stays clean.
- The frozen legacy dialogs (ADR-044) stay out of the restoration.

Two field lessons (paid for with a real regression: zero margins and a
dead "Load FITS…" button), now written into the loader so they never
recur:

- **`adopt_ui(host, name)`** is the adoption idiom: load, let the root
  layout take over the host, and HIDE the husk (the .ui's root widget
  otherwise stays as a visible 100x30 child at (0, 0): it covers the
  first row and eats its clicks).
- **`drop_in(layout, placeholder, widget)`** for every placeholder:
  `QLayout.replaceWidget` does NOT hide the replaced widget (unlike
  `QSplitter.replaceWidget`, which does); left visible it floats over
  the first row.
- **Margins are explicit in every .ui**: QUiLoader delivers 0 while the
  old code got the style's (11 px on top-level dialogs, 9 px on child
  tabs/panels, 9 px on group boxes); the values measured from the
  pre-migration tree live in the files. All of this is pinned by
  `tests/unit/test_ui_files.py` (margins + the honest `childAt`
  hit-test that found the culprit).
