############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: SIMBAD mirror fallback
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import logging

import pytest
import requests

from nightscribe.core.sources import simbad


class _NoCacheDb:
    # Stand-in for core.db.db: no caching, fetch always runs.
    def http_get(self, _key, _source, fetch_fn):
        return fetch_fn()


class _Resp:
    def __init__(self, body=b"::data::\nSN 2023ixf | SN | 0.000811\n"):
        self.content = body

    def raise_for_status(self):
        pass


@pytest.fixture
def patched(monkeypatch):
    # @return: list of (url, script) calls plus a controllable failures set
    calls = []
    fail_urls = set()

    def fake_post(url, data=None, timeout=None):
        calls.append((url, data["script"], timeout))
        if url in fail_urls:
            raise requests.ReadTimeout(f"read timed out: {url}")
        return _Resp()

    monkeypatch.setattr(simbad, "db", _NoCacheDb())
    monkeypatch.setattr(requests, "post", fake_post)
    return calls, fail_urls


def test_primary_ok_never_touches_mirror(patched):
    calls, _fail = patched
    lines = simbad._run_script("query id X\n", "k")
    assert lines == ["SN 2023ixf | SN | 0.000811"]
    assert [c[0] for c in calls] == [simbad.URLS[0]]


def test_mirror_retry_uses_same_script(patched):
    calls, fail = patched
    fail.add(simbad.URLS[0])
    lines = simbad._run_script("query around X radius=10m\n", "k")
    assert lines == ["SN 2023ixf | SN | 0.000811"]
    assert [c[0] for c in calls] == list(simbad.URLS)
    # the exact same script goes to the mirror
    assert calls[0][1] == calls[1][1] == "query around X radius=10m\n"


def test_all_mirrors_down_returns_empty(patched, caplog):
    calls, fail = patched
    fail.update(simbad.URLS)
    with caplog.at_level(logging.WARNING, logger="nightscribe.core.sources.simbad"):
        assert simbad._run_script("query id X\n", "k") == []
    assert len(calls) == len(simbad.URLS)
    assert sum("SIMBAD script failed" in r.message for r in caplog.records) == 1


def test_around_queries_get_the_longer_timeout(patched):
    calls, _fail = patched
    simbad.query_around_galaxy("SN2023ixf", radius="3m")
    assert calls and all(c[2] == simbad.TIMEOUT_AROUND_S for c in calls)
