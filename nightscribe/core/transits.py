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
# Safety (ADR-020): a transit is listed only when the star clears the local
# horizon + margin AT MID-TRANSIT — the moment the planet crosses. The
# ingress/egress samples stay as coverage information, not as the gate.


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


def _altaz_at(ra, dec, lat, lon, jd):
    # @return: (altitude, azimuth) of the star at a given instant
    alt, az = coords.altaz(ra, dec, lat, coords.lst_degrees(jd, lon))
    return alt, az


def transits_tonight(planets, lat, lon, date=None, threshold_fn=None,
                      min_alt=None, max_vmag=14.0, margin=0.0,
                      aperture_in=None):
    # Exoplanet transits visible from a site during tonight's darkness.
    # @args: planets - list from sources.exoclock.planets(),
    #        lat, lon - site, date - datetime.date (UTC, tonight),
    #        threshold_fn - az->min altitude per the local horizon (ADR-020),
    #        min_alt - flat fallback (used when threshold_fn is not given),
    #        max_vmag - star magnitude limit,
    #        margin - extra safety degrees on top of the horizon (ADR-020),
    #                 applied at the gate exactly like the other families
    #        aperture_in - the user's telescope aperture in inches: a hard
    #                 gate against ExoClock's min_telescope_in (ADR-015
    #                 consequence, object-card plan subplan 6); a planet
    #                 without that datum is NEVER discarded
    # @return: list of dicts with the transit window and coverage
    if threshold_fn is None:
        threshold_fn = (lambda az, m=min_alt: m) if min_alt is not None \
            else (lambda az: 30.0)
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
        if aperture_in is not None:
            try:
                min_tel = p.get("min_telescope_in")
                too_big = min_tel is not None \
                    and float(min_tel) > float(aperture_in)
            except (TypeError, ValueError):
                too_big = False
            if too_big:
                continue
        for mid_jd in transit_times(p["t0"], p["period"], from_jd, to_jd):
            dur_h = p.get("duration_h") or 2.0
            half = dur_h / 48.0  # half duration in days
            ingress = mid_jd - half
            egress = mid_jd + half
            # star altitude/azimuth at ingress, mid, egress
            pts = [_altaz_at(p["ra"], p["dec"], lat, lon, jd)
                   for jd in (ingress, mid_jd, egress)]
            # gate: the star must be up when the planet actually crosses —
            # a transit only glimpsed at ingress/egress is not observable
            mid_alt, mid_az = pts[1]
            if mid_alt < threshold_fn(mid_az) + margin:
                continue
            above = sum(1 for (a, az) in pts if a >= threshold_fn(az) + margin)
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
                "max_alt": round(max(a for (a, _az) in pts), 1),
            })
    results.sort(key=lambda t: (not t["full"], t["ingress"]))
    return results
