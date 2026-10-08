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
3. **Capture and reduce**: it drives your mount and camera through CCDciel,
   and it calibrates, stacks and measures your own frames: photometry
   (variables, exoplanets, supernovae) and MPC-ready astrometry of minor
   bodies, without leaving the window.
4. **Tell it**: a bilingual (ES/EN) draft and the night's charts, written
   with the real data of your session.

And the piece that ties them together: every chosen target becomes a
**project**, a persistent entity with its own folder, that guides you through
**Card → Capture → Analysis → Publishing** without re-asking you anything it
already knows (coordinates, window, magnitude, exposure plan). And the app
does not stop at the plan: it drives your mount and camera, and it calibrates,
stacks and measures your own frames (astrometry, photometry, periods) without
leaving the window. Weeks later, the project is still there: follow-up visits,
light curve, final outcome.

## What you can follow

Eight kinds of targets share the same list every night, with the Sun and the
sky as context. This is what you get from each one:

- **NEOs, confirmed and unconfirmed.** NEOfixer's *site-specific* list with
  score, priority and cost in minutes of telescope time; apparent rate and
  sky uncertainty; flags for NEOCP, impact-risk, radar or NHATS interest. For
  the still unconfirmed NEOCP candidates, preliminary orbital elements with
  their sigmas, computed from the MPC astrometry. The app knows your camera
  and tells you the maximum trail-free exposure; you export the ephemeris to
  your planetarium and the sequence to your capture software, and then the
  frames are **stacked and measured in the app** (the track & stack: solve the
  reference, register, stack following the object, detect, sweep the velocity,
  measure each observation), or you paste the astrometry your own tool
  produced and the validator reviews it line by line. The MPC report is
  generated in ADES or 80 columns and checked against the observations other
  stations have published. The motion animation, your frames star-aligned with
  a marker riding the object, is the smoking gun.
- **Comets.** Live observed magnitudes from COBS, perihelion dates and
  activity flags, so you know how each comet is doing tonight, not last
  month.
- **Comet candidates (PCCP).** The MPC's Possible Comet Confirmation Page:
  objects reported as asteroids that might be comets, with their comet-score.
  Getting there first matters.
- **Supernovae.** The recent discoveries list from Rochester Astronomy and a
  complete flow: a confirmation blink of your FITS against a PanSTARRS
  reference requested with the exact geometry of your image, multi-night
  follow-up with your photometry drawn against the typical templates of each
  type (Ia, II-P/L, Ib/c, SLSN, kilonova), an indicative campaign analysis,
  an evolution animation, CSV or AAVSO EFF export, and cadence reminders when
  it is time to go back.
- **Exoplanet transits.** Tonight's transits from ExoClock (the ESA Ariel
  mission's ephemeris-refinement programme), with priority and O-C drift: how
  much the observed transit time is drifting from the prediction, which is
  the scientific point of re-observing. The card tells you whether the whole
  transit fits in your night, whether it is detectable with your aperture and
  when to start capturing, with a visual timeline, a pre-flight checklist and
  the EXOTIC handoff: the app writes the `inits.json`, runs EXOTIC for you and
  imports its light curve and parameters back into the project.
- **Close approaches.** ESA NEOCC upcoming flybys: miss distance, estimated
  size and peak magnitude, to catch the week's fast visitor.
- **HADS stars.** High-amplitude δ Scuti variables: they pulse so fast
  (periods of 1–5 h) and so strongly (≥ 0.3 mag) that you watch them vary in
  a single session. From the living catalogue maintained by P. Wils, with
  color-coded priorities: found or possible period changes, never-observed
  stars and this month's coverage gaps. Your run folds by phase into the
  classic saw-tooth.
- **Variable stars and duties.** Members of your campaigns that are due by
  cadence, stars with an event in progress, stars nearing a predicted VSX
  extremum, your standing vigils (the T CrB eruption, the R CrB fade) checked
  daily against ZTF and the AAVSO community photometry, and the AAVSO
  editorial channel with its alerts and active campaigns. Whenever the star
  is up tonight. The frames are measured in the app (the photometric series:
  a calibrated point per frame, the zero point anchored by a comparison star
  every frame, the ensemble of comparisons with its outlier veto) and the
  period is searched there too (Lomb-Scargle and PDM, with the false-alarm
  probability and the folded curve by night).
