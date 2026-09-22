# Unified FITS Editor (UFE)

*[Versión en español](UFE.es.md)*

The **Unified FITS Editor** is NightScribe's single place to view and
work FITS images (ADR-044). Open it from **Tools → FITS editor…**; it
coexists with the classic dialogs (blink, comparison chart, annotated
FITS), which stay where they always were.

## The window

```
| Load · Invert · Export PNG · Fit 50 100 200 400 · %                |
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
  plate carries a WCS.
* **Tabs**: one per feature. **Blink** and **Annotate** are already
  available (below); Compare arrives in the plan's phase F. Only the
  visible tab answers clicks on the image.

## Blink

The **Blink** tab blinks your plate against the PanSTARRS DR1 g
reference (supernovae and transients; the plate is the one you loaded
with "Load FITS…"):

* Type the SN name (or tick "Manual coordinates" and give RA/Dec) and
  press **Prepare pair**: it resolves the target, downloads the
  reference in your plate's geometry and starts the live blink.
* The **stretch is the common one** (the histogram strip drives the
  blink too); **Balance** multiplies the reference to match the sky
  background (Auto button); **Nudge ref** shifts the reference by
  sub-pixel steps when the registration is not perfect.
* **Blink** (alternates at the chosen interval) or **Fade** (static
  blend with the slider); the amber marker sits at the SN position
  mapped through your plate's WCS.
* **GIF… / MP4… / PNG…** export the pair (side by side for PNG), with
  the crop zoom on the SN of your choice.
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
