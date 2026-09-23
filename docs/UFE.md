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
coordinates; Compare: target and mag; Annotate: label, the marker on
the object's position and the extra visits; Measure: B−V when the
record carries it). What it writes (annotated copies, blink GIF/PNG,
sequence CSV/PNG) registers into the project just like the classics did.
With no plate of your own, the Compare tab downloads the survey field
(DSS2/PS1) as a FITS with WCS and works on it directly.

## The window

```
| Load · Export PNG · Fit 50 100 200 400 · %                         |
|────────────────────────────────────────────|──────────────────────|
|                                            | [Blink][Compare]     |
|              IMAGE                         | [Annotate]           |
|                                            | (one tab per         |
|                                            |  feature)            |
|────────────────────────────────────────────|──────────────────────|
| Histogram with handles + Black/White/Gamma + Auto + Invert          |
```

* **Image**: takes up most of the window. The wheel zooms anchored at
  the cursor; dragging pans; double-click returns to the fit. Hovering
  shows a tooltip with the pixel, its DN value and the RA/Dec when the
  plate carries a WCS. In the marking tabs (Measure, Annotate, Compare)
  the cursor becomes a crosshair with a centre-gap reticle that **snaps
  to the source's centroid** under the mouse: the click is born
  centred.
* **Tabs**: one per feature. **Blink**, **Compare**, **Measure** and
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

## Compare

The **Compare** tab builds the photometric sequence on your plate (a
WCS is needed; if it is missing, "Solve astrometry…" gets you one):

* **Generate field** queries the catalog (Gaia EDR3 or APASS DR9) and
  the VSX variables around the plate centre: the brightest stars come
  out labelled and the known variables with a red ring (they can never
  be comparisons).
* **Click** a star to add or remove it from the sequence, as Comparison
  (cyan) or Check (pink); **Propose sequence** automatically picks
  isolated, non-variable stars matched to the target's brightness (give
  it the approximate magnitude).
* The **table** renames, retypes and removes rows; hovering tells you
  each star's catalog, magnitude and colour.
* **Export CSV…** writes the sequence (fixed columns plus every band).
  The **chart PNG** goes through the shared "Export PNG…" button in the
  top bar: plate, rings, labels and the north arrow / scale bar,
  exactly what you see.

To understand how photometry is then measured with these sequences:
[docs/PHOTOMETRY.md](PHOTOMETRY.md).

## Measure

The **Measure** tab turns one click into a catalog-calibrated magnitude
(single-plate differential aperture photometry):

* It needs the plate with a WCS (if missing, "Solve astrometry…" gets
  one) and a sequence in the Compare tab (if there is none, the tab
  guides you and has a button that takes you there).
* **Click** on the star or the SN: sub-pixel centroid, aperture and sky
  annulus visible on the image, and the panel tells the full story:
  instrumental magnitude, the zero point with its error and how many
  comps were used (and why any was refused), and the **calibrated
  magnitude ± error**. Coming from Compare, the sequence stays visible
  (rings and labels): you measure WITH it in sight; and changing any
  option (sky, sigma-clip, colour term, target B−V, radii) re-measures
  at once.
* The default band is V; apertures and the sky sigma-clip are
  adjustable. When the header lacks the gain, the panel warns that the
  error is the comps' scatter only.
* The apertures measure live: touching a radius re-measures the point at
  once, and your hand edit wins over the seeing auto-scale until you
  load another plate (or re-arm the checkbox). When the sequence lacks
  the target's magnitude, it is looked up in the project (planner, VSX,
  or the last saved sequence); exporting the sequence writes it into the
  project for next time.
* Quality controls (phase H): sky by median or by a fitted **plane** on
  galactic cores, **seeing-following aperture** (FWHM measured on the
  plate), the **colour term** fitted with the comps' and the target's
  B−V, the **real saturation** ceiling (SATURATE or `ccd_saturate`),
  **internal vs. total error** (photons + scatter + scintillation +
  colour + flats), the **check star as the measurement's traffic
  light**, and **host-galaxy subtraction** with the blink's PS1
  reference for SNe on cores.
* **CSV…** exports the measurement as one row and **AAVSO EFF…** in the
  AAVSO's format, with the sequence in CNAME/CMAG/KNAME/KMAG. The plate
  on disk is never modified.
* **Annotations on load**: if the plate already carries ANNOTATE cards
  (written by NightScribe or AstroImageJ), they are drawn on load:
  circles with their plate-pixel sizes and labels readable at any zoom.
* **North arrow and scale bar** (the "N" and "Scale" buttons, with a
  WCS): top-right and bottom-left corners, and they are stamped into the
  exported PNG too.
* **Solve astrometry…**: when the plate has no WCS (or you want a fresh
  one), blind-solves it with Astrometry.net (your API key from Settings
  required). The solution applies in memory for the session: the file on
  disk is never modified, and the probe, the north arrow, the scale bar
  and Annotate pick it up at once.

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
