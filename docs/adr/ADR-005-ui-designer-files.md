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
decisión. Se restaura con estas reglas operativas, que ya valen para todo
lo nuevo:

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
The restoration sets these operative rules, in force for everything new:

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
