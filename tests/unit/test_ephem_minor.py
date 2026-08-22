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
