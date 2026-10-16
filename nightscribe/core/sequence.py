############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Capture sequence exporters (ADR-021)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import csv
import datetime
import json
import logging
import xml.etree.ElementTree as ET
from pathlib import Path

logger = logging.getLogger(__name__)

# Exporters for capture-sequence files read by NINA, CCDciel and any CSV
# reader.
#
# * NINA / CSV: best-effort starting points, to be confirmed against the
#   user's actual software during phase 5.
# * CCDciel: the real ".targets" format (CONFIG Version="5"), locked
#   against the user's real sequence file docs/ccdciel_sequence_sample.targets
#   (2026-09-06). The generated list keeps CCDciel's default rise/set time
#   constraints and emits a Light step plus optional Dark/Bias calibration.


def make_plan(n_frames, exp_s, filter_name="L", overhead_s=None, cfg=None,
              n_darks=0, exp_dark=None, n_bias=0, steps=None,
              recipe=None, dark_filter=None, bias_filter=None):
    # Builds a capture plan dict from parameters + config defaults.
    # Calibration frames are optional: Dark (count + exposure) and Bias
    # (count) steps get appended to the sequence and their wall-clock time
    # is folded into duration_s (each cal frame still pays the overhead).
    # 2026-10-16: the two steps carry their OWN wheel slot. A dark is taken
    # with the light path blocked, and that is a position on the wheel (an
    # opaque slot, "Dark" by convention): writing the light's filter there
    # would tell the observatory to take the darks through the observer's
    # glass. The bias follows the dark's slot unless it is given its own.
    # B8: multi-filter — pass steps=[(filter, n, exp), ...] for interleaved
    # bands. Retrocompatible: a single-filter call (n_frames, exp_s,
    # filter_name) is equivalent to steps=[(filter_name, n_frames, exp_s)].
    # ADR-083: `recipe` carries the capture options (dither, autofocus, gain,
    # offset, binning, delay_s) that the sequence file writes; without it the
    # step keeps the sample's conventions (dither and autofocus on).
    # @args: n_frames - light frame count (ignored when steps is given),
    #        exp_s - exposure per light frame (ignored when steps is given),
    #        filter_name - filter wheel slot name (ignored when steps),
    #        overhead_s - per-frame time that is not the exposure (the camera's
    #        readout/download plus the mount settle); defaults to
    #        exposure.frame_overhead_s(cfg) when cfg is given,
    #        cfg - Config, n_darks - dark count, exp_dark - dark exp,
    #        n_bias - bias count,
    #        steps - list of (filter, n_frames, exp_s) tuples for multi-filter,
    #        recipe - dict from capture_recipe.recommend (or None)
    # @return: {"n_frames", "exp_s", "filter", "overhead_s", "darks",
    #           "bias", "duration_s", "steps"} + the recipe fields
    recipe = dict(recipe or {})
    if overhead_s is None:
        # ADR-083 rev: the per-frame overhead is the camera's readout/download
        # PLUS the mount settle, from ONE helper, so the plan's wall clock and
        # the recipe's frame count can never disagree.
        from . import exposure as _exposure
        overhead_s = (_exposure.frame_overhead_s(cfg) if cfg is not None
                      else _exposure.DEFAULT_READOUT_S)
    if steps:
        light_steps = []
        total_light = 0.0
        for filt, n, exp in steps:
            n = int(n)
            exp = float(exp)
            light_steps.append({"filter": filt, "n_frames": n,
                                 "exp_s": exp})
            total_light += n * (exp + overhead_s)
        n_frames = sum(s["n_frames"] for s in light_steps)
        exp_s = light_steps[0]["exp_s"] if light_steps else 0.0
        filter_name = light_steps[0]["filter"] if light_steps else filter_name
    else:
        exp_s = float(exp_s)
        n_frames = int(n_frames)
        light_steps = [{"filter": filter_name, "n_frames": n_frames,
                            "exp_s": exp_s}]
    exp_dark = float(exp_dark) if exp_dark else exp_s
    n_darks = int(n_darks)
    n_bias = int(n_bias)
    dark_filter = str(dark_filter or "Dark")
    bias_filter = str(bias_filter or dark_filter)
    total = (total_light if steps else
             n_frames * (exp_s + overhead_s))
    total += n_darks * (exp_dark + overhead_s) + n_bias * overhead_s
    return {"n_frames": n_frames, "exp_s": exp_s,
            "filter": filter_name, "overhead_s": float(overhead_s),
            "darks": {"count": n_darks, "exp_s": exp_dark,
                      "filter": dark_filter},
            "bias": {"count": n_bias, "filter": bias_filter},
            "duration_s": total,
            "steps": light_steps,
            "dither": recipe.get("dither") or {},
            "autofocus": recipe.get("autofocus") or {},
            "gain": recipe.get("gain"),
            "offset": recipe.get("offset"),
            "binning": recipe.get("binning"),
            "delay_s": recipe.get("delay_s") or 0}


def export_csv(target, plan, out):
    # Generic CSV: one row per frame, readable by any capture software.
    # B8: multi-filter plans emit rows with the per-step filter.
    # Track D: when the target carries a transit capture window, each row
    # gets its planned UTC `start_time` (capture_start + cumulative
    # exposure+overhead); the column exists always and stays empty without
    # a window, so the header is stable for parsers.
    # @args: target - dict with name, ra_deg, dec_deg, plan - make_plan dict,
    #        out - output path
    # @return: the output path
    name = target.get("name") or target.get("id") or "target"
    ra = target.get("ra_deg", 0.0)
    dec = target.get("dec_deg", 0.0)
    tw = _transit_window(target)
    overhead = float(plan.get("overhead_s", 2.0))
    rows = []
    elapsed = 0.0
    for s in plan.get("steps", [{"filter": plan["filter"],
                                 "n_frames": plan["n_frames"],
                                 "exp_s": plan["exp_s"]}]):
        for i in range(s["n_frames"]):
            row = {
                "frame": len(rows) + 1, "target": name,
                "ra_deg": f"{ra:.6f}", "dec_deg": f"{dec:+.6f}",
                "exposure_s": s["exp_s"], "filter": s["filter"],
                "start_time": (tw[0] + datetime.timedelta(
                    seconds=elapsed)).isoformat() if tw else "",
            }
            rows.append(row)
            elapsed += float(s["exp_s"]) + overhead
    # 2026-10-16: the calibration frames are frames too, and a list that says
    # only "30 rows" while the night also takes darks and bias is a list that
    # lies by omission. The `type` column is LAST on purpose: a parser that
    # reads the first seven columns keeps working.
    cal = [("dark", plan.get("darks") or {}, True),
           ("bias", plan.get("bias") or {}, False)]
    for kind, step, has_exposure in cal:
        for _i in range(int(step.get("count") or 0)):
            rows.append({
                "frame": len(rows) + 1, "target": name,
                "ra_deg": f"{ra:.6f}", "dec_deg": f"{dec:+.6f}",
                "exposure_s": (float(step.get("exp_s") or 0.0)
                               if has_exposure else 0.0),
                "filter": step.get("filter") or "Dark",
                "start_time": "", "type": kind,
            })
    for row in rows:
        row.setdefault("type", "light")
    _write_csv(out, ["frame", "target", "ra_deg", "dec_deg",
                  "exposure_s", "filter", "start_time", "type"], rows)
    logger.info("CSV sequence written to %s", out)
    return str(out)


def _transit_window(target):
    # The transit capture window (baseline + transit + baseline, Track D).
    # @args: target - dict with optional "capture_start"/"capture_end"
    #         (ISO strings or datetimes)
    # @return: (start, end) datetimes, or None when not carried
    def _dt(v):
        if isinstance(v, datetime.datetime):
            return v
        try:
            return datetime.datetime.fromisoformat(str(v))
        except (ValueError, TypeError):
            return None
    s, e = _dt(target.get("capture_start")), _dt(target.get("capture_end"))
    if s is None or e is None:
        return None
    return s, e


def export_nina_summary(target, plan, out):
    # The human-readable PLAN SUMMARY for NINA: a bespoke JSON that says what
    # the plan is (target, exposures, capture options) for a person or another
    # tool to read. It is NOT a loadable NINA sequence (that is export_nina);
    # the two are separate so the summary can stay simple and stable.
    # @args: target - dict with name, ra_deg, dec_deg, plan - make_plan dict,
    #        out - output path (.json)
    # @return: the output path
    name = target.get("name") or target.get("id") or "target"
    ra_deg = target.get("ra_deg", 0.0)
    dec_deg = target.get("dec_deg", 0.0)
    ra_h, ra_m, ra_s = _deg_to_hms(ra_deg)
    sign, dec_d, dec_m, dec_s = _deg_to_dms(dec_deg)
    exposures = []
    for s in plan.get("steps", [{"filter": plan["filter"],
                                 "n_frames": plan["n_frames"],
                                 "exp_s": plan["exp_s"]}]):
        exposures += [{"ExposureTime": s["exp_s"], "Filter": s["filter"],
                        "Binning": 1}] * s["n_frames"]
    seq = {
        "Name": name,
        "Description": f"NightScribe plan summary for {name}",
        "Target": {
            "TargetName": name,
            "TargetCoordinates": {
                "RAHours": ra_h, "RAMinutes": ra_m, "RASeconds": ra_s,
                "Sign": "+" if sign >= 0 else "-",
                "DecDegrees": dec_d, "DecMinutes": dec_m, "DecSeconds": dec_s,
                "Epoch": "J2000",
            },
        },
        "Sequence": {
            "Exposures": exposures,
        },
        "Metadata": {
            "Generator": "NightScribe",
            "Created": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "FrameCount": plan["n_frames"],
            "TotalDuration_s": plan["duration_s"],
        },
    }
    # ADR-083: the capture options travel with the summary too.
    d = plan.get("dither") or {}
    a = plan.get("autofocus") or {}
    seq["Metadata"]["Capture"] = {
        "Dither": bool(d.get("on")),
        "DitherEvery": int(d.get("every") or 0),
        "DitherPixels": int(d.get("pixels") or 0),
        "Autofocus": bool(a.get("on")),
        "AutofocusEveryMinutes": int(a.get("minutes") or 0),
        "AutofocusDeltaC": float(a.get("delta_c") or 0.0),
        "AutofocusOnFilter": bool(a.get("on_filter")),
        "Gain": plan.get("gain"),
        "Offset": plan.get("offset"),
        "Binning": plan.get("binning"),
        "Delay_s": plan.get("delay_s") or 0,
    }
    # 2026-10-16: the calibration steps are part of the plan, so the summary
    # says them (with their own wheel slot) instead of leaving them out.
    cal = []
    for key, frame_type in (("darks", "Dark"), ("bias", "Bias")):
        step = plan.get(key) or {}
        if int(step.get("count") or 0) > 0:
            cal.append({"FrameType": frame_type,
                        "Count": int(step["count"]),
                        "Exposure_s": (float(step.get("exp_s") or 0.0)
                                       if frame_type == "Dark" else 0.0),
                        "Filter": step.get("filter") or "Dark"})
    if cal:
        seq["Metadata"]["Calibration"] = cal
    tw = _transit_window(target)
    if tw:
        seq["Metadata"]["StartTime"] = tw[0].isoformat()
        seq["Metadata"]["EndTime"] = tw[1].isoformat()
    Path(out).write_text(json.dumps(seq, indent=2, ensure_ascii=False),
                         encoding="utf-8")
    logger.info("NINA plan summary written to %s", out)
    return str(out)


# ---- NINA native sequence (SequenceJsonConverter) ------------------------
#
# NINA loads a sequence with SequenceJsonConverter: JSON.NET with
# TypeNameHandling.All + PreserveReferencesHandling.All, i.e. every object
# carries a `$type` (assembly-qualified) and an `$id`, and references use
# `$ref`. The shape is fixed against NINA's own test corpus
# (master-3.2-all-sequence-entities.sequence.json): a `SequenceRootContainer`
# with Start/Target/End areas, a `DeepSkyObjectContainer` for the target, and
# `SwitchFilter` + `TakeManyExposures`/`TakeExposure` per band; dither and
# autofocus are TRIGGERS on the container. The assembly suffix `, NINA` is
# accepted and migrated by NINA to `, NINA.Sequencer`, so it is the most
# version-stable spelling; Core/Astrometry types keep their own assembly.
#
# PENDING: pin the exact `$type` strings against a real NINA/PINS (ADR-021/030
# philosophy). The structure is validated against the corpus; a real instance
# may need a `$type` adjustment, and those strings live in ONE place.

_NINA_SEQ = "NINA.Sequencer"
_NINA_CORE = "NINA.Core"
_NINA_ASTRO = "NINA.Astrometry"
_NINA_COLL = "System.Collections.ObjectModel.ObservableCollection`1[[{}]], System.ObjectModel"
_COLL_ITEM = _NINA_COLL.format(
    "NINA.Sequencer.SequenceItem.ISequenceItem, NINA")
_COLL_COND = _NINA_COLL.format(
    "NINA.Sequencer.Conditions.ISequenceCondition, NINA")
_COLL_TRIG = _NINA_COLL.format(
    "NINA.Sequencer.Trigger.ISequenceTrigger, NINA")
_STRAT_SEQ = "NINA.Sequencer.Container.ExecutionStrategy.SequentialStrategy, NINA"
_STRAT_PAR = "NINA.Sequencer.Container.ExecutionStrategy.ParallelStrategy, NINA"


class _NinaIds:
    # A deterministic $id allocator: PreserveReferencesHandling.All needs
    # unique ids and matching $ref, and a wrong one breaks the load.
    def __init__(self):
        self._n = 0

    def next(self):
        # @return: the next id as a string
        self._n += 1
        return str(self._n)


def _nina_coll(ids, coll_type, values):
    # @return: a JSON.NET collection object ($id + $type + $values)
    return {"$id": ids.next(), "$type": coll_type, "$values": values}


def _nina_container(ids, container_type, name, items, parent_id,
                    strategy=_STRAT_SEQ, conditions=None, triggers=None,
                    expanded=True):
    # @return: a container object (Start/Target/End area, TakeManyExposures or
    #          a TriggerRunner), wired to its parent by $ref
    return {
        "$id": ids.next(), "$type": container_type,
        "Strategy": {"$type": strategy},
        "Name": name,
        "Conditions": _nina_coll(ids, _COLL_COND, conditions or []),
        "IsExpanded": expanded,
        "Items": _nina_coll(ids, _COLL_ITEM, items),
        "Triggers": _nina_coll(ids, _COLL_TRIG, triggers or []),
        "Parent": {"$ref": parent_id} if parent_id else None,
        "ErrorBehavior": 0, "Attempts": 1,
    }


def _nina_trigger_runner(ids, parent_id, item):
    # Every trigger carries a TriggerRunner: a SequentialContainer holding the
    # instruction that actually runs (Dither / RunAutofocus).
    return _nina_container(
        ids, f"NINA.Sequencer.Container.SequentialContainer, NINA",
        None, [item], parent_id, expanded=True)


def _nina_filter(ids, name, position):
    # A FilterInfo (the SwitchFilter target). Only the fields that matter are
    # written; JSON.NET fills the rest from the type's defaults.
    return {
        "$id": ids.next(),
        "$type": f"NINA.Core.Model.Equipment.FilterInfo, {_NINA_CORE}",
        "_name": name, "_focusOffset": 0, "_position": position,
        "_autoFocusExposureTime": -1.0, "_autoFocusFilter": False,
    }


def _nina_binning(ids, binning):
    # @args: binning - "2x2" | 2 | None -> (X, Y) as a BinningMode object
    factor = 1
    text = str(binning or "").strip().lower()
    if "x" in text:
        parts = text.split("x")
        try:
            factor = int(parts[0])
        except ValueError:
            factor = 1
    elif text.isdigit():
        factor = int(text)
    return {"$id": ids.next(),
            "$type": f"NINA.Core.Model.Equipment.BinningMode, {_NINA_CORE}",
            "X": factor, "Y": factor}


def _nina_light_steps(plan):
    # @return: [(filter, count, exposure_s), ...] from the plan's steps
    steps = plan.get("steps")
    if steps:
        return [(s["filter"], int(s["n_frames"]), float(s["exp_s"]))
                for s in steps]
    return [(plan["filter"], int(plan["n_frames"]), float(plan["exp_s"]))]


def _nina_triggers(ids, dso_id, plan):
    # Dither and autofocus as NINA TRIGGERS on the target container, from the
    # recipe (ADR-083): they fire every N frames / on time / on temperature /
    # on filter change, exactly as NINA models them.
    d = plan.get("dither") or {}
    a = plan.get("autofocus") or {}
    out = []
    if d.get("on") and int(d.get("every") or 0) > 0:
        runner = _nina_trigger_runner(ids, None, {
            "$id": ids.next(),
            "$type": "NINA.Sequencer.SequenceItem.Guider.Dither, NINA",
            "Parent": None, "ErrorBehavior": 0, "Attempts": 1})
        out.append({
            "$id": ids.next(),
            "$type": "NINA.Sequencer.Trigger.Guider.DitherAfterExposures, NINA",
            "AfterExposures": int(d["every"]),
            "Parent": {"$ref": dso_id}, "TriggerRunner": runner})
    if a.get("on"):
        def _af(label, extra):
            runner = _nina_trigger_runner(ids, None, {
                "$id": ids.next(),
                "$type": "NINA.Sequencer.SequenceItem.Autofocus.RunAutofocus, NINA",
                "Parent": None, "ErrorBehavior": 0, "Attempts": 1})
            trig = {"$id": ids.next(), "$type": label,
                    "Parent": {"$ref": dso_id}, "TriggerRunner": runner}
            trig.update(extra)
            return trig
        if int(a.get("every") or 0) > 0:
            out.append(_af("NINA.Sequencer.Trigger.Autofocus.AutofocusAfterExposures, NINA",
                           {"AfterExposures": int(a["every"])}))
        if int(a.get("minutes") or 0) > 0:
            out.append(_af("NINA.Sequencer.Trigger.Autofocus.AutofocusAfterTimeTrigger, NINA",
                           {"Amount": float(a["minutes"])}))
        if float(a.get("delta_c") or 0.0) > 0:
            out.append(_af("NINA.Sequencer.Trigger.Autofocus.AutofocusAfterTemperatureChangeTrigger, NINA",
                           {"Amount": float(a["delta_c"])}))
        if a.get("on_filter"):
            out.append(_af("NINA.Sequencer.Trigger.Autofocus.AutofocusAfterFilterChange, NINA", {}))
    return out


