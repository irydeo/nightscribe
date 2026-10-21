# Changelog

All notable changes to NightScribe are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **The "Saved" line no longer moves the buttons.** It appeared on the first
  save and stayed, pushing the Analyse button **77 px** down under the
  observer's own cursor, once, for good. It keeps its room now and goes away by
  itself after a couple of seconds, which is what a confirmation is for.

- **The plate's own ceiling gates the measurement when the plate is not from
  your camera.** The camera profile's linearity limit is written in your ADU,
  and ADU are a property of one instrument: a Las Cumbres plate (a 248 800 ADU
  ceiling) was refused frame after frame as "nonlinear" and the chart came out
  empty with no explanation. The full well in electrons is what tells the two
  detectors apart, and the panel now says which of the two cases it is.

- **The plate's filter becomes a band only when it really is one.** A plate
  whose `FILTER` card says `R` against a sequence that carries `Rc` used to
  fall to the first band of the list, which is a silent wrong calibration (the
  zero point then hangs from another band's magnitudes). A Cousins `R` is the
  catalogue's `Rc`; a Pan-STARRS `rp` is **not**, and pretending otherwise
  would be inventing one.

- **A series that measured nothing says why.** No more empty chart with a clean
  list of frames next to it: the panel counts the flags, names the one that
  dominated and says what to do about it.

- **A series that finishes no longer closes the workbench.** Saving the
  measurement refreshed the project by RE-OPENING it, and opening a project
  switches the screen to it: the editor the series had just been measured in
  closed itself, and the page it rebuilt took the visit window down with it.
  The project's own blocks (the visits list with its counts, the curve, the
  cadence line, the runs and the header) refresh where they are now, and the
  visit window comes back filled when the observer leaves the workbench.

- **"Measure the series…" answers the first click.** The workbench is not
  instant to open, and on a real 379-frame visit it took **2.5 seconds** during
  which the window did not repaint: with the visit window still on top, the
  pause read as a dead button, so the observer pressed again and the second
  press got the credit for opening it. The visit window steps aside BEFORE that
  work, and the whole open now wears the wait notice, so the press is answered
  on the spot. And the open got **1.8 seconds shorter**: arming the Track &
  Stack tab's context reads the header of every frame of the visit (1.85 s for
  379 of them), and that was being paid even when the editor was opened for the
  series. A tab now arms itself when it takes the stage, which is when it is
  looked at.

- **The airmass and the site are taken from the plate, not from your
  Settings.** The engine computed the target's altitude from the site
  configured in Settings, which is right for your own observatory and wrong
  for anybody else's plate: on a Las Cumbres plate (a 1 m at McDonald) reduced
  from a site in Spain the airmass came out **rising to 5.2 through the night**
  where the plate's own header said 1.16 to 1.03. That number feeds the
  scintillation term of the error, so the error grew from 0.05 to **0.39 mag**
  over the night, which the chart reads as green, then orange, then red. With
  the plate's own cards the same errors are flat at 0.03. The same rule the
  plate scale already followed applies now to the time: **what the plate says
  about itself wins over the observer's Settings**, and the Settings are the
  fallback for a rig that declares nothing. The detrend benefits too, since the
  airmass is its regressor: **re-measure a series** to get the corrected errors
  and the corrected trend (the points already stored keep the old numbers, they
  are the record of what was measured).

- **The telescope's size is read from the plate as well.** It is the input of
  that same scintillation term, and a Las Cumbres 1 m measured with the
  observer's 10" got it 2.5 times too big. Only a plate that really states the
  size is trusted, because that is the only way to read it without inventing it:
  Las Cumbres writes it into the telescope's own id (`1m0a`, `0m4c`, `2m0a`),
  while a name like `Cecilia` or `CDK17` says nothing about the size, and there
  the observer's Settings stay: for their own telescope that is the right answer
  anyway. With both cards read, the errors of the series that was reported went
  from 0.05 to 0.39 mag across the night (the green-orange-red ramp) to a **flat
  0.016**.

### Changed

