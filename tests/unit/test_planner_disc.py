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


class _Cfg:
    def __init__(self, code):
        self._v = {"lat": 40.0, "lon": -3.0, "limit_mag": 20.0,
                   "mpc_code": code}

    def get(self, key, default=None):
        return self._v.get(key, default)


def test_site_code_falls_back_to_the_geocentric_500():
    # NEOfixer REJECTS an empty site, so an observer with only coordinates got
    # no NEOs at all, in silence. The planning site falls back to 500
    # (geocentric), which is honest for planning and never written to the
    # config (2026-10-14).
    assert planner.site_code(_Cfg("Z41")) == "Z41"
    assert planner.site_code(_Cfg("")) == "500"
    assert planner.site_code(_Cfg(None)) == "500"


def test_build_tonight_asks_neofixer_for_the_geocentric_site(monkeypatch):
    # The fix end to end: with no MPC code the NEO stage is asked for site
    # 500 instead of an empty site (which returns nothing).
    seen = {}

    def _fake_neo(site, *a, **k):
        seen["site"] = site
        return []
    monkeypatch.setattr(planner, "_neo_targets", _fake_neo)
    for name in ("_sn_targets", "_comet_targets", "_pccp_targets",
                 "_transit_targets", "_hads_targets", "_campaign_targets",
                 "_vigil_targets", "_aavso_targets", "_approach_alerts"):
        monkeypatch.setattr(planner, name, lambda *a, **k: [])
    monkeypatch.setattr(planner.vigils, "check_vigils", lambda _cfg: {})
    monkeypatch.setattr(planner, "_aavso_fetch", lambda _cfg: [])
    monkeypatch.setattr(planner, "_transit_aperture", lambda _cfg: None)
    monkeypatch.setattr(planner, "_transit_plate_scale", lambda _cfg: None)
    planner.build_tonight(_Cfg(""), date=None)
    assert seen["site"] == "500"
