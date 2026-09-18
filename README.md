# NightScribe

*[Versión en español](README.es.md)*

**Plan your night, understand every object, tell your science.**

NightScribe is a desktop application (Qt6 GUI + CLI) for amateur astronomical
observatories, built around three missions:

1. **Plan the night** — the best targets visible from *your* observatory,
   under *your* real constraints.
2. **Understand every object** — orbital and physical parameters translated
   into accurate, engaging explanations.
3. **Tell your science** — bilingual (ES/EN) posts, tweets and charts ready
   for social media.

Everything starts from a suggestion and ends as a published result: each chosen
target becomes a **project** that guides you through plan → capture → process →
publish without re-asking anything.

## Tonight — plan the night

One ranked answer to *"what can I do tonight?"*, mixing eight kinds of targets:

- **NEOs** — NEOfixer site-specific list: score, priority, cost in minutes,
  apparent rate, uncertainty, NEOCP/impact/radar/NHATS flags, and preliminary
  orbital elements (with sigmas) for unconfirmed NEOCP objects.
- **Comets** — COBS live magnitudes, perihelion dates, activity flags.
- **PCCP** — the MPC's possible-comet confirmation page, with its comet score.
- **Supernovae** — Rochester Astronomy's recent discoveries.
- **Exoplanet transits** — ExoClock (ESA Ariel) priorities and O-C drift.
- **Close-approach alerts** — ESA NEOCC upcoming flybys (miss distance, size,
  peak magnitude).
- **HADS & variable stars** — the high-amplitude δ Scuti catalogue (P. Wils)
  and VSX extrema predictions, matched to your night.
- **Campaign duties & AAVSO channel** — campaign members due by cadence, your
  variable-star vigils, and the AAVSO forum alerts/active campaigns, surfaced
  when the star is up.

Every target gets a **unified 0–100 score** from four weighted families:
scientific priority (0–35), observability from your site (0–30), urgency
(0–20) and outreach hook (0–15) — plus feedback from your own history
(observed-but-not-posted gets a nudge; recently posted loses novelty). The
Top-N guarantees **kind diversity**: a night with a NEO, a comet and a transit
beats three NEOs. Each pick comes with a one-line **"why tonight"** reason, in
Spanish and English.

The planner honours your real constraints:

- **Limiting magnitude** — hybrid policy: hard cut for SNe/comets/transits,
  soft `⚠` warning for NEOs/PCCPs (predictions can be wrong; flagged and
  dimmed, never dropped).
- **Local horizon** — your TheSkyX `.hrz` file (or "az alt" pairs) plus a
  safety margin; flat minimum altitude as fallback.
- **Moon** — warning and score penalty by separation/illumination, never a
  hard filter.
- **Session feasibility** — the window must cover the session; the card tells
  you *"safe start until HH:MM"*.
- **Plate scale** — camera pixel + focal length set the maximum trailing-free
  exposure for fast NEOs.

Sky-event chips in the Tonight header (full moon, an opposition, a Jupiter
shadow transit…) jump straight to the sky calendar. One click on any target
**creates its project**.

## Projects — from target to published result

A project is a persistent entity (kind, object, status, full context snapshot)
with a **container folder** that gathers everything it produces, and three
guided steps. The **Details tab** always shows the object's calling card first:
hook line, outreach bullets, parameter table with ES/EN explanations, charts
(orbit, night sky, field, light curve) and the capture chips (magnitude,
rate ″/min, max no-trail exposure, window, hours above horizon).

- **Plan & Capture** — size the session (N frames × exposure, filter) and the
  app checks it fits the safe window. Export the sequence for **NINA** (JSON),
  **CCDciel** (`.targets`) or **CSV**; export **ephemerides** at a configurable
  step for TheSkyX and Cartes du Ciel. With CCDciel connected, send the plan
  and start the capture without leaving the app.
- **Process** — import the result FITS (target and coordinates already known
  from context). Supernovae confirm with the **blink** against PanSTARRS DR1 g
  — GIF/MP4/before-and-after PNG with the observatory watermark. NEO/PCCP
  astrometry is pasted in, validated (80-column/ADES, MPC code, designation)
  and packaged into an **MPC report** ready to email. Photometry exports as
  **CSV** and **AAVSO EFF**. Transits hand off to **EXOTIC** with a pre-filled
  `inits.json`.
- **Publish** — the bilingual post + tweet are drafted with the **real session
  data** (date, N×t, filter), and observed/posted marks feed back into the
  suggestion engine.

## Campaigns & variables

- **Campaigns** — a campaign is the shared commitment of a group: science
  goal, protocol (cadence, filters, comparison stars), report/data URLs. One
  campaign, many attached projects (deleting a campaign frees them). A member
  is *due* when its last session is `cadence_nights` old — and lands in
  Tonight automatically. The tab shows the full health: members × cadence ×
  events (⚡ when a variable flares).
- **Variable vigils** — your standing watch list (T CrB eruption watch, R CrB
  fade watch, …), one star per line, checked against the latest ZTF magnitude;
  bright targets read AAVSO community photometry with your token.
- **Variables engine** — VSX extrema predictions with heliocentric Julian
  dates, an event advisor on magnitude jumps, and the hybrid HADS catalogue
  (local snapshot + P. Wils' live sheet).

## Observatory — CCDciel control center

The fourth tab drives your local **CCDciel** observatory over JSON-RPC (only
while CCDciel is running): status at a glance (version, CCD temperature,
tracking, slewing), **Point telescope** (quick slew to a moving target's
freshly computed position), **Astrometric Goto** (slew + capture + plate-solve
+ correction — absorbs ephemeris error, the reliable route for NEOCPs) and
**live capture** (stage the project's saved plan, start the run).

## Sun & sky calendar

From the Tools menu:

- **The Sun now** — NASA SDO channels (corona 193/304/171 Å, sunspots,
  magnetogram), NOAA active-regions map, SSN / F10.7 / Kp / weekly flare, a
  watermarked PNG panel for your socials and a bilingual "sky today" post
  draft.
- **Sky calendar** — today + 60 days, computed **100 % locally** (no network):
  true lunar phases, perigee/apogee, Moon–planet and planet–planet
  conjunctions, oppositions and greatest elongations (as ecliptic-longitude
  crossings), **probable eclipses** (shadow-cone geometry, honestly labelled)
  and meteor showers. Validated against astropy and almanacs.
- **Jupiter's moons this week** — Galilean satellite **and shadow** transits
  across the disc, filtered for your site (Jupiter up at night), planning
  grade ±10 min.

## Journal

Your observing diary writes itself: projects created/closed, sessions logged,
files produced, photometry points, campaigns — grouped by **observing night**
(noon-to-noon local) and filterable by kind.

## Explore & Post — understand and tell

- **Explore** any object: identity and physical data cross-matched from JPL
  SBDB/Horizons/CAD, SIMBAD, TNS, NASA Exoplanet Archive and more; orbital
  family, MOID, size from H, next close approach — every parameter explained
  in plain language, ES and EN.
- **Post** renders the bilingual drafts + tweet + ready-to-attach PNG charts:
  orbit view, night sky with *your* horizon silhouette, Sun panel, transit
  light-curve timeline, supernova before/after, NEO motion trail.

## Needs your attention

The app speaks first: the Projects home lists the 3–5 things asking for action
— a campaign member due tonight, a supernova project overdue for a revisit, an
observation never posted — each with its plain-language reason and one button
that lands exactly where you act.

## Data sources

NEOfixer · MPC (PCCP, ObsCodes) · JPL SBDB / Horizons / CAD · ESA NEOCC ·
COBS · Rochester Astronomy · SIMBAD · TNS · ExoClock · NASA Exoplanet Archive ·
AAVSO (VSX, forum alerts, campaigns, community photometry) · ALeRCE/ZTF ·
HADS catalogue (P. Wils) · NOAA SWPC · SILSO · NASA SDO · Astrometry.net ·
PanSTARRS DR1 cutouts — plus your local CCDciel when connected.

All network access goes through an SQLite cache with per-source TTLs; a source
being down never breaks the rest (status in the *Data sources* menu), and
everything but the live data works offline.

## Quickstart

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m nightscribe gui        # desktop app
.venv/bin/python -m nightscribe tonight    # best targets tonight (CLI)
```

CLI commands (`--help` on each for details):

| Command | What it does |
|---|---|
| `gui` | desktop application |
| `tonight` | best targets tonight (`--fecha`, `--top`) |
| `explore` | explained object card |
| `post` | bilingual drafts + tweet (`--png` for charts) |
| `solar` | Sun state (`--png` for the panel) |
| `blink` | SN blink: your FITS vs PanSTARRS (`--video`, `--post`, `--zoom`…) |
| `history` | observing journal |
| `project` | minimal project management (list/create/advance/close/…) |

See [INSTALL.md](INSTALL.md) for full per-OS instructions and the standalone
installer, and [CONTRIBUTING.md](CONTRIBUTING.md) to hack on it.

## Documentation

Design, architecture, data sources, scoring, workflows and all decisions (ADRs)
live in [`docs/`](docs/) (bilingual ES/EN).

## Licence

GPL v3 — (c) 2026 Francisco José Calvo Fernández (Irydeo Observatory, MPC Z41).
