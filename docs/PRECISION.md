# Precision photometry in NightScribe: how it is achieved

*[Versión en español](PRECISION.es.md)*

This document answers one question: **what separates a 0.05 mag
measurement from a 0.005 mag one**. It serves two readers: the observer,
who wants the concepts and to get the most out of their equipment (part
one, no mathematics); and an AI or developer extending the
implementation (technical appendix at the end). Almost everything
described here already exists in NightScribe (phases G and H,
2026-09-23); phase I (same date) added the precision centroid
(`refined_centroid`) and the aperture suggestion from the growth curve
and the measured surroundings (`suggest_apertures` plus the Measure
tab's button); only the exoplanet-transit regime is pending a decision
(ADR-015).

Documentation of the base photometric process:
[PHOTOMETRY.md](PHOTOMETRY.md). This document is its quality sequel.

---

## Part I: for the observer

### 1. The two error budgets

Every photometric measurement carries two errors of different nature,
and mixing them up is the source of almost every disappointment:

* **Noise** is the needle's jitter. Photons arriving at random, a
  glowing sky, humming electronics. It goes down by collecting photons:
  longer exposures, more telescope aperture, or averaging measurements.
  It is honest and predictable.
* **Systematics** are a badly tared kitchen scale. They do not jitter:
  they lie always in the same direction. Optics that illuminate the
  corners a little less (a badly corrected flat), a filter whose
  response is not exactly the standard one, a comparison star that turns
  out to be variable. **No amount of averaging fixes them**: they are
  fought only by calibrating against known weights (the comparison
  stars) and by careful technique.

Precision photometry is, above all, the systematic hunt of the
systematics.

### 2. The quality ladder

From the free to the heroic; each rung "buys" a typical improvement, and
almost all of them already live in the FITS editor (Measure tab, phase
H):

| Rung | Where it lives | What it buys |
|---|---|---|
| Well-reduced plate (bias, darks, **flats**) | you, when stacking | a flat field: without it, 1–5 % error depending on position |
| Comparisons of similar colour to the target | you, Compare tab | removes most of the colour term |
| Aperture that follows the night's seeing | Measure tab (H3) | optimal SNR and night-to-night consistency |
| Well-estimated sky (robust median or plane) | Measure tab (H2a) | the SN stops being measured "galaxy included" |
| Your camera's real saturation level | Measure tab (H4: SATURATE card or `ccd_saturate` setting) | no clipped star sneaks in as a good one |
| Colour term fitted with the comps | Measure tab (H1) | your equipment's response stops biasing the zero |
| Host-galaxy subtraction (SNe) | Measure tab (H2b) | on galactic cores: from 0.05–0.15 to 0.03–0.05 mag |
| Per-frame normalization + detrending (series) | pending (ADR-015) | the transits' requirement: 0.001–0.005 mag relative |

### 3. Three scenarios, honest figures

* **Variable star on a good night, reduced plate**: the series flow
  gives Δmag with 0.02–0.05 mag total precision; the Measure tab
  (adaptive aperture, colour term and the check star watching) brings it
  to **0.01–0.02 mag**. Beyond that the colour calibration rules, and
  going further means measuring your own camera's transformation
  coefficients on standard fields (another league, noted as v2).
* **Supernova against a galactic core**: the enemy is not noise, it is
  the galaxy. The Measure tab does both things: the plane-fitted sky
  already improves the measurement, and with **host subtraction** (the
  PS1 reference aligned by the blink is subtracted, scaled so the stars
  vanish and only the SN remains) you go from 0.05–0.15 to **0.03–0.05
  mag**.
* **Exoplanet transit (hot Jupiter)**: the signal is a 0.01–0.02 mag
  dip lasting hours. Absolute accuracy is not needed; **extreme relative
  stability** is: every frame is normalized with its own comparison
  stars (a thin cloud must not fake a transit), the ensemble is weighted
  by each star's error, the aperture is chosen to minimize the check
  star's scatter, and the curve is detrended against air mass always
  showing the raw one beside it. With that and good practices, an
  amateur reaches 0.001–0.005 mag per binned point: enough for
  publishable transit curves. Today EXOTIC does that reduction (signed
  decision, ADR-015); doing it in-house is possible but is the major
  work item left.

### 4. When to trust a number

* **The check star is the traffic light**: the Measure tab measures it
  as if it were the target and compares it with its catalog value. If it
  moves, the variable is not to blame: the night, the plate or the
  sequence is not trustworthy. If only the target moves, that is
  astrophysics.
* **Saturation with a real level**: "almost saturated" does not exist.
  The ceiling comes from the SATURATE card or the `ccd_saturate`
  setting, not estimated from the frame itself.
* **The reported error vs. the total**: the panel distinguishes
  "internal" (photons) from "total" (plus comps' scatter, scintillation,
  colour and flats). Trusting the first number as if it were the second
  is the most common mistake.

### 5. What is what today

| Piece | Status |
|---|---|
| Sub-pixel centroid, aperture, median sky, guards | Exists (`core/series.py`) |
| Comparison sequences with catalog magnitudes (Gaia/APASS, VSX veto) | Exists (the FITS editor's Compare tab) |
| Δmag series with automatic ensemble + SN quick-look | Exists (`core/series.py`, Follow-up flow) |
| CSV / AAVSO EFF export | Exists (`core/photometry_export.py`) |
| Calibrated measurement on one plate (zero point from comps) | Exists (the FITS editor's Measure tab, phase G) |
| Colour term, gradient sky, FWHM aperture, real saturation, total error, check semaphore | Exists (phase H, 2026-09-23: `core/photometry.py` + Measure tab) |
| Host-galaxy subtraction | Exists (phase H: the blink's aligned PS1 reference, comp-scaled) |
| Per-frame normalized series + detrending for transits | Missing: pieces T1–T8; ADR-015 decision to revisit or scope |

---

## Appendix: the implementation's technical reference

**Status**: pieces H1–H7 are implemented (2026-09-23) in
`core/photometry.py` and `gui/ufe_measure_tab.py`, with tests in
`tests/unit/test_photometry.py` and `test_ufe_measure_tab.py`; phase G
(calibrated single-plate measurement) lives in
`docs/PLANS/ufe-photometry.md`. Pieces T1–T8 (transits) remain pending
the ADR-015 decision. This appendix stays as the reference specification
for future extensions.

House rules: the project header on every `.py`; code in English with
`# @args:`/`# @return:` comments; every visible string through
`self.tr()`; network only from `core/sources/` via `core/db.py`;
offscreen tests with a fixed `np.random.default_rng(<seed>)`; the legacy
dialogs are never touched; docs in natural language (the usual style
rule: colons, commas and semicolons; the en dash only for numeric
ranges).

### A. Single-shot improvements (variables, SNe): pieces H1–H7

Existing context, verified 2026-09-22 (do not re-explore):

* `core/series.py`: `_centroid(data, x, y, half=5)`,
  `aperture_flux(data, x, y, r_ap, r_ann_in, r_ann_out) ->
  (flux, sky_pp)`, `instrumental_mag`, `_is_unsaturated` (estimated
  ceiling: 99.9th percentile × 1.5, or absolute `sat_adu`), `R_AP=6.0`,
  `R_ANN_IN=10.0`, `R_ANN_OUT=15.0`, `_SAT_FRAC=0.85`.
* `core/compstars.py`: stars carry `bands` (APASS: direct B, V; Gaia: G
  plus derived B, V, Rc, Ic) and `star["bv"]` (direct or estimated;
  `color_origin` says which).
* `core/blink.py:prepare_pair` returns the PS1-g reference aligned to
  the plate's geometry (same centre/scale/rotation, up to
  `WORK_MAX=2048`): the base of the subtraction.
* `core/phototrans.py`, `core/photometry_export.py` (EFF with
  CNAME/CMAG/KNAME/KMAG).

The pieces, in impact-per-effort order:

* **H1. Colour term**: weighted fit of `(V_cat − v_inst) = ZP +
  k·(B−V)` over the comps (≥6 with colour spread; MAD-clip the residuals
  before quoting ZP±err); apply with the target's B−V (VSX for
  variables; SN: B−V≈0 assumed with a visible warning, or report
  untransformed). Pure numpy. Test: synthetic comps with a known slope
  are recovered; without colour spread the slope reports as
  undetermined and nothing breaks.
* **H2. Sky on a galactic core**, two levels:
  (a) a plane fitted to the annulus pixels (after 2.5σ sigma-clipping)
  evaluated at the star's position, instead of the flat median;
  (b) **host subtraction**: take the aligned pair from
  `core/blink.prepare_pair`, scale the reference by the flux ratio of
  the comps present in both images (the comps must vanish in the
  difference; their mean residual is the scaling criterion), subtract,
  and measure the SN on the difference image. The PS1-g reference is not
  calibrated to the user's filter: the comp fit absorbs that, and the
  docs must say so. Tests: synthetic gradient galaxy + known-flux SN;
  the post-subtraction measurement recovers the flux to 1 %.
* **H3. FWHM-based aperture**: FWHM measured from bright unsaturated
  comps (second-order moments after sky subtraction); `r_ap = k·FWHM`
  with k ∈ [1.2, 1.6], default 1.35; the annulus scales in proportion.
  Test: two synthetic seeings give different apertures and the measured
  SNR improves over the fixed one.
* **H4. Real saturation**: ceiling from the `SATURATE` card or a
  `ccd_saturate` settings key; fallback to the current estimator with a
  warning. Test: a star at 95 % of the ceiling is flagged and not
  measured.
* **H5. Honest total error**: CCD equation (gain/RON from header or
  settings, see D2 of the phase-G plan) + scintillation (Young 1967:
  `σ ∝ D^(−2/3) · X^1.75 · t^(−1/2) · e^(−h/8 km)`; site parameters in
  Settings with sensible defaults) + covariance of the ZP+colour fit +
  a configurable flat-residual floor (`flat_resid_mag`, default 0.007).
  The panel distinguishes "internal error" from "total error". Test: the
  total is never below the internal one; without gain it degrades with a
  warning.
* **H6. Check semaphore**: measure the check star on the same plate and
  compare with the catalog; |Δ| > 2.5·σ_total flags the measurement as
  "unreliable" with a plain-language explanation. Test: a plate with a
  simulated cloud (global flux scale) trips the semaphore.
* **H7. Outlier rejection in the ZP**: MAD-clip of residuals (already
  cited in H1; its own piece if H1 is skipped). Test: one corrupted comp
  does not move the median.

Everything lands in `core/photometry.py` (the phase-G module) and in
the Measure tab's panel; nothing touches the legacy flows.

### B. Exoplanet transits: pieces T1–T8

**Decision note (read first)**: ADR-015 signed that transit reduction is
100 % EXOTIC (the `inits.json` handoff; EXOTIC needs astropy and Python
≤3.10, vetoed by ADR-004). Implementing T1–T8 requires reopening ADR-015
or scoping the work as "high-precision calibrated series" while EXOTIC
keeps the transit fitting. Sign it with the user before writing code.

* **T1. Per-frame zero-point series**: every image is normalized with
  the comps measured on THAT image (extinction and thin clouds stop
  faking signal). Reuses `core/series.load_series`/`measure_series`,
  swapping the ensemble's global mean for a per-frame ZP.
* **T2. Weighted ensemble**: error-weighted mean per comp (or flux sum,
  AIJ's "superstar"), with a per-frame outlier veto (per-frame MAD).
* **T3. Optimal aperture per night**: sweep k in [1.0, 2.0]×FWHM keeping
  the one that minimizes the check star's rms; per-frame FWHM (small
  guiding wobbles no longer break the curve).
* **T4. Full noise**: H5 plus cadence; the per-point error must include
  scintillation (dominant in fast-cadence short exposures).
* **T5. Honest detrending**: against air mass at minimum; optionally
  against FWHM, sky level, centroid x/y (flat residuals). Golden rule:
  the raw curve always visible next to the detrended one, and the user
  docs explain that detrending can eat signal.
* **T6. Mid-exposure HJD**: `hjd_of` already corrects to the Sun; add
  EXPTIME/2 to the DATE-OBS card instant (a clearly documented
  convention).
* **T7. Per-frame quality gates**: saturation (H4), guiding jump
  (centroid shifted beyond a threshold), cosmic ray in the aperture
  (local sigma-clip), outlier ZP (cloud) flagged, not deleted.
* **T8. Observing practices**: a user-doc section (PHOTOMETRY): flats
  mandatory at mmag level, dithering, deliberate slight defocus,
  constant cadence, nothing saturated.

**Validation**: a seeded synthetic series with a known 0.01 mag dip
recovered to ±0.001 mag; and, once real data exists, a known transit
(e.g. HD 209458 b) with the depth recovered within 10 % and the check
star's rms inside what the noise model predicts.

### C. Global acceptance criteria

1. Every piece arrives with seeded unit tests and the full suite green
   (`.venv/bin/python -m pytest tests/unit`).
2. The user docs (PHOTOMETRY + PRECISION, both languages) explain the
   new piece with an example; i18n with no `unfinished` strings.
3. The legacy flows (series quick-look, blink, legacy chart, EXOTIC
   handoff) stay green untouched.
4. The reported total error is never smaller than the internal one; when
   a datum is missing (gain, saturation, B−V), the panel says so in
   plain language instead of staying silent.
