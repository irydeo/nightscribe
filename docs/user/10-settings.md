# 10. Settings

Everything configurable in NightScribe lives under **Tools → Settings…**.
The dialog is a rail of six categories on the left (an icon each: hover to
read the name), a page on the right and a **search box** on top: type a word (a field's name or the first line of
its help) and only what matches stays on screen, across every page. Each
field carries its help right below it, and the rare knobs hide behind an
**advanced** section that opens with a click, so the common path stays
short.

Nothing here is mandatory except the site; each missing integration simply
leaves its feature quiet.

## Observatory

Where and who you are.

- **MPC code**, name, coordinates and height of the observatory (**Resolve
  coordinates** from the code, **Pick on the map…**, or by hand). This is
  the identity of your MPC reports: if you submit astrometry, use the code.
- **AAVSO code**: your observer code; it is written into the EXOTIC handoff
  of transit projects.

## Equipment

What you observe with.

- **Telescope and limits**: the **aperture** and the **limiting magnitude**.
  The Tonight scoring reads them to avoid suggesting the unreachable. Be
  honest with the limiting magnitude; the `inject` command (chapter 09)
  gives you the measured number.
- **Camera**: led by the **preset**, which fills the pixel size and a
  starting profile in one go. Choosing a preset loads **that camera's
  datasheet** over the profile (full well, read noise, dark current,
  linearity); the system gain is never touched, because it is yours. The
  pixel size and the focal length are printed back as the **plate scale**
  (arcseconds per pixel), which is what the NEO exposure advice, the
  photometry and the MPC report actually use. The measured profile (full
  well, system gain, read noise, dark current, linearity, working max
  exposure) is one click away.

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
  list** and the **AAVSO channel** switch) and the **projects folder**.

## Measurement

Everything that turns a night of frames into numbers: photometry,
calibration and astrometry together, so whoever measures does not jump
between pages.

- **Photometry**: the method a *new* plate starts with (the matched
  filter). An already measured plate keeps its own recipe; the plate's
  switch lives in the Photometry tab, beside the measurement (chapter 06).
- **Calibration masters**: the library of bias, dark and flat frames the
  editor's Calibration tab resolves its recipe against. The files are
  linked, never copied or moved.
- **Astrometry**: the detection gate, the MPC submission floor, the
  velocity sweep, the check against other stations (with **Find_Orb**) and
  the worker threads.
- **Plate solver**: *Auto* tries local ASTAP and falls back to
  nova.astrometry.net; you can also force one. **ASTAP binary**: path to
  the executable (empty = look for `astap` on the PATH), with **Test** to
  check it. **Save the solved WCS into the FITS header** (on by default)
  leaves the plate solved for any program, without touching the pixels.
- **EXOTIC (transit reduction)**: path to a **Python ≤ 3.10** and to the
  **EXOTIC environment**. **Prepare environment** builds a private one and
  installs EXOTIC into it (needs network the first time); **Test** checks
  that it imports and reports its version.
- **Advanced**: the saturation ceiling, the flat-field residual and the
  astrometry tolerances. They have sensible defaults; touch them only if
  you know why.

## Integrations

The outside world: a capture server and the optional keys.

- **CCDciel**: host, port (3277 by default) and auto-connect. Control only
  works while CCDciel is open (chapter 05).
- **NEOfixer**, **Astrometry.net**, **TNS bot**, **AAVSO API token**:
  optional keys for, respectively, community reporting, blind-solving plates
  without WCS, transient discovery images and the community photometry that
  feeds the bright-star vigils (chapter 04).
- **Language model (AI, optional)**: to draft the post and the assistant
  (chapters 08 and 11). The endpoint is OpenAI-compatible: a cloud service
  (OpenRouter, Groq, Google AI Studio) or a local one (Ollama, LM Studio)
  both work. Pick the known service, paste the key and type the model, or
  press **List models** and choose the one the endpoint gives you (with its
  exact names if it is local); **Test connection** checks that the three
  agree. It is off by default and nothing leaves your machine until you use
  it.

## Interface

How the app looks and speaks.

- **Language**: Spanish, English or system default; applies on restart.
- **Animated sky on Welcome**: a few stars twinkle and the screen fades in;
  the Moon is drawn at tonight's real phase either way. Applies at once.
- **Icons-only top bar** (FITS editor): the action buttons show compact
  glyphs instead of their labels. Applies at once.
- **Charts and annotations**: your name (**Observer**), who measured the
  plate (**Measurer**; empty = the observer), the **telescope** and
  **camera** lines, the object marker's shape and colour, and the two
  layers of metadata (the plate's band in the editor, the corner boxes of
  the other charts).

> **Why is so much "optional", with no account required anywhere?** Because
> the observatory is yours and so is the data: NightScribe works fully
> without a single key, and each missing integration degrades gracefully
> (the feature stays quiet) instead of blocking you. Keys open doors; they
> do not raise walls.
