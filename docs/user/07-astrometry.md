# 07. Astrometry

Minor-body astrometry (asteroids, NEOs, comets) lives in the **Astrometry**
tab of the FITS editor, and its engine is *track & stack*: stacking your
frames **following the object's motion**, not the stars'.

## First of all: solving the plate

Everything astrometric needs a **plate solution** (the WCS: which point of
the sky each pixel is). Under **Settings → Measurement → Plate solver** you choose:

- **Auto** (recommended): tries local **ASTAP** first (fast, offline, free)
  and falls back to **nova.astrometry.net** if you do not have it or it
  fails.
- ASTAP only, or nova only, if you prefer.

With *Save the solved WCS into the FITS header* (on by default), the
solution is written into the FITS header (pixels are never touched) and any
other program will see it.

> **Why ASTAP first?** Because it solves in seconds on your machine, with no
> uploads and no dependence on someone else's queue. Nova is the fallback:
> slower and API-key based, but truly blind (it does not need to know where
> you were pointing). The combination covers 99% of cases without you having
> to decide.

## The track & stack

**Stack the sequence** runs the whole pipeline: solves the reference,
registers the frames against each other, sweeps the object's velocity
(fetched from Horizons when the run starts), detects, stacks each
observation, measures and checks. While it runs, the same button is Cancel.

The key decision is **Observations**: into how many observations
(measurement points) you split the sequence. Each observation is a
contiguous group of frames with its own middle-of-exposure instant (T_mid).

> **Why does the number of observations matter?** Because SNR grows with the
> square root of the frames: asking for more observations *splits* the
> signal and each one reaches less far. Next to the selector you will see
> the SNR each observation is expected to reach with the current split.
> Three solid observations are worth more to the MPC than six weak ones; the
> practical rule is: just enough to see the motion, no more.

> **Why T_mid and not the exposure start?** Because the object's position
> during the exposure is the mean of its travel, and its best estimator is
> the central instant. Reporting the start introduces a half-exposure bias,
> which on a fast NEO (5″/min) means tens of arcseconds of systematic error.
> The MPC expects T_mid; NightScribe computes it for you.

### The stack options, and their motivation

- **Method** (how the frames are combined): the **sigma-clipped mean** is
  the default because it reaches about a quarter of a magnitude deeper than
  the median (a median is 1.25 times noisier than a mean) and, unlike the
  plain mean, it rejects satellite trails and cosmic rays. **Weighted** is
  the same clip with each frame weighed by its own sky noise: on a stable
  night it changes nothing, and it is what saves a night with thin cloud or
  Moon. Use the **median** only when something must be rejected outright and
  the clip cannot.
- **Resampling**: **bilinear** (default) gives a visibly cleaner image *at
  no cost in depth* (measured by source injection, not assumed). **Cubic**
  keeps a marginally sharper PSF with a grainier image: use it if you are
  chasing detail in a crowded field. Beware: a smoother image is not a
  deeper one; depth is decided by the method above and the frames that go
  in.
- **Field**: how much sky each observation's final stack covers. The whole
  frame keeps the comparison stars around; a smaller window is faster and
  lighter. The velocity sweep always works on the object's own trail cutout,
  whatever this says.
- **Apply the calibration**: applies the Calibration tab's recipe to each
  frame as it is read. Without it, the optical train's dust and vignetting
  leak into the stack and, since the object and the comparisons do not sit
  in the same place, the smooth vignetting alone is worth a systematic error
  of a tenth of a magnitude in the brightness.
- **Measure the brightness** and **Keep the star stack**: the magnitude is
  measured on the object's stack and on a second stack aligned on the stars
  (on the object's stack they are streaks). Without comparisons in the
  field, the run reports positions only and says so.

## Reading the result

The panel shows what the run found: the session's dithering, the composed
WCS quality, the velocity sweep, the detection and the brightness. Each
observation is measured **twice** with the same centroid recipe: on the
stack and frame by frame. A disagreement beyond 0.5″ or 3σ is flagged;
it is never resolved silently.

The **Re-measure the brightness** button re-runs the recipe on the
observation's **saved stacks** (the object's and the star's) without
re-stacking the visit, and rewrites only the stack's band: the position and
the detection are untouched. It needs the run to have kept the **star stack**.
When a track & stack is open, the project's own object mark is switched off:
the stack already carries the run's measured position, and two marks (at the
plan's coordinates and at the measured ones) read as an error.

**Animate / verify** plays the observation stacks centred on the object with
one shared stretch: the object must stay put in the middle while the stars
crawl. That is the acid test that the detection is real. **Save animation…**
writes that very loop as a GIF or an MP4, with the levels you applied and the
plate's heading on every frame, so the proof can be shared. **Blink /
montage…** writes the figure (GIF or montage) with the same stretch on every
panel, so a faint one does not look as bright as a real one.

If the object is below the detection gate, **Manual mode (faint object)…**
lets you mark it by hand on the whole-sequence stack: the position is yours
(snapped to the centroid, nudgeable in 0.1 px steps) and the velocity is the
ephemeris', with no sweep.

## The check against the published data

After the run, NightScribe compares your points with the object's already
published observations (the MPC API, or the NEOCP if not yet confirmed) and
gives a verdict: whether your point fits or stands out.

> **Why "the check filters, it does not prove"?** Because fitting a short
> arc does not prove a detection: it proves you do not contradict it. The
> check exists to catch mistakes (a misidentified object, a wrongly solved
> scale), not to certify reality. If your point stands out, the report is
> blocked by default; **Force the report** forces it while leaving the fact
> on record in the report's own note.

## The MPC report

**Generate** writes the report with the middle-of-exposure instants, the
propagated uncertainties and the magnitude only when there are comparison
stars. Every observation below the **submission floor** (SNR ≥ 20, settable
in Settings) is left out, with its reason.

> **Why an SNR floor?** Because the MPC archives your measurements forever
> and uses them for orbits: a point with SNR 8 carries a position
> uncertainty that spoils everyone else's fit. Better not to submit than to
> submit noise. The floor is yours: lower it if you know what you are doing,
> but the default is what experience dictates.

- **Format**: **ADES PSV** is the modern, machine-readable format the MPC
  prefers; **80-column** is the classic one, readable by every program. If
  in doubt: ADES.
- **Send to the MPC block** fills the visit's paste box; the validator in
  that window has the last word before saving.
- If you configured **Find_Orb** in Settings, the app cross-checks your
  measurements against the orbit it computes itself and shows you the
  residuals before you submit.
- **Undo this run** removes this execution's observations from the project
  (the run stays, marked undone, for the audit trail); everything else is
  untouched.

Next: [08. Reporting it](08-posts.md).
