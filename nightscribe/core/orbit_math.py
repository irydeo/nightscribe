############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - orbit math helpers (pure, no matplotlib)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Pure orbit sampling math shared by the matplotlib chart layer
(`viz/orbit_view.py`) and the PySide6 GUI widget layer (`gui/widgets/
orbit_widget.py`).

This module deliberately does NOT import `matplotlib` (ADR-029) — it only
depends on `math` + the ephem helpers in `core.ephem_minor`, so it is
import-safe from the QGraphicsView widgets.
"""

import math

from . import ephem_minor


def bound_orbit_xy(elements, n=360):
    # Samples a full bound orbit (e < 1) as x/y in heliocentric ecliptic AU.
    # @args: elements - dict with a, e, i, om, w (deg); n - number of samples
    # @return: (xs, ys) lists in AU
    a = elements.get("a")
    e = elements.get("e", 0)
    if a is None:
        q = elements.get("q")
        if q is not None and e < 1.0:
            a = q / (1.0 - e)
        else:
            return [], []
    om = elements.get("om", 0.0)
    i = elements.get("i", 0.0)
    w = elements.get("w", 0.0)
    xs, ys = [], []
    for k in range(n + 1):
        m = 360.0 * k / n
        try:
            x, y, z, _r = ephem_minor._elements_to_ecliptic(om, i, w, a, e, m)
            xs.append(x)
            ys.append(y)
        except (KeyError, ZeroDivisionError, ValueError):
            continue
    return xs, ys


def open_orbit_xy(elements, n=360):
    # Samples an open parabola/hyperbola over valid true anomalies.
    # @args: elements - dict with q, e, i, om, w (deg); n - number of samples
    # @return: (xs, ys) lists in AU
    q = elements.get("q")
    e = elements.get("e", 0)
    if q is None or q <= 0:
        return [], []
    # nu_max = the true anomaly where the object escapes (1 + e cos nu -> 0)
    nu_max = min(150.0, math.degrees(math.acos(-1.0 / e)) - 5.0)
    om = elements.get("om", 0.0)
    i = elements.get("i", 0.0)
    w = elements.get("w", 0.0)
    xs, ys = [], []
    for k in range(n + 1):
        nu = -nu_max + 2.0 * nu_max * k / n
        try:
            x, y, z, _r = ephem_minor._open_orbit_ecliptic(om, i, w, q, e, nu)
            xs.append(x)
            ys.append(y)
        except (KeyError, ZeroDivisionError, ValueError):
            continue
    return xs, ys


def orbit_xy(elements, n=360):
    # One entry point for both bound and open orbits.
    # @args: elements - dict (a or q, e, i, om, w); n - samples
    # @return: (xs, ys) in AU (may be empty if the shape cannot be sampled)
    if elements.get("e", 0) >= 1.0:
        return open_orbit_xy(elements, n)
    return bound_orbit_xy(elements, n)


def position_now(elements, jd):
    # Current heliocentric position of the object.
    # @args: elements - dict (a or q + e, i, om, w, ma/tp/epoch for time);
    #        jd - Julian date
    # @return: (x, y, z, r, nu_deg) or None if the data is insufficient
    e = elements.get("e", 0)
    a = elements.get("a")
    if (a is None or a <= 0) and e < 1.0:
        q = elements.get("q")
        if q is not None:
            a = q / (1.0 - e)
            elements = dict(elements, a=a)
    if e >= 1.0:
        q = elements.get("q")
        tp = elements.get("tp")
        if not (q and tp):
            return None
        nu = ephem_minor._barker_true_anomaly(q, jd - tp)
        x, y, z, r = ephem_minor._open_orbit_ecliptic(
            elements.get("om", 0.0), elements.get("i", 0.0),
            elements.get("w", 0.0), q, e, nu)
        return (x, y, z, r, nu)
    if a is None:
        return None
    m_now = None
    if elements.get("ma") is not None and elements.get("epoch") is not None:
        n_day = 0.9856076686 / (a ** 1.5)
        m_now = (elements["ma"] + n_day * (jd - elements["epoch"])) % 360
    elif elements.get("tp") is not None:
        n_day = 0.9856076686 / (a ** 1.5)
        m_now = (n_day * (jd - elements["tp"])) % 360
    if m_now is None:
        return None
    E = ephem_minor._kepler_e(m_now, e)
    # recompute nu from E (the solver does not expose it)
    xv = a * (math.cos(math.radians(E)) - e)
    yv = a * math.sqrt(1.0 - e * e) * math.sin(math.radians(E))
    nu = math.degrees(math.atan2(yv, xv))
    x, y, z, r = ephem_minor._elements_to_ecliptic(
        elements.get("om", 0.0), elements.get("i", 0.0),
        elements.get("w", 0.0), a, e, m_now)
    return (x, y, z, r, nu)


def _ecliptic_to_orbit(x, y, z, om_deg, i_deg, w_deg):
    # Rotates a heliocentric ecliptic vector into the orbit frame.
    # @return: (x', y', z') in the orbit frame; x' is toward periapsis.
    om, i, w = (math.radians(v) for v in (om_deg, i_deg, w_deg))
    c1 = math.cos(om) * math.cos(w) - math.sin(om) * math.sin(w) * math.cos(i)
    c2 = math.cos(om) * math.sin(w) + math.sin(om) * math.cos(w) * math.cos(i)
    c3 = math.sin(om) * math.sin(i)
    d1 = -math.sin(om) * math.cos(w) - math.cos(om) * math.sin(w) * math.cos(i)
    d2 = -math.sin(om) * math.sin(w) + math.cos(om) * math.cos(w) * math.cos(i)
    d3 = math.cos(om) * math.sin(i)
    e1 = math.sin(w) * math.sin(i)
    e2 = -math.cos(w) * math.sin(i)
    e3 = math.cos(i)
    return (c1 * x + c2 * y + c3 * z,
            d1 * x + d2 * y + d3 * z,
            e1 * x + e2 * y + e3 * z)


def hover_at(scene_x, scene_y, scene_z, elements):
    # Hit test on a scene coordinate (heliocentric ecliptic AU) and
    # recover the true anomaly correctly.
    # @args: scene_x, scene_y, scene_z - AU in ecliptic frame; elements - dict
    # @return: (r, nu_deg) if the point is valid, else None
    r = math.sqrt(scene_x * scene_x + scene_y * scene_y + scene_z * scene_z)
    if r <= 0:
        return None
    xo, yo, zo = _ecliptic_to_orbit(
        scene_x, scene_y, scene_z,
        elements.get("om", 0.0), elements.get("i", 0.0),
        elements.get("w", 0.0))
    nu = math.degrees(math.atan2(yo, xo))
    return (r, nu)


def planet_heliocentric(pname, jd):
    # Current heliocentric position of one of the reference planets.
    # @args: pname - "mercury" | "venus" | "mars" | "jupiter"
    #        (Earth is handled specially)
    # @return: (x, y, z, r) in AU
    if pname == "earth":
        xe, ye, ze = ephem_minor.earth_ecliptic_xyz(jd)
        return (xe, ye, ze, math.hypot(xe, ye, ze))
    p = ephem_minor._PLANETS[pname]
    d = jd - 2451543.5
    els = {"om": (p[0] + p[1] * d) % 360, "i": p[2] + p[3] * d,
           "w": (p[4] + p[5] * d) % 360, "a": p[6] + p[7] * d,
           "e": p[8] + p[9] * d, "ma": (p[10] + p[11] * d) % 360}
    x, y, z, r = ephem_minor._elements_to_ecliptic(
        els["om"], els["i"], els["w"], els["a"], els["e"], els["ma"])
    return (x, y, z, r)


def distance_to_earth(elements, jd):
    # Geocentric distance of the object (AU) — the number an
    # observer cares most about when planning a night.
    # @args: elements - dict (a or q, e, i, om, w, ma/tp/epoch)
    #        jd - Julian date
    # @return: float in AU, or None if the object cannot be located
    pos = position_now(elements, jd)
    if pos is None:
        return None
    xo, yo, zo, _r, _nu = pos
    xe, ye, ze, _re = planet_heliocentric("earth", jd)
    return math.sqrt((xo - xe) ** 2 + (yo - ye) ** 2 + (zo - ze) ** 2)


def closest_approach(elements, jd_center, half_window_days=60.0, n=480):
    # Samples the object-Earth distance over a window centred on
    # `jd_center` and returns the minimum. The grid is deliberately
    # coarse: the widget's date scrub drives the "right now" view, so
    # the purpose here is a label, not an ephemeris-grade answer.
    # @args: elements - dict (a or q, e, i, om, w, ma/tp/epoch)
    #        jd_center - centre of the search window
    #        half_window_days - half the window in days (default 60)
    #        n - samples across the window
    # @return: (jd_best, dist_au) or None if the object cannot be located
    best_jd, best_d = None, float("inf")
    for k in range(n + 1):
        jd = jd_center - half_window_days + 2.0 * half_window_days * k / n
        d = distance_to_earth(elements, jd)
        if d is None:
            continue
        if d < best_d:
            best_d, best_jd = d, jd
    if best_jd is None:
        return None
    return (best_jd, best_d)