def export_nina(target, plan, out):
    # The NATIVE NINA sequence JSON (SequenceRootContainer), loadable by NINA
    # via /sequence/load. PENDING confirmation against a real NINA/PINS: the
    # structure is pinned against NINA's test corpus, the $type strings may
    # need a tweak per version.
    # @args: target - dict with name, ra_deg, dec_deg, plan - make_plan dict,
    #        out - output path (.json)
    # @return: the output path
    name = target.get("name") or target.get("id") or "target"
    ra_h, ra_m, ra_s = _deg_to_hms(target.get("ra_deg", 0.0))
    sign, dec_d, dec_m, dec_s = _deg_to_dms(target.get("dec_deg", 0.0))
    ids = _NinaIds()

    root = _nina_container(
        ids, f"NINA.Sequencer.Container.SequenceRootContainer, NINA",
        name, [], None)
    root_id = root["$id"]
    start = _nina_container(
        ids, f"NINA.Sequencer.Container.StartAreaContainer, NINA",
        "Start", [], root_id, strategy=_STRAT_PAR)
    end = _nina_container(
        ids, f"NINA.Sequencer.Container.EndAreaContainer, NINA",
        "End", [], root_id, strategy=_STRAT_PAR)
    target_area = _nina_container(
        ids, f"NINA.Sequencer.Container.TargetAreaContainer, NINA",
        "Target", [], root_id)

    # the target itself
    coords = {"$id": ids.next(),
              "$type": f"NINA.Astrometry.InputCoordinates, {_NINA_ASTRO}",
              "RAHours": ra_h, "RAMinutes": ra_m, "RASeconds": ra_s,
              "NegativeDec": sign < 0,
              "DecDegrees": dec_d, "DecMinutes": dec_m, "DecSeconds": dec_s}
    input_target = {"$id": ids.next(),
                    "$type": f"NINA.Astrometry.InputTarget, {_NINA_ASTRO}",
                    "Expanded": True, "TargetName": name,
                    "PositionAngle": 0.0, "InputCoordinates": coords}
    dso = {
        "$id": ids.next(),
        "$type": "NINA.Sequencer.Container.DeepSkyObjectContainer, NINA",
        "Target": input_target, "ExposureInfoListExpanded": False,
        "ExposureInfoList": {
            "$id": ids.next(),
            "$type": ("NINA.Core.Utility.AsyncObservableCollection`1"
                      f"[[NINA.Sequencer.Utility.ExposureInfo, NINA]], {_NINA_CORE}"),
            "$values": []},
        "Strategy": {"$type": _STRAT_SEQ}, "Name": name,
        "Conditions": _nina_coll(ids, _COLL_COND, []),
        "IsExpanded": True, "Items": None, "Triggers": None,
        "Parent": {"$ref": target_area["$id"]},
        "ErrorBehavior": 0, "Attempts": 1,
    }
    dso_id = dso["$id"]

    # per band: SwitchFilter + TakeManyExposures(LoopCondition) -> TakeExposure
    gain = int(plan["gain"]) if plan.get("gain") not in (None, "") else -1
    offset = int(plan["offset"]) if plan.get("offset") not in (None, "") else -1
    binning = _nina_binning(ids, plan.get("binning"))
    items = []
    for position, (filter_name, count, exposure) in enumerate(
            _nina_light_steps(plan)):
        items.append({
            "$id": ids.next(),
            "$type": "NINA.Sequencer.SequenceItem.FilterWheel.SwitchFilter, NINA",
            "Filter": _nina_filter(ids, filter_name, position),
            "Parent": {"$ref": dso_id}, "ErrorBehavior": 0, "Attempts": 1})
        tme = _nina_container(
            ids, "NINA.Sequencer.SequenceItem.Imaging.TakeManyExposures, NINA",
            f"{filter_name} x{count}", [], dso_id, expanded=False)
        loop = {"$id": ids.next(),
                "$type": "NINA.Sequencer.Conditions.LoopCondition, NINA",
                "CompletedIterations": 0, "Iterations": int(count),
                "Parent": {"$ref": tme["$id"]}}
        tme["Conditions"]["$values"] = [loop]
        tme["Items"]["$values"] = [{
            "$id": ids.next(),
            "$type": "NINA.Sequencer.SequenceItem.Imaging.TakeExposure, NINA",
            "ExposureTime": float(exposure), "Gain": gain, "Offset": offset,
            "Binning": binning, "ImageType": "LIGHT", "ExposureCount": 0,
            "Parent": {"$ref": tme["$id"]},
            "ErrorBehavior": 0, "Attempts": 1}]
        items.append(tme)

    # The calibration steps run AFTER the light frames (2026-10-16): they are
    # the last thing the night does, and NINA's own ImageType says what each
    # one is, so nothing has to be guessed from the file name. A bias goes in
    # with exposure 0, which is what NINA expects for it.
    for frame_type, key, default_filter in (("DARK", "darks", "Dark"),
                                            ("BIAS", "bias", "Dark")):
        step = plan.get(key) or {}
        count = int(step.get("count") or 0)
        if count <= 0:
            continue
        filter_name = step.get("filter") or default_filter
        exposure = float(step.get("exp_s") or 0.0) if frame_type == "DARK" \
            else 0.0
        items.append({
            "$id": ids.next(),
            "$type": "NINA.Sequencer.SequenceItem.FilterWheel.SwitchFilter, NINA",
            "Filter": _nina_filter(ids, filter_name, 0),
            "Parent": {"$ref": dso_id}, "ErrorBehavior": 0, "Attempts": 1})
        tme = _nina_container(
            ids, "NINA.Sequencer.SequenceItem.Imaging.TakeManyExposures, NINA",
            f"{frame_type.title()} x{count}", [], dso_id, expanded=False)
        loop = {"$id": ids.next(),
                "$type": "NINA.Sequencer.Conditions.LoopCondition, NINA",
                "CompletedIterations": 0, "Iterations": count,
                "Parent": {"$ref": tme["$id"]}}
        tme["Conditions"]["$values"] = [loop]
        tme["Items"]["$values"] = [{
            "$id": ids.next(),
            "$type": "NINA.Sequencer.SequenceItem.Imaging.TakeExposure, NINA",
            "ExposureTime": exposure, "Gain": gain, "Offset": offset,
            "Binning": binning, "ImageType": frame_type, "ExposureCount": 0,
            "Parent": {"$ref": tme["$id"]},
            "ErrorBehavior": 0, "Attempts": 1}]
        items.append(tme)

    dso["Items"] = _nina_coll(ids, _COLL_ITEM, items)
    dso["Triggers"] = _nina_coll(ids, _COLL_TRIG,
                                 _nina_triggers(ids, dso_id, plan))
    target_area["Items"] = _nina_coll(ids, _COLL_ITEM, [dso])
    root["Items"] = _nina_coll(ids, _COLL_ITEM, [start, target_area, end])

    Path(out).write_text(json.dumps(root, indent=2, ensure_ascii=False),
                         encoding="utf-8")
    logger.info("NINA native sequence written to %s", out)
    return str(out)


# ---- CCDciel ".targets" format -------------------------------------------
#
# Locked against the user's real file docs/ccdciel_sequence_sample.targets:
# <CONFIG Version="5"> wrapping <Targets>/<Startup>/<Termination>. Each
# target carries the full set of attributes CCDciel writes; the plan steps
# keep the sample's conventions (Binning "1x1", Gain 1, Offset 0, dither/
# autofocus flags on the Light step, calibration frames without them).


def _ccdciel_target(attrs):
    # Ordered attribute list for a <TargetN> element. The order mirrors the
    # sample file so diffs against a real export stay readable. Track D: a
    # transit capture window switches the rise/set defaults for a mandatory
    # start (attrs "mandatory"/"start_rise").
    return (
        ("PA", "-"), ("RA", attrs["ra"]), ("Dec", attrs["dec"]),
        ("Path", ""), ("Plan", ""), ("Skip", "False"),
        ("Delay", str(attrs.get("delay", "0"))),
        ("EndSet", "True"), ("EndTime", attrs["end"]),
        ("Preview", "False"), ("FlatBinX", "0"), ("FlatBinY", "0"),
        ("FlatGain", "0"), ("DarkNight", "False"), ("FlatCount", "0"),
        ("FlatFstop", ""), ("StartRise", attrs.get("start_rise", "True")),
        ("StartTime", attrs["start"]),
        ("FlatOffset", "0"), ("ObjectName", attrs["name"]),
        ("RepeatDone", "0"), ("ScriptArgs", ""), ("EndMeridian", "-9999"),
        ("FlatFilters", ""), ("HFM_Enabled", "True"), ("RepeatCount", "1"),
        ("UpdateCoord", "False"),
        ("AutofocusTemp", attrs.get("autofocus_temp", "False")),
        ("SolarTracking", "False"), ("StartMeridian", "-9999"),
        ("PreviewExposure", "0.001"), ("InplaceAutofocus", "True"),
        ("AstrometryPointing", "True"),
        ("MandatoryStartTime", attrs.get("mandatory", "False")),
        ("NoAutoguidingChange", "False"),
    )


def _ccdciel_step(index, spec):
    # Ordered attribute list for the <StepN> element of one capture step.
    # ADR-083: gain, offset and binning come from the step spec (the plan's
    # recipe), so a capture option chosen in the app reaches the file.
    # @args: index - step number (1-based), spec - dict with the values
    # @return: the attribute tuples
    return (
        ("Done", "0"), ("Gain", spec.get("gain", "1")), ("Type", "0"),
        ("Count", spec["count"]),
        ("Fstop", ""), ("Dither", spec["dither"]), ("Filter", spec["filter"]),
        ("Offset", spec.get("offset", "0")), ("Binning",
                                              spec.get("binning", "1x1")),
        ("Exposure", spec["exposure"]),
        ("Autofocus", spec["autofocus"]), ("FrameType", spec["frame_type"]),
        ("ScriptArgs", ""), ("ScriptName", ""), ("ScriptPath", ""),
        ("StackCount", "1"), ("SwitchName", ""),
        ("Description", spec["description"]), ("DitherCount", spec["dither_count"]),
        ("SwitchValue", ""), ("AutofocusCount", spec["autofocus_count"]),
        ("AutofocusStart", spec["autofocus_start"]), ("SwitchNickname", ""),
    )


def _camera_attrs(plan):
    # @args: plan - make_plan dict
    # @return: the Gain/Offset/Binning strings for a step, from the recipe
    #          (ADR-083). The sample's defaults (1 / 0 / 1x1) when unset.
    gain = plan.get("gain")
    offset = plan.get("offset")
    return {"gain": str(gain) if gain not in (None, "") else "1",
            "offset": str(offset) if offset not in (None, "") else "0",
            "binning": str(plan.get("binning") or "1x1")}


