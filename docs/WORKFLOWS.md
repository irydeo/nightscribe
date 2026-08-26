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
