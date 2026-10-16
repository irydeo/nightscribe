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

From a project's **Capture** step the **Observatory** console drives it. Its
status sits on top (who answers, the mount's state, the temperature, the
version) with the red **STOP** always at hand, and its commands are three verbs
and two checkboxes:

- **Connect CCDciel** / **Connect NINA / PINS** is the only way in, and it shows
  the observatory status (mount, filter wheel, camera) on the panel. The small
  power button beside the status disconnects; the status refreshes by itself
  every couple of seconds.
- **Point telescope** slews to the target's freshly computed position. With
  **Astrometric goto** ticked it also plate-solves and corrects to the true sky
  position: the reliable route for a preliminary orbit. The box is a
  preference (its default lives in Settings → Integrations) and it is
  remembered between sessions.
- **STOP** halts the telescope movement **right now**. It is armed the moment
  the mount starts moving (a slew, an astrometric goto or a follow run) and
  disarmed when it ends: use it if the mount heads somewhere it should not.
- **Send plan** prepares the plan (object, frames × exposure, filter, binning,
  gain, offset, dither) in the software and **reads it back** (including the
  binning and dither it is really holding), so the panel shows what actually
  landed. A rejected optional setting (the binning, a gain out of range, a wheel
  that refuses the slot) is reported **without aborting the plan**: the object,
  the exposure and the frame count always land. If the plan's filter is not in
  your wheel, the filter is left as it is and the read-back says so.
- **Start capture** fires it, and the **same button stops it** while the run is
  in flight ("Stop capture"): it stops the **camera**, not the mount (that is
  STOP). With **Follow the object** ticked it runs the night in passes instead
  of one block (see below), and the button becomes "Stop following".
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

At the bottom of the same block are the **darks** and the **bias** of the night
(how many, the dark's exposure, and **the wheel slot each one uses**). They run
**at the end**, after the light frames, in that order. The slot matters: a dark
is taken with the light path blocked, so it must not go through the filter the
lights used. Both start on the **dark slot** you set in Settings → Equipment
(`Dark` by convention) and you can change either one for a single night here.
All four exports carry them: CCDciel and the native NINA sequence as real steps
(`DARK`/`BIAS`), the NINA summary in its `Calibration` list and the CSV as rows
with a `type` column.

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

### Follow the object: N observations without re-pointing by hand

A fast object leaves the camera's field: capture it as-is and half the run ends
up without it. **Follow the object** (a checkbox in the console, for a moving
object and connected) plus **Start capture** asks for a **number of
observations** and drives the whole run:
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
so and honours it anyway.

While it runs you always know where it is: a **progress bar** and a line in the
Capture step say which **observation** (i of N), which **frame** (c of f) and
how much exposure is left, with the percentage of the whole run. **Stop
following** (the same button) stops the camera and the mount right away, not at
the end of the step.

**The guider is put back before each observation.** A slew stops the guider, so
without this each observation would be captured unguided. The run connects the
guider when it can (CCDciel), starts it **using the calibration you already
have** (a fresh calibration is only run if you ask for it in Settings), and
waits until it says it is guiding before capturing. If it cannot start it, the
run says so and captures anyway (short exposures are often usable) and you
decide. Turn it off in Settings if you guide by hand.

**The frames are grouped per observation.** Each observation's frames are
copied into their own subfolder (in the capture folder when NightScribe can see
it, in the project otherwise) and the run writes down how many each took. The
FITS editor then **groups them by themselves**: no more guessing how many
observations there were. When the subfolders are not reachable, the run's own
record groups them; if that does not fit either, the gap the re-point leaves
separates them; the manual count is the last resort. The number is a
**suggestion**: it comes prefilled and you can type another one, and then your
number is the one that counts.

Two things to know: it needs a **plate solver** (the centering is an astrometric
goto), and with **NINA/PINS** each observation is **one frame** (its snapshot
capture takes one) unless you load the native sequence; with CCDciel the frame
count is honoured.

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

The **Calibration** tab of the FITS editor manages the **master library** and
each visit's recipe. The library itself lives in **Settings → Measurement**,
its single home: the tab reads it, resolves the recipe against the visit's
first frame, and **Calibration settings…** is the door there. **Calibrate the
visit** is a one-off run over the visit's frames, not the switch that
calibrates the stack: every pipeline that applies the calibration has its own
checkbox in its own tab, and the Astrometry one (**Apply the calibration**) is
three-state, with the library deciding until you choose.

The library is indexed, not copied: you point at your master FITS and the
app reads from their headers what makes them valid (camera, gain,
temperature, exposure, filter). **What each file is comes from its own
header** (`IMAGETYP`): **Bias**, **Dark** or **Flat**. Only when the header is
silent does the exposure decide, and narrowly: at zero it is a bias, and from
five seconds up it is a dark; anything in between is not guessed, and a light
frame refuses itself. There are **three kinds, not four**: a "dark of the
flats" is a **Dark** at the flat's exposure, and the exposure is what the
matching already keys on.

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

**What each piece is matched on**, and why it is not more:

- **Dark**: camera, gain, sensor temperature within the tolerance (default
  **±3 °C**, set in Settings → Measurement) and **exact exposure**. The
  thermal current is the level, so all four matter.
- **Bias**: camera and gain. It is the read-out pedestal, and it barely moves
  with the sensor's temperature.
- **Flat**: camera and filter **only**. Its shape is the optical train's and
  its level is normalised away, so the gain and the temperature are left out
  of the match on purpose: requiring them rejected real flats.
- A flat's own offset is removed first: a **dark at the flat's exposure**
  (the same pool of darks), or the **bias** when the flat is short.

**The library says why.** When a master you can see is not used, the recipe
names the closest one of that kind with the criterion it failed and the
numbers ("a dark, but at −16 °C against −10 °C, tolerance 3 °C"), so "why is
it not using my dark" has an answer instead of a shrug. A flat older than
**30 days** is used but flagged: the train's dust moves, and a mote may have
appeared or gone.

**Every master has an owner.** A master built from a project's frames belongs
to that project; a bias or a flat can be **shared** with every project. The
recipe tries the project's own masters first and the shared ones as the
fallback, and it never reaches another project's master by accident; one the
project does not own is marked **"(shared)"** in the recipe line, so you know
those pixels are not from your nights. A project can also **use another
project's master** with a **link** (a second row on the same file, never a
copy), and deleting a master takes its row out while the file stays as long
as another row points at it.

