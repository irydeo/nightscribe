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
* **Tabs**: one per feature. Phases D, E and F of the plan fill them
  with Annotate, Blink and Compare; adding a new feature is adding a
  tab.
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
