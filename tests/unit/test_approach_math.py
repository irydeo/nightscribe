############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - approach math unit tests (pure, no net)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Unit tests for nightscribe.core.approach_math (no network).

Lock in the geocentric position, track, closest-approach and moon routines
so the ApproachChart widget can build on them safely.
"""

import math

import pytest

from nightscribe.core import approach_math as am
from nightscribe.core import orbit_math

# a plausible Apollo-like NEO (e < 1)
ELS = {"a": 1.5, "e": 0.5, "i": 10.0, "om": 60.0, "w": 20.0,
       "epoch": 2460000.0, "ma": 100.0}
JD = 2460900.0


def test_ld_from_au_and_back():
    assert am.ld_from_au(0.0) == 0.0
    au = 0.008
    assert am.au_from_ld(am.ld_from_au(au)) == pytest.approx(au, rel=1e-9)
    assert am.ld_from_au(au) == pytest.approx(au / am.AU_PER_LD, rel=1e-9)


def test_aup_per_ld_is_about_0p00257():
    assert 0.0025 < am.AU_PER_LD < 0.0026


def test_geocentric_position_returns_tuple_of_five():
    g = am.geocentric_position(ELS, JD)
    assert g is not None
    assert len(g) == 5
    xg, yg, zg, r_au, r_ld = g
    assert math.isfinite(xg) and math.isfinite(yg) and math.isfinite(zg)
    # r_au must satisfy the Pythagorean relation
    assert math.sqrt(xg**2 + yg**2 + zg**2) == pytest.approx(r_au, rel=1e-9)
    # r_ld = r_au / AU_PER_LD
    assert r_ld == pytest.approx(am.ld_from_au(r_au), rel=1e-9)
    # cross-check: r_au must equal orbit_math.distance_to_earth
    assert r_au == pytest.approx(orbit_math.distance_to_earth(ELS, JD), rel=1e-9)


def test_geocentric_position_insufficient_data_returns_none():
    # an object we cannot locate (no time-of-date reference)
    assert am.geocentric_position({"e": 0.2, "a": 1.2}, JD) is None


def test_geocentric_track_has_n_plus_one_points_when_resolvable():
    jds, xs, ys, zs, r_lds = am.geocentric_track(ELS, JD, 30.0, 12)
    # a closed, resolvable orbit should yield all 13 points
    assert len(jds) == 13
    assert len(xs) == 13 and len(ys) == 13 and len(zs) == 13 and len(r_lds) == 13
    # first JD = center − half window; last = center + half window
    assert jds[0] == pytest.approx(JD - 30.0)
    assert jds[-1] == pytest.approx(JD + 30.0)
    # every r is finite and positive
    assert all(r > 0 and math.isfinite(r) for r in r_lds)


def test_geocentric_track_insufficient_data_returns_empty():
    jds, xs, ys, zs, r_lds = am.geocentric_track({"e": 0.2, "a": 1.2}, JD, 30.0, 4)
    assert jds == [] and xs == [] and ys == [] and zs == [] and r_lds == []


def test_closest_approach_geocentric_returns_three():
    ca = am.closest_approach_geocentric(ELS, JD, 90.0, 160)
    assert ca is not None
    jd_best, dist_au, dist_ld = ca
    assert math.isfinite(jd_best)
    assert dist_au > 0
    assert dist_ld == pytest.approx(am.ld_from_au(dist_au), rel=1e-9)
    # dist_au must equal closest_approach's own answer (same logic, + LD)
    jd0, dist0 = orbit_math.closest_approach(ELS, JD, 90.0, 160)
    assert jd_best == pytest.approx(jd0)
    assert dist_au == pytest.approx(dist0, rel=1e-9)


def test_closest_approach_geocentric_insufficient_returns_none():
    assert am.closest_approach_geocentric({"e": 0.2, "a": 1.2}, JD) is None


def test_moon_geocentric_ecliptic_is_about_one_ld():
    xe, ye, r_au, r_ld = am.moon_geocentric_ecliptic(JD)
    assert math.isfinite(xe) and math.isfinite(ye)
    # the moon is ~384 400 km away = 1 LD
    assert 0.90 < r_ld < 1.10
    # and the AU distance is in the right band (0.0025 … 0.0026)
    assert 0.0024 < r_au < 0.0027
    assert r_au == pytest.approx(r_ld * am.AU_PER_LD, rel=1e-9)


def test_moon_geocentric_ecliptic_differs_over_time():
    m1 = am.moon_geocentric_ecliptic(JD)
    m2 = am.moon_geocentric_ecliptic(JD + 7.0)
    # the moon moves ~13°/day, so the geocentric xy must differ
    assert not (m1[0] == m2[0] and m1[1] == m2[1])