**The app can build the masters.** **Build masters…** takes a folder of
calibration frames, classifies each by its header, groups them by the same
key the recipe matches on (a dark's temperature rounded to the degree, so a
night of darks is one master and not a handful), combines each group with the
**median** and writes the master in the library folder. A group of a single
frame is called out: it is a copy of that frame, not an average. The
originals are deleted only if you ask, and only after each master is written
**and** indexed, so a build that fails halfway leaves them where they were.
**Use another project's master…** links one in.

**The visit's recipe**: when you open the editor from a visit, the app
resolves which library master each piece uses, reading the first frame's
header, and warns about anything missing (**What is missing, and why**).
**Calibrate the visit** applies the recipe to every frame; calibration works
in memory and only writes FITS copies if you tick the export box. Those
copies land in the project's **`calibrados/`** subfolder and register to the
visit like any other product. Each copy carries the **NSCALIB** card: feeding
it back into a run, the app sees it is already clean and does **not** subtract
the dark and divide the flat a second time (a double-calibrated frame has no
tell in the image), and both the run and the tab say so.

**If you have no flat for a filter**: the *Model the vignetting from the
frames* option (in Settings → Measurement, its single home; the tab only reads
it) samples the sky on a grid of tiles over a score of spread frames and fits
a smooth surface to what they have in common: the train's vignetting, which is
fixed on the frame. The tiles that a star, a galaxy or a mote pushed off the
trend are thrown away by the fit itself, so no source ends up in the model. It
corrects the **vignetting** (the systematic that matters, about a tenth of a
magnitude) and **not the dust**: a smooth surface has no fine structure, and
that is what a real master is for. It is called a model and not a flat for
exactly that reason, and **a real flat always wins**: the model is the
fallback only for the filters the library has no flat for.

> **Why is a smooth surface enough?** Because the vignetting is smooth and
> worth 0.087 mag, while the dust is worth 0.026 mag: measured against a real
> master, the model reaches 3.93 % against a full-resolution masked flat's
> 4.26 %, in 3 s instead of 20. It needs neither *dithering* nor the stars to
> move, because the tiles they spoil are dropped by themselves. You can open
> it with **See the model** and judge it: it has to be a smooth surface, with
> no star and no mote.

One thing the model depends on: it is built from the frames **with the same
dark or bias removed as the light**. Without one, the pedestal stays in and
compresses the model's shape, so it corrects only part of the vignetting (the
correction drops to about 44 % of what it should be); the app says so and asks
you to index a bias for that camera.

## Further reading

This chapter is the tour; the depth lives in the repository, in the topic
documents the app itself opens from its **?**:

- [`docs/SEQUENCES.md`](../SEQUENCES.md): the sequence export, the capture
  recipe and its troubleshooting section;
- [`docs/UFE.md`](../UFE.md): the FITS editor in full, calibration included.

Next: [06. Photometry](06-photometry.md).
