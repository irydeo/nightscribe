# How NightScribe raises the SNR of a faint object

> The techniques, the filters and the decisions that make a faint object
> emerge from the noise, explained **at three levels**: for the observer who
> uses the app, for the astronomer who wants the arithmetic, and for whoever
> maintains the code.
>
> The campaign's plan and its phase-by-phase results live in
> `docs/PLANS/astrometry-snr/`. What follows is the **what and the why**, not
> the work log.

---

# 1. For the observer

## What this is about

A faint NEO does not appear in a single frame: its signal is of the order of
the sky's noise. What makes it appear is **adding up many frames** along its
motion, and everything on this list exists so that sum reaches further. In
your 2025 UR data, with 3 s exposures, the object's signal in **one** frame
is about 2 times the noise; with 30 frames stacked it is about 11 times, and
the MPC asks for 20 to accept an observation. The difference between "I can
see it" and "I can send it" is exactly there.

## The six things the app does for you

**1. It does not lose frames.** If your visit mixes two runs (a pause, a
re-point), the app detects it, fits the small field rotation between them and
**stacks both**. It used to keep the first and throw the second away without
telling you. In your 140-frame visit: from 78 to **139 usable**, and the
stack's SNR went up **x1.48**. What it does leave out, it says, with **why**:
"too few stars" (a cloud) or "their stars did not agree on the fit" (a
satellite trail), and also "these frames do not contain the object" when the
second run's field points elsewhere.

**2. It weights each frame by its noise.** The **Weighted (1/sigma^2)**
method is the same clip as always and then each frame counts by the noise of
**its own** sky. On a stable night it comes out the same as the sigma clip;
on a night with thin cloud or moon it is what keeps a bad frame from
dragging the mean. It is opt-in because, measured, on a good night it
changes nothing.

**3. It measures with the matched filter, and that is the default.** The
**matched filter** weights each pixel by the star's expected shape instead of
summing a circle, and it is applied to the target **and to the comparisons**,
so the zero point comes from the same arithmetic. Measured on your frames:
**1.55 to 1.63x the SNR**, the zero point's error **2.6x smaller** and the
brightness bias at low SNR **halved**, for 3 % more time.

