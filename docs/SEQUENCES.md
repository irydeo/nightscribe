# SEQUENCES · Photometric series

*What NightScribe's photometric series is, how it is measured from the visit
and how to read the curve that comes out. User documentation.*

The observing practices live in [PHOTOMETRY.md](PHOTOMETRY.md) and the quality
figures in [PRECISION.md](PRECISION.md); this document is the "how you work".

---

## 1. What a series is

A **series** is the measurement of **many frames of the same object**, one
after another, as a single set:

- each frame is measured with the **same recipe** as a single plate (centroid,
  aperture, sky, guards) and with its **own zero point** (the comparisons of
  that same frame);
- the curve is **magnitude (or relative flux) against time**, with its errors;
- the **quality gates** flag what does not fit, but they **never delete a
  point**: the observer decides.

The engine is the same for every type; the type only chooses the parameters and
the cadence warning.

## 2. Series types

| Type | Read with | Cadence warning |
|---|---|---|
| **Exoplanet transit** | T_mid and depth | points per ingress (red if lost) |
| **Variable** | phase and period (folded) | Nyquist |
| **HADS** | 12 points per cycle | AAVSO 15 min cap |
| **Supernova** | nights and rise | none of its own (follow-up decides) |

The engine is kind-agnostic: validating a type means choosing parameters and a
checklist, not writing new code.

## 3. Where you work from

**Always from a project visit.** The flow is:

```
Project sheet : Capture : Analysis (visit) : Publication
```

The visit window holds its files (FITS frames) and the **"Measure the
sequence..."** action, which opens the editor on the first frame with the series
block armed. There is no loose-folder dialog: no visit means no series, no
Undo, no analysis, no aggregation.

To get files there from a listing, use **"Attach files to the visit"**
(multi-select) in the visit window itself.

## 4. Step by step

1. **Build the comparison sequence** in the editor's Photometry tab (top half,
   "Build the sequence..."). The series uses those comparisons on every frame.
2. **Measure the target** once (a click) so the series knows where to measure;
   or open the editor from the sheet with coordinates, which land by themselves.
3. Click **"Measure the sequence"**. A **run** starts (with its `run_id`), the
   progress shows per frame and the curve is drawn when it ends.
4. Check the **curve** (raw and, if you asked for detrend, detrended too), the
   **flagged points** (diamonds) and the **summary panel** (points, flags,
   coefficients, cadence and multi-night warnings).
5. If something went wrong, **"Undo this run"** deletes only that run's points,
   leaving the rest of the visit untouched.
6. To submit a transit to ExoClock, click **"ExoClock..."** (see section 10).

## 5. Controls and defaults

The day-to-day controls are on the tab: **band** and **apertures**. The rest
live in **Advanced...** (a small, non-modal window):

| Control | Default | What it does |
|---|---|---|
| Sky | median | flat median or a tilted plane (galactic cores) |
| Sigma-clip | on | two 2.5-sigma rounds on the sky annulus |
| Aperture follows the seeing | on | `r = 1.35 · FWHM` measured on the comps |
| Colour term | on | fits the ZP and its slope with the comps' B-V |
| Subtract host galaxy | off | aligned PS1 reference, scaled by the comps |
| **Group frames** (`group_n`) | 1 | combines N frames per point in the measurement domain; never pixel stacking |
| **Detrend** | off | `airmass` removes the minimum; `auto` adds FWHM/sky/x-y only if it improves |
| **Aperture sweep per night (T3)** | off | picks the k in [1.0, 2.0]·FWHM with the smallest check scatter |
| **Saturation ceiling** | 0 = auto | absolute ADU value; 0 uses the SATURATE card or Settings |

Every control has its tooltip with units and reason, and there is a **"Restore
defaults"**.

## 6. When to trust it

- **The raw curve is always visible** next to the detrended one: detrending can
  eat signal, and seeing it is the only defence.
- **Honest errors**: the total error is never below the internal (photon) one;
  it includes the zero point, scintillation and the flat residual. If the gain
  is missing, the panel says so.
- **Flagged points** (diamond): saturation, guide jump, cosmic ray, cloud or
  shifted zero point. They are never deleted; they can be disregarded in
  analysis.
- **Traffic light**: the cadence and multi-night warnings (mixed band, shifted
  zero point) speak in plain language; in red, a transit ingress is lost.

## 7. Multi-night

Each night is **one run** with its own `run_id` and Undo. The project curve
aggregates them. The detrend is fitted **per night** (local coefficients), with
an offset-only fallback on short nights or nights without airmass range. If you
mix filters, the band guard warns: they are not combined into one magnitude
curve. A shifted zero point is **flagged**, never hidden.

## 8. When you do NOT need a series

A **single point** (for example an SN among other observations) is a
**single-plate** action: measure it in the Photometry tab and save the point;
the series engine only starts with two or more frames.

## 9. Live mode

**Optional and off by default.** Turn on **"Live (watch the folder)"** in the
series block: a light watcher observes the visit's folder, detects new frames
(waits for the file to stop growing, never reads a half-written one), measures
them with the same engine and updates the curve every few frames. Live files
need **no astrometry**: the reference plate seeds the target and the
comparisons.

## 10. ExoClock (manual submission)

NightScribe does **not** upload to ExoClock: it prepares the two files and opens
the upload page in the browser.

