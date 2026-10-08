# 05. Capture

## CCDciel: from plan to telescope

If your observatory runs on [CCDciel](https://www.ap-i.net/ccdciel/),
NightScribe can hand the capture plan to it directly, without exporting
files or retyping coordinates.

One-time setup under **Tools → Settings → Integrations**: host and port of
the machine running CCDciel (default 3277), and whether to auto-connect. One
condition: **CCDciel must be open**; NightScribe talks to its JSON-RPC
server, not to the drivers.

From a project's **Capture** step:

- **Connect CCDciel** shows the observatory status (mount, filter wheel,
  camera) on the panel.
- **Send plan** prepares in CCDciel the object name, exposure, frame count
  and filter (the list is read from your wheel; if it does not answer, the
  classic L/R/G/B/Ha/OIII/SII list is used).
- The slew converts the plan's J2000 coordinates to **apparent** before
  sending them, and can do a plate-solved goto if your CCDciel workflow is
  set up for it.

> **Why apparent coordinates and not J2000?** Because the mount points at
> the sky of *now*, not the one from the year 2000. Precession, nutation and
> aberration move a star's apparent position by tens of arcseconds: more
> than the field of many cameras. NightScribe does the conversion for you so
> the target lands on the chip, not off it.

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
