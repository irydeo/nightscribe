# ADR-043: La pestaña Observatory se pliega en el paso Captura / the Observatory tab folds into the Capture step

**Estado / Status**: Accepted · **Fecha / Date**: 2026-09-21 · **ejecutado /
executed**: 2026-09-21 (suite unitaria 1494 green, i18n 0 unfinished) ·
**Enmendado / Amended**: 2026-09-22 (los nombres de paso pasan a la lista
autoritativa del observador; se retira por completo el Skip de la UI; el
bloque CCD se ata directamente al proyecto actual, sin combo de objetivos)
· 2026-09-24 (ADR-045: la lista autoritativa de pasos pasa a Ficha →
Captura → Análisis → Publicación; «Procesado» se renombra «Análisis» y la
pestaña Seguimiento se disuelve en ella — Captura no cambia en absoluto)

**Ver / See**: ADR-030 (cliente CCDciel JSON-RPC; el control de hardware no
cambia) · ADR-038 (prominencia a 3 niveles y lenguaje llano) · ADR-041 (la
barra de pestañas del proyecto; enmendado por esta decisión) ·
`docs/WORKFLOWS.md` (Track UX, sub U3 «CCDciel → Observatory», enmendado por
esta decisión).

## Español

**Contexto**: el Track UX (sub U3, ADR-041) sacó el control de CCDciel de la
página del proyecto y le hizo una **pestaña de primera clase del main
window**, cuatro pestañas en total (Tonight · Projects · Campaigns ·
Observatory). La decisión era buena en su momento: el hardware no debe
matarse con un rebuild de proyecto. Pero al repasar la app con el
observador quedó clara la fricción:

1. **La pestaña no pertenece a ningún flujo.** Se llama «Observatory», no
   a ningún proyecto, y sin embargo solo importa cuando vas a capturar.
   Una consola de hardware flotando entre pestañas que son flujos.
2. **Las pestañas de paso no decían lo que el observador hace.** *Plan ·
   Process · Publish* son verbos de software; el observador **captura**
   (o prepara la captura), **sigue** al objeto y **escribe la bitácora**.
3. **El «Save plan» era una duda en lugar de un hecho.** El botón
   existía, la app avisaba, y aun así el observador preguntaba «¿se
   guardó?», porque había una cosa (el guardado) que no se veía.
4. **Dos Skip, dos lenguajes.** La tarjeta «Siguiente» ofrecía un Skip y
   cada paso ofrecía otro; el Skip de tarjeta era el más visible y el
   menos concreto (¿omitir qué?).

**Decisión** (pactada con el observador, 2026-09-21):

1. **La pestaña Observatory se jubila**: `main_window.ui` pierde
   `tab_observatory` y `observatory_tab.ui` se elimina. El main window
   queda a **tres pestañas** (Tonight · Projects · Campaigns, Ctrl+1..3).
2. **El paso Captura es dueño del hardware**: `main_window.py` construye
   el panel completo (conexión, estado del observatorio, telescopio,
   captura) con `_build_capture_ccd_block`, **dentro de la pestaña
   *plan* de cada página de proyecto**. El panel registra sus 14
   controles en `window._obs_widgets`; `_clear_project_page` lo vacía a
   `{}` y cada slot de CCD se guarda contra la ausencia (el bloque muere
   con la página; los slots nunca tocan widgets muertos). El bloque
   trabaja directo sobre el **proyecto actual**
   (`window._current_project`): no hay combo de objetivos, y sin
   proyecto abierto los botones de captura y goto se deshabilitan con la
   pista «Abre primero un proyecto (el paso Captura lo necesita)». El
   cliente
   (`core/sources/ccdciel.py`, caché 60 s) y los workers no cambian
   (ADR-030). Las cadenas `tr()` re-utilizan las antiguas anclas de
   «ObservatoryTab», que quedan en el contexto «MainWindow» sin
   re-traducir.
