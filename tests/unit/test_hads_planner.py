############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: HADS planner phase (subplan A.1)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import datetime

import pytest

from nightscribe.core import hads, horizon, planner

LAT, LON = 28.3, -16.5          # Irydeo-ish site
DATE = datetime.date(2026, 9, 11)


def _star(name, ra_deg, dec_deg, period_h, max_mag=10.4, min_mag=11.0):
    # @return: a minimal catalog star dict as hads.catalog() would return
    return {"name": name, "aliases": [], "ra_deg": ra_deg, "dec_deg": dec_deg,
            "max": max_mag, "min": min_mag, "period_h": period_h,
            "multiperiodic": False, "non_radial": False, "amp_change": False,
            "priority": None, "observed": True, "coverage": {}}


def _targets(monkeypatch, stars, limit_mag=14.0):
    monkeypatch.setattr(hads, "catalog", lambda merge_online=True: stars)
    hor = horizon.FlatHorizon(10.0)
    return planner._hads_targets(LAT, LON, DATE, hor, limit_mag=limit_mag)


def test_phases_include_hads_before_scoring():
    assert "hads" in planner.PHASES
    assert planner.PHASES.index("hads") < planner.PHASES.index("scoring")


def test_circumpolar_star_is_listed_with_cycles(monkeypatch):
    # dec +80 from lat 28.3 with a 10-degree horizon: up all night long
    out = _targets(monkeypatch, [_star("TEST One", 10.0, 80.0, 2.0)])
    assert len(out) == 1
    t = out[0]
    assert t["kind"] == "hads" and t["id"] == "TEST One"
    assert t["mag"] == 10.7                       # median of 10.4/11.0 (H-e)
    h = t["hads"]
    assert h["cycles"] == round(t["hours_up"] / 2.0, 1)
    assert h["cycles"] > 1
    assert h["session_fits"] is True              # 2P=4 h fits in the night
    assert h["session_req_h"] == 4.0
    assert t["window_start"] is not None and t["best_time"] is not None


def test_star_never_up_is_excluded(monkeypatch):
    out = _targets(monkeypatch, [_star("TEST Two", 10.0, -70.0, 2.0)])
    assert out == []


def test_longer_period_than_the_span_is_excluded(monkeypatch):
    # up all night (~11 h) but the cycle (30 h) never completes (H-a gate)
    out = _targets(monkeypatch, [_star("TEST Three", 10.0, 80.0, 30.0)])
    assert out == []


def test_two_periods_not_fitting_sets_session_flag(monkeypatch):
    # one 6 h cycle fits in the ~11 h window, but the 2P session (12 h) does not
    out = _targets(monkeypatch, [_star("TEST Four", 10.0, 80.0, 6.0)])
    assert len(out) == 1
    assert out[0]["hads"]["session_fits"] is False
    assert out[0]["hads"]["cycles"] >= 1


def test_median_magnitude_gate(monkeypatch):
    faint = _star("TEST Five", 10.0, 80.0, 2.0, max_mag=15.0, min_mag=16.0)
    assert _targets(monkeypatch, [faint], limit_mag=14.0) == []
    assert len(_targets(monkeypatch, [faint], limit_mag=16.0)) == 1


def test_broken_star_rows_are_skipped(monkeypatch):
    broken = _star("TEST Six", 10.0, 80.0, 2.0)
    broken["period_h"] = None
    out = _targets(monkeypatch, [broken, _star("TEST Seven", 10.0, 80.0, 2.0)])
    assert [t["id"] for t in out] == ["TEST Seven"]
