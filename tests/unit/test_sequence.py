############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: capture sequence exporters (ADR-021)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import csv
import json
import xml.etree.ElementTree as ET

from nightscribe.core import sequence


def _target():
    return {"name": "SN 2026ziz", "ra_deg": 180.0, "dec_deg": 40.0,
            "kind": "sn"}


def test_make_plan():
    p = sequence.make_plan(30, 60.0, "L", overhead_s=15.0)
    assert p["n_frames"] == 30
    assert p["exp_s"] == 60.0
    assert p["filter"] == "L"
    assert p["duration_s"] == 30 * (60 + 15)


def test_make_plan_defaults_overhead():
    p = sequence.make_plan(10, 120.0, "R")
    assert p["overhead_s"] == 15.0


def test_make_plan_calibration():
    p = sequence.make_plan(30, 60.0, "L", overhead_s=15.0,
                           n_darks=25, exp_dark=None, n_bias=100)
    assert p["darks"] == {"count": 25, "exp_s": 60.0}
    assert p["bias"] == {"count": 100}
    # darks pay exposure + overhead, bias pays overhead only
    assert p["duration_s"] == (30 * 75 + 25 * 75 + 100 * 15)


def test_make_plan_calibration_backward_compatible():
    p = sequence.make_plan(10, 120.0, "R", n_darks=5, n_bias=2)
    assert p["darks"]["exp_s"] == 120.0  # falls back to the light exposure
    p0 = sequence.make_plan(10, 120.0, "R")
    p1 = sequence.make_plan(10, 120.0, "R", n_darks=0, n_bias=0)
    assert p1["duration_s"] == p0["duration_s"]


