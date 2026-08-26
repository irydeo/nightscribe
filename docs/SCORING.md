# NightScribe — Suggestion Engine & Scoring

*[Versión en español](SCORING.es.md)*

The suggestion engine (`core/suggest.py`) turns five heterogeneous target lists into
one answer: **"these are your best targets tonight, and here is why"**. Everything is
plain, testable rules — no machine learning, no magic.

## Unified score: 0–100

Each target gets a score built from four weighted families:

| Family | Weight | What it measures |
|---|---|---|
| Scientific priority | 0–35 | NEOfixer score (NEOs), brightness+freshness (SNe), activity/perihelion (comets), PCCP score, ExoClock priority + O-C drift (transits) |
| Observability | 0–30 | Max altitude tonight, hours above min altitude, magnitude vs. user limits, Moon interference, transit coverage % |
| Urgency | 0–20 | NEOfixer urgency, short arc, days since discovery, perihelion imminence, ephemeris degradation (O-C) |
| Outreach hook ★ | 0–15 | "How good a story is this?" — our differentiator |

★ Outreach bonuses (stacked, capped at 15):

- NEO: NEOCP listed, potential impactor (Sentry), radar/NHATS target,
  MOID < 0.05 AU, predicted approach < 10 LD soon.
- Comet: dynamically new (first visit), perihelion within days, outburst detected
  (observed mag ≫ M1/K1 prediction), brighter than 12 ("binoculars!").
- Supernova: brighter than 15, famous host galaxy (M51, M101, NGC...), discovered
  within the last week.
- Transit: famous system (HD 209458, TRAPPIST-1, 55 Cnc...), full transit visible,
  high priority for ESA Ariel.
- PCCP: comet score > 50 on the MPC page.

### History feedback

From SQLite (`observations`): targets **observed but not yet posted** get +5 urgency
("you observed it on Tuesday — tell the world!"); targets **already posted** in the
last 30 days lose the outreach bonus (novelty decay).

## Top N with kind diversity

`top_n` first picks the best target **of each kind** (NEO, SN, comet, PCCP,
transit) and then fills the remaining slots with the next best scores. A night
with a NEO, a comet and a transit beats three NEOs — both scientifically and
for the audience.

Per-object details shown in the app: **NObs** (accumulated observations: more
means a more reliable orbit — a quick reality check for NEO candidates) and
**Discovered** (discovery date for transients; approach date for close-approach
alerts).

## "Why tonight" phrases

One generated one-liner per top target, ES + EN. Rule-based in `narrative.py`: the
first matching rule wins, so phrases are specific, not generic. Examples:

- NEOCP: *"On the MPC confirmation page: every measurement counts for its orbit."*
- Short arc: *"Single-opposition arc: this week is the window before it is lost."*
- Fresh SN: *"Discovered 6 days ago and still rising; its light has travelled
  55 million years."*
- PCCP: *"Comet score 85/100 on the MPC's PCCP: your image could confirm it."*
- Transit: *"A planet 1.4× Jupiter eclipses its star by 1.5% for 3 h — your light
  curve helps ESA's Ariel mission."*
- Close approach: *"Passes at 3.2 lunar distances on Thursday: closer than the
  Moon is a story."*

Each card also shows: magnitude, max altitude + time (or transit window), estimated
cost in minutes when known, and action buttons.

## Feasibility filtering

User equipment enters through Settings (telescope aperture, limiting magnitude).
The policy is **hybrid** (ADR-025):

| Family | Policy | Where |
|---|---|---|
| SNe, comets, exoplanets | **Hard cut** — out of reach means out of the list | `sources/rochester.py`, `sources/cobs.py`, `core/transits.py` |
| NEOs, PCCPs | **Soft warning** — the magnitude is a prediction, so we sink the score and flag the card / CLI row; we never drop the target | `core/suggest.py` → `beyond_limit()` |

Targets beyond reach are shown dimmed, never hidden (in the soft case): planning is
about knowing what is up there, even if you cannot take it tonight.

## Testing

Unit tests use synthetic targets with known properties ("a bright NEOCP must outscore
a mag-21 numbered asteroid"); functional tests run the whole engine against live
sources for the configured site.
