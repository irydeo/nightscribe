############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - EXOTIC result import (orchestration phase D)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Read EXOTIC's outputs back into the project (plan phase D).

EXOTIC writes, next to the plots, a final light curve and a parameters
JSON (see the orchestration plan, phase 0). This module parses them into
the project's own shapes:

  - the curve becomes photometry points (mjd, mag, err) with
    source="exotic", so the light-curve widget and the payload builder
    show them like any other series;
  - the fitted parameters (T_mid, Rp/Rs, depth, inclination, duration)
    become a plain dict carried in the series run and the report.

The parser is tolerant: a missing file or a foreign format yields empty
results and a warning, never an exception.
"""

import csv
import json
import logging
import math
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# BJD_TDB -> MJD (the project stores MJD)
MJD0 = 2400000.5


def _pair(text):
    # @args: text - an EXOTIC parameter string like
    #        "2458107.71358 +/- 0.00094 BJD_TDB"
    # @return: (value, uncertainty) as floats, or (None, None)
    if not text:
        return None, None
    m = re.match(r"\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)"
                 r"(?:\s*\+/-\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?))?", str(text))
    if not m:
        return None, None
    val = float(m.group(1))
    unc = float(m.group(2)) if m.group(2) is not None else None
    return val, unc


def _find(folder, pattern):
    # @return: the first matching path as a string, or None
    if not folder.is_dir():
        return None
    hits = sorted(folder.glob(pattern))
    return str(hits[0]) if hits else None


def load_curve(path):
    # @args: path - EXOTIC's FinalLightCurve CSV (BJD_TDB, Phase, Flux,
    #        Uncertainty, Model, Airmass)
    # @return: list of {"mjd", "mag", "err", "flux", "airmass"}
    points = []
    if not path:
        return points
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for row in csv.reader(fh):
                if not row or row[0].lstrip().startswith("#"):
                    continue
                try:
                    bjd = float(row[0])
                    flux = float(row[2])
                    err = float(row[3]) if len(row) > 3 else None
                    air = float(row[5]) if len(row) > 5 else None
                except (ValueError, IndexError):
                    continue
                if flux <= 0:
                    continue
                mag = -2.5 * math.log10(flux)
                mag_err = (1.0857 * err / flux) if err else None
                points.append({"mjd": bjd - MJD0, "mag": mag,
                               "err": mag_err, "flux": flux,
                               "airmass": air, "source": "exotic"})
    except OSError as err:
        logger.warning("EXOTIC curve unreadable: %s", err)
    return points


def load_params(path):
    # @args: path - EXOTIC's FinalParams JSON (values are strings)
    # @return: dict with tmid/tmid_err/rprs/rprs_err/depth/... or {}
    if not path:
        return {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        logger.warning("EXOTIC params unreadable: %s", err)
        return {}
    final = data.get("FINAL PLANETARY PARAMETERS") or data
    tmid, tmid_err = _pair(final.get("Mid-Transit Time (Tmid)"))
    rprs, rprs_err = _pair(final.get("Ratio of Planet to Stellar Radius (Rp/R*)"))
    depth_pct, depth_err_pct = _pair(final.get("Transit depth (Rp/Rs)^2"))
    inc, inc_err = _pair(final.get("Orbital Inclination (inc)"))
    dur, dur_err = _pair(final.get("Transit Duration (day)"))
    out = {"tmid": tmid, "tmid_err": tmid_err, "rprs": rprs,
           "rprs_err": rprs_err,
           "depth": (depth_pct / 100.0) if depth_pct is not None else None,
           "depth_err": (depth_err_pct / 100.0)
           if depth_err_pct is not None else None,
           "inc": inc, "inc_err": inc_err, "duration_d": dur,
           "duration_err": dur_err}
    return out


def load_result(out_dir):
    # @args: out_dir - EXOTIC's "Directory to Save Plots"
    # @return: {"points", "params", "curve_csv", "params_json",
    #          "figure_png", "aavso_txt"}
    folder = Path(out_dir)
    temp = folder / "temp"
    curve_csv = _find(temp, "FinalLightCurve_*.csv")
    params_json = _find(temp, "FinalParams_*.json")
    return {
        "points": load_curve(curve_csv),
        "params": load_params(params_json),
        "curve_csv": curve_csv,
        "params_json": params_json,
        "figure_png": _find(folder, "FinalLightCurve_*.png"),
        "aavso_txt": _find(folder, "AAVSO_*.txt"),
    }


def persist(db, project_id, session_id, result, filter_name=None):
    # Writes EXOTIC's curve into the project as one run (source="exotic")
    # and returns the run id.
    # @args: db - Database, project_id/session_id - the project and visit,
    #        result - load_result output, filter_name - the band or None
    # @return: (run_id, n_points)
    from . import followup as fu
    run_id = fu.create_run(db, session_id=session_id,
                           cfg={"source": "exotic",
                                "curve_csv": result.get("curve_csv"),
                                "params": result.get("params")},
                           status="complete")
    rows = []
    for p in result.get("points", []):
        rows.append({"project_id": project_id, "session_id": session_id,
                     "mjd": p["mjd"], "filter": filter_name,
                     "mag": p["mag"], "err": p.get("err"),
                     "source": "exotic", "mag_raw": p.get("flux"),
                     "flags": [], "run_id": run_id})
    if rows:
        fu.add_points(db, rows)
    return run_id, len(rows)
