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
    assert p["overhead_s"] == 2.0        # the readout+download fallback


def test_make_plan_calibration():
    p = sequence.make_plan(30, 60.0, "L", overhead_s=15.0,
                           n_darks=25, exp_dark=None, n_bias=100)
    # the two steps carry their own wheel slot: a dark is taken with the light
    # path blocked, and that is a position on the wheel (2026-10-16)
    assert p["darks"] == {"count": 25, "exp_s": 60.0, "filter": "Dark"}
    assert p["bias"] == {"count": 100, "filter": "Dark"}
    # and the slot is the observer's, not the app's
    p2 = sequence.make_plan(30, 60.0, "L", n_darks=5, n_bias=5,
                            dark_filter="Opaque")
    assert p2["darks"]["filter"] == "Opaque"
    assert p2["bias"]["filter"] == "Opaque"   # the bias follows the dark's
    p3 = sequence.make_plan(30, 60.0, "L", n_darks=5, n_bias=5,
                            dark_filter="Opaque", bias_filter="D")
    assert p3["bias"]["filter"] == "D"
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


def _all_of_type(node, name):
    # @args: node - a decoded NINA sequence, name - the $type's class name
    # @return: every dict of that type, in document order (the walk order is
    #          the order the sequence runs in, which is what the test needs)
    out = []

    def walk(n):
        if isinstance(n, dict):
            if str(n.get("$type", "")).split(".")[-1].split(",")[0] == name:
                out.append(n)
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    walk(node)
    return out


