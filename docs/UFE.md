# Unified FITS Editor (UFE)

*[Versión en español](UFE.es.md)*

The **Unified FITS Editor** is NightScribe's single place to view and
work FITS images (ADR-044). In the interface it is called the
**«NightScribe Image Workbench»** (it is the processing workspace by
now, not just an editor) and opens from **Tools → NightScribe Image
Workbench…**; "UFE" stays as the internal codename in code and docs.

**Coexistence and the default setting**: the classic dialogs (blink,
comparison chart, annotated FITS) still exist for comparison and review,
but by default the flows open the UFE: under **Settings → Development**
you can switch the classic ones back as the default (`ufe_default`).
Opened from a project, the UFE comes with the plate loaded, the right
tab on stage and **everything the project knows about the object already
in place**: name, coordinates and magnitude on the line under the top
bar and in the title, and every tab pre-filled (Blink: name and
coordinates; Photometry: target, magnitude and B−V when the record
carries it; Annotate: label, the marker on the object's position and
the extra visits). What it writes (annotated copies, blink GIF/PNG,
sequence CSV/PNG) registers into the project just like the classics did.
With no plate of your own, the Photometry tab (Sequence mode) downloads
the survey field (DSS2/PS1) as a FITS with WCS and works on it directly.

## The window

```
| [Open][Export][Solve] | [Fit][100 %][Zoom ▾] 100 % | [View ▾] | Image|Curve |
|───────────────────┬────────────────────────────────────────┬──────────────|
|  visit / series   |                                        |  tab         |
|  (foldable)       |   IMAGE  (or the curve)                |  ────────    |
|                   |   · the object, over the plate          |  primary     |
|                   |                                        |  [Settings▸] |
|───────────────────┴────────────────────────────────────────┴──────────────|
| Histogram ▸  (folded: 24 px; open: ~110 px, two rows of controls)         |
|──────────────────────────────────────────────────────────────────────────|
| ⓘ status: one line, fixed height, never grows                            |
```

The chrome takes what it NEEDS and the work area gets everything else: the
plate is what the window is for. The top bar is stable (it measured 25 px
in a short window and 69 px in a tall one before: the layout's stretch was
never applied by the loader), and the histogram strip is compact and folds
with its state remembered. The object's name, position and magnitude are
painted OVER the plate (and into the exported PNG), not in a row of their
own.

The series block in the left panel keeps what an observer touches while
measuring (the frame navigator, the grouping of frames, **Measure the
sequence**, live mode and the progress) and puts the rest behind two
doors: **Chart and quality…** opens the chart's own non-modal window
(scale, error bars, binning, mean curve, outliers and exclusions) and
**Series ▾** holds the occasional actions (undo, ExoClock, the night's
figures, save the chart, period and phase, the guide). Before this the
same panel showed some thirty controls stacked in a column.

