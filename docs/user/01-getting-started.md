# 01. First steps

## Installation

Three paths, depending on how comfortable you are with a terminal:

- **Windows installer** (no Python needed): download `NightScribeSetup-*.exe`
  from the [releases page](https://github.com/irydeo/nightscribe/releases) and
  run it. Windows SmartScreen will warn because the binary is unsigned:
  *More info → Run anyway*.
- **pip**: `pip install nightscribe` inside a virtual environment, then
  `nightscribe gui`.
- **From source** (if you plan to contribute): clone the repository, create
  the environment and run `.venv/bin/python -m nightscribe gui`.

The detailed, per-system steps are in [INSTALL.md](https://github.com/irydeo/nightscribe/blob/main/INSTALL.md).

Either way you need an internet connection: ephemerides and catalogues are
downloaded on the fly (and cached locally, so the second query for the same
object no longer touches the network).

## First run: the Welcome screen

The first time it starts, NightScribe asks you for the minimum it needs to
work. Everything you answer here can be changed later under
**Tools → Settings**.

### Your observatory

Three ways to tell it where you are; pick one:

1. **Your MPC code** (e.g. `Z41`): the coordinates resolve automatically from
   the official Minor Planet Center list. This is the most accurate option if
   you plan to submit astrometry, because it uses exactly the same point the
   MPC will see in your reports.
2. **"Find my location"**: resolves your city from your public IP. Fine to
   get started, but check the coordinates: an IP does not know on which
   rooftop your telescope sits.
3. **"Pick on the map"** or type latitude, longitude and height by hand.

> **Why so much insistence on coordinates?** Everything else derives from
> them: what is visible tonight, at what altitude, when twilight starts and
> ends. And in minor-planet astrometry, a 100 m error in your position turns
> into a measurable error in the asteroid's position, because the topocentric
> parallax of a nearby NEO can exceed one arcsecond.

### Your equipment

- **Aperture** of the telescope and a realistic **limiting magnitude** for
  your site: NightScribe uses them to avoid suggesting targets you cannot
  reach.
- **Plate scale**: camera pixel size and telescope focal length. If your
  camera is in the **preset** list, choosing it fills in the pixel size and a
  starting photometric profile (read noise, full well, working exposure).

> **Why does the plate scale matter?** Pixel size and focal length give the
> arcseconds per pixel, and from that, how much a NEO moves during an
> exposure or which photometric aperture fits between two stars. A wrong
> value breaks nothing, but it degrades the advice.

### What you want to follow

One card per target kind (NEOs, comets, supernovae, variables, transits...).
Untick what does not interest you: tonight's list will be shorter and more
useful. New kinds arriving with an update come enabled, so you do not miss
them.

### Your data

NightScribe keeps everything (projects, observations, cache) in a local
database. On every update it first writes a verified backup and tells you so
on this same screen; if something does not add up, you will see it here
before anything is touched.

## Settings: what you will change eventually

Under **Tools → Settings…** lives what did not fit in the Welcome. Chapter
[10. Settings](10-settings.md) walks through all of it; here, what is worth
an early visit:

- **Interface language**: Spanish, English or system default. Applies on
  restart.
- **Camera photometric profile**: gain (e⁻/ADU), read noise and linearity.
  These are the numbers that turn the error bar of your measurements into
  something honest; the preset provides starting values, but gain and
  linearity depend on *your* unit and *your* gain setting, and NightScribe
  can measure them from your own frames (chapter 06).
- **Local horizon**: if your observatory has obstacles (buildings, trees,
  mountains), you can load a horizon file. The planner will stop suggesting
  targets hiding behind the neighbour's house.
- **Plate solver**: local ASTAP if you have it installed, with
  nova.astrometry.net as fallback. Needed for astrometry (chapter 07).
- **Optional integrations**: CCDciel (capture, chapter 05), and the NEOfixer,
  Astrometry.net, TNS and AAVSO keys. None is mandatory: without them, the
  corresponding feature simply stays quiet.

> **Why does it ask for an AAVSO token?** The bright-star vigils (T CrB,
> R CrB) compare the current state with the photometry the community uploads
> to the AAVSO, and that API requires identification. Without a token the
> vigils stay silent; with one, they warn you the day T CrB erupts.

Next: [02. Planning the night](02-tonight.md).
