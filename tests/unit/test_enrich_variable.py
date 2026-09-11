############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Variable detection & enrich branch (Track V, VB.5/VB.6)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import pytest

from nightscribe.core import enrich


def test_detect_variable_gcvs_names():
    assert enrich.detect_type("T CrB") == "variable"
    assert enrich.detect_type("EE Cep") == "variable"
    assert enrich.detect_type("V1490 Cyg") == "variable"
    assert enrich.detect_type("NSV 01234") == "variable"


def test_detect_collisions_stay_put():
    assert enrich.detect_type("GP And") == "hads"         # HADS regression
    assert enrich.detect_type("GQ Lup b") == "exoplanet"  # 3 tokens: planet
    assert enrich.detect_type("SN 2026abc") == "transient"
    assert enrich.detect_type("2026 AB1") == "small_body"


def test_detect_local_variable_project_name(monkeypatch):
    class _FakeDb:
        def execute(self, sql, params=()):
            class _Cur:
                def fetchone(self):
                    return (1,)
            return _Cur()
    from nightscribe.core import db as dbmod
    monkeypatch.setattr(dbmod, "db", _FakeDb())
    assert enrich.detect_type("WeSb 1") == "variable"     # not GCVS-shaped


# ---- VB.6: enrich branch -------------------------------------------------


def _vsx_tcrb():
    return {"name": "T CrB", "auid": "000-BBW-825", "ra_deg": 239.87567,
            "dec_deg": 25.92017, "var_type": "NR+ELL", "period_d": 227.5528,
            "epoch_mjd": 55828.4, "max": 2.0, "min": 10.8,
            "max_band": "V", "min_band": "V", "spectral": "M3III+WD",
            "constellation": "CrB"}


def test_enrich_variable_from_vsx(monkeypatch):
    from nightscribe.core.sources import vsx
    monkeypatch.setattr(vsx, "lookup", lambda name: _vsx_tcrb())
    e = enrich.enrich("T CrB")
    assert e["type"] == "variable"
    v = e["data"]["variable"]
    assert v["amp"] == 8.8                          # min - max
    assert v["next_extremum"]["kind"] in ("max", "min")
    assert e["data"]["ra_deg"] == 239.87567


def test_enrich_variable_vsx_miss_falls_to_simbad(monkeypatch):
    from nightscribe.core.sources import simbad, vsx
    from nightscribe.core import db as dbmod
    class _FakeDb:
        def execute(self, sql, params=()):
            class _Cur:
                def fetchone(self):
                    return (1,)
            return _Cur()
    monkeypatch.setattr(dbmod, "db", _FakeDb())
    monkeypatch.setattr(vsx, "lookup", lambda name: None)
    monkeypatch.setattr(simbad, "query_id", lambda name: {
        "name": "WeSb 1", "otype": "PN?", "ra": "01 00 54.10",
        "dec": "+55 04 00.1", "vmag": 15.0, "z": None})
    e = enrich.enrich("WeSb 1")
    v = e["data"]["variable"]
    assert v["ra_deg"] == pytest.approx(15.2254, abs=1e-3)
    assert v["max"] == 15.0
    assert e["data"]["simbad"]["name"] == "WeSb 1"


def test_enrich_variable_planner_snapshot_wins(monkeypatch):
    from nightscribe.core.sources import vsx
    monkeypatch.setattr(vsx, "lookup", lambda name: _vsx_tcrb())
    fb = {"kind": "variable", "mag": 10.5,
          "variable": {"var_type": "NR", "period_d": 227.5528,
                       "epoch_mjd": 55828.4, "max": 2.0, "min": 10.8,
                       "next_extremum": {"kind": "max", "mjd": 61250.0,
                                         "days": 3.0}},
          "campaign": {"id": 1, "name": "Campaña T CrB", "overdue_days": 4,
                       "cadence_nights": 1, "never_visited": False,
                       "event": None},
          "safe_window": "2026-09-11T22:00|2026-09-12T04:00"}
    e = enrich.enrich("T CrB", fallback_target=fb)
    assert e["data"]["campaign"]["name"] == "Campaña T CrB"
    assert e["data"]["variable"]["next_extremum"]["days"] == 3.0
    assert e["data"]["safe_window"] == "2026-09-11T22:00|2026-09-12T04:00"
