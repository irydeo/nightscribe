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
JSON context and three guided steps. Context is captured when the project is created
from Tonight (target snapshot: coords, mag, rate, window…) and enriched at each step
(exported sequence, imported FITS, measurements, posts).

**Steps**: Plan & Capture → Process → Publish (ADR-019's 2026-09-06 review merged the
Capture step into Plan and added real CCDciel control — ADR-030).

## 4. Flow — supernova / transient

1. **Plan**: card with current magnitude, age, host galaxy, window above the real
   horizon and "safe start until HH:MM". The user sets N frames × exposure and filter;
   the app checks the session ends inside the safety range.
2. **Capture**: export sequence (NINA JSON / CCDciel / CSV) with name, J2000 coords
   and times; the file is registered in the project. **With CCDciel connected**
    (ADR-030) the same tab can also: point the telescope, run an **astrometric goto**
    (plate-solve + correction), send the plan (target, exposure, frame count, filter)
    and start the capture live.
3. **Process** (external): the user calibrates/stacks with their own tools; back in
   NightScribe, "Import result FITS" — **without asking for target or coordinates**
   (already in context) — then confirm with the blink, matched against PS1-g
   (pre-filled ADR-018 pipeline), and export GIF/MP4/PNG with the observatory
   watermark.
4. **Publish**: ES/EN story + tweet with the **real session data** (date, N×t, filter)
   + observed/posted marks in history.

## 5. Flow — NEO / PCCP candidate

1. **Plan**: card with apparent rate (″/min) and **maximum trailing-free exposure**
   computed from the equipment's plate scale; frame count; window and "safe start".
   Warning if the session would end outside the safety range.
2. **Capture**: export **ephemerides** at a configurable step for TheSkyX and Cartes
   du Ciel (formats validated against real imports in phase 5; CSV as the base) +
   sequence for the capture software. With CCDciel connected (ADR-030): send the plan
   and start the capture live.
3. **Process**: the user measures externally (Astrometrica or other) and **pastes**
   the measurements into the project → validation (80-col/ADES, MPC code, designation)
   → packaged file ready to email to the MPC (ADR-022). Sending is done by the user.
4. **Publish**: ES/EN story + `orbit_view`/`sky_view` + observed/posted marks +
   NEOfixer report if an API key is configured. The orbital interpretation itself
   (family, MOID, size from H, next close approach — reuses `enrich.py` + `orbits.py`)
   is not a step: it already renders in the *Details* tab the moment the project is
   opened.

## 6. Later flows

Comets and exoplanet transits reuse the same 3-step skeleton once the SN and NEO flows
are settled. Out of this initial redesign.

## 7. Roadmap and entry point

| Phase | Deliverable | Status |
|---|---|---|
| 1 | ADR-019…022 + this document + updated DESIGN | **Done (2026-08-24)** |
| 2 | Constraint foundation: `core/horizon.py`, Moon, `core/exposure.py`, camera profile in config, planner/suggest integration, horizon silhouette in `sky_view`, tests | **Done (2026-08-24)** |
| 3 | Project model: db migration (`user_version` 0→1), `core/project.py`, step machine, tests | **Done (2026-08-24)** |
| 4 | GUI v3: 4 tabs, Projects hub with per-kind stepper, contextual blink, Tonight cards with "Create project" and "safe start", Settings (Camera/Horizon/Session/Moon), i18n | **Done (2026-08-24)** |
| 5 | Exporters: `core/sequence.py` (NINA/CCDciel/CSV) + ephemerides (CSV + TheSkyX + CdC validated against real imports), tests | **Done (2026-08-24)**; CCDciel with the real `.targets` format (CONFIG v5) against `docs/ccdciel_sequence_sample.targets` (**2026-09-06**) |
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

1. The object view is a **fixed panel above the step tabs** (Plan/Capture/Process/
   Publish) in the Projects hub. It is not a step: it cannot be skipped or "marked
   done"; it stays out of the step machine.
   *(Revised 2026-08-27: it is now the **"Details" tab** — first and the one that
   stays open on project selection — same guarantee, the object always visible, but
   owning the full panel height. Revised again 2026-08-28 (ADR-019): the step list is
   now four — see ADR-019 review.)*
2. It contains (all pre-existing): **hook line** + **outreach bullets** +
   **parameter table with multiline ES/EN explanations** + **the charts**
   (orbit, sky, field, light curve — the ones build_charts cannot produce are
   hidden; with none, the group disappears) + **capture/window block** (mag, ″/min
   rate, max no-trail exposure where applicable, window start–end, hours above).
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
 | PNGs (orbit/sky/field/light curve) | `core/post.build_charts` (`core/post.py:172`) |
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
 | **D2** | `ObjectPanel` with a **2×2 chart grid** filled by `core/post.build_charts`; "why not" messages (hyperbolic / no elements / unconfirmed) scaled to the widget | With fake `e`: 4 chart slots or the right absence messages; without `e`: empty | **Done (2026-08-26)** — `orbit/sky/families/field` grid in `gui/overview.py` + 5 offscreen tests in `tests/unit/test_overview_panel.py` (14 total, offline; only `field` would touch the network and stays on a "why not" line) → **revised 2026-08-27** — no families (below), slots `orbit/sky/field/transit`, `panel` size (1200×675); unbuildable slots are hidden instead of a "why not" line; with no chart, the whole group disappears → **2026-09-06** — the produced charts are grouped into **tabs** (`QTabWidget` in `gui/overview.py`, one tab per chart, titled; with a single chart the tab bar auto-hides and it stands alone; the 2×2 grid is gone) |
