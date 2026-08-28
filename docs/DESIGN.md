# NightScribe — Product Design

*[Versión en español](DESIGN.es.md)*

## Vision

**Plan your night, understand every object, tell your science.**

NightScribe is a desktop application for amateur astronomical observatories that closes
the loop: it tells you *what is worth observing tonight*, explains *why each object
matters* in plain language, and turns your observation into *ready-to-post bilingual
content* for social networks.

The differentiator: existing tools show raw tables or dated charts. NightScribe
**translates, explains and draws beautifully** — rigorous but human.

## Target users

- Amateur observatories with an MPC code that report astrometry (NEOs, comets, PCCP).
- Amateur astronomers who follow supernovae, comets and exoplanet transits.
- Anyone who wants engaging, data-driven astronomy content without spending hours.

Default configuration ships with MPC station **Z41** (Irydeo Observatory) as an example;
everything is configurable so any observatory can adopt it.

## The views

*(UX v3, ADR-019: the app reorganises around **Projects**; tabs: Tonight · Projects ·
Solar system · History. Explore/Post/Blink become contextual panels opened from a
project, with ad-hoc access under Tools. Guided per-kind flows in WORKFLOWS.md.)*

### 1. Tonight — the home view

Not a table: a **recommendation** (see ADR-017 for the v2 redesign, ADR-019 for v3).

- **"Right now" band**: targets currently above the horizon, with live altitude
  and azimuth, ordered by score.
- **Top 3 unified ranking** (NEOs, supernovae, comets, PCCP candidates and
  exoplanet transits compete on one 0–100 score) with medals and a generated
  one-liner: *"why tonight"* (in the UI language).
- Full target list below: **sortable by clicking any column header**, with
  **dynamic columns per type filter** (NEOs show NObs/MOID/NEOfixer priority;
  supernovae show type/host/discovery date...) plus a detail panel with
  per-target actions (Explore / Post / Observed).
- Buttons per target: *Mark observed* (optionally reports to NEOfixer), *Post* and
  **Create project** (UX v3).

### Interface shell

Menu bar (File / View / Tools / Help); **Settings live in a modal dialog**
(Tools → Settings…); language switch under View. Tabs (UX v3, ADR-019): Tonight ·
Projects · Solar system · History. The UI shows a single language at a time; only
generated posts are bilingual.
- Header with night context: sunset, end of twilight, Moon phase/illumination.

### 2. Projects — the guided flow (UX v3, ADR-019)

Every target can become a **project**: a persistent, guided flow per object kind
 (Plan → Capture → Process → Publish) that carries the full context — no
re-asking for names, coordinates or images. Capture sequences and ephemerides are
exported as files for external software (NINA, CCDciel, TheSkyX, Cartes du Ciel —
ADR-021); astrometry measured elsewhere is pasted back, validated and packaged for the
MPC report (ADR-022). Constraints honoured by the planner: real local horizon, Moon,
session feasibility and camera plate scale (ADR-020).

### 3. Explore ("Explora")

Type any identifier (`2021EQ3`, `29P`, `SN2023ixf`, `HD 209458 b`, `sol`) and get the
**explained object card**:

- Orbital family with context (Apollo, Aten, Trojan, Jupiter-family comet, Oort...).
- Every orbital/physical parameter translated, in two depth levels (basic / deep).
- Honest risk assessment (MOID, PHA, Torino scale) without alarmism.
- Size estimates from H and spectral class, everyday comparisons.
- For comets: expected brightness from M1/K1, perihelion window, origin story.
- For supernovae: host galaxy, distance, "the light left home X million years ago",
  reference field cutout with crosshair.
- For exoplanets: planet type, "its year lasts X days", equilibrium temperature, host star.

### 4. Post

- Drafts in **Spanish and English** plus a 280-character tweet, always both languages
  regardless of UI language (the audience is bilingual).
- Ready-to-attach PNG charts (orbit, night sky curve, transit window, SN before/after),
  rendered with the same code that draws them in the GUI.
- Copy buttons; CLI writes `post_ES.md`, `post_EN.md`, `tweet.txt`, PNGs.
- Optional user observation image → side-by-side or animated blink GIF
  (reference survey vs. observatory image).

### 5. Solar system now ("Sistema solar ahora")

- **Sun**: latest SDO image (public domain) in several wavelengths, own active-region map
  built from NOAA coordinates, sunspot number and trend (NOAA + SILSO), GOES flares,
  solar wind (DSCOVR), Kp → "auroras tonight?"
- **Moon**: phase, illumination, current distance in km (the measuring stick of our posts).
- **Planets tonight**: which are visible from your site after dusk, with magnitudes.
- External resources as links (Raben maps, SolarMonitor, SIDC, universemonitor) — never
  embedded, for copyright reasons.

### 6. Settings ("Configuración")

- First-run wizard: enter your **MPC observatory code** → coordinates resolved
  automatically (MPC ObsCodes) — or full manual location (lat/lon/height).
- Observatory name (signs the posts), telescope aperture (filters transit feasibility),
  UI language (System / Español / English), NEOfixer API key (optional), TNS
  credentials (optional, only to display discovery images in-app).

## UX principles (identity trait)

- **Guided flow, not technical panels**: open the app and the night is already suggested.
- Zero required fields; sensible defaults (mag < 18, altitude > 30 deg).
- Tooltips everywhere; human-readable errors; progress in the status bar.
- Native light/dark theme, HiDPI friendly (Qt6).
- Everything reachable in two clicks: suggest → observe → publish.

## Object types and their stories

| Type | Sources | The story we tell |
|---|---|---|
| NEO | NEOfixer, SBDB, Horizons, CAD, ESA NEOCC | distance in lunar distances, size vs. everyday things, next close approach, why your astrometry matters |
| Comet | COBS, SBDB (M1/K1), Horizons | origin (Oort / Jupiter family), expected brightness, outbursts, perihelion window, anti-sunward tail |
| PCCP candidate | MPC PCCP page | "score 85/100 on the MPC's possible-comet page: your image could confirm the discovery" |
| Supernova / transient | Rochester, SIMBAD, cutouts | host galaxy + distance, "the light left X million years ago", before/after blink |
| Exoplanet transit | ExoClock, NASA Exoplanet Archive | "tonight a planet eclipses its star by 1.5% for 3 h; your light curve helps ESA's Ariel" |
| Sun | SDO, NOAA/GOES/DSCOVR, SILSO | solar cycle state, active regions, flares, aurora chances |

## Out of scope

- Telescope control (the sibling project `saas` does that). **Exporting capture
  sequences and ephemerides as files** for external software (NINA, CCDciel,
  planetariums) **is in scope** — it is file generation, not control (ADR-021).
- Automatic publishing to Meta/X APIs (copy & paste by design decision; the MPC report
  is also packaged for the user to send, ADR-022).
- 3D orbit visualization (2D top-down by design; maybe later).
