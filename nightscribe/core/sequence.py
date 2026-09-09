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
              n_darks=0, exp_dark=None, n_bias=0, steps=None):
    # Builds a capture plan dict from parameters + config defaults.
    # Calibration frames are optional: Dark (count + exposure) and Bias
    # (count) steps get appended to the sequence and their wall-clock time
    # is folded into duration_s (each cal frame still pays the overhead).
    # B8: multi-filter — pass steps=[(filter, n, exp), ...] for interleaved
    # bands. Retrocompatible: a single-filter call (n_frames, exp_s,
    # filter_name) is equivalent to steps=[(filter_name, n_frames, exp_s)].
    # @args: n_frames - light frame count (ignored when steps is given),
    #        exp_s - exposure per light frame (ignored when steps is given),
    #        filter_name - filter wheel slot name (ignored when steps),
    #        overhead_s - readout/slew per frame (defaults to config),
    #        cfg - Config, n_darks - dark count, exp_dark - dark exp,
    #        n_bias - bias count,
    #        steps - list of (filter, n_frames, exp_s) tuples for multi-filter
    # @return: {"n_frames", "exp_s", "filter", "overhead_s", "darks",
    #           "bias", "duration_s", "steps"}
    if overhead_s is None:
        overhead_s = float(cfg.get("overhead_s", 15.0)) if cfg else 15.0
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
    total = (total_light if steps else
             n_frames * (exp_s + overhead_s))
    total += n_darks * (exp_dark + overhead_s) + n_bias * overhead_s
    return {"n_frames": n_frames, "exp_s": exp_s,
            "filter": filter_name, "overhead_s": float(overhead_s),
            "darks": {"count": n_darks, "exp_s": exp_dark},
            "bias": {"count": n_bias},
            "duration_s": total,
            "steps": light_steps}


def export_csv(target, plan, out):
    # Generic CSV: one row per frame, readable by any capture software.
    # B8: multi-filter plans emit rows with the per-step filter.
    # @args: target - dict with name, ra_deg, dec_deg, plan - make_plan dict,
    #        out - output path
    # @return: the output path
    name = target.get("name") or target.get("id") or "target"
    ra = target.get("ra_deg", 0.0)
    dec = target.get("dec_deg", 0.0)
    rows = []
    for s in plan.get("steps", [{"filter": plan["filter"],
                                 "n_frames": plan["n_frames"],
                                 "exp_s": plan["exp_s"]}]):
        for i in range(s["n_frames"]):
            rows.append({
                "frame": len(rows) + 1, "target": name,
                "ra_deg": f"{ra:.6f}", "dec_deg": f"{dec:+.6f}",
                "exposure_s": s["exp_s"], "filter": s["filter"],
            })
    _write_csv(out, ["frame", "target", "ra_deg", "dec_deg",
                 "exposure_s", "filter"], rows)
    logger.info("CSV sequence written to %s", out)
    return str(out)


def export_nina(target, plan, out):
    # NINA sequence JSON. Basic structure with target coordinates and a
    # flat list of exposure items. B8: multi-filter plans emit
    # one exposure entry per filter step.
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
        "Description": f"NightScribe sequence for {name}",
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
    Path(out).write_text(json.dumps(seq, indent=2, ensure_ascii=False),
                         encoding="utf-8")
    logger.info("NINA sequence written to %s", out)
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
    # sample file so diffs against a real export stay readable.
    return (
        ("PA", "-"), ("RA", attrs["ra"]), ("Dec", attrs["dec"]),
        ("Path", ""), ("Plan", ""), ("Skip", "False"), ("Delay", "0"),
        ("EndSet", "True"), ("EndTime", attrs["end"]),
        ("Preview", "False"), ("FlatBinX", "0"), ("FlatBinY", "0"),
        ("FlatGain", "0"), ("DarkNight", "False"), ("FlatCount", "0"),
        ("FlatFstop", ""), ("StartRise", "True"), ("StartTime", attrs["start"]),
        ("FlatOffset", "0"), ("ObjectName", attrs["name"]),
        ("RepeatDone", "0"), ("ScriptArgs", ""), ("EndMeridian", "-9999"),
        ("FlatFilters", ""), ("HFM_Enabled", "True"), ("RepeatCount", "1"),
        ("UpdateCoord", "False"), ("AutofocusTemp", "False"),
        ("SolarTracking", "False"), ("StartMeridian", "-9999"),
        ("PreviewExposure", "0.001"), ("InplaceAutofocus", "True"),
        ("AstrometryPointing", "True"), ("MandatoryStartTime", "False"),
        ("NoAutoguidingChange", "False"),
    )