def _light_spec(plan, count, exposure, filter_name):
    # One Light step, carrying the plan's dither and autofocus options
    # (ADR-083). Without a recipe the sample's conventions are kept: dither
    # on, autofocus at the start, the counts the sample file uses.
    d = plan.get("dither") or {}
    a = plan.get("autofocus") or {}
    on = d.get("on", True)
    every = int(d.get("every") or 0)
    af_on = a.get("on", True)
    spec = {"count": str(count), "exposure": f"{exposure:g}",
            "filter": filter_name, "frame_type": "Light",
            "description": "Light",
            "dither": "True" if on else "False",
            "dither_count": str(every) if (on and every) else "25",
            "autofocus": "True" if af_on else "False",
            "autofocus_start": "True",
            "autofocus_count": str(int(a.get("every") or 0) or 50)}
    spec.update(_camera_attrs(plan))
    return spec


def _light_step(plan):
    # The light step: the actual NightScribe plan.
    return _light_spec(plan, plan["n_frames"], plan["exp_s"], plan["filter"])


def _calibration_steps(plan):
    # Dark/Bias steps: counted, no dither, no autofocus (sample: Filter
    # "Dark" for both, bias exposure 0).
    steps = []
    cam = _camera_attrs(plan)
    darks = plan["darks"]
    if darks["count"] > 0:
        spec = {"count": str(darks["count"]),
                "exposure": f"{darks['exp_s']:g}",
                "filter": darks.get("filter") or "Dark",
                "frame_type": "Dark", "description": "Dark", "dither": "False",
                "autofocus": "False", "autofocus_start": "False",
                "dither_count": "0", "autofocus_count": "0"}
        spec.update(cam)
        steps.append(spec)
    bias = plan["bias"]
    if bias["count"] > 0:
        spec = {"count": str(bias["count"]), "exposure": "0",
                "filter": bias.get("filter") or "Dark", "frame_type": "Bias",
                "description": "Bias",
                "dither": "False", "autofocus": "False",
                "autofocus_start": "False", "dither_count": "0",
                "autofocus_count": "0"}
        spec.update(cam)
        steps.append(spec)
    return steps


def _ccdciel_times(target):
    # Start/End window for the target, as UTC "HH:MM:SS", and whether the
    # start is MANDATORY. A transit capture window (Track D) must start on
    # time — the pre-ingress baseline is what the light curve is compared
    # against — so it writes the capture window with mandatory start.
    # Otherwise CCDciel runs with StartRise/EndSet (it recomputes rise/set
    # from its own observatory settings) and NightScribe's safe window, when
    # known, is written as informative values.
    # @args: target - dict with optional "capture_start"/"capture_end"
    #         (transit) or "safe_window" ("ISO|ISO")
    # @return: (start "HH:MM:SS", end "HH:MM:SS", mandatory bool)
    def hhmmss(value):
        try:
            return datetime.datetime.fromisoformat(str(value)).strftime(
                "%H:%M:%S")
        except (ValueError, TypeError):
            return "0:00:00"
    tw = _transit_window(target)
    if tw:
        # a capture_advisory window (HADS, ADR-034) writes the times but
        # keeps the start soft: any contiguous run inside the safe span is
        # scientifically fine, so CCDciel is free to schedule around it
        mandatory = not target.get("capture_advisory", False)
        return tw[0].strftime("%H:%M:%S"), tw[1].strftime("%H:%M:%S"), mandatory
    sw = target.get("safe_window")
    if sw:
        try:
            s0, s1 = str(sw).split("|")
            return hhmmss(s0), hhmmss(s1), False
        except ValueError:
            pass
    return "0:00:00", "0:00:00", False


def _ra_sex(ra_deg):
    # RA in CCDciel's sexagesimal form ("00h37m28s").
    # @args: ra_deg - right ascension in degrees
    # @return: the "HHhMMmSSs" string
    s = int(round(ra_deg * 240.0)) % 86400  # deg -> seconds of time
    return f"{s // 3600:02d}h{(s % 3600) // 60:02d}m{s % 60:02d}s"


def _dec_sex(dec_deg):
    # Dec in CCDciel's sexagesimal form ("+72d20m51s").
    # @args: dec_deg - declination in degrees
    # @return: the "sDDdMMmSSs" string
    sign = "+" if dec_deg >= 0 else "-"
    s = int(round(abs(dec_deg) * 3600.0)) % 1296000  # deg -> arcseconds
    return f"{sign}{s // 3600:02d}d{(s % 3600) // 60:02d}m{s % 60:02d}s"


def _light_steps(plan):
    # @return: list of light-step specs. B8: multi-filter plans carry
    #         one step per filter in plan["steps"]; single-filter plans
    #         have a single entry built from the legacy fields. Every step
    #         carries the plan's dither/autofocus/camera options (ADR-083).
    steps = plan.get("steps")
    if steps:
        return [_light_spec(plan, s["n_frames"], s["exp_s"], s["filter"])
                for s in steps]
    return [_light_step(plan)]


