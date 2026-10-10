# Minor-planet astrometry: user guide

> The techniques that raise the signal-to-noise (stacking both runs,
> weighting by 1/sigma^2, the matched filter, the trail, the diagnosis and
> the pseudo-flat) are explained at three levels, observer, astronomer and
> developer, in `docs/SNR.md`.

*How to measure a faint asteroid with NightScribe and report it to the MPC.*

---

## 1. What it is and what it is for

A faint asteroid that moves cannot be photographed well: short exposures
carry too much noise, long ones leave a trail. The answer is stacking: take
a sequence of short frames, work out how far the object moved between them
and shift them digitally **the other way** before combining. The asteroid
stays still in one point (where its light adds up) and the stars become
trails the algorithm rejects.

NightScribe does that end to end: it calibrates, stacks following the
motion from the ephemeris, measures the position two ways, contrasts it
with what other observatories see and generates the Minor Planet Center
report. The field's reference is Tycho-Tracker, and the quality check rests
on Find_Orb, the same tool the community uses.

## 2. Before you start: calibration

A faint object does not emerge if the frame still carries the sensor's
thermal pattern and the optical train's dust. NightScribe uses a **master
library** (bias, dark, flat) that you build elsewhere; the app only points
at it.

- You index each master from the **Calibration tab** of the editor (or from
  Settings → Measurement). It is keyed by camera, gain, temperature, exposure
  and filter, which is what makes a master valid. A **flat does not have to
  share the lights' gain**: it is normalised before it is applied, so the gain
  only scales its whole level, never its shape (measured: the author's own
  flats were taken at gain 3 and the lights at gain 5, and requiring the same
  gain used to lose the flat).
- For the light a **dark at its own exposure** is preferred (it already
  includes the bias; subtracting a bias as well would subtract it twice).
  Without a dark the bias is subtracted and the app warns that the thermal
  current remains.
- The **flat** is corrected per filter, with its own dark-flat removed and
  normalised, so the division does not change the frame's brightness.

If a piece is missing the app says so in plain language; it never fails
silently or invents a calibration.

## 3. The flow, step by step

Everything starts in a **visit** (one night of a NEO, comet or PCCP
project). No visit, no series: that is the house rule.