def test_export_csv(tmp_path):
    t = _target()
    plan = sequence.make_plan(5, 60.0, "L")
    out = sequence.export_csv(t, plan, tmp_path / "seq.csv")
    with open(out, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 5
    assert rows[0]["target"] == "SN 2026ziz"
    assert rows[0]["exposure_s"] == "60.0"
    assert rows[0]["filter"] == "L"
    assert rows[0]["ra_deg"] == "180.000000"
    assert rows[4]["frame"] == "5"


def test_export_nina(tmp_path):
    t = _target()
    plan = sequence.make_plan(3, 120.0, "Ha")
    out = sequence.export_nina(t, plan, tmp_path / "seq.json")
    data = json.loads(open(out, encoding="utf-8").read())
    assert data["Name"] == "SN 2026ziz"
    assert data["Target"]["TargetCoordinates"]["RAHours"] == 12
    assert data["Target"]["TargetCoordinates"]["Sign"] == "+"
    assert data["Target"]["TargetCoordinates"]["DecDegrees"] == 40
    assert len(data["Sequence"]["Exposures"]) == 3
    assert data["Sequence"]["Exposures"][0]["ExposureTime"] == 120.0
    assert data["Sequence"]["Exposures"][0]["Filter"] == "Ha"
    assert data["Metadata"]["Generator"] == "NightScribe"


def _parse_targets(path):
    return ET.parse(path)


def test_export_ccdciel_real_format(tmp_path):
    t = _target()
    # safe window drives StartTime/EndTime (informative; rise/set still on)
    t["safe_window"] = "2026-09-06T16:52:02+00:00|2026-09-07T12:53:15+00:00"
    plan = sequence.make_plan(4, 90.0, "R", n_darks=25,
                              exp_dark=None, n_bias=100)
    out = sequence.export_ccdciel(t, plan, tmp_path / "seq.targets")
    root = _parse_targets(out).getroot()
    # XML declaration + CONFIG Version="5", the real format (ADR-021)
    assert root.tag == "CONFIG"
    assert root.get("Version") == "5"
    assert root.get("ListName") == "SN 2026ziz"
    assert root.get("TargetNum") == "1"
    tgt = root.find("Targets/Target1")
    assert tgt is not None
    assert tgt.get("ObjectName") == "SN 2026ziz"
    # sexagesimal coords like the sample file
    assert tgt.get("RA") == "12h00m00s"
    assert tgt.get("Dec") == "+40d00m00s"
    # rise/set window by default + informative times
    assert tgt.get("StartRise") == "True"
    assert tgt.get("EndSet") == "True"
    assert tgt.get("StartTime") == "16:52:02"
    assert tgt.get("EndTime") == "12:53:15"
    # plan steps: Light + Dark + Bias
    steps = root.findall(".//Plan/Steps/*")
    assert [s.tag for s in steps] == ["Step1", "Step2", "Step3"]
    assert tgt.find("Plan").get("StepNum") == "3"
    light, dark, bias = steps
    assert light.get("FrameType") == "Light"
    assert light.get("Count") == "4"
    assert light.get("Exposure") == "90"
    assert light.get("Filter") == "R"
    assert light.get("Dither") == "True"
    assert light.get("AutofocusStart") == "True"
    assert dark.get("FrameType") == "Dark"
    assert dark.get("Count") == "25"
    assert dark.get("Filter") == "Dark"
    assert dark.get("Dither") == "False"
    assert bias.get("FrameType") == "Bias"
    assert bias.get("Count") == "100"
    assert bias.get("Exposure") == "0"
    # sample startup/termination blocks
    assert root.find("Startup").get("SeqStartTwilight") == "False"
    assert root.find("Startup").get("CoolCamera") == "False"
    assert root.find("Termination").get("WarmCamera") == "True"
    assert root.find("Termination").get("StopTracking") == "True"


def test_export_ccdciel_no_calibration(tmp_path):
    t = _target()
    plan = sequence.make_plan(2, 60.0, "L")
    out = sequence.export_ccdciel(t, plan, tmp_path / "seq.targets")
    root = _parse_targets(out).getroot()
    steps = root.findall(".//Plan/Steps/*")
    assert [s.tag for s in steps] == ["Step1"]
    assert steps[0].get("FrameType") == "Light"


def test_export_ccdciel_times_fallback(tmp_path):
    t = _target()
    t["safe_window"] = None
    out = sequence.export_ccdciel(t, sequence.make_plan(1, 10.0, "L"),
                                  tmp_path / "seq.targets")
    tgt = _parse_targets(out).getroot().find("Targets/Target1")
    assert tgt.get("StartTime") == "0:00:00"
    assert tgt.get("EndTime") == "0:00:00"


def test_export_ccdciel_escapes(tmp_path):
    t = {"name": 'AT "q" <x> & y', "ra_deg": 0.0, "dec_deg": 0.0}
    out = sequence.export_ccdciel(t, sequence.make_plan(1, 5.0, "L"),
                                  tmp_path / "sq.targets")
    tgt = _parse_targets(out).getroot().find("Targets/Target1")
    assert tgt.get("ObjectName") == 'AT "q" <x> & y'
    assert ET.tostring(tgt).find(b"<x>") == -1  # escaped, not parsed as XML


def test_export_dispatcher(tmp_path):
    t = _target()
    plan = sequence.make_plan(2, 60.0, "L")
    # csv
    out = sequence.export(t, plan, tmp_path / "seq", fmt="csv")
    assert out.endswith(".csv")
    # nina
    out = sequence.export(t, plan, tmp_path / "seq", fmt="nina")
    assert out.endswith(".json")
    # ccdciel: real extension is .targets
    out = sequence.export(t, plan, tmp_path / "seq", fmt="ccdciel")
    assert out.endswith(".targets")


def test_ra_sex():
    assert sequence._ra_sex(0.0) == "00h00m00s"
    assert sequence._ra_sex(9.36667) == "00h37m28s"
    assert sequence._ra_sex(180.0) == "12h00m00s"


def test_dec_sex():
    assert sequence._dec_sex(0.0) == "+00d00m00s"
    assert sequence._dec_sex(72.3475) == "+72d20m51s"
    assert sequence._dec_sex(-40.0) == "-40d00m00s"


def test_deg_to_hms():
    h, m, s = sequence._deg_to_hms(180.0)
    assert h == 12
    assert m == 0
    assert abs(s - 0.0) < 0.01


def test_deg_to_dms():
    sign, d, m, s = sequence._deg_to_dms(40.0)
    assert sign == 1
    assert d == 40
    assert m == 0
    sign, d, m, s = sequence._deg_to_dms(-30.5)
    assert sign == -1
    assert d == 30
    assert m == 30