# 10. Settings

Everything configurable in NightScribe lives under **Tools → Settings…**.
This chapter walks each section: what it decides and when it is worth
touching. Nothing here is mandatory except the site; each missing
integration simply leaves its feature quiet.

## Site & equipment

- **MPC code**, name, coordinates and height of the observatory (**Resolve
  coordinates** from the code, **Pick on the map…**, or by hand). This is
  the identity of your MPC reports: if you submit astrometry, use the code.
- **AAVSO code**: your observer code; it is written into the EXOTIC handoff
  of transit projects.
- **Interface language**: Spanish, English or system default; applies on
  restart.

## Equipment and limits

- **Aperture (inches)** and **limiting magnitude**: the Tonight scoring
  reads them to avoid suggesting the unreachable. Be honest with the
  limiting magnitude; the `inject` command (chapter 09) gives you the
  measured number.

> **Why measure the limiting magnitude instead of trusting the datasheet?**
> Because the real limit depends on your sky, your camera, your exposures
> and your reduction. An optimistic figure fills the list with impossible
> targets; a pessimistic one hides good nights from you.

## Camera (plate scale)

**Pixel size**, **focal length**, **camera type** (CCD/CMOS/DSLR) and
**pixel binning**. Pixel and focal give the arcseconds-per-pixel scale: it
feeds the NEO exposure advice, the photometry and the MPC report (the
camera type is written into it).

## Photometric camera profile

**Preset** (fills the pixel size and a starting profile), **full well**,
**linearity (ADU)**, **system gain (e⁻/ADU)**, **read noise (e⁻)**, **dark
current** and **working max exposure**.

> **Why "per unit and per gain"?** Because linearity and maximum exposure
> are not properties of the camera model, but of your specific unit at the
> gain setting you use. The preset provides the datasheet value as a starting
> point; the true value is measured on your own frames (the app does it,
> chapter 06), and 0 means "unknown": the app says so instead of making
> something up.

## Photometry

- **Measure with the matched filter by default**: what a *new* plate starts
  with. An already measured plate keeps its own recipe; the plate's switch
  lives in the Photometry tab, beside the measurement (chapter 06).

## Chart annotations

Your name (**Observer**), who measured the plate (**Measurer**; empty = the
observer) and the **telescope** line as they should read in the boxes of
the charts you export.

## Observing

- **Local horizon**: a horizon file (TheSkyX `.hrz` or "az alt" pairs) with
  a safety margin. With it, the planner stops suggesting what hides behind
  your obstacles.
- **Object kinds** shown in Tonight, **Moon constraint**, default **session
  values**, the variable **vigils list** and the **projects folder**.

## Plate solver

**Solver**: *Auto* tries local ASTAP and falls back to nova.astrometry.net;
you can also force one. **ASTAP binary**: path to the executable (empty =
look for `astap` on the PATH), with **Test** to check it. **Save the solved
WCS into the FITS header** (on by default) leaves the plate solved for any
program, without touching the pixels.

## Find_Orb (orbit check)

The **Find_Orb binary** (the non-interactive `fo`) cross-checks your
measurements against the orbit before the MPC report. **Install…** sorts it
out for you: if `fo` is already on the PATH it uses it, and if not, it
creates a private conda-forge environment without touching anything on your
system. Without it, the check is not available, and the app says so.

## EXOTIC (transit reduction)

Path to a **Python ≤ 3.10** and to the **EXOTIC environment**. **Prepare
environment** builds a private one and installs EXOTIC into it (needs
network the first time); **Test** checks that it imports and reports its
version. Without this, the EXOTIC block of transits (chapter 06) does not
run, although the rest of the flow keeps working.

## Integrations

- **CCDciel**: host, port (3277 by default) and auto-connect. Control only
  works while CCDciel is open (chapter 05).
- **NEOfixer**, **Astrometry.net**, **TNS bot**, **AAVSO API token**:
  optional keys for, respectively, community reporting, blind-solving plates
  without WCS, transient discovery images and the community photometry that
  feeds the bright-star vigils (chapter 04).

## Interface

- **Animated sky on Welcome**: a few stars twinkle and the screen fades in;
  the Moon is drawn at tonight's real phase either way. Applies at once.
- **Icons-only top bar** (FITS editor): the action buttons show compact
  glyphs instead of their labels. Applies at once.

> **Why is so much "optional", with no account required anywhere?** Because
> the observatory is yours and so is the data: NightScribe works fully
> without a single key, and each missing integration degrades gracefully
> (the feature stays quiet) instead of blocking you. Keys open doors; they
> do not raise walls.
