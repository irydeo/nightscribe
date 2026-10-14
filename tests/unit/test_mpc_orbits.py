############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: MPC orbits source (ADR-087)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offline checks for core/sources/mpc_orbits.py.

Everything runs against tests/fixtures/mpc_orb_2026tg69.json (a trimmed but
real get-orb reply) and a faked db.http_get: no network. The fixture is the
object that made the point: the MPC's API says Apollo while its db_search page
says Amor, and JPL says Apollo.
"""

import json
from pathlib import Path

import pytest
import requests

from nightscribe.core.sources import mpc_orbits

FIX = Path(__file__).resolve().parent.parent / "fixtures"


def _fixture_bytes():
    return (FIX / "mpc_orb_2026tg69.json").read_bytes()


class _CachingDb:
    # The cache-aside contract of core.db.db: hit once, and force bypasses.
    def __init__(self):
        self.store = {}
        self.fetches = 0

    def http_get(self, key, source, fetch_fn, force=False):
        assert source == "mpc_orbits"
        if not force and key in self.store:
            return self.store[key]
        self.fetches += 1
        result = fetch_fn()
        self.store[key] = result
        return result


class _Resp:
    def __init__(self, body, status=200):
        self.status_code = status
        self.content = body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Client Error",
                                     response=self)


@pytest.fixture
def fake(monkeypatch):
    cache = _CachingDb()
    calls = []

    def fake_get(url, json=None, timeout=None):
        calls.append({"url": url, "json": json, "timeout": timeout})
        return _Resp(_fixture_bytes())

    monkeypatch.setattr(mpc_orbits.db, "http_get", cache.http_get)
    monkeypatch.setattr(requests, "get", fake_get)
    return cache, calls


def test_get_orb_reads_the_official_type_and_elements(fake):
    _cache, calls = fake
    orb = mpc_orbits.get_orb("2026 TG69")
    assert orb["orbit_type"] == "Apollo"
    assert orb["packed"] == "K26T69G"
    assert orb["designation"] == "2026 TG69"
    assert orb["elements"]["a"] == pytest.approx(1.7960513594394207)
    assert orb["elements"]["e"] == pytest.approx(0.442621999590748)
    assert orb["elements"]["i"] == pytest.approx(26.608933666309)
    # q and Q are not in the KEP block: they are derived from a and e
    assert orb["elements"]["q"] == pytest.approx(
        1.7960513594394207 * (1 - 0.442621999590748))
    assert orb["moid"]["Earth"] == pytest.approx(0.02254)
    assert calls[0]["url"] == mpc_orbits.URL_ORB
    assert calls[0]["json"] == {"desig": "2026 TG69"}


def test_get_orb_uses_the_cache_and_force_bypasses_it(fake):
    cache, _calls = fake
    assert mpc_orbits.get_orb("2026 TG69")["orbit_type"] == "Apollo"
    assert mpc_orbits.get_orb("2026 TG69")["orbit_type"] == "Apollo"
    assert cache.fetches == 1                 # the second read is cached
    mpc_orbits.get_orb("2026 TG69", force=True)
    assert cache.fetches == 2                 # force re-reads


def test_get_orb_returns_none_for_an_unknown_object(monkeypatch, fake):
    monkeypatch.setattr(requests, "get",
                        lambda *a, **k: _Resp(b'[{"mpc_orb": []}, 200]'))
    assert mpc_orbits.get_orb("NOT-THERE") is None


def test_get_orb_returns_none_without_a_name(fake):
    assert mpc_orbits.get_orb("") is None
    assert mpc_orbits.get_orb(None) is None


def test_network_error_returns_none(monkeypatch):
    def boom(*_a, **_k):
        raise requests.ConnectionError("offline")
    monkeypatch.setattr(mpc_orbits.db, "http_get",
                        lambda *a, **k: boom())
    assert mpc_orbits.get_orb("2026 TG69") is None


def test_parse_orb_handles_a_missing_kep_block():
    orb = mpc_orbits.parse_orb({"categorization": {"orbit_type_str": "Amor"}})
    assert orb["orbit_type"] == "Amor"
    assert orb["elements"] == {} and orb["packed"] == ""


def _fake_small_body(monkeypatch, orbit_type):
    # A confirmed NEO whose local q rule says Apollo (q = 1.796*(1-0.4426)).
    from nightscribe.core import enrich
    monkeypatch.setattr(enrich.sbdb, "get", lambda name, force=False: {
        "des": "2026 TG69",
        "elements": {"a": 1.796, "e": 0.4426, "i": 26.6},
        "phys": {"H": 25.8}, "orbit_code": "APO"})
    monkeypatch.setattr(enrich.horizons, "ephemeris", lambda *a, **k: [])
    monkeypatch.setattr(enrich.cad, "next_approach", lambda *a, **k: None)
    monkeypatch.setattr(
        enrich.mpc_orbits, "get_orb",
        lambda name, force=False: {"orbit_type": orbit_type})
    return enrich


def test_the_mpc_type_overrides_the_local_classification(monkeypatch):
    # ADR-087: the observer reads the MPC's page, so the MPC's own type wins
    # when it is one of the NEO families (and it can differ from JPL and from
    # our q rule).
    enrich = _fake_small_body(monkeypatch, "Amor")
    out = enrich._enrich_small_body("2026 TG69", None, "Z41")
    assert out["family"] == "Amor"
    assert out["family_source"] == "MPC"
    assert out["mpc_orbit_type"] == "Amor"


def test_a_non_neo_mpc_type_keeps_our_classification(monkeypatch):
    # The MPC's other labels (Mars Crosser, Hungaria, ...) do not match our
    # FAMILIES keys, so our own rule stays and the source is left empty.
    enrich = _fake_small_body(monkeypatch, "Hungaria")
    out = enrich._enrich_small_body("2026 TG69", None, "Z41")
    assert out["family"] == "Apollo"      # our q-based rule
    assert out["family_source"] == ""