**What you can expect, and what you cannot.** The good: a faint object enters
where it did not before (1.57x the aperture's SNR, measured on real catalogue
stars too), the magnitude lands closer to the truth (the bias drops from
+0.54 to +0.23 mag at SNR 9) and it **removes the aperture's faint-star
bias**: against Gaia, the aperture underestimates the faint half by 0.037 mag
and the filter by 0.007. The risks, said plainly: it **moves the magnitude
that gets published**, so a curve started before this will show a step of
0.05 to 0.15 mag (towards the truth, not away from it); **its flux follows
the shape of the PSF**, so where the PSF changes across the field (a visit
with two runs, a field with coma) it can move by 0.1 mag from star to star,
which the zero point spreads out but does not erase (measured: 0.012 mag of
zero-point error against the aperture's 0.010); and it has **not** been
checked on host-subtracted images, nor with a trailed object. The aperture's
value is kept beside the reported one and the run says which method measured,
so you can always compare. To go back to the proven path, untick the box in
the Photometry tab's advanced settings.

**4. It tells you whether the object came out trailed.** If the object moved
during the exposure it comes out elongated, and the app says it with a
number: "the object is trailed by 2.4 px along PA 245". That is fixed next
night by shortening the exposure, and it is the cheapest improvement there
is. Below 1.5 px the object is called round, because a round star can read
that much from noise alone.

**5. It tells you how far you got.** When the run ends, the night's
**5-sigma limiting magnitude**, measured with your own stars, and the
**solution residuals** with the worst cell of a 4x4 grid (where a wrong
scale or a tilted chip shows up). And if the field is **not** sky-limited
(moon, short exposure, saturated comparisons), the app warns you that the
figure is not to be quoted.

**6. It can build you a flat from the frames themselves.** If you have no
flats (most people), the checkbox in the Calibration tab builds a
**pseudo-flat**: dust and vignetting are fixed on the frame and survive a low
percentile over the frames, while the stars move and do not. It needs the
sequence to be dithered, and it tells you when it is not. A real flat always
wins.

**7. Calibrate the frames before stacking them.** The **Calibrate the
frames** checkbox in the Astrometry tab applies the recipe (the masters of
the Calibration tab: dark/bias and flat) to each frame **as it is read**, so
the stacking never needs calibrated copies on disk. It matters more than it
looks: without a flat the object and the comparisons fall in different parts
of the vignetting, and **measured on a real visit that is worth 0.087 mag**
of systematic error in the magnitude. If you have no flat, the app builds
one from the frames themselves (it needs dither, and it tells you); a real
flat always wins.

## What you can do, which is what gains the most

- **More frames, not longer exposures.** SNR goes with the square root of the
  frame count: doubling the frames raises the SNR by 41 %. Doubling the
  exposure, on the other hand, trails the object if it moves.
- **Let the app tell you the maximum exposure.** The object card already
  computes the exposure before the object trails.
- **Dither.** Moving the telescope a little between frames not only removes
  the sensor's fixed pattern: it is what makes the pseudo-flat possible.
- **Do not throw the second run away.** If you stop and re-point, it is a
  different visit for the MPC but the app stacks them together, and it is
  grateful.

## What the app does NOT do, and why

**It does not put an AI denoiser in the measurement path.** Neural-network
noise reduction tools exist, very good at making a picture look nice, and
there is a paid one with a command line. **They do not come in here**: such a
filter **correlates the noise**, so the scatter we measured afterwards would
come out optimistic and the uncertainties sent to the MPC would stop being
true; and it can **move the centroid**, which is what astrometry lives on.
The MPC's SNR >= 20 floor exists precisely to keep marginal detections out,
and raising the SNR with a denoiser is exactly what that floor means to
prevent. The decision is written in ADR-063; if it ever enters, it will be
for presentation only, and the injection-recovery instrument will judge it.

---

# 2. For the astronomer

## The problem, in one line

For a sky-limited source the signal is `F` and the measurement's noise is
`sigma*sqrt(N_eff)`, where `N_eff` is the effective number of pixels being
summed. Raising the SNR therefore means **adding more signal** (more frames)
or **lowering `N_eff` without losing signal** (weighting better). Every
technique below is one of the two.

## T1. Stacking both runs of a visit

SNR grows with `sqrt(N)`. Recovering 62 frames out of 140 is not cosmetic: it
is `sqrt(139/78) = 1.34` in the best case. **Measured** on the 2025 UR star
stack: **1826 -> 2702 (x1.48)**.

The registration is a translation plus a rigid rotation about the centre.
The quality gate stopped being an absolute pixel figure and became a
**fraction of the measured FWHM** (0.25, floored at 0.5 px), because what
matters is how much the misregistration broadens the stack, and that is a
ratio: 0.8 px is harmless on 5.4 px of seeing and a lot on 1.2 px.

And a rule of honesty: **a frame that does not contain the object is not
stacked**. Registered is not the same as useful, and a shifted field only
adds noise where the measurement happens.

## T2. Inverse-variance co-addition

Combining `N` independent measurements of the same signal with different
noises `sigma_i` has a textbook optimum: the inverse-variance weighted mean,
because it minimises the variance of the result.

    sigma^2_combined = 1 / sum(1/sigma_i^2)   versus   sigma^2_mean = sum(sigma_i^2) / N^2

**Measured** on the two visits: the frame-to-frame noise varies 4.0 % on
2025 UR (gain 1.003x) and 11.0 % on 2026 PY9 (gain 1.022x). That is, **almost
nothing on these two nights**, and it is published as such. Modelled on the
2025 UR measurements themselves, if a tenth of the frames came out with
three times the noise (thin cloud), the gain would be **28 %**: it is
insurance for the night that breaks, not a silver bullet.

It has a second role: the per-frame `sigma_i` is the **noise model** the
matched filter needs.

## T3. The matched filter (the default since 2026-10-07)

**The default, by measurement and not by taste.** On the real 139-frame stack
of 2025 UR it wins on all three counts: **1.55 to 1.63x** the SNR, the zero
point's error **2.6x smaller** (0.035 against 0.092 mag, with 8 sources of
known flux) and the brightness bias at SNR 9 **halved** (+0.234 against
+0.541 mag), for **+3 %** of runtime. And at the edge that matters: with 30
frames of 3 s the MPC's submission floor (SNR 20) is reached around mag 18.5
and the detection gate is crossed between 19.9 and 20.9, so a 1.6x SNR is the
difference between being able to send an observation and not.