def _ccdciel_step(index, spec):
    # Ordered attribute list for the <StepN> element of one capture step.
    # @args: index - step number (1-based), spec - dict with the values
    # @return: the attribute tuples
    return (
        ("Done", "0"), ("Gain", "1"), ("Type", "0"), ("Count", spec["count"]),
        ("Fstop", ""), ("Dither", spec["dither"]), ("Filter", spec["filter"]),
        ("Offset", "0"), ("Binning", "1x1"), ("Exposure", spec["exposure"]),
        ("Autofocus", spec["autofocus"]), ("FrameType", spec["frame_type"]),
        ("ScriptArgs", ""), ("ScriptName", ""), ("ScriptPath", ""),
        ("StackCount", "1"), ("SwitchName", ""),
        ("Description", spec["description"]), ("DitherCount", spec["dither_count"]),
        ("SwitchValue", ""), ("AutofocusCount", spec["autofocus_count"]),
        ("AutofocusStart", spec["autofocus_start"]), ("SwitchNickname", ""),
    )


def _light_step(plan):
    # The light step: the actual NightScribe plan, with dithering and an
    # autofocus at the start (sample conventions).
    return {"count": plan["n_frames"], "exposure": f"{plan['exp_s']:g}",
            "filter": plan["filter"], "frame_type": "Light",
            "description": "Light", "dither": "True", "autofocus": "True",
            "autofocus_start": "True", "dither_count": "25",
            "autofocus_count": "50"}


def _calibration_steps(plan):
    # Dark/Bias steps: counted, no dither, no autofocus (sample: Filter
    # "Dark" for both, bias exposure 0).
    steps = []
    darks = plan["darks"]
    if darks["count"] > 0:
        steps.append({"count": darks["count"], "exposure": f"{darks['exp_s']:g}",
                      "filter": "Dark", "frame_type": "Dark",
                      "description": "Dark", "dither": "False",
                      "autofocus": "False", "autofocus_start": "False",
                      "dither_count": "0", "autofocus_count": "0"})
    bias = plan["bias"]
    if bias["count"] > 0:
        steps.append({"count": bias["count"], "exposure": "0",
                      "filter": "Dark", "frame_type": "Bias",
                      "description": "Bias", "dither": "False",
                      "autofocus": "False", "autofocus_start": "False",
                      "dither_count": "0", "autofocus_count": "0"})
    return steps


def _ccdciel_times(target):
    # Start/End window for the target, as UTC "HH:MM:SS". CCDciel runs with
    # StartRise/EndSet anyway (it recomputes rise/set from its own observatory
    # settings); when NightScribe knows the safe window these are the
    # informative values written to the file.
    # @args: target - dict with optional "safe_window" ("ISO|ISO")
    # @return: (start "HH:MM:SS", end "HH:MM:SS"), defaulting to "0:00:00"
    def hhmmss(value):
        try:
            return datetime.datetime.fromisoformat(str(value)).strftime(
                "%H:%M:%S")
        except (ValueError, TypeError):
            return "0:00:00"
    sw = target.get("safe_window")
    if sw:
        try:
            s0, s1 = str(sw).split("|")
            return hhmmss(s0), hhmmss(s1)
        except ValueError:
            pass
    return "0:00:00", "0:00:00"


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
    #         have a single entry built from the legacy fields.
    steps = plan.get("steps")
    if steps:
        return [{"count": s["n_frames"], "exposure": f"{s['exp_s']:g}",
                 "filter": s["filter"], "frame_type": "Light",
                 "description": "Light", "dither": "True",
                 "autofocus": "True", "autofocus_start": "True",
                 "dither_count": "25", "autofocus_count": "50"}
                for s in steps]
    return [_light_step(plan)]


def export_ccdciel(target, plan, out):
    # CCDciel target-list file ("<CONFIG Version="5">), the real format the
    # sequence tool reads and writes; see docs/ccdciel_sequence_sample.targets.
    # The target keeps CCDciel's default rise/set window; the plan becomes a
    # Light step plus optional Dark/Bias calibration steps. B8: a multi-filter
    # plan writes one Light step per filter.
    # @args: target - dict with name, ra_deg, dec_deg, safe_window; plan -
    #        make_plan dict; out - output path (.targets)
    # @return: the output path
    name = target.get("name") or target.get("id") or "target"
    ra_deg = target.get("ra_deg", 0.0)
    dec_deg = target.get("dec_deg", 0.0)
    start_t, end_t = _ccdciel_times(target)
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
    for k, v in _ccdciel_target({
            "name": name, "ra": _ra_sex(ra_deg), "dec": _dec_sex(dec_deg),
            "start": start_t, "end": end_t}):
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
    # @args: target - dict, plan - make_plan dict, out - path, fmt - "csv"|"nina"|"ccdciel"
    # @return: output path
    out = Path(out)
    if fmt == "nina":
        return export_nina(target, plan, out.with_suffix(".json"))
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