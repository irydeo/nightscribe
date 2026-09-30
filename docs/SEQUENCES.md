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
Undo, no analysis, no aggregation. The panel **at the left of the image**
(visible only with the visit armed) carries the **frame navigator** (previous /
next, `frame i/N`, "first frame": the open frame is the reference), the
**Photometric series** block (the curve opens large on a **click**) and,
in transit projects, the **EXOTIC** block. If the first frame has no WCS, it is
solved by itself with the configured solver before starting.

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

The day-to-day controls are on the tab: **band**, **apertures** and, in the
series block, **group frames** (`group_n`). The rest live in **Advanced...**
(a small, non-modal window):

| Control | Default | What it does |
|---|---|---|
| Sky | median | flat median or a tilted plane (galactic cores) |
| Sigma-clip | on | two 2.5-sigma rounds on the sky annulus |
| Aperture follows the seeing | on | `r = 1.35 · FWHM` measured on the comps; in a series, each frame's own FWHM |
| Colour term | on | fits the ZP and its slope with the comps' B-V |
| Subtract host galaxy | off | aligned PS1 reference, scaled by the comps |
| **Align frames** | **auto** | see below; `off` only when the frames are already aligned |
| **Group frames** (`group_n`) | 1 | combines N frames per point in the measurement domain; never pixel stacking; also a quick knob in the series block |
| **Detrend** | off (variable/HADS: airmass) | `airmass` removes the minimum; `auto` adds FWHM/sky/x-y only if it improves |
| **Aperture sweep per night (T3)** | off | picks the k in [1.0, 2.0]·FWHM with the smallest check scatter |
| **Saturation ceiling** | 0 = auto | absolute ADU value; 0 uses the SATURATE card or Settings |

Every control has its tooltip with units and reason, and there is a **"Restore
defaults"**.

### 5.1 Aligning the frames (important)

**The frames of a visit rarely land on the same pixels.** The telescope drifts
(polar misalignment, refraction, guiding) and a frame may carry a dither. If the
engine always measures where the reference plate said, the star **walks out of the
aperture**: in the real V0526 Per series (244 frames of 40 s) the field moved 134"
in 2.9 h and the curve went from 13.4 to 17.4 magnitudes with 0.5 mag errors. That
no longer happens: `align="auto"` is on and it does this:

1. it removes the sky from each frame (block medians) so vignetting is not mistaken
   for signal;
2. **the stars vote the transform**: for every candidate rotation each star pair
   proposes a translation and the one most independent pairs agree on wins; a **pure
   translation** is tried first and the rotation only enters when it is not enough;
3. it measures each frame **on its own native grid** with the composed WCS
   (`coords`), so the PSF is **never resampled**;
4. it **verifies** the transform against the stars it paired: quality is the number
   of pairs and their residual in pixels, not a magic correlation number.

A frame that cannot be verified **inherits the previous alignment and is flagged**
(`align_failed`): it is never measured on a guess. The summary panel says all of it
in plain language: how many frames were aligned, how far the image moved (px and
arcmin), the star residual and the frames left unverified.

Aligning costs about 0.15 s per frame (2 % of the total) and can be switched off in
**Advanced... → Align frames** when your frames are already aligned (for instance if
every one carries its own WCS).

### 5.2 The comparison stars: the zero point is tied per star

A comp's catalogue value can be wrong (on very red stars the V derived from Gaia
deviates by up to 0.9 mag) and, on top of that, the drift makes a comp **come in and
out of the frame** or saturate. The median of whatever was left used to jump from
frame to frame; now each comp measures its **own level** over the whole series and
the zero point no longer depends on which ones were present. The **check star never
enters the zero point** (it is the monitor). The panel warns you when the comps
disagree with each other and about those missing from almost every frame: that
usually means the sequence deserves rebuilding with stars closer to the target and of
similar brightness.

And the sequence the app proposes no longer comes from the catalogue blind: every
candidate is **measured on your own plate** and rejected with its reason (saturated,
above the camera's linearity limit, outside the sensor's real rectangle, or too
faint). The field is the sensor's rectangle, not a square, and it carries a safety
ring so the night's drift cannot lose a comp at the very edge.

### 5.3 Gain and read noise: or the error is not the CCD's

Without a gain, a point's error is the scatter of the comparison stars, not the CCD
equation (0.17 mag instead of 0.005 on the V0526 Per series). Both fields live in
**Settings → camera profile**: the read noise is filled from the preset (a datasheet
fact) and the gain never is, because it depends on the unit and the gain setting. If
you do not set it, the engine **measures it on your own frames** (two frames at the
same exposure are enough) and says so in the panel, with its uncertainty and its
origin; it never writes it into Settings behind your back.

### 5.4 The chart's scale