def export_ccdciel(target, plan, out):
    # CCDciel target-list file ("<CONFIG Version="5">), the real format the
    # sequence tool reads and writes; see docs/ccdciel_sequence_sample.targets.
    # The target keeps CCDciel's default rise/set window; the plan becomes a
    # Light step plus optional Dark/Bias calibration steps. B8: a multi-filter
    # plan writes one Light step per filter. Track D: a transit capture
    # window writes StartTime/EndTime with MandatoryStartTime=True and
    # StartRise=False — best-effort until validated against the observatory's
    # real CCDciel (ADR-021 philosophy).
    # @args: target - dict with name, ra_deg, dec_deg, safe_window,
    #        capture_start/capture_end (transit); plan - make_plan dict;
    #        out - output path (.targets)
    # @return: the output path
    name = target.get("name") or target.get("id") or "target"
    ra_deg = target.get("ra_deg", 0.0)
    dec_deg = target.get("dec_deg", 0.0)
    start_t, end_t, mandatory = _ccdciel_times(target)
    steps = [*_light_steps(plan), *_calibration_steps(plan)]

    root = ET.Element("CONFIG")
    for k, v in (("Version", "5"), ("ListName", name),
                 ("TargetNum", "1"), ("RepeatCount", "1")):
        root.set(k, str(v))
    targets = ET.SubElement(root, "Targets")
    for k, v in (("RepeatDone", "0"), ("ResetRepeat", "True"),
                 ("IgnoreRestart", "False")):
        targets.set(k, v)
    t1 = ET.SubElement(targets, "Target1")
    _af = plan.get("autofocus") or {}
    for k, v in _ccdciel_target({
            "name": name, "ra": _ra_sex(ra_deg), "dec": _dec_sex(dec_deg),
            "start": start_t, "end": end_t,
            "mandatory": "True" if mandatory else "False",
            "start_rise": "False" if mandatory else "True",
            "delay": plan.get("delay_s") or 0,
            # temperature-triggered autofocus when the recipe asks for it
            "autofocus_temp": "True" if _af.get("delta_c") else "False"}):
        t1.set(k, str(v))
    plan_el = ET.SubElement(t1, "Plan")
    plan_el.set("Name", "")
    plan_el.set("StepNum", str(len(steps)))
    steps_el = ET.SubElement(plan_el, "Steps")
    for i, spec in enumerate(steps, start=1):
        step_el = ET.SubElement(steps_el, f"Step{i}")
        for k, v in _ccdciel_step(i, spec):
            step_el.set(k, str(v))
    startup = ET.SubElement(root, "Startup")
    for k, v in (("Unpark", "False"), ("SeqStop", "False"),
                 ("SeqStart", "False"), ("RunScript", "False"),
                 ("SeqStopAt", "0:00:00"), ("CoolCamera", "False"),
                 ("SeqStartAt", "22:30:00"), ("StartScript", ""),
                 ("SeqStopTwilight", "False"), ("SeqStartTwilight", "False")):
        startup.set(k, v)
    term = ET.SubElement(root, "Termination")
    for k, v in (("Park", "False"), ("CloseDome", "False"),
                 ("EndScript", ""), ("RunScript", "False"),
                 ("WarmCamera", "True"), ("ErrorScript", ""),
                 ("StopTracking", "True"), ("ErrorRunScript", "False")):
        term.set(k, v)
    ET.indent(root, space="  ")
    xml = '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(
        root, encoding="unicode") + "\n"
    Path(out).write_text(xml, encoding="utf-8")
    logger.info("CCDciel target list written to %s", out)
    return str(out)


def export(target, plan, out, fmt="csv"):
    # Dispatcher: picks the exporter for the given format.
    # @args: target - dict, plan - make_plan dict, out - path,
    #        fmt - "csv"|"nina"|"nina_summary"|"ccdciel"
    # @return: output path
    out = Path(out)
    if fmt == "nina":
        return export_nina(target, plan, out.with_suffix(".json"))
    if fmt == "nina_summary":
        return export_nina_summary(target, plan, out.with_suffix(".plan.json"))
    if fmt == "ccdciel":
        return export_ccdciel(target, plan, out.with_suffix(".targets"))
    return export_csv(target, plan, out.with_suffix(".csv"))


# ---- helpers ----

def _deg_to_hms(ra_deg):
    # @return: (hours, minutes, seconds) as ints/floats
    hours = ra_deg / 15.0
    h = int(hours)
    m = int((hours - h) * 60)
    s = round((hours - h - m / 60.0) * 3600, 2)
    return h, m, s


def _deg_to_dms(dec_deg):
    # @return: (sign, degrees, minutes, seconds) sign is +1/-1
    sign = 1 if dec_deg >= 0 else -1
    dec = abs(dec_deg)
    d = int(dec)
    m = int((dec - d) * 60)
    s = round((dec - d - m / 60.0) * 3600, 2)
    return sign, d, m, s


def _write_csv(path, headers, rows):
    # @args: path - output path, headers - column names, rows - list of dicts
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        w.writerows(rows)