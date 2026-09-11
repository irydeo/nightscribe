############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Night planner module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import datetime
import logging
from concurrent.futures import ThreadPoolExecutor

from . import coords, dates, exposure, hads, horizon, transits
from .sources import (cobs, esa_neo, exoclock, horizons, neofixer, pccp,
                      rochester, sbdb)

logger = logging.getLogger(__name__)

# Load-phase order (single source of truth for the build_tonight stages and
# the GUI progress bar total). Scoring is the final phase, emitted by the
# worker after build_tonight returns. The GUI keeps the human labels (they
# must be literal tr() strings so lupdate sees them).
PHASES = ("neo", "sn", "comet", "pccp", "transit", "hads", "approach",
          "scoring")

# Builds the raw list of tonight's targets from every source. Each target is
# a flat dict; scoring lives in suggest.py. A source that fails simply
# contributes nothing (graceful degradation, see ARCHITECTURE).


def build_tonight(cfg, date=None, n_neofixer=40, n_comets=15,
                  session_duration_s=None, on_phase=None):
    # @args: cfg - Config instance, date - datetime.date (tonight, UTC),
    #        n_neofixer - NEOfixer list size, n_comets - brightest comets
    #        to locate, session_duration_s - planned capture session time
    #        when known (the horizon is then sized to contain it, ADR-020),
    #        on_phase - optional callback(idx, key) fired at the start of
    #        each source block; used by the GUI to show per-phase progress
    # @return: list of target dicts
    lat, lon = cfg.get("lat"), cfg.get("lon")
    site = cfg.get("mpc_code")
    limit_mag = float(cfg.get("limit_mag", 20.0))
    hor = horizon.from_config(cfg)
    margin = float(cfg.get("horizon_margin_deg", 0.0))
    targets = []
    stages = (
        (1, "neo",
         lambda: _neo_targets(site, n_neofixer, lat, lon, date, hor, margin,
                              session_duration_s)),
        (2, "sn",
         lambda: _sn_targets(limit_mag, lat, lon, date, hor, margin,
                             session_duration_s, max_days=90)),
        (3, "comet",
         lambda: _comet_targets(limit_mag, lat, lon, site, n_comets, date,
                                hor, margin, session_duration_s)),
        (4, "pccp",
         lambda: _pccp_targets(lat, lon, date, hor, margin,
                               session_duration_s)),
        (5, "transit",
         lambda: _transit_targets(lat, lon, date, hor, limit_mag, margin,
                                  _transit_aperture(cfg),
                                  _transit_plate_scale(cfg))),
        (6, "hads",
         lambda: _hads_targets(lat, lon, date, hor, limit_mag, margin,
                               _transit_plate_scale(cfg))),
        (7, "approach",
         lambda: _approach_alerts()),
    )
    for idx, key, fetch in stages:
        if on_phase:
            on_phase(idx, key)  # GUI: "loading <key>" (i, N progress)
        targets += fetch()
    # keep what is actually up tonight (alerts have no visibility info)
    visible = [t for t in targets
               if t["kind"] == "alert"
               or t.get("window_start") is not None]
    return visible


def visible_now(targets, cfg, when=None, min_alt=None):
    # Targets above the horizon *right now* (not just tonight).
    # @args: targets - list from build_tonight, cfg - Config,
    #        when - UTC datetime (now), min_alt - override threshold (config)
    # @return: list of (target, alt, az) for the ones currently up
    lat, lon = cfg.get("lat"), cfg.get("lon")
    if min_alt is not None:
        hor = horizon.FlatHorizon(min_alt)
        margin = 0.0
    else:
        hor = horizon.from_config(cfg)
        margin = float(cfg.get("horizon_margin_deg", 0.0))
    out = []
    for t in targets:
        if t.get("ra_deg") is None or t.get("dec_deg") is None:
            continue
        alt, az = coords.current_altaz(t["ra_deg"], t["dec_deg"], lat, lon, when)
        if alt >= hor.alt_at(az) + margin:
            out.append((t, round(alt, 1), round(az, 1)))
    out.sort(key=lambda x: -x[1])
    return out


