# NightScribe — Guided workflows (UX v3)

*[Versión en español](WORKFLOWS.es.md)*

Master document of the project-centric redesign. Decisions: **ADR-019** (projects UX),
**ADR-020** (horizon & constraints), **ADR-021** (sequence & ephemeris exports),
**ADR-022** (MPC report). This document describes **what** gets built and in **which
order**; no code exists yet (2026-08-24).

## 1. The observer's question

"What can I do tonight — or right now?" The app answers by suggesting the most
interesting targets **under the observatory's real constraints**, and from the chosen
one a **project** is born that guides everything else without re-asking anything.

## 2. Constraints the planner must honour

| Constraint | Source | Effect |
|---|---|---|
| Limiting magnitude | `limit_mag` in config (equipment) | **Hybrid (ADR-025)**: hard cut for SNe/comets/exoplanets, `⚠ mag>N` warning for NEOs/PCCPs — never dropped |
| Local horizon | User's TheSkyX file (ADR-020) | Minimum altitude per azimuth + safety margin; fallback to flat `min_alt` |
| Moon | `ephem_minor` (ADR-009) | Warning + score penalty by separation/illumination; **not** a hard filter |
| Session feasibility | `core/exposure.py` + horizon | The window must cover the session duration; "safe start until HH:MM" is shown |
| Plate scale | Camera profile (`pixel_um`, `focal_mm`) | Maximum trailing-free exposure for NEOs |

## 3. Anatomy of a project

Persistent entity (ADR-019): kind, target, status (`active`/`done`/`archived`), full
JSON context and five guided steps. Context is captured when the project is created
from Tonight (target snapshot: coords, mag, rate, window…) and enriched at each step
(exported sequence, imported FITS, measurements, posts).

**Steps**: Plan → Capture → Process → Analyse → Publish.

## 4. Flow — supernova / transient

1. **Plan**: card with current magnitude, age, host galaxy, window above the real
   horizon and "safe start until HH:MM". The user sets N frames × exposure and filter;
   the app checks the session ends inside the safety range.
2. **Capture**: export sequence (NINA JSON / CCDciel / CSV) with name, J2000 coords
   and times; the file is registered in the project.
3. **Process** (external): the user calibrates/stacks with their own tools; back in
   NightScribe, "Import result FITS" — **without asking for target or coordinates**
   (already in context).
4. **Analyse**: blink with matched PS1-g (pre-filled ADR-018 pipeline), labelling,
   GIF/MP4/PNG with observatory watermark.
5. **Publish**: ES/EN story + tweet with the **real session data** (date, N×t, filter)
   + observed/posted marks in history.

## 5. Flow — NEO / PCCP candidate

1. **Plan**: card with apparent rate (″/min) and **maximum trailing-free exposure**
   computed from the equipment's plate scale; frame count; window and "safe start".
   Warning if the session would end outside the safety range.
2. **Capture**: export **ephemerides** at a configurable step for TheSkyX and Cartes
   du Ciel (formats validated against real imports in phase 5; CSV as the base) +
   sequence for the capture software.
3. **Process**: the user measures externally (Astrometrica or other) and **pastes**
   the measurements into the project → validation (80-col/ADES, MPC code, designation)
   → packaged file ready to email to the MPC (ADR-022). Sending is done by the user.
4. **Analyse**: orbital interpretation with context — family, MOID, size from H, next
   close approach (reuses `enrich.py` + `orbits.py`).
5. **Publish**: ES/EN story + `orbit_view`/`sky_view` + observed/posted marks +
   NEOfixer report if an API key is configured.

## 6. Later flows

Comets and exoplanet transits reuse the same 5-step skeleton once the SN and NEO flows
are settled. Out of this initial redesign.

## 7. Roadmap and entry point