**The zero point against a real catalogue** (2026-10-07, 40 Gaia EDR3 comps
from mag 13.5 to 19.5 on the real 139-frame stack): the filter's SNR is
**1.57x** the aperture's and the zero point's error lands at **0.0119 against
0.0095 mag**. Split in halves, the filter wins on the faint one (0.063
against 0.118 mag per star) and the aperture on the bright one (0.037 against
0.117), and the bias against the catalogue explains it: the aperture
**underestimates** the faint half by +0.037 mag, the filter by +0.007. The
whole chain agrees with the sky: the object measures 17.94 (aperture) and
18.09 (filter) where the ephemeris predicts 18.25 V.

**The limit that is left, measured**: the filter's PSF is a Gaussian from the
measured seeing and its flux follows that shape
(`2*sm^2/(sm^2 + sg^2)`), so where the PSF changes across the field the
filter carries a positional bias the aperture does not have: on this visit
the aperture-minus-filter difference steps by about 0.2 mag where the second
run starts contributing (corr with x +0.75). The fix that would remove it is
measuring the PSF per region or per comp, and it has not been done because it
costs 0.002 mag of zero-point error. Still unchecked: the
**host-subtracted image** path (in one test it recovers 9.6 % less flux than
the aperture) and a **trailed** object (line PSF). None of that is hidden:
the aperture's value goes beside the reported one and the run says which
method measured.

With a known shape `m` (normalised, `sum m = 1`) and white noise `sigma` per
pixel, the best **linear** estimate of the flux is

    A = sum(m (p - sky)) / sum(m^2)       SNR = A sqrt(sum(m^2)) / sigma

and its SNR is the largest any linear filter reaches on that data
(Cauchy-Schwarz: the optimal weight is proportional to the shape). An
aperture is the case `m = 1` inside the circle, which gives the noisy wings
the weight of the core: it is **not** optimal.

The effective area is `N_eff = 1/sum(m^2)`, so the gain over an aperture of
area `N_ap` is `sqrt(N_ap/N_eff)`.

**Measured** on the real 139-frame 2025 UR stack (FWHM 4.63 px, aperture
r = 6.3 px, `N_ap = 203`, `N_eff = 80`):

| Star peak | Aperture SNR | Filter SNR | Gain |
| --- | --- | --- | --- |
| 19,744 | 1,088 | 1,771 | 1.63x |
| 15,792 | 1,227 | 1,909 | 1.56x |
| 15,552 | 995 | 1,565 | 1.57x |
| 14,560 | 923 | 1,497 | 1.62x |

and `sqrt(203/80) = 1.59` is what the formula predicts: theory and
measurement agree.

**Monte Carlo verification** (200 realisations): the measured gain lands on
`sqrt(N_ap/N_eff)` within 5 %, and the filter's flux has less scatter than
the aperture's with the same noise.

## T4. The trail

A uniform segment of length `L` convolved with a round PSF of width `sigma`
gives a Gaussian whose long axis carries

    sigma_long^2 = sigma^2 + L^2/12

(the variance of a uniform segment), so from the second moments
`L = sqrt(12 (sigma_long^2 - sigma_short^2))` comes back, and the position
angle of the major axis comes out of the covariance's eigenvectors. With the
measured shape, the matched filter is built with a **line PSF** and filters
the object as the line it actually is.

Second moments are sensitive to the window: with 4 FWHM the noise of the
wings dominates and a **round, bright** star reported **1.56 px of trail**.
Hence the **2-FWHM** window and the **1-sigma** threshold, and hence
`TRAIL_MIN_PX = 1.5`: below that, the object is called round.

## T5. Diagnosing the night

**Limiting magnitude.** For a sky-limited source,
`log10(SNR) = a + b*mag` with `b = -0.4` (a magnitude is a factor
`10^0.4 = 2.512` in flux and the noise does not care how bright the star is).
Fitting that line to the measured stars and solving it for SNR = 5 gives the
limiting magnitude **of that night**.