3. **El plan se guarda solo, en silencio**: los seis controles
   (`spn_nframes`, `spn_exps`, `cmb_filter`, `spn_darks`, `spn_darkexp`,
   `spn_bias`) conectan a `_project_save_plan` al construirse, *después*
   de los `setValue()` de arranque, así el payload (incluida la ventana
   segura re-derivada, ADR-020) se escribe solo cuando el observador toca
   algo. No hay botón de guardar y no hay destello «Plan saved»: la
   verdad visible es la barra del proyecto.
4. **Los pasos se renomean en el lenguaje del observador** (solo
   visual; las claves internas no cambian):

   | clave estable | antes ES | ahora ES | antes EN | ahora EN |
   |---|---|---|---|---|
   | `details` | Ficha | Ficha | Details | **Object card** |
   | `plan` | Plan | **Captura** | Plan | **Capture** |
   | `process` | Proceso | **Procesado** | Process | Process |
   | `publish` | Publicar | Publicar | Publish | Publish |
   | `followup` | Follow-up | **Seguimiento** | Follow-up | **Follow-up** |

   Los dicts viven en `main_window.py` (`_STEP_LABELS_ES/EN`): las
   claves de paso `details/plan/process/publish/followup` y los nombres
   de botones `btn_tab_*` de `projects_tab.ui` se mantienen, de modo que
   deep-links, tests y la API de pestañas no cambian. El menú
   Herramientas y el menú contextual del hub dicen ahora «Seguimiento» /
   «Follow-up».
5. **El Skip desaparece de la UI**: el botón de la tarjeta «Siguiente» y
   el pie «Skip step» de cada paso se retiran del código (la tarjeta
   queda a **Go + Mark done**). El estado `STEP_SKIPPED` de la API del
   core y de la base de datos **se conserva** (las filas antiguas quedan
   legibles y reabribles con «Reopen step», que aparece también en los
   pasos hechos). Saltar un paso deja de ser una acción que la app
   ofrezca.
6. **La barra se lee como una flecha**: separadores «→» entre los
   botones de la barra (`lbl_sep_plan/process/publish` en
   `projects_tab.ui`); el último (`lbl_sep_followup`) solo se muestra
   para los kinds con follow-up (`FOLLOWUP_KINDS`, ADR-041 punto 3).

**Consecuencias**: la ventana principal deja de ser un flujo con una
consola colgada; el hardware tiene una sola casa (el paso que lo usa) y
muere con la página, que es el precio de construirlo por proyecto. La
pestaña *plan* pesa un poco más al construirse. i18n: el contexto
«ObservatoryTab» desaparece de las tablas compiladas (innocuo); las 10
cadenas nuevas del contexto «MainWindow» van traducidas ES/EN. Tests:
`test_observatory_tab.py` re-escrito sobre el bloque embebido
(3 pestañas + `_obs_widgets` + estado desconectado + atado al proyecto
actual); `test_project_tabs.py` (tarjeta a 2 botones + reabrir paso
hizo/saltado); `test_projects_hub.py` (envío de plan al proyecto
actual, menú con «Seguimiento»; sin combo de objetivos),
`test_campaigns_tab.py`, `test_sunsky_tab.py` y el test de arranque
funcional pasan de 4 a 3 pestañas.

## English

**Context**: the UX track (sub U3, ADR-041) pulled CCDciel control out
of the project page and gave it a **first-class main-window tab**, four
tabs in total (Tonight · Projects · Campaigns · Observatory). That was
the right call at the time: hardware must not die with a project
rebuild. But reviewing the app with the observer made the friction
clear:

1. **The tab belongs to no flow.** It is called "Observatory", it is
   not about any project, and yet it only matters when you are about to
   capture. A hardware console floating between flow tabs.
2. **The step tabs did not say what the observer does.** *Plan ·
   Process · Publish* are software verbs; the observer **captures** (or
   prepares the capture), **tracks** the object and **keeps the
   worklog**.
3. **"Save plan" was a doubt, not a fact.** The button existed, the app
   confirmed, and the observer still asked "did it save?", because there
   was one thing (the saving) that was not visible.
4. **Two Skips, two dialects.** The "Next" card offered a Skip and each
   step offered one too; the card's Skip was the most visible and the
   least specific (skip what?).