The magnitude axis follows the **core** of the curve (median ± 6 robust sigmas), not
the minimum and maximum, so an anomalous point does not flatten the rest; the ones
outside stay on the chart, anchored to the edge. The wheel zooms, the left button
drags and **Fit** returns to the panel. The **Robust**, **Errors** and **Hide
flagged** buttons sit above the series curve: "Errors" draws each point's photon
error and the **band** of the calibration systematic (the zero point belongs to the
whole night: a band, never a bar per point).

**Flags come in two kinds.** A **data** flag (saturated, cosmic ray, focus, cloud,
unaligned frame) comes out as the hollow diamond. A calibration **caveat** (few
comps, a borrowed zero point) is the normal marker with a faint amber edge: the curve
is fine, its calibration leans on few stars.

**The colour of each point is a code** (the **Quality colours** button, on by
default): **green** when the point is clean (error up to 0.05, more than three
comparisons holding the zero point), **orange** when it is usable but not clean (a
thin comparison set, an error up to 0.15) and **red** when its data is in doubt. The
**shape** still says which decision was taken; the colour says how good the
measurement is. Off gives the filter colours back. The plate's band and the
measurement's panel wear the same code, with the same thresholds: see
[the editor's guide](UFE.md).

### 5.5 A defocus is not a cloud

If a frame's FWHM leaves its night's robust range, the point is flagged **`seeing`**
(defocus, a trail or a satellite through the core) and not `cloud`: a cloud moves the
sky and the zero point **without** changing the PSF, a defocus changes the PSF and
leaves the sky alone. With "the aperture follows the seeing" on (the default), the
radii you choose belong to the reference FWHM and each frame scales them by its own,
so the light that was falling outside the aperture comes back: on the real series,
the defocused frame goes from deviating 0.049 to 0.017 mag.

The **camera profile** (Settings → Photometric camera profile) fixes the
**full well, the dark current and the linearity limit / working max exposure per
gain** (measure them; a suggested value is offered). On a very sensitive sCMOS
(QHY42Pro/GSENSE400) the recipe is **5–10 s exposures and grouping** (`group_n`)
to beat scintillation without saturating or drowning in sky background; modern
IMX and CCDs take long exposures. The **linearity limit** is what decides which
stars are good enough as comp/check.

### 5.6 The two PNGs, and what the night figures need

The series block's **Series ▾** door carries two exports:

* **Save the chart in the visit (PNG)…** writes the curve **exactly as you see it**
  (the window you zoomed to, the points you selected or excluded, the fixed range):
  what is on screen is what lands in the file. It works with the visit's own curve
  too, the one loaded from the project without measuring anything again.
* **Night conditions (PNG)…** writes the two figures that explain the night, the
  **airmass** and the measured **position** (the drift), and opens them. They are made
  of fields that travel WITH each point (airmass, x, y, fwhm, sky), so a curve read
  back from the database can draw its own night months later. A point measured before
  the app stored them has no airmass to draw, and the button says exactly that instead
  of going quiet: measure the series again and the figures are there.

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

### 7.1 A series over several nights, in ONE pass

A variable you follow for the whole campaign is measured **in one go**, not
night by night. In the series block, next to the frame counter, is the
**"this visit" / "all visits"** selector: it only appears when the project has
more than one visit with frames.

With **"all visits"** the engine gets the frames of **every visit** (in time
order) and measures them as one series. The result is filed as **one run per
visit**, because a visit is one night and every point belongs to the night it
was taken on: each visit's curve is its own and the project's is the union of
the nights, one pass per night, which is what folding a period needs. The
nights are not mixed in the calibration: the zero point, the detrend and the
quality control are **per night**, as always.

The whole pass is **one thing** to undo: the Undo button removes that pass's
nights in one click (the runs stay marked undone, the trail is never silent).
In the door **Series ▾ → Passes of this visit…** every night of a pass says
which pass it belongs to ("part of a 3-night pass").

**Live mode** stays per visit: it watches today's folder. With "all visits" it
is turned off and says why, because watching several folders at once is
another thing. And **discarding the curve** is per visit too: with "all
visits" it is disabled and says to open the visit whose curve you want to
undo.

### 7.2 A visit is ONE curve (and the other passes stay)

**One frame, one measurement.** A curve never shows the same frame twice: it
shows its **newest** measurement. If you measure the whole night again, the
new pass replaces the old one; if you measure only a part, the rest stays as
it was and the night is still **one** curve. Measured on your own database:
the 244 frames of visit 18 had been measured again as visits 20 (35 frames)
and 21 (3), every one inside the 244, so the union held 282 points with 38 of
them duplicated at two levels; it is 244 now.

The **visit's curve** is the pass the visit shows (the passes door): that
pass answers for ITS frames, and the ones it does not cover are filled with
their newest measurement. The **project's curve** is the objective union: one
point per frame, its newest measurement, with no visit's choice changing what
another sees. That is why a visit's chart can show one pass while the
project's shows the whole set: the first is the working view ("which pass am
I looking at?"), the second is the science.

A visit can hold **several passes**: you measure the series again with another
band, with another sequence, or just to check something. Every pass keeps its
points and none is deleted, but **the visit's chart draws only one**, the one
the visit has marked. Measuring again makes the new pass the curve (it is what
you just measured, and what you were watching live); the earlier ones are
**not drawn**, and drawing them all at once is what shows a curve duplicated at
two levels joined by a zigzag.

To go back to an earlier pass: **Series ▾ → Passes of this visit…**. Every pass
is there with its time, its band, its points, the stretch of night it covers
and its state, and the one the chart shows is in bold. Two actions per row:

* **Make this the curve**: the chart draws that pass. **Nothing is deleted**
  and nothing is measured again.
* **Undo this pass**: its points go, its row stays marked undone and the chart
  falls back to the pass before it. The frames are untouched.

Undoing the last pass **brings the previous one back**, which is what you
expect from an Undo. And the visit's panel says it out loud: which pass it is
drawing and how many more it holds (with their points), so the list of passes
is never a secret.

The same rule holds for the **project's** curve: it aggregates the nights, and
takes one pass per night (the one the visit marks, or the last one measured).
A night measured five times counts once.

## 8. When you do NOT need a series

A **single point** (for example an SN among other observations) is a
**single-plate** action: measure it in the Photometry tab and save the point;
the series engine only starts with two or more frames.

## 9. The period: find it, fold it, and say what cannot be known

Once the curve is measured, the next question is **what its period is**. There are
two doors: the **"Period and phase…"** button in the visit window (Analysis tab) and
the one in the series block of the editor's Measure tab. The window works on the
**project's** curve (every visit, whatever measured each point).

- **Methods**: the generalised Lomb-Scargle (with a floating mean: nothing has to be
  centred and every point is weighted by its own error) and the **PDM** (phase
  dispersion minimisation), which assumes no shape and is the honest cross-check for
  an eclipser or a sawtooth. **"Both"** runs each and tells you whether they agree.
- **What you see**: the periodogram with the peak marked and the **FAP** levels
  (dashed lines, obtained by shuffling your own magnitudes), and the **curve folded
  to two cycles with one colour per night**, with error bars and a binned mean.
- **What the tool says, which is the important part**:
  - **cycles covered**: if the baseline does not reach two cycles, the period is
    **not fixed**. One 3 h night of a 0.127 d variable is one cycle: the periodogram
    will show a peak, but any peak out there is as good as an alias. The answer is
    another night or community photometry.
  - **FAP**: below 0.01 is a serious detection; above it, it may be noise.
  - **the spectral window**: if your observing pattern peaks right at the period
    found (the classic one-day alias), the warning says so.
  - **disagreement between methods**: if Lomb-Scargle and PDM give different
    periods, one of them is seeing a harmonic or an alias.
- **Saving**: "Save the period to the project" writes the period (with its method,
  its FAP and its cycles) into the project, and the project's curve folds by it. It
  is only saved when you ask, and only when there is a period.
- **Export**: the report PNG (like PerWin's/PhaseWin's, both panels) and a CSV with
  the whole periodogram and the folded curve.
- **The community's curve**: "Add the community curve…" fetches the AAVSO
  observations of the star (it needs the API token in Settings) and folds them WITH
  yours, grey and hollow, never mixed. This is how one night stops being the whole
  story and how the reference report was made.
- **Robustness**: "Leave out the flagged points" (on by default) keeps a point whose
  data is in doubt from steering the periodogram, and "Reject outliers" folds the
  curve by the first pass's period and drops what leaves its own phase bin, saying
  how many.

A real example: the **V0526 Per** series (244 frames, 2.9 h) peaks at 0.134 d with
FAP 0.016 and **1.0 cycles covered**. The observer's own report, with several nights
and ASASSN, gives 0.12695 d: the tool does not contradict it, it says exactly what
one night can say.

## 10. Live mode

**Optional and off by default.** Turn on **"Live (watch the folder)"** in the
series block: a light watcher observes the visit's folder, detects new frames
(waits for the file to stop growing, never reads a half-written one), measures
them with the same engine and updates the curve every few frames. Live files
need **no astrometry**: the reference plate seeds the target and the
comparisons.

## 11. ExoClock (manual submission)

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

## 12. External reduction with EXOTIC

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
   The app needs the first frame's astrometry: if it is missing, it solves it
   with the configured solver (local ASTAP or nova, ADR-051) and **stores the
   WCS in the FITS itself**, so the frame stays solved for any program. Pixel
   coordinates are never asked for by hand.
3. **Sequence**: open it in the editor (the Analysis door opens the visit
   there) and confirm the comparisons; the frame navigator in the left panel
   walks the visit, and **the open frame is the reference**.
4. **Reduce**: in the editor, **"Reduce and fit with EXOTIC..."** in the left
   panel (or Analysis → "Open the visit in the editor..."), and follow the log.
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

## 13. Troubleshooting

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

## 14. Glossary and links

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
