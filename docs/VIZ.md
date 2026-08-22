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

### `families_view.py` — "where it lives"

Radial bands of the solar system families (NEOs, main belt, Trojans, Centaurs, TNOs)
with a **"you are here"** marker for the object.

### `sky_view.py` — night altitude curve

Altitude vs. time for the target across the night, twilight phases shaded, Moon
altitude overlaid. Exoplanet transits draw ingress/egress windows
(`transit_view.py` adds a simple theoretical light curve for posts).

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

## Rules

- No third-party copyrighted images in exports: only public-domain (SDO) or
  public-service (Legacy Survey / CDS) material with credit, or our own renders.
- Every viz function takes the data dict and returns/exports a figure; no network
  inside `viz/`.