1. **Open the Astrometry tab** from the visit and press the big button:
   **Stack the sequence**. On entering you see three things and nothing else:
   the object with its frames and its window, the button (painted in the
   **object kind's colour**, with its glyph) and a line saying **what it will
   do** with the current values ("8 frames · 1 observation · brightness with
   G 5.0/9.0/14.0 · calibration: dark + flat · check against other
   observers"). Everything else lives in **cards** with a title (a bordered
   group, so an expanded one shows where it ends): the **decisions** ("How many
   observations" and "Stacking settings") are always there and start closed,
   and the **result** appears with the run, open, in cards of its own ("What
   the run found", "The observations", "Measurement per observation", "Manual
   mark", "Check against other observers" and "Report"). The occasional actions
   (the blink figure, undoing the run) are behind the **⋯** menu in the header.
   Nothing has disappeared: it is one click away, and the default is what most
   nights want. Outside the cards there are only the object, the button, its
   subtitle and the progress bar with its status line.

   The apparent rate and the position angle come from Horizons when the run
   starts and land in the run's notes. The calibration (the Calibration tab's
   recipe: dark/bias and flat) is applied to each frame **as it is read**, with
   no copies on disk, and it **comes on by itself when the library has a master
   that matches** this camera and filter: for a faint object it matters for the
   magnitude, because without a flat the object and the comparisons fall in
   different parts of the vignetting and that is **0.087 mag** measured on a
   real visit. The moment you touch it, your choice rules. If you have no flat,
   the app builds one from the frames themselves: it masks the stars out of it
   and, for the pedestal, it needs a dark/bias (with none it says so, because
   the flat's shape then comes out compressed).
2. **Choose how many observations you want.** The MPC prefers several
   measurements spread in time over a single one. You give a number and the
   software splits the sequence into contiguous equal groups. The table
   shows the **expected SNR of each group**: SNR grows with the square root
   of the frame count, so asking for more observations splits the signal,
   and it is worth seeing that before accepting.
3. **Stack.** The app solves the first frame, aligns the rest on the stars
   and shifts each frame so the object always lands on the same point. You
   can pick the combination: **sigma-clipped** (the default, and the one to
   use: measured by injecting sources of a known brightness into a real
   207-frame visit and measuring them back, it reaches magnitude **18.23**),
   median, mean, sum, or **weighted (1/sigma^2)**. The median is **0.26
   magnitudes shallower** (17.97 on the same frames) for a plain statistical
   reason: the median of N measurements is 1.25x noisier than their mean, and
   the clip already rejects the star trails (it discards about 17 % of the
   pixels here) without paying that. Mean and sum differ only in scale and
   keep the trails, which is what the clip is for. Weighted is the same sigma
   clip, and then each frame counts by the noise of **its own** sky: on a
   stable night it comes out the same as sigma-clipped (measured: 0.3 % on
   2025 UR and 2.2 % on 2026 PY9), and it is what saves a night with thin
   cloud or moon, where a frame with three times the noise would drag the
   whole mean (modelled on those same frames: up to 28 %).
   Two things that look like depth and are not. The **resampling** (the
   "Resampling" setting) only changes the look: the bilinear, which is the
   default, and the cubic tie at magnitude 18.20 against 18.21 while the pixel
   noise differs by 29 %, so a smoother image is not a deeper one, and that is
   why the pixel noise of a smoothed stack is not used as a measure of reach.
   The cubic and the quintic are there for a crowded field, where sharpness
   rules. And the frames the registration leaves out are left out for a reason
   worth knowing: on that same visit the 21
   refused frames had a much worse seeing (8.34 px against 5.08), and
   stacking them **costs 0.11 magnitudes** because they broaden the stack's
   point spread. Every stack's header says how it was made (`NS_COMB`, the
   method; `NS_ORDER`, the interpolation; `NS_NUSED`, the frames that went
   in; `NS_LEFT`, the ones left out), so a saved file can always be audited
   (ADR-068). The
   final stack of each observation covers the **whole frame** by default,
   which is what the photometry needs (comparison stars all around); short
   on memory or time you can shrink it to 1024, 512 or 256 px, and the
   velocity sweep keeps working on the object's own trail cutout.
   If the visit mixes **two runs** (a pause, a re-point), the app says so
   in the result: "the visit looks like 2 runs: the second one is 884 px
   away and starts 5 min later", with the field's rotation. Those frames
   **stack anyway**: the registration fits the field's small rotation (up
   to 15 deg) and recovers frames that used to be thrown away. The ones
   that really do not fit (a cloud, a satellite trail) are left out **with
   their reason**, never silently. Measured on a 2025 UR visit: recovering
   the second run took the star stack's SNR from **1826 to 2702 (x1.48)**.
   The stacking uses **every core it can**: the number of threads is computed
   by itself, from the processor and the memory one task needs, so there is
   nothing to configure. Measured on a 16-core machine with 60 frames of
   1024²: the sweep fell from 6.3 s to **1.3 s** (x5.0), the final stack from
   10.1 s to **2.7 s** (x3.7) and the combination from 957 ms to **298 ms**
   (x3.2). If you want to cap the threads (because the machine is busy with
   something else), the **`astrometry_threads`** setting allows it: 0 is
   automatic.
   Besides each observation's stack, the app saves the **whole sequence's**
   stack into the project (`<object>_base.fits`): every frame combined with
   the object frozen, the deepest image of the visit. It is the one the manual
   mode marks on, and you can open it in the Photometry tab to look at the
   field. It carries its own header (the cutout's WCS, date, exposure, filter,
   the motion and the magnitude with their source, and the detection made on
   it), so reopening it the band says the same as on the night of the run.
4. **Velocity sweep.** The ephemeris and the mount have real small drifts,
   so 25 combinations (±5 %) around the theoretical velocity are tried and
   the one that gives a brighter **and** rounder object is kept. That is the
   fine tuning, with two guards (ADR-062 rev): the ephemeris' own prediction
   is **one of the candidates**, measured on the same pixels, and the sweep's
   winner is only used when it beats it by more than three times the grid's
   own scatter. When it does, a second finer pass (3×3, no extra disk reads)
   takes the PA resolution from the grid's 4.5° to about 0.9°. Measured
   before this: the app published PA 33 where the ephemeris says 41.8
   (2025 HL5) and 37 where it says 46.2 (2025 FG18), exactly one grid step.
   When the sweep does not improve on the ephemeris, the reported rate and PA
   are the ephemeris' prediction and the note says so.
5. **Centred sequence.** A GIF or a montage of the N observations, all
   centred on the object: if it is there in every panel the detection is
   solid; if one panel is empty, you see it. The tab also carries a **strip
   of thumbnails** with the N observations at one stretch: clicking one
   brings it to the main view to work on it.
6. **Measurement.** The object is measured twice: on the final stack and
   frame by frame. Both use the same centroid, so their comparison means
   something. If they differ by more than 0.5″ or 3σ, the point is flagged.
7. **Brightness.** The magnitude is measured on the **stacks**, not on the
   frames: on a single frame a faint NEO barely shows (SNR 2) and its
   aperture ends up chasing noise. The object is measured on **its** stack,
   where its light is concentrated, and the comparison stars on a **second
   stack** of the same frames aligned on the stars, because on the object's
   stack they are streaks and a streak calibrates nothing. It is the
   Tycho-Tracker recipe, and it costs one more stacking pass: you can turn
   it off with the **"Measure the brightness"** box, and then the run
   reports positions only and says so. One measurement is made **per
   observation**, which is what the MPC publishes. The comps come from the
   sequence you have saved in the project; with none, the app proposes one
   automatically and says so, because an automatic proposal is a starting
   point, not your choice. The settings (apertures, sky method, centroid,
   colour term) are the **Photometry tab's**: they are edited there and
   nowhere else, and this tab's line tells you, before the run, what the
   brightness will be measured with.
   The run also tells you the **object's shape** on its stack: if it comes
   out **trailed** (say 2.4 px along PA 245) the exposure was long for that
   motion, and shortening it is the cheapest improvement there is. And it
   **measures with the matched filter** (weighting each pixel by the
   expected shape instead of summing a circle), which is the **default**
   since 2026-10-07: measured on a real 139-frame stack it gives **1.55 to
   1.63x the aperture's SNR** and a zero point **2.6x better**, for 3 % more
   time. It moves the magnitude that gets published (0.05 to 0.1 mag,
   towards the truth) and it has unchecked paths; the box in the Photometry
   tab's panel turns it off and the run says which method measured and what
   the other would give.
8. **Check.** NightScribe downloads the object's published observations (or
   the NEOCP ones if it is not confirmed), runs them through **Find_Orb**
   together with yours (excluding yours from the fit) and compares your
   residual with the others' cloud. Outside the cloud, the report is
   blocked by default.
