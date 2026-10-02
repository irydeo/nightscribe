# ADR-041: La página del proyecto como barra de pestañas perezosas / The project page as a lazy tab bar

**Estado / Status**: Accepted · **Fecha / Date**: 2026-09-19 · **ejecutado /
executed**: 2026-09-19 (`test_project_tabs.py` 25 + `test_projects_hub.py` 97
+ suite unitaria 1391 green) · **Enmendado / Amended**: 2026-10-02
(Interfaz 1.7: el cromo del proyecto baja de cinco filas a tres, las
páginas dejan de repetir el nombre de su pestaña, Análisis pone las
visitas y la curva una al lado de la otra, y las gráficas declaran su
tamaño; `test_project_tabs_layout.py` fija el criterio: **ninguna de las
dos pestañas hace scroll** a 1360x940 ni a 1360x860)

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

**Enmendado por ADR-043 (2026-09-21)**: los nombres *Plan · Proceso ·
Publicar · Follow-up* eran solo de pantalla (ahora *Captura · Seguimiento
· Follow-up · Bitácora*; las claves `plan/process/publish/followup` se
mantienen estables); el Skip de la tarjeta «Siguiente» se jubila (cada
paso conserva su pie «Skip step»); la pestaña Observatory del main window
desaparece y su control pasa al paso Captura.

**Enmendado por ADR-045 (2026-09-24)**: la barra pasa a cuatro pestañas
(Ficha → Captura → Análisis → Publicación): la clave `process` se
renombra `analysis` (migración v8) y la pestaña Seguimiento desaparece
como tal (su contenido vive en Análisis, construida sobre el gestor de
visitas, para todos los tipos). Las claves retiradas `process` y
`followup` quedan como alias permanentes de `analysis` para los deep
links. La barra sigue siendo una fila de botones planos en
`projects_tab.ui`, una página visible a la vez, lazy build, y el
contrato de deep link se mantiene.

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

**Amended by ADR-043 (2026-09-21)**: the tab names *Plan · Process ·
Publish · Follow-up* were display-only (now *Capture · Track · Follow-up
· Worklog*; the keys `plan/process/publish/followup` stay stable); the
"Next" card's Skip retires (each step keeps its "Skip step" footer); the
main window's Observatory tab is gone and its control moves into the
Capture step.

**Amended by ADR-045 (2026-09-24)**: the bar drops to four tabs (Object
card → Capture → Analysis → Publish): the `process` key is renamed
`analysis` (migration v8) and the Follow-up tab as such is gone (its
content lives in Analysis, built around the visits manager, for every
kind). The retired `process` and `followup` keys stay as permanent
aliases of `analysis` for deep links. The bar remains a row of flat
buttons in `projects_tab.ui`, one page visible at a time, lazy build,
and the deep-link contract holds.

**Amendment (2026-10-02, Interfaz 1.7: the tabs stop scrolling).** The
pages had grown past the fold: with a project holding a visit, its frames
and a measured curve, the Object card asked for 499 px and Analysis for
1058 in a 537 px viewport. Four changes, all of them measured:

1. **The project chrome drops from five rows to three** (~75 px in every
   tab): the four small buttons (`»`, `⌂`, `☆`, `⋯`) and the context line
   (`mag · RA · Dec`) move into the masthead row, and the "Next" box stops
   being a `QGroupBox` (a slim band keeps the action and its two buttons).
2. **A page no longer repeats its tab's name.** `_section_layout` drew a
   bold title above the content that said exactly what the active tab
   already said: 25 px spent twice. The state chip stays, in a slim row.
3. **Analysis puts the visits and the curve side by side.** Stacked they
   asked for ~800 px; as a master-detail pair (visits left, curve right)
   they fit in ~330, and the reading is better: pick the visit, read its
   curve. The visits list grows with its content (capped) instead of
   reserving a fixed 180 px box.