| Phase | Deliverable | Status |
|---|---|---|
| 1 | ADR-019…022 + this document + updated DESIGN | **Done (2026-08-24)** |
| 2 | Constraint foundation: `core/horizon.py`, Moon, `core/exposure.py`, camera profile in config, planner/suggest integration, horizon silhouette in `sky_view`, tests | **Done (2026-08-24)** |
| 3 | Project model: db migration (`user_version` 0→1), `core/project.py`, step machine, tests | **Done (2026-08-24)** |
| 4 | GUI v3: 4 tabs, Projects hub with per-kind stepper, contextual blink, Tonight cards with "Create project" and "safe start", Settings (Camera/Horizon/Session/Moon), i18n | **Done (2026-08-24)** |
| 5 | Exporters: `core/sequence.py` (NINA/CCDciel/CSV) + ephemerides (CSV + TheSkyX + CdC validated against real imports), tests | **Done (2026-08-24)** |
| 6 | `core/mpc_report.py` + step in the NEO flow + minimal CLI `project` subcommand + polish, i18n and final docs | **Done (2026-08-24)** |

### 7bis. Home screen redesign (2026-08-25)

Why: the «Tonight» screen did not match the app's look, it never explained
**why** each target is suggested (the "why tonight" phrase only lived in the
tooltip) and the 4×2 grid of mini-cards felt cramped. The app also had no
global theme: dark cards floating over the platform's light chrome.

| Phase | Deliverable | Status |
|---|---|---|
| A | Global dark theme: `gui/theme.py` (palette + chrome QSS + `KIND_COLORS`), `apply_theme(app)` in `app.py`, ADR-026, `tests/unit/test_theme.py` | **Done (2026-08-25)** |
| B | «Tonight» as a **vertical list of wide rows**: name, visible "why tonight" line, chips (mag/alt/window/moon/⚠), 4-segment score mini-bar, 0-100 score, Start/Continue button, subtle metallic top-3 podium, row-click→Explore, loading/empty states | **Done (2026-08-25)** |
| C | Redesigned «Full target list» table over the theme, double-click→project, ES/EN i18n regeneration of the new strings, smoke tests | **Done (2026-08-26)** |

**Phase C (done, 2026-08-26)**: the table is kept and now behaves like the
wide rows above it — row-level selection (no cell 2×2, no row numbers),
every row tinted with its kind color, the top 3 (score order) wearing a
stronger tinge as a quiet podium, bold name + score in the kind color,
headers/selection/hover from the global theme (ADR-026). Double-click from
*any* column starts/continues the project. Code in
`nightscribe/gui/main_window.py` (`_prepare_table`, `_fill_table`,
`_table_start_project`) + `tonight_tab.ui` (tooltip). New strings
translanted ES/EN and `.ts`/`.qm` regenerated (ADR-014). Smoke tests in
`tests/unit/test_tonight_table.py` (pattern of `test_tonight_rows.py`).

### 7ter. Phase D — the object view as the Projects hub's lead (2026-08-26)

Motivation: opening a project showed the **Plan** first (frames × exposure), but
without an object there is no plan. The object's "business card" — today only
inside the modal *Explore…* dialog — must be the first and always-visible panel.
**Nothing new is built**: everything already exists (enrich, narrative, orbits,
charts, exposure); the work is **unifying it into a fixed panel**, attractively
laid out, with no clipped text (multiline, everything visible).

**Agreed decisions (2026-08-26)**:

1. The object view is a **fixed panel above the Plan/Capture/Process/Analyse/
   Publish tabs** in the Projects hub. It is not a step: it cannot be skipped or
   "marked done"; it stays out of the 5-step machine.
2. It contains (all pre-existing): **hook line** + **outreach bullets** +
   **parameter table with multiline ES/EN explanations** + **the 4 charts**
   (orbit, sky, families, field) + **capture/window block** (mag, ″/min rate,
   max no-trail exposure where applicable, window start–end, hours above).
3. A **shared panel is extracted to `gui/overview.py`** (`ObjectPanel`) used by
   the Projects hub **and** the ad-hoc *Explore…* dialog: one source of truth.
4. **Untouched**: all of `core/`, the step machine (`core/project.py`,
   `_STEP_KEYS`) and the *Plan* panel (its max-exposure calculator keeps living there).

