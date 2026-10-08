############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: SBDB parenthetical-name retry
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import pytest
import requests

from nightscribe.core.sources import sbdb


class _NoCacheDb:
    # Stand-in for core.db.db: no caching, fetch always runs.
    def http_get(self, _key, _source, fetch_fn, **_kw):
        return fetch_fn()


class _Resp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self.content = body or (
            b'{"object": {"fullname": "P/2020 G1 (Pimentel)",'
            b' "des": "P/2020 G1"}, "orbit": {"elements": []},'
            b' "phys_par": []}')

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Client Error",
                                     response=self)


@pytest.fixture
def patched(monkeypatch):
    # @return: list of sstr values SBDB was queried with
    calls = []
    fail_sstr = set()

    def fake_get(_url, params=None, timeout=None):
        sstr = params["sstr"]
        calls.append(sstr)
        if sstr in fail_sstr:
            return _Resp(status=400)
        return _Resp()

    monkeypatch.setattr(sbdb, "db", _NoCacheDb())
    monkeypatch.setattr(requests, "get", fake_get)
    return calls, fail_sstr


def test_400_on_parenthetical_retries_short_name(patched):
    calls, fail = patched
    fail.add("P/2020 G1 (Pimentel)")
    body = sbdb.get("P/2020 G1 (Pimentel)")
    assert body and body["des"] == "P/2020 G1"
    assert calls == ["P/2020 G1 (Pimentel)", "P/2020 G1"]


def test_400_without_parenthetical_does_not_retry(patched):
    calls, fail = patched
    fail.add("NoSuchThing123")
    assert sbdb.get("NoSuchThing123") is None
    assert calls == ["NoSuchThing123"]


def test_plain_name_never_retries(patched):
    calls, _fail = patched
    body = sbdb.get("29P")
    assert body and body["des"] == "P/2020 G1"
    assert calls == ["29P"]


def test_the_epoch_travels_with_the_elements():
    # orbit.epoch is NOT one of the element rows. Dropping it made every
    # local propagation freeze the mean anomaly at its value at the solution
    # epoch (measured: 82 deg of error on 2026 PY9). It has to be carried.
    body = sbdb.parse_sbdb({
        "object": {"des": "2026 PY9", "fullname": "(2026 PY9)"},
        "orbit": {"epoch": "2461200.5", "elements": [
            {"name": "a", "value": "2.329264345717"},
            {"name": "e", "value": ".5508738138610355"},
            {"name": "ma", "value": "333.0"}]},
        "phys_par": []})
    assert body["elements"]["epoch"] == pytest.approx(2461200.5)
    assert body["elements"]["a"] == pytest.approx(2.329264345717)


def test_the_lookup_asks_for_full_precision_and_versions_the_key(monkeypatch):
    # Without full-prec=1 SBDB answers "a": "2.33": three figures, useless to
    # propagate. And the cache key carries the flag, so a body cached before
    # it is never reused.
    seen = {}
    keys = []

    class _Db:
        def http_get(self, key, source, fetch_fn, **_kw):
            keys.append(key)
            return fetch_fn()

    def fake_get(_url, params=None, timeout=None):
        seen.update(params or {})
        return _Resp()

    monkeypatch.setattr(sbdb, "db", _Db())
    monkeypatch.setattr(requests, "get", fake_get)
    sbdb.get("2026 PY9")
    assert seen.get("full-prec") == "1"
    assert keys == ["sbdb:2026 PY9:fp"]
