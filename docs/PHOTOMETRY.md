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

The target position comes from the plate's WCS (its astrometric
solution): RA/Dec converts to a pixel. Because that position falls
between pixels, it is refined with a **centroid**: the centre of mass of
the light in an 11×11 pixel box around the initial position. The result
has a fraction-of-a-pixel precision, which is what photometry needs so
the aperture always lands centred.

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

**Formula 3: the differential magnitude**

```
Δmag = instrumental mag(target) − mean(ensemble instrumental mags)
```

If the SN sits 2 mag below the ensemble mean today and 1.5 mag tomorrow,
it has faded by 0.5 mag: the absolute zero does not matter, the
**evolution** is the signal.

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
catalog-calibrated magnitude. Imported points (measured with another
tool) keep the magnitude they arrived with. Always read it with the
point's filter and origin in view.

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
   tab).
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
* [ ] Neither the target nor the comparisons saturated (the 85 % guard
      watches; the FITS editor's histogram shows it).
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
* **Zero point (ZP)**: the constant that would turn instrumental into
  catalog magnitude; the current series flow does not use it, because
  Δmag already cancels what is common.
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
