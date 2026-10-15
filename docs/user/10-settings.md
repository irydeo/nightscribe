# 10. Settings

Everything configurable in NightScribe lives under **Tools → Settings…**.
The dialog is a rail of six named categories on the left, a page on the
right and a **search box** on top: type a word (a field's name or the first
line of its help, like "gain", "moon" or "api key") and only what matches
stays on screen, across every page. Each field carries its help right below
it. Each group shows its **title in a bar** that clearly starts it.

The common settings are always in view; the expert ones live behind a
single **Advanced** door at the bottom of their page, closed by default, so
a page reads short and finished. Nothing is removed: open the door with one
click, or just search; a match behind a door opens it by itself, and
clearing the box hands the door back to the state you left it in.

Nothing here is mandatory except the site; each missing integration simply
leaves its feature quiet.

## Observatory

Where and who you are. Set it once; everything is computed from here.

- **Site**: **MPC code**, name, coordinates and height of the observatory
  (**Resolve coordinates** from the code, **Pick on the map…**, or by
  hand). This is the identity of your MPC reports: if you submit
  astrometry, use the code. **AAVSO code**: your observer code, written
  into the EXOTIC handoff of transit projects. **Sky brightness**
  (mag/arcsec²): how bright your zenith sky is; it sets the suggested
  sub-exposure (chapter 05). **Look up** fills it from the light-pollution
  atlas when you have the key (Integrations), or read it off the map the
  button opens at your site.
- **Observer and reports**: how your measurements are signed. Your name
  (**Observer**), who measured the plate (**Measurer**; empty = the
  observer), the **contact email** (the MPC submission cannot be sent
  without it), the **telescope** and **camera** lines (free text, or built
  from the aperture, the type and the focal ratio) and an optional **report
  comment**. The MPC report's header and the chart boxes read from here.

## Equipment

What you observe with.

- **Telescope and limits**: the **aperture** and the **limiting magnitude**.
  The Tonight scoring reads them to avoid suggesting the unreachable. Be
  honest with the limiting magnitude; the `inject` command (chapter 09)
  gives you the measured number.
- **Camera**: led by the **preset**, which fills the pixel size and a
  starting profile in one go. Choosing a preset loads **that camera's
  datasheet** over the profile (full well, read noise, dark current,
  readout/download, linearity); the system gain is never touched, because it
  is yours. The pixel size and the focal length are printed back as the
  **plate scale** (arcseconds per pixel), which is what the NEO exposure
  advice, the photometry and the MPC report actually use.
- **Camera: measured profile** (behind the **Advanced** door): the sensor
  physics at your gain setting (full well, system gain, read noise, dark
  current, readout/download, linearity, working max exposure), with the
  **Measure gain…** action. The preset already fills starting values and 0
  means "unknown"; measure yours before trusting an error bar. The
  **readout + download** is the app's **one per-frame overhead** (the preset
  fills it from the sensor, by type and size; a CCD reads out in seconds):
  it sizes a sequence and bounds a fast object's run, so a slow download
  means fewer frames before the object leaves the field. Raise it if your
  mount also needs to settle between frames.

> **Why measure the limiting magnitude instead of trusting the datasheet?**
> Because the real limit depends on your sky, your camera, your exposures
> and your reduction. An optimistic figure fills the list with impossible
> targets; a pessimistic one hides good nights from you.

> **Why "per unit and per gain"?** Because linearity and maximum exposure
> are not properties of the camera model, but of your specific unit at the
> gain setting you use. The preset provides the datasheet value as a
> starting point; the true value is measured on your own frames (the app
> does it, chapter 06), and 0 means "unknown": the app says so instead of
> making something up.

> **Your own camera.** The preset catalogue is a data file. If your camera is
> not there, add it (or fix one) in `<config>/cameras.toml`, next to
> `nightscribe.json`: a `[[camera]]` with a new `key` adds it, the same `key`
> corrects a bundled one, and `hide = ["key"]` removes one. Settings re-reads
> the file when it opens, so no restart is needed; if there is a mistake,
> Settings → Camera tells you and keeps the bundled catalogue.

## Observing

How the night is planned and filtered.

- **Local horizon**: a horizon file (TheSkyX `.hrz` or "az alt" pairs) with
  a safety margin. With it, the planner stops suggesting what hides behind
  your obstacles.
- **Object kinds** shown in Tonight, the **transits** filter, the **Moon**
  constraint, the default **session** values (with the variable **vigils
  list**, the **AAVSO channel** switch and the follow run's **guider
  handling**: whether the guider is restarted before each observation of a
  run, and whether it is recalibrated at the start; the Capture step reads
  them when a run begins) and the **projects folder**.

## Measurement