**Reused pieces, unmodified** (with their current home):

| Piece | Origin |
|---|---|
| Enrich (network, cache) | `gui/workers.py` `ExploreWorker` → `core/enrich` |
| Hook line, bullets | `core/narrative.hook`, `core/narrative.fact_bullets` |
| Parameters + ES/EN explanation | `core/orbits.explain_elements`, `core/orbits.explain_neofixer` |
| 4 PNGs (orbit/sky/families/field) | `core/post.build_charts` (`core/post.py:172`) |
| Max no-trail exposure (NEO) | `core/exposure.plate_scale` + `max_exposure_no_trail` |
| Mag, rate, window, hours | `project.context` (snapshot, `gui/main_window.py:1474`) |
| Chart click → zoom/export | `gui/main_window.py:74` `_ChartClickFilter` |
| ES/EN pair language | `orbits.pick` (pattern of `MainWindow._txt`) |

**Current state being reorganised**: the object presentation currently lives only
in the modal dialog `gui/main_window.py:1504` (`_open_explore_dialog`,
`_dialog_explore_params`:1551, `_dialog_explore_charts`:1588,
`_render_object_charts`:1572), opened via step 4 *Analyse*
(`_build_analyse_tab`:1197). The Projects hub shows *Plan* first and a one-line
truncated `lbl_context` header (`gui/ui/projects_tab.ui:51`).

| Phase | Deliverable | Acceptance | Status |
|---|---|---|---|
| **D1** | `gui/overview.py`: `ObjectPanel` without charts — *loading / not found / ready* states, hook line, bullets, parameter table with a wide (multiline) explanation column. `show(e, ctx=None)` + injectable `loader` (offscreen, no network). GPL header, ES/EN pairs | Panel built offscreen; with fake `e`: hook visible, parameter rows with explanation; with `{}`: *not found* state | **Done (2026-08-26)** — `gui/overview.py` + `tests/unit/test_overview_panel.py` (9 offscreen tests, no network) |
| **D2** | `ObjectPanel` with a **2×2 chart grid** filled by `core/post.build_charts`; "why not" messages (hyperbolic / no elements / unconfirmed) scaled to the widget | With fake `e`: 4 chart slots or the right absence messages; without `e`: empty | **Pending** |
| **D3** | `ObjectPanel` with **capture/window blocks** from `ctx`: mag, ″/min rate, max no-trail exposure (neo/pccp only, with rate + `pixel_um`/`focal_mm`), window start–end + hours above; missing data is omitted | With a fake neo `ctx`: full chips; with an sn `ctx`: no rate/exposure; does not break on empty `ctx` | **Pending** |
| **D4** | **Integration in the hub**: `projects_tab.ui` inserts `ObjectPanel` between `lbl_context` and `tabs_steps` (keep/replace `lbl_context` decided here). On project selection → `loader` = `ExploreWorker` (same `fallback_target` from the context), worker kept via `_keep`, signals disconnected when switching project | Without network: selecting a project shows *loading* state and does not crash; step machine, plan panel and buttons stay intact; offscreen smoke tests | **Pending** |
| **D5** | ***Explore…* dialog over the shared panel**: `main_window.py:1504` becomes `ObjectPanel` + a *Make post* button; the `_dialog_explore_*` functions delegate to the panel; chart click→zoom is kept (the panel exposes its chart labels); `_project_explore` (step 4) / `_tools_explore` keep working | The Tools-menu *Explore…* dialog is identical in content; the NEO step 4 still opens it pre-filled | **Pending** |
| **D6** | **i18n + verification + docs**: `lupdate`/`lrelease` → `nightscribe_{es,en}.ts/.qm` (ADR-014); `pytest tests/unit` green; this section with final statuses | New strings translated ES/EN; smoke tests in `tests/unit/test_overview_panel.py` (D1-D3) + hub smoke (D4) green | **Pending** |

