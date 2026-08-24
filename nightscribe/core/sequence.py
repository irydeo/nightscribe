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
# reader. The NINA/CCDciel native formats are validated against the user's
# actual software versions during phase 5; the structures below are the
# best-effort starting points to be confirmed.


def make_plan(n_frames, exp_s, filter_name="L", overhead_s=None, cfg=None):
    # Builds a capture plan dict from parameters + config defaults.
    # @args: n_frames - frame count, exp_s - exposure per frame in seconds,
    #        filter_name - filter wheel slot name, overhead_s - readout/slew
    #        per frame (defaults to config), cfg - Config
    # @return: {"n_frames", "exp_s", "filter", "overhead_s", "duration_s"}
    if overhead_s is None:
        overhead_s = float(cfg.get("overhead_s", 15.0)) if cfg else 15.0
    total = n_frames * (float(exp_s) + float(overhead_s))
    return {"n_frames": int(n_frames), "exp_s": float(exp_s),
            "filter": filter_name, "overhead_s": float(overhead_s),
            "duration_s": total}


def export_csv(target, plan, out):
    # Generic CSV: one row per frame, readable by any capture software.
    # @args: target - dict with name, ra_deg, dec_deg, plan - make_plan dict,
    #        out - output path
    # @return: the output path
    name = target.get("name") or target.get("id") or "target"
    ra = target.get("ra_deg", 0.0)
    dec = target.get("dec_deg", 0.0)
    rows = []
    for i in range(plan["n_frames"]):
        rows.append({
            "frame": i + 1, "target": name,
            "ra_deg": f"{ra:.6f}", "dec_deg": f"{dec:+.6f}",
            "exposure_s": plan["exp_s"], "filter": plan["filter"],
        })
    _write_csv(out, ["frame", "target", "ra_deg", "dec_deg",
                     "exposure_s", "filter"], rows)
    logger.info("CSV sequence written to %s", out)
    return str(out)


def export_nina(target, plan, out):
    # NINA sequence JSON. Basic structure with target coordinates and a
    # flat list of exposure items. Validate against your NINA version.
    # @args: target - dict with name, ra_deg, dec_deg, plan - make_plan dict,
    #        out - output path (.json)
    # @return: the output path
    name = target.get("name") or target.get("id") or "target"
    ra_deg = target.get("ra_deg", 0.0)
    dec_deg = target.get("dec_deg", 0.0)
    # split degrees into HMS/DMS for NINA's coordinate format
    ra_h, ra_m, ra_s = _deg_to_hms(ra_deg)
    sign, dec_d, dec_m, dec_s = _deg_to_dms(dec_deg)
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
            "Exposures": [
                {"ExposureTime": plan["exp_s"], "Filter": plan["filter"],
                 "Binning": 1}
            ] * plan["n_frames"],
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


def export_ccdciel(target, plan, out):
    # CCDciel plan file (XML). Basic structure with target, exposure and
    # filter. Validate against your CCDciel version.
    # @args: target - dict with name, ra_deg, dec_deg, plan - make_plan dict,
    #        out - output path (.xml)
    # @return: the output path
    name = target.get("name") or target.get("id") or "target"
    ra_deg = target.get("ra_deg", 0.0)
    dec_deg = target.get("dec_deg", 0.0)
    root = ET.Element("plan")
    ET.SubElement(root, "name").text = name
    ET.SubElement(root, "target").text = name
    coords = ET.SubElement(root, "coordinates")
    ET.SubElement(coords, "ra_deg").text = f"{ra_deg:.6f}"
    ET.SubElement(coords, "dec_deg").text = f"{dec_deg:+.6f}"
    ET.SubElement(coords, "epoch").text = "J2000"
    seq = ET.SubElement(root, "sequence")
    for i in range(plan["n_frames"]):
        item = ET.SubElement(seq, "exposure")
        item.set("index", str(i + 1))
        ET.SubElement(item, "exposure_s").text = str(plan["exp_s"])
        ET.SubElement(item, "filter").text = plan["filter"]
        ET.SubElement(item, "binning").text = "1"
    meta = ET.SubElement(root, "metadata")
    ET.SubElement(meta, "generator").text = "NightScribe"
    ET.SubElement(meta, "created").text = (
        datetime.datetime.now(datetime.timezone.utc).isoformat())
    ET.SubElement(meta, "frame_count").text = str(plan["n_frames"])
    ET.indent(root, space="  ")
    Path(out).write_text(
        ET.tostring(root, encoding="unicode") + "\n", encoding="utf-8")
    logger.info("CCDciel plan written to %s", out)
    return str(out)


def export(target, plan, out, fmt="csv"):
    # Dispatcher: picks the exporter for the given format.
    # @args: target - dict, plan - make_plan dict, out - path, fmt - "csv"|"nina"|"ccdciel"
    # @return: output path
    out = Path(out)
    if fmt == "nina":
        return export_nina(target, plan, out.with_suffix(".json"))
    if fmt == "ccdciel":
        return export_ccdciel(target, plan, out.with_suffix(".xml"))
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
