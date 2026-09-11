############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - unit tests: VSX source (Track V, V0.8)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

from pathlib import Path

import pytest

from nightscribe.core.sources import vsx

FIX = Path(__file__).resolve().parent.parent / "fixtures"


def _fixture(name):
    return (FIX / name).read_bytes()


def test_parse_t_crb():
    v = vsx.parse_object(_fixture("vsx_t_crb.json"))
    assert v["name"] == "T CrB"
    assert v["auid"] == "000-BBW-825"
    assert v["ra_deg"] == pytest.approx(239.87567)
    assert v["dec_deg"] == pytest.approx(25.92017)
    assert v["var_type"] == "NR+ELL"
    assert v["period_d"] == pytest.approx(227.5528)
    assert v["epoch_mjd"] == pytest.approx(2455828.9 - 2400000.5)
    assert v["max"] == 2.0 and v["max_band"] == "V"
    assert v["min"] == 10.8 and v["min_band"] == "V"
    assert v["spectral"] == "M3III+WD"


def test_parse_mira_and_eclipsing():
    mira = vsx.parse_object(_fixture("vsx_omi_cet.json"))
    assert mira["var_type"] == "M"
    assert mira["period_d"] == pytest.approx(331.3)
    ee = vsx.parse_object(_fixture("vsx_ee_cep.json"))
    assert ee["var_type"] == "E-DO"


def test_parse_not_found_is_none():
    assert vsx.parse_object(_fixture("vsx_not_found.json")) is None
    assert vsx.parse_object(b"broken") is None


def test_lookup_uses_the_cache_and_swallows_network_errors(monkeypatch):
    calls = []

    def fake_http_get(key, source, fetch, force=False):
        calls.append(key)
        return _fixture("vsx_t_crb.json"), "application/json"

    monkeypatch.setattr(vsx.db, "http_get", fake_http_get)
    v = vsx.lookup("T CrB")
    assert v["name"] == "T CrB"
    assert calls == ["vsx:object:T CrB"]

    import requests
    def failing(key, source, fetch, force=False):
        raise requests.RequestException("no network")
    monkeypatch.setattr(vsx.db, "http_get", failing)
    assert vsx.lookup("T CrB") is None