Everything that turns a night of frames into numbers. The three groups you
see first (photometry, solver, masters) cover a normal night; the rest is
one click away behind the **Advanced** door.

- **Photometry**: the method a *new* plate starts with (the matched
  filter). An already measured plate keeps its own recipe; the plate's
  switch lives in the Photometry tab, beside the measurement (chapter 06).
- **Calibration masters**: the library of bias, dark and flat frames the
  editor's Calibration tab resolves its recipe against, plus the
  calibration's policy (model the vignetting when no real flat is there, and
  the dark's temperature tolerance). The files are linked, never copied or
  moved, and they go in **by files or by folder**: each frame is classified
  by its own header (`IMAGETYP`), so you never say which is a dark and which
  is a flat. There are **three kinds, not four**: a "dark of the flats" is a
  dark, and its exposure is what makes it valid. The app can also **build
  the masters** from a folder of frames: it groups them by their key,
  combines them with the median and writes the master in the library folder.
  Every master has an **owner**: the ones a project builds are its own, a
  bias or a flat can be **shared** with everyone, and a project can **use**
  another's without copying it. The table says who owns each row ("Shared"
  when it belongs to all) and from here you change the owner. The library
  lives only here; the editor's Calibration tab **reads** it and links back
  to this page.
- **Plate solver**: *Auto* tries local ASTAP and falls back to
  nova.astrometry.net; you can also force one. **ASTAP binary**: path to
  the executable (empty = look for `astap` on the PATH), with **Test** to
  check it. **Save the solved WCS into the FITS header** (on by default)
  leaves the plate solved for any program, without touching the pixels.
- **Advanced**: the saturation ceiling and the flat-field residual, the
  astrometry gates and tolerances (the detection gate, the MPC submission
  floor, the velocity sweep, the check against other stations, the worker
  threads and the **graphics card** with its **backend**: on by default,
  with **OpenCL**; chapter 12 says what it accelerates, how to install CUDA
  and why it changes nothing about the result), **Find_Orb** (the orbit
  check) and **EXOTIC** (the transit reduction: path to a **Python ≤ 3.10**
  and to the environment; **Prepare environment** builds a private one and
  installs EXOTIC into it, and **Test** checks that it imports). They all
  have sensible defaults; touch them only if you know why.

## Integrations

The outside world: your observatory software and the optional keys.

- **Observatory software**: pick **CCDciel** or **NINA / PINS** (one at a
  time). Only the chosen program's fields are shown. Each keeps its own host,
  port (3277 for CCDciel, 1888 for NINA/PINS) and auto-connect. Control only
  works while the program is open, and for NINA/PINS its Advanced API v2 plugin
  must be installed and enabled (chapter 05). Switching the choice disconnects
  the other program.
- **NEOfixer**, **Astrometry.net**, **TNS bot**, **AAVSO API token**,
  **light pollution**: optional keys for, respectively, community reporting,
  blind-solving plates without WCS, transient discovery images, the community
  photometry that feeds the bright-star vigils (chapter 04) and the site's sky
  brightness (chapter 05).
- **Language model (AI, optional, experimental; behind the Advanced door)**:
  to draft the post and the assistant (chapters 08 and 11). The endpoint is
  OpenAI-compatible: a cloud service (OpenRouter, Groq, Google AI Studio) or
  a local one (Ollama, LM Studio) both work. Pick the known service, paste
  the key and type the model, or press **List models** and choose the one the
  endpoint gives you (with its exact names if it is local); **Test
  connection** checks that the three agree. It is off by default: with it
  off, the assistant and the AI buttons are disabled, and nothing leaves
  your machine until you use it.
- **Long reports**: with this on, the AI writes a full article (Spanish and
  English) with every project fact and the generated images, not just the
  short post. It spends many more tokens, so a paid endpoint charges more for
  it; a local server costs nothing. Off by default.

## Interface

How the app looks and speaks.

- **Language**: Spanish, English or system default; applies on restart.
- **Animated sky on Welcome**: a few stars twinkle and the screen fades in;
  the Moon is drawn at tonight's real phase either way. Applies at once.
- **Icons-only top bar** (FITS editor): the action buttons show compact
  glyphs instead of their labels. Applies at once.
- **Charts and annotations**: the object marker's shape and colour, and the
  two layers of metadata (the plate's band in the editor, the corner boxes
  of the other charts). Who signs them (observer, measurer, telescope,
  camera) is set in **Observatory → Observer and reports**.

> **Why is so much "optional", with no account required anywhere?** Because
> the observatory is yours and so is the data: NightScribe works fully
> without a single key, and each missing integration degrades gracefully
> (the feature stays quiet) instead of blocking you. Keys open doors; they
> do not raise walls.
