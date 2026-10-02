############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: site detection sources (geo)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The IP geolocation and elevation sources behind "Find my location".

Two real bugs lived here (2026-10-02) and these tests pin them shut:

  * open-meteo answers {"elevation": [666.0]}, a LIST; reading it as a
    number raised a TypeError the caller did not catch, so the button died
    with "Finding your observatory..." still on screen;
  * ipwho.is (the fallback provider) spells the country "country", not
    "country_name", so the suggested name lost the country.

No network: the HTTP layer is stubbed.
"""

import json

import pytest


@pytest.fixture()
def geo(monkeypatch):
    from nightscribe.core.sources import geo as mod
    return mod


def _payload(geo, monkeypatch, body):
    # Stubs the cache/HTTP layer with a canned JSON body.
    def fake(key, kind, fetch, force=False):
        return json.dumps(body).encode("utf-8"), "application/json"
    monkeypatch.setattr(geo.db, "http_get", fake)


def test_parse_accepts_both_provider_shapes(geo):
    # ipapi.co
    out = geo._parse({"latitude": 40.4, "longitude": -3.7,
                      "city": "Madrid", "country_name": "Spain"})
    assert out == {"lat": 40.4, "lon": -3.7, "name": "Madrid, Spain"}
    # ipwho.is
    out = geo._parse({"latitude": 40.4, "longitude": -3.7,
                      "city": "Madrid", "country": "Spain"})
    assert out == {"lat": 40.4, "lon": -3.7, "name": "Madrid, Spain"}


def test_parse_survives_a_missing_city(geo):
    out = geo._parse({"latitude": 1.0, "longitude": 2.0})
    assert out["name"] == "your location"
    assert geo._parse({"latitude": "nope", "longitude": 2.0}) is None


def test_elevation_reads_the_list_payload(geo, monkeypatch):
    # the real shape: a list, one value per requested point
    _payload(geo, monkeypatch, {"elevation": [666.0]})
    assert geo.elevation(40.4, -3.7) == 666


def test_elevation_still_reads_a_bare_number(geo, monkeypatch):
    _payload(geo, monkeypatch, {"elevation": 12.4})
    assert geo.elevation(40.4, -3.7) == 12


def test_elevation_never_raises(geo, monkeypatch):
    # A shape nobody expected must come back as None, not as a traceback
    # escaping into the button that called it.
    _payload(geo, monkeypatch, {"elevation": ["oops"]})
    assert geo.elevation(40.4, -3.7) is None
    _payload(geo, monkeypatch, {})
    assert geo.elevation(40.4, -3.7) is None
    _payload(geo, monkeypatch, {"elevation": []})
    assert geo.elevation(40.4, -3.7) is None
