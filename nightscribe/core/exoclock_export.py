############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - ExoClock export module (series plan, phase 8)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Prepare an ExoClock submission by hand (ADR-049, phase 8).

ExoClock has no public upload API (verified 2026-09-27; /upload/ is behind
a login and robots forbids scraping), so the app writes the two files the
project expects and opens the upload page in the browser:

  1. a three-column text file: JD_UTC of the exposure START, relative
     flux (the series' differential flux, target over the comparison
     ensemble) and its error (HOPS format);
  2. ExoClock_info.txt with the observer's metadata and a prefilled
     Comments field (the honest self-assessment).

No credentials, no network calls, no scraping. A point without an exposure
time cannot be exported: the start instant would be a lie (D15), so it is
refused in plain language.
"""

import logging
import math
from pathlib import Path

from . import variables

logger = logging.getLogger(__name__)

# ExoClock's own recommendation (Kokori et al. 2021): observers may upload
# any time basis, JD_UTC recommended, and the server converts to BJD_TDB.
TIME_FORMAT = "JD_UTC"
TIME_STAMP = "Exposure start"
FLUX_FORMAT = "Flux"


def _flux_err(flux, mag_err):
    # dm = 1.086 dF/F -> dF = F * dm / 1.086
    if flux is None or mag_err is None:
        return None
    return flux * mag_err / 1.0857


def _ref_mag(mags):
    # The out-of-transit reference: the median magnitude of the series.
    vals = [m for m in mags if m is not None]
    if not vals:
        return None
    return float(sorted(vals)[len(vals) // 2])


def build_data(points):
    # Build the three-column rows (JD_UTC start, relative flux, error).
    # The reference flux is the series' median magnitude (out of transit),
    # so flux ~ 1 on the baseline and dips in transit.
    # @args: points - dicts with mjd (mid exposure), mag, err, exptime
    #        (seconds; the group's total integration when grouped)
    # @return: (rows, warnings): rows are (jd_start, flux, flux_err) with
    #          None flux/err when the point carries no magnitude
    warnings = []
    mags = [p.get("mag") for p in points]
    ref = _ref_mag(mags)
    rows = []
    for p in points:
        mjd = p.get("mjd")
        exp = p.get("exptime")
        if mjd is None:
            warnings.append("point without a time")
            continue
        if not exp:
            warnings.append("point without EXPTIME")
            continue
        jd_start = (mjd - float(exp) / 2.0 / 86400.0) + variables.MJD0
        mag = p.get("mag")
        if mag is None or ref is None:
            rows.append((jd_start, None, None))
            continue
        flux = 10.0 ** (-0.4 * (mag - ref))
        rows.append((jd_start, flux, _flux_err(flux, p.get("err"))))
    return rows, warnings


def format_data(rows):
    # @args: rows - build_data output
    # @return: the three-column text (JD, flux, error), dot decimals
    lines = []
    for jd, flux, err in rows:
        f = "" if flux is None else f"{flux:.6f}"
        e = "" if err is None else f"{err:.6f}"
        lines.append(f"{jd:.6f} {f} {e}")
    return "\n".join(lines) + "\n"


def build_info(planet, filter_name, exptime_s, comments, extra=None):
    # ExoClock_info.txt: the header ExoClock reads next to the data file
    # (the field names are its own; the values are plain text).
    # @args: planet - target name, filter_name - band, exptime_s - the
    #        exposure (s), comments - the honest self-assessment (non-empty)
    # @return: the info file text
    lines = [
        f"Planet: {planet or ''}",
        f"Time format: {TIME_FORMAT}",
        f"Time stamp: {TIME_STAMP}",
        f"Flux format: {FLUX_FORMAT}",
        f"Filter: {filter_name or ''}",
        f"Exposure time: {'' if exptime_s is None else exptime_s}",
        f"Comments: {comments or ''}",
    ]
    if extra:
        for key, value in extra.items():
            lines.append(f"{key}: {value}")
    return "\n".join(lines) + "\n"


def checklist(points, duration_h=None, baseline_h=1.0):
    # D41: a non-blocking pre-flight check in plain language. Never blocks
    # the export; it warns what would make the submission weak.
    # @args: points - series point dicts (with mag and flags),
    #        duration_h - transit duration (for the ingress density)
    # @return: {"level": ok|warn|red, "messages": [{es, en}]}
    msgs, level = [], "ok"
    good = [p for p in points if p.get("mag") is not None]
    if not good:
        return {"level": "red",
                "messages": [{"es": "no hay puntos con magnitud",
                              "en": "no points with a magnitude"}]}
    mjds = [p["mjd"] for p in good if p.get("mjd") is not None]
    if mjds and duration_h:
        span = max(mjds) - min(mjds)
        transit = float(duration_h) / 24.0
        baseline = (span - transit) / 2.0
        if baseline < baseline_h / 24.0:
            level = "warn"
            msgs.append({
                "es": f"solo {baseline * 24:.1f} h de línea base a cada "
                      "lado (se recomienda ≥ 1 h)",
                "en": f"only {baseline * 24:.1f} h of baseline on each "
                      "side (>= 1 h recommended)"})
    red = sum(1 for p in good if p.get("flags"))
    if red:
        level = "warn"
        msgs.append({
            "es": f"{red} punto(s) con marcas de calidad",
            "en": f"{red} point(s) with quality flags"})
    if duration_h:
        ingress_s = 0.15 * float(duration_h) * 3600.0
        mids = sorted(mjds)
        cad = None
        if len(mids) >= 2:
            gaps = [(mids[i + 1] - mids[i]) * 86400.0
                    for i in range(len(mids) - 1)]
            gaps = [g for g in gaps if g > 0]
            if gaps:
                cad = sorted(gaps)[len(gaps) // 2]
        if cad and ingress_s / cad < 3:
            level = "red"
            msgs.append({
                "es": f"la cadencia deja {ingress_s / cad:.1f} puntos por "
                      "ingress",
                "en": f"the cadence leaves {ingress_s / cad:.1f} points "
                      "per ingress"})
    return {"level": level, "messages": msgs}


def write_submission(points, base_path, planet, filter_name, exptime_s,
                     comments, extra=None):
    # Writes <base>.txt (data) and <base>_info.txt (metadata).
    # @args: base_path - the data file path; its stem names the info file
    # @return: (data_path, info_path)
    rows, warnings = build_data(points)
    data_path = Path(base_path)
    data_path.write_text(format_data(rows), encoding="utf-8")
    info_path = data_path.with_name(data_path.stem + "_info.txt")
    info_path.write_text(build_info(planet, filter_name, exptime_s,
                                    comments, extra=extra),
                         encoding="utf-8")
    logger.info("ExoClock submission written: %s + %s",
                data_path, info_path)
    return data_path, info_path
