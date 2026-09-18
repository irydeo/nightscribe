# NightScribe

*[Versión en español](README.es.md)*

**Plan your night, understand every object, tell your science.**

NightScribe is a free (GPL v3) desktop application for amateur astronomical
observatories, with a graphical interface (Qt6, dark theme) and a command
line. It was built by the manager of a real observatory (Irydeo, MPC Z41) who
got tired of doing by hand, every single clear day, what a computer does
better.

## Sound familiar?

- **The afternoon ritual.** Before dinner you open NEOfixer for the NEOs, the
  MPC page for possible comets, COBS for comet magnitudes, Rochester for fresh
  supernovae, ExoClock for tonight's transits, VSX for your variables… and by
  the time you have the full picture, you have lost an hour of twilight.
- **"What can I *actually* observe tonight?"** — not what is above the horizon
  in general, but what is visible *from your site*, over *your horizon*, with
  *your telescope* and *your camera*, in the hours *you* have.
- **The fast-mover trap.** You planned 60-second exposures for an unconfirmed
  NEO and it turns out it moves 5″/min: every frame trailed, the slot wasted.
- **The MPC report.** You measured your asteroid in Astrometrica and now you
  have to assemble an 80-column file by hand, hoping no field slipped.
- **The post that never happened.** You captured something great last month.
  You never wrote it up — and right now you couldn't say which night, how many
  frames or which filter.
- **The variable that flared while nobody looked.** T CrB can erupt any day;
  R CrB fades without warning. Who checks them every single day?

NightScribe exists to answer all of that from one window.

## What is NightScribe?

Three missions, one loop:

1. **Plan the night** — the best targets visible from *your* observatory,
   under *your* real constraints, ranked and explained.
2. **Understand every object** — orbital and physical parameters translated
   into accurate, engaging explanations, in Spanish and English.
3. **Tell your science** — bilingual (ES/EN) posts, a tweet and ready-to-share
   charts, written with the *real data of your session*.

And the piece that ties them together: every chosen target becomes a
**project** — a persistent entity with its own folder — that guides you
through **plan → capture → process → publish** without re-asking you anything
it already knows (coordinates, window, magnitude, exposure plan). Weeks later,
the project is still there: follow-up visits, light curve, final outcome.

## What you need

| | |
|---|---|
| **Required** | Linux or Windows · Python 3.11+ (3.12 recommended) *or* the standalone installer (no Python needed) · ~500 MB of disk · an internet connection for the live data (everything else works offline) |
| **Recommended** | Your **MPC observatory code** (e.g. `Z41`): the first-run wizard resolves your coordinates automatically and it unlocks the site-specific NEO list · your **local horizon file** (TheSkyX `.hrz` or simple `az alt` pairs) · your telescope aperture and camera pixel/focal length |
| **Optional** | **CCDciel** running locally, if you want the app to drive the mount/camera · four free API keys that each unlock one extra (NEOfixer report, Astrometry.net blind solve, TNS bot, AAVSO token) — see *Optional integrations* |

No account, no registration, no telemetry: NightScribe runs on your computer
and talks only to the public data services listed below.

## Your first five minutes

1. **Install** (details in [INSTALL.md](INSTALL.md)):

   ```bash
   python3 -m venv --system-site-packages .venv
   .venv/bin/pip install -r requirements.txt
   .venv/bin/python -m nightscribe gui
   ```

2. **The wizard asks for one thing: your observatory.** Type your MPC code and
   your coordinates are filled in from the MPC list — or enter name, latitude,
   longitude and altitude by hand.
3. The **Tonight** tab computes your night on its own: it downloads the target
   lists, filters them by your site and gear, and ranks everything.
4. **Click any target** — you get its full explained card. Like what you see?
   One button: **Create project**.
5. When you have a minute, open **Tools → Settings**: horizon file, limiting
   magnitude, camera plate scale, session defaults. Everything has a sensible
   default; nothing else is mandatory.

## A whole night (and the weeks after)

What using NightScribe actually feels like, in six scenes:

1. **Late afternoon.** You open the app. Tonight is already computed: a row of
   wide cards, best target first. A chip in the header warns you the Moon is
   87 % lit; another announces a shadow transit on Jupiter at 23:12. The top
   card is an unconfirmed NEO with *"safe start until 23:41 — up to 2.5 h over
   your horizon"* and a one-line reason: *"only seen for 2 days — every night
   counts"*.
2. **You click it.** The object card tells you what it is in plain words, how
   big it probably is, which family its (preliminary) orbit belongs to, how
   fast it moves (5″/min) and — because it knows your camera — that your
   longest trail-free exposure is 45 s. You press **Create project**.
3. **Plan & capture.** You size the session: 40 frames × 45 s, Clear filter.
   The app confirms it fits inside the safe window. You export the ephemeris
   for Cartes du Ciel and the sequence for your capture software — or, with
   CCDciel connected, you send the plan and start the run without leaving the
   app.
4. **Processing.** You measure the stack in your usual astrometry tool and
   **paste** the lines into the project. NightScribe validates them (format,
   your MPC code, designation) and packages the **MPC report file**, ready to
   attach to the email you send.
5. **Publish.** The bilingual post and the tweet are already drafted with the
   real session data — date, 40×45 s, filter — plus the orbit and sky charts.
   You copy, paste, done.
6. **The weeks after.** The journal remembers that night by itself. The
   supernova you confirmed keeps its own light curve, and the dashboard nudges
   you when three nights have passed without a revisit. One evening a chip
   appears in Tonight: *"R CrB is fading — your vigil"*.

## What you can do — in detail

### Plan the night (Tonight tab)

One ranked answer to *"what can I do tonight?"*, mixing eight kinds of
targets:

- **NEOs** — near-Earth asteroids from NEOfixer's *site-specific* list: score,
  priority, cost in minutes of telescope time, apparent rate, sky uncertainty,
  flags for NEOCP/impact-risk/radar/NHATS interest, and — for the still
  unconfirmed NEOCP objects — **preliminary orbital elements with their
  sigmas** (per-element uncertainties), computed from the MPC astrometry.
- **Comets** — live observed magnitudes from COBS, perihelion dates, activity
  flags.
- **PCCP** — the MPC's Possible Comet Confirmation Page: objects reported as
  asteroids that might be comets, with their comet-score. Getting there first
  matters.
- **Supernovae** — the recent discoveries list from Rochester Astronomy.
- **Exoplanet transits** — tonight's transits from ExoClock (the ESA Ariel
  mission's ephemeris-refinement programme), with priority and O-C drift (how
  much the observed transit time is drifting from the prediction — the
  scientific point of re-observing).
- **Close-approach alerts** — ESA NEOCC upcoming flybys: miss distance,
  estimated size, peak magnitude.
- **HADS stars** — high-amplitude δ Scuti variables: stars that pulse so fast
  (periods of 1–5 h) and so strongly (≥ 0.3 mag) that **you watch them vary in
  a single session**. From the living catalogue maintained by P. Wils.
- **Variable stars & duties** — members of your campaigns that are due by
  cadence, stars with an event in progress, stars nearing a predicted VSX
  extremum, your standing vigils, and the AAVSO editorial channel (forum
  alerts and active campaigns) — whenever the star is up tonight.

Every target gets a **unified 0–100 score** built from four weighted families:
**scientific priority** (0–35), **observability from your site** (0–30),
**urgency** (0–20) and **outreach hook** (0–15) — plus feedback from your own
history: observed-but-never-posted gets a nudge, recently posted loses
novelty. The ranking guarantees **kind diversity** — a night with a NEO, a
comet and a transit beats three NEOs — and the best target of each kind gets a
discreet highlight. Each pick carries a one-line **"why tonight"** reason, in
Spanish and English.

The planner respects your real constraints, and tells you when one bites:

- **Limiting magnitude** — hybrid policy: hard cut for supernovae, comets and
  transits; a soft `⚠ mag>N` flag for NEOs/PCCPs (their magnitude predictions
  are often wrong — flagged and dimmed, never silently dropped).
- **Local horizon** — your TheSkyX `.hrz` file (or `az alt` pairs) plus a
  safety margin; a flat minimum altitude as fallback. When a valid horizon
  file exists, it wins.
- **Moon** — warning and score penalty by separation and illumination, never a
  hard filter. A real phase icon, drawn from geometry, sits in the header.
- **Session feasibility** — the dark window over your horizon must cover the
  whole session; the card tells you *"safe start until HH:MM"*.
- **Plate scale** — your camera's pixel size and focal length set the maximum
  trail-free exposure for fast movers, computed per target.

A filter in the header narrows the night to one kind ("only supernovas
today"), Settings holds a permanent whitelist of kinds, and a per-kind cap
keeps one busy source from flooding the view. Up to three **sky-event chips**
(full moon, an opposition, a Jupiter shadow transit…) sit in the header and
jump straight to the sky calendar.

### Chase NEOs and comet candidates

The flow that turns a moving dot into a reported observation:

- The card shows apparent rate (″/min), your **maximum trail-free exposure**,
  the safe window and — for unconfirmed objects — the full preliminary orbit
  with sigmas, drawn as a chart.
- Export **ephemerides** at a configurable step in the formats your planetarium
  software imports (TheSkyX, Cartes du Ciel, CSV) — validated with real
  imports — and the **capture sequence** for NINA (JSON), CCDciel (`.targets`,
  validated against a real CCDciel export, calibration frames included) or a
  generic CSV.
- With CCDciel connected: **Point telescope** slews to the *freshly computed*
  position (Horizons interpolated to the minute, not the stale plan), and
  **Astrometric Goto** adds a plate-solve-and-correct cycle that absorbs
  ephemeris error — the reliable route to NEOCPs with large uncertainties.
- Process in your usual tool, **paste the astrometry** into the project and
  get a validated, packaged **MPC report** (80-column or ADES PSV, your MPC
  code and the designation checked). You send the email; the file is ready.
- The **motion animation** is the smoking gun for outreach: your frames
  star-aligned, a marker riding the *predicted* position with the predicted
  rate/PA and the ephemeris source in the caption. If a dot stays under the
  marker while the stars drift — that's your object.

### Confirm and follow supernovae

- **Confirmation blink**: import your result FITS (target and coordinates are
  already in the project context) and blink it against a PanSTARRS DR1 g
  reference requested with the *exact* center, pixel scale and rotation of your
  image — aligned by construction (DSS2-red takes over south of −30°). If your
  FITS has no astrometric solution, Astrometry.net solves it (free key).
  Exports: animated GIF, H.264 MP4 and a before/after PNG, with your
  observatory watermark and an optional zoom on the transient.
- **Multi-night follow-up**: a supernova project lives for weeks or months.
  Each visit registers the stacked result per filter and your photometry with
  minimal friction — quick entry (just the magnitude), tolerant paste
  (AstroImageJ/Tycho/CSV) or file import. The **light curve** draws your points
  against the typical templates of each type (Ia, II-P/L, Ib/c, SLSN,
  kilonova), the app computes an indicative campaign analysis and verdict, an
  **evolution animation** shows the fade, an annotated FITS copy carries the
  metadata, and a cadence reminder ("3 nights since your last visit") surfaces
  in Tonight when it's time to go back.
- Reference context on request: ZTF points via ALeRCE appear as grey reference
  points under yours, never mixed with your own measurements.
- Export your photometry as **CSV** or **AAVSO EFF** (the AAVSO's extended
  format), with the heliocentric Julian date computed in-app.

### Catch exoplanet transits

Designed so that *anyone dares* to capture their first transit:

- Selection leads with the two real decisions: *"the whole transit fits in
  your night, baselines included"* and *"detectable with your aperture"*
  (ExoClock's minimum-telescope estimate versus yours, as a plain verdict).
- The card tells you **"start capturing at HH:MM UTC"** — the transit plus the
  out-of-transit baseline on both edges — and a **visual timeline** shows
  night, horizon, capture window and milestones at a glance.
- Suggested exposure and maximum cadence (so the ingress is resolved), with
  the readout overhead made explicit, and a warning when the baseline doesn't
  fit. A persistent five-step **pre-flight checklist** walks the capture.
- The reduction is 100 % external: NightScribe exports a **pre-filled
  `inits.json` for EXOTIC** (the NASA/JPL citizen-science pipeline) and guides
  the final submission to ExoClock or the AAVSO Exoplanet Database.

### Variable stars, HADS, campaigns and vigils

- **HADS sessions**: no known phase to aim at — the recommendation is a
  continuous capture of 2× the period (cadence ≤ P/12), and the listing gate
  requires a full cycle to fit over your horizon. The catalogue is hybrid:
  P. Wils' Google Sheet (updated daily) merged with a packaged snapshot that
  also works offline. The sheet's color legend feeds the score — stars with
  found or possible period changes, never-observed stars, and this month's
  coverage gaps get urgency bonuses. Your run folds by phase into the classic
  saw-tooth, on screen and in PNG.
- **Campaigns**: a campaign is the shared commitment of a group — science
  goal, protocol (cadence, filters, comparison stars), report/data URLs. One
  campaign, many attached projects (deleting the campaign frees them, never
  deletes them). A member is *due* when its last session is `cadence_nights`
  old and lands in Tonight automatically; it also lands when an **event** is
  detected or a predicted **extremum** is imminent. The Campaigns tab is the
  war room: "Happening now" with ⚡ events, ⏳ upcoming extrema and 👁 vigils,
  per-campaign health cards (members × cadence × events), and full sentences
  in plain language.
- **Vigils**: your standing watch list — *T CrB eruption watch*, *R CrB fade
  watch* — one star per line, editable in Settings. Each vigil is checked
  against the latest ZTF magnitude versus its baseline (own 12 h cache); for
  stars brighter than ZTF's saturation, it reads the AAVSO community
  photometry with your token.
- **AAVSO channel**: editorial alerts from the AAVSO forum and the active
  observing campaigns, with the star name validated against VSX before it is
  shown. A signal about a star that already is a project merges into that
  project's reasons — never a duplicate row.
- **The variables engine**: VSX extrema predictions with heliocentric Julian
  dates, an event advisor on magnitude jumps (configurable threshold), and
  fold-by-epoch views for periodic stars.

### The Sun and the sky calendar

From the **Tools** menu:

- **The Sun now** — the latest NASA SDO channels (corona at 193/304/171 Å,
  sunspots, magnetogram), the NOAA active-regions map, the indices (sunspot
  number, F10.7 radio flux, Kp, the week's strongest flare), a watermarked PNG
  panel ready for your socials and a bilingual "the sky today" post draft. An
  "impact on your night" line connects it to observing: a bright Moon hurts
  faint targets, a high Kp may mean auroras.
- **Sky calendar** — today + 60 days, computed **100 % locally** (no network):
  true lunar phases, perigee/apogee, Moon–planet and planet–planet
  conjunctions, oppositions and greatest elongations (as ecliptic-longitude
  crossings), **probable eclipses** from shadow-cone geometry — honestly
  labelled as probable — and meteor showers. Validated against astropy and
  published almanacs.
- **Jupiter's moons this week** — Galilean satellite **and shadow** transits
  across the disc, filtered for your site (Jupiter up, at night), at planning
  grade with the "±10 min" label always visible (validated against 22 JPL
  Horizons windows; worst case 9.6 min).

### Drive your observatory (CCDciel)

The fourth tab talks to your local **CCDciel** over JSON-RPC — only while
CCDciel is actually running: status at a glance (version, CCD temperature,
tracking, slewing), **Point telescope** (quick slew to a moving target's
freshly computed position), **Astrometric Goto** (slew + capture + plate-solve
+ correction) and **live capture** (stage the project's saved plan, start the
run).

### Remember everything: journal and attention

- **Observing journal** (Tools menu): your diary writes itself — projects
  created and closed, sessions logged, files produced, photometry points,
  campaign activity — grouped by **observing night** (noon-to-noon local,
  the astronomer's day), filterable by kind and searchable. Double-click jumps
  back to the project.
- **Needs your attention**: the app speaks first. The Projects home lists the
  3–5 things asking for action — a campaign member due tonight, a supernova
  overdue for a revisit, an observation never posted — each with its reason in
  plain words and one button that lands exactly where you act. Computed
  locally, no network.
- Your activity feeds back into the planner: the suggestion engine knows what
  you already observed or posted, and the Tonight list reflects it.

### Understand any object

**Tools → Explore object…** (or click any target): identity and physical data
cross-matched from JPL SBDB/Horizons/CAD, SIMBAD, TNS and the NASA Exoplanet
Archive, rendered as a calling card:

- A **hook line** and outreach bullets, in Spanish and English.
- A **parameter table where every row is explained** in plain language:
  orbital family, MOID (minimum distance the orbit ever gets to Earth's),
  size estimated from the absolute magnitude, next close approach, discovery
  date… Multiline, nothing truncated.
- **Charts**: the orbit (animated by date, with hover readouts), the night sky
  with *your* horizon silhouette and the safe window shaded, the survey field,
  the light curve. In the app they are live vector graphics (zoom, pan,
  hover); the same engines render the PNGs for social media.
- **Capture chips**: current magnitude, apparent rate, max trail-free
  exposure, window and hours above the horizon — plus copyable coordinates
  (decimal and sexagesimal) with their epoch.

### Tell the world

The post is not an afterthought; it is the last step of every project:

- Bilingual drafts (ES/EN) plus a tweet, written with the **real session
  data** — date, N×t, filter — not a generic template.
- The chart inventory: orbit view, night sky with your horizon silhouette,
  survey field, light curve against templates, transit timeline, Sun panel,
  supernova before/after and blink GIF/MP4, NEO motion trail, SN evolution
  animation. Ready to attach.

## Where the data comes from

Every external source, what it gives you, how fresh it is, and whether it
needs a key. All network access goes through an **SQLite cache with per-source
TTLs** (the refresh column): repeat queries are instant and free for the
service. If a source is down, the rest of the app never breaks — check
**Help → Data sources** for the live status of each one.

**Planning sources (feed Tonight):**

| Source | What it gives you | Refresh | Key? |
|---|---|---|---|
| NEOfixer (U. Arizona) | Site-specific NEO list: score, priority, cost, magnitude, rate, uncertainty, NEOCP/impact/radar/NHATS flags; preliminary orbits with sigmas for unconfirmed objects | 12 h (orbits 1.5 h) | No (only for the optional community report) |
| MPC — PCCP | Possible comets awaiting confirmation, with comet-score | 6 h | No |
| COBS | Live comet magnitudes, perihelion, activity | 6 h | No |
| Rochester Astronomy | Recent supernova discoveries | 6 h | No |
| ExoClock (ESA Ariel) | ~776 exoplanet transit ephemerides: depth, duration, priority, O-C drift, minimum telescope | 24 h | No |
| ESA NEOCC | Upcoming close approaches: miss distance, size, peak magnitude | 6 h | No |
| HADS sheet (P. Wils / VVS) | The living high-amplitude δ Scuti catalogue with color-coded priorities and monthly coverage (packaged snapshot as offline fallback) | 12 h | No |
| AAVSO VSX | Variable star identity: type, period, epoch, extrema | 7 d | No |
| AAVSO forum & campaigns | Editorial alerts and active observing campaigns | 12 h | No |
| ALeRCE / ZTF | Latest magnitude for your vigils | 12 h | No |
| AAVSO photometry | Community measurements for bright vigils | 12 h | Yes (free token) |

**Object data (feed the cards and posts):**

| Source | What it gives you | Refresh | Key? |
|---|---|---|---|
| JPL SBDB | Identity, orbital class, elements, MOID, physical parameters (H, size, rotation, albedo, spectral class) | 7 d | No |
| JPL Horizons | Precise ephemerides topocentric to *your* MPC code | 12 h | No |
| JPL CAD | Next close approaches | 7 d | No |
| SIMBAD (CDS) | Transients and host galaxies (Harvard mirror as fallback) | 7 d | No |
| TNS | Fresh transient positions — days before SIMBAD ingests them | 6 h | No (only for discovery images) |
| NASA Exoplanet Archive | Planet period, radius, mass, host star | 7 d | No |
| ALeRCE / ZTF | Reference light-curve context | 30 d | No |

**Sun and environment:**

| Source | What it gives you | Refresh | Key? |
|---|---|---|---|
| NOAA SWPC | Sunspot number, F10.7, Kp, active regions, X-ray flux | 1 h | No |
| SILSO | Sunspot series and cycle context | 24 h | No |
| NASA SDO | Latest corona and magnetogram images (public domain) | 1 h | No |

**Images:**

| Source | What it gives you | Refresh | Key? |
|---|---|---|---|
| DESI Legacy Survey / CDS hips2fits | Color cutouts and PanSTARRS DR1 g / DSS2 reference fields, requested with your image's exact geometry | 30 d | No |
| Astrometry.net | Blind plate-solve when your FITS has no WCS | 30 d per file | Yes (free key) |

**Computed locally, no network at all:** Sun, Moon and planet positions
(Schlyter's algorithms, arcminute precision), minor-body propagation (Kepler
from the SBDB elements), transit instants, heliocentric Julian dates, the
whole 60-day sky calendar and Jupiter's moon events. Images are credited
(NASA/SDO, PanSTARRS, DSS); external websites (SolarMonitor, ETD, NEOfixer,
TNS…) open in your browser, never embedded.

## Optional integrations

Everything below is optional; each missing piece degrades gracefully and tells
you so. Configure them in **Tools → Settings → Integrations**.

| Integration | What it unlocks |
|---|---|
| **CCDciel** (local, host/port) | The Observatory tab: status, point telescope, astrometric goto, live capture. Only while CCDciel is running |
| **NEOfixer API key** | Report `will_observe` / `observed` back for community coordination |
| **Astrometry.net key** (free) | Blind solve of WCS-less FITS in the blink |
| **TNS bot credentials** | Discovery images shown inside the app (respecting each survey's licence) |
| **AAVSO API token** | Community photometry for the bright-star vigils |
| **AAVSO observer code** | Filled into the photometry exports and the EXOTIC handoff |

## Your data stays with you

Everything NightScribe knows lives in a local **SQLite** database in your
user's data directory: the HTTP cache, your projects, sessions, photometry,
campaigns and settings. Each project gets its own **container folder** —
plans, sequences, reports, charts, posts — under a root you choose and can
change later. No accounts, no cloud, no telemetry. Uninstall and delete the
folder: nothing remains anywhere else.

## What NightScribe is *not* (yet)

Honesty section, so you know where the edges are:

- **Not a planetarium.** It does not replace Stellarium or Cartes du Ciel — it
  exports ephemerides *to* them.
- **It does not reduce your raw frames.** Calibration, stacking and
  astrometric/photometric measurement happen in your usual tools
  (Astrometrica, AstroImageJ, EXOTIC…). NightScribe prepares the night,
  validates and packages the results, and writes the story.
- **The MPC report is packaged and validated; you send the email.**
- **Export formats**: the CCDciel sequence format is validated against a real
  CCDciel export, and the TheSkyX/Cartes du Ciel ephemerides against real
  imports; the NINA and generic-CSV sequence exports are starting points to
  validate against your own versions.
- **Planning-grade sky events**: eclipses are *probable eclipses*, labelled as
  such, and Galilean moon events carry their ±10 min label.
- **Status: alpha.** It is the daily driver of a real observatory (MPC Z41)
  with a 1,300+ automated test suite, but expect sharp edges — and please
  report them.

## Quickstart and CLI

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m nightscribe gui        # desktop app
.venv/bin/python -m nightscribe tonight    # best targets tonight (CLI)
```

Everything the GUI does has a command-line counterpart (`--help` on each for
details):

| Command | What it does |
|---|---|
| `gui` | desktop application |
| `tonight` | best targets tonight (`--fecha YYYY-MM-DD`, `--top N`) |
| `explore <object>` | explained object card in the terminal |
| `post <object>` | bilingual drafts + tweet (`--png` adds the charts) |
| `solar` | Sun state (`--png` renders the panel) |
| `blink <name> <fits>` | supernova blink vs PanSTARRS (`--video`, `--post`, `--zoom`, `--efecto blink/fade`…) |
| `history` | the observing journal in the terminal |
| `project …` | minimal project management: `list`, `create`, `advance`, `show`, `close`, `reopen`, `files` |

See [INSTALL.md](INSTALL.md) for full per-OS instructions, the pip package and
the standalone installer, and [CONTRIBUTING.md](CONTRIBUTING.md) to hack on
it.

## Documentation

Design, architecture, data sources, scoring, workflows and every decision
(ADRs) live in [`docs/`](docs/) — bilingual ES/EN.

## Licence

GPL v3 — (c) 2026 Francisco José Calvo Fernández
([Irydeo Observatory](https://www.irydeo.com), MPC Z41).