The fit is **Theil-Sen** (the median of the pairwise slopes), not least
squares with a clip: with seven points and one saturated comparison the clip
does not repair a dragged line (the wrong line inflates the MAD the clip is
measured against) and the limit moved **0.5 mag**; the median of 21 pairs
does not move. It also needs no threshold to tune, which on five points is a
hunch dressed as a parameter.

**And the slope is the check**: `b` must come out near -0.4. **Measured**
with 14 stars from the real 139-frame stack: **-0.394**, a 1.5 % agreement
with the law. A field far from that (moon, short exposure, saturation) is
flagged and the figure is not quoted.

**Solution quality.** The median residual per cell of a 4x4 grid: one number
for the whole plate hides the corners, which is where a wrong scale or a
tilted chip shows up. Median per cell (one bad match cannot paint a corner
red alone) and a cell with no stars stays **empty**, never zero.

## T6. The pseudo-flat

Dust and vignetting are **fixed** on the frame; the stars **move**. A low
percentile over the frames (33 %: the sky and the stars only add light) keeps
the train and is biased away from the stars, and the smoothing (41 px, much
larger than the PSF and much smaller than the vignetting) takes out what is
left. Normalised to a median of one, it is a multiplicative flat.

It does not replace a real flat: it measures the train's response **times**
the sky's shape, so the flat-field error is larger. It is the honest
fallback, and the recipe says which one was used.

**When the stars do not move, there is no pseudo-flat.** With a sidereal
mount (the normal case) the same star sits on the same pixel all night, so
the percentile keeps it and the "flat" divides every star by itself: a flat
that carries the stars is worse than no flat. Measured on the author's own
2025 FG18 visit, a comparison star on a bright star came out **1.08 mag**
off. What IS usable from those frames is the **vignetting**, which is smooth
and fixed: the app masks the sources (what is more than 5σ above the
smoothed percentile, dilated 12 px) and fits a degree-4 surface. Measured
against a real master flat of the same night, the agreement is within ~3 %
(median 0.9963, p5–p95 0.954–1.045) and the fine structure it does not
correct (the dust) is worth 0.6 % = 0.007 mag. The recipe says
`vignette_model` and the note says what it is and what it does not correct.

## T7. The calibration, inside the stacking

A stack of uncalibrated frames keeps the pedestal, the thermal current, the
dust and the vignetting. For the **position** it matters little (the centroid
is local), but for the **magnitude** it matters a lot: the zero point is
measured on the comparisons, and if the object falls in a zone with a
different transmission than they do, the error goes straight in. Measured on
a real visit, the smooth part of the vignetting is worth **0.087 mag**, and a
dust spot under the object much more.

The recipe is ADR-061's and it is applied **on read** (`FrameCalibrator`),
not into copies: the engine reads each frame many times and in pieces, and a
calibrated copy per frame would be gigabytes of I/O. Measured with the P4
instrument, the same injection with and without the pseudo-flat: **0.0707
mag** of correction and the SNR from 32.9 to 34.0.

## T8. What measures the result: injection and recovery

Everything above is a claim. The instrument that measures it puts a source of
**known** flux, at a known place, moving at a known rate, into **copies** of
the real frames, runs the real chain on them and compares with the truth.

**Measured** on the first 30 frames of 2025 UR (3 s each, injected motion
1.5 px/frame):

| Flux | Magnitude equivalent | Detected? | SNR | Position error |
| --- | --- | --- | --- | --- |
| 12,000 ADU | 17.93 | yes | 32.9 | 0.14 px |
| 5,000 ADU | 18.88 | yes | 13.2 | 0.14 px |
| 2,000 ADU | 19.87 | yes | 5.6 | 0.14 px |
| 800 ADU | 20.87 | no | 1.7 | - |
| **no injection** | - | **no** | **0.0** | - |

With 30 frames of 3 s: the detection gate (3.5 sigma) is crossed between
mag ~19.9 and ~20.9, the submission floor (SNR 20) is reached around
mag ~18.5, and the position is recovered to **0.14 px** even at SNR 5.6. The
control with no injection gives SNR 0: the pipeline does not manufacture
detections.

---

# 3. For the developer

## Where everything lives

