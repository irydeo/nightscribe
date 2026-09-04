############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - geocentric approach math (pure, no matplotlib)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Geocentric approach math for the ApproachChart widget
(`gui/widgets/approach_widget.py`).

Pure (math + core.ephem_minor + core.orbit_math only — no matplotlib),
in the same spirit as core/orbit_math.py (ADR-029).

Internal unit: AU.  Public API also returns LD (lunar distances) where
relevant, so the widget can display "X.XX LD" directly.
"""

import math

from . import ephem_minor
from . import orbit_math

AU_KM = ephem_minor.AU_KM          # 149 597 870.7 km
LD_KM = 384_400.0                  # 1 lunar distance (mean Earth-Moon)
AU_PER_LD = LD_KM / AU_KM          # ≈ 0.00257 AU per LD


def ld_from_au(au):
    # @args: au - distance in AU
    # @return: the same distance in lunar distances
    return au / AU_PER_LD


def au_from_ld(ld):
    # @args: ld - distance in lunar distances
    # @return: the same distance in AU
    return ld * AU_PER_LD


def geocentric_position(elements, jd):
    # Geocentric ecliptic position of the object at `jd`.
    # @args: elements - orbital dict; jd - Julian date
    # @return: (xg, yg, zg, r_au, r_ld) or None if the object cannot be located
    pos = orbit_math.position_now(elements, jd)
    if pos is None:
        return None
    xo, yo, zo, _r, _nu = pos
    xe, ye, ze = ephem_minor.earth_ecliptic_xyz(jd)
    xg, yg, zg = xo - xe, yo - ye, zo - ze
    r_au = math.sqrt(xg * xg + yg * yg + zg * zg)
    return (xg, yg, zg, r_au, ld_from_au(r_au))


def geocentric_track(elements, jd_center, half_window_days=30.0, n=180):
    # Samples the object's geocentric ecliptic track over
    # [jd_center − half_window_days, jd_center + half_window_days].
    # @args: elements - orbital dict; jd_center - reference Julian date
    #        (usually the CA); half_window_days - half the time window (days);
    #        n - number of intervals (n+1 points)
    # @return: (jds, xs, ys, zs, r_lds) — five parallel lists (may be shorter
    #          than n+1 if some samples could not be located)
    jds, xs, ys, zs, r_lds = [], [], [], [], []
    for k in range(n + 1):
        jd = jd_center - half_window_days + 2.0 * half_window_days * k / n
        g = geocentric_position(elements, jd)
        if g is None:
            continue
        jds.append(jd)
        xs.append(g[0])
        ys.append(g[1])
        zs.append(g[2])
        r_lds.append(g[4])
    return jds, xs, ys, zs, r_lds


def closest_approach_geocentric(elements, jd_center,
                                  half_window_days=60.0, n=480):
    # Finds the minimum object-Earth distance over the window by reusing
    # orbit_math.closest_approach (same grid/bisection logic), then adds
    # the LD conversion.
    # @args: elements - orbital dict; jd_center - Julian date of search centre;
    #        half_window_days - half the search window (default 60);
    #        n - sampling resolution
    # @return: (jd_best, dist_au, dist_ld) or None if the object cannot be
    #          located in the window
    res = orbit_math.closest_approach(elements, jd_center,
                                       half_window_days, n)
    if res is None:
        return None
    jd_best, dist_au = res
    return (jd_best, dist_au, ld_from_au(dist_au))


def moon_geocentric_ecliptic(jd):
    # Moon geocentric ecliptic position at `jd`, in AU.
    # @args: jd - Julian date
    # @return: (xe, ye, r_au, r_ld) — geocentric ecliptic x/y (AU),
    #          heliocentric distance (AU), and distance in LD
    m = ephem_minor.moon(jd)
    r_au = m["dist_km"] / AU_KM
    ra  = math.radians(m["ra"])
    dec = math.radians(m["dec"])
    ECL = math.radians(23.4393)   # obliquity (constant to <1″ over 800 yr)
    xe = r_au * math.cos(dec) * math.cos(ra)
    ye = r_au * (math.cos(dec) * math.sin(ra) * math.cos(ECL)
                 + math.sin(dec) * math.sin(ECL))
    return (xe, ye, r_au, r_au / AU_PER_LD)
