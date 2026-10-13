# NightScribe — Project buttons and exports

*[Spanish version](UI_EXPORTS.es.md)*

What each delivery button and each export format does, for whom it is, and why. The
goal: before you click, you know exactly which file you get and which program opens
it.

## Export ephemeris (`gui/main_window.py` → `_project_export_ephem`)

The **«Export ephemeris»** dialog offers two formats and one optional flag. Pick the
format by where the file ends up:

| Format | File | For | What it is |
|--------|------|-----|------------|
| **MPC elements (MPOrbit)** (primary) | `<name>_elements.txt` | **Any planetarium or orbit reader** (universal MPC elements handover) | One **MPC MPOrbit element line** per object (202-character, the Minor Planet Center's "Export Format for Minor-Planet Orbits"): packed designation, H/G, packed epoch, mean anomaly, perihelion/node/inclination, eccentricity, mean motion, semi-major axis, uncertainty, last-observation reference, arc and RMS — exactly the layout Find_Orb writes, so software that already digests Find_Orb elements lists reads it unchanged. This is the **canonical orbit handover**: the one to use when the target is another program. |
| **MPC orbit report** | `<name>_orbit_report.txt` | **Readable follow-up** and general tools | The **readable** MPC/Find_Orb-style orbit report: Keplerian elements + sigmas, perihelion, P/Q vectors, J2000 state vector (position AU / velocity mAU·day⁻¹), MOIDs of the 8 planets, Tisserand, encounter speed, estimated diameter and an MPC-style element footer. Every field is a pure formula. |

**«Force fresh data (bypass cache)» flag** — re-queries JPL SBDB / NEOfixer *now*
instead of using the orbit already cached in SQLite. Use it after the **MPC has
improved the preliminary orbit** (more observations, longer arc) so the report
reflects the newest solution.

**No local Find_Orb**: every field in the MPC report is a **pure formula** over the
elements returned by NEOfixer/SBDB (`core/orbits.py`, `core/ephem_minor.py`,
verified against `docs/Sar2911-sample-ephemerids.txt`). Find_Orb is **not** run
locally.

**Topocentric parallax**: the CCD position and the position CSV use `kepler_ra_dec()` with
the observatory lat/lon/height from config — the position you see is the one from
*the site*, not geocentric (for Sar2911 at 0.102 AU the correction is ~86″; typical
NEOCPs at 0.1–0.2 AU, ~44–88″). Make sure the Settings observatory is correct before
exporting.

## Observatory control — Capture step buttons (`gui/main_window.py`)

Require the observatory software running with its API active (ADR-030, ADR-081);
reads cached 60 s. One backend at a time, picked in **Settings → Integrations**:
**CCDciel** (JSON-RPC) or **NINA / PINS** (Advanced API v2).

| Button | What it does | When to use it |
|--------|--------------|----------------|
| **Point telescope** | Quick slew to the **freshly computed** position of the moving target: `J2000_to_Apparent` + `Telescope_slewasync` on CCDciel, `mount/slew` on NINA, **no plate-solve**. Fast, but assumes the ephemeris is already accurate. | Well-determined orbits (planets, asteroids with a firm orbit, objects with long arcs). |
| **Astrometric Goto** | Slew + **capture + plate-solve** and correction to the true sky position. Absorbs **residual ephemeris error**. | **NEOCPs** and **preliminary orbits**: always this route, because a 1–2-arc ephemeris carries arcsec-level errors the plate-solve cancels out. |
| **Stop goto** | Halts the telescope movement **now** (`Telescope_abortmotion` on CCDciel, `mount/slew/stop` on NINA). Armed the moment a pointing starts, on its own worker. | The mount is heading somewhere it should not. Safety. |
| **Send plan** | Stages the saved plan (object, frames × exposure, filter, binning, gain, offset, dither) and **reads it back** (`Capture_getobjectname/exposure/count/frametype/binning/dither` on CCDciel; held in the client on NINA) so the panel shows what is really held. The **autofocus cadence is not applied live** (CCDciel's API does not expose it): it travels with the exported sequence. | Before starting a capture. |
| **Start / Stop capture** | Fires the staged capture, and the same button stops it while a run is in flight (`Capture_start`/`Capture_stop` on CCDciel; a one-shot snapshot / `abort-exposure` on NINA). | When the telescope is pointed and the plan is staged. |

The plan's filter list is the one the wheel really has (read on connect); the
classic L/R/G/B/Ha/OIII/SII list is only the fallback while disconnected. The
`.targets` / NINA JSON files are also generated (Light + Dark + Bias).

**Last frame** (ADR-082): after *Start capture*, the step shows a thumbnail of
the last frame the program has, fetched over the network (CCDciel's
`fullimage.jpg`, NINA's image stream), with its file name, filter, exposure and
date, and **Open in the editor** (NINA downloads the FITS; CCDciel opens the
file on disk when its path is reachable). No folder, works remote.

**Capture options** (ADR-083): a collapsed block with dithering, autofocus,
gain, offset, binning and delays. The recommended values come from
`core/capture_recipe.py` (by object type and the physics) and the ⓘ explains
each one; they travel with the exported sequence and, where the API allows, are
applied live.

**Suggested values** (ADR-083): a project with no plan opens with the suggested
frames, exposure, dither, autofocus and camera values filled in; the observer's
changes are kept, **Set suggested values** re-applies them and the **?** per
block opens a dialog with the reason and the numbers used. The exposure is
shortened for a camera that saturates sooner (full well / linearity, plate
scale) and checked against the site's sky brightness and the read noise.

## Capture sequences (`gui/main_window.py` → `_project_export_sequence`)

| Format | File | Status |
|--------|------|--------|
| **CCDciel** | `<name>.targets` (CONFIG Version="5") | **Real** — fixed against the user's actual export (`docs/ccdciel_sequence_sample.targets`); Light + Dark + Bias steps, re-computable rise/set window. |
| **NINA** | native sequence JSON (`SequenceRootContainer`) | Loadable by NINA via `/sequence/load`; structure pinned against NINA's test corpus, **pending confirmation against a real NINA/PINS** (the `$type` strings live in one place). |
| **NINA (plan summary)** | `*.plan.json` | A human-readable summary of the plan (target, exposures, capture options); NOT a loadable sequence. |
| **Generic CSV** | `<name>.csv` | Best-effort; times/exposure tables readable by any script. |

Every export is **registered in `project_files`** (ADR-019) so the path can be
re-opened after the export. Since the re-homing (ADR-019 review 2026-09-24),
that list is opened from the project masthead's **"Files (n)"** button, in
its own window: a double-click on a plate (`fits`/`image`) re-opens it in
the **unified FITS editor** (ADR-044) with the project's object attached,
and the rest of the files open with the OS (the per-row menu keeps "Open
with the system", folder and copy path).
