# Photometry in NightScribe: how the light is measured

*[Versión en español](PHOTOMETRY.es.md)*

The user guide to the photometric reduction process exactly as
NightScribe implements it: what the program does with your images, with
which parameters, and what precision you can expect from the numbers
that come out. Everything described here exists in the code today;
nothing is a promise.

---

## 1. The idea in three sentences

1. Photometry **measures light**: it counts how many photons from a
   star landed on each pixel; it does not measure an "absolute
   brightness".
2. The atmosphere, the telescope and the camera dim or amplify **all**
   the stars in the same image equally.
3. That is why we measure **differentially**: the target against
   comparison stars on the very same plate. What is common cancels out;
   what remains is the true difference.

This is called **differential aperture photometry**: the classic
photoelectric-photometer technique carried onto the CCD/CMOS.

---

## 2. From FITS to magnitude, step by step

This is what NightScribe runs (in `core/series.py`) every time it
measures a point. The quoted parameters are the program's real default
values.

### 2.1 Locating the target with sub-pixel precision

The target position comes from the plate's WCS or from your click. Since
it falls between pixels, it is refined with a **centroid**: in the
editor, a gaussian matched filter (the seeing PSF measured on the plate)
correlating the cutout on a 0.1 px lattice with parabolic refinement:
it lands within hundredths of a pixel with decent signal and within a
few hundredths on faint sources when the noise allows; when it does
not, it keeps your point and says so. The series quick-look keeps its
classic moment centroid (comparability during the review).

When marking with the mouse (Measure, Annotate, Compare), the cursor
becomes a crosshair with a reticle that **snaps to the gaussian
centroid** of the source under the mouse: the click is born centred.

### 2.2 The aperture and the sky annulus

```
            . . . . . . . . . . . .        sky annulus:
            .                     .        between r = 10 and r = 15 px
            .    . . . . . . .    .        (sky only; the median
            .    .           .    .         ignores neighbouring stars)
            .    .  aperture .    .
            .    .   r = 6   .    .
            .    .    px     .    .
            .    .           .    .
            .    . . . . . . .    .
            .                     .
            . . . . . . . . . . . .
```

* **Aperture**: a circle of radius 6 pixels centred on the centroid. It
  captures nearly all the starlight without swallowing too much sky.
* **Sky annulus**: a ring between 10 and 15 pixels, far from the star
  but close to its surroundings. Its **median** is used (not the mean:
  the median is immune to pixels of neighbouring stars falling in the
  ring).

### 2.3 From flux to instrumental magnitude

**Formula 1: the net flux**

```
net flux = sum of the aperture pixels
           − median sky × number of aperture pixels
```

**Formula 2: the instrumental magnitude**

```
instrumental mag = −2.5 × log10(net flux)
```

It is "instrumental" because it depends on your equipment, your exposure
and your sky: it is only comparable within the same image (or sister
images of a series, once matched). Which is why the next step is needed:
comparing.

### 2.4 Automatic guards

Before trusting a measurement, the engine discards it when:

* the star is **saturated** (its peak exceeds 85 % of the frame maximum:
  near the sensor's clipping the numbers lie);
* the sky annulus **touches the edge** of the image or another detected
  source (the star is not isolated);
* the net flux comes out **negative or zero** (there is no measurable
  star there).

---

## 3. The comparison stars: two paths

NightScribe has two ways of getting "the other stars", depending on
where you come from.

### 3.1 The automatic ensemble (supernova series)

In the series quick-look (the Follow-up tab of a SN project), the
program picks its own comparisons:

1. **Detection** of stellar sources on the reference frame: 3×3 local
   maxima above `sky + 5σ` of the background noise, at least 10 pixels
   apart.
2. **Constancy veto on variables**: every candidate is measured in ALL
   the frames of the series; if its scatter exceeds 0.1 mag it was a
   variable and is out. Also out: saturated, non-isolated, or not
   measurable in at least 80 % of the frames.
3. They are ranked by scatter (the most constant first) and **up to 8
   stars** are taken (3 is the healthy minimum).

It is the astronomer's criterion turned algorithm: a good comparison is
the one that does not move.

### 3.2 The catalog sequence (the FITS editor's Compare tab)

For photometry with catalog magnitudes, the **Compare** tab of the FITS
editor brings stars of known magnitude around the plate centre:

* **Gaia EDR3**: native G magnitude and B, V, Rc, Ic **estimated** from
  the BP−RP colour with the Riello et al. 2021 transformations (valid
  for BP−RP between −0.5 and 4.0; Rc/Ic only up to 2.75). Derived values
  are always marked "(est.)".
* **APASS DR9**: **direct** B and V, plus the Sloan bands.
* **VSX veto**: any star cross-matched with the AAVSO variable-star
  catalog gets a red ring and can never be chosen as a comparison.

The chosen sequence (click by click, or the automatic proposal matched
to the target's brightness) exports to CSV with every band.

### 3.3 The calibrated measurement (the FITS editor's Measure tab)

With the plate loaded and the sequence built, the **Measure** tab turns
one click into a catalog magnitude:

1. The click measures the target (centroid, aperture, sigma-clipped sky;
  the section 2.4 guards speak in plain language: "saturated", "too
  close to the edge", "no measurable signal").
2. The sequence stars are measured **on the same plate**, with the same
  aperture: that is what makes comparable comparable.
3. The **zero point** is the median of `catalog mag − instrumental mag`
  over the comps, with its error from the median absolute deviation
  (MAD) divided by √N; stars lacking the chosen band or not measurable
  are skipped and counted.
4. The target's magnitude is `instrumental + ZP`, with the combined
   error: the CCD equation (when the header carries GAIN/RDNOISE;
   otherwise the comps' scatter only, and the panel says so) plus the
   zero-point error.

The panel shows everything used and everything refused, and the default
band is V (direct in APASS, Gaia-estimated via Riello 2021, and the
panel marks it). The measurement exports to a one-row CSV or an AAVSO
EFF line with the sequence in CNAME/CMAG/KNAME/KMAG. The FITS file on
disk is never modified.

**Quality controls** (phase H, 2026-09-23):

* **Sky**: flat median by default; on galactic cores the "Plane" mode
  fits a ramp to the annulus and evaluates the sky at the star's
  position (the flat median is biased there).
* **Aperture follows the seeing**: the comps' FWHM is measured on the
  plate and the aperture is sized at 1.35 × FWHM (the fields stay
  visible and hand-adjustable).
* **Precision centroid** (phase I): the position is refined with the
  local sky subtracted, only significant pixels weighted, the box scaled
  to the seeing and two passes; on faint sources or over gradients it
  lands within hundredths of a pixel of the truth, instead of the raw
  moment's tenths. The ring and the "Pixel" line sit at the measured
  centroid, not at the click; when it moved more than 1 px, the panel
  says so.
* **"Suggest apertures"**: proposes the radii from the target's own
  growth curve and its measured surroundings (nearest neighbour,
  background gradient), and explains the reasons in plain language in
  the panel; your hand edit is never stomped on its own. The 99 %
  plateau rule is only believed within what a point source allows
  (4 × FWHM): when the curve never flattens there (a blend, or a
  mis-subtracted sky), it proposes the seeing aperture and says why.
* **Colour term**: with at least 6 comps carrying B−V spread, the fit
  is `ZP + k·(B−V)` applied with the target's B−V. That B−V is no
  longer assumed in silence: when the click lands on a star of the
  field loaded in Compare, its own B−V is used, and the panel always
  states the provenance (field, project, by hand, or assumed); when it
  is assumed and the fitted slope is large, the panel quantifies the
  risk in magnitudes. Without enough spread, a plain zero point, and
  it says so. Comp outliers are MAD-rejected before fitting.
* **Real saturation**: the ceiling comes from the header's SATURATE
  card or the `ccd_saturate` setting; when nobody knows, the plate
  gives itself away: dozens of pixels pinned at the frame maximum can
  only be a clipping level, and any star peaking next to it is refused
  as "clipped". It matters because the CMOS roll-off compresses cores
  long before a plateau forms: comps measured on compressed cores pull
  the zero point LOW coherently, and the check star, compressed alike,
  cannot rat on it (its traffic light reads scatter, not a shared
  bias). The panel itemises the exclusions by cause and warns out loud
  when clipping removed comps.
* **Catalog cross-match**: after every measurement the panel says which
  source of the field loaded in Compare sits under the centroid, how
  many arcsec away, and its catalog magnitude against ours (Δ). For a
  SN or a new candidate the expected answer is the opposite: "no
  source within 8″".
* **Honest total error**: the panel distinguishes "internal" (photons,
  when the gain is known) from "total" (plus ZP scatter, Young
  scintillation with your aperture and site height from Settings, the
  colour term and a 0.007 mag flat floor configurable as
  `flat_resid_mag`).
* **The check star as a traffic light**: when the sequence has one, it
  is measured and compared with its catalog value; beyond 2.5σ_total
  the measurement is flagged NOT reliable before you trust it.
* **Subtract host galaxy**: downloads the aligned PS1 reference (the
  blink's one), scales it so the stars vanish, and measures the target
  on the difference image; the comps calibrate on the original plate.
  For SNe on cores this is the difference between "not measurable" and
  "0.03–0.05 mag".

**Formula 3: the differential magnitude**

```
Δmag = instrumental mag(target) − mean(ensemble instrumental mags)
```

If the SN sits 2 mag below the ensemble mean today and 1.5 mag tomorrow,
it has faded by 0.5 mag: the absolute zero does not matter, the
**evolution** is the signal.

### 3.4 Measuring faint supernovae on their host galaxy (field lessons)

A 16-18 mag SN sitting on its host's glow is the most delicate case of
aperture photometry. These are the options the FITS editor offers today
and when each one pays off (lessons paid for with real 10 s,
Clear-filter plates):

**The comparison sequence**

* ✅ Comps **close in brightness** to the target: the automatic proposal
  already prefers them (a brightness window around the target), and when
  only much brighter ones exist, each star's reason flags the saturation
  risk.
* ❌ Comps "the brightest in the field, they have the best SNR": on a
  short Clear exposure they sit compressed by the full well, the zero
  point lies LOW (in the field we watched it lie by −0.9 mag) and the
  check star cannot rat on it because it shares the bias. The panel
  excludes the clipped ones and says so; if the ZP runs short, shorten
  the exposure or pick fainter comps.

**The centring (clicking on the SN)**

* ✅ Keep "aperture follows the seeing" on: the seeing measured from the
  comps is what anchors the centroid template over the galaxy's glow;
  without it the local estimate inflates and wanders.
* ✅ The crosshair detects faint sources on structured backgrounds (a
  robust local detector) and snaps to the source nearest the cursor with
  a short, fixed reach (9 plate px): if it snaps to nothing, there is
  nothing detectable there, and clicking measures exactly where you
  clicked, with a panel note ("no source could be locked"). For a SN at
  the limit that is the honest flow: the point is a limit, not a
  detection.
* ❌ Trusting a centroid without reading the "Pixel" line: the ring is
  drawn at the MEASURED centroid; when it moved more than 1 px from your
  click, the panel says so. On a galaxy, a few pixels of drift is the
  difference between the SN and its host's glow.

**The local sky**

* ✅ Median (default) for flat sky; **Plane** when the galaxy tilts the
  background under the SN (in the field: 16.67 → 16.87, a real
  difference); **host-galaxy subtraction** (PS1 reference scaled by the
  comps) when the SN lives on the core.
* ❌ Annuli squeezed against the SN, or inflated apertures "because the
  growth curve keeps rising": when the curve never flattens by
  4 × FWHM, what keeps rising is not the star (the suggester already
  refuses it and proposes the seeing aperture, saying why).

**The band and the colour**

* ✅ Read the panel's band line: when the sequence cannot derive Johnson
  V, the calibration runs in catalog G and says so; for red stars G and
  V can differ by more than 1 mag.
* ✅ The target's B−V pre-fills itself when the click lands on a
  catalogued star; if the panel says "assumed" and the fitted colour
  slope is large, enter the real B−V by hand (unfiltered/L/OSC chains
  make the colour term a first-order correction; with a V filter it is
  a touch-up).

**The verdict**

* ✅ The **catalog cross-match** line is your first control: a large,
  repeatable Δ is either science (the SN shining) or a blend, and the
  line itself tells you which source sat under the centroid.
* ✅ The check star watches the night's **scatter**; what it cannot see
  (and never will) is a coherent bias across every comp: that is why the
  panel itemises why each sequence star was left out.
* ✅ Repeat the measurement each night: two points catch what one hides.

---

## 4. Time series: the supernova quick-look

With the stacked images of several nights registered in the project,
the quick-look button runs the whole chain:

1. It loads each stack and locates the SN through its WCS (without a
   WCS the verdict is `no_wcs`: solve the astrometry first; the FITS
   editor has the "Solve astrometry…" button for that).
2. It builds the ensemble (section 3.1).
3. It measures the SN in every frame: one point per night with
   `{HJD, Δmag, error}`, where the error is the ensemble's scatter in
   that frame.
4. It summarizes the campaign: **slope** in mag/day (linear fit of the
   main band), **Δmag from peak** and, when the SN type has a template,
   a **verdict** ("normal", "faster", "slower") comparing the last point
   with the template at the same epoch (3-day and 0.3-mag tolerances).

Dates are stored as **HJD** (heliocentric Julian date): the time
corrected to the Sun's position, so month-long curves do not carry the
±8-minute swing of the Earth's orbit. The points are saved into the
project and feed the light curve and the post.

---

## 5. Exporting the measurements

From the project (Follow-up tab) two formats come out:

### 5.1 The working CSV

One row per point: name, HJD, magnitude, error, filter, and the
comparisons in a single cell joined by "+". Header lines carry the
object's name and the note that the dates are HJD. This is the format
for spreadsheets and for reading points back into NightScribe.

### 5.2 AAVSO EFF (Extended File Format)

The AAVSO interchange format (WebObs/FotoDif), line by line:

```
NAME,DATE,MAG,MERR,FILT,TRANS,MTYPE,CNAME,CMAG,KNAME,KMAG,AMASS,GROUP,CHART,NOTES
```

* `DATE` is HJD (`#DATE=HJD` in the header); points without a full HJD
  are skipped: the format has no empty-date concept.
* `TRANS` is honestly written `NA`: NightScribe does not transform your
  measurement to the standard photometric system (that would require
  knowing your equipment's colour and extinction coefficients).
* `CNAME`/`CMAG` and `KNAME`/`KMAG` are filled from the comparison
  sequence saved in the project (Compare tab / chart); `na` when there
  is none.
* `#OBSCODE` comes from your AAVSO code in Settings,
  `#SOFTWARE=NightScribe` and `#OBSTYPE=CCD`.

**What MAG means here**: for quick-look points it is the differential
instrumental magnitude (Δmag against the ensemble), not a
catalog-calibrated magnitude. In the Measure tab's measurement it IS a
catalog-calibrated magnitude via the zero point (TRANS stays `NA`, in
all honesty: there is no colour transformation to the standard system).
Imported points (measured with another tool) keep the magnitude they
arrived with. Always read it with the point's filter and origin in
view.

---

## 6. A worked example, number by number

One star on a typical 16-bit plate:

* the r = 6 px aperture holds 113 pixels;
* aperture sum: 245,000 ADU;
* sky annulus median: 820 ADU/px.

```
net flux  = 245,000 − 820 × 113 = 152,340 ADU
inst mag  = −2.5 × log10(152,340) = −12.957
```

The night's ensemble is 6 stars with instrumental magnitudes
−9.412 · −9.388 · −9.401 · −9.433 · −9.390 · −9.408:

```
ensemble mean = −9.405     scatter = 0.015 mag
Δmag = −12.957 − (−9.405) = −3.552 ± 0.015
```

Reading: the target shines 3.55 mag brighter than the ensemble's average
star, with an internal uncertainty of 0.015 mag. Tomorrow the same
arithmetic will tell whether it rose or faded.

---

## 7. Precision: what to expect and what it depends on

The two error budgets worth not mixing:

### 7.1 The internal error (the one the program reports)

Source and sky shot noise, read noise, and the scatter between
comparisons. With a well-measured star (SNR > 50) and a good ensemble:
**0.01–0.02 mag**. With an 18–19 mag SN against a galactic core:
**0.05–0.15 mag**.

### 7.2 The systematics (the ones the error does not show)

In the usual order of impact:

1. **The unreduced plate**: NightScribe measures, it does not reduce.
   Stacks must arrive already corrected for bias, darks and **flats**;
   an uncorrected flat field introduces 1–5 % errors depending on the
   position on the sensor.
2. **The colour term**: your filter and camera do not respond like the
   standard system. If the target and the comparisons have very
   different B−V colours (a blue SN against solar-type stars), a drift
   of hundredths of a magnitude appears. Rule of thumb: pick comparisons
   of similar colour to the target (B−V is right there in the Compare
   tab), or let the Measure tab fit it with the comps (phase H).
3. **The catalog transformation**: Gaia-derived V adds a ~0.01–0.03 mag
   systematic; APASS's direct V avoids it.
4. **Sky with a gradient**: near a galactic core the background is not
   flat and the annulus median is biased. A smaller aperture and shorter
   exposures help; read the errors carefully.

**Verdict**: with a reduced plate and a good sequence, a realistic total
precision of 0.02–0.05 mag; publishable-in-AAVSO work lives in that
range.

And to go below that? What precision photometry takes (exoplanet
transits included), explained for the observer with a technical
implementation appendix: [docs/PRECISION.md](PRECISION.md).

---

## 8. Good practices (the observer's checklist)

* [ ] Stacks reduced (bias/dark/flat) before measuring.
* [ ] Astrometry solved (no WCS, no target localisation).
* [ ] Neither the target nor the comparisons saturated or squeezed by
      the full well (the guard watches even without a SATURATE card:
      the panel excludes the stars next to the clipping level and says
      so; a ZP built on compressed cores lies LOW and the check star
      cannot see it). Rule of thumb: comps close in brightness to the
      target, never the brightest stars in the field.
* [ ] The same aperture for the whole series (the program fixes it for
      you).
* [ ] A **check** star in the sequence: if it moves, the night is not to
      be trusted; if only the target moves, that is astrophysics.
* [ ] Record the real filter of each session; mixing bands pollutes the
      curve's slope.
* [ ] Repeat the measurement each night: two points per session catch
      problems a single one hides.

---

## 9. The minimal glossary

* **Instrumental magnitude**: the one coming out of the net flux's
  logarithm; only comparable within the same image or matched series.
* **Δmag**: the instrumental-magnitude difference between the target and
  the comparison set.
* **Zero point (ZP)**: the constant that turns instrumental into catalog
  magnitude. The series flow does not use it (Δmag already cancels what
  is common); the FITS editor's Measure tab does compute it from the
  comps (median of `cat − inst`).
* **Ensemble**: the group of constant stars chosen as the reference in a
  series.
* **Check**: the witness star that watches whether the night and the
  sequence behave.
* **HJD**: heliocentric Julian date; time measured from the Sun.
* **B−V**: the colour index (blue minus visual); it describes the
  star's "colour temperature" and drives the colour terms.
* **VSX**: the AAVSO's variable-star catalog; which is why its members
  are never comparisons.
* **EFF**: the AAVSO's Extended File Format, the delivery format for
  photometric measurements.

---

*Implementation details and decisions: `core/series.py`,
`core/compstars.py`, `core/phototrans.py`, `core/photometry_export.py`;
ADR-018 (own FITS/WCS), ADR-042 (photometric sequences), ADR-044
(unified FITS editor).*