| **D3** | `ObjectPanel` with **capture/window blocks** from `ctx`: mag, ″/min rate, max no-trail exposure (neo/pccp only, with rate + `pixel_um`/`focal_mm`), window start–end + hours above; missing data is omitted | With a fake neo `ctx`: full chips; with an sn `ctx`: no rate/exposure; does not break on empty `ctx` | **Done (2026-08-26)** — chip row in `gui/overview.py` (mag / rate / max no-trail exposure / window / hours, from `project.context`; rate and exposure only for neo/pccp) + 5 offscreen tests in `tests/unit/test_overview_panel.py` (19 total, no network). New `self.tr()` strings pending D6 i18n (D1/D2 pattern) |
 | **D4** | **Integration in the hub**: the hub inserts `ObjectPanel` between `lbl_context` and `tabs_steps` (keeping the `lbl_context` header). On project selection → `loader` = `ExploreWorker` (same `fallback_target` from the context), worker kept via `_keep`, the in-flight worker is cancelled when switching project | Without network: selecting a project shows *loading* state and does not crash; step machine, plan panel and buttons stay intact; offscreen smoke tests | **Done (2026-08-26)** — `gui/main_window.py` builds the `ObjectPanel` lazily in `_get_proj_panel()` (wrapped in a `QScrollArea`, inserted before `tabs_steps`); `_project_selected` loads it with `ctx` + `fallback_target` and `cancel()`s the in-flight worker when switching (a late result never lands on the next) + `tests/unit/test_projects_hub.py` (6 offscreen tests, no network) → **revised 2026-08-27** — the panel now lives inside the **Details** tab (index 0, new in `projects_tab.ui`), which is the one left open on project selection; prev/skip/done are disabled on it and next enters step 1 → **2026-09-06** — the hub list is **always up to date without "Refresh"**: `on_refresh_projects()` is scheduled with `QTimer.singleShot(0,…)` when the app opens and re-run on every visit to the Projects tab (`_on_main_tab_changed`, `tabs.currentChanged` → index 1); the **Refresh** button stays as a fallback; the selected project is **preserved** across a refresh (its `id` is re-selected after re-rendering); +3 offscreen tests in `tests/unit/test_projects_hub.py` (load on startup, list without the button, selection preserved) |
