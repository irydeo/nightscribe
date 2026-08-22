############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Exoplanet transits module
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

from . import coords

logger = logging.getLogger(__name__)

# Exoplanet transits are events: t0 + n*period (see ADR-015). We compute
# them locally and keep those crossing tonight's darkness for the site.


def transit_times(t0_jd, period_days, from_jd, to_jd):
    # Transit mid-times within a window.
    # @args: t0_jd - reference mid-transit (BJD, close enough to JD for us),
    #        period_days - orbital period, from_jd/to_jd - window
    # @return: list of mid-transit Julian dates
    if not t0_jd or not period_days:
        return []
    n0 = int((from_jd - t0_jd) / period_days) - 1
    times = []
    n = n0
    while True:
        t = t0_jd + n * period_days
        if t > to_jd:
            break
        if t >= from_jd - period_days:
            times.append(t)
        n += 1
    return times


def _altitude_ok(ra, dec, lat, lon, jd, min_alt):
    # @return: altitude of the star at a given instant
    alt, _ = coords.altaz(ra, dec, lat, coords.lst_degrees(jd, lon))
    return alt


def transits_tonight(planets, lat, lon, date=None, min_alt=30.0, max_vmag=14.0):
    # Exoplanet transits visible from a site during tonight's darkness.
    # @args: planets - list from sources.exoclock.planets(),
    #        lat, lon - site, date - datetime.date (UTC, tonight),
    #        min_alt - min star altitude, max_vmag - star magnitude limit
    # @return: list of dicts with the transit window and coverage
    window = coords.tonight_window(lat, lon, date)
    if not window:
        return []
    start, end = window
    from_jd = coords.jd_from_datetime(start)
    to_jd = coords.jd_from_datetime(end)
    results = []
    for p in planets:
        if p.get("v_mag") and p["v_mag"] > max_vmag:
            continue
        for mid_jd in transit_times(p["t0"], p["period"], from_jd, to_jd):
            dur_h = p.get("duration_h") or 2.0
            half = dur_h / 48.0  # half duration in days
            ingress = mid_jd - half
            egress = mid_jd + half
            # star altitude at ingress, mid, egress
            alts = [_altitude_ok(p["ra"], p["dec"], lat, lon, jd, min_alt)
                    for jd in (ingress, mid_jd, egress)]
            above = sum(1 for a in alts if a >= min_alt)
            if above == 0:
                continue
            coverage = above / 3.0
            results.append({
                "name": p["name"],
                "star": p.get("star"),
                "ra": p["ra"], "dec": p["dec"],
                "ingress": coords.datetime_from_jd(ingress),
                "mid": coords.datetime_from_jd(mid_jd),
                "egress": coords.datetime_from_jd(egress),
                "coverage": coverage,
                "full": above == 3,
                "depth_mmag": p.get("depth_mmag"),
                "duration_h": dur_h,
                "v_mag": p.get("v_mag"),
                "priority": p.get("priority"),
                "min_telescope_in": p.get("min_telescope_in"),
                "oc_min": p.get("oc_min"),
                "max_alt": round(max(alts), 1),
            })
    results.sort(key=lambda t: (not t["full"], t["ingress"]))
    return results