4. **Charts declare their size.** `QGraphicsView` has no `sizeHint` of its
   own and answers with the SCENE's, which is whatever the data spans (a
   light curve asked for 520 px). `ChartView.sizeHint()` is 640x260, and
   the layout's stretch still grows them where there is room.

Along the way, three real bugs surfaced: the chips of the object card
stretched into slabs (a trailing stretch lost on every refill), the
parameters table clipped its last row (a `QTableWidget`'s sizeHint uses
the DEFAULT row height, so wrapped explanations did not count), and the
light curve printed its legend on top of its axis labels (the legend's
geometry was in fixed scene units while its font is pinned to pixels).

**The criterion is a test** (`tests/unit/test_project_tabs_layout.py`):
with a project that has a visit, its frames and a curve, **neither the
Object card nor Analysis may ask for more than the scroll viewport** at
1360x940 and at 1360x860.

**Amendment (2026-10-02, Interfaz 1.8: the night, drawn).** The three
project tabs (Object card, Capture, Analysis) had the same problem the
Welcome view had before Interfaz 1.4: they were correct and told you
nothing at a glance. The fix is the same trick, applied to ONE object: a
painted night with real numbers.

1. **`gui/widgets/night_ribbon.py`**, a band ~58 px tall (30 px of sky, 16
   of caption, 12 of padding): the twilight → night → twilight gradient,
   the astronomical window, the object's altitude arc, the Moon at its real
   phase, a marker for "now", any number of coloured blocks on the timeline
   and a caption of numbers, elided rather than cut. Local (`core/coords` +
   `core/night_brief` + `gui/moon_icon`), no network, and tolerant: no
   site, no coordinates, no astronomical night or an object that never
   rises all draw something honest ("never rises tonight", "max 12°: too
   low"). Its height is FIXED: a band that stretches is how a 58 px strip
   becomes a 200 px empty box.
2. **One widget, three readings**: the Object card draws the object's
   night; Capture drops the PLAN on it as a block with the verdict ("fits:
   30 min of 9.2 h" in green, "does not fit before dawn" in amber);
   Analysis drops the selected VISIT's frames on the night they happened.
3. **The Object card goes two-column**: the parameters table (left, 60%)
   and the band + the charts (right, 40%). Stacked they asked for 836 px
   in a 631 px page; together, 520. The table became a **definition list**
   (two columns: the value, and its explanation UNDER it across both):
   as a third column in a half-width card it wrapped to one word per line,
   and the explanation row is measured by hand because Qt sizes a spanned
   cell against the first column's width only.
   With **no charts yet** (a brand new project) the right column would be
   empty, so the band moves to the full width, above the table: the card
   fills the page and the explanations stop wrapping. That case asks 549 px
   in a 551 px viewport at 1360x860, which is the tightest number in the
   whole design.
4. **"In depth" is on by default** (the observer asked for it).
5. **Capture is one control panel, not three group boxes** ("Telescope and
   camera": the connection, the status, the pointing and the live capture
   in four rows), and the observatory status is a single row of four pairs
   instead of a four-row form. With CCDciel connected the page asked for
   712 px in a 551 px viewport, which put the status (the reason you
   connect at all) 161 px BELOW the fold.
6. **Colour with meaning**: the connection is a chip (green `● CCDciel:
   127.0.0.1:3277 · 0.9.9` / amber `● CCDciel: not connected`), and the
   status values are tinted by what they say (tracking green, stopped
   amber, slewing blue, idle grey). No decorative colour.

**The criterion holds and grew**: with a project that has a visit, its
frames and a curve, **all four tabs fit the viewport** at 1360x940 and at
1360x860 (Object card 520, Capture 509, Analysis 532, Publish 95, against
631 and 551), and the Capture tab also fits **with CCDciel connected**
(533). The Ficha with no charts yet fits at 549, and below 1360x860 the
card scrolls: the two-column layout needs the width and there is a point
where the honest answer is a scrollbar.

`tests/unit/test_project_tabs_layout.py` holds the criterion, including
the connected case, and `tests/unit/test_night_ribbon.py` holds the band's
honesty in every state it can be put in.
