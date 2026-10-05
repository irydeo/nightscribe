# Minor-planet astrometry: user guide

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

- In **Settings** you index each master. It is keyed by camera, gain,
  temperature, exposure and filter, which is what makes a master valid.
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

1. **Open the Astrometry tab** from the visit. At the top you see the
   object and its ephemeris (apparent rate and position angle).
2. **Choose how many observations you want.** The MPC prefers several
   measurements spread in time over a single one. You give a number and the
   software splits the sequence into contiguous equal groups. The table
   shows the **expected SNR of each group**: SNR grows with the square root
   of the frame count, so asking for more observations splits the signal,
   and it is worth seeing that before accepting.
3. **Stack.** The app solves the first frame, aligns the rest on the stars
   and shifts each frame so the object always lands on the same point. You
   can pick the combination: **sigma-clipped** (the professional standard:
   nearly all of the mean's signal with the median's cleanliness), median
   (fast, for trying), mean or sum. Mean and sum differ only in scale. The
   final stack of each observation covers the **whole frame** by default,
   which is what the photometry needs (comparison stars all around); short
   on memory or time you can shrink it to 1024, 512 or 256 px, and the
   velocity sweep keeps working on the object's own trail cutout.
4. **Velocity sweep.** The ephemeris and the mount have real small drifts,
   so 25 combinations (±5 %) around the theoretical velocity are tried and
   the one that gives a brighter **and** rounder object is kept. That is the
   fine tuning.
5. **Centred sequence.** A GIF or a montage of the N observations, all
   centred on the object: if it is there in every panel the detection is
   solid; if one panel is empty, you see it. The tab also carries a **strip
   of thumbnails** with the N observations at one stretch: clicking one
   brings it to the main view to work on it.
6. **Measurement.** The object is measured twice: on the final stack and
   frame by frame. Both use the same centroid, so their comparison means
   something. If they differ by more than 0.5″ or 3σ, the point is flagged.
7. **Brightness.** The magnitude is measured on the frames, **not** on the
   stack: on a stack that follows the object the comparison stars are
   trails, and measuring them there would be wrong. The series engine is
   reused, so every frame is calibrated against a set of comps (with a MAD
   veto) and the **median** of the curve is taken, with its error from the
   MAD. The comps come from the sequence you have saved in the project; with
   none, the app proposes one automatically and says so, because an
   automatic proposal is a starting point, not your choice.
8. **Check.** NightScribe downloads the object's published observations (or
   the NEOCP ones if it is not confirmed), runs them through **Find_Orb**
   together with yours (excluding yours from the fit) and compares your
   residual with the others' cloud. Outside the cloud, the report is
   blocked by default.
9. **Report.** It is generated in **ADES PSV** and **MPC 80-column**,
   validated with the same validator as always and sent to the visit's MPC
   block. You do the sending.

## 4. What each figure means

- **SNR**: how many times the object's signal beats the background noise.
  Below 3.5σ the app does **not** run the sweep: sweeping over noise and
  keeping the best is how a false positive is made.
- **Submission SNR**: a different threshold. The MPC recommends **20 or
  more** to submit and forbids marginal detections, so a group below the bar
  does not go into the report and the reason is explained.
- **Residual**: how far your measurement is from what the orbit predicts,
  in arcseconds.
- **Scatter of the others**: how far they are. It is the fair scale: with a
  bad orbit every residual is large, and what matters is whether you are
  **outside the cloud**, not how far you are from zero.
- **rmsRA / rmsDec**: your position's uncertainty, itemised (centroid, WCS,
  timing).
- **Magnitude limit**: how deep the stack went. It is useful even with no
  object: it says whether the night could have given more.
- **Brightness**: the object's magnitude measured on the frames against the
  comps, with its band (Gaia G when the comps are Gaia's, the usual case
  with a Clear filter). It comes with the number of comps and frames behind
  it, and with its error: if the object is very faint per frame, the error
  says so instead of hiding it.
- **Distinct observatories and last observation** (on the object card):
  many and recent means a live, well-determined object; one and months ago,
  a candidate to be lost.

## 5. When to trust it and when not to

- **Dithering**: if the sequence never moved, the sensor's pattern noise
  stacks into phantom detections. The app warns about it (it is the number
  one cause the MPC documents). Move the telescope between frames.
- **The check filters, it does not prove**: the MPC itself warns that on a
  short arc a wrong observation fits just as well. The real proof is a high
  SNR and seeing the object in the centred sequence.
- **A very faint object's brightness is noisy**: if the object barely shows
  in a single frame (SNR of 2 or 3), its per-frame magnitude scatters widely
  and the final figure depends on how many frames go in. The position
  suffers less, because the stack does add signal. If the brightness really
  matters, lengthen the sequence or ask for fewer observations.
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
- In **Settings**, point the Find_Orb field at `fo` and press "Test".

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
- **Large residuals everywhere**: the orbit may be poor; look at the
  others' scatter before blaming your measurement.
