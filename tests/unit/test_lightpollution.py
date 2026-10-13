############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: light pollution source (ADR-083)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The atlas returns the ARTIFICIAL zenith radiance; the site documents the
exact conversion to mag/arcsec2 (FAQ #31). These tests pin the conversion (the
natural sky must come out at 22.0) and the no-key / cached behaviour.
"""

import requests
import pytest

from nightscribe.core.sources import lightpollution


class _Resp:
    def __init__(self, text):
        self.text = text


@pytest.fixture
def lp_db(tmp_db, monkeypatch):
    monkeypatch.setattr(lightpollution, "db", tmp_db)
    return tmp_db


def test_a_natural_sky_is_22():
    # zero artificial radiance -> the natural floor -> exactly 22.0 mag/arcsec2
    assert abs(lightpollution.mpsas_from_artificial(0.0) - 22.0) < 1e-6


def test_doubling_the_radiance_darkens_by_0_75():
    # twice the radiance is 2x the flux -> -0.75 mag
    base = lightpollution.mpsas_from_artificial(0.171168465)
    assert abs((22.0 - base) - 0.75) < 0.01


def test_no_key_is_a_named_error():
    with pytest.raises(lightpollution.LightPollutionError, match="key"):
        lightpollution.sky_brightness_mpsas(40.0, -3.0, "")


def test_query_converts_and_caches(lp_db, monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(params)
        return _Resp('{"value": 0.171168465}')

    monkeypatch.setattr(lightpollution.requests, "get", fake_get)
    first = lightpollution.sky_brightness_mpsas(40.0, -3.0, "KEY")
    second = lightpollution.sky_brightness_mpsas(40.0, -3.0, "KEY")
    assert abs(first - 21.25) < 0.01
    assert first == second
    assert len(calls) == 1            # cached (30 days)
    assert calls[0]["qd"] == "-3.000000,40.000000"


def test_transport_error_is_wrapped(lp_db, monkeypatch):
    def boom(url, params=None, timeout=None):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(lightpollution.requests, "get", boom)
    with pytest.raises(lightpollution.LightPollutionError):
        lightpollution.sky_brightness_mpsas(40.0, -3.0, "KEY")