**Decision** (agreed with the observer, 2026-09-21):

1. **The Observatory tab retires**: `main_window.ui` loses
   `tab_observatory` and `observatory_tab.ui` is deleted. The main
   window drops to **three tabs** (Tonight · Projects · Campaigns,
   Ctrl+1..3).
2. **The Capture step owns the hardware**: `main_window.py` builds the
   whole panel (connection, observatory status, telescope, capture)
   with `_build_capture_ccd_block`, **inside the *plan* tab of each
   project page**. The panel registers its 14 controls in
   `window._obs_widgets`; `_clear_project_page` empties it to `{}` and
   every CCD slot guard-checks its keys against absence (the block dies
   with the page; slots never touch dead widgets). The block works
   straight on the **current project**
   (`window._current_project`): there is no target combo, and with no
   project open the capture and goto buttons stay disabled with the
   hint "Open a project first (the Capture step needs one)". The client
   (`core/sources/ccdciel.py`, 60 s cache) and the workers do not
   change (ADR-030). The `tr()` strings reuse the old
   «ObservatoryTab» anchors, so they land in the «MainWindow» context
   already translated.
3. **The plan auto-saves, silently**: the six controls
   (`spn_nframes`, `spn_exps`, `cmb_filter`, `spn_darks`, `spn_darkexp`,
   `spn_bias`) connect to `_project_save_plan` when built, *after* the
   startup `setValue()` calls, so the payload (including the re-derived
   safe window, ADR-020) is written only when the observer touches
   something. No save button, no "Plan saved" flash: the visible truth
   is the project bar.
4. **The steps are renamed in the observer's language** (display only;
   the stable keys do not change):

   | stable key | ES before | ES now | EN before | EN now |
   |---|---|---|---|---|
   | `details` | Ficha | Ficha | Details | **Object card** |
   | `plan` | Plan | **Captura** | Plan | **Capture** |
   | `process` | Proceso | **Procesado** | Process | Process |
   | `publish` | Publicar | Publicar | Publish | Publish |
   | `followup` | Follow-up | **Seguimiento** | Follow-up | **Follow-up** |

   They live in `_STEP_LABELS_ES/EN`: the step keys
   `details/plan/process/publish/followup` and the `btn_tab_*` names of
   `projects_tab.ui` stay, so deep links, tests and the tab API do not
   change. The Tools menu and the hub context menu now say
   "Follow-up" / «Seguimiento».
5. **The Skip disappears from the UI**: the "Next" card button and the
   per-step "Skip step" footer are removed from the code (the card is
   down to **Go + Mark done**). The `STEP_SKIPPED` state of the core API
   and of the database is **kept** (legacy rows stay readable and
   reopenable with "Reopen step", which now also appears on done
   steps). Skipping a step is no longer an action the app offers.
6. **The bar reads like an arrow**: "→" separators between the bar's
   buttons (`lbl_sep_plan/process/publish` in `projects_tab.ui`); the
   last one (`lbl_sep_followup`) is only shown for the kinds that have
   a follow-up (`FOLLOWUP_KINDS`, ADR-041 point 3).

**Consequences**: the main window stops being a flow with a console
hanging off it; the hardware has one home (the step that uses it) and
dies with the page, which is the price of building it per project. The
*plan* tab is a little heavier to build. i18n: the «ObservatoryTab»
context drops out of the compiled tables (harmless); the new
«MainWindow» context strings are translated ES/EN (the vanished anchors
«Skip step», «Target:», «Worklog» are left as-is, lrelease drops them).
Tests: `test_observatory_tab.py` re-written on the in-page block (3
tabs + `_obs_widgets` + disconnected state + bound to the current
project); `test_project_tabs.py` (card down to 2 buttons + reopen for
done/skipped steps); `test_projects_hub.py` (send plan to the current
project, menu with "Follow-up"; no target combo),
`test_campaigns_tab.py`, `test_sunsky_tab.py` and the functional boot
test drop from 4 to 3 tabs.
