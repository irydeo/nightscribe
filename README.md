# NightScribe

*[Versión en español](README.es.md)*

**Plan your night, understand every object, tell your science.**

NightScribe is the working tool of an amateur astronomical observatory: it
gathers the whole cycle of an observation in one place, from choosing what to
look at tonight with your sky and your equipment, to understanding the object,
capturing and reducing the images and telling what you have found.

## What is NightScribe?

Four missions, one loop:

1. **Plan the night**: the best targets visible from *your* observatory,
   under *your* real constraints, ranked and explained.
2. **Understand every object**: orbital and physical parameters translated
   into accurate, engaging explanations, in Spanish and English.
3. **Capture and reduce**: it drives your mount and camera through CCDciel or
   NINA/PINS, and it calibrates, stacks and measures your own frames:
   photometry (variables, exoplanets, supernovae) and MPC-ready astrometry of
   minor bodies, without leaving the window.
4. **Tell it**: a bilingual (ES/EN) draft and the night's charts, written
   with the real data of your session.

Every chosen target becomes a **project**: a persistent entity with its own
folder that walks you through **Card → Capture → Analysis → Publishing**
without asking again what it already knows (coordinates, window, magnitude,
exposure plan). Weeks later the project is still there: follow-up visits, the
light curve, the final outcome.

## What you can follow

Eight kinds of targets share the same list every night, with the Sun and the
sky as context. Each one has its own chapter in the
[user guide](docs/user/README.md): what it is, why it matters tonight and how
it is measured.

- **NEOs, confirmed and unconfirmed**: a site-specific list with score,
  priority and cost in minutes of telescope time, the trail-free exposure your
  camera allows, the track & stack in the app and the MPC report checked
  against what other stations published.
- **Comets**: live observed magnitudes, perihelion dates and activity.
- **Comet candidates (PCCP)**: objects reported as asteroids that might be
  comets. Getting there first matters.
- **Supernovae**: the recent discoveries, a confirmation blink against a
  survey reference, multi-night follow-up against the typical templates of
  each type, and the export.
- **Exoplanet transits**: tonight's transits with their O-C drift, whether the
  whole transit fits in your night, and the EXOTIC handoff.
- **Close approaches**: ESA NEOCC flybys with miss distance, size and peak
  magnitude.
- **HADS stars**: high-amplitude δ Scuti variables that vary within a single
  session, with colour-coded priorities and the phase-folded curve.
- **Variable stars and duties**: your campaigns by cadence, the stars nearing
  a predicted extremum, your vigils checked daily against ZTF and the AAVSO
  community photometry, and the period search.
- **The Sun and the sky**: the state of the Sun, Jupiter's moon events for
  your site and a 60-day sky calendar computed locally.

## What you need

| | |
|---|---|
| **Required** | Linux or Windows · Python 3.11+ (3.12 recommended) *or* the standalone installer (no Python needed) · ~500 MB of disk · an internet connection for the live data (everything else works offline) |
| **Recommended** | Your **MPC observatory code** (three characters, the ones assigned to your station): the first-run wizard resolves your coordinates automatically and it unlocks the site-specific NEO list · your **local horizon file** (TheSkyX `.hrz` or simple `az alt` pairs) · your telescope aperture and camera pixel/focal length |
| **Optional** | **CCDciel or NINA/PINS** running locally, if you want the app to drive the mount and camera (the observatory integration; one backend at a time) · five free API keys that each unlock one extra (NEOfixer report, Astrometry.net blind solve, light-pollution atlas, TNS bot, AAVSO token) · the optional **assistant** (a model you configure) · **EXOTIC** (the transit reduction), the one external tool you install by hand: **Find_Orb** travels inside the installers and the Linux packages; see *Optional integrations* |

No account, no registration, no telemetry: NightScribe runs on your computer
and talks only to the public data services listed below.

## Your first five minutes