- **Data**: a **3-column** text file: JD_UTC of the exposure **start**, relative
  flux (the target over the mean of the comparisons) and its error.
- **`ExoClock_info.txt`**: planet, time format (JD_UTC), stamp (Exposure start),
  flux format (Flux), filter, exposure time and a **Comments** field filled with
  your honest self-assessment.
- A point **without an exposure time** cannot be exported: the start would be a
  lie.
- Before the button there is a **checklist** (baseline each side, points per
  ingress, no red flags, coherent dip). It warns, it does not block.
- On confirming, the project records the outcome **`reported_exoclock`**.

## 11. External reduction with EXOTIC

For a scientifically-minded transit, the reduction and the fit are done by
**EXOTIC** (NASA/JPL), which NightScribe **orchestrates** as an external tool
(it does not embed it). This is the primary path; the numpy series in the
photometry block stays as a quick **preview**.

1. **Prepare the environment** once in **Settings → EXOTIC**: point to a
   **Python <= 3.10** interpreter (or let it detect one) and click **"Prepare
   environment"**; it builds a private environment and installs EXOTIC (needs
   network the first time). **"Test"** checks that it imports.
2. In the transit project, **Analysis → "Reduce and fit with EXOTIC..."**: the
   app writes the visit's `inits.json` (frames, target and comparisons in
   pixels), runs EXOTIC headless with the log in sight (you can cancel) and
   **imports its light curve and parameters** (T_mid, Rp/Rs, depth, inclination,
   duration) into the project. The curve lands as "exotic" points and shows in
   the chart like any other.
3. Then upload the result to ExoClock with **"ExoClock..."** (or to the AAVSO
   Exoplanet Database).

Without an EXOTIC environment, the manual **"Export to EXOTIC (inits.json)..."**
button stays available to reduce outside and come back. EXOTIC's first run needs
network (NASA Archive, limb-darkening data, astrometry.net).

### Real end-to-end test

Requirements: a transit project, a visit with the night's frames, a comparison
sequence and the EXOTIC environment prepared.

1. **Environment**: Settings → EXOTIC (transit reduction) → point to a **Python
   <= 3.10** → **"Prepare environment"** → **"Test"** (it should report
   `EXOTIC 4.3.x`). Save.
2. **Visit**: open the transit visit and attach the frames ("Attach files...").
   If the first frame carries a WCS, the app computes the target and comparison
   pixels by itself; if not (an unsolved session), it will ask you by hand for
   the **target pixel** (`X,Y`) and the **comparisons** (`X,Y; X,Y; ...`, up to
   10).
3. **Sequence**: confirm the project's comparisons (in the editor).
4. **Reduce**: Analysis → **"Reduce and fit with EXOTIC..."** and follow the log.
   It can take a while; do not close the app (you can cancel).
5. **Result**: a message with **T_mid** and **Rp/Rs**; the "exotic" curve shows
   in the chart; the `inits.json` and the report stay in the project, and the
   `FinalLightCurve_*.png` figure in the work folder.
6. **Verify**: T_mid within 3 sigma, Rp/Rs within 5 % and depth within 10 %
   against the reference. Then **"ExoClock..."** to submit the transit.

EXOTIC's **first run** needs network (NASA Archive, limb-darkening data,
astrometry.net). Without an EXOTIC environment, the manual **"Export to EXOTIC
(inits.json)..."** button stays available.

**On Windows (the cleanest)**: install **Python 3.10** from python.org (tick the
*py launcher*) and run `pip install exotic` in it; then point the app to that
interpreter (Settings → EXOTIC; the app also detects it with the `py -3.10`
launcher). The **"Prepare environment"** button is optional and builds a private
environment for you if you prefer. Some EXOTIC dependencies may lack a Windows
wheel; if `pip install` fails, the app shows the error and the numpy series keeps
working.

## 12. Troubleshooting

- **"No visit with frames"**: open the editor from a visit, not from the loose
  Tools menu.
- **"No comparison sequence"**: build it in the top half of the Photometry tab.
- **"Measure the target once"**: a click on the target (or open from the sheet
  with coordinates).
- **A transit that does not fit**: check comp saturation, the ceiling, and that
  no filters are mixed; look at the raw and detrended curves separately.
- **Frames that drift or rotate and carry no WCS**: the series measures at fixed
  coordinates on the reference plate; if the field moves a lot, points get
  flagged (`guide_jump`). Per-frame registration is available as an advanced
  option.

## 13. Glossary and links

- **ZP**: zero point; the difference between the instrumental magnitude and the
  comps' catalogue magnitude.
- **Ensemble**: the combined comparison set (weighted mean with a robust veto).
- **Detrend**: removing a trend from the curve (airmass, etc.); its model is
  `a1·exp(a2·X)+a3`.
- **Ingress**: the transit's entry; resolving it needs several points.
- **Run**: one press of "Measure the sequence", with its own Undo.

Links: [PHOTOMETRY.md](PHOTOMETRY.md) (practices), [PRECISION.md](PRECISION.md)
(quality and figures), [WORKFLOWS.md](WORKFLOWS.md) (project flow), ADR-048
(series), ADR-049 (ExoClock), ADR-050 (live mode), ADR-051 (local solver),
ADR-052 (EXOTIC orchestration).
