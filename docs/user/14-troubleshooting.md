# 14. When something goes wrong

Most nights nothing goes wrong. This chapter is for the ones that do: what
each failure means, what NightScribe does on its own, and what is left for
you to do.

## First stop: the log

**Help → Open the log…** opens the file the application writes while it runs.
If a dialog appeared and vanished, or a step failed without saying why, the
answer is almost always in there. When you report a problem, attach that file.

The file does not grow without a limit: it rotates by size, so the folder holds
the current log and a few older ones (a handful of megabytes at most) and you
never have to clean it by hand.

## There is no network

NightScribe works offline for everything that does not need live data: the
Sun and Moon, the twilights, the sky calendar, the whole reduction (calibration,
stacking, photometry, astrometry) and your saved projects. What stops working
is the part that fetches fresh lists: tonight's targets, the ephemerides, the
survey cutouts.

- If **Tonight** comes back empty, it says so. The empty state tells the two
  cases apart: *no sources answered* (a network problem, check the
  connection) and *nothing of your enabled kinds is up tonight* (the sources
  answered; try enabling more kinds in the filter).
- The sources that fail degrade gracefully and are logged as a warning; the
  app never crashes because a website is down.
- Everything already fetched is cached with its own freshness window, so a
  list you loaded an hour ago still works.

## The plate will not solve

Solving finds the stars in your image and works out where it points. It needs
a solver:

- **Settings → Integrations → Solver**: `auto` tries a local **ASTAP** first
  and falls back to **Astrometry.net** (which needs a free key and a network);
- if you have no local solver, set it to `astrometry` and make sure the key
  is filled in;
- a plate with very few stars, heavy trailing or a wrong target can defeat
  any solver. The error names the frame, and the log has the detail.

## The plate has no WCS

The FITS editor and the astrometry need a solved plate (a WCS: the map from
pixels to sky). If your camera did not write one, the editor says
**Load a FITS image or open a visit**, and the visit's own **Solve** button
(and the batch solve) is the door: it resolves the reference frame and the
rest follow it.

## The MPC report is rejected

The report has to match the format the Minor Planet Center accepts, and the
observations have to be good enough. The app builds the report from your
measurements and checks it as it builds it: the format (80 columns or ADES
PSV), the dates, the codes and the signal-to-noise of each observation. Where
you measured, it also says which observations it does not recommend sending
(the decision stays yours). If the MPC itself rejects a report, its message
names the line; fix the measurement and build the report again. The astrometry
chapter (07) walks the whole path.

## EXOTIC is not configured

The transit reduction runs in **EXOTIC**, an external program that needs a
Python of its own (3.10 to 3.12). The transit block of the editor tells you
whether it found one; without it you can still export the handoff
(`inits.json`) and run EXOTIC yourself, then import its output back. Nothing
is lost: the handoff is always yours.

The shortest way out is the environment **ready to unzip** that the project
publishes in its own release, [`exotic-env`](https://github.com/irydeo/nightscribe/releases/tag/exotic-env)
(chapter 06): download the zip for your platform, unzip it anywhere and point
**Settings → Measurement → Advanced → EXOTIC** at the interpreter inside it.

Two things that save time when something goes wrong:

- If the app says the interpreter you pointed at **is not there any more**,
  that field was holding a path to something that was deleted or that sits on
  a drive that is not mounted. Clear it: the app then looks for another one
  and tells you what it found.
- The interpreter must live **outside** the environment folder. Pointing at a
  Python that sits inside it is refused, with the reason: rebuilding the
  environment would delete the interpreter halfway through the build.

## The app does not start

- Run it once from a terminal (`nightscribe gui`). The traceback, if any,
  goes to the console and to the log file.
- The log lives in your user data directory; **Help → Open the log…** shows
  it, and the path is printed at the top of the file.
- A read-only home or a full disk can stop the app from writing its database.
  The message says which.

## The package installed but apt said "Permiso denegado"

Installing the `.deb` from your Downloads folder can print a line like:

> Download is performed unsandboxed as root as file '...' couldn't be accessed
> by user '_apt'. - pkgAcquire::Run (13: Permission denied)

It is apt's own note, **not an error**: apt reads a local package through its
unprivileged `_apt` user, and when that user cannot reach the file (the folder
or the file itself is not readable by everyone) it reads it as **root without
the sandbox** instead, and says so. The install finishes normally.

If you would rather not see it, copy the file somewhere every user can read
first:

```bash
cp ~/Downloads/nightscribe_*.deb /tmp/ && sudo apt install /tmp/nightscribe_*.deb
```

Nothing is wrong with the package: the note is about **where the file is**,
not about what is inside it.

## Reporting a problem

The repository's issue tracker is the place. Include: what you were doing,
what you expected, what happened, and the log file. The **About** box names
the exact version and the data sources, which is what a bug report needs
first.

Back to the [index](README.md).
