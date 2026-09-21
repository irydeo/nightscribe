# NightScribe — Data Sources

*[Versión en español](DATA_SOURCES.es.md)*

Every external source used by NightScribe, one module per source under
`core/sources/`. All verified working on 2026-08-21. Network access always goes
through the SQLite HTTP cache (`core/db.py`) with the TTL listed below.

## Planning sources (feed "Tonight")

### NEOfixer — `neofixer.py` — primary NEO source

- `GET https://neofixerapi.arizona.edu/targets/?site=<MPC code>&num=N` — public,
  JSON-RPC. Site-specific target list with score, priority, cost (minutes), vmag,
  rate, uncertainty, NEOCP flag, impact/radar/NHATS/Yarkovsky flags.
- `GET .../ephem/?site=<code>&object=<packed>` — public. Site-specific ephemeris
  (alt, az, mag, motion) precomputed by NEOfixer (Bill Gray's find_orb).
- `GET .../orbit/?object=<packed>` — public. **Preliminary orbital elements** for
  unconfirmed (NEOCP) objects, computed with Find_Orb from MPC astrometry: full
  Keplerian elements (`a, e, q, Q, i, asc_node, arg_per, M, Tp, epoch`) with
  per-element sigmas, per-planet MOIDs, `p_NEO`, residual count and observed arc.
  Normalised by `parse_neofixer_orbit()` into the SBDB shape (ADR-023); feeds the
  orbit chart, the params table (with sigmas) and the local ephemeris fallback in
  `core/ephemeris.py`.
- `GET .../report/?key=<api key>&site=<code>&object=<id>&status=<s>` — **requires
  the user's API key** (Settings). Reports `will_observe`/`observed`/... for
  community coordination. Optional.
- TTL: 12 h (`targets`, `ephem`); 1.5 h (`orbit` — preliminary orbits change fast).
  Note: `object` must be a *packed* designation.

### Rochester Astronomy (David Bishop) — `rochester.py` — recent supernovae

- `https://www.rochesterastronomy.org/snimages/sndate.html` — public HTML table,
  parsed with lxml (column layout as in legacy `saas/supernova.py`).
- TTL: 6 h. Handle with care: it is a one-man site, be a good citizen (cache!).

### COBS — `cobs.py` — active comets

- `https://cobs.si/api/comet_list.api` — public JSON: current observed magnitude,
  perihelion date/magnitude, activity flag, type (C/P/N), MPC name.
- TTL: 6 h.

### MPC PCCP — `pccp.py` — possible comets

- `https://www.minorplanetcenter.net/iau/NEO/pccp_tabular.html` — public HTML table:
  temporary designation, comet-score (0–100), RA/Dec, V, arc, notes.
  No JSON endpoint exists; parsed with lxml.
- TTL: 6 h.

### ESA NEOCC — `esa_neo.py` — upcoming close approaches (alerts)

- `https://neo.ssa.esa.int/PSDB-portlet/download?file=esa_upcoming_close_app` —
  public fixed-width text: object, date, miss distance (km/AU/LD), diameter, H,
  max magnitude, relative velocity.
- TTL: 6 h. (The ESA priority list endpoint answers 200 with an empty body as of
  2026-08; kept with graceful degradation.)

### ExoClock (ESA Ariel) — `exoclock.py` — exoplanet transits

- `https://www.exoclock.space/database/planets_json` — public JSON, ~776 planets:
  transit ephemeris (`ephem_mid_time`, `ephem_period`), depth (mmag), duration,
  priority, `min_telescope_inches`, O-C drift, star magnitude, coordinates.
- TTL: 24 h. Transit times are computed locally (t0 + n·P) — see `core/transits.py`.

### HADS catalogue (P. Wils / VVS) — `hads_sheet.py` — high-amplitude δ Scuti stars

- `https://docs.google.com/spreadsheets/d/1oGA2HaEHE8L6eX19ZoHqQQTu0LYV56HX3Srg7oCtOHo/export?format=xlsx`
  — public Google Sheets workbook (one tab per year, updated daily by the
  programme coordinator): star name (with aliases), RA/Dec, Max/Min magnitudes,
  period (h), **font-color priorities** (red/orange name = period changes
  found/possible — priority!; blue coordinates = not yet observed; purple name
  = multiperiodic) and the monthly observer-coverage cells.
- TTL: 12 h, two-level cache (raw XLSX + parsed JSON). Parsed with stdlib
  `zipfile`+`xml.etree` (no openpyxl at runtime). The bundled snapshot
  `assets/HADS-stars.csv` (168 stars, rich aliases) is the offline fallback;
  the merge lives in `core/hads.py` (ADR-034).

### AAVSO VSX — `vsx.py` — variable stars (Track V, ADR-035)

- `GET https://vsx.aavso.org/index.php?view=api.object&ident=<name>&format=json`
  — public Variable Star Index API. **Note: the `www.aavso.org` domain sits
  behind a Cloudflare challenge that blocks plain clients; the
  `vsx.aavso.org` subdomain answers a clean 200** (verified 2026-09-11).
  Extracted: name + AUID, RA/Dec, variable type, period (d), epoch (JD→MJD in
  the parser), Max/Min with band, spectral class, constellation.
- TTL: 7 d. **Degradation**: `lookup()` returns `None` on unknown/failure →
  card via SIMBAD (coordinates) → manual entry; Tonight is local and never
  breaks.

### ALeRCE ZTF API v1 — `surveys.py` — light-curve context (V-f)

- `GET https://api.alerce.online/ztf/v1/conesearch?_ra=..&_dec=..&_radius=..`
  and `GET .../lightcurve?oid=<oid>` — two cached calls per object (oid →
  light curve). Grey reference points `source="survey:ztf"` under the
  observer's own, never mixed (ZTF g/r/i bands mapped to filters). Verified
  2026-09-11.
- TTL: 30 d for the light-curve context (survey photometry does not
  change). The **vigils** (ADR-037) reuse the same calls under `vigils:*`
  keys with a 12 h TTL: a watch needs the *latest* point, not the context.
  Failure → `[]`/`None`; the survey button warns and nothing else breaks.

### AAVSO editorial channel — `aavso.py` — forum alerts + campaigns (SC4b)

- `GET https://forums.aavso.org/c/observing/alerts/50.json` — the forum is
  Discourse and serves native per-category JSON (spike validated
  2026-09-16: titles like "SU Tau is dimming", "T CRB Johnson V scores
  below 8.5"). Topics with activity in the last 60 days are listed (the
  pinned "About" post is discarded).
- `GET https://apps.aavso.org/v2/campaigns/` — the observing-campaigns
  list page (HTML); rows `<tr>` are parsed with the stdlib (id+link |
  title | requester | start | end | kinds) and filtered to active ones
  (start ≤ today ≤ end).
- The star name is extracted from the free-text title with tolerant
  patterns (`Nova Sgr 2026 No. 3`, `NSV 11664`, designation + genitive
  like `SU Tau` / `T CRB`) and **validated via VSX** before anything is
  shown: what does not resolve is not shown. TTL: 12 h. Failure → `[]`.
- **Community photometry (bright vigils, SC4a rev. 2)**:
  `GET https://apps.aavso.org/v2/api/observations/photometry/?target=<star>&start_date=..&end_date=..`
  — official endpoint (docs.aavso.org), **requires the user's API token**
  (`Authorization: Token …`, 401 without it; configured in Settings next
  to the observer code). It is the backend of vigils with a baseline
  under 11.5 mag: ZTF saturates there (verified 2026-09-16: T CrB/R CrB
  have no ALeRCE object). Fields used: `jd_dbl`, `magnitude`, `band`
  (DRF-paginated or bare list; tolerant parsing). TTL: 12 h. No token →
  `None`, silent by design.

## Object data sources (feed "Explore" and "Post")

### JPL SBDB — `sbdb.py` — small-body identity and physical data

- `GET https://ssd-api.jpl.nasa.gov/sbdb.api?sstr=<name>&phys-par=1` — public JSON:
  fullname, `kind` (asteroid/comet), orbit class, elements (a, e, i, q, Q, per...),
  MOID, and physical parameters (H, diameter, rotation, albedo, spectral class;
  M1/K1 for comets). TTL: 7 d.

### JPL Horizons — `horizons.py` — precise ephemerides

- `GET https://ssd.jpl.nasa.gov/api/horizons.api?...` — public. `CENTER` accepts MPC
  observatory codes directly (e.g. `'Z41'`). QUANTITIES used: `1` (RA/Dec),
  `4` (apparent az/el), `19` (heliocentric range), `20` (observer range).
  TTL: 12 h.

### JPL CAD — `cad.py` — close approaches

- `GET https://ssd-api.jpl.nasa.gov/cad.api?des=<des>&date-min=..&date-max=..` —
  public JSON: approach date, distance (AU), relative velocity. TTL: 7 d.

### SIMBAD (CDS) — `simbad.py` — transients and host galaxies

- `POST https://simbad.cds.unistra.fr/simbad/sim-script` — public script interface.
  Queries: `query id <name>` (otype, coordinates, V flux), `query around <name>
  radius=<r>` (host galaxy candidates with redshift via `%RV`). TTL: 7 d.
  Fallback: on a network failure the same script is retried once against the
  Harvard mirror (`https://simbad.harvard.edu/simbad/sim-script`) — heavy
  `query around` scripts regularly exceed the 40 s read timeout on Strasbourg
  while the mirror answers 3x faster (measured 2026-09); `around` scripts get
  60 s, `id` scripts 40 s.

### TNS (Transient Name Server) — `tns.py` — freshest transient positions

- `GET https://www.wis-tns.org/object/<name>` — public object page (HTML), parsed
  with lxml: the `field-radec` block carries J2000 coordinates in decimal degrees
  plus type/discovery magnitude/date. No credentials needed; one cached fetch per
  object, TTL 6 h — be a good citizen. First resolver for the blink feature
  (ADR-018): fresh transients appear on TNS days before SIMBAD ingests them.
  (The official bot API remains available once `tns_bot_name`/`tns_bot_key` are
  wired in.)

### Astrometry.net (nova) — `astrometry.py` — blind plate solving

- `POST /api/login` + `POST /api/upload` + poll `/api/submissions/<id>` and
  `/api/jobs/<id>` + `GET /wcs_file/<jobid>` — requires the user's free API key
  (`astrometry_key` in Settings). Used by the blink feature when the user's FITS
  has no WCS (ADR-018). The solved WCS cards are cached by file hash (TTL 30 d):
  the same image is never re-solved.

### NASA Exoplanet Archive — `exoplanet_archive.py` — exoplanet details

- TAP sync query (`https://exoplanetarchive.ipac.caltech.edu/TAP/sync`,
  `format=json`) on `pscomppars`: period, radius, mass, equilibrium temperature,
  system distance, host star. TTL: 7 d.

### VizieR (CDS) — `vizier.py` — catalog photometry for sequences (ADR-042)

- `GET https://vizier.cds.unistra.fr/viz-bin/asu-tsv?-source=<cat>&-c=<ra>+<dec>&
  -c.r=<arcmin>...` — TSV cone search over the catalogs: **Gaia EDR3**
  (`I/350/gaiaedr3`: G/BP/RP plus errors), **APASS DR9** (`II/336/apass9`: direct
  B,V and g′r′i′) and **AAVSO VSX** (`B/vsx/vsx`: type, period, max/min) for the
  field's variable cross-match. Feeds the photometric sequences and comparison
  charts (the follow-up's "with what do I compare?" question).
- Tolerant parsing (SecFot's pattern): an explicit column list is requested
  first; when a probed column is missing the query is repeated with `-out.all`
  and the richer answer wins, so a renamed column breaks nothing.
- TTL: 30 d (reference photometry is quasi-static). Failure → `None`; the user
  gets the honest notice and nothing else breaks.

## Sun and environment

### NOAA SWPC — `noaa.py`

- `services.swpc.noaa.gov/json/solar-cycle/observed-solar-cycle-indices.json` (SSN, F10.7)
- `.../products/noaa-planetary-k-index.json` (Kp)
- `.../json/solar_regions.json` (active regions — feeds our own sunspot map)
- `.../json/goes/primary/xrays-7-day.json` (X-ray flux → flare classes)
- All public JSON. TTL: 1 h.

### SILSO (SIDC, Royal Observatory of Belgium) — `silso.py`

- Sunspot number series for cycle context. Public data with credit. TTL: 24 h.

### NASA SDO — `sdo.py`

- `https://sdo.gsfc.nasa.gov/assets/img/latest/latest_1024_<channel>.jpg`
  (0193, 0304, HMII, ...). Public domain images with credit
  ("Courtesy of NASA/SDO and the AIA, EVE, and HMI science teams"). TTL: 1 h.

## Images

### Cutouts — `cutouts.py` — reference fields for supernovae

- DESI Legacy Survey: `https://www.legacysurvey.org/viewer/jpeg-cutout?ra=..&dec=..`
  (colour, pretty). CDS hips2fits: `https://alasky.cds.unistra.fr/
  hips-image-services/hips2fits?...` (DSS colour, Pan-STARRS). Both public services.
- **Blink reference (ADR-018)**: hips2fits `hips=CDS/P/PanSTARRS/DR1/g`, FITS format,
  requested at the exact celestial centre, pixel scale and rotation of the user's
  image (`rotation_angle` parameter) so both images align by construction. Fallback
  `CDS/P/DSS2/red` when dec < −30° (outside PS1 3π coverage). Attribution in exports:
  "PanSTARRS DR1 g (CDS hips2fits)" / "DSS2-red (CDS hips2fits)".
- TTL: 30 d (reference fields do not change).

### Discovery images (TNS) — optional, in-app only

- TNS object pages show survey discovery images; automated access requires the
  user's TNS bot credentials (Settings). Shown **inside the app** as reference;
  only reused in posts when the survey licence allows it (ZTF/ATLAS with credit).
  Otherwise we link to the TNS object page. See ADR-016.

## External links (never embedded — copyright)

Raben solar maps, SolarMonitor, SIDC/uset, universemonitor, ETD (var.astro.cz),
NEOfixer web, TNS web. The app opens them in the browser.

## Local ephemerides

Sun, Moon and planets: Paul Schlyter's low-precision algorithms
(`core/ephem_minor.py`) — pure math, arcminute accuracy, offline. Minor bodies:
Kepler propagation from SBDB elements. See ADR-009.

Moon *surface* (the phase icon only, no ephemeris): one bundled photograph,
`nightscribe/assets/moon_disk.png` — Gregory H. Revera, "FullMoon2010",
Wikimedia Commons, CC BY-SA 3.0 (full credit in `assets/ATTRIBUTION.txt`).
Generated once at dev time; the app needs no network for it.
