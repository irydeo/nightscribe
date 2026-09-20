############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: ephem_minor (Schlyter)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import datetime

from nightscribe.core import coords, ephem_minor

JD = coords.jd_from_datetime(
    datetime.datetime(2026, 8, 21, 22, 0, tzinfo=datetime.timezone.utc))


def test_sun_position_sane():
    # late August: Sun around RA 10h (150 deg), declination ~+12 deg
    ra, dec, r = ephem_minor.sun_ra_dec(JD)
    assert 140 < ra < 165
    assert 8 < dec < 16
    assert 0.98 < r < 1.02


def test_moon_distance_range():
    # the Moon is always between ~356k and ~407k km
    m = ephem_minor.moon(JD)
    assert 350000 < m["dist_km"] < 410000
    assert 0.0 <= m["illum"] <= 1.0
    assert 0.0 <= m["phase_age_days"] <= 29.6


def test_planets_sane():
    # every planet must give finite coordinates and a plausible magnitude
    for name in ("mercury", "venus", "mars", "jupiter", "saturn", "uranus",
                 "neptune"):
        p = ephem_minor.planet(name, JD)
        assert 0 <= p["ra"] < 360
        assert -90 <= p["dec"] <= 90
        assert p["dist_au"] > 0
        assert p["mag"] < 9  # Neptune sits around mag 8


def test_kepler_roundtrip_apophis():
    # Apophis elements from SBDB (epoch 2026-Feb-21): position must exist
    # and sit within its known heliocentric range [q, Q]
    els = {"a": 0.9224, "e": 0.1912, "i": 3.33, "om": 204.43, "w": 126.4,
           "ma": 288.0, "epoch": 2461760.5}
    out = ephem_minor.kepler_ra_dec(els, JD)
    assert out is not None
    ra, dec, r, delta = out
    q = els["a"] * (1 - els["e"])
    qq = els["a"] * (1 + els["e"])
    assert q * 0.99 < r < qq * 1.01
    assert delta > 0


def test_kepler_geocentric_sign_against_horizons():
    # Regression: geocentric = heliocentric_object - heliocentric_earth.
    # Ground truth from the Horizons fixture (tests/fixtures/horizons_apophis.json):
    # Apophis on 2026-Aug-21 00:00 UT at RA 11 49 44.60 = 177.436 deg,
    # Dec +01 14 01.2 = 1.234 deg, delta = 1.7384 AU.
    # Tolerance 1 deg: two-body propagation from tp + Schlyter Sun (of-date
    # frame vs Horizons ICRF adds ~0.4 deg of equinox precession).
    els = {"a": 0.922, "e": 0.191, "i": 3.34, "om": 204.0, "w": 127.0,
           "tp": 2461042.919}
    jd0 = coords.jd_from_datetime(
        datetime.datetime(2026, 8, 21, 0, 0, tzinfo=datetime.timezone.utc))
    ra, dec, r, delta = ephem_minor.kepler_ra_dec(els, jd0)
    assert abs(ra - 177.436) < 1.0
    assert abs(dec - 1.234) < 1.0
    assert abs(delta - 1.7384) < 0.05


def test_planet_mars_against_horizons():
    # Mars on 2026-Aug-24 00:00 UT (queried from Horizons): RA 06 34 31 =
    # 98.63 deg, Dec +23 36 54 = 23.615 deg. Same frame caveat as above.
    jd0 = coords.jd_from_datetime(
        datetime.datetime(2026, 8, 24, 0, 0, tzinfo=datetime.timezone.utc))
    p = ephem_minor.planet("mars", jd0)
    assert abs(p["ra"] - 98.63) < 1.0
    assert abs(p["dec"] - 23.615) < 1.0


def test_kepler_high_e_bound_comet():
    # 12P/Pons-Brooks: e=0.955 — the old e<0.99 guard blocked this
    els = {"a": 17.2, "e": 0.955, "i": 74.0, "om": 70.0, "w": 199.0,
           "q": 0.781, "tp": 2460421.631, "ma": 357.0}
    out = ephem_minor.kepler_ra_dec(els, JD)
    assert out is not None
    ra, dec, r, delta = out
    q = els["a"] * (1 - els["e"])
    assert r >= q * 0.9  # never below perihelion


def test_barker_parabolic_comet():
    # C/2023 A3: e=1.0, q=0.391, tp=2460581.241 (parabolic)
    els = {"a": -4100.0, "e": 1.0, "i": 139.0, "om": 21.6, "w": 308.0,
           "q": 0.391, "tp": 2460581.241}
    out = ephem_minor.kepler_ra_dec(els, JD)
    assert out is not None
    ra, dec, r, delta = out
    assert 0 <= ra < 360
    assert -90 <= dec <= 90
    assert r > 0 and delta > 0


def test_open_orbit_ecliptic_perihelion():
    # at nu=0 (perihelion), r must equal q
    x, y, z, r = ephem_minor._open_orbit_ecliptic(0, 0, 0, 1.5, 1.0, 0.0)
    assert abs(r - 1.5) < 1e-10


def test_barker_at_perihelion():
    # at t=tp (dt=0), true anomaly must be 0
    nu = ephem_minor._barker_true_anomaly(1.0, 0.0)
    assert abs(nu) < 1e-10
