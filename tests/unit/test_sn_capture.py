############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: SN exposure + multi-filter sequences (Track B, B8)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

from nightscribe.core.exposure import recommended_sn_exposure
from nightscribe.core.sequence import (
    make_plan, export_csv, export_nina, export_ccdciel, export,
)
import xml.etree.ElementTree as ET


# ---------------- recommended_sn_exposure ----------------

def test_sn_exposure_bright():
    assert recommended_sn_exposure(8.0) == 30


def test_sn_exposure_mag_12():
    assert recommended_sn_exposure(12.0) == 90


def test_sn_exposure_mag_16():
    assert recommended_sn_exposure(16.0) == 180


def test_sn_exposure_faint():
    assert recommended_sn_exposure(20.0) == 300


def test_sn_exposure_fainter_than_table():
    # fainter than the last entry → cap at 300
    assert recommended_sn_exposure(25.0) == 300


def test_sn_exposure_none():
    assert recommended_sn_exposure(None) is None


# ---------------- make_plan multi-filter retrocompatible ----------------

def test_make_plan_single_filter():
    plan = make_plan(30, 60.0, "Clear")
    assert plan["n_frames"] == 30
    assert plan["filter"] == "Clear"
    assert plan["exp_s"] == 60.0
    assert "steps" in plan
    assert len(plan["steps"]) == 1


def test_make_plan_multi_filter():
    steps = [("Clear", 30, 60.0), ("V", 20, 120.0)]
    plan = make_plan(0, 0, "L", steps=steps)
    assert plan["n_frames"] == 50   # 30 + 20
    assert len(plan["steps"]) == 2
    assert plan["steps"][0]["filter"] == "Clear"
    assert plan["steps"][1]["filter"] == "V"
    # duration includes both light steps + overhead
    assert plan["duration_s"] > 50 * 60   # at least the light time


def test_make_plan_multi_filter_with_cals():
    steps = [("Clear", 30, 60.0)]
    plan = make_plan(0, 0, "L", steps=steps, n_darks=25, n_bias=100)
    assert plan["darks"]["count"] == 25
    assert plan["bias"]["count"] == 100


# ---------------- export CSV multi-filter ----------------

def test_export_csv_multi_filter(tmp_path):
    steps = [("Clear", 30, 60.0), ("V", 20, 120.0)]
    plan = make_plan(0, 0, "L", steps=steps)
    target = {"name": "SN2026abc", "ra_deg": 10.0, "dec_deg": 20.0}
    out = tmp_path / "seq.csv"
    export_csv(target, plan, str(out))
    text = out.read_text(encoding="utf-8")
    assert "Clear" in text and "V" in text
    assert "SN2026abc" in text


# ---------------- export NINA multi-filter ----------------

def test_export_nina_multi_filter(tmp_path):
    steps = [("Clear", 30, 60.0), ("V", 20, 120.0)]
    plan = make_plan(0, 0, "L", steps=steps)
    target = {"name": "SN2026abc", "ra_deg": 10.0, "dec_deg": 20.0}
    out = tmp_path / "seq.json"
    export_nina(target, plan, str(out))
    import json
    seq = json.loads(out.read_text(encoding="utf-8"))
    exposures = seq["Sequence"]["Exposures"]
    # 30 Clear + 20 V = 50 total exposures
    assert len(exposures) == 50
    filters = {e["Filter"] for e in exposures}
    assert "Clear" in filters and "V" in filters


# ---------------- export CCDciel multi-filter ----------------

def test_export_ccdciel_multi_filter(tmp_path):
    steps = [("Clear", 30, 60.0), ("V", 20, 120.0)]
    plan = make_plan(0, 0, "L", steps=steps, n_darks=10, n_bias=50)
    target = {"name": "SN2026abc", "ra_deg": 10.0, "dec_deg": 20.0}
    out = tmp_path / "seq.targets"
    export_ccdciel(target, plan, str(out))
    text = out.read_text(encoding="utf-8")
    # parse the XML and count Light steps (elements are Step1, Step2, …)
    root = ET.fromstring(text)
    step_els = root.findall(".//Steps/*")
    light_steps = [s for s in step_els
                 if s.get("FrameType") == "Light"]
    assert len(light_steps) == 2   # one per filter
    # check the filters match
    filters = [s.get("Filter") for s in light_steps]
    assert "Clear" in filters and "V" in filters
    # dark + bias steps still present
    dark_steps = [s for s in step_els if s.get("FrameType") == "Dark"]
    assert len(dark_steps) == 1


def test_export_ccdciel_single_filter_retrocompatible(tmp_path):
    plan = make_plan(30, 60.0, "Clear")
    target = {"name": "SNx", "ra_deg": 10.0, "dec_deg": 20.0}
    out = tmp_path / "single.targets"
    export_ccdciel(target, plan, str(out))
    text = out.read_text(encoding="utf-8")
    root = ET.fromstring(text)
    light_steps = [s for s in root.findall(".//Steps/*")
                 if s.get("FrameType") == "Light"]
    assert len(light_steps) == 1   # single filter = single Light step


# ---------------- export dispatcher ----------------

def test_export_dispatch_multi(tmp_path):
    steps = [("R", 30, 120.0)]
    plan = make_plan(0, 0, "L", steps=steps)
    target = {"name": "SNx", "ra_deg": 10.0, "dec_deg": 20.0}
    out = tmp_path / "dispatch.targets"
    path = export(target, plan, str(out), fmt="ccdciel")
    assert path is not None
