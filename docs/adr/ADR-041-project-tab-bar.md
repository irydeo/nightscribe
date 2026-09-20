# ADR-041: La página del proyecto como barra de pestañas perezosas / The project page as a lazy tab bar

**Estado / Status**: Accepted · **Fecha / Date**: 2026-09-19 · **ejecutado /
executed**: 2026-09-19 (`test_project_tabs.py` 25 + `test_projects_hub.py` 97
+ suite unitaria 1391 green)

**Ver / See**: ADR-019 (hub de proyectos — enmendado dos veces: wizard →
página única plegable (Track UX) → esta barra) · ADR-038 (prominencia y
lenguaje llano) · ADR-034 D3 (HADS comparte el follow-up) ·
`docs/WORKFLOWS.es.md` §7sexdecies (Track UX, UD «página única», enmendado
por esta decisión).

## Español

**Contexto**: el Track UX (UD) fundió las pestañas de paso en una **página
única con secciones plegables**: un solo acordeón con *Object card · Plan ·
Proceso · Publicar · Follow-up*, y la tarjeta «Siguiente» como banner global.
Funcionaba, pero al revisar la UX el observador notó que la página
«desapila» todo de golpe: cinco bloques, varios plegados por defecto, y el
ojo no puede separar *dónde estoy* de *qué me falta*. Un acordeón es una
lista de cajones; una barra de pestañas es un mapa. Y la tarjeta
«Siguiente» ya decía la verdad — ahora la navegación debería parecerse a
ella.

**Decisión** (pactada con el observador, 2026-09-19):

1. **Barra de 5 pestañas planas sobre la página** (reemplaza la pista de
   pasos, no es un `QTabWidget`): *Object card · Plan · Proceso · Publicar
   · Follow-up*. Cinco `QPushButton` checkables planos en
   `projects_tab.ui` (`tabLayout`, `btn_tab_details/plan/process/
   publish/followup`), estado visual por `theme.tab_state_style`
   (`theme.py`): normal / hover / checked con el color del kind.
2. **Una pestaña visible a la vez; las páginas se construyen perezosas**
   (`main_window.py`): `self._tab_pages` (key → QWidget) y
   `self._active_tab`. Solo se construye el que se abre — el primero y el
   objetivo de la tarjeta «Siguiente» al seleccionar un proyecto
   (`_build_project_page` → `_show_tab(next target)`), el resto al primer
   clic. Cada builder (`_build_{plan,process,publish,followup}_tab`) se
   ejecuta una sola vez por selección; el mapa se limpia en
   `_clear_project_page`.
3. **El follow-up sigue gateado por kind** (`FOLLOWUP_KINDS` =
   sn/hads/variable, `core/project.py` L37): la pestaña se oculta en la
   barra para los demás kinds y un deep-link a ella es un **no-op seguro**
   (`_ensure_tab_built`/`_show_tab` no construyen lo que no existe).
4. **La tarjeta «Siguiente» sigue siendo el banner global** entre
   masthead y página: su *Go* no despliega una sección, **cambia de
   pestaña** (`_show_tab`); *Mark done / Skip* avanzan el ciclo y pintan el
   chip de estado en la barra (pendiente · omitido · hecho %fecha).
5. **Contrato de deep-links idéntico** al del acordeón: `"files"` →
   pestaña *Object card* plegando la caja de archivos, `None` → no-op,
   cualquier otro key → abrir esa pestaña. El resto de la app
   (dashboard, chips de cadencia, doble clic) no cambia una línea.

**Consecuencias**: el hub se lee como 5 lugares, no como 5 cajones; la
memoria se gana por construir solo el tab abierto (cada builder pesa); el
estado por paso sigue siendo de `project.steps` (los chips pintan, las
pestañas navegan). Se jubila `_page_sections`/`CollapsibleSection` de la
página de proyecto (la sección *Files* sigue siendo plegable dentro de la
*Object card* — es un cajón, no un lugar). `project_row`/`campaign_row` no
cambian. Tests: `tests/unit/test_project_tabs.py` (25) + `test_projects_hub.py`
(97) + 55 tests de hads/transit/neo/campaigns re-dirigidos a la API de
pestañas.

## English

**Context**: the UX track (UD) folded the step tabs into a **single page of
collapsible sections**: one accordion with *Object card · Plan · Process ·
Publish · Follow-up*, and the "Next" card as a global banner. It worked,
but reviewing the UX, the observer noted the page "unstacks" everything at
once — five blocks, several collapsed by default — and the eye can't
separate *where I am* from *what I'm missing*. An accordion is a list of
drawers; a tab bar is a map. And the "Next" card already told the truth —
the navigation should now look like it.

**Decision** (agreed with the observer, 2026-09-19):

1. **A flat 5-tab bar over the page** (replaces the step trail, not a
   `QTabWidget`): *Object card · Plan · Process · Publish · Follow-up*.
   Five flat checkable `QPushButton`s in `projects_tab.ui` (`tabLayout`,
   `btn_tab_details/plan/process/publish/followup`), visual state via
   `theme.tab_state_style` (`theme.py`): normal / hover / checked with the
   project's kind colour.
2. **One visible tab at a time; pages build lazily** (`main_window.py`):
   `self._tab_pages` (key → QWidget) and `self._active_tab`. Only what is
   opened gets built — the first one plus the "Next" card's target when a
   project is selected (`_build_project_page` → `_show_tab(next
   target)`), the rest on first click. Each builder
   (`_build_{plan,process,publish,followup}_tab`) runs once per selection;
   the map is wiped in `_clear_project_page`.
3. **Follow-up stays kind-gated** (`FOLLOWUP_KINDS` = sn/hads/variable,
   `core/project.py` L37): the tab is hidden on the bar for other kinds,
   and a deep link to it is a **safe no-op**
   (`_ensure_tab_built`/`_show_tab` never build what doesn't exist).
4. **The "Next" card stays the global banner** between masthead and page:
   its *Go* no longer expands a section — it **switches tabs**
   (`_show_tab`); *Mark done / Skip* advance the step and paint the state
   chip on the bar (pending · skipped · done %date).
5. **Deep-link contract unchanged** from the accordion: `"files"` → the
   *Object card* tab with the files box expanded, `None` → no-op, any
   other key → open that tab. The rest of the app (dashboard, cadence
   chips, double-click) changes not a line.

**Consequences**: the hub reads as 5 places, not 5 drawers; memory wins by
building only the open tab (each builder is heavy); per-step state still
lives in `project.steps` (the chips paint, the tabs navigate).
`_page_sections`/`CollapsibleSection` retires from the project page (the
*Files* box stays a collapsible inside the *Object card* — a drawer, not a
place). `project_row`/`campaign_row` unchanged. Tests:
`tests/unit/test_project_tabs.py` (25) + `test_projects_hub.py` (97) + 55
hads/transit/neo/campaigns tests re-pointed to the tab API.
