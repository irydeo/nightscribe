############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: EXOTIC result import (phase D)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Phase-D acceptance: EXOTIC's curve becomes project points and its
parameters a plain dict; a missing folder never raises. No network."""

import json

from nightscribe.core import exotic_import as ei
from nightscribe.core.db import Database
from nightscribe.core import project, followup as fu


def _out_dir(tmp_path):
    out = tmp_path / "exotic_out"
    temp = out / "temp"
    temp.mkdir(parents=True)
    (temp / "FinalLightCurve_HAT-P-32 b_17-December-2017.csv").write_text(
        "# FINAL TIMESERIES\n"
        "# BJD_TDB,Orbital Phase,Flux,Uncertainty,Model,Airmass\n"
        "2458107.5698574726,-0.06,0.9989802,0.0059087,1.0,1.0176\n"
        "2458107.5715829000,-0.05,0.9900000,0.0060000,0.99,1.02\n",
        encoding="utf-8")
    params = {"FINAL PLANETARY PARAMETERS": {
        "Mid-Transit Time (Tmid)": "2458107.71358 +/- 0.00094 BJD_TDB",
        "Ratio of Planet to Stellar Radius (Rp/R*)": "0.1569 +/- 0.0034",
        "Transit depth (Rp/Rs)^2": "2.46 +/- 0.11 [%]",
        "Orbital Inclination (inc)": "88.17 +/- 0.98 ",
        "Transit Duration (day)": "0.1303 +/- 0.0012"}}
    (temp / "FinalParams_HAT-P-32 b_17-December-2017.json").write_text(
        json.dumps(params), encoding="utf-8")
    (out / "FinalLightCurve_HAT-P-32 b_17-December-2017.png").write_bytes(b"p")
    return out


def test_load_result_parses_curve_and_params(tmp_path):
    res = ei.load_result(_out_dir(tmp_path))
    assert len(res["points"]) == 2
    p0 = res["points"][0]
    assert abs(p0["mjd"] - (2458107.5698574726 - 2400000.5)) < 1e-9
    assert p0["source"] == "exotic"
    assert p0["flux"] == 0.9989802 and p0["err"] is not None
    par = res["params"]
    assert par["tmid"] == 2458107.71358 and par["tmid_err"] == 0.00094
    assert par["rprs"] == 0.1569 and par["rprs_err"] == 0.0034
    assert abs(par["depth"] - 0.0246) < 1e-9        # percent -> fraction
    assert par["inc"] == 88.17 and par["duration_d"] == 0.1303
    assert res["figure_png"]


def test_missing_folder_is_empty_not_an_error(tmp_path):
    res = ei.load_result(tmp_path / "nope")
    assert res["points"] == [] and res["params"] == {}
    assert res["curve_csv"] is None


def test_persist_creates_a_run_and_points(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    p = project.create(db, "transit", "HAT-P-32 b")
    sid = fu.create_session(db, p["id"], obs_date="2017-12-20")
    res = ei.load_result(_out_dir(tmp_path))
    run_id, n = ei.persist(db, p["id"], sid, res, filter_name="V")
    assert n == 2
    pts = fu.list_points_for_run(db, run_id)
    assert len(pts) == 2 and all(pt["source"] == "exotic" for pt in pts)
    assert pts[0]["filter"] == "V" and pts[0]["mag"] is not None
    db.close()
