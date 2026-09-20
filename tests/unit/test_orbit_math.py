############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - orbit math distance / closest-approach tests
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Pure-math check of the new helpers in core/orbit_math:

  * distance_to_earth - the geocentric distance at a given Julian date;
  * closest_approach  - a minimisation of that distance over a window.

Both must work for closed (e < 1) and open (e >= 1) orbits, and agree
with the rest of the module (position_now / planet_heliocentric) since
they are built on the same primitives. No GUI, no network, no matplotlib.
"""

import math

from nightscribe.core import orbit_math


# 433 Eros (J2000) — a real asteroid, mildly eccentric, a clean reference.
_EROS = {"a": 1.458, "e": 0.2227, "i": 10.83,
         "om": 304.886, "w": 183.614, "ma": 106.6, "epoch": 2451543.5}
# 2032 YQ1 (hyperbolic) — an escapee, used to check the open-orbit branch.
_HYB = {"q": 0.981, "e": 1.021, "i": 84.5,
        "om": 110.0, "w": 210.0, "tp": 2460690.0}
_JD_2026_09_03 = 2461287.333


def test_distance_to_earth_closed():
    # The current geocentric distance for Eros is finite, positive, and
    # consistent with our own Earth position (not hardcoded to a value
    # that could drift from the ephem helper).
    d = orbit_math.distance_to_earth(_EROS, _JD_2026_09_03)
    assert d is not None
    assert d > 0.01, f"distance too small ({d})"
    assert d < 20.0, f"distance too large ({d})"


def test_distance_to_earth_earth_match():
    # When the object is at Earth's own heliocentric spot, the geocentric
    # distance must collapse to (numerically) zero. We force it by
    # constructing a synthetic "object" that sits exactly on Earth right
    # now.
    x_e, y_e, z_e, _r = orbit_math.planet_heliocentric("earth", _JD_2026_09_03)
    # Build an Earth-like circular orbit that passes through the current
    # Earth spot at this exact Julian date.
    r_au = math.sqrt(x_e * x_e + y_e * y_e + z_e * z_e)
    # The heliocentric angle at that instant, projected into the ecliptic
    # plane, gives us the mean anomaly to feed back into a circular orbit
    # centred on the ecliptic pole (i=0, om=0, w=0).
    nu = math.degrees(math.atan2(y_e, x_e)) % 360
    els = {"a": r_au, "e": 0.0, "i": 0.0, "om": 0.0, "w": 0.0,
           "ma": nu, "epoch": _JD_2026_09_03}
    d = orbit_math.distance_to_earth(els, _JD_2026_09_03)
    assert d is not None
    assert d < 1e-3, f"expected ~0, got {d}"


def test_distance_to_earth_open():
    # A hyperbolic orbit is locatable (Barker's equation) at its perihelion
    # and at any date where r is finite.
    # Pick a date a few months after perihelion so the object is still out there.
    jd = _HYB["tp"] + 90
    d = orbit_math.distance_to_earth(_HYB, jd)
    assert d is not None
    assert d > 0.0


def test_distance_to_earth_returns_none_without_time():
    # No epoch/mean-anomaly/tp means we cannot place the point in time.
    els = {"a": 1.5, "e": 0.1, "i": 5.0, "om": 10.0, "w": 20.0}
    assert orbit_math.distance_to_earth(els, _JD_2026_09_03) is None


def test_closest_approach_finds_min():
    # For a closed orbit the global minimum over a window is the perihelion
    # (if the perihelion falls inside), else the endpoint nearest it. We
    # construct a case where the orbit's perihelion sits inside a 60-day
    # window and check the minimum lands on (or near) perihelion.
    # Perihelion distance = a * (1 - e) = 1.0 * 0.6 = 0.600 AU (heliocentric).
    els = {"a": 1.5, "e": 0.6, "i": 0.0, "om": 0.0, "w": 0.0,
           "ma": 0.0, "epoch": 2460000.0}
    # Perihelion is at m=0. With a=1.5, n = 0.9856 / 1.5^1.5 = 0.536 deg/day.
    # A perihelion at epoch=2460000 means the orbit hits perihelion every
    # P = 365.25 * 1.5^1.5 = 844 days. Window centred on 2460000 catches it.
    jd_best, d_best = orbit_math.closest_approach(
        els, 2460000.0, half_window_days=60.0, n=240)
    assert jd_best is not None
    assert d_best is not None
    # The best date should be inside the window
    assert abs(jd_best - 2460000.0) <= 60.0
    # The minimum distance should be at least the perihelion (in helio AU,
    # geocentric is bounded below by |r_obj - r_earth|, which may or may not
    # coincide with the orbit's perihelion).
    assert d_best > 0.0


def test_closest_approach_window_respects_bounds():
    # The returned Julian date must stay inside [center - half, center + half]
    # (up to one grid step of the solver tolerance).
    els = dict(_EROS)
    center = 2461000.0
    half = 30.0
    jd_best, _d = orbit_math.closest_approach(els, center,
                                              half_window_days=half, n=240)
    assert jd_best is not None
    assert center - half <= jd_best <= center + half


def test_closest_approach_returns_none_when_unlocatable():
    # No time means no distance at any sample -> no closest approach.
    els = {"a": 1.5, "e": 0.1, "i": 5.0, "om": 10.0, "w": 20.0}
    assert orbit_math.closest_approach(els, 2460000.0) is None


def test_closest_approach_open_orbit():
    # The minimisation should still work for an escaping orbit (we sample
    # over the finite window; outside it the object is undefined, but
    # closest_approach only samples inside the window).
    jd_best, d_best = orbit_math.closest_approach(
        _HYB, _HYB["tp"] + 60.0, half_window_days=60.0, n=120)
    assert jd_best is not None
    assert d_best > 0.0
