############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - unit tests: VizieR source (ADR-042)
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
import requests

from nightscribe.core.sources import vizier

FIX = Path(__file__).resolve().parent.parent / "fixtures"


def _fixture(name):
    return (FIX / name).read_bytes()


def test_parse_tsv_gaia():
    headers, rows = vizier.parse_tsv(
        _fixture("vizier_gaia.tsv").decode("utf-8"), "Gmag")
    assert "Gmag" in headers and "BPmag" in headers
    # 9 data rows, all with numeric coordinates (mag may be blank)
    assert len(rows) == 9
    assert rows[0]["Source"] == "2100000000000001"
    assert float(rows[0]["RAJ2000"]) == pytest.approx(291.366)


def test_parse_tsv_missing_header_returns_empty():
    headers, rows = vizier.parse_tsv("# nothing\nA\tB\n1\t2\n", "Gmag")
    assert headers == [] and rows == []


def test_parse_tsv_drops_rows_without_coordinates():
    text = "Source\tRAJ2000\tDEJ2000\tGmag\n1\t\t42.7\t12.3\n"
    headers, rows = vizier.parse_tsv(text, "Gmag")
    assert rows == []


def test_catalog_url_carries_the_query():
    url = vizier._catalog_url(vizier.CATALOGS["gaia"], 291.366, 42.784,
                              13.5, vizier.CATALOGS["gaia"]["fields"], 100)
    assert url.startswith(vizier.VIZIER_URL)
    # requests.utils.quote keeps "/" safe by default
    assert "-source=I/350/gaiaedr3" in url
    assert "-c=291.366%2042.784" in url
    assert "-c.r=13.5" in url
    assert "-out=Source" in url
    url_all = vizier._catalog_url(vizier.CATALOGS["gaia"], 1.0, 2.0, 5.0,
                                  "all", 100)
    assert "-out.all=1" in url_all


def test_cone_search_uses_the_cache_and_parses(monkeypatch):
    calls = []

    def fake_http_get(key, source, fetch, force=False):
        calls.append((key, source))
        return _fixture("vizier_gaia.tsv"), "text/tab-separated-values"

    monkeypatch.setattr(vizier.db, "http_get", fake_http_get)
    res = vizier.cone_search("gaia", 291.366, 42.784, 13.5)
    assert res is not None
    headers, rows = res
    assert len(rows) == 9
    assert calls[0][1] == "vizier"
    assert "I/350/gaiaedr3" in calls[0][0]
    assert "291.3660" in calls[0][0]


def test_cone_search_network_error_returns_none(monkeypatch):
    def failing(key, source, fetch, force=False):
        raise requests.RequestException("down")

    monkeypatch.setattr(vizier.db, "http_get", failing)
    assert vizier.cone_search("gaia", 291.366, 42.784, 13.5) is None


def test_cone_search_unknown_catalog_returns_none():
    assert vizier.cone_search("hipparcos", 1.0, 2.0, 5.0) is None


def test_cone_search_retries_with_all_columns(monkeypatch):
    # First answer lacks BP/RP (probe coverage 1/3); the -out.all retry
    # recovers them and wins.
    calls = []

    def fake_http_get(key, source, fetch, force=False):
        calls.append(key)
        if key.endswith(":all"):
            return _fixture("vizier_gaia.tsv"), "text/tab-separated-values"
        return (_fixture("vizier_gaia_truncated.tsv"),
                "text/tab-separated-values")

    monkeypatch.setattr(vizier.db, "http_get", fake_http_get)
    res = vizier.cone_search("gaia", 291.366, 42.784, 13.5)
    assert res is not None
    headers, rows = res
    assert "BPmag" in headers and "RPmag" in headers
    assert len(rows) == 9
    assert any(k.endswith(":all") for k in calls)


def test_cone_search_keeps_first_answer_when_retry_fails(monkeypatch):
    def fake_http_get(key, source, fetch, force=False):
        if key.endswith(":all"):
            raise requests.RequestException("down")
        return (_fixture("vizier_gaia_truncated.tsv"),
                "text/tab-separated-values")

    monkeypatch.setattr(vizier.db, "http_get", fake_http_get)
    res = vizier.cone_search("gaia", 291.366, 42.784, 13.5)
    assert res is not None
    assert "Gmag" in res[0] and len(res[1]) == 2
