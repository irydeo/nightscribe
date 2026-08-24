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

import logging

from . import coords, horizon, transits
from .sources import (cobs, esa_neo, exoclock, horizons, neofixer, pccp,
                      rochester)

logger = logging.getLogger(__name__)

# Builds the raw list of tonight's targets from every source. Each target is
# a flat dict; scoring lives in suggest.py. A source that fails simply
# contributes nothing (graceful degradation, see ARCHITECTURE).


def build_tonight(cfg, date=None, n_neofixer=40, n_comets=15):
    # @args: cfg - Config instance, date - datetime.date (tonight, UTC),
    #        n_neofixer - NEOfixer list size, n_comets - brightest comets to locate
    # @return: list of target dicts
    lat, lon = cfg.get("lat"), cfg.get("lon")
    site = cfg.get("mpc_code")
    min_alt = float(cfg.get("min_alt", 30.0))
    limit_mag = float(cfg.get("limit_mag", 20.0))
    hor = horizon.from_config(cfg)
    margin = float(cfg.get("horizon_margin_deg", 0.0))
    targets = []
    targets += _neo_targets(site, n_neofixer, lat, lon, date, hor, margin)
    targets += _sn_targets(limit_mag, lat, lon, date, hor, margin)
    targets += _comet_targets(limit_mag, lat, lon, site, n_comets, date,
                              hor, margin)
    targets += _pccp_targets(lat, lon, date, hor, margin)
    targets += _transit_targets(lat, lon, date, min_alt, limit_mag)
    targets += _approach_alerts()
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


def _visibility(ra_deg, dec_deg, lat, lon, date, hor, margin=0.0):
    # Altitude summary for a fixed RA/Dec tonight against the local horizon.
    # @return: dict with max_alt, max_time, max_az, hours_up, window_start/end
    alt, t = coords.max_altitude_tonight(ra_deg, dec_deg, lat, lon, date)
    max_az = None
    if t is not None:
        jd = coords.jd_from_datetime(t)
        _a, max_az = coords.altaz(ra_deg, dec_deg, lat,
                                  coords.lst_degrees(jd, lon))
    win = coords.window_above(ra_deg, dec_deg, lat, lon, hor.alt_at, date, margin)
    hours = coords.hours_above_h(ra_deg, dec_deg, lat, lon, hor.alt_at,
                                 date, margin)
    return {"max_alt": round(alt, 1) if alt else None,
            "max_time": t.isoformat() if t else None,
            "max_az": round(max_az, 1) if max_az is not None else None,
            "hours_up": round(hours, 1),
            "window_start": win[0].isoformat() if win else None,
            "window_end": win[1].isoformat() if win else None}


def _neo_targets(site, n, lat, lon, date, hor, margin):
    # NEOfixer priority list for the site (see ADR-003).
    out = []
    for t in neofixer.targets(site, n):
        try:
            vis = _visibility(t["ra deg"], t["dec deg"], lat, lon, date,
                              hor, margin)
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
    return out


def _sn_targets(limit_mag, lat, lon, date, hor, margin, max_days=90):
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
            **_visibility(ra, dec, lat, lon, date, hor, margin),
        })
    return out


def _comet_targets(limit_mag, lat, lon, site, n, date, hor, margin):
    # Brightest active comets from COBS; position via Horizons (cached).
    out = []
    for c in cobs.active_comets(limit_mag)[:n]:
        rows = horizons.ephemeris(c["mpc_name"] or c["name"], center=site)
        if not rows:
            continue
        ra_s, dec_s = rows[0]["ra"], rows[0]["dec"]
        try:
            ra = coords.ra_hms_to_deg(ra_s)
            dec = coords.dec_dms_to_deg(dec_s)
        except (ValueError, AttributeError):
            continue
        out.append({
            "id": c["name"], "kind": "comet", "name": c["fullname"] or c["name"],
            "mag": c["mag"], "ra_deg": ra, "dec_deg": dec,
            "perihelion_date": c.get("perihelion_date"),
            "delta_au": rows[0]["delta"], "r_au": rows[0]["r"],
            **_visibility(ra, dec, lat, lon, date, hor, margin),
        })
    return out


def _pccp_targets(lat, lon, date, hor, margin):
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
            **_visibility(ra, dec, lat, lon, date, hor, margin),
        })
    return out


def _transit_targets(lat, lon, date, min_alt, limit_mag=14.0):
    # Exoplanet transits computed locally from the ExoClock catalogue.
    out = []
    for t in transits.transits_tonight(exoclock.planets(), lat, lon, date,
                                       min_alt, limit_mag):
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


def _approach_alerts():
    # Upcoming close approaches from ESA NEOCC (outreach alerts pillar).
    out = []
    for a in esa_neo.close_approaches(20.0)[:10]:
        out.append({
            "id": a["name"], "kind": "alert", "name": a["name"],
            "mag": a.get("mag_max"), "ra_deg": None, "dec_deg": None,
            "max_alt": None, "hours_up": None, "max_time": None,
            "approach": a,
        })
    return out