* **Image**: takes up most of the window. The wheel zooms anchored at
  the cursor; dragging pans; double-click returns to the fit. Hovering
  shows a tooltip with the pixel, its DN value and the RA/Dec when the
  plate carries a WCS. In the marking tabs (Photometry, Annotate)
  the cursor becomes a crosshair with a centre-gap reticle that **snaps
  to the source's centroid** under the mouse: the click is born
  centred. The detection is local and robust (it sees faint sources even
  on a galaxy's glow) and the snap's reach is capped at 9 plate px: the
  reticle never jumps to a bright star far away.
* **Tabs**: one per feature. **Blink**, **Photometry** and
  **Annotate** are available (below). Only the visible tab answers
  clicks on the image.

## Blink

The **Blink** tab blinks your plate against the PanSTARRS DR1 g
reference (supernovae and transients; the plate is the one you loaded
with "Load FITS…"):

* Type the SN name (or tick "Manual coordinates" and give RA/Dec) and
  press **Prepare pair**: it resolves the target, downloads the
  reference in your plate's geometry and starts the live blink.
* The **stretch is the common one** (the histogram strip drives the
  blink too); **Balance** multiplies the reference to match the sky
  background (Auto button); **Fine alignment** is the cross of arrows
  that walks the reference in half-pixel steps when the registration
  is not perfect, just like the legacy blink dialog.
* **Blink** (alternates at the chosen interval) or **Fade** (static
  blend with the slider); the amber marker sits at the SN position
  mapped through your plate's WCS.
* **GIF… / MP4… / PNG…** export the pair (side by side for PNG), with
  the crop zoom on the SN of your choice.

## Photometry

The **Photometry** tab does both jobs in the same place, in two stacked
halves (there is a draggable divider between them): the **Sequence**
radio on top picks which half receives the clicks, and the other stays
in sight with its rings and labels, so you can switch between building
and measuring without losing track of what is on the plate (ADR-044,
layout revision, 2026-09-24).

### Sequence (top half)

Builds the photometric sequence on your plate (a WCS is needed; if it
is missing, the configured solver gets you one, ASTAP or nova):

With the visit open, the left panel also carries the **frame navigator**
(previous/next, `frame i/N`, "first frame": the open frame is the reference)
and, in transit projects, the **EXOTIC** reduction buttons. The project's
saved sequence loads by itself when the visit opens.

The **top bar** carries the two astrometries together, side by side: **Solve
astrometry...** (this plate) and **Solve the visit...** (every frame of the
visit in one go). The pair explains itself: the first solves the plate in
front of you, the second the whole night's field.

**Solve the visit...** is preparation, not measurement: it
solves every frame of the visit in one go, and what needs it are the visit's
**products** (the astrometry report and the EXOTIC reduction of a transit),
not the series, which measures on the reference plate and registers the rest.
With no frames in the visit the button is not shown at all (there is nothing
to solve). A visit is
one field, and the project knows where it is, so each frame takes a moment
instead of a minute of blind search: frames that already carry a WCS are
skipped, and each solution is written into its own FITS (it needs "Save the
solved WCS in the FITS" in Settings; with it off the button explains instead
of leaving solutions that would die with the session). If the project has no
coordinates, the first frame is solved blind and the rest follow its field.
One frame that fails does not stop the batch: it is counted and named in the
status line. A plate opened from a project is also solved with its field, so
the Solve button of the top bar answers in a moment.

**Build the sequence...** does the whole pipeline in one click: if the plate
has no WCS it solves it first (the project's field points the solver, so it
is a moment), then it queries the catalogue (the field) and proposes. The
manual window's **Propose sequence** fills in the missing step the same way,
so the order of the buttons is never something to remember. A rebuild that
cannot deliver (the query fails, nothing lands on this plate, no usable
comparison star) keeps the sequence you already had and says why.

* **Target** and **Target mag** pre-fill what the project knows; the
  approximate magnitude guides the proposal.
* **Generate field** queries the catalog (Gaia EDR3 or APASS DR9) and
  the VSX variables around the plate centre: the brightest stars come
  out labelled ("show catalog magnitudes" checkbox) and the known
  variables with a red ring (they can never be comparisons). **DSS2...**
  on the same row downloads the survey field (PS1-g, fallback
  DSS2-red) as a FITS with WCS when you have no plate: you work on it
  directly.
* **Click** a star to add or remove it from the sequence, as Comparison
  (cyan) or Check (pink, "on click, add as" radio).
* **Propose sequence** automatically picks isolated, non-variable stars
  matched to the target's brightness.
* **Sequence (N)...** opens the *table* in a small non-modal window (N
  is the current number of stars, and it updates itself): you can
  rename, retype, **edit the band and the magnitude by hand** (a doubtful
  catalog value is fixed there: the measurement uses the manual value) and
  remove rows, and leave it open while you keep
  picking stars on the plate. Hovering tells you each star's catalog,
  magnitude and colour, with the window open too.
* **Remove all** empties the sequence and **Export CSV...** writes it
  (fixed columns plus every band); the **chart PNG** goes through the
  shared "Export PNG..." button in the top bar: plate, rings, labels
  and the north arrow / scale bar, exactly what you see.

### Measure (bottom half)

Turns one click into a catalog-calibrated magnitude (single-plate
differential aperture photometry):

* It needs the plate with a WCS (if missing, it solves it by itself) and
  a sequence in the top half (if there is none, a "Go to the sequence"
  button takes you there).
* **Click** on the star or the SN: sub-pixel centroid, aperture and sky
  annulus visible on the image, and the panel tells the full story:
  instrumental magnitude, the zero point with its error and how many
  comps were used (and why any was refused), and the **calibrated
  magnitude +/- error**. The sequence stays in sight (rings and
  labels): you measure WITH it; and changing any option (band, radii,
  sky, sigma-clip, colour term, B-V, subtraction) re-measures at once.
* The daily flow is **Band** (default V) and the three **aperture
  radii** (aperture, inner and outer annulus): touching a radius
  re-measures the point at once, and your hand edit wins over the
  seeing auto-scale until you load another plate (or re-arm the
  checkbox).
* **Centre**: the arrows ↑ ← → ↓ move the measurement centre in 0.5 px
  steps (like the blink's alignment) and the centroid refines again
  around it; the **0** button returns to the clicked centre. A new click
  starts at (0,0). It helps when the centroid locks onto a neighbour.
* **Advanced...** opens the full recipe in another small non-modal
  window (you can leave it open while measuring): the **sky** model
  (flat median or a tilted plane for galactic cores), **sigma-clip** of
  the sky (two 2.5-sigma passes), the **seeing-following aperture**
  (FWHM of the comps on your plate, aperture at 1.35 times), the
  **colour term** fitted with the comps' and the target's B-V,
  **host-galaxy subtraction** with the aligned PS1 reference (for SNe
  on cores, one download per field), and the **Suggest** button that
  proposes the radii with the target's growth curve and its
  neighbourhood, with the reasons in plain words.
* Quality controls (phase H, in the background): the **real
  saturation** ceiling (SATURATE or `ccd_saturate`), **internal vs.
  total error** (photons + scatter + scintillation + colour + flats)
  and the **check star as the measurement's traffic light**. When the
  header lacks the gain, the panel warns that the error is the comps'
  scatter only.
* **CSV...** exports the measurement as one row, **AAVSO EFF...** in
  the AAVSO's format (sequence in CNAME/CMAG/KNAME/KMAG) and, when the
  editor opened from a project, **Save…** records it in
  the light curve (source "measure", visit attached). When the sequence
  lacks the target's magnitude, it is looked up in the project
  (planner, VSX, or the last saved sequence); and exporting the
  sequence writes it into the project for next time. The plate on disk
  is never modified.

Both halves share: the **annotations on load** (if the plate already
carries ANNOTATE cards, written by NightScribe or AstroImageJ, they are
drawn on load with their plate-pixel sizes and labels readable at any
zoom), the **north arrow and scale bar** (the "N" and "Scale" buttons
in the top bar, with a WCS) and **Solve astrometry...** (blind-solves
with the configured solver, ASTAP or Astrometry.net; a progress dialog with
a Cancel that stops the solver; the solution lands in memory and is stored
into the FITS itself, atomically, so the plate stays solved for any other
program).

To understand how photometry is then measured with these sequences:
[docs/PHOTOMETRY.md](PHOTOMETRY.md).

## A visit's curve: one night, one pass

The series block measures **one visit** (one night) by default. When the
project has more than one visit with frames, the **"this visit" / "all
visits"** selector appears next to the frame counter: with "all visits" the
engine measures the frames of **every visit** in one pass, each night is filed
in its visit (one run per night) and the chart shows the project's curve, the
union of the nights. Live mode and "discard the curve" are per visit: with
"all visits" they step aside and say why.


When the editor is opened from a visit, the chart in the centre draws **the
curve the visit already has**, read from the project: nothing is measured
again.

A visit can hold **several passes** (you measured the series again with another
band, with another sequence, or to check something). Every one keeps its points,
but **the chart draws only one**, the one the visit has marked. Measuring again
makes the new pass the curve; the earlier ones are not drawn, and the panel says
so: how many points the one you see has and how many more passes the visit
holds. The door **Series ▾ → Passes of this visit…** lists them all (time, band,
points, stretch of night, state) and lets any of them **be the curve** without
deleting anything, or **undo** a pass (its points go, its row stays marked, and
the chart falls back to the pass before it).

The band in the legend and in the AAVSO file is **the band it was calibrated
with** (the one the engine used on the comparisons), not an invented "V" when
the frames' header carries no `FILTER`. And the **detrended** curve is refitted
on load (it is deterministic: the same points with the same airmass give the
same coefficients), so the detrended switch has something to show after
reopening the visit too.

## The plate's band and the marker style (ADR-046)

The plate says what it knows in the **band at the top of the image**, on
screen and burned into the exported PNG, in two lines:

* **Line 1, who it is**: the object, the target's sexagesimal RA/Dec and
  its brightness.
* **Line 2, the context**: UT date, exposure, filter, the kit that took
  the frame (from its own header), the MPC station, the plate scale in
  ″/px and the FOV of what is shown (the last two only when the plate is
  solved).

**The colour of each datum says how much to trust it**, and that is the
point of the band:

* the **position** in ink when this plate's own solution places it, and
  dimmed with a `cat` when it is only the catalogue's (an unsolved plate);
* the **magnitude** in a scale of its own: **green** when the measurement
  is clean (error up to 0.05, comparisons and check star in order),
  **orange** when it is usable but not clean (up to 0.15, or a light
  caveat: only three comparisons, a magnitude derived from a colour, no
  check star in the sequence, a flag on the point), **red** when it is not
  worth reporting without looking (error above 0.15, too few comparisons, a
  check star that fails, a clipped core), and **white** with a `cat` when it
  is only the project's or the catalogue's value, which is not a measurement
  of this plate. The magnitude shown is the one measured on THAT frame (the
  visit's curve when there is one), then a single-plate measurement, and
  only then the catalogue;
* everything else (date, exposure, filter, kit, station, scale, FOV) in
  the quiet colour: it is context, not a judgement.

The same code is on the **curve's points** (the chart's **Quality colours**
button, on by default) and on the measurement's **panel**: green clean, orange
usable but not clean, red doubtful, white for a catalogue value. See
[the series guide](SEQUENCES.md) for the thresholds and what each figure needs.

The band never cuts a word: when the window is narrow it drops whole
fields (the FOV first, the date last) and, in the extreme, the context
line goes and only the plate's name is left. The top bar's **"Data"**
button turns it off (Settings → Site & equipment → "Plate band" sets the
default), and the compass and the scale bar keep their classic corners.
The **blink GIF/MP4** and the **sequence chart** keep their own metadata
boxes, with their own switch ("Other charts" in the same Settings group).

In the same Settings group, **Object marker** picks the look of the
object's mark: ring with ticks (classic) or full-frame cross with a box
(applied in Photometry, Annotate, Blink and the sequence chart).

## Annotate

The **Annotate** tab saves AstroImageJ-compatible annotated FITS copies
(the original file is never modified):

* **Click** on the image drops the marker; **dx/dy + Nudge** move it by
  tenths of a pixel; size and colour are yours.
* **Label** and **notes** travel in the ANNOTATE and NS_NOTES cards;
  RA/Dec, plate scale and north PA are written from the plate's WCS
  (NS_RA, NS_DEC, NS_SCALE, NS_NORTH).
* **Also annotate (visits)**: a list of extra plates receives the same
  annotation; the marker lands on each through its own WCS.
* **Save annotated copy…** writes the chosen copy plus, next to every
  visit, its `<name>_annotated.fits`.
* **Histogram**: 256 log-scaled bins computed on the display frame. The
  shaded zones are what the stretch throws away.

## Fine stretching

Built for subtle targets (supernovae against galactic cores):

* **Handles**: blue (black) and orange (white) draggable lines on the
  histogram, AstroImageJ style; a plain click moves the nearest one.
* **Black / White** in absolute DN with a fine step adapted to the
  plate's range; they never cross (white always stays above black).
* **Gamma**: below 1 lifts the mid-tones; above 1 sinks them.
* **Auto**: back to the 1 / 99.5 percentiles.
* **Invert**: swaps black for white; faint objects pop against the sky.
* **Keep stretch on load**: the next plate keeps your black, white,
  gamma and invert values instead of the auto percentiles. This is what
  you want when reviewing a same-camera series of frames.

## Zoom

The **Fit / 50 / 100 / 200 / 400** presets set the absolute scale: 100
is one plate pixel per screen pixel, and at 200/400 you inspect real,
uninterpolated pixels. The zoom survives window resizes, and the view
pans 25 % past the plate edge.

## Keyboard

| Key | Action |
|---|---|
| `F` | Fit the plate to the window |
| `1` | Zoom 100 % (1:1) |
| `+` / `-` | Zoom in wheel steps |
| Arrows | Pan a quarter of the window |
| `Ctrl+O` | Load FITS… |
| `Ctrl+E` | Export PNG… |

## Exporting

**Export PNG…** saves exactly what is on screen (with the NightScribe
watermark), ready to attach. Data exports (annotated FITS, charts)
always use the original file, never the screen pixmap.

## When something does not work

The window has **one** status line at the bottom, with the whole text in its
tooltip (the result of a measurement stays in its own box, next to the action
that produced it). A build that cannot deliver keeps your sequence and says
why; a solve that fails says what it was doing.

And the application **writes what it does to a file** while it runs:
**Help > Open the log**. A GUI launched from a menu has no console at all, so
a report like "a dialog appears and disappears and I do not know what happens"
has its answer in there.
