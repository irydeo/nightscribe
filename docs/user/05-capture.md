# 05. Capture

## Driving your observatory: CCDciel or NINA/PINS

NightScribe can hand the capture plan to your observatory software and point
the telescope directly, without exporting files or retyping coordinates. Two
programs are supported, and you pick one under **Tools → Settings →
Integrations**:

- **CCDciel** ([ap-i.net/ccdciel](https://www.ap-i.net/ccdciel/)) over its
  JSON-RPC server (host and port, default 3277).
- **NINA** (Windows) or **PINS** (Linux), its Linux build, over the
  community **Advanced API v2** plugin (host and port, default 1888).

One at a time: the Capture step drives whichever program you chose, and
switching the choice disconnects the other. One condition either way: the
program must be **open** (and, for NINA/PINS, its Advanced API plugin
installed and enabled); NightScribe talks to its API, not to the drivers.

From a project's **Capture** step:

- **Connect CCDciel** / **Connect NINA / PINS** shows the observatory status
  (mount, filter wheel, camera) on the panel.
- **Point telescope** slews to the target's freshly computed position.
- **Astrometric Goto** slews, plate-solves and corrects to the true sky
  position: the reliable route for a preliminary orbit.
- **Stop goto** stops the telescope movement **right now**. It is armed the
  moment you press either pointing button and disarmed when the pointing
  ends: use it if the mount heads somewhere it should not.
- **Send plan** prepares the plan (object, frames × exposure, filter, binning,
  gain, offset, dither) in the software and **reads it back** (including the
  binning and dither it is really holding), so the panel shows what actually
  landed. A rejected optional setting (the binning, a gain out of range, a wheel
  that refuses the slot) is reported **without aborting the plan**: the object,
  the exposure and the frame count always land. If the plan's filter is not in
  your wheel, the filter is left as it is and the read-back says so.
- **Start capture** fires it, and the **same button stops it** while the run is
  in flight ("Stop capture"): it stops the **camera**, not the mount (that is
  Stop goto).
- The filter list of the **Exposure plan** card is the one your wheel really
  has (read from the program on connect); only when nothing is connected does
  the classic L/R/G/B/Ha/OIII/SII list appear.

> **What travels live and what goes in the sequence.** "Send plan" can set, live,
> the object, exposure, frame count, filter, binning, gain, offset and the dither
> count (CCDciel) or a one-shot snapshot (NINA). The **autofocus cadence** is not
> a live setting in either program: it travels with the **exported sequence**
> (CCDciel `.targets`, NINA's native sequence).

> **Why apparent coordinates and not J2000?** Because a mount points at the
> sky of *now*, not the one from the year 2000. Precession, nutation and
> aberration move a star's apparent position by tens of arcseconds: more than
> the field of many cameras. With CCDciel NightScribe does the conversion for
> you so the target lands on the chip, not off it. NINA/PINS take J2000
> directly, so there the plan's coordinates go as they are.

### The last frame, in the window

When you press **Start capture**, a preview of the last frame appears under the
capture row, with its file name, filter, exposure and date, and a button to
**open it in the editor**. It refreshes as new frames land and stops when the
run ends. The image comes over the network from the program itself (CCDciel's
`fullimage.jpg`, NINA/PINS's image stream), so it works with the observatory on
another machine and needs no folder or setting. With NINA/PINS the FITS is
downloaded and opened in the workbench; with CCDciel, which serves only a
picture over the network, the FITS opens when NightScribe can see the file on
disk (same machine or a mounted folder).

### Dither and autofocus, with the reason

Under **Capture options** (a collapsed block in the Capture step) you set
**dithering** (every N frames, how many pixels) and **autofocus** (every so
many minutes or on a temperature change), plus gain, offset, binning and the
delays. The app proposes the values for your object and explains each one when
you hover the ⓘ; you can override any of them. The reasoning is short:

- **Dither** moves the field a few pixels between frames so hot pixels and
  fixed-pattern noise land on different pixels and stacking removes them. A
  moving object (an NEO, a comet) already shifts the field by itself, so it
  gets no dither; a transit or a HADS cannot afford the gap, so it is dithered
  before the run, not during.
- **Autofocus** keeps the stars small as the tube cools and the filter changes:
  a defocused star spreads its light and loses signal-to-noise. In fast
  photometry it runs before the run only.

The values travel with the exported sequence (CCDciel `.targets`, NINA JSON)
and, where the API allows, are applied live; the full autofocus cadence lives
in the sequence file.

### Suggested values, and why

When a project has no plan yet, the **Exposure plan** and **Capture options
and calibration** blocks open with the values the app thinks best for your
object, your camera, your telescope and your sky: frames, exposure, dither,
autofocus, gain, offset, binning. They are only a starting point: change any of
them and they are yours (the app never overwrites a value you touched). The
**Set suggested values** button brings the suggestion back, and the **?** next
to each block opens a dialog that explains, with the numbers it used, why each
value is what it is.

The exposure is the careful one: it comes from the object's brightness, then
**shortens** it for a camera that saturates sooner (a small full well, or big
pixels on a short focal length), respects your camera's limits and the
trail-free cap for a moving object, and checks it against your sky and your
read noise. A sensitive sCMOS that saturates in seconds gets short frames; a
faint object on a dark sky gets longer ones.

The **frame count** is the other careful one: the app fills your object's
visibility window, but never past the moment it crosses the camera's field. A
moving object starts centred (the goto does that), so it has half the short
side of the sensor before it reaches the edge; the run is capped there, because
after that every frame is an image without the object. The crossing comes from
the sensor size, your focal length and the object's apparent rate, and the
per-frame time it is divided by includes the camera's **readout and download**
(its own number, in the camera profile) plus the mount settle: a slow download
means fewer frames. If the field or the rate is unknown, the app says the count
cannot be bounded instead of pretending.

Your **sky brightness** (Settings → Observatory) feeds that check. With a
light-pollution key (Settings → Integrations, from lightpollutionmap.info),
**Look up** fills it from the atlas; without a key, read it off the map (the
button opens it at your site). It is the zenith value and a model, so treat it
as a good starting point, not a promise.

### Start and follow: N observations without re-pointing by hand

A fast object leaves the camera's field: capture it as-is and half the run ends
up without it. **Start and follow…** (in the Capture step, for a moving object
and connected) asks for a **number of observations** and drives the whole run:
each observation captures as many frames as fit before the object reaches the
edge of the field (the same crossing the frame count is bounded by), then the
telescope points again at the object's **fresh position** and the next
observation starts. The app follows the object across the sky, one observation
at a time, and you get the most out of each one without touching the mount by
hand.

Before it starts it shows the numbers: observations, frames per observation,
exposure, the re-point cost and the total, and whether the whole thing fits
your object's visibility window. It runs **your** numbers from the Plan step
(the **Frames** and **Exposure** boxes), not a fresh suggestion; if your frame
count is more than fit before the object reaches the edge of the field, it says
so and honours it anyway. While it runs the button becomes **Stop following**,
and the panel says which observation it is on. The commercial software uses the
word *recenter* for each step (CCDciel) and *Center After Drift* (NINA); the
difference is that here each step points at the object's **updated ephemeris**,
not fixed coordinates, because the object really moves.

Two things to know: it needs a **plate solver** (the centering is an astrometric
goto), and with **NINA/PINS** each observation is **one frame** (its snapshot
capture takes one) unless you load the native sequence; with CCDciel the frame
count is honoured. Each re-point opens a new batch, so the FITS editor can
treat them as separate observations.

### What NINA / PINS does not do (yet)

- Its snapshot capture takes **one exposure**, so **Start capture fires one
  frame**, not the plan's whole count: the panel says the frame count is
  information only. CCDciel does honour the count.
- NINA has **no persistent staging**: **Send plan** sets the wheel filter and
  NightScribe remembers the rest, instead of a state you can read back inside
  NINA.
- The astrometric goto needs a **plate solver configured in NINA**; without
  it, the pointing fails and the error is shown as-is.
- **PINS uses the same plugin and settings as NINA**; only host and port
  change.

## Calibration: bias, darks and flats

The **Calibration** tab of the FITS editor manages a **master library** and
each visit's recipe.

The library is indexed, not copied: you point at your master FITS and the
app reads from their headers what makes them valid (camera, gain,
temperature, exposure, filter). When indexing you declare what each file
*is*:

- **Bias**: the electronic read offset (zero exposure).
- **Dark**: thermal current, at the same exposure as the lights. *A dark
  already includes the bias*, so with a dark you do not need a separate
  bias.
- **Flat dark**: at the flats' exposure.
- **Flat**: per filter, normalised.

> **Why calibrate?** Because your sensor lies in three known, repeatable
> ways: it adds an electronic pedestal to every pixel (bias), it accumulates
> thermal charge over time (dark) and it multiplies the light by the shadow
> of dust and vignetting (flat). Subtracting bias+dark and dividing by the
> flat is not cosmetics: it is what turns ADU into photons that are
> comparable from one corner of the chip to the other and from one night to
> the next. Without it, the photometry of chapter 06 measures the dust in
> your optical train, not the star.

> **Why is the flat per filter?** Because dust shadows change scale with the
> optics and the wheel, and the sensor's response changes with colour. A V
> flat does not correct an R frame: the same speck's shadow lands elsewhere
> if the wheel parks differently.

**The visit's recipe**: when you open the editor from a visit, the app
resolves which library master each piece uses, reading the first frame's
header, and warns about anything missing (Warnings). **Calibrate the visit**
applies the recipe to every frame; calibration works in memory and only
writes FITS copies if you tick the export box.

**If you have no flat for a filter**: the *Build a flat from the frames*
option builds a pseudo-flat by stacking the lights themselves (dust and
vignetting stay fixed on the frame; stars move between frames and vanish in
the low percentile). Use it for what it is: an honest patch that never
overrides a real flat. You can open it with **See the flat** and judge it: a
flat with a star in it is not a flat.

> **Why does the pseudo-flat work?** Because in a series with *dithering*
> (small offsets between frames) the only thing that does not move is what
> belongs to the instrument: dust, vignetting, hot pixels. A low percentile
> over many frames keeps what is fixed and rejects what moved. If your field
> is static (no dithering), the app masks the stars before stacking, for the
> same reason.

Next: [06. Photometry](06-photometry.md).