- **The detrend starts from "auto" for every kind of project except a transit.**
  The extinction is a systematic that is always there, and a rotation, an
  outburst or a pulsation do not share its timescale, which is what makes the
  trend separable. It is the self-limiting policy: it always applies the
  airmass and only adds the extra terms when the scatter really drops. A
  transit keeps the raw curve on purpose, because its trend is solved together
  with the model (EXOTIC's own airmass term).

## [0.1.3] - 2026-10-21

### Fixed

- **The editor's list of frames now shows what the series said about each
  one.** The light curve marked a frame whose measurement the series had thrown
  away while the list of frames showed nothing wrong, so an observer looking at
  an empty chart and a spotless strip of frames could only conclude that his
  data were bad: on the night this was reported **338 of 379 frames carried a
  flag and the strip said nothing at all**. The list marks them now with the
  same classification the curve reads (`core/series_measure`): a data flag
  (nonlinear, cloud, seeing, a cosmic ray, a frame that could not be aligned)
  makes the frame a problem and the "only problems" filter keeps it; a caveat
  (a thin comparison set) is a note and never hides a frame. The mark names the
  flag and explains it in the tooltip, and the border wears the colour the
  measurement deserves: the same grammar the curve and the measurement panel
  already share.

## [0.1.2] - 2026-10-20

Fixes the one thing that could take a working EXOTIC environment away, and stops
the app from claiming there is no Python when there is.

### Fixed

- **"Prepare environment" can no longer destroy the environment you already had.**
  It used to wipe the target folder *before* building, so any failure after that
  (no network, no disk space, a cancel) left nothing behind; and one case did it
  every single time: the app offers the environment it already built as the base
  interpreter, the wipe took that interpreter away halfway through the build, and
  the next command could not even run. It now builds in a sibling folder and swaps
  it in only once the new environment works, so a failed rebuild is harmless.
- **A base interpreter that lives inside the environment folder is refused**, with
  the reason written out, instead of being deleted mid-build.
- **The app no longer says "no Python found" when the configured interpreter is
  gone.** That message, on a machine with a perfectly good Python installed, is
  what made a deleted environment look like a lost configuration. It now tells the
  two cases apart ("the interpreter you pointed at is not there any more" and "it
  is not one EXOTIC can use") and goes looking for another interpreter on its own.
- The outcome of "Prepare environment" always reaches the log, so a failure leaves
  a trace instead of a silence.

### Added

- **The EXOTIC environment is published ready to unzip.** It is now built and
  published by the project, in its own release (tag `exotic-env`), as one zip per
  platform with a portable CPython 3.11 and EXOTIC 4.3.1 already installed inside:
  unzip it anywhere and point Settings at the interpreter it carries. Nothing to
  install, no Python to hunt for. The versions inside are pinned in a lock file
  committed in the repository, so the same zip is always the same stack, and the
  release is only rebuilt when that lock changes.

### Changed

- **EXOTIC accepts Python 3.10 to 3.12**, not only 3.10 and older. 3.10 reached end
  of life in October 2026, and refusing 3.11 and 3.12 forced people to hunt for an
  interpreter the app could already have used. 3.11 is verified end to end: a full
  `pip install exotic` on 3.11.2 leaves EXOTIC 4.3.1 importable with every version
  it pins (numpy 1.26.4, astropy 6.1.7, numba 0.59.1). 3.13 stays out, because
  numpy 1.26 has no wheels for it.

## [0.1.1] - 2026-10-19

Fixes photometry on **normalised** plates (the 32-bit float masters with values
from 0 to 1 that PixInsight and Siril write by default) and a track & stack run
that died without saying why.

### Fixed

- **Comparison stars are found again on a normalised plate.** The validation of
  each candidate mixed units: it read the signal from the plate (0 to 1) and
  computed the noise with the CCD equation, anchored in electrons per ADU. The
  read-noise term, which does not scale with the plate, drowned the signal and
  **every** candidate was refused as "SNR 0 in the aperture", so the proposal
  came back empty. Measured on a real plate (a magnitude 20.5 NEO, 10 s frames):
  0 comparisons before, 8 plus the check star after.
- **The error bar is the right one again on those plates.** The same mismatch
  made the magnitude error of a real star come out as **52 magnitudes** where
  the honest answer is 0.012. And when measuring a **series** on a 2020
  transient's stacks, the stored points carried errors of **228 to 384
  magnitudes**: the same point, with the fix, comes out at 0.09.
- **Both ceilings guard again on those plates.** Saturation and the linearity
  limit are compared in ADU, so on a 0..1 plate they never fired: a peak of 0.9
  sailed past a 53 000 ADU limit without a word.
- **A target the plate cannot measure no longer kills the track & stack run.**
  The path that measures the target on its own stack and the comps on another
  multiplied the target's centroid by the plate scale, and a target that cannot
  be measured comes back with a `None` centroid: the run died with a `TypeError`
  instead of reporting the reason it already carried. Seen with two real
  objects, one of them forty pixels from the field's edge.

**If you are still on 0.1.0 and hit this**, the provisional way out is to
measure on a plate in ADU: the individual frames, or a master multiplied by
65 535 to give it its scale back. 0.1.1 no longer needs it.

## [0.1.0] - 2026-10-18

The first public release. NightScribe follows an observatory project through its
whole life: **plan the night, understand the object, capture and reduce, and
tell it**. It is a beta: expect rough edges.

### Added

**Plan the night**
- A ranked, explained list of what is worth observing tonight from your site and
  with your equipment, across eight kinds of targets: NEOs (confirmed and NEOCP
  candidates), comets, comet candidates (PCCP), supernovae, exoplanet transits,
  close approaches, HADS stars, and variable stars and duties.
- A 0–100 score with its "why tonight" sentence, the local horizon and the
  limiting magnitude, the Moon's interference, the session's feasibility and the
  cost in telescope minutes.
- The Sun and the Moon, a 60-day sky calendar computed offline, and Jupiter's
  moon events (transits and shadows) for your site.

**Understand every object**
- An object card that turns orbital and physical parameters into plain language,
  with orbit, sky, survey-field and light-curve charts and capture chips
  (magnitude, rate, longest trail-free exposure, window, copyable coordinates).

**Capture**
- It drives CCDciel (complete) or NINA/PINS (in test) and points the telescope:
  send the plan, start and stop the run, and watch it with the last frame
  previewed in the window.
- Export the ephemeris (MPC elements or orbit report) and the capture sequence.

**Reduce, in the unified FITS editor**
- Calibration: an indexed library of masters by camera, gain, temperature,
  exposure and filter, with a declarative recipe and normalised flats.
- Track & stack: solve, register and combine, with a per-frame position, a
  dithering warning, the centred sequence (GIF or montage) and a manual mode for
  a weak object.
- Photometry: single measurements with guards, comparison sequences with the
  finder-chart picker, series with an ensemble veto and quality gates, the
  period search (Lomb-Scargle, PDM, FAP by bootstrap) and the transit fit with
  the EXOTIC handoff.
- Astrometry: sub-pixel centroids, per-frame and stack combination, the MPC
  report (ADES XML/PSV and 80 columns), the submission, the check against other
  stations with Find_Orb and the ExoClock export.
- Freeing space: archive a visit's originals inside the project and bring them
  back, never overwriting a recaptured frame.

**Projects, visits and campaigns**
- Every target becomes a project with its own folder and a Card, Capture,
  Analysis, Publishing flow; each night is a visit; campaigns and variable-star
  vigils carry their own cadence.
- The observation journal, the "needs your attention" dashboard and the daily
  check of the vigils against ZTF and the AAVSO community photometry.

**Tell it**
- Bilingual (ES/EN) post and tweet drafts with the night's charts, from the real
  session data, with an optional AI pass.

**Interface and languages**
- Three tabs (Tonight, Projects, Campaigns), the unified FITS editor, the
  Spanish and English interface and the offline user guide.

**Command line**
- Plan and publish from the terminal: `tonight`, `explore`, `post`, `solar`,
  `blink`, `history`, `sequence`, `inject`, `project` and `gui`.

**Optional assistant**
- Off by default: it answers from the app's own guide and ADRs, offline, through
  a model you configure.

**Distribution**
- Windows installer (per-user, no admin rights) and portable zip, a `.deb` for
  Debian 13+ and Ubuntu 25.10+, a `.rpm` for Fedora 42+ and openSUSE Tumbleweed
  and a PKGBUILD for Arch. Find_Orb travels inside them and the docs travel with
  the app.
- An OpenCL GPU path for the registration and the combine, on by default, that
  falls back to the processor.

### Notes

- This is the first public release, so it is a **beta**: expect rough edges.
  Report them at <https://github.com/irydeo/nightscribe/issues>, attaching the
  log (**Help → Open the log**).
- Find_Orb travels inside the Windows installer and the Linux packages; EXOTIC
  (the transit reduction) is the one external tool you install by hand.
- The **NINA/PINS** integration is **not finished**: it is there to be tried and
  to report what is missing or broken, and the rest is planned for **0.2**.
  CCDciel is the complete one today (chapter 05 lists what NINA/PINS does not do
  yet).
- The Windows binaries are **unsigned**: Smart App Control blocks them outright
  and SmartScreen warns until reputation builds, so the installer may need an
  explicit *Run anyway* or a machine with Smart App Control off. The details are
  in docs/user/01-getting-started.
