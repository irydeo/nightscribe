############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: HADS catalog module (subplan H0.4)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

from datetime import date

from nightscribe.core import hads
from nightscribe.core.sources import hads_sheet


# ---------------- bundled catalog ----------------

def test_bundled_catalog_parses_all_stars():
    stars = hads.catalog_bundled()
    assert len(stars) == 168
    gp = next(s for s in stars if s["name"] == "GP And")
    assert "GSC 01739-01964" in gp["aliases"]
    assert abs(gp["ra_deg"] - 13.825) < 0.01
    assert abs(gp["dec_deg"] - 23.164) < 0.01
    assert gp["period_h"] == 1.89
    # text flags from the Name cell (verified counts in the real CSV)
    assert sum(1 for s in stars if s["multiperiodic"]) == 10
    assert sum(1 for s in stars if s["non_radial"]) == 3
    assert sum(1 for s in stars if s["amp_change"]) == 1


def test_bundled_catalog_name_forms():
    stars = {s["name"]: s for s in hads.catalog_bundled()}
    lr = stars["LR Psc"]
    assert set(lr["aliases"]) == {"GSC 0612-0771", "ASAS J010618+0846.2"}
    v965 = stars["V965 Cep"]
    assert "GSC 4500-0083" in v965["aliases"] and "NSVS 304708" in v965["aliases"]
    assert v965["multiperiodic"] is True
    plain = stars["DW Psc"]
    assert plain["aliases"] == [] and plain["multiperiodic"] is False


def test_lookup_by_name_and_alias_offline():
    assert hads.lookup("GP And")["name"] == "GP And"
    assert hads.lookup("gsc  01739-01964")["name"] == "GP And"  # case/space
    assert hads.lookup("not a star") is None


# ---------------- session maths ----------------

def test_derive_gp_and():
    star = next(s for s in hads.catalog_bundled() if s["name"] == "GP And")
    d = hads.derive(star, hours_up=5.0)
    assert d["amp"] == 0.6                     # mind: Min - Max
    assert d["mag_med"] == 10.7
    assert d["cycles"] == round(5.0 / 1.89, 1)
    assert d["cadence_s"] == 567.0             # 1.89 h / 12 points
    assert d["session_req_h"] == 3.78
    assert isinstance(d["exp_s"], int) and 5 <= d["exp_s"] <= 300


def test_derive_cadence_caps_at_fifteen_minutes():
    star = {"max": 10.0, "min": 10.8, "period_h": 4.88}
    d = hads.derive(star, hours_up=8.0)
    assert d["cadence_s"] == 900.0             # AAVSO 15-min rule


def test_span_hours():
    assert hads.span_hours("2026-09-11T22:00:00", "2026-09-12T02:30:00") == 4.5
    assert hads.span_hours(None, "2026-09-12T02:30:00") is None
    assert hads.span_hours("junk", "2026-09-12T02:30:00") is None


# ---------------- online merge ----------------

def _fake_live(gp_period=2.0):
    return {"fetched_year": 2026,
            "stars": [
                {"sheet_name": "GP And (=GSC 01739-01964)",
                 "ra": "00 55 18.1", "dec": "+23 09 49",
                 "max": 10.4, "min": 11.0, "period_h": gp_period,
                 "priority": "period_change", "observed": True,
                 "multiperiodic_sheet": False},
                {"sheet_name": "BRAND NEW One",
                 "ra": "12 00 00.0", "dec": "-30 00 00",
                 "max": 12.0, "min": 12.5, "period_h": 2.5,
                 "priority": None, "observed": False,
                 "multiperiodic_sheet": True}],
            "coverage": {"2026": {"GP And (=GSC 01739-01964)": [3, 9],
                                  "BRAND NEW One": []}}}


def test_catalog_merge_overlays_the_live_sheet(monkeypatch):
    monkeypatch.setattr(hads_sheet, "parsed", lambda force=False: _fake_live())
    stars = {s["name"]: s for s in hads.catalog()}
    gp = stars["GP And"]
    assert gp["period_h"] == 2.0                       # sheet wins (fresher)
    assert gp["priority"] == "period_change"
    assert gp["coverage"] == {"2026": [3, 9]}
    new = stars["BRAND NEW One"]                       # sheet-only star added
    assert new["observed"] is False and new["multiperiodic"] is True
    assert len(stars) == 169


def test_catalog_offline_falls_back_to_the_snapshot(monkeypatch):
    monkeypatch.setattr(hads_sheet, "parsed", lambda force=False: None)
    stars = hads.catalog()
    assert len(stars) == 168
    assert all(s["priority"] is None for s in stars)


def test_merge_leaves_the_cached_bundle_pristine(monkeypatch):
    monkeypatch.setattr(hads_sheet, "parsed", lambda force=False: _fake_live())
    hads.catalog()
    gp = next(s for s in hads.catalog_bundled() if s["name"] == "GP And")
    assert gp["period_h"] == 1.89 and gp["priority"] is None


def test_covered_this_month(monkeypatch):
    monkeypatch.setattr(hads_sheet, "parsed", lambda force=False: _fake_live())
    gp = next(s for s in hads.catalog() if s["name"] == "GP And")
    assert hads.covered_this_month(gp, date(2026, 9, 15)) is True
    assert hads.covered_this_month(gp, date(2026, 5, 15)) is False
    assert hads.covered_this_month(gp, date(2020, 9, 15)) is None


# ---------------- schematic sawtooth ----------------

def test_sawtooth_template_shape():
    pts = hads.sawtooth_template(1.89, 0.6, 10.7, rise_frac=0.35, n=40)
    assert len(pts) == 41
    peak_phase, peak_mag = min(pts, key=lambda p: p[1])   # brightest = min mag
    assert abs(peak_phase - 0.35) < 0.03
    assert abs(peak_mag - (10.7 - 0.3)) < 0.01
    assert abs(pts[0][1] - 11.0) < 0.01 and abs(pts[-1][1] - 11.0) < 0.01
