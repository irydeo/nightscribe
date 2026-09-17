############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - unit tests: ALeRCE survey context (Track V, V0.9)
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

from nightscribe.core.sources import surveys

FIX = Path(__file__).resolve().parent.parent / "fixtures"


def _fake_http_get(key, source, fetch, force=False):
    if key.startswith("surveys:cone:"):
        return (FIX / "alerce_conesearch_wesb1.json").read_bytes(), \
            "application/json"
    return (FIX / "alerce_lightcurve_wesb1.json").read_bytes(), \
        "application/json"


def test_fetch_points_happy_path(monkeypatch):
    monkeypatch.setattr(surveys.db, "http_get", _fake_http_get)
    pts = surveys.fetch_points(15.2254, 55.0667)
    assert len(pts) == 40                       # the trimmed fixture
    p = pts[0]
    assert p["source"] == "survey:ztf"
    assert p["filter"] in ("g", "r", "i")
    assert 15.0 < p["mag"] < 18.0               # WeSb 1 in ZTF
    assert p["mjd"] > 58000


def test_fetch_points_network_failure_returns_empty(monkeypatch):
    import requests

    def failing(key, source, fetch, force=False):
        raise requests.RequestException("no network")
    monkeypatch.setattr(surveys.db, "http_get", failing)
    assert surveys.fetch_points(15.2254, 55.0667) == []


# ---------------- 2026-09-17: ok / empty / error reporting ---------------

def test_fetch_points_detailed_ok(monkeypatch):
    monkeypatch.setattr(surveys.db, "http_get", _fake_http_get)
    out = surveys.fetch_points_detailed(15.2254, 55.0667)
    assert out["status"] == "ok"
    assert len(out["points"]) == 40
    assert out["points"][0]["source"] == "survey:ztf"
    assert out["error"] is None


def test_fetch_points_detailed_empty_no_object(monkeypatch):
    # a valid conesearch answer with no matches at all
    import json

    def no_match(key, source, fetch, force=False):
        return (json.dumps({"items": []}).encode(), "application/json")
    monkeypatch.setattr(surveys.db, "http_get", no_match)
    out = surveys.fetch_points_detailed(15.2254, 55.0667)
    assert out["status"] == "empty"
    assert out["points"] == []
    assert out["error"] is None


def test_fetch_points_detailed_empty_no_detections(monkeypatch):
    # an object is found, but the survey has never detected it
    import json

    def lc_only(key, source, fetch, force=False):
        if key.startswith("surveys:cone:"):
            return ((FIX / "alerce_conesearch_wesb1.json").read_bytes(),
                    "application/json")
        return (json.dumps({"detections": []}).encode(),
                "application/json")
    monkeypatch.setattr(surveys.db, "http_get", lc_only)
    out = surveys.fetch_points_detailed(15.2254, 55.0667)
    assert out["status"] == "empty"
    assert out["points"] == []


def test_fetch_points_detailed_error_reports_reason(monkeypatch):
    import requests

    def failing(key, source, fetch, force=False):
        raise requests.RequestException("no network")
    monkeypatch.setattr(surveys.db, "http_get", failing)
    out = surveys.fetch_points_detailed(15.2254, 55.0667)
    assert out["status"] == "error"
    assert out["points"] == []
    assert "no network" in out["error"]


def test_to_points_falls_back_to_raw_psf_when_corr_invalid():
    det = {"mjd": 59000.0, "fid": 2, "magpsf": 15.5, "sigmapsf": 0.02,
           "magpsf_corr": None, "sigmapsf_corr_ext": None}
    pts = surveys._to_points({"detections": [det]})
    assert pts == [{"mjd": 59000.0, "filter": "r", "mag": 15.5,
                    "err": 0.02, "source": "survey:ztf"}]
