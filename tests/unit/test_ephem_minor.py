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
import math

import pytest

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


def test_kepler_j2000_matches_horizons_far_better_than_of_date():
    # The local fallback has to be in the SAME frame as the plate's WCS
    # (J2000/ICRF). The of-date path mixed a J2000 object with an of-date
    # Earth and missed by degrees on a close object (measured: 13039" on
    # 2026 PY9); the J2000 path, with the light-time, lands within a couple
    # of arcminutes (the residual is two-body + the coarse Earth, which the
    # caller absorbs by widening the cutout). Ground truth from the cached
    # Horizons ephemeris of the visit: 2026-08-16 22:25 UT, RA 313.3204,
    # Dec -4.8532.
    els = {"a": 2.329264345717352, "e": 0.5508738138610355,
           "i": 11.04772931873822, "om": 148.529452272859,
           "w": 207.3810299700251, "ma": 332.5479727971131,
           "epoch": 2461200.5}
    jd = 2461269.4342676736
    truth = (313.3204143893593, -4.853223733125551)

    def sep(p):
        dra = (p[0] - truth[0]) * math.cos(math.radians(truth[1])) * 3600.0
        return math.hypot(dra, (p[1] - truth[1]) * 3600.0)

    old = ephem_minor.kepler_ra_dec(els, jd)
    new = ephem_minor.kepler_ra_dec_j2000(els, jd)
    assert sep(old) > 5000.0            # degrees off: unusable
    assert sep(new) < 300.0             # arcminutes: guides the cutout
    assert new[3] > 0                   # a distance, not a direction only


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


# ------------------------------------------- the H-G predicted magnitude

# 2026 PY9's elements and H, as JPL's SBDB publishes them. The expected value
# is JPL Horizons' own APmag for that instant (22.208), which is what makes
# this a cross-check against an external truth and not a restatement of the
# code: the two agree to 0.01 mag.
_PY9 = {"a": 2.329264345717352, "e": 0.5508738138610355,
        "i": 11.04772931873822, "om": 148.529452272859,
        "w": 207.3810299700251, "ma": 332.5479727971131,
        "tp": 2461299.514435335, "epoch": 2461200.5, "q": 1.046133612101505}
_PY9_H = 23.356
# 2026-10-06 00:00 UT
_PY9_JD = 2461319.5


def test_the_hg_magnitude_matches_horizons():
    mag, band = ephem_minor.hg_magnitude_j2000(_PY9, _PY9_JD, _PY9_H)
    assert band == "V"
    assert mag == pytest.approx(22.208, abs=0.02)


def test_the_hg_magnitude_needs_an_absolute_magnitude():
    # Without H there is no figure to publish, and inventing one (a default,
    # a zero) would put a number on the plate that nobody measured.
    assert ephem_minor.hg_magnitude_j2000(_PY9, _PY9_JD, None) == (None, None)
    assert ephem_minor.hg_magnitude_j2000(_PY9, _PY9_JD, "n.a.") == (None,
                                                                    None)
    assert ephem_minor.hg_magnitude_j2000({}, _PY9_JD, 20.0) == (None, None)


def test_a_bigger_h_is_a_fainter_magnitude():
    # The H offset is exact in the H-G system: +1 in H is +1 mag, whatever
    # the geometry.
    a, _b = ephem_minor.hg_magnitude_j2000(_PY9, _PY9_JD, _PY9_H)
    b, _b2 = ephem_minor.hg_magnitude_j2000(_PY9, _PY9_JD, _PY9_H + 1.0)
    assert b - a == pytest.approx(1.0)
