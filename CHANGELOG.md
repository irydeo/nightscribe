# Changelog

All notable changes to NightScribe are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.1] - 2026-10-19

Fixes photometry on **normalised** plates: the 32-bit float masters with values
from 0 to 1 that PixInsight and Siril write by default.

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
