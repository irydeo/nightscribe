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
| Limiting magnitude | `limit_mag` in config (equipment) | Filters families and scores observability; consistent across all (no hard-coded 14.0 for transits) |
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
| 4 | GUI v3: 4 tabs, Projects hub with per-kind stepper, contextual blink, Tonight cards with "Create project" and "safe start", Settings (Camera/Horizon/Session/Moon), i18n | Pending ← **entry point** |
| 5 | Exporters: `core/sequence.py` (NINA/CCDciel/CSV) + ephemerides (CSV + TheSkyX + CdC validated against real imports), tests | Pending |
| 6 | `core/mpc_report.py` + step in the NEO flow + minimal CLI `project` subcommand + polish, i18n and final docs | Pending |

**ENTRY POINT (for any AI or human resuming the work)**:

1. Read, in this order: `docs/adr/ADR-019`, `ADR-020`, `ADR-021`, `ADR-022` and this
   full document.
2. Phases 2 and 3 are already implemented on branch `feature/ux-v3-projects`:
   - Phase 2: `core/horizon.py`, `core/exposure.py`, helpers in `coords.py`, Moon
     penalty in `suggest.py`, planner integration in `planner.py`, silhouette in
     `viz/sky_view.py`, extended config, mock `tests/fixtures/horizon_sample.txt` + tests.
   - Phase 3: `core/db.py` migration (`user_version` 0→1: tables `projects`,
     `project_steps`, `project_files`; `observations` += `project_id`), `core/project.py`
     (model + step machine Plan→Capture→Process→Analyse→Publish), tests.
   The **real TheSkyX horizon** is still mocked: when the user shares their file,
   replace the parser/fixture in `core/horizon.py` validating against that file (ADR-020).
3. Continue at **phase 4**: GUI redesign. Navigation becomes 4 tabs (Tonight · Projects
   · Solar · History); build the Projects hub with a per-kind stepper; make
   Explore/Post/Blink contextual (pre-filled from the project); add "Create project" and
   "safe start" to Tonight cards; extend Settings with Camera/Horizon/Session/Moon
   groups; update i18n (.ts/.qm).
4. Standing rules: English code with GPL header and `# @args:` comments, GUI strings
   via `self.tr()`, network only from `core/sources/` through `core/db.py`, bilingual
   documentation (ADR-013), unit tests per module + end-to-end functional tests.

Each phase leaves the app working and ships its own tests. Do not mix phases in one
commit without the previous one being verified.