| **D5** | ***Explore…* dialog over the shared panel**: `main_window.py:1504` becomes `ObjectPanel` + a *Make post* button; the `_dialog_explore_*` functions delegate to the panel; chart click→zoom is kept (the panel exposes its chart labels); `_project_explore` (step 4) / `_tools_explore` keep working | The Tools-menu *Explore…* dialog is identical in content; the NEO step 4 still opens it pre-filled | **Done (2026-08-26)** — `_open_explore_dialog` now builds `ObjectPanel(for_post=True)` inside a `QScrollArea` + a *Create post* button (the panel's `post_requested(name, fallback)` signal → `_open_post_dialog` + close); the `_dialog_explore*` / `_orbit_rows` / `_ChartClickFilter` / `_set_scaled_pixmap` helpers are gone (they live in `overview.py` already); `_render_object_charts` stays for the post flow; the orphan `explore_tab.ui` is deleted. Tests: 6 new offscreen in `test_overview_panel.py` (post button visible/hidden, `post_requested` carries name + fallback, in-flight guard, cancel clears) + 2 in `test_projects_hub.py` (integration of `_explore_panel`) + the 2 functional tests now drive the panel (parabolic orbit chart + unconfirmed NEO) |
| **D6** | **i18n + verification + docs**: `lupdate`/`lrelease` → `nightscribe_{es,en}.ts/.qm` (ADR-014); `pytest tests/unit` green; this section with final statuses | New strings translated ES/EN; smoke tests in `tests/unit/test_overview_panel.py` (D1-D3) + hub smoke (D4) green | **Done (2026-08-26)** — `pyside6-lupdate` (sources `gui/*.py + gui/ui/*.ui`) refreshes both `.ts` (+17 `ObjectPanel` strings, −21 obsolete `ExploreTab`); 17 new strings filled by hand (EN passthrough, ES translated); `pyside6-lrelease` → 2 `.qm` (306 strings, 0 unfinished); i18n smoke: `test_panel_strings_resolve_in_{spanish,english}` loads each `.qm` and verifies `btn_post` / `grp_params` / `grp_charts` / table headers / chip tooltips → 234 tests green (no network) |

**Revision (2026-08-27)** — "Details" up front, cleaner charts:

1. **Details tab first**: new in `projects_tab.ui` (index 0 of `tabs_steps`).
   The object's calling card — `ObjectPanel` — lives inside it
   (`_get_proj_panel` docks it there) and it is the tab left open when a
   project is selected: all the object info at a glance. The current step is
   still marked ● on its tab and reached with *Next →*; *prev / Skip / Mark
   done* are disabled on Details (no step to act on), *Next* stays allowed
   (enters Plan).
2. **Farewell to "Where does it live?"**: `viz/families_view.py` deleted (it had
   no more consumers); `core/post.build_charts` stops drawing it and
   `CHART_LABELS` loses the `families` entry. In the panel the slot becomes
   **orbit / sky / field / light curve** (exoplanet transits, already covered
   by `transit_view`).
3. **Empty slots are hidden**: the slots `build_charts` cannot generate are
   **hidden** instead of a "why not" line; when no chart is generated at all,
   the whole group disappears. Panel charts use the `panel` size (1200×675,
   added to `style.SIZES`) for less margin and more legibility in the window.
 4. **Chart resolution setting**: `Settings > Panel charts` adds a
    *On window resize* choice — **Fast** (the chart is drawn once at the
    `panel` size and re-scaled, the default) or **Sharper** (re-drawn at 2×,
    2400×1350, so big slots stay crisp). Stored as `config["chart_zoom"]`
    (`"scale"` / `"re-render"`) and read by `ObjectPanel` before every
    `build_charts` call; switching the setting while a panel is on screen
    re-draws it (`rebuild_charts`).
    _(Removed 2026-09-04: the `chart_zoom` option and the Settings > Charts
    tab were dropped once the ADR-029 vector widgets arrived, which render at
    native resolution. See `docs/adr/ADR-028` and the Slice 0 of
    `docs/PLANS/approach-chart.md`.)_
5. **Chart viewer opens fitted**: clicking a chart opens `ChartViewer`
   fitted to the window — the dialog is sized to the image's aspect so the
   default view fills it without scrolling (wheel zoom / drag pan / 1:1
   unchanged). The last window size the user left is remembered per chart
   (`config["chart_viewer_sizes"]`, restored on the next open).
6. Tests: `tests/unit/test_overview_panel.py`, `test_projects_hub.py`,
   `test_style.py` (panel preset, size override, squeezed margins) and the
   new `test_chart_viewer.py` (fit without scrollbars, fit follows the
   window, zoom buttons, per-chart size memory) updated to the new
   contract (6 tabs, panel inside the Details tab, hidden slots without
   data, group hidden without charts). `pytest tests/unit` green
   (247 tests, no network).

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
   - Phase 5: `core/sequence.py` (NINA JSON / CCDciel `.targets` / generic CSV capture
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
    The **TheSkyX safety horizon is fully in place** (E1+E2, 2026-08-28):
    (E1) `core/horizon.py` parses the SkyX limits export
    (`docs/limits-sample.hrz` = canonical reference) in addition to `az alt` text,
    with 16 safety tests and rejection of corrupt files.
    (E2) A **valid horizon file wins**: Settings disables `min_alt` under it
    (explanatory tooltip) and `horizon_margin_deg` is added on top. The **safe
    range** is visible app-wide (ADR-020): `planner.safe_window_for` computes the
    safe span + `best_time` + `latest_safe_start`; `sky_view` shades the span and
    marks «start by HH:MM»; the *Tonight* cards and the project hub show a green
    «⊕ HH:MM–HH:MM · ≤ HH:MM» chip or a red «⚠ does not fit» chip when the planned
    session does not fit; the ES/EN prose carries the window and its warning
    («DO NOT force the instrument»). 313 unit tests green.
   The **native CCDciel format is now real**: `export_ccdciel` writes the
   `.targets` list (CONFIG Version="5") fixed against a real user export
   (`docs/ccdciel_sequence_sample.targets`, 2026-09-06), with **Light + Dark + Bias**
   steps (calibration configurable in the project's Capture tab) and the default
   rise/set window that CCDciel recomputes from its own observatory settings.
   **NINA** and **generic CSV** remain starting points that require validation
   against the user's software versions via real import (ADR-021).

**Suggested next steps** (beyond the initial redesign):
- *(Done 2026-08-28: the real TheSkyX horizon is parsed and now outranks `min_alt` — see E1+E2 above.)*
- **Real moon icon (2026-08-27)**: `gui/moon_icon.py` composes the lunar
  surface (`assets/moon_disk.png`, CC BY-SA 3.0 photo — see
  `assets/ATTRIBUTION.txt`) with the terminator drawn by exact geometry
  (`r·cos E`), waxing on the right / waning on the left per
  `ephem_minor.moon["elong_deg"]`. It replaces the % in the *Tonight* header
  (tooltip: % now vs. by dawn + why it changes within one night) and the
  emoji in the *Solar* almanac. Flat grey disc fallback if the asset is
  missing. 8 offscreen tests, no network.
- Validate the sequence and ephemeris export formats against real software.
- Add flows for comets and exoplanet transits in the same 4-step skeleton.
- Test the GUI thoroughly and refine the stepper and contextual dialog UX.
4. Standing rules: English code with GPL header and `# @args:` comments, GUI strings
   via `self.tr()`, network only from `core/sources/` through `core/db.py`, bilingual
   documentation (ADR-013), unit tests per module + end-to-end functional tests.

### 7quater. Object-kind filter across the «Tonight» tab (2026-08-30)

Why: the kind filter (NEO / SN / CMT / PCCP / TRN / ALT) used to live only inside the
**collapsed table** (`grp_list / cmb_filter`), at the bottom of the tab. The **wide
rows** of the grid above and the **podium** (ring / stronger tint) were always built
over *every* target of the night, mixing classes. Observers could not tell the app
"tonight I only want supernovae" or "stop showing me comets". **K1** lifts the filter
to the header and makes it rule the whole view (rows + table); **K2** turns the
shown kinds into a permanent whitelist preference in Settings.

**Agreed decisions (2026-08-30)**:

1. **One filter in the header** (K1). `cmb_filter` leaves `grp_list` and moves to the
   `Tonight` header row (next to `lbl_context` and `lbl_moon`). Changing it
   **refreshes both views at once**: the grid rebuilds its rows for the chosen kind
   **and** recomputes the podium over **what is visible** (the top 3 of the filtered
   set, not of the whole night), and the table re-fills with the kind's own columns
   (`TABLE_COLS[kind]`). Single source of truth: `MainWindow._visible_targets()`
   (whitelist + filter); both grid and table call it.
2. **Whitelist of enabled kinds** in Settings (K2). Adds `config["enabled_kinds"]`
   (default = all 6) and a «Tonight: object kinds» group in `tab_observing` with 6
   checkboxes (NEO, SN, CMT, PCCP, TRN, ALT). On *Save*, the combo **only lists the
   enabled kinds** + «All»; if the active kind is disabled it falls back to «All»;
   if the whitelist grew, the combo grows too. «All» means **every enabled kind**,
   not every target of the night.
3. **`core/` is not touched**: all filtering lives in `gui/main_window.py` —
   `config.py` (defaults), `ui/tonight_tab.ui` (header combo), `ui/settings_dialog.ui`
   (kinds group), `main_window.py` (`_rebuild_kind_filters`, `_enabled_kinds`,
   `_visible_targets`, `_apply_kind_filter`). `suggest.top_n` keeps diversifying;
   `enabled_kinds` only cuts *what is shown* on this tab, never the scoring.
4. **Persistence**: `config["tonight_kind"]` ("" = All) is written on every combo
   change and restored on start when still in the whitelist. No new ADR: it is a
   local UX decision layered on the already-documented ADR-019/ADR-026 plane
   (single source of `KIND_LABELS` / `KIND_COLORS`).
5. **Tests**: `tests/unit/test_tonight_kinds.py` (offscreen): combo in the header
   with the 7 items (All + 6), grid and table limited to a kind, podium recomputed
   over the visible set, `tonight_kind` persistence, whitelist shrinking/growing the
   combo, and the fallback to «All» when the active kind is removed.
   `pytest tests/unit` green.

 ### 7quinquies. Per-kind cap for the grid + best-of-kind ring (K3, 2026-08-30)

 Why: with K1+K2 the night can bring 15 NEOs from NEOfixer, 90 SNs from
 Rochester, 15 comets from COBS… and the grid used to paint **all** of them
 (a wall of one class that forced the observer to filter to see anything).
 **K3** introduces the *best-of-each-kind* cap (configurable, not grouped)
 directly on the grid, and the **ring** now lands on the *best of each
 visible kind* — not on "the first three of the set" (7quater is superseded
 for the ring semantics).

 **Agreed decisions (2026-08-30)**:

 1. **`core/suggest.best_per_kind(scored, n)`**: input is the already scored,
    global-score-sorted list (the one `top_n` returns); keeps at most `n` of
    every kind (default `config["best_per_kind_n"] = 5`, configurable 1..50);
    `n<=0` = no cap. Returns `(grid, best_ids)`: `grid` keeps the **global
    score order** (not grouped by kind) and `best_ids` is the id of the BEST
    target of each kind present (the "rings").
 2. **The Tonight grid** (`_build_suggestion_grid`): filters to the visible
    set (K1+K2), applies `best_per_kind`, paints the result. The ring lands on
    **the best of each visible kind** (not on `i<3`); the status/action button
    stays on the right. The grid rebuilds when `best_per_kind_n` changes from
    Settings.
 3. **The Tonight table**: **unchanged in content** — the full list (all 6
    groups, all scores, all filters) stays *the whole set*; only its *order*
    and its *tint* (already best-per-rank 0/1/2) reflect the same best-per-kind
    rule. `suggest.top_n` (CLI) is not touched.
 4. **Planner `_comet_targets`** (bottleneck): the 15 Horizons ephemerides
    now run **in parallel** (~4-worker pool, COBS still returns the 15
    brightest). `n_comets=15` is preserved.
 5. **Config**: `config["best_per_kind_n"] = 5` (new, default 5) and
    `ui/settings_dialog.ui` `tab_observing` → row `spn_best_pk` (SpinBox 1..50)
    with ES/EN translations.
 6. **Tests**: `tests/unit/test_best_per_kind.py` (6 cases: cap, best-per-kind,
    no cap, order, empty id, empty input); `test_tonight_rows.py` updated —
    *now* every row in the fixture wears the ring (one per kind ⇒ best of each);
    `test_tonight_kinds.py` updated — the PCCP (rank 4 overall) DOES wear the
    ring when switching to the "PCCP" filter (and keeps it in "All").
    `pytest tests/unit` green (345 tests, 13.1 s).
 7. **Languages**: 346 strings (2 new), 0 unfinished.

 **Entry point (for any AI or human resuming this screen)**:

1. Read this section 7quater, ADR-019 (the tab hub) and ADR-026 (single theming
   source).
2. Start with **K1** (`tonight_tab.ui` + `main_window.py` `_apply_kind_filter` /
   `_visible_targets`), verify the contract (grid + table together, podium over the
   visible set), then do **K2** (`config.enabled_kinds` + the kinds group in
   `settings_dialog.ui` + the guards in `on_open_settings`).
3. **Do not touch** `core/` to filter — if it looks needed, open a new ADR before
   the minimal change (the planner still returns all 6 groups; scoring keeps
   diversifying; the whitelist only cuts the view).
4. Mandatory GPL header on every new `.py`, English code, GUI-visible strings via
   `self.tr()` (pattern in `main_window.py`), ES/EN pairs via `orbits.pick` (or
   `tr()` for static ones). Active language: `config.get("language")` (pattern
   `MainWindow._lang`).

 ### 7ses. Phase E — single entry point (2026-09-02)

 Motivation: with phases D and K done, the "way to get to an object" was
 scattered: row click → **Explore**, double-click on the table → **silently
 creates a project**, the row's button → **project**. The observer could not
 consciously choose between exploring and working on a project, and the table
 (the fastest view) did not let them see the object before creating anything.
 **Phase E** unifies: one single entry point ("Explore"), and the Continue/
 Explore buttons become pure shortcuts; the project is created or resumed
 *from inside* the Explore dialog.

 **Agreed decisions (2026-09-02)**:

 1. **Row click → Explore** (already the case; kept).
 2. **Table double-click → Explore** (was a silent project-creator — now
    `_table_open_explore`, same destination as the row and as the Explore
    button).
 3. **Row button** (`_card_button`): green **"▶ Continue"** when an active
    project already exists for the object (short-cuts to `_start_or_continue`,
    which jumps to the hub); orange **"🔭 Explore"** when there is none (opens
    the Explore dialog with that object). The button is a shortcut, not a
    different action from the row's.
  4. **Explore dialog** (`_open_explore_dialog`): the panel's only action
     is the **single CTA** (bottom of the section, full width, 46 px).
     The D5 **"Create post"** button is gone: posts are written inside
     the project (Publish step) or on demand from Tools. The CTA's face
     depends on the `project_lookup` the window injects: green
     **"Continue project"** if one is active for this object, orange
     **"Create project"** if not. It emits one of two new signals, each
     with two arguments (`name, fallback`): `project_create` /
     `project_continue` (the earlier `project_action(name, fallback,
     continue_)` is gone). `MainWindow` reacts in `_on_create` (goes to
     `_create_project`) and `_on_continue` (goes to
     `_goto_active_project`; creates a fresh one if the "explored name"
     does not match the active); the dialog closes after either. The
     dialog auto-fits to its content with reading floors
     (`resize_to_panel_content` in `gui/overview.py`: width ≥ 780,
     height = sizeHint + frame headroom) so the text reads comfortably
     and the CTA is always visible with no vertical scroll.
 5. **`_create_project` now returns the created dict** (or `None`, with a
    status-bar message when the kind is not a valid project kind — e.g. an
    ad-hoc transit from the Tools menu cannot create a project, only a post).
 6. **`_goto_active_project(name, fallback=None)`** (new, private): finds the
    active project whose `object_name` matches `name` or the `id`/`name` of
    the `fallback` (NEOCP/PCCP store the MPC number as `id` and a tentative
    name as `name`; either one may be the one kept with the project), and
    selects it in the hub. Returns `True/False`.
  7. **The panel stays testable**: `ObjectPanel` accepts `project_lookup` as
     an injected callable (no `core.db` import — `MainWindow._explore_panel`
     builds it); `for_post=False` (hub) → CTA hidden; `for_post=True`
     (Explore) → CTA appears once the object is loaded and the lookup reports
     the intent.

 **Tests**: `tests/unit/test_overview_panel.py` (7 new: pair hidden without a
 lookup, "Continue" when there is an active, "Create" when there is not, the
 signal with the right `continue_`, ignored while loading, `_blank` resets
 them); `test_tonight_rows.py` (3 new: "Explore" button wired to
 `_open_explore_dialog`, "Continue" button wired to `_start_or_continue`, and
 the "continue" → "create" fallback path); `test_projects_hub.py` (4 new:
 `_goto_active_project` by name, by `fallback id`, no match, and the dialog
 `project_lookup` honouring the planner's `id`/`name`); `test_tonight_table.py`
 already covered the double-click. `pytest tests/unit` green.

 **Languages**: 4 new strings ("Continue", "Explore", "Continue project",
 "Create project" + their tooltips), ES/EN pairs in both `.ts` and both
 `.qm` recompiled.

 **Entry point (for whoever resumes this phase)**:

 1. Read this section, ADR-019 (hub) and ADR-026 (themes).
  2. The four `gui/` touchpoints: `_card_button`, `_table_open_explore`,
     `_open_explore_dialog`, `_explore_panel` (in `main_window.py`) and the
     `ObjectPanel` constructor + `_refresh_cta` / `_cta_clicked`
     (in `overview.py`).
 3. **Do not touch** `core/project.py` to add kinds — `VALID_KINDS` stays as
    the single source; if a new kind enters, add its case to the creation
    tests (the dialog already honours it via the `kind` carried in the
    target).
  4. Mandatory GPL header, English code, `self.tr()` in the GUI,
     `pyside6-lrelease` after every `.ts` change.

  **Correction (2026-09-02, same day)**: the pair and the i18n smoke
  tests were failing because the pair's API is now the single CTA.
  `ObjectPanel` exposes `btn_project` (one full-width button,
  `min-height: 46`, section bottom) and the two signals
  `project_create(name, fallback)` / `project_continue(name,
  fallback)` (two args each; `post_requested` and `project_action` are
  retired). The window connects both in `_on_create` /
  `_on_continue` (in `main_window.py:1979`); the earlier orchestrator
  (`_do_project` / `_make_post` / `_explore_post`) is removed. The 9
  CTA tests in `test_overview_panel.py` + 4 in `test_projects_hub.py`
  + 2 in `test_tonight_rows.py` pass.

Each phase leaves the app working and ships its own tests. Do not mix phases in one
commit without the previous one being verified.

### 7septies. Unified object card (2026-09-07, ADR-031)

Motivation: the object card only gave a parameters table to NEO/comet/PCCP;
SNe and transits were left with hook + bullets, the table clipped long
explanations, the coordinates were nowhere to be seen, "Discovered" did not
apply to NEOs and the ADR-015 aperture filter was never implemented. Plan:
`docs/PLANS/object-card.md` (branch `feature/object-card`).

**What changes** (one subplan = one commit):

0. **Copyable coordinates**: block under the hook with RA/Dec in decimal and
   sexagesimal + a "Copy" button (`_coords_from`: same source chain as the
   sky chart).
1. **Multi-line table**: wordWrap + row auto-height that follows the stretch
   column on resizes (beware: `sectionResized` fires before `columnWidth()`
   updates — the handler forces the notified width first).
2. **SN table**: `orbits.explain_transient` (type, host galaxy, distance,
   brightness, discovery; redshift in depth).
3. **Transit card**: bug fixed — the exoplanet branch of `enrich` used to
   lose the ExoClock event; it is now merged with the ADR-027 pattern.
   `orbits.explain_transit` table with start/end UTC, depth (mmag and %),
   duration and the **minimum telescope vs. your aperture verdict**.
4. **Per-kind chips with one grammar**: SN gains event type and freshness
   ("N d", green when ≤14 days); transit gains depth Δmmag.
5. **Exact "Discovered" for NEOs and PCCPs**: SBDB `discovery=1` (fallback
   `first_obs`), NEOfixer `/orbit/` for NEOCP, PCCP maps its own column.
   Parallel pool of 4 + 7-day cache. New single `core/dates.py`.
6. **Hard aperture gate for transits**: `transits_tonight(aperture_in=)` +
   `transit_scope_filter` toggle in Settings > Observing (on by default; no
   ExoClock datum means no discard — ADR-025 spirit).

**Status**: subplans 0-6 done; unit suite green (555). Commits: `72d66ee`
(plan), `b163f6c`, `376a23c`+`67ceadf`, `02c05bf`, `3412c3c`, `8c4c336`,
`afab280`, `03290ea` + the i18n/docs closing commit.

**i18n note**: the `lupdate` command documented in CONTRIBUTING now includes
`gui/widgets/*.py` — without it lupdate marks live chart-widget strings as
"vanished" and the i18n tests fail on regeneration.

### 7octies. Fresh-ephemeris goto for moving targets (2026-09-07, ADR-030 rev.)

Motivation: NEOs, comets and PCCP candidates have no fixed coordinates (unlike
SN and transits). The goto used the **snapshot** the planner stored when the
project was created — a 5″/min NEO with a 2-hour-old plan accrues 10′ of error,
and the astrometric goto solved the wrong field. The card also showed the
Horizons row at 00:00 UT (`eph[0]`, daily step), up to 24 h stale. Plan:
`docs/PLANS/goto-fresh-ephemeris.md`.

**What changes** (one subplan = one commit):

0. **`core/ephemeris.py::position_at`**: queries Horizons at a 2-min step over
   a ±2 h window (rounded to 30 min to reuse the cache), linearly interpolates
   to "now" (RA unwrapped at the 0h/24h seam), derives the apparent rate
   (″/min) and PA. Offline fallback: SBDB+Kepler → NEOfixer preliminary →
   `None`.
1. **Fresh goto in `main_window.py`**: for `neo`/`comet`/`pccp` the
   `CcdcielWorker` action resolves `position_at` before the slew/solve and
   folds the result into the context (`coords_epoch`/`coords_source`/`rate`).
   SN and transits keep using the snapshot. A "Position at HH:MM:SS UT" label
   + a warning when it falls back to the snapshot.
2. **Card with visible epoch**: `_enrich_small_body` requests a 30-min step and
   picks the row nearest now (`ephem_epoch`); the coords block shows the epoch
   next to the copyable RA/Dec.
3. **Closure**: ES/EN i18n (~4 strings), ADR-030 revision, this section,
   `pytest tests/unit` green (582).

**Status**: subplans 0-3 done; unit suite green (582). **Out of this
iteration**: `SolarTracking`/`UpdateCoord=True` in the `.targets` and
non-sidereal rates via JSON-RPC (they need validation against the real
CCDciel); the per-exposure no-trail cap (`max_exposure_no_trail` +
`rate_arcsec_min`) already protects the frames.

### 7terdecies. Project container folder (2026-09-10, ADR-032)

*Note: this English file is behind the Spanish master (`WORKFLOWS.es.md`),
which already carries the *7nonies*…*7duodecies* sections (Tracks A–D). The
chunk below matches the ADR-032 slice; a backfill of the missing English
sections is pending.*

No dedicated `docs/PLANS/` file: a short jump decided in ADR-032. Everything
a project produces (plan, sequences, FITS, posts, charts) fell under
`data_dir()/projects/<id>-<slug>` (fixed, `platformdirs`): the user neither
knew where the files ended up nor could point them at their working disk.
Give control of the **container folder**: a configurable global root and, when
needed, a per-project folder.

| Sub | Deliverable | Status |
|---|---|---|
| P1 | `user_version` 6 migration: `root_dir` in `projects` + backfill to the legacy path; `config.projects_root`; `paths.project_dir(root=)` stays pure; `project.storage_dir()` (project root → config → default), `set_root_dir()`, and `create` freezes the root; tests `test_project_storage.py` | **Done** |
| P2 | All 9 `main_window.py` call sites write through `project.storage_dir()`; CLI `project show` prints `folder:` | **Done** |
| P3 | Settings > Observing: "Projects folder" group (browse/reset of `projects_root`) + a "Change folder…" hub button (re-homes future exports only, v1 never moves files); tests `test_settings_storage.py` + extended | **Done** |
| P4 | Closure: ES/EN i18n (598 strings, 11 new), lrelease, ADR-032, this section | **Done** |

**Status**: full unit suite green (**895**). **Behaviour**: the global root
change only affects **new projects**; legacy ones keep their exact folder
frozen in `root_dir`; the hub button only re-homes what is written from then
on.

### 7quaterdecies. HADS track — high-amplitude variable stars (2026-09-11, ADR-034)

*Note: the Spanish master (`WORKFLOWS.es.md`) carries the authoritative
version of this section.*

Plan: `docs/PLANS/hads-stars.md` (master) + `docs/PLANS/hads/fase-*.md`
(20 self-contained subplans). Branch `feature/hads`.

New `hads` target kind: high-amplitude δ Scuti stars (1–5 h periods,
ΔV ≥ 0.3 mag) — **you watch them pulsate live**. No known phase → the
recommendation is a **continuous 2×P capture** (not an event); the listing
gate demands a contiguous ≥ 1-cycle window. The data source is **hybrid**:
Patrick Wils' Google Sheets workbook (updated daily) is downloaded at runtime
with a 12 h cache (`core/sources/hads_sheet.py`, stdlib-only XLSX parsing,
two levels: raw + parsed JSON) and merged over the bundled snapshot
(`assets/HADS-stars.csv`, offline fallback + aliases). The sheet's color
legend feeds the score: red/orange (period changes!) +12/+8 urgency, blue
(not yet observed) +6, monthly coverage gap +10 — never stacked (max wins).

| Sub | Deliverable | Status |
|---|---|---|
| H0.1–H0.5 | stdlib XLSX reader, 12 h TTL cache, color+coverage parsing, `core/hads.py` (catalog/merge/derived/sawtooth), data docs | **Done** |
| A.1–A.3 | `hads` planner phase (1-cycle gate, 2P session in `_visibility`), scoring (4 families), ES/EN fragments | **Done** |
| B.1–B.4 | listable GUI (magenta, icon, columns, phase), config + friendly migration + combos, `enrich` (before the exoplanet regex), object card with `explain_hads` + chips | **Done** |
| C.1–C.3 | hads projects (`reported_aavso`), ES/EN narrative citing Wils/VVS/VSX, post/tweet | **Done** |
| D.1–D.5 | plan block (2P, cadence ≤ P/12, checklist), CCDciel sequence (advisory window), Follow-up + process (FotoDif/WebObs), **phase folding** (widget + PNG) | **Done** |

**Status**: unit suite green (**989**) + network functional green
(`test_hads_live`). **Out of this iteration**: the native live monitor
(**parked** — FotoDif AUTO already covers live watching); the
generalisation to long-period variables and campaigns (agreed model:
campaign = orthogonal project attribute + `variable` kind) is the **next
track, on its own branch** (see "Generalización futura" in the master plan).

### 7quindecies. Track V — long-period variables and campaigns (2026-09-11, ADR-035)

Plan: `docs/PLANS/variables-campaigns.md` (master) +
`docs/PLANS/variables/fase-*.md` (40 subplans). Branch
`feature/variables-campaigns`.

New `variable` kind (the multi-night Track B mould; HADS was the
exception) and a **campaign** entity, orthogonal 1:N (migration v7),
taken from the obsSN group's real campaigns (WeSb 1, T CrB). Tonight
gains the local `campaigns` phase (due only, V-d); the object card
resolves VSX (the `vsx.aavso.org` subdomain — www sits behind
Cloudflare) → SIMBAD → manual; extremum prediction from the VSX epoch;
event advisor (dip/eruption, configurable threshold); ZTF/ALeRCE survey
context in the light curve (closes the B12 option); CSV + AAVSO EFF
reports with **in-app HJD** (Schlyter Sun).

| Sub | Deliverable | Status |
|---|---|---|
| V0.1–V0.9 | `core/variables.py`, `core/campaign.py`, `core/sources/vsx.py` (TTL 7 d), `core/sources/surveys.py` (ALeRCE ZTF, TTL 30 d), migration v7 | **Done** |
| VA.1–VA.4 | `campaigns` planner phase (due + visibility), `variable` sub-dict, campaign scoring, ES/EN fragments | **Done** |
| VB.1–VB.6 | listable `variable` GUI, VSX→SIMBAD→manual card, epoch folding, contexts | **Done** |
| VC.1–VC.10 | variable projects, campaign manager (create/edit/close, targets, attach), hub filter, Follow-up | **Done** |
| VD.1–VD.9 | generalised Tonight chip + event warning, plan tab, multi-filter sequence, `photometry_export.py` (CSV + AAVSO EFF), export dialog, survey button, narrative, folded post chart | **Done** |
| VE.1–VE.2 | full i18n (714 strings, 0 unfinished), documentation close (this track) | **Done** |

**Status**: unit suite green (**1096**). **Out of this iteration**:
eclipse hour windows, campaign sharing, AAVSO Alert Notices, ASAS-SN
Sky Patrol, live monitor.

**Next track**: the usability audit (2026-09-13) found Track V's features
correct but hidden (the campaign manager is a selector with no detail
view) and the project flow stacked two navigation models (tabs + wizard).
The fix is its own track — plan written, pending execution on the
**independent** branch `feature/campaigns-ux`:
`docs/PLANS/ux-variables-campaigns.md` (master) +
`docs/PLANS/ux/fase-*.md` (23 subplans: the Campaigns fifth tab,
bidirectional links, one gesture language, the project as a single
checklist page with a Next-action card, and CCDciel moved to its own
Observatory tab). Also pending, approved 2026-09-12: the
featured-variables discovery add-on (predictable extrema + T CrB/R CrB
watch lists).

### 7sexdecies. Track UX — variables & campaigns usability (2026-09-13, amends ADR-035 + ADR-019)

Plan: `docs/PLANS/ux-variables-campaigns.md` (master) +
`docs/PLANS/ux/fase-*.md` (23 subplans). Branch `feature/campaigns-ux`
(independent: no merge-back into the feature chain).

The usability audit (2026-09-13) found Track V's features correct but
hidden: the campaign manager was a selector with no detail view, no
mention of a campaign was a link, the gesture language differed per
list, and the project flow stacked two navigation models (tabs +
wizard). The track delivers: the **Campaigns fifth tab** (master-detail:
per-campaign health at a glance — members × cadence × events via the
new `campaign.status_report` query — protocol, clickable URLs, members
table; the modal manager retires and ADR-035 decision 9 is superseded);
**bidirectional navigation** (project header badge, ⚑ Tonight card chip,
per-project clickable cadence chips landing on Follow-up, member
double-click → hub, History double-click → project/Explore); **one
gesture language** everywhere (click selects · double-click/Enter opens ·
right-click menu · hand cursor); the **project as a single page**
(Next-action card fed by `project.next_action()` + collapsible sections
with plain-word state — the step tabs and wizard retire; ADR-019
amended, lifecycle model unchanged); the **Observatory sixth tab**
(CCDciel control leaves the Plan step); and the fixes batch (no silent
validation, network off the GUI thread via `ResolveWorker`/
`SurveyWorker`, `event_mag_threshold` in Settings, persisted campaign
filter, stale detail cleared, CTA no longer closes on failure).

| Sub | Deliverable | Status |
|---|---|---|
| U0.1–U0.6 | fixes & feedback batch | **Done** |
| UA.1–UA.7 | Campaigns tab + links | **Done** |
| UB.1–UB.3 | gesture language | **Done** |
| UD.1–UD.5 | project single page + Observatory tab | **Done** |
| UC.1–UC.2 | i18n + docs close (this track) | **Done** |

**Status**: unit suite green (**1146**). **Out of this iteration**:
campaign-level photometric export, campaign sharing, the featured-
variables discovery add-on (approved 2026-09-12, its own track).
