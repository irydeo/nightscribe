# 00. Concepts

This is the map. The rest of the guide leans on five words NightScribe repeats
on every screen: **project**, **visit**, **run**, **series** and **report**.
They are nested, one inside the next, and knowing which is which is what makes
the buttons predictable. Read this chapter once; the others will land on solid
ground.

## The hierarchy at a glance

```
project (one object you follow)
└── visit (one observing night, with a date and an optional name)
    ├── astrometry run     -> MPC report
    └── photometry series  -> CSV / AAVSO report, light curve
report / export: what leaves the app
```

| Word | What it is | What hangs from it |
|---|---|---|
| **Project** | One object you follow | Its folder, its visits, its light curve, its outcome |
| **Visit** | One observing night on that project | The night's plates and everything the night produced |
| **Astrometry run** | One track & stack pass over a visit's frames | Its measured points, its stacks, its MPC report, its undo |
| **Photometry series** | The frame-by-frame measurement of a visit | The visit's curve and, joined with the other visits, the project's light curve |
| **Report / export** | What leaves the app | MPC report, CSV and AAVSO report, annotated FITS, charts, posts |

> **Why a hierarchy and not a pile of files?** Because an observing project is
> a story in time, not a folder: the same object is visited night after night,
> each night produces its own plates and its own measurements, and the result
> is the union of all of them. The hierarchy is what lets the app rebuild the
> story (which night, which pass, which curve) without you remembering
> filenames.

## Project

A **project** is one object you follow, with its own folder, its visits, its
measurements and its outcome. Everything you do with that object (captures,
light curve, reports, posts) hangs from the project, so weeks later you pick
it up without rebuilding anything. Chapter [03. Projects](03-projects.md)
creates them; here it is enough to know that the project is the widest box.

## Visit

A **visit** is one observing night on that project. Everything the
night produced hangs from the visit: the FITS plates, the imported photometry,
the ephemerides, the reports, the charts, the notes. Keeping the night as its
own box is what lets the app show you "what came out of a given night" without
you sorting files by hand.

A visit has a **date**, which is its folder and its sort key, and, since
2026-10-16, an optional **name** of its own. The date is still the identity;
the name is for the observer. It is useful when you work the same project
twice in one day, or when a session runs past midnight and the calendar date
is not what you would call that night.

## Astrometry run

An **astrometry run** is one execution of track & stack over a visit's frames.
It has its own measured points, its own stack files, its report and
its undo, so a run is a self-contained result and not a scratch pad.

A visit can hold several runs: several passes in one night, each with its own
stack. The visit's own **Measure the position…** button opens the last one, so
the common case is one click. When the visit already holds a run, opening that
run shows its MPC report already rebuilt from its measurements (2026-10-16):
you reopen a night to send it, not to measure it again. Chapter
[07. Astrometry](07-astrometry.md) has the details.

## Photometry series

The **photometry series** is the equivalent for objects that vary.
**Measure the sequence** measures the whole visit's frames frame by frame,
with a zero point per frame, quality flags and an undo by run. The series
becomes the visit's curve and, joined with the other visits, the project's
light curve. Chapter [06. Photometry](06-photometry.md) has the details.

## Report and export

A **report or export** is what leaves the app: the MPC report of a run, the
CSV and AAVSO report of a series, the annotated FITS, the charts and the
posts. Nothing leaves on its own; each one is a deliberate gesture, and the
app shows you the figure or the text before it goes. Chapter
[08. Reporting it](08-posts.md) covers the last of them.

## Inside a project: the folders

Two housekeeping folders live inside a project, and they exist to keep the
disk honest:

- `prcd/`: the frames of a successful run, moved aside to give disk back. They
  are never deleted and you can bring them back whenever you want. It used to
  be called `procesados/`; renamed on 2026-10-16.
- `dscrd/`: the frames you take out of a night. Moving a frame there is a real
  move, and the registry follows it, so nothing is lost. It used to be called
  `descartados/`; renamed on 2026-10-16.

## The master calibration library

Calibration uses a **master library** that is indexed, not copied (chapter
[05. Capture](05-capture.md)): you point at your master FITS files and the app
reads from their headers what makes them valid (camera, gain, temperature,
exposure, filter). The ownership rule is simple: a master belongs to a
project, but the reusable ones (bias, flat) can be shared with every project,
and another project's master can be used without copying it. So one good flat
serves the whole observatory.

## The unified FITS editor

The **FITS editor** (**Tools → NightScribe Image Workbench**) is the single
door to all FITS work. **Photometry** and **Astrometry** are its tabs, and
**Blink**, **Calibration** and **Annotate** open as windows over the same
plate, with the same zoom and stretch. Opening it from a visit already carries
that visit's frames. A plate that carries astrometry opens **north-up** by
default, the way charts and acquisition screens show the sky; the Settings
switch can turn that off.

## Where to go next

The five words open the rest of the guide:

- [03. Projects](03-projects.md): the project in full, from the card to
  publication.
- [05. Capture](05-capture.md): the visit's frames and the master library.
- [06. Photometry](06-photometry.md): the series, the light curve and periods.
- [07. Astrometry](07-astrometry.md): the run, the stack and the MPC report.
- [08. Reporting it](08-posts.md): the posts and the charts.
- [13. Understanding an object](13-object-card.md): what each type and each
  figure means. The taxonomies and the magnitudes are explained once, in the
  object card; no chapter repeats them.

Next: [01. First steps](01-getting-started.md).
