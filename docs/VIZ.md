# NightScribe — Visual Style Guide (viz/)

*[Versión en español](VIZ.es.md)*

One renderer, two outputs: everything under `nightscribe/viz/` draws on a matplotlib
canvas embedded in the GUI **and** exports PNG files ready to attach to posts.
Style is defined once in `viz/style.py`.

## Style

- Dark space background (#0b0d17 family), consistent accent palette, clear sans-serif
  type, subtle grid, optional watermark "NightScribe · <observatory name>".
- Export formats: 1080×1080 px (Instagram square), 1200×630 px (Facebook/X card).
  DPI fixed so text stays legible on phones.
- Tests render with the `Agg` backend (no display needed).

## Views

### `orbit_view.py` — top-down ecliptic chart

- Orbits of Mercury→Mars (→Jupiter for Trojans / long-period comets), planets at their
  **current** positions (Schlyter), the object's orbit highlighted, its current
  position and a ±N-day track.
- Close-approach inset: zoom centred on Earth with the **Moon's orbit** drawn and the
  flyby labelled in lunar distances — "to put it in perspective".
- Comets: anti-sunward tail marker in the zoom inset.

### `sky_view.py` — night altitude curve

Altitude vs. time for the target across the night, twilight phases shaded, Moon
altitude overlaid. Exoplanet transits draw ingress/egress windows
(`transit_view.py` adds a simple theoretical light curve for posts).

### SkyChart — interactive visibility chart (ADR-029)

Vector widget in `gui/widgets/sky_widget.py` (no matplotlib): the same altitude
curve as `sky_view.py`, plus the dark window, the safe band (ADR-020), best time,
local horizon, the Moon and the transit. **Legend** in the bottom-right of the data
area identifying each line (target, Moon, horizon limit) with the same style and
colour, over a translucent backdrop; labels go through `self.tr()` and are translated
ES/EN. The curve is clamped to 0° at draw time (nothing below the Y axis), but the
tooltip still reports the real altitude.

Every chart widget also carries a **watermark** ("NightScribe", configurable with
`set_watermark()`) in the bottom-right corner, painted in viewport space (stays
anchored while zooming/panning) and also stamped on exported PNGs —
`gui/widgets/base_chart.py`.

### `sun_panel.py` — Sun today

Latest SDO image (channel selectable) + our own active-region map plotted from NOAA
coordinates (our "Raben" without copyright issues).

### `sn_view.py` — supernova field

Reference cutout (DESI Legacy Survey / DSS via hips2fits) with a crosshair at the SN
position; side-by-side or animated blink GIF when the user provides the observatory
image.

### `blink_view.py` — supernova blink (ADR-018)

Aligned pair (user FITS + PanSTARRS DR1 g cutout matched in centre/scale/rotation via
hips2fits) rendered for blinking: percentile-stretched frames with the SN marked at
its catalogued position, exported as animated GIF (blink and fade modes) and as a
side-by-side PNG for posts. Captions are single-language (UI language) and name the
configured observatory; exports can be zoomed around the SN (`crop_zoom`), the marker
size is adjustable, the survey background can be equalized with `auto_gain` (median
matching), and the blink dwell is configurable. The same stretch and zoom feed the
live GUI blink tab.

### ApproachChart — animated geocentric view (ADR-029)

Interactive vector chart in `gui/widgets/approach_widget.py` (no matplotlib).
Shows the object approaching **from Earth's perspective**, using the **Moon as a
fixed 1 LD scale reference** (real position at the reference date, not animated).

- Earth at the origin (`ACCENT2` dot), moving object point (`ACCENT`).
- 1 LD reference circle (`MUTED`); Moon at its real ecliptic position on it.
- Dashed geocentric track (`ACCENT`) over a ±30-day window centred on the CA
  (or the given date when `e ≥ 1`).
- CA diamond + `CA X.XX LD` label (closed orbits only).
- Status: `<date> · X.XX LD <trend> · CA X.XX LD (<CA date>)` or
  `<date> · X.XX LD <trend> · no return (open orbit)`.
- Play/Pause + scrub slider + hover over the track (`R = X.XX LD`).
- PNG export via `ChartView.export_png` (renders what is visible, zoom included).
- **Framing** (the whole ±30-day sweep): the frame half-extent fits the approach
  arc — `span = min(1.9 · max(CA, current distance, arc maximum), CA / _PASS_SCENE_MIN)`,
  floor `_MIN_SPAN_LD` — so the asteroid is **on canvas from the moment the
  chart loads** at any pass distance, without a zoom ceiling. On very close
  flybys the guard `CA / _PASS_SCENE_MIN` (0.30) stops the pass from sinking
  into the Earth corner; on open orbits (e ≥ 1) the arc / current point fit the
  frame the same way.
- **Earth–Moon bundle**: always drawn and always legible. The pair lives in the
  corner **farthest from the encounter**; the 1 LD reference circle is drawn
  with its **true centre at Earth**, clamped to a legible radius band
  `[_BUNDLE_RADIUS_MIN, _BUNDLE_RADIUS_MAX]` scene units (the Moon keeps its
  true ecliptic direction, so out-of-band distances are *diagrammatic* — the
  separation reads in the status line, not from the drawing). Inside-the-Moon-
  orbit flybys no longer crop it. Outer track that would escape the frame is
  clipped at the frame edge.
- **CA marker** (closed orbits): with the sweep always in frame the closest
  approach is *always* the classic diamond + `CA X.XX LD` label (no edge pin).
- **Labels never step on objects**: each label probe avoids the track, other
  labels, the solid markers (Earth, Moon, CA — halo radius + `_OBST_PAD`)
  and the frame edge, so no label ever covers a body.
- **Earth/Moon labels auto-separate**: the Earth label is given the side
  *opposite* the Moon and the Moon label the side behind its own body (both
  derived from the Moon's scene direction), and when the two markers sit
  close together the labels walk out a **radius ladder** (`_PROBE_RADII`) into
  the empty space instead of butting against each other by the origin.
- Orbital math in `core/approach_math.py` (pure, no matplotlib).
- Does not replace the static inset in `viz/orbit_view.py` (social PNGs are
  unchanged); it is the live GUI equivalent.

**Visual polish:**

- Separation halos (a thin ring in the body's own colour, `NoBrush`, cosmetic
  pen) around Earth, the Moon, the object point and the CA diamond — the
  bodies always read as distinct, even when their distances coincide.
- Labels (Moon / Earth / CA) carry **no background box**: each text
  is echoed underneath as a thin 2 px BG-colour contour (`QPainterPathStroker`),
  which keeps the glyphs readable over the dashed track and the circle while
  the canvas stays light.
- **Collision-avoidant placement**: each label probes 8 directions around its
  anchor (starting from the most natural one) and takes the first whose rect
  neither crosses the track, another label nor a solid marker (and stays
  inside the frame); if none is safe it falls back to the preferred one.
  Labels are fixed in the frame (they do not follow the scrubber).
- Geocentric track dashed at 1.5 px `[8, 5]` (thin on purpose — the moving
  point reads over its own line at any zoom); the 1 LD reference circle dotted
  at 1.5 px `[2, 4]` (both cosmetic pens: they do not thicken on zoom).

## Rules

- No third-party copyrighted images in exports: only public-domain (SDO) or
  public-service (Legacy Survey / CDS) material with credit, or our own renders.
- Every viz function takes the data dict and returns/exports a figure; no network
  inside `viz/`.
