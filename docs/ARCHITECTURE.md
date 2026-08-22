# NightScribe — Architecture

*[Versión en español](ARCHITECTURE.es.md)*

## Overview

Layered, boring-on-purpose architecture. The CLI and the GUI are thin shells over the
same core; all expensive work (network, ephemerides) is cached in SQLite.

```
            ┌──────────────┐   ┌──────────────┐
            │  CLI         │   │  GUI (Qt6)   │
            │ __main__.py  │   │ gui/ (.ui)   │
            └──────┬───────┘   └──────┬───────┘
                   │        same core │
        ┌──────────▼──────────────────▼──────────┐
         │  core: planner · suggest · orbits ·     │
         │  solar · transits · enrich · narrative  │
         │  · post · coords · ephem_minor · blink  │
         │  · fits_io · wcs (own FITS/WCS, ADR-018)│
        └──────────┬─────────────────────────────┘
                   │ only sources/ talk to the net
        ┌──────────▼──────────┐    ┌─────────────┐
        │  core/sources/*     │───►│ core/db.py  │  SQLite:
        │  neofixer, sbdb,    │    │ http cache  │  cache + targets +
        │  horizons, cobs...  │    │ (TTL)       │  observations + settings
        └─────────────────────┘    └─────────────┘
                   │
                   ▼
             viz/  (matplotlib: one renderer, GUI canvas + PNG export)
```

## Modules

| Module | Responsibility |
|---|---|
| `nightscribe/__main__.py` | CLI entry: `tonight`, `explore`, `post`, `solar`, `blink`, `history`, `gui` |
| `nightscribe/config.py` | Persistent settings (observatory, aperture, language, API keys); MPC code → coordinates resolution |
| `nightscribe/paths.py` | Per-OS config/data dirs (platformdirs) |
| `core/db.py` | SQLite: `http_cache` (TTL per source), `targets`, `observations`, `settings`. Single access point |
| `core/coords.py` | Sidereal time, alt-az, twilight — pure math, no astropy |
| `core/ephem_minor.py` | Sun/Moon/planets (Schlyter low-precision) + Kepler propagation for minor bodies |
| `core/planner.py` | Builds the night's raw target list from sources |
| `core/suggest.py` | Unified 0–100 score, Top N, "why tonight" phrases (see SCORING.md) |
| `core/orbits.py` | Orbital families + parameter translation (see ORBITS.md) |
| `core/solar.py` | Aggregated Sun state (SSN, regions, flares, Kp, wind) |
| `core/transits.py` | Exoplanet transits: t0 + n·P, night matching, visibility |
| `core/enrich.py` | Object type detection + raw data orchestration |
| `core/narrative.py` | Bilingual ES/EN engaging prose |
| `core/post.py` | Templates → post_ES / post_EN / tweet |
| `core/fits_io.py` | Minimal FITS reader on numpy, no astropy (ADR-018) |
| `core/wcs.py` | Minimal TAN WCS: pixel↔sky, scale, rotation (ADR-018) |
| `core/blink.py` | Supernova blink orchestrator: name → coordinates, geometry-matched PanSTARRS DR1 g pair (ADR-018) |
| `core/sources/*` | One module per external source (see DATA_SOURCES.md) |
| `viz/*` | matplotlib renderers shared by GUI canvas and PNG export |
| `gui/*` | PySide6 shell: `.ui` files (Qt Designer), QThread workers, wizard |

## Data flow — "tonight"

1. `planner` asks sources for raw lists: NEOfixer targets (site = MPC code), Rochester
   supernovae, COBS active comets, MPC PCCP page, ExoClock catalogue.
2. Each raw response is stored in `http_cache` with its TTL; repeat calls are free.
3. Visibility per target: NEOs via NEOfixer `ephem` (site-specific); SNs/comets/PCCP via
   own alt-az math (`coords.py`); transits computed locally (t0 + n·P) then alt-az.
4. `suggest` scores everything 0–100, builds the Top N and the "why tonight" phrases.
5. Observed flags and post history come from SQLite and feed back into the score
   (recently published objects lose novelty; observed-but-unposted gain urgency).

## Data flow — "post"

1. `enrich` detects the object type (regex + SBDB `kind`) and gathers raw data.
2. `orbits` translates parameters; `narrative` writes ES/EN prose; `viz` renders PNGs.
3. `post` fills templates → files + GUI preview. History recorded in SQLite.

## Threading

Network and rendering never run on the GUI thread: `gui/workers.py` (QThread) with
Qt signals back to the UI. The CLI is synchronous.

## Internationalisation

Qt Linguist: every visible string through `self.tr()`; sources in
`gui/i18n/nightscribe_{es,en}.ts`, compiled to `.qm` with `pyside6-lrelease`.
UI language selectable in Settings (default: OS locale). Generated content (posts,
phrases) is always produced in both languages independently of the UI language.

## Persistence

SQLite file in the user data dir (see `paths.py`). Schema versioned with a simple
`PRAGMA user_version` migration ladder. TTLs per source are defined in
`core/db.py` (NOAA 1 h, NEOfixer/ephemerides 12 h, Rochester/COBS/ESA/PCCP 6 h,
SBDB/SIMBAD/CAD/ExoClock 7 d).

## Errors

Human-readable messages, no stack traces in the UI. Network failures degrade
gracefully: a source that fails simply contributes no targets (logged as a warning);
the app never crashes because a website is down.