def _visibility(ra_deg, dec_deg, lat, lon, date, hor, margin=0.0,
                duration_s=None):
    # Altitude summary for a fixed RA/Dec tonight against the local horizon.
    # One sample pass feeds the max-altitude, the hours above and the best
    # safe span; the span is the longest contiguous run (still containing
    # the session duration when one is given) and best_time is how to start
    # inside it (ADR-020).
    # @return: dict with max_alt, safe_max_alt, max_time, max_az, hours_up,
    #          window_start/end, safe_window, best_time, latest_safe_start
    samples = coords.samples_tonight(ra_deg, dec_deg, lat, lon, date)
    if not samples:
        return {"max_alt": None, "max_time": None, "max_az": None,
                "hours_up": 0.0, "safe_max_alt": None,
                "window_start": None, "window_end": None,
                "safe_window": None, "best_time": None,
                "latest_safe_start": None}
    t_max, alt_max, az_max = max(samples, key=lambda s: s[1])
    hours = sum(1 for (_t, alt, az) in samples
                if alt >= hor.alt_at(az) + margin) / 6.0
    # window = full span above the horizon (unchanged meaning for the list)
    full = hor.best_span(samples, margin)
    # safe span = the one that still contains the planned session, if any
    safe = hor.best_span(samples, margin, duration_s) if duration_s else None
    # highest altitude actually reachable tonight: best sample inside the
    # full safe span — the raw peak may sit behind a local obstacle and
    # must not advertise an altitude the telescope can never use
    safe_alt = None
    if full is not None:
        f0, f1 = full[0], full[1]
        inside = [alt for (t, alt, az) in samples
                  if alt >= hor.alt_at(az) + margin and f0 <= t <= f1]
        if inside:
            safe_alt = round(max(inside), 1)
    out = {"max_alt": round(alt_max, 1),
           "max_time": t_max.isoformat(),
           "max_az": round(az_max, 1),
           "safe_max_alt": safe_alt,
           "hours_up": round(hours, 1),
           "window_start": full[0].isoformat() if full else None,
           "window_end": full[1].isoformat() if full else None,
           "safe_window": None, "best_time": None,
           "latest_safe_start": None}
    if duration_s and safe is not None:
        s_start, _s_end, s_latest = safe
        # recommended start: centre the session on the peak altitude,
        # clamped so that the whole session stays inside the safe span
        d = datetime.timedelta(seconds=float(duration_s))
        ideal = t_max - d / 2
        best = min(max(ideal, s_start), s_latest)
        out["safe_window"] = "%s|%s" % (s_start.isoformat(), _s_end.isoformat())
        out["best_time"] = best.isoformat()
        out["latest_safe_start"] = s_latest.isoformat()
    elif full is not None:
        # no session planned yet: the highest altitude reached *inside the
        # safe span* is the best time — the raw peak may sit behind a local
        # obstacle, and recommending it would be a safety error (ADR-020)
        f0, f1 = full[0], full[1]
        inside = [(t, alt) for (t, alt, _az) in samples
                  if alt >= hor.alt_at(_az) + margin
                  and f0 <= t <= f1]
        if inside:
            t_best, _ = max(inside, key=lambda s: s[1])
            out["best_time"] = t_best.isoformat()
    return out


def safe_window_for(ra_deg, dec_deg, cfg, duration_s, date=None):
    # The session-safe span for one object given a planned capture duration:
    # the longest run of the night that still clears the local horizon while
    # containing the whole session (ADR-020). Lets the project hub and the
    # narrative reuse the exact same maths as build_tonight.
    # @args: ra_deg/dec_deg - object, cfg - Config (site + horizon),
    #        duration_s - planned session seconds, date - date or None (today)
    # @return: dict {safe_window, best_time, latest_safe_start,
    #               window_start, window_end, fits: bool}, or its "does not
    #               fit" shape when the duration cannot be placed
    import datetime as _dt
    if date is None:
        date = _dt.datetime.now(_dt.timezone.utc).date()
    lat, lon = cfg.get("lat"), cfg.get("lon")
    hor = horizon.from_config(cfg)
    margin = float(cfg.get("horizon_margin_deg", 0.0))
    vis = _visibility(ra_deg, dec_deg, lat, lon, date, hor, margin,
                      duration_s)
    sw = vis.get("safe_window")
    fits = sw is not None
    out = {
        "safe_window": sw,
        "best_time": vis.get("best_time"),
        "latest_safe_start": vis.get("latest_safe_start"),
        "window_start": vis.get("window_start"),
        "window_end": vis.get("window_end"),
        "fits": fits,
        "duration_s": int(duration_s),
    }
    return out


def _disc_date_for(t):
    # Exact discovery date for a NEO (object-card plan, subplan 5c):
    # SBDB's discovery record first (or the orbit's first observation),
    # else the NEOfixer preliminary orbit's earliest observation.
    # @args: t - planner target dict ("name"/"packed" keys)
    # @return: "YYYY-MM-DD" or None
    name = t.get("name") or t.get("packed")
    if not name:
        return None
    body = sbdb.get(name)
    if body and body.get("disc_date"):
        return body["disc_date"]
    orb = neofixer.orbit(t.get("packed") or name)
    if orb:
        return orb.get("disc_date")
    return None


