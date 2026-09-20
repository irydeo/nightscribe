############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - HADS stars module (High-Amplitude delta Scuti)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""HADS stars: catalog access, online merge and session maths.

A HADS is a high-amplitude delta Scuti star: it pulsates every ~1-5 h with
a >= 0.3 mag swing, so a full light curve fits in a single night and you
watch the star pulsate live. Unlike exoplanet transits there is NO known
phase in the catalog: we know how long the cycle lasts, not when the
maximum happens — so the advice is a continuous 2-period capture (see it
repeat, then fold), never an "event" (ADR-034, decision H-a).

Hybrid source (H-j): the bundled snapshot (assets/HADS-stars.csv, with the
rich aliases) is overlaid with Patrick Wils' live Google Sheet (priority
colors + monthly coverage, cached 12 h by sources/hads_sheet.py). Offline,
the snapshot alone keeps everything working. Legend of the sheet: red name
= period changes found (priority!), orange = possible (priority!), blue
coordinates = not yet observed, purple name = multiperiodic (observe on
consecutive nights).
"""

import csv
import logging
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from . import coords, exposure
from .sources import hads_sheet

logger = logging.getLogger(__name__)

# Bundled vector/data assets live next to moon_disk.png (theme.py pattern)
_ASSETS = Path(__file__).resolve().parent.parent / "assets"
BUNDLED_CSV = _ASSETS / "HADS-stars.csv"

# Session constants (ADR-034): watch it repeat, then fold
POINTS_PER_CYCLE = 12          # AAVSO: resolve the curve
CADENCE_CAP_S = 900.0          # AAVSO: one image at least every 15 min
SESSION_CYCLES = 2             # recommended capture: two full periods

# Famous prototypes of the class, all present in the bundled catalog
FAMOUS_HADS = ("CY Aqr", "DY Peg", "SZ Lyn", "XX Cyg", "V2455 Cyg", "AD CMi")

# Merge tolerance: same star when closer than one arcminute
_MATCH_DEG = 1.0 / 60.0

_FLAG_RE = re.compile(r"multiperiodic|non-radial|change in amplitude", re.I)


# ---------------- bundled catalog ----------------

def _parse_name(raw):
    # Splits a catalog Name cell into primary name, aliases and flags.
    # Forms seen: "V965 Cep = GSC 4500-0083 (=NSVS 304708), multiperiodic?",
    # "LR Psc (=GSC 0612-0771=ASAS J010618+0846.2)",
    # "GSC 7015-0399 (=ASAS J025743-3351.6) -- Non-radial"
    # @return: (primary, aliases, multiperiodic, non_radial, amp_change)
    multi = "multiperiodic" in raw.lower()
    non_radial = "non-radial" in raw.lower()
    amp_change = "change in amplitude" in raw.lower()
    cleaned = re.sub(r"\s*--.*$", "", raw)            # tail after "--" = flags
    cleaned = re.sub(r",?\s*(multiperiodic[?!]?)", "", cleaned, flags=re.I)
    aliases = []
    for grp in re.findall(r"\(([^)]*)\)", cleaned):   # "(=A=B)" -> A, B
        for part in grp.split("="):
            part = part.strip()
            if part and not _FLAG_RE.search(part):
                aliases.append(part)
    base = re.sub(r"\([^)]*\)", "", cleaned)          # drop parens groups
    parts = [p.strip() for p in base.split("=") if p.strip()]
    primary = parts[0] if parts else cleaned.strip()
    aliases += [p for p in parts[1:] if not _FLAG_RE.search(p)]
    return primary, aliases, multi, non_radial, amp_change


@lru_cache(maxsize=1)
def catalog_bundled():
    # The packaged snapshot: 168 stars with rich aliases. Immutable in
    # runtime, so it is parsed once per process.
    # @return: list of dicts {name, aliases, ra_deg, dec_deg, max, min,
    #          period_h, multiperiodic, non_radial, amp_change,
    #          priority: None, observed: True, coverage: {}}
    out = []
    with open(BUNDLED_CSV, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                primary, aliases, multi, non_radial, amp_change = \
                    _parse_name(row["Name"])
                out.append({
                    "name": primary, "aliases": aliases,
                    "ra_deg": coords.ra_hms_to_deg(row["RA"]),
                    "dec_deg": coords.dec_dms_to_deg(row["DEC"]),
                    "max": float(row["Max"]), "min": float(row["Min"]),
                    "period_h": float(row["Period_h"]),
                    "multiperiodic": multi, "non_radial": non_radial,
                    "amp_change": amp_change,
                    "priority": None, "observed": True, "coverage": {}})
            except (ValueError, KeyError, AttributeError) as err:
                logger.debug("skipping malformed HADS row: %s", err)
    return out


def lookup(name):
    # @args: name - user-typed identifier (case/space tolerant)
    # @return: the bundled catalog entry matching the name or any alias,
    #          or None. Bundle-only on purpose: Explore works offline
    n = " ".join(name.casefold().split())
    for star in catalog_bundled():
        names = [star["name"]] + star["aliases"]
        if any(" ".join(x.casefold().split()) == n for x in names):
            return star
    return None


# ---------------- online merge ----------------

def catalog(merge_online=True):
    # The working catalog: bundled snapshot overlaid with the live sheet.
    # @args: merge_online - False forces the pure snapshot (tests, offline)
    # @return: list of star dicts; the online overlay brings period/max/min,
    #          priority, observed and coverage; the bundle keeps the names,
    #          aliases and text flags. Not memoized on purpose: the merge is
    #          cheap (168x168) and a long-running GUI must respect the cache
    #          TTL of the live layer
    base = [dict(s) for s in catalog_bundled()]   # copy: the overlay mutates
    if not merge_online:
        return base
    live = hads_sheet.parsed()
    if not live:
        return base
    for ls in live.get("stars", []):
        try:
            ra = coords.ra_hms_to_deg(ls["ra"])
            dec = coords.dec_dms_to_deg(ls["dec"])
        except (ValueError, AttributeError, TypeError) as err:
            logger.debug("skipping sheet star %r: %s", ls.get("sheet_name"),
                         err)
            continue
        best, best_d = None, _MATCH_DEG
        for b in base:
            d = coords.angular_separation(ra, dec, b["ra_deg"], b["dec_deg"])
            if d < best_d:
                best, best_d = b, d
        coverage = {year: cov.get(ls["sheet_name"], [])
                    for year, cov in live.get("coverage", {}).items()}
        if best is None:
            base.append({
                "name": ls["sheet_name"], "aliases": [],
                "ra_deg": ra, "dec_deg": dec,
                "max": ls.get("max"), "min": ls.get("min"),
                "period_h": ls.get("period_h"),
                "multiperiodic": bool(ls.get("multiperiodic_sheet")),
                "non_radial": False, "amp_change": False,
                "priority": ls.get("priority"),
                "observed": ls.get("observed", True),
                "coverage": coverage})
            continue
        for key in ("period_h", "max", "min"):
            if ls.get(key) is not None:
                best[key] = ls[key]          # the sheet is fresher (H-j)
        best["priority"] = ls.get("priority")
        best["observed"] = ls.get("observed", True)
        if ls.get("multiperiodic_sheet"):
            best["multiperiodic"] = True
        best["coverage"] = coverage
    return base


# ---------------- session maths ----------------

def derive(star, hours_up, plate_scale_arcsec_px=None):
    # Derived per-night values for one star.
    # @args: star - catalog dict, hours_up - hours above the local horizon
    #        tonight, plate_scale_arcsec_px - camera/telescope scale or None
    # @return: {amp, mag_med, cycles, cadence_s, session_req_h, exp_s}
    #          (mind the inverted magnitude axis: Min - Max > 0)
    amp = star["min"] - star["max"]
    mag_med = (star["max"] + star["min"]) / 2
    period_h = star["period_h"]
    cycles = hours_up / period_h if hours_up and period_h else 0.0
    cadence_s = min(period_h * 3600 / POINTS_PER_CYCLE, CADENCE_CAP_S)
    return {
        "amp": round(amp, 2),
        "mag_med": round(mag_med, 2),
        "cycles": round(cycles, 1),
        "cadence_s": cadence_s,
        "session_req_h": SESSION_CYCLES * period_h,
        "exp_s": exposure.recommended_transit_exposure(mag_med,
                                                       plate_scale_arcsec_px),
    }


def span_hours(window_start_iso, window_end_iso):
    # @return: hours between two ISO timestamps, or None when either is None
    if not window_start_iso or not window_end_iso:
        return None
    try:
        return (datetime.fromisoformat(window_end_iso)
                - datetime.fromisoformat(window_start_iso)).total_seconds() / 3600
    except ValueError:
        return None


def covered_this_month(star, when=None):
    # @args: star - catalog dict with "coverage" {year_str: [months]},
    #        when - datetime/date (default: now UTC)
    # @return: True/False, or None when the current-year tab is missing
    #          (early January before Wils creates it: no bonus, no penalty)
    when = when or datetime.now(timezone.utc)
    year_cov = star.get("coverage", {}).get(str(when.year))
    if year_cov is None:
        return None
    return when.month in year_cov


# ---------------- schematic light curve ----------------

def sawtooth_template(period_h, amp, mag_med, rise_frac=0.35, n=40):
    # Normalized sawtooth: fast rise to maximum light, slow decline — the
    # classic HADS/"dwarf Cepheid" shape. SCHEMATIC, never real data: it is
    # drawn only as a reference under the folded observations. Kind-agnostic
    # on purpose (the future variables track will reuse it, H-n).
    # @args: period_h - pulsation period (unused in the shape, carried for
    #        the caller's labels), amp - peak-to-peak amplitude in mag,
    #        mag_med - median magnitude, rise_frac - fraction of the cycle
    #        spent rising, n - number of points
    # @return: list of (phase 0..1, mag) — faintest at phase 0/1, brightest
    #          at phase == rise_frac (inverted magnitude axis!)
    faint, bright = mag_med + amp / 2, mag_med - amp / 2
    out = []
    for i in range(n + 1):
        p = i / n
        if p <= rise_frac:
            mag = faint - amp * (p / rise_frac)
        else:
            mag = bright + amp * ((p - rise_frac) / (1 - rise_frac))
        out.append((p, round(mag, 4)))
    return out
