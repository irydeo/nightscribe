############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Planner discovery-date tests
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Unit tests for the planner's disc_date resolution (object-card plan,
subplan 5c): SBDB first, NEOfixer's earliest observation as the fallback
for unconfirmed NEOCPs, PCCP mapped from the page's own column. Sources
are monkeypatched — no network.
"""

from nightscribe.core import planner


def test_fill_disc_dates_from_sbdb(monkeypatch):
    monkeypatch.setattr(planner.sbdb, "get",
                        lambda _name: {"disc_date": "2020-05-04"})
    monkeypatch.setattr(planner.neofixer, "orbit", lambda _p: None)
    targets = [{"name": "2020 JG5", "packed": "K20J05G"}]
    planner._fill_disc_dates(targets)
    assert targets[0]["disc_date"] == "2020-05-04"


def test_fill_disc_dates_neofixer_fallback(monkeypatch):
    # SBDB does not know the unconfirmed NEOCP: the preliminary orbit's
    # earliest observation stands in
    monkeypatch.setattr(planner.sbdb, "get", lambda _name: None)
    monkeypatch.setattr(planner.neofixer, "orbit",
                        lambda _p: {"disc_date": "2026-08-24"})
    targets = [{"name": "P11Xabc", "packed": "P11Xabc"}]
    planner._fill_disc_dates(targets)
    assert targets[0]["disc_date"] == "2026-08-24"


def test_fill_disc_dates_unknown_everywhere(monkeypatch):
    # no SBDB, no NEOfixer orbit: the key stays absent, no crash
    monkeypatch.setattr(planner.sbdb, "get", lambda _name: None)
    monkeypatch.setattr(planner.neofixer, "orbit", lambda _p: None)
    targets = [{"name": "ZZZ9999", "packed": "ZZZ9999"}]
    planner._fill_disc_dates(targets)
    assert "disc_date" not in targets[0]


def test_fill_disc_dates_empty_list():
    planner._fill_disc_dates([])   # must not raise, must not spawn a pool


def test_pccp_targets_carry_disc_date(monkeypatch):
    # the PCCP page already has a discovery column — the planner was
    # simply not mapping it
    monkeypatch.setattr(planner.pccp, "candidates", lambda: [
        {"desig": "P11Xabc", "discovery": "2026-09-01", "ra_deg": 10.0,
         "dec_deg": 20.0, "vmag": "20.5", "score": None, "arc": 3,
         "nobs": 5}])
    monkeypatch.setattr(planner, "_visibility", lambda *a, **k: {})
    out = planner._pccp_targets(40.0, -3.0, None, None, 0.0)
    assert len(out) == 1
    assert out[0]["disc_date"] == "2026-09-01"
