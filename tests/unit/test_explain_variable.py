############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: explain_variable (Track V, VC.1)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

from nightscribe.core import orbits


def _d(vt="NR+ELL", **vkw):
    v = {"var_type": vt, "period_d": 227.55, "epoch_mjd": 55828.4,
         "max": 2.0, "min": 10.8, "amp": 8.8, "spectral": "M3III+WD",
         "next_extremum": {"kind": "max", "mjd": 61250.0, "days": 3.0}}
    v.update(vkw)
    d = {"variable": v}
    if vkw.pop("campaign", None):
        d["campaign"] = vkw["campaign"]
    return d


def test_full_rows_es_en():
    rows = orbits.explain_variable(_d())
    params = [r["param"]["en"] for r in rows]
    assert "Variable type" in params
    assert "Period" in params
    assert "Next extremum" in params
    assert "Brightness range" in params
    assert "Amplitude" in params
    assert "Spectral type" in params
    for r in rows:
        assert r["es"] and r["en"] and r["value"]


def test_family_texts():
    assert "Binaria eclipsante" in orbits.explain_variable(_d("E-DO"))[0]["es"]
    assert "Mira" in orbits.explain_variable(_d("M"))[0]["es"]
    assert "Nova recurrente" in orbits.explain_variable(_d("NR+ELL"))[0]["es"]
    assert "Nova enana" in orbits.explain_variable(_d("UGSS"))[0]["es"]
    assert "hollín" in orbits.explain_variable(_d("RCB"))[0]["es"]


def test_minimal_variable_still_explains():
    rows = orbits.explain_variable({"variable": {}})
    assert len(rows) == 1                       # just the generic type row
    assert rows[0]["value"] == "—"


def test_campaign_row():
    d = _d()
    d["campaign"] = {"name": "Campaña T CrB", "group_name": "obsSN",
                     "goal": "Catch the eruption"}
    rows = orbits.explain_variable(d)
    row = [r for r in rows if r["param"]["en"] == "Campaign"][0]
    assert "obsSN" in row["es"] and "Catch the eruption" in row["en"]