| What | Module | Main entry point |
| --- | --- | --- |
| Registration, quality gate, report | `core/register.py`, `core/track_stack.py` | `register.trusted`, `register_sequence`, `registration_report`, `inside_frame` |
| Co-addition and weights | `core/track_stack.py` | `combine`, `_sigma_clip_keep`, `frame_weights`, `_frame_noise` |
| PSF and matched filter | `core/photometry.py` | `gaussian_psf`, `empirical_psf`, `measure_matched`, `psf_elongation` |
| Diagnosis | `core/photometry.py` | `limiting_magnitude`, `quality_grid` |
| Pseudo-flat | `core/calibration.py` | `pseudo_flat`, `calibrate(pseudo_flat=...)` |
| Injection and recovery | `core/injection.py` | `inject_sequence`, `recover`, `completeness`, `truth_of` |
| The zero point against a real catalogue | `benchmarks/zp_catalog_check.py` | `load_visit`, `pick_comps`, `compare` |
| Orchestration | `gui/workers.py` | `TrackStackWorker`, `CalibrationWorker` |
| What the observer sees | `gui/ufe_trackstack_tab.py` | `_register_note`, `_shape_note`, `_diag_note` |

## The invariants that must not be broken

1. **A frame that does not contain the object is not stacked.** `inside_frame`
   is the gate; `_indices` applies it. Skipping it puts noise exactly where
   the measurement happens.
2. **A read is never 1-D.** `calibration.read_image` always returns 2-D. A
   1-D "image" makes scipy take a 2x2 rotation for a homogeneous matrix and
   crash three layers up with a message that blames the matrix.
3. **`_source_box` returns `None` when there is no overlap**, and
   `_warp_to_box` then returns an invalid frame **without reading**. Never a
   box "one pixel outside".
4. **The aperture and the filter measurements share centroid, sky and
   sigma.** Otherwise the comparison measures something else.
5. **The matched filter does not replace the aperture in the report.** The
   ADR-022 validator and the MPC expect the aperture; the filter is a
   measured second opinion.
6. **An injection's truth lives in the file's header**, not in a session
   variable.
7. **A figure without its check is not published**: the limit's slope against
   -0.4, the pseudo-flat's residual against the dither, the filter's gain
   against `sqrt(N_ap/N_eff)`.

## The mistakes found while measuring (and which repeat)

- **The moments' window.** With 4 FWHM a round, bright star reported 1.56 px
  of trail. Window of 2 FWHM and a 1-sigma threshold.
- **The sign of the sub-pixel shift** in the bench: the star fell in the
  corner, the stack came out with FWHM 12 px instead of 4.6, and the first
  measurement of the matched filter gave **0.62** (it looked worse than the
  aperture) instead of 1.6. **The first measurement of an improvement usually
  measures the bench.**
- **A clip with few points** does not repair a dragged line: Theil-Sen.
- **`np.percentile` over bands** costs 197 s where `np.partition` costs 12 s,
  with the same result.
- **scipy's error** that blames the matrix when the image is 1-D.

## How to extend it

- **A new combination method**: add it to `METHODS`, implement it in
  `_combine_masked` or as its own function, and **use `_sigma_clip_keep`** if
  it clips: the clip has to reject the same pixels in every method. Add it to
  the tab's combo with its `tr()` and its tooltip.
- **A new measurement**: `measure_point` gives the centroid and the sky; a
  new measurement must **reuse them** and return its own `snr`, as
  `measure_matched` does, so that comparisons are comparisons.
- **A new diagnostic**: return `{"ok", "reason", ...}` with the `reason` in
  English (the core speaks English; the interface translates), like
  `limiting_magnitude` and `quality_grid`.
- **A new SNR technique**: measure it with `nightscribe inject` **before**
  believing it, and write the number in the code's comment and in
  `docs/PLANS/astrometry-snr/`.

## How it is verified

```bash
.venv/bin/python -m pytest tests/unit              # fast, no network
.venv/bin/python -m nightscribe inject <folder>    # the real reach
```

The campaign's tests: `test_track_stack_register.py` (the second run and the
frame off the field), `test_track_stack_stack.py` (the weights and the two
stacking paths), `test_photometry_matched.py` (the filter against the
formula, Monte Carlo), `test_photometry_diagnostics.py` (the limit and the
grid), `test_calibration_pseudo_flat.py` (the pseudo-flat against a known
vignetting) and `test_injection.py` (the instrument).