**Per-phase rules**: one phase = one commit; each phase leaves the app working
with its tests; two phases are never mixed before the previous one is verified
(rule of this document, §7). Offscreen tests follow the
`tests/unit/test_tonight_table.py` pattern (QApplication + `theme.apply_theme`
+ panel directly + fake payloads, no network).

**ENTRY POINT (for any AI or human resuming Phase D)**:

1. Read this section 7ter in full, in order.
2. Start with **D1** (`gui/overview.py`), validate the base, then proceed
   D2 → D3 → D4 → D5 → D6 in order.
3. **Do not touch** `core/` or the step machine; if it turns out necessary,
   stop and open a new ADR/decision before writing the minimum.
4. GPL header mandatory in every new `.py`, code in English, GUI-visible
   strings via `self.tr()` and ES/EN pairs via `orbits.pick` (or `tr()` for
   the static ones). Active language: `config.get("language")` (pattern
   `MainWindow._lang`, `gui/main_window.py:227`).
5. Phase D is **independent** of the "suggested next steps" that follow below
   (real horizon, native formats, comet/transit flows).

Before Phase D, the historical **ENTRY POINT** (UX v3 project, phases 1-6):

1. Read, in this order: `docs/adr/ADR-019`, `ADR-020`, `ADR-021`, `ADR-022` and this
   full document.
2. Phases 2 and 3 are already implemented on branch `feature/ux-v3-projects`:
   - Phase 2: `core/horizon.py`, `core/exposure.py`, helpers in `coords.py`, Moon
     penalty in `suggest.py`, planner integration in `planner.py`, silhouette in
     `viz/sky_view.py`, extended config, mock `tests/fixtures/horizon_sample.txt` + tests.
   - Phase 3: `core/db.py` migration (`user_version` 0→1: tables `projects`,
     `project_steps`, `project_files`; `observations` += `project_id`), `core/project.py`
     (model + step machine Plan→Capture→Process→Analyse→Publish), tests.
   - Phase 4: GUI v3 — 4 tabs (Tonight · Projects · Solar · History),
     `projects_tab.ui` with list + stepper, Explore/Post/Blink as contextual modal
     dialogs (pre-filled from project), ad-hoc access from the Tools menu, Tonight cards
     with "Create project" + window + Moon, Settings extended with Camera/Horizon/
     Session/Moon groups, `sky_view` with real horizon, i18n (.ts/.qm) updated.
   - Phase 5: `core/sequence.py` (NINA JSON / CCDciel XML / generic CSV capture
     sequence exporters) and `core/ephemeris.py` (Horizons-based generation + CSV /
     TheSkyX / Cartes du Ciel ephemeris exporters). "Capture plan" panel in the Projects
     hub with frames/exposure/filter fields and export buttons. The native NINA/CCDciel/
     TheSkyX/CdC formats are starting points that require validation against the user's
     software versions via real import.
   - Phase 6: `core/mpc_report.py` (validator for pasted measurements in MPC 80-col or
     ADES PSV: format, observatory code, designation; file packaging for MPC submission).
     "MPC report" panel in the Projects hub. CLI subcommand
     `nightscribe project list|create|advance|show`. Full i18n (208 strings ES/EN).
     **All phases complete.**
   The **real TheSkyX horizon** is still mocked: when the user shares their file,
   replace the parser/fixture in `core/horizon.py` validating against that file (ADR-020).
   The **native NINA/CCDciel/TheSkyX/CdC formats** are starting points that require
   validation against the user's software versions via real import (ADR-021).

**Suggested next steps** (beyond the initial redesign):
- Replace the mocked horizon with the user's real TheSkyX file.
- Validate the sequence and ephemeris export formats against real software.
- Add flows for comets and exoplanet transits in the same 5-step skeleton.
- Test the GUI thoroughly and refine the stepper and contextual dialog UX.
4. Standing rules: English code with GPL header and `# @args:` comments, GUI strings
   via `self.tr()`, network only from `core/sources/` through `core/db.py`, bilingual
   documentation (ADR-013), unit tests per module + end-to-end functional tests.

Each phase leaves the app working and ships its own tests. Do not mix phases in one
commit without the previous one being verified.