def _fill_disc_dates(targets):
    # Resolves disc_date for each target in a small thread pool: SBDB is
    # one HTTP call per object (cached for a week), so a serial loop
    # would slow Tonight down on a cold cache (same pattern as comets).
    # @args: targets - planner target dicts, mutated in place
    if not targets:
        return
    with ThreadPoolExecutor(max_workers=min(4, len(targets))) as pool:
        found = list(pool.map(_disc_date_for, targets))
    for t, d in zip(targets, found):
        if d:
            t["disc_date"] = d


def _neo_targets(site, n, lat, lon, date, hor, margin, duration_s=None):
    # NEOfixer priority list for the site (see ADR-003).
    out = []
    for t in neofixer.targets(site, n):
        try:
            vis = _visibility(t["ra deg"], t["dec deg"], lat, lon, date,
                              hor, margin, duration_s)
            out.append({
                "id": t.get("packed"), "kind": "neo",
                "name": t.get("provisional") or t.get("packed"),
                "packed": t.get("packed"),
                "mag": t.get("vmag"),
                "ra_deg": t.get("ra deg"), "dec_deg": t.get("dec deg"),
                "nf_score": t.get("score"), "nf_priority": t.get("priority"),
                "nf_cost_min": t.get("cost"), "nf_urgency": t.get("urgency"),
                "neocp": bool(t.get("neocp")), "impact": t.get("impact"),
                "moid": t.get("moid"), "h": t.get("h"),
                "rate_arcsec_min": t.get("rate"),
                "nobs": t.get("obs num"), "arc_days": t.get("arc len"),
                **vis,
            })
        except (TypeError, KeyError) as err:
            logger.debug("skipping NEO target: %s", err)
    _fill_disc_dates(out)
    return out


def _sn_targets(limit_mag, lat, lon, date, hor, margin, duration_s=None,
                max_days=90):
    # Recent supernovae from Rochester (D. Bishop); only fresh ones make it
    # to the night list (the rest would just be noise).
    import datetime
    out = []
    for s in rochester.latest_sne(limit_mag):
        try:
            d = datetime.datetime.strptime(s["date"].split(".")[0], "%Y/%m/%d")
            if (datetime.datetime.now() - d).days > max_days:
                continue
        except (ValueError, AttributeError):
            pass
        try:
            ra = coords.ra_hms_to_deg(s["ra"])
            dec = coords.dec_dms_to_deg(s["dec"])
        except (ValueError, AttributeError):
            continue
        out.append({
            "id": s["name"], "kind": "sn", "name": s["name"],
            "mag": s["mag"], "ra_deg": ra, "dec_deg": dec,
            "sn_type": s["type"], "host": s["host"], "disc_date": s["date"],
            **_visibility(ra, dec, lat, lon, date, hor, margin, duration_s),
        })
    return out


def _comet_targets(limit_mag, lat, lon, site, n, date, hor, margin,
                   duration_s=None):
    # Brightest active comets from COBS; position via Horizons (cached).
    # The per-comet ephemeris is the slow network part, so it runs in a small
    # thread pool (each comet queries a different object) while the cheap
    # visibility maths stay sequential.
    def fetch(name):
        # @return: first Horizons row for the comet (may be None)
        rows = horizons.ephemeris(name, center=site)
        return rows[0] if rows else None

    comets = list(cobs.active_comets(limit_mag)[:n])
    if comets:
        with ThreadPoolExecutor(max_workers=min(4, len(comets))) as pool:
            rows = list(pool.map(lambda c: fetch(c["mpc_name"] or c["name"]),
                                 comets))
    else:
        rows = []

    out = []
    for c, first in zip(comets, rows):
        if first is None:
            continue
        ra_s, dec_s = first["ra"], first["dec"]
        try:
            ra = coords.ra_hms_to_deg(ra_s)
            dec = coords.dec_dms_to_deg(dec_s)
        except (ValueError, AttributeError):
            continue
        out.append({
            "id": c["name"], "kind": "comet", "name": c["fullname"] or c["name"],
            "mag": c["mag"], "ra_deg": ra, "dec_deg": dec,
            "perihelion_date": c.get("perihelion_date"),
            "delta_au": first["delta"], "r_au": first["r"],
            **_visibility(ra, dec, lat, lon, date, hor, margin, duration_s),
        })
    return out


def _pccp_targets(lat, lon, date, hor, margin, duration_s=None):
    # Possible-comet candidates from the MPC PCCP page (see ADR-012).
    out = []
    for c in pccp.candidates():
        ra, dec = c.get("ra_deg"), c.get("dec_deg")
        if ra is None or dec is None:
            continue
        try:
            mag = float(c["vmag"]) if c.get("vmag") else None
        except ValueError:
            mag = None
        out.append({
            "id": c["desig"], "kind": "pccp", "name": c["desig"],
            "mag": mag, "ra_deg": ra, "dec_deg": dec,
            "pccp_score": c.get("score"), "arc_days": c.get("arc"),
            "nobs": c.get("nobs"),
            "disc_date": dates.normalize_date(c.get("discovery")),
            **_visibility(ra, dec, lat, lon, date, hor, margin, duration_s),
        })
    return out


