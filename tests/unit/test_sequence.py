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


def test_export_ccdciel(tmp_path):
    t = _target()
    plan = sequence.make_plan(4, 90.0, "R")
    out = sequence.export_ccdciel(t, plan, tmp_path / "seq.xml")
    tree = ET.parse(out)
    root = tree.getroot()
    assert root.tag == "plan"
    assert root.find("target").text == "SN 2026ziz"
    exposures = root.findall(".//exposure")
    assert len(exposures) == 4
    assert exposures[0].find("exposure_s").text == "90.0"
    assert exposures[0].find("filter").text == "R"


def test_export_dispatcher(tmp_path):
    t = _target()
    plan = sequence.make_plan(2, 60.0, "L")
    # csv
    out = sequence.export(t, plan, tmp_path / "seq", fmt="csv")
    assert out.endswith(".csv")
    # nina
    out = sequence.export(t, plan, tmp_path / "seq", fmt="nina")
    assert out.endswith(".json")
    # ccdciel
    out = sequence.export(t, plan, tmp_path / "seq", fmt="ccdciel")
    assert out.endswith(".xml")


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