def _csv_rows(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _find_type(node, name):
    # @return: the first object whose $type ends with ".<name>", or None
    if isinstance(node, dict):
        t = str(node.get("$type", "")).split(",")[0]
        if t.endswith("." + name):
            return node
        for v in node.values():
            found = _find_type(v, name)
            if found is not None:
                return found
    elif isinstance(node, list):
        for v in node:
            found = _find_type(v, name)
            if found is not None:
                return found
    return None


def _ids_and_refs(node):
    ids, refs = [], []

    def walk(n):
        if isinstance(n, dict):
            if "$id" in n:
                ids.append(n["$id"])
            if "$ref" in n:
                refs.append(n["$ref"])
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    walk(node)
    return ids, refs


def test_export_nina_is_the_native_sequence(tmp_path):
    # ADR-021 rev: the native NINA sequence (SequenceRootContainer), the one
    # SequenceJsonConverter can load, not the old bespoke shape.
    t = _target()
    plan = sequence.make_plan(3, 120.0, "Ha")
    out = sequence.export_nina(t, plan, tmp_path / "seq.json")
    data = json.loads(open(out, encoding="utf-8").read())
    assert data["$type"].startswith(
        "NINA.Sequencer.Container.SequenceRootContainer")
    areas = [i["$type"] for i in data["Items"]["$values"]]
    assert any("StartAreaContainer" in a for a in areas)
    assert any("TargetAreaContainer" in a for a in areas)
    assert any("EndAreaContainer" in a for a in areas)
    dso = _find_type(data, "DeepSkyObjectContainer")
    assert dso["Target"]["TargetName"] == "SN 2026ziz"
    coords = dso["Target"]["InputCoordinates"]
    assert coords["RAHours"] == 12
    assert coords["DecDegrees"] == 40 and coords["NegativeDec"] is False
    kinds = [i["$type"].split(".")[-1].split(",")[0]
             for i in dso["Items"]["$values"]]
    assert "SwitchFilter" in kinds and "TakeManyExposures" in kinds
    tme = _find_type(dso, "TakeManyExposures")
    assert tme["Conditions"]["$values"][0]["Iterations"] == 3
    exposure = _find_type(tme, "TakeExposure")
    assert exposure["ExposureTime"] == 120.0
    assert exposure["ImageType"] == "LIGHT"
    # every $ref must point to an existing $id (a broken one breaks the load)
    ids, refs = _ids_and_refs(data)
    assert refs and all(r in ids for r in refs)
    assert len(ids) == len(set(ids))


def test_export_nina_writes_dither_and_autofocus_triggers(tmp_path):
    # ADR-083: dither and autofocus are NINA TRIGGERS on the target container
    t = _target()
    recipe = {"dither": {"on": True, "every": 4, "pixels": 5},
              "autofocus": {"on": True, "minutes": 45, "delta_c": 1.0,
                            "on_filter": True}}
    plan = sequence.make_plan(3, 120.0, "L", recipe=recipe)
    out = sequence.export_nina(t, plan, tmp_path / "seq.json")
    data = json.loads(open(out, encoding="utf-8").read())
    dso = _find_type(data, "DeepSkyObjectContainer")
    triggers = [t["$type"] for t in dso["Triggers"]["$values"]]
    assert any("DitherAfterExposures" in t for t in triggers)
    assert any("AutofocusAfterTimeTrigger" in t for t in triggers)
    assert any("AutofocusAfterTemperatureChangeTrigger" in t for t in triggers)
    assert any("AutofocusAfterFilterChange" in t for t in triggers)
    dither = _find_type(dso, "DitherAfterExposures")
    assert dither["AfterExposures"] == 4
    # each trigger's runner holds the instruction that runs
    assert _find_type(dither, "Dither") is not None


def test_export_nina_summary_keeps_the_plan_shape(tmp_path):
    # the human-readable plan summary (not a loadable sequence) keeps its shape
    t = _target()
    plan = sequence.make_plan(3, 120.0, "Ha")
    out = sequence.export_nina_summary(t, plan, tmp_path / "seq.plan.json")
    data = json.loads(open(out, encoding="utf-8").read())
    assert data["Name"] == "SN 2026ziz"
    assert data["Target"]["TargetCoordinates"]["RAHours"] == 12
    assert data["Target"]["TargetCoordinates"]["DecDegrees"] == 40
    assert len(data["Sequence"]["Exposures"]) == 3
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


def test_export_ccdciel_writes_the_capture_options(tmp_path):
    # ADR-083: the recipe (dither, autofocus, gain, offset, binning, delay)
    # reaches the real .targets format.
    t = _target()
    recipe = {"dither": {"on": False, "every": 0, "pixels": 5, "settle_s": 0},
              "autofocus": {"on": True, "every": 0, "minutes": 45,
                            "delta_c": 1.0, "on_filter": True},
              "gain": 120, "offset": 30, "binning": "2x2", "delay_s": 10}
    plan = sequence.make_plan(4, 90.0, "R", recipe=recipe)
    out = sequence.export_ccdciel(t, plan, tmp_path / "opt.targets")
    root = _parse_targets(out).getroot()
    tgt = root.find("Targets/Target1")
    assert tgt.get("Delay") == "10"
    assert tgt.get("AutofocusTemp") == "True"
    light = root.find(".//Plan/Steps/Step1")
    assert light.get("Dither") == "False"
    assert light.get("Gain") == "120"
    assert light.get("Offset") == "30"
    assert light.get("Binning") == "2x2"


def test_export_nina_summary_carries_the_capture_options(tmp_path):
    t = _target()
    recipe = {"dither": {"on": True, "every": 3, "pixels": 5},
              "autofocus": {"on": True, "minutes": 45, "delta_c": 1.0},
              "gain": 120, "offset": None, "binning": "2x2", "delay_s": 0}
    plan = sequence.make_plan(3, 120.0, "Ha", recipe=recipe)
    out = sequence.export_nina_summary(t, plan, tmp_path / "opt.plan.json")
    data = json.loads(open(out, encoding="utf-8").read())
    cap = data["Metadata"]["Capture"]
    assert cap["Dither"] is True and cap["DitherEvery"] == 3
    assert cap["AutofocusDeltaC"] == 1.0
    assert cap["Gain"] == 120 and cap["Binning"] == "2x2"


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


# ---------------- Track D: transit capture window ----------------

def _transit_target():
    # A transit target carrying the recommended capture window (baseline +
    # transit + baseline) as ISO strings — how the project context hands it
    # over after the JSON round-trip.
    t = _target()
    t["name"] = "WASP-999 b"
    t["capture_start"] = "2026-08-21T22:50:00+00:00"
    t["capture_end"] = "2026-08-22T01:50:00+00:00"
    return t


def test_ccdciel_transit_window_is_mandatory(tmp_path):
    # The transit capture window writes StartTime/EndTime with a mandatory
    # start and StartRise off (the pre-ingress baseline cannot wait for
    # the rise).
    t = _transit_target()
    out = sequence.export_ccdciel(t, sequence.make_plan(4, 60.0, "L"),
                                  tmp_path / "seq.targets")
    tgt = _parse_targets(out).getroot().find("Targets/Target1")
    assert tgt.get("StartTime") == "22:50:00"
    assert tgt.get("EndTime") == "01:50:00"
    assert tgt.get("MandatoryStartTime") == "True"
    assert tgt.get("StartRise") == "False"


def test_ccdciel_safe_window_stays_soft(tmp_path):
    # The pre-existing safe-window path is untouched: informative times,
    # rise/set still on, start NOT mandatory.
    t = _target()
    t["safe_window"] = "2026-09-06T16:52:02+00:00|2026-09-07T12:53:15+00:00"
    out = sequence.export_ccdciel(t, sequence.make_plan(1, 10.0, "L"),
                                  tmp_path / "seq.targets")
    tgt = _parse_targets(out).getroot().find("Targets/Target1")
    assert tgt.get("StartTime") == "16:52:02"
    assert tgt.get("StartRise") == "True"
    assert tgt.get("MandatoryStartTime") == "False"


def test_nina_transit_window_metadata(tmp_path):
    t = _transit_target()
    out = sequence.export_nina_summary(t, sequence.make_plan(2, 60.0, "L"),
                                       tmp_path / "seq.plan.json")
    data = json.loads(open(out, encoding="utf-8").read())
    assert data["Metadata"]["StartTime"] == "2026-08-21T22:50:00+00:00"
    assert data["Metadata"]["EndTime"] == "2026-08-22T01:50:00+00:00"


def test_nina_without_window_has_no_times(tmp_path):
    out = sequence.export_nina_summary(
        _target(), sequence.make_plan(1, 60.0, "L"), tmp_path / "seq.plan.json")
    data = json.loads(open(out, encoding="utf-8").read())
    assert "StartTime" not in data["Metadata"]


def test_csv_start_time_per_frame(tmp_path):
    # 3 frames x (60 s + 15 s overhead) from the capture start
    t = _transit_target()
    out = sequence.export_csv(t, sequence.make_plan(3, 60.0, "L",
                                                    overhead_s=15.0),
                              tmp_path / "seq.csv")
    with open(out, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["start_time"] == "2026-08-21T22:50:00+00:00"
    assert rows[1]["start_time"] == "2026-08-21T22:51:15+00:00"
    assert rows[2]["start_time"] == "2026-08-21T22:52:30+00:00"


def test_csv_start_time_empty_without_window(tmp_path):
    out = sequence.export_csv(_target(), sequence.make_plan(2, 60.0, "L"),
                              tmp_path / "seq.csv")
    with open(out, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    # the column exists (stable header) but stays empty
    assert rows[0]["start_time"] == ""


def test_transit_window_helper_tolerates_datetimes_and_junk():
    import datetime
    assert sequence._transit_window({}) is None
    assert sequence._transit_window(
        {"capture_start": "junk", "capture_end": None}) is None
    tw = sequence._transit_window(
        {"capture_start": datetime.datetime(2026, 8, 21, 22, 50),
         "capture_end": datetime.datetime(2026, 8, 22, 1, 50)})
    assert tw[0].hour == 22 and tw[1].hour == 1

def test_ccdciel_hads_window_is_written_but_advisory(tmp_path):
    # ADR-034: the HADS 2P session window exports StartTime/EndTime, but the
    # start is NOT mandatory and StartRise stays on (soft semantics)
    t = _target()
    t["name"] = "CY Aqr"
    t["capture_start"] = "2026-09-12T00:28:00+00:00"
    t["capture_end"] = "2026-09-12T03:23:00+00:00"
    t["capture_advisory"] = True
    out = sequence.export_ccdciel(t, sequence.make_plan(4, 60.0, "L"),
                                  tmp_path / "seq.targets")
    tgt = _parse_targets(out).getroot().find("Targets/Target1")
    assert tgt.get("StartTime") == "00:28:00"
    assert tgt.get("EndTime") == "03:23:00"
    assert tgt.get("MandatoryStartTime") == "False"
    assert tgt.get("StartRise") == "True"


def test_ccdciel_hads_window_duration_covers_two_periods(tmp_path):
    # 2.92 h between the advisory bounds (the CY Aqr 2P session)
    t = _target()
    t["capture_start"] = "2026-09-12T00:28:00+00:00"
    t["capture_end"] = "2026-09-12T03:23:12+00:00"
    t["capture_advisory"] = True
    out = sequence.export_csv(t, sequence.make_plan(4, 60.0, "L"),
                              tmp_path / "seq.csv")
    text = open(out, encoding="utf-8").read()
    assert "00:28" in text

def test_the_calibration_steps_carry_their_own_wheel_slot(tmp_path):
    # 2026-10-16: a dark is taken with the LIGHT PATH BLOCKED, and that is a
    # position on the wheel. Each calibration step writes its own slot, and
    # the four formats say the same thing: the light frames first, then the
    # darks, then the bias.
    t = _target()
    plan = sequence.make_plan(5, 60.0, "L", n_darks=3, exp_dark=60.0,
                              n_bias=4, dark_filter="Opaque")

    # CCDciel: the slot is the plan's, not the hardcoded "Dark"
    root = _parse_targets(
        sequence.export_ccdciel(t, plan, tmp_path / "s.targets")).getroot()
    steps = root.findall(".//Plan/Steps/*")
    assert [s.get("FrameType") for s in steps] == ["Light", "Dark", "Bias"]
    assert steps[1].get("Filter") == "Opaque"
    assert steps[2].get("Filter") == "Opaque"
    assert steps[2].get("Exposure") == "0"

    # NINA native: DARK and BIAS TakeExposure items AFTER the lights, each
    # behind its own SwitchFilter, with the bias at exposure 0
    data = json.loads(open(sequence.export_nina(
        t, plan, tmp_path / "n.json"), encoding="utf-8").read())
    dso = _find_type(data, "DeepSkyObjectContainer")
    images = [i["ImageType"] for i in _all_of_type(dso, "TakeExposure")]
    assert images == ["LIGHT", "DARK", "BIAS"]
    dark = [i for i in _all_of_type(dso, "TakeExposure")
            if i["ImageType"] == "DARK"][0]
    bias = [i for i in _all_of_type(dso, "TakeExposure")
            if i["ImageType"] == "BIAS"][0]
    assert dark["ExposureTime"] == 60.0 and bias["ExposureTime"] == 0.0
    switches = [i["Filter"]["_name"] for i in _all_of_type(dso, "SwitchFilter")]
    assert switches == ["L", "Opaque", "Opaque"]
    ids, refs = _ids_and_refs(data)
    assert all(r in ids for r in refs)

    # NINA summary: the calibration is part of the plan, with its slot
    s = json.loads(open(sequence.export_nina_summary(
        t, plan, tmp_path / "s.json"), encoding="utf-8").read())
    cal = s["Metadata"]["Calibration"]
    assert cal[0] == {"FrameType": "Dark", "Count": 3, "Exposure_s": 60.0,
                      "Filter": "Opaque"}
    assert cal[1]["FrameType"] == "Bias" and cal[1]["Count"] == 4

    # CSV: one row per frame, the calibration included and typed
    out = sequence.export_csv(t, plan, tmp_path / "s.csv")
    rows = _csv_rows(out)
    assert [r["type"] for r in rows] == (["light"] * 5 + ["dark"] * 3
                                         + ["bias"] * 4)
    assert rows[-1]["filter"] == "Opaque"
    assert float(rows[-1]["exposure_s"]) == 0.0