- **The Sun and the sky.** The state of the Sun with the latest NASA SDO
  channels and the NOAA indices, transits and shadows of Jupiter's moons
  filtered for your site, and a 60-day sky calendar computed locally: phases,
  conjunctions, oppositions, probable eclipses and meteor showers.

## What you need

| | |
|---|---|
| **Required** | Linux or Windows · Python 3.11+ (3.12 recommended) *or* the standalone installer (no Python needed) · ~500 MB of disk · an internet connection for the live data (everything else works offline) |
| **Recommended** | Your **MPC observatory code** (e.g. `Z41`): the first-run wizard resolves your coordinates automatically and it unlocks the site-specific NEO list · your **local horizon file** (TheSkyX `.hrz` or simple `az alt` pairs) · your telescope aperture and camera pixel/focal length |
| **Optional** | **CCDciel** running locally, if you want the app to drive the mount and camera (the first observatory integration; NINA and others are planned) · four free API keys that each unlock one extra (NEOfixer report, Astrometry.net blind solve, TNS bot, AAVSO token) · two optional external tools, **Find_Orb** (the check against other observers) and **EXOTIC** (the transit reduction); see *Optional integrations* |

No account, no registration, no telemetry: NightScribe runs on your computer
and talks only to the public data services listed below.

## Your first five minutes

