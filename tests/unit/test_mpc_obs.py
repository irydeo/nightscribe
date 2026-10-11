############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: MPC observations source
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offline checks for core/sources/mpc_obs.py.

Everything runs against tests/fixtures/mpc_obs_apophis.json (a real but
trimmed get-obs reply) and a faked db.http_get: no network. The fixture is
documented inside the JSON itself.
"""

import json
from pathlib import Path

import pytest
import requests

from nightscribe.core.sources import mpc_obs

FIX = Path(__file__).resolve().parent.parent / "fixtures"


def _fixture_bytes():
    # @return: raw bytes of the trimmed Apophis get-obs reply
    return (FIX / "mpc_obs_apophis.json").read_bytes()


class _CachingDb:
    # Minimal stand-in for core.db.db: a per-key cache with the same
    # cache-aside contract, so we can prove the module hits the network
    # once and that force=True bypasses the stored copy.
    def __init__(self):
        self.store = {}
        self.fetches = 0

    def http_get(self, key, source, fetch_fn, force=False):
        # @args: key - cache key, source - the source name (the module uses
        #        "mpc_obs" for the observation endpoints and "mpc_neocp_prev"
        #        for the rolling cross-reference page), fetch_fn - the
        #        module's network closure, force - bypass the cache read
        # @return: (body bytes, content_type)
        assert source in ("mpc_obs", "mpc_neocp_prev")
        if not force and key in self.store:
            return self.store[key]
        self.fetches += 1
        result = fetch_fn()
        self.store[key] = result
        return result


@pytest.fixture
def fake(monkeypatch):
    # Fakes the DB cache (patching db.http_get itself) and the HTTP call;
    # returns the cache object and the request log so a test can check the
    # key, the JSON body and how many times we hit the network.
    cache = _CachingDb()
    calls = []

    def fake_get(url, json=None, timeout=None):
        calls.append({"url": url, "json": json, "timeout": timeout})
        return _Resp(_fixture_bytes())

    monkeypatch.setattr(mpc_obs.db, "http_get", cache.http_get)
    monkeypatch.setattr(requests, "get", fake_get)
    return cache, calls


class _Resp:
    def __init__(self, body, status=200):
        self.status_code = status
        self.content = body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Client Error",
                                     response=self)


def test_iso_to_mjd_handles_z_suffix_and_bad_input():
    # 2020-12-12T14:25:30.4Z -> MJD 59195.601046 (fraction 14.42511/24)
    assert mpc_obs.iso_to_mjd("2020-12-12T14:25:30.4Z") == pytest.approx(
        59195.601046, abs=1e-5)
    # a naive timestamp is read as UTC, not as local time
    assert mpc_obs.iso_to_mjd("2020-12-12T14:25:30.4") == pytest.approx(
        59195.601046, abs=1e-5)
    assert mpc_obs.iso_to_mjd(None) is None
    assert mpc_obs.iso_to_mjd("") is None
    assert mpc_obs.iso_to_mjd("not a date") is None


def test_parse_ades_df_reads_the_fixture():
    obs = mpc_obs.parse_ades_df(json.loads(_fixture_bytes()))
    assert len(obs) == 5
    first = obs[0]
    assert first.stn == "W34"
    assert first.ra == pytest.approx(53.53118)
    assert first.dec == pytest.approx(12.77173)
    assert first.rms_ra == pytest.approx(0.15)
    assert first.rms_dec == pytest.approx(0.15)
    assert first.mag == pytest.approx(19.8)
    assert first.band == "G"
    assert first.astcat == "Gaia2"
    assert first.ref == "MPS  1158847"
    assert first.mode == "CCD"
    assert obs[-1].stn == "F51" and obs[-1].band == "Pw"


def test_parse_ades_df_keeps_missing_rms_as_none():
    # The MPC only reports rms for modern ADES submissions: absent or null
    # must stay None (a fake 0 would be read as a perfect measurement).
    obs = mpc_obs.parse_ades_df({"ADES_DF": [
        {"stn": "691", "obstime": "2004-03-15T02:35:21.696Z",
         "ra": "61.53367", "dec": "16.91794", "rmsra": None,
         "mag": None},
        {"stn": "691", "obstime": "2004-03-15T02:35:21.696Z",
         "ra": "61.53367", "dec": "16.91794"},
    ]})
    assert len(obs) == 2
    assert obs[0].rms_ra is None and obs[0].rms_dec is None
    assert obs[0].mag is None
    assert obs[1].rms_ra is None


def test_parse_ades_df_skips_status_and_rows_without_time():
    # The envelope is [payload, 200]; a row without obstime cannot be
    # placed in the timeline and is dropped, but a row without RA/Dec (an
    # occultation) is a real observation and is kept.
    data = [{"ADES_DF": [
        {"stn": "500", "obstime": None, "ra": "10.0", "dec": "10.0"},
        {"stn": "275", "obstime": "2022-04-09T08:41:13.94Z", "ra": None,
         "dec": None, "mode": "OCC"},
    ]}, 200]
    obs = mpc_obs.parse_ades_df(data)
    assert len(obs) == 1
    assert obs[0].stn == "275" and obs[0].mode == "OCC"
    assert obs[0].ra is None and obs[0].dec is None


def test_occultation_rows_count_in_history(monkeypatch):
    # Station 275 only ever saw Apophis as an occultation (no RA/Dec):
    # that row still counts as an observation, a station and a date, which
    # is exactly what the object card needs (D28).
    payload = b'[{"ADES_DF": [' \
        b'{"stn": "500", "obstime": "2021-05-20T18:48:48.96Z",' \
        b' "ra": "114.0", "dec": "30.0"},' \
        b'{"stn": "275", "obstime": "2022-04-09T08:41:13.94Z",' \
        b' "ra": null, "dec": null, "mode": "OCC"}]}, 200]'

    def fake_get(url, json=None, timeout=None):
        return _Resp(payload)

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(mpc_obs.db, "http_get", _CachingDb().http_get)
    assert mpc_obs.history("99942") == {
        "n_obs": 2, "n_stations": 2, "last_obs": "2022-04-09"}


def test_observations_hits_the_right_endpoint_and_parses(fake):
    _db, calls = fake
    obs = mpc_obs.observations("99942")
    assert len(obs) == 5
    assert calls[0]["url"] == mpc_obs.URL_OBS
    assert calls[0]["json"] == {"desigs": ["99942"],
                                "output_format": ["ADES_DF"]}


def test_observations_uses_the_cache_and_force_bypasses_it(fake):
    cache, _calls = fake
    mpc_obs.observations("99942")
    mpc_obs.observations("99942")
    assert cache.fetches == 1  # second call served from the fake cache
    mpc_obs.observations("99942", force=True)
    assert cache.fetches == 2  # force goes through to the network


def test_neocp_observations_uses_the_trksub_endpoint(fake):
    _db, calls = fake
    obs = mpc_obs.neocp_observations("P21vXYZ")
    assert len(obs) == 5
    assert calls[0]["url"] == mpc_obs.URL_NEOCP
    assert calls[0]["json"] == {"trksubs": ["P21vXYZ"],
                                "output_format": ["ADES_DF"]}


def test_observations_80_returns_the_lines_verbatim(fake):
    _db, calls = fake
    text = mpc_obs.observations_80("99942")
    lines = text.splitlines()
    assert len(lines) == 5
    assert lines[0].endswith("W34")
    assert lines[-1].endswith("F51")
    assert calls[0]["json"] == {"desigs": ["99942"],
                                "output_format": ["OBS80"]}


def test_history_counts_observations_stations_and_last_date(fake):
    hist = mpc_obs.history("99942")
    assert hist == {"n_obs": 5, "n_stations": 5, "last_obs": "2020-12-12"}


def test_unknown_object_returns_empty_without_raising(monkeypatch):
    # The NEOCP envelope answers a null ADES_DF for an unknown tracklet;
    # an empty answer must degrade to empty results, never an exception.
    def fake_get(url, json=None, timeout=None):
        return _Resp(b'[{"ADES_DF": null, "OBS80": null}, 200]')

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(mpc_obs.db, "http_get", _CachingDb().http_get)
    assert mpc_obs.observations("does-not-exist") == []
    assert mpc_obs.observations_80("does-not-exist") == ""
    assert mpc_obs.history("does-not-exist") == {
        "n_obs": 0, "n_stations": 0, "last_obs": None}


def test_network_error_returns_empty_without_raising(monkeypatch):
    def failing(key, source, fetch_fn, force=False):
        raise requests.RequestException("down")

    monkeypatch.setattr(mpc_obs.db, "http_get", failing)
    assert mpc_obs.observations("99942") == []
    assert mpc_obs.observations_80("99942") == ""
    assert mpc_obs.history("99942") == {
        "n_obs": 0, "n_stations": 0, "last_obs": None}


# ------------------------------------------ the missing NEOCP reference path

# A trimmed slice of the MPC's rolling "Previous NEOCP Objects" table: the
# first row is a confirmed object (temp -> designation + MPEC), the second
# left the page WITHOUT a designation (moved to the PCCP) and must be
# skipped, or the check would fetch an object that does not exist.
_NEOCP_PREV_HTML = """
<table><tbody>
<tr>
<td>A11HPKO</td>
<td><a href="https://www.minorplanetcenter.net/db_search/show_object?
utf8=True&amp;object_id=2026+TQ8" target="_blank">2026 TQ8</a></td>
<td>None</td>
<td><a href="https://www.minorplanetcenter.net/mpec/K26/K26TK1.html"
target="_blank">MPEC 2026-T201</a></td>
<td>2026-10-10T00:07:53</td>
</tr>
<tr>
<td>A11HQSs</td>
<td>None</td>
<td>None</td>
<td>None</td>
<td>2026-10-10T06:12:42</td>
</tr>
</tbody></table>
"""


def test_parse_neocp_prev_maps_a_temp_designation_to_the_confirmed_one():
    table = mpc_obs.parse_neocp_prev(_NEOCP_PREV_HTML)
    assert table["A11HPKO"] == {
        "designation": "2026 TQ8",
        "mpec": "MPEC 2026-T201",
        "mpec_url": "https://www.minorplanetcenter.net/mpec/K26/K26TK1.html",
        "confirmed_at": "2026-10-10T00:07:53"}
    # a row that left the page without a designation is not a mapping
    assert "A11HQSs" not in table


def test_parse_neocp_prev_accepts_bytes_and_empty_input():
    assert mpc_obs.parse_neocp_prev(_NEOCP_PREV_HTML.encode()) == \
        mpc_obs.parse_neocp_prev(_NEOCP_PREV_HTML)
    assert mpc_obs.parse_neocp_prev("") == {}
    assert mpc_obs.parse_neocp_prev(None) == {}


def test_neocp_observations_80_uses_the_trksub_endpoint(monkeypatch):
    calls = []

    def fake_get(url, json=None, timeout=None):
        calls.append({"url": url, "json": json})
        return _Resp(b'[{"ADES_DF": null, '
                     b'"OBS80": "LINE-1\\nLINE-2"}, 200]')

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(mpc_obs.db, "http_get", _CachingDb().http_get)
    text = mpc_obs.neocp_observations_80("A11HQSz")
    assert text.splitlines() == ["LINE-1", "LINE-2"]
    assert calls[0]["url"] == mpc_obs.URL_NEOCP
    assert calls[0]["json"] == {"trksubs": ["A11HQSz"],
                                "output_format": ["OBS80"]}


def test_resolve_neocp_alias_reads_the_rolling_page(monkeypatch):
    monkeypatch.setattr(mpc_obs, "neocp_prev",
                        lambda force=False: {"A11HPKO": {
                            "designation": "2026 TQ8",
                            "mpec": "MPEC 2026-T201",
                            "confirmed_at": "2026-10-10T00:07:53"}})
    hit = mpc_obs.resolve_neocp_alias("A11HPKO")
    assert hit["designation"] == "2026 TQ8" and hit["mpec"] == "MPEC 2026-T201"
    assert mpc_obs.resolve_neocp_alias("NOT-THERE") is None


def test_reference_80_tries_confirmed_then_neocp_then_alias(monkeypatch):
    # The whole strategy in one place: a designated object comes from the
    # confirmed endpoint; one still on the NEOCP from the trksub endpoint;
    # and a temporary name confirmed SINCE THE VISIT (A11HPKO -> 2026 TQ8)
    # is resolved and fetched under its real name.
    monkeypatch.setattr(
        mpc_obs, "observations_80",
        lambda d, force=False: "LINE-A\n" if d == "2026 TQ8" else "")
    monkeypatch.setattr(
        mpc_obs, "neocp_observations_80",
        lambda d, force=False: "LINE-N\n" if d == "A11HQSs" else "")
    monkeypatch.setattr(
        mpc_obs, "resolve_neocp_alias",
        lambda d, force=False: ({"designation": "2026 TQ8",
                                 "mpec": "MPEC 2026-T201",
                                 "confirmed_at": "2026-10-10T00:07:53"}
                                if d == "A11HPKO" else None))
    confirmed = mpc_obs.reference_80("2026 TQ8")
    assert confirmed.source == "MPC" and confirmed.lines == "LINE-A\n"
    neocp = mpc_obs.reference_80("A11HQSs")
    assert neocp.source == "NEOCP" and neocp.lines == "LINE-N\n"
    renamed = mpc_obs.reference_80("A11HPKO")
    assert renamed.source == "MPC" and renamed.designation == "2026 TQ8"
    assert renamed.mpec == "MPEC 2026-T201" and renamed.lines == "LINE-A\n"


def test_reference_80_says_so_when_there_is_nothing(monkeypatch):
    monkeypatch.setattr(mpc_obs, "observations_80", lambda d, force=False: "")
    monkeypatch.setattr(mpc_obs, "neocp_observations_80",
                        lambda d, force=False: "")
    monkeypatch.setattr(mpc_obs, "resolve_neocp_alias",
                        lambda d, force=False: None)
    ref = mpc_obs.reference_80("ZZZ9999")
    assert ref.source == "" and not ref.lines
    assert "no published observations" in ref.note


def test_reference_80_flags_when_our_station_is_already_published(monkeypatch):
    # "Tus datos están en ese MPEC": our station already among the published
    # lines is the fact the rename notice leans on.
    line = " " * 77 + "Z41"
    monkeypatch.setattr(mpc_obs, "observations_80",
                        lambda d, force=False: line + "\n")
    monkeypatch.setattr(mpc_obs, "neocp_observations_80",
                        lambda d, force=False: "")
    assert mpc_obs.reference_80("X", obs_code="Z41").ours_present is True
    assert mpc_obs.reference_80("X", obs_code="W99").ours_present is False
