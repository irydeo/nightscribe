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

## CCDciel — CCD tab buttons (`gui/main_window.py:1635`)

Require CCDciel running with its JSON-RPC active (ADR-030); reads cached 60 s.

| Button | What it does | When to use it |
|--------|--------------|----------------|
| **Point telescope** | Quick slew to the **freshly computed** position of the moving target: `J2000_to_Apparent` + `Telescope_slewasync`, **no plate-solve**. Fast, but assumes the ephemeris is already accurate. | Well-determined orbits (planets, asteroids with a firm orbit, objects with long arcs). |
| **Astrometric Goto** | Slew + **capture + plate-solve** and correction to the true sky position. Absorbs **residual ephemeris error**. | **NEOCPs** and **preliminary orbits**: always this route, because a 1–2-arc ephemeris carries arcsec-level errors the plate-solve cancels out. |

The rest of the CCD panel (connect, filter, push plan, start capture) follows ADR-021
§5 and ADR-030: the plan is **delivered live** over JSON-RPC (`Capture_set*`,
`Wheel_setfilter`, `Capture_start`) and the `.targets` file is also generated
(Light + Dark + Bias).

## Capture sequences (`gui/main_window.py` → `_project_export_sequence`)

| Format | File | Status |
|--------|------|--------|
| **CCDciel** | `<name>.targets` (CONFIG Version="5") | **Real** — fixed against the user's actual export (`docs/ccdciel_sequence_sample.targets`); Light + Dark + Bias steps, re-computable rise/set window. |
| **NINA** | native sequence JSON | Best-effort; validation pending against the user's real version. |
| **Generic CSV** | `<name>.csv` | Best-effort; times/exposure tables readable by any script. |

Every export is **registered in `project_files`** (ADR-019) so the path can be
re-opened after the export. Since the re-homing (ADR-019 review 2026-09-24),
that list is opened from the project masthead's **"Files (n)"** button, in
its own window: a double-click on a plate (`fits`/`image`) re-opens it in
the **unified FITS editor** (ADR-044) with the project's object attached,
and the rest of the files open with the OS (the per-row menu keeps "Open
with the system", folder and copy path).