1. **Install.** No Python needed: every file lives on the
   [Releases page](https://github.com/irydeo/nightscribe/releases). Pick your
   system:
   - **Windows**: run the `NightScribeSetup-*.exe` installer (per-user, no
     admin rights). It is not code signed, so Windows has two ways to stop it:
     SmartScreen warns and lets you through with *More info → Run anyway*,
     while **Smart App Control** (Windows 11, on by default on new
     installations) blocks it with no way through at all. Prefer not to
     install anything? Unzip the portable `NightScribe-*-windows-x64.zip` and
     run `nightscribe.exe gui` (the same two gates apply to it). What to do
     about Smart App Control is in
     [the guide](docs/user/01-getting-started.md).
   - **Linux**: install the `.deb` (Debian, Ubuntu, Mint) with
     `sudo apt install ./nightscribe_*_amd64.deb`, or the `.rpm` (Fedora,
     openSUSE) with `sudo dnf install ./nightscribe-*.x86_64.rpm`, then run
     `nightscribe gui`.

   The full per-system steps are in [INSTALL.md](INSTALL.md). Running from a
   source checkout is the last option there, for contributors.

2. **The wizard asks for one thing: your observatory.** Type your MPC code and
   your coordinates are filled in from the MPC list; or enter name, latitude,
   longitude and altitude by hand.
3. The **Tonight** view (from **+ NEW PROJECT** in the header) computes your
   night on its own: it downloads the target lists, filters them by your site
   and gear, and ranks everything.
4. **Click any target** and you get its full explained card. Like what you
   see? One button: **Create project**.
5. When you have a minute, open **Tools → Settings…**: horizon file, limiting
   magnitude, camera plate scale, session defaults. Everything has a sensible
   default; nothing else is mandatory.

### From source (contributors)

NightScribe also runs from a checkout; the full, per-system walkthrough is in
[INSTALL.md](INSTALL.md). The short version:

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m nightscribe gui
```

## Video tutorials

The [tutorial playlist on YouTube](https://www.youtube.com/playlist?list=PLASv2NZqn7zU)
collects the walkthroughs of the project. The narration is in Spanish and the
interface in English; the [user guide](docs/user/README.md) is the written
reference.

## A whole night (and the weeks after)

The guide walks
[a real night](docs/user/03-projects.md) from the first click to the report.
The short version:

1. **Late afternoon.** One click on **+ NEW PROJECT** computes the night: the
   best target first, a chip saying how lit the Moon is and another announcing
   a shadow transit on Jupiter, and a one-line reason for the top row.
2. **You click it.** The card says what the object is, how fast it moves and,
   because it knows your camera, your longest trail-free exposure. You press
   **Create project**.
3. **Plan and capture.** Size the session; the app confirms it fits inside the
   safe window. Export the ephemeris and the sequence, or, with CCDciel or
   NINA/PINS connected, send the plan and start the run without leaving the
   app.
4. **Analysis.** Back home you open the visit in the editor: it solves the
   reference frame, registers the sequence and **stacks it following the
   object**, measures every observation and checks the result against the
   other stations. The MPC report comes out ready to send.
5. **The weeks after.** The journal remembers that night by itself, the light
   curve grows, the dashboard nudges you when a revisit is due and the
   bilingual draft is already written with the real session data.

## Where the data comes from

Tonight's list and the object cards are fed by public services, each with its
own refresh: **NEOfixer**, the **MPC** (PCCP, observatory codes, published
observations), **COBS**, **Rochester Astronomy**, **ExoClock**, **ESA NEOCC**,
the **HADS** catalogue, **AAVSO** (VSX, forum, campaigns and photometry),
**ALeRCE/ZTF**, **JPL** (SBDB, Horizons, CAD), **SIMBAD**, **TNS**, the
**NASA Exoplanet Archive**, **VizieR**, **NOAA SWPC**, **SILSO**, **NASA SDO**
and the **DESI Legacy Survey**.

All network access goes through an **SQLite cache with per-source TTLs**:
repeat queries are instant and free for the service, and a source that is down
never breaks the rest of the app. Sun, Moon and planet positions, the sky
calendar and the whole **reduction** (registration, stack, measurement,
periods) are computed locally, with no service involved. The full table, with
what each source gives you and whether it needs a key, is in
[docs/DATA_SOURCES.md](docs/DATA_SOURCES.md).

## Optional integrations

Everything below is optional; each missing piece degrades gracefully and tells
you so. Configure them in **Tools → Settings → Integrations**.

| Integration | What it unlocks |
|---|---|
| **CCDciel** (local, host/port) | The Capture step of each project: status, point telescope, astrometric goto, **Stop goto**, staging the saved plan (read back) and live capture. Only while CCDciel is running |
| **NINA / PINS** (local, host/port) | The same Capture step over the **Advanced API v2** plugin: status, point telescope, astrometric goto (Center), **Stop goto**, filter wheel and a one-shot snapshot capture. NINA on Windows, PINS on Linux; one backend at a time |
| **NEOfixer API key** | Report `will_observe` / `observed` back for community coordination |
| **Astrometry.net key** (free) | Blind solve of WCS-less FITS in the blink |
| **TNS bot credentials** | Discovery images shown inside the app (respecting each survey's licence) |
| **AAVSO API token** | Community photometry for the bright-star vigils |
| **AAVSO observer code** | Filled into the photometry exports and the EXOTIC handoff |
| **Light-pollution key** (free, lightpollutionmap.info) | The sky-brightness atlas at your site: the Bortle context the sky-quality notes use |
| **Assistant** (optional, off by default) | A chat panel that answers from the app's own guide and design notes, offline and without embeddings. It needs a model you configure; without it the app is unchanged |
| **Find_Orb** (ships with the installers and the Linux packages) | The check of your astrometric measurement against the observations other stations published, before the MPC report. It travels inside NightScribe, so it works out of the box; from a source checkout you install it yourself, and the app says so instead of pretending |
| **EXOTIC** (external Python 3.10 or older) | The transit reduction: the app writes the handoff, runs EXOTIC for you and imports its light curve and parameters into the project. Without it the handoff is still yours to run by hand |

## Your data stays with you

Everything NightScribe knows lives in a local **SQLite** database in your
user's data directory: the HTTP cache, your projects, sessions, photometry,
campaigns and settings. Each project gets its own **container folder** (plans,
sequences, reports, charts, posts) under a root you choose and can change
later. No accounts, no cloud, no telemetry. Uninstall and delete the folder:
nothing remains anywhere else.

## Quickstart and CLI

Install first (see *Your first five minutes*). Then everything the GUI does
for **planning and publishing** has a command-line counterpart:

```bash
nightscribe gui        # desktop app
nightscribe tonight    # best targets tonight (CLI)
```

`tonight`, `explore`, `post`, `solar`, `blink`, `sequence`, `history`,
`project` and `inject` are the rest (`--help` on each for the details), and
chapter [09. The command line](docs/user/09-cli.md) has the whole list. The
**reduction** (calibration, track & stack, astrometry, photometry, periods)
lives in the GUI.

See [INSTALL.md](INSTALL.md) for the full per-OS instructions (the standalone
installer and the Linux packages first), and
[CONTRIBUTING.md](CONTRIBUTING.md) to hack on it.

## Documentation

**The [user guide](docs/user/README.md)** ([español](docs/user/README.es.md))
walks the whole cycle, from the first run to the MPC report, in short
chapters with the "why" of each option. It is published as a website:
**<https://irydeo.github.io/nightscribe/>** (**Help → User guide (web)**).

Design, architecture, data sources, scoring, workflows and every design
decision live in [`docs/`](docs/), in Spanish and English.

Something missing, wrong or unclear? [Open an issue](https://github.com/irydeo/nightscribe/issues).

## Licence

NightScribe is free software, published under the
[GPL v3](https://github.com/irydeo/nightscribe/blob/main/LICENSE): you can use
it, study it, change it and share it, and whatever you pass on stays free for
the next person. There is no paid edition and no locked feature.