9. **Report.** It is generated in **ADES PSV** and **MPC 80-column**,
   validated with the same validator as always and sent to the visit's MPC
   block. You do the sending.
   When it finishes, the app also tells you **how far you got**: the night's
   **5-sigma limiting magnitude**, measured with your own stars (and warning
   when the field is not sky-limited, in which case the figure is not to be
   quoted), and the **solution residuals**, with the worst cell of a 4x4
   grid, which is where a wrong scale or a tilted chip shows up.
10. **Read them back later.** In the project's **Analysis** tab, the
    **Astrometry runs** block lists every pass: the date, how many
    observations it measured, the motion it resolved, the brightness, the
    check and the state. The magnitude says **who wrote it**: *automatic*
    (the run itself) or *by hand* (a measurement you made in the Photometry
    tab and sent to the report with **Use for the report**; the run's own
    value is kept beside it, for the audit). From there you can **open the
    visit in the editor** or **undo** a whole execution (its positions go;
    the row stays marked as undone). A run with **no detection** is listed
    too: "we looked and there was nothing" is data, and the next night
    needs to know it.
    Reopening the visit shows the run again, without stacking anything: the
    notes, the table, the group viewer, the strip, the blink and the
    **report** come back from what was saved (the run's own summary in the
    database, its points and the stack files it wrote, one per observation
    plus the whole sequence's stack, inside the project). The status line says
    so, and **Stack** is still there if you want to redo it. A saved run that
    found nothing comes back with its notes (how deep the night reached), not
    with an empty column.
11. **The manual mode, whenever you want.** The **"Manual mode (faint
    object)"** box appears with **any run** (not only a "not detected" one): it
    is useful for an object below the gate and also to place by eye the
    centroid of one that WAS detected. It opens a small window where you mark the object on the
    **whole sequence's stack**: the click snaps to the **gaussian centroid**
    of the nearest source, a short **cross** shows where the mark is (with its
    own switch), and the arrows nudge it in **0.1 px** steps. **Measure at the
    mark** runs the pipeline again from your mark, carrying its offset (the
    prediction's error, constant over the visit) to every observation, with
    the gate bypassed and the velocity sweep skipped. The note says the
    position came from a **human mark** and the table flags the point as
    measured from your mark: the mark is your signature and it travels with
    the figure. The red cross of the measured position stays on the plate: it
    is anchored to the sky, so it survives loading another image of the series
    and switching to the Photometry tab. On a track & stack the **project's own
    object mark is switched off**: the stack already carries the run's measured
    position, and two marks (at the plan's coordinates and at the measured ones)
    read as an error. The top-bar toggle brings it back if you want it.
12. **Tune the brightness without re-stacking.** The Photometry tab's recipe
    (apertures, sky, comps, and what the band reports) used to be frozen when
    the run started, so changing it meant re-stacking the whole visit. The
    Astrometry tab now has **Re-measure the brightness**: it re-runs the recipe
    on the **saved stacks** of the observation on stage (the object's and the
    star's) and rewrites only the stack's band. The position and the detection
    are untouched. It needs the run to have kept the **star stack** (the box in
    the panel); without it the button says so.

## 4. What each figure means

- **SNR**: how many times the object's signal beats the background noise,
  measured with the **astrometry's own aperture** (not with the photometry
  recipe): it is the number the detection gate, the position's error and the
  submission floor use, which is why the **matched filter does not change
  it** (it changes the brightness, which has its own pair of signal-to-noise
  values, said in the notes).
  Below 3.5σ the app does **not** run the sweep: sweeping over noise and
  keeping the best is how a false positive is made. It still **measures the
  brightness** (ADR-062 rev), at the ephemeris' own position, and marks it
  **red** with a note: a marked number is worth more than no number. The
  table's magnitude is green when the measurement is clean, orange when it is
  usable but not clean (a large error, only three comps, no check star) and
  red when it is not to be published without looking at it.
- **Submission SNR**: a different threshold. The MPC recommends **20 or
  more** to submit and forbids marginal detections, so a group below the bar
  does not go into the report and the reason is explained. The app ships **10**
  (the author's own Tycho submissions ran at about 16 and were accepted) and
  you change it in **Settings → Measurement**, together with the detection gate,
  the velocity sweep, the cutout margin, the check and the threads. When **no**
  observation clears it, the report's own group says so, with the floor's
  number and where it is set, and the button that sends the report stays
  disabled: a report with no observations is not a report.
- **Residual**: how far your measurement is from what the orbit predicts,
  in arcseconds.
- **Scatter of the others**: how far they are. It is the fair scale: with a
  bad orbit every residual is large, and what matters is whether you are
  **outside the cloud**, not how far you are from zero.
- **rmsRA / rmsDec**: your position's uncertainty, itemised (centroid, WCS,
  timing).
- **Magnitude limit**: how deep the stack went. It is useful even with no
  object: it says whether the night could have given more.
- **Brightness**: the object's magnitude measured on the stacks against the
  comps, with its band (Gaia G when the comps are Gaia's, the usual case
  with a Clear filter). It comes with the number of comps and observations
  behind it, and with its error. The star stack also brings a **check
  star**: if it leaves its catalogue value, the night did not behave and
  the run says so.
  When the zero point rests on **too few comps** the run says **why** the
  others were dropped (off the plate, saturated, non-linear, no positive flux,
  no catalogue value) and warns that the large error is the honest consequence
  of a thin sequence: a big error stops looking like a bug and becomes a figure
  with a cause.
  What the band **reports** is a choice of the **photometry recipe** (Photometry
  tab): the **measurement** or the **ephemeris' prediction**. A measurement not
  worth reporting (too few comps, a trailed object) is replaced by the labelled
  `(eph)` figure without hiding it: the measurement stays in the run and in the
  astrometry point.
- **Distinct observatories and last observation** (on the object card):
  many and recent means a live, well-determined object; one and months ago,
  a candidate to be lost.
- **The plate's band** (the strip at the top, over the image) says where each
  figure comes from, and that is why **every number carries its word**: the
  velocity and the PA go with **`(measured)`** when the velocity sweep
  measured them and with **`(eph)`** when they are the ephemeris' prediction;
  the magnitude goes with `(measured)` if it was measured on that plate, with
  `(eph)` if it is what the ephemeris predicts (it always appears, even when
  the run did not measure the brightness) and with `(cat)` if it is the
  catalogue's or the project's. Over the whole-sequence stack the band adds
  the **detection made on it**: `SNR 1.4 (gate 3.5σ)` and `limit 19.4` (the
  limit magnitude).

## 5. When to trust it and when not to

- **Dithering**: if the sequence never moved, the sensor's pattern noise
  stacks into phantom detections. The app warns about it (it is the number
  one cause the MPC documents). Move the telescope between frames.
- **The check filters, it does not prove**: the MPC itself warns that on a
  short arc a wrong observation fits just as well. The real proof is a high
  SNR and seeing the object in the centred sequence.
- **A faint object's brightness is demanding**: it comes from the stack, so
  it no longer suffers a single frame's noise, but it does depend on the
  field having comps of a similar brightness and on the object's stack not
  being crossed by a bright star's streak. The tab tells you which
  apertures and which sky the run will use before it starts: when something
  does not add up, that is where to look.
- **No reference does not block**: if the object is a discovery and nobody
  else has seen it, the check says there is nothing to compare with and does
  not block; the SNR and the sequence decide.
- **An object recovered after months** may have a drifted orbit: a large
  residual may be the orbit's fault, not yours.

## 6. Find_Orb: installation and setup

The check rests on Find_Orb, which NightScribe does **not** distribute: it
only detects your copy and runs it. It needs the **non-interactive**
executable (`fo` on Linux/macOS, `fo64.exe` on Windows).

- **Linux/macOS**: `micromamba install -c conda-forge findorb` (it brings
  `fo`, `find_orb` and the DE430t ephemerides). Or build from source.
- **Windows**: `find_c64.zip` and `fo64.exe` from Project Pluto, in the
  same folder.
- In **Settings**, point the Find_Orb field at `fo` and press "Test". The
  **Install…** button does it for you: first it checks whether `fo` is
  already on PATH (the common case: you installed it and the app was never
  told) and points the path at it; if it is not there, it looks for
  **micromamba**, **mamba** or **conda**, creates a **private** environment
  with the conda-forge package `findorb` (inside the folder you choose,
  touching nothing of your setup) and shows you what it is doing. With no
  manager found it says what to install and what to type: the app does
  **not** download a package manager on its own.

NightScribe writes the observation file, runs `fo` in a temporary folder
with its own environment (`-D`) and a CPU limit (`-r`), and reads the
residuals from `total.json`. If Find_Orb is not configured the check is
**not available** and the app says so; it never fakes a verdict.

## 7. Freeing space

One night is hundreds of FITS. Once the stack, the sequence and the report
are saved, the app **offers** to move the used originals to a `procesados`
folder inside the project (it does not delete them: they can be restored)
and to delete the exported calibrated copies separately. Only the frames of
a successful run, and nothing moves without your confirmation.

## 8. Troubleshooting

- **"Not available" in the check**: almost always you pointed at the
  interactive `find_orb` instead of `fo`.
- **The object does not appear**: check each group's SNR, try fewer
  observations (more frames per group) and make sure the sequence is
  dithered.
- **"N frames do not contain the object and were left out"**: the visit
  mixes two runs and the second one points elsewhere, so the object falls
  off the sensor in those frames. They are left out **on purpose**:
  stacking them would add noise exactly where the object is measured. If
  there are many and you did not expect two runs, check that the ephemeris
  is for the right object.
- **"N frames could not be aligned"**: the result says **why**. *Too few
  stars* is usually a cloud, fog or too short an exposure in that frame;
  *their stars did not agree on the fit* is usually a satellite trail, an
  aircraft or a guiding jump. If the message adds that **the visit looks
  like several runs**, there was a pause or a re-point: those frames stack
  anyway, and splitting the visit is only worth it when the runs are from
  different nights. And remember the runs overlap only in part: comparison
  stars outside the common area cannot be measured in every frame.
- **Large residuals everywhere**: the orbit may be poor; look at the
  others' scatter before blaming your measurement.
