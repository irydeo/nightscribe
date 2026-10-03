############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: nearest-place lookup (core/places.py)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Naming a clicked point from the bundled city list.

No network: the list is an asset, and the whole point of using it is that
the answer is instant and offline.
"""

import pytest


@pytest.fixture()
def places():
    from nightscribe.core import places as mod
    return mod


def test_distance_is_a_great_circle(places):
    # Madrid to Barcelona is about 505 km
    km = places.distance_km(40.4168, -3.7038, 41.3874, 2.1686)
    assert 500 < km < 510
    assert places.distance_km(10.0, 20.0, 10.0, 20.0) == 0.0


def test_nearest_finds_the_city(places):
    near = places.nearest(40.41678, -3.70379)
    assert near is not None
    assert near["name"] == "Madrid, Spain"
    assert near["km"] < 5.0


def test_nearest_refuses_to_guess_far_away(places):
    # Middle of the Atlantic: the nearest city is hundreds of km away, and
    # naming the point after it would be confidently wrong.
    assert places.nearest(0.0, -30.0) is None
    assert places.nearest(0.0, -30.0, max_km=5000.0) is not None


def test_label_falls_back_to_the_coordinates(places):
    text = places.label(0.0, -30.0)
    assert "N" in text and "W" in text
    assert "30.0000" in text
    # and it goes through the translator for the hemisphere letters, where
    # west is W in English and O in Spanish
    seen = []
    text = places.label(0.0, -30.0, lambda s: seen.append(s) or {"W": "O"}.get(s, s))
    assert text.endswith("O")
    assert seen == ["N", "W"]


def test_label_returns_the_city_when_there_is_one(places):
    assert places.label(40.41678, -3.70379) == "Madrid, Spain"


def test_the_asset_is_complete(places):
    rows = places._load()
    assert len(rows) > 1000
    for name, country, lon, lat in rows[:50]:
        assert name and isinstance(name, str)
        assert -180.0 <= lon <= 180.0
        assert -90.0 <= lat <= 90.0