def _transit_aperture(cfg):
    # The hard aperture gate for transits (ADR-015 consequence, object-card
    # plan subplan 6): the user's aperture when the Settings toggle is on,
    # else None (no gate). A missing/unparseable aperture also means no gate.
    # @args: cfg - Config instance
    # @return: float inches or None
    if not cfg.get("transit_scope_filter", True):
        return None
    try:
        ap = cfg.get("aperture_inches")
        return float(ap) if ap else None
    except (TypeError, ValueError):
        return None


def _transit_plate_scale(cfg):
    # The camera/telescope plate scale for the transit exposure heuristic
    # (Track D). Returns None (no correction) when the camera profile is
    # incomplete — plate_scale() gives 0.0 without a focal length.
    # @args: cfg - Config instance
    # @return: arcsec/pixel or None
    ps = exposure.plate_scale(cfg.get("pixel_um"), cfg.get("focal_mm"))
    return ps or None


def _transit_targets(lat, lon, date, hor, limit_mag=14.0, margin=0.0,
                     aperture_in=None, plate_scale_arcsec_px=None):
    # Exoplanet transits computed locally from the ExoClock catalogue.
    # The star must clear the local horizon + margin at mid-transit
    # (ADR-020) — the same safety rule as every other family.
    out = []
    for t in transits.transits_tonight(exoclock.planets(), lat, lon, date,
                                        threshold_fn=hor.alt_at,
                                        max_vmag=limit_mag, margin=margin,
                                        aperture_in=aperture_in,
                                        plate_scale_arcsec_px=
                                        plate_scale_arcsec_px):
        out.append({
            "id": t["name"], "kind": "transit",
            "name": t["name"], "mag": t.get("v_mag"),
            "ra_deg": t["ra"], "dec_deg": t["dec"],
            "max_alt": t.get("max_alt"), "hours_up": None,
            "max_time": t["mid"].isoformat(),
            "window_start": t["ingress"].isoformat(),
            "window_end": t["egress"].isoformat(),
            "transit": t,
        })
    return out


def _hads_targets(lat, lon, date, hor, limit_mag=20.0, margin=0.0,
                  plate_scale_arcsec_px=None):
    # HADS stars from the hybrid catalog (bundled snapshot + Wils' live
    # sheet, core/hads.py). No phase is known for these pulsators, so the
    # gate is not an event but a contiguous above-horizon span holding at
    # least one full pulsation cycle; the recommended session (2P) is passed
    # as the planned duration so safe_window/best_time answer "can I watch
    # it repeat twice?" (ADR-020 safety stays in _visibility).
    out = []
    for star in hads.catalog():
        if not star.get("period_h") or star.get("max") is None:
            continue
        mag_med = (star["max"] + star["min"]) / 2     # H-e: median gate
        if mag_med > limit_mag:
            continue
        vis = _visibility(star["ra_deg"], star["dec_deg"], lat, lon, date,
                          hor, margin, star["period_h"] * 2 * 3600)
        span = hads.span_hours(vis["window_start"], vis["window_end"])
        if span is None or span < star["period_h"]:
            continue                                  # not even one cycle
        d = hads.derive(star, vis["hours_up"], plate_scale_arcsec_px)
        d["session_fits"] = vis["safe_window"] is not None
        d["covered_this_month"] = hads.covered_this_month(star)
        out.append({
            "id": star["name"], "kind": "hads", "name": star["name"],
            "mag": mag_med, "ra_deg": star["ra_deg"], "dec_deg": star["dec_deg"],
            **vis,
            "hads": {"period_h": star["period_h"], "max": star["max"],
                     "min": star["min"], "amp": d["amp"],
                     "cycles": d["cycles"], "cadence_s": d["cadence_s"],
                     "session_req_h": d["session_req_h"],
                     "session_fits": d["session_fits"], "exp_s": d["exp_s"],
                     "priority": star.get("priority"),
                     "observed": star.get("observed"),
                     "multiperiodic": star.get("multiperiodic"),
                     "non_radial": star.get("non_radial"),
                     "covered_this_month": d["covered_this_month"]},
        })
    return out


def _approach_alerts():    # Upcoming close approaches from ESA NEOCC (outreach alerts pillar).
    out = []
    for a in esa_neo.close_approaches(20.0)[:10]:
        out.append({
            "id": a["name"], "kind": "alert", "name": a["name"],
            "mag": a.get("mag_max"), "ra_deg": None, "dec_deg": None,
            "max_alt": None, "hours_up": None, "max_time": None,
            "approach": a,
        })
    return out