1. **Install** (details in [INSTALL.md](INSTALL.md); on Windows there is a
   [standalone installer](https://github.com/irydeo/nightscribe/releases),
   no Python needed):

   ```bash
   python3 -m venv --system-site-packages .venv
   .venv/bin/pip install -r requirements.txt
   .venv/bin/python -m nightscribe gui
   ```

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

## A whole night (and the weeks after)

What using NightScribe actually feels like, in five scenes:

1. **Late afternoon.** You open the app and the night panel greets you; one click on **+ NEW PROJECT** and the night is already computed: a list
   of wide rows, best target first. A chip in the header warns you the Moon is
   87 % lit; another announces a shadow transit on Jupiter at 23:12. The top
   row is an unconfirmed NEO with *"safe start until 23:41; 2.5 h over your
   horizon"* and a one-line reason: *"only seen for 2 days: every night
   counts"*.
2. **You click it.** The object card tells you what it is in plain words, how
   big it probably is, which family its (preliminary) orbit belongs to, how
   fast it moves (5″/min) and, because it knows your camera, that your longest
   trail-free exposure is 45 s. You press **Create project**.
3. **Plan and capture.** You size the session: 40 frames × 45 s, Clear filter.
   The app confirms it fits inside the safe window. You export the ephemeris
   for Cartes du Ciel and the sequence for your capture software; or, with
   CCDciel connected, you send the plan and start the run without leaving the
   app.
4. **Analysis.** Back home you open the visit in the editor. The app solves
   the reference frame, registers the sequence and **stacks it following the
   object**; it looks for the dot, sweeps the velocity, measures every
   observation twice (on its stack and per frame) and checks the result
   against what the other stations have published. The MPC report comes out
   in ADES or 80 columns with the middle-of-exposure instants and the
   propagated uncertainties, ready to send. (You can also measure in Tycho
   Tracker or another tool and **paste** the lines: NightScribe validates them
   one by one before they leave.)
5. **The weeks after.** The journal remembers that night by itself. The
   supernova you confirmed keeps its own light curve, and the dashboard nudges
   you when three nights have passed without a revisit. If you feel like
   telling it, the bilingual draft is already written with the real session
   data. One evening a chip appears in the Tonight view: *"R CrB is fading: your
   vigil"*.

## What you can do: in detail

### Plan the night (the Tonight view)

One ranked answer to *"what can I do tonight?"*, with the eight kinds of
targets from the previous section mixed into a single ranking.

Every target gets a **unified 0–100 score** built from four weighted families:
**scientific priority** (0–35), **observability from your site** (0–30),
**urgency** (0–20) and **outreach hook** (0–15); plus feedback from your own
history: observed-but-never-posted gets a nudge, recently posted loses
novelty. The ranking guarantees **kind diversity**: a night with a NEO, a
comet and a transit beats three NEOs; and the best target of each kind gets a
discreet highlight. Each pick carries a one-line **"why tonight"** reason, in
Spanish and English.

The planner respects your real constraints, and tells you when one bites:

- **Limiting magnitude**: a hybrid policy: hard cut for supernovae, comets and
  transits; a soft `⚠ mag>N` flag for NEOs and PCCPs (their magnitude
  predictions are often wrong: flagged and dimmed, never silently dropped).
- **Local horizon**: your TheSkyX `.hrz` file (or `az alt` pairs) plus a
  safety margin; a flat minimum altitude as fallback. When a valid horizon
  file exists, it wins.
- **Moon**: warning and score penalty by separation and illumination, never a
  hard filter. A real phase icon, drawn from geometry, sits in the header.
- **Session feasibility**: the dark window over your horizon must cover the
  whole session; the card tells you *"safe start until HH:MM"*.
- **Plate scale**: your camera's pixel size and focal length set the maximum
  trail-free exposure for fast movers, computed per target.

A filter in the header narrows the night to one kind ("only supernovas
today"), Settings holds a permanent whitelist of kinds, and a per-kind cap
keeps one busy source from flooding the view. Up to three **sky-event chips**
(full moon, an opposition, a Jupiter shadow transit…) sit in the header and
jump straight to the sky calendar.

### Chase NEOs and comet candidates

The flow that turns a moving dot into a reported observation:

- The card shows apparent rate (″/min), your **maximum trail-free exposure**,
  the safe window and, for unconfirmed objects, the full preliminary orbit
  with sigmas, drawn as a chart.
- Export **ephemerides** at a configurable step in the formats your planetarium
  software imports (TheSkyX, Cartes du Ciel, CSV), validated with real
  imports, and the **capture sequence** for NINA (JSON), CCDciel (`.targets`,
  validated against a real CCDciel export, calibration frames included) or a
  generic CSV.
- With CCDciel connected: **Point telescope** slews to the *freshly computed*
  position (Horizons interpolated to the minute, not the stale plan), and
  **Astrometric Goto** adds a plate-solve-and-correct cycle that absorbs
  ephemeris error: the reliable route to NEOCPs with large uncertainties.
- The frames come home and the app does the astrometry: it solves the
  reference frame, registers the sequence, stacks it following the object,
  finds the dot, sweeps the velocity and measures every observation twice (on
  its stack and per frame), flagging any disagreement. The result is checked
  against the observations other stations have published and the **MPC
  report** is generated in ADES PSV or 80 columns, with your camera's
  instrument type, ready to send.
- You can also measure in your usual tool (Tycho Tracker or another) and
  **paste the astrometry** into the visit: NightScribe validates every line
  (80-column or ADES PSV, your MPC code, the designation) before it leaves.
- The **motion animation** is the smoking gun, now played in the editor: the
  observation stacks centred on the object, the stars crawling while the
  asteroid stands still. If it stands still in every panel, the detection is
  solid.

### Confirm and follow supernovae

- **Confirmation blink**: import your result FITS (target and coordinates are
  already in the project context) and blink it against a PanSTARRS DR1 g
  reference requested with the *exact* center, pixel scale and rotation of your
  image: aligned by construction (DSS2-red takes over south of −30°). If your
  FITS has no astrometric solution, Astrometry.net solves it (free key).
  Exports: animated GIF, H.264 MP4 and a before/after PNG, with your
  observatory watermark and an optional zoom on the transient.
- **Multi-night follow-up**: a supernova project lives for weeks or months.
  Each visit registers the stacked result per filter and your photometry with
  minimal friction: quick entry (just the magnitude), tolerant paste
  (AstroImageJ, Tycho, CSV) or file import. The **light curve** draws your
  points against the typical templates of each type (Ia, II-P/L, Ib/c, SLSN,
  kilonova), the app computes an indicative campaign analysis and verdict, an
  **evolution animation** shows the fade, an annotated FITS copy carries the
  metadata, and a cadence reminder ("3 nights since your last visit") surfaces
  in the Tonight view when it's time to go back.
- Reference context on request: ZTF points via ALeRCE appear as grey reference
  points under yours, never mixed with your own measurements.
- Export your photometry as **CSV** or **AAVSO EFF** (the AAVSO's extended
  format), with the heliocentric Julian date computed in-app.

### Catch exoplanet transits

Designed so that *anyone dares* to capture their first transit:

- Selection leads with the two real decisions: *"the whole transit fits in
  your night, baselines included"* and *"detectable with your aperture"*
  (ExoClock's minimum-telescope estimate versus yours, as a plain verdict).
- The card tells you **"start capturing at HH:MM UTC"**, the transit plus the
  out-of-transit baseline on both edges, and a **visual timeline** shows
  night, horizon, capture window and milestones at a glance.
- Suggested exposure and maximum cadence (so the ingress is resolved), with
  the readout overhead made explicit, and a warning when the baseline doesn't
  fit. A persistent five-step **pre-flight checklist** walks the capture.
- The reduction is 100 % external: NightScribe exports a **pre-filled
  `inits.json` for EXOTIC** (the NASA/JPL citizen-science pipeline) and guides
  the final submission to ExoClock or the AAVSO Exoplanet Database.

### Variable stars, HADS, campaigns and vigils

- **HADS sessions**: there is no known phase to aim at; the recommendation is
  a continuous capture of 2× the period (cadence ≤ P/12), and the listing gate
  requires a full cycle to fit over your horizon. The catalogue is hybrid:
  P. Wils' Google Sheet (updated daily) merged with a packaged snapshot that
  also works offline. The sheet's color legend feeds the score: stars with
  found or possible period changes, never-observed stars and this month's
  coverage gaps get urgency bonuses. Your run folds by phase into the classic
  saw-tooth, on screen and in PNG.
- **Campaigns**: a campaign is the shared commitment of a group: science
  goal, protocol (cadence, filters, comparison stars), report and data URLs.
  One campaign, many attached projects (deleting the campaign frees them,
  never deletes them). A member is *due* when its last session is
  `cadence_nights` old and lands in the Tonight view automatically; it also lands when
  an **event** is detected or a predicted **extremum** is imminent. The
  Campaigns view is the war room: "Happening now" with ⚡ events, ⏳ upcoming
  extrema and 👁 vigils, per-campaign health cards (members × cadence ×
  events), and full sentences in plain language.
- **Vigils**: your standing watch list, *T CrB eruption watch*, *R CrB fade
  watch*, one star per line, editable in Settings. Each vigil is checked
  against the latest ZTF magnitude versus its baseline (own 12 h cache); for
  stars brighter than ZTF's saturation, it reads the AAVSO community
  photometry with your token.
- **AAVSO channel**: editorial alerts from the AAVSO forum and the active
  observing campaigns, with the star name validated against VSX before it is
  shown. A signal about a star that already is a project merges into that
  project's reasons, never a duplicate row.
- **The variables engine**: VSX extrema predictions with heliocentric Julian
  dates, an event advisor on magnitude jumps (configurable threshold), and
  fold-by-epoch views for periodic stars.

### The Sun and the sky calendar

From the **Tools** menu:

- **The Sun now**: the latest NASA SDO channels (corona at 193/304/171 Å,
  sunspots, magnetogram), the NOAA active-regions map and the indices (sunspot
  number, F10.7 radio flux, Kp, the week's strongest flare), with a
  watermarked PNG panel and a bilingual "the sky today" draft. An "impact on
  your night" line connects it to observing: a bright Moon hurts faint
  targets, a high Kp may mean auroras.
- **Sky calendar**: today + 60 days, computed **100 % locally** (no network):
  true lunar phases, perigee and apogee, Moon–planet and planet–planet
  conjunctions, oppositions and greatest elongations (as ecliptic-longitude
  crossings), **probable eclipses** from shadow-cone geometry, honestly
  labelled as probable, and meteor showers. Validated against astropy and
  published almanacs.
- **Jupiter's moons this week**: Galilean satellite **and shadow** transits
  across the disc, filtered for your site (Jupiter up, at night), at planning
  grade with the "±10 min" label always visible (validated against 22 JPL
  Horizons windows; worst case 9.6 min).

### Drive your observatory (CCDciel)

The **Capture** step of each project talks to your local **CCDciel** over
JSON-RPC, only while CCDciel is actually running: status at a glance (version,
CCD temperature, tracking, slewing), **Point telescope** (quick slew to a
moving target's freshly computed position), **Astrometric Goto** (slew,
capture, plate-solve and correction) and **live capture** (stage the project's
saved plan and start the run).

CCDciel is the first direct observatory integration; NINA and others are on
the roadmap. Meanwhile, file-based sequence export already covers NINA (JSON),
CCDciel itself and generic CSV.

### Reduce and measure in the app (the editor)

Everything the night produced opens in one workbench, the **unified FITS
editor**: the plate with its histogram and stretch, a band that says what the
plate itself knows (position, magnitude, date, exposure, kit, station, scale)
and, hanging from each visit, the frames that came home. The work happens in
tabs, and every figure it shows is explained where it appears.

- **Photometry.** The comparison stars are proposed next to the target (never
  the brightest of the field: they saturate), and the plate is measured with a
  calibrated recipe (aperture or matched filter, sky, colour term, the
  catalogue the zero point stands on). On a whole sequence the **series**
  engine measures one point per frame, with the zero point anchored by a
  comparison every frame, the ensemble of comparisons vetoing an outlier, the
  optimum aperture per night and an honest multi-night detrend; the light
  curve is drawn from it, and it exports as CSV or AAVSO EFF, or straight to
  ExoClock.
- **Period and phase.** Lomb-Scargle (with a floating mean) and PDM, the
  spectral window, the false-alarm probability by bootstrap, how many cycles
  the data really cover, and the folded curve night by night: a period is
  claimed with its evidence, not as a bare number.
- **Calibration.** A library of masters (dark/bias and flat) indexed by
  camera, gain, temperature, exposure and filter, and a declarative recipe:
  the flat is normalised, a dark already carries the bias, and a dark without
  an exact exposure match is not scaled. When the library has no flat for the
  filter, one is built from the dithered frames themselves and the run says
  so. A star that touches the saturation or the linearity does not enter the
  zero point.
- **Astrometry (track & stack).** The sequence becomes MPC observations: the
  reference frame is solved, the frames are registered (small rotation
  included), the sequence is stacked **following the object** so its light is
  concentrated while the stars trail, the dot is detected and the velocity
  swept; each observation is stacked on its own and measured twice (on its
  stack and per frame, the disagreement flagged). The result is checked
  against the observations other stations published (Find_Orb, leave-one-out)
  and the report is generated in ADES PSV or 80 columns, with the
  middle-of-exposure instants, the propagated uncertainties and your camera's
  instrument type. Below the detection gate there is a **manual mode** (mark
  the object by eye on the whole-sequence stack) and the **animation** plays
  the observations in the editor to see the asteroid stand still while the
  stars crawl.
- **Blink and annotate.** Your FITS blinked against a PanSTARRS DR1 g
  reference requested with the exact geometry of your image (animated GIF,
  H.264 MP4, before/after PNG), and an AIJ-compatible annotated copy of the
  plate with the object's position written into the header.

The external tools keep their place: what the app produces is standard FITS,
ADES and AAVSO files, so Tycho Tracker, AstroImageJ, EXOTIC or your own
scripts pick up exactly where it leaves off.

### Remember everything: journal and attention

- **Observing journal** (Tools menu): your diary writes itself: projects
  created and closed, sessions logged, files produced, photometry points,
  campaign activity; grouped by **observing night** (noon-to-noon local, the
  astronomer's day), filterable by kind and searchable. Double-click jumps
  back to the project.
- **Needs your attention**: the app speaks first. The Projects home lists the
  3–5 things asking for action: a campaign member due tonight, a supernova
  overdue for a revisit, an observation never posted; each with its reason in
  plain words and one button that lands exactly where you act. Computed
  locally, no network.
- Your activity feeds back into the planner: the suggestion engine knows what
  you already observed or posted, and the Tonight list reflects it.

### Understand any object

**The "Explore an object…" box in the top bar** (type a name, press Enter) or
**Tools → Explore object…** (or click any target): identity and physical data
cross-matched from JPL SBDB, Horizons and CAD, SIMBAD, TNS and the NASA
Exoplanet Archive, rendered as a calling card:

- A **hook line** and outreach bullets, in Spanish and English.
- A **parameter table where every row is explained** in plain language:
  orbital family, MOID (the minimum distance the orbit ever gets to Earth's),
  size estimated from the absolute magnitude, next close approach, discovery
  date… Multiline, nothing truncated.
- **Charts**: the orbit (animated by date, with hover readouts), the night sky
  with *your* horizon silhouette and the safe window shaded, the survey field,
  the light curve. In the app they are live vector graphics (zoom, pan,
  hover); the same engines render the PNGs.
- **Capture chips**: current magnitude, apparent rate, max trail-free
  exposure, window and hours above the horizon; plus copyable coordinates
  (decimal and sexagesimal) with their epoch.

### Tell the world

The last step of every project is telling it, if you feel like it: bilingual
drafts (ES/EN) and a tweet written with the real session data (date, N×t,
filter), plus the chart inventory already generated: orbit view, night sky
with your horizon, survey field, light curve against templates, transit
timeline, Sun panel, supernova blink and before/after, NEO motion trail.
Copy, paste, done.

## Where the data comes from

Every external source, what it gives you, how fresh it is, and whether it
needs a key. All network access goes through an **SQLite cache with per-source
TTLs** (the refresh column): repeat queries are instant and free for the
service. If a source is down, the rest of the app never breaks; the sources
are listed under **Help → About NightScribe**.

**Planning sources (feed Tonight):**

| Source | What it gives you | Refresh | Key? |
|---|---|---|---|
| NEOfixer (U. Arizona) | Site-specific NEO list: score, priority, cost, magnitude, rate, uncertainty, NEOCP/impact/radar/NHATS flags; preliminary orbits with sigmas for unconfirmed objects | 12 h (orbits 1.5 h) | No (only for the optional community report) |
| MPC (PCCP) | Possible comets awaiting confirmation, with comet-score | 6 h | No |
| COBS | Live comet magnitudes, perihelion, activity | 6 h | No |
| Rochester Astronomy | Recent supernova discoveries | 6 h | No |
| ExoClock (ESA Ariel) | ~776 exoplanet transit ephemerides: depth, duration, priority, O-C drift, minimum telescope | 24 h | No |
| ESA NEOCC | Upcoming close approaches: miss distance, size, peak magnitude | 6 h | No |
| HADS sheet (P. Wils / VVS) | The living high-amplitude δ Scuti catalogue with color-coded priorities and monthly coverage (packaged snapshot as offline fallback) | 12 h | No |
| AAVSO VSX | Variable star identity: type, period, epoch, extrema | 7 d | No |
| AAVSO forum & campaigns | Editorial alerts and active observing campaigns | 12 h | No |
| ALeRCE / ZTF | Latest magnitude for your vigils | 12 h | No |
| AAVSO photometry | Community measurements for bright vigils | 12 h | Yes (free token) |

**Object data (feed the cards):**

| Source | What it gives you | Refresh | Key? |
|---|---|---|---|
| JPL SBDB | Identity, orbital class, elements, MOID, physical parameters (H, size, rotation, albedo, spectral class) | 7 d | No |
| JPL Horizons | Precise ephemerides topocentric to *your* MPC code | 12 h | No |
| JPL CAD | Next close approaches | 7 d | No |
| SIMBAD (CDS) | Transients and host galaxies (Harvard mirror as fallback) | 7 d | No |
| TNS | Fresh transient positions, days before SIMBAD ingests them | 6 h | No (only for discovery images) |
| NASA Exoplanet Archive | Planet period, radius, mass, host star | 7 d | No |
| VizieR (CDS) | Star fields for the comparison sequences and the astrometric references (Gaia EDR3, APASS DR9, VSX) | 30 d | No |
| MPC Observations API | What other stations have published about the object, for the check before sending | 6 h | No |
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
whole 60-day sky calendar and Jupiter's moon events. And the **reduction
itself**: the registration, the stack, the astrometric and photometric
measurement, the series, the period search and the light curve are arithmetic
on your own pixels, with no service involved. Images are credited (NASA/SDO,
PanSTARRS, DSS); external websites (SolarMonitor, ETD, NEOfixer, TNS…) open in
your browser, never embedded.

## Optional integrations

Everything below is optional; each missing piece degrades gracefully and tells
you so. Configure them in **Tools → Settings → Integrations**.

| Integration | What it unlocks |
|---|---|
| **CCDciel** (local, host/port) | The Capture step of each project: status, point telescope, astrometric goto, staging the saved plan, live capture. Only while CCDciel is running. First observatory integration; NINA and others are planned |
| **NEOfixer API key** | Report `will_observe` / `observed` back for community coordination |
| **Astrometry.net key** (free) | Blind solve of WCS-less FITS in the blink |
| **TNS bot credentials** | Discovery images shown inside the app (respecting each survey's licence) |
| **AAVSO API token** | Community photometry for the bright-star vigils |
| **AAVSO observer code** | Filled into the photometry exports and the EXOTIC handoff |
| **Find_Orb** (external binary) | The check of your astrometric measurement against the observations other stations published, before the MPC report. Without it the check is not available, and the app says so instead of pretending |
| **EXOTIC** (external Python 3.10 or older) | The transit reduction: the app writes the handoff, runs EXOTIC for you and imports its light curve and parameters into the project. Without it the handoff is still yours to run by hand |

## Your data stays with you

Everything NightScribe knows lives in a local **SQLite** database in your
user's data directory: the HTTP cache, your projects, sessions, photometry,
campaigns and settings. Each project gets its own **container folder** (plans,
sequences, reports, charts, posts) under a root you choose and can change
later. No accounts, no cloud, no telemetry. Uninstall and delete the folder:
nothing remains anywhere else.

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
| `sequence <object>` | photometric sequence + finder chart (`--mag`, `--fov`, `--comps`, `--catalog gaia/apass`, `--fits` as background) |
| `history` | the observing journal in the terminal |
| `project …` | minimal project management: `list`, `create`, `advance`, `show`, `close`, `reopen`, `files` |
| `inject <folder>` | injection and recovery: synthetic sources of a known brightness are added to a copy of your frames and measured back, to say how deep the pipeline really reaches |

See [INSTALL.md](INSTALL.md) for full per-OS instructions, the pip package and
the standalone installer, and [CONTRIBUTING.md](CONTRIBUTING.md) to hack on
it.

## Documentation

**The [user guide](docs/user/README.md)** ([español](docs/user/README.es.md))
walks the whole cycle, from the first run to the MPC report, in short
chapters with the "why" of each option. It is published as a website:
**<https://irydeo.github.io/nightscribe/>** (**Help → User guide (web)**).

Design, architecture, data sources, scoring, workflows and every decision
(ADRs) live in [`docs/`](docs/), in Spanish and English.

Something missing, wrong or unclear? [Open an issue](https://github.com/irydeo/nightscribe/issues).

## Licence

NightScribe is free software, published under the
[GPL v3](https://github.com/irydeo/nightscribe/blob/main/LICENSE): you can use
it, study it, change it and share it, and whatever you pass on stays free for
the next person. There is no paid edition and no locked feature.
