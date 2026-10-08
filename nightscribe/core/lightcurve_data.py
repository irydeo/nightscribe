############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Light-curve payload assembly
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Assemble the follow-up light-curve payload in one place.

Before this module the fold/schematic/amp logic was duplicated in
gui/overview.py and core/post.py and could drift silently (post.py did
not even honour the project's own sn_type). `build_payload` returns a
dict that maps 1-to-1 onto the keyword arguments of
`viz.lightcurve_view.draw_lightcurve` and of
`gui.widgets.lightcurve_widget.LightCurveChart.set_data`.
"""

import numpy as np

from . import outliers

# The magnitude window's own constants (quality plan, phase A): the scale
# is set by the CORE of the data (median +/- K robust sigmas), never by
# min/max, so one anomalous frame or one badly calibrated night cannot
# flatten the curve into a line.
ROBUST_K = 6.0
MIN_WINDOW = 0.05           # mag: never a degenerate window
WINDOW_PAD = 0.10           # 10 % of the window as air


def mag_window(mags, y_range=None, robust=True, k=ROBUST_K,
               min_window=MIN_WINDOW, pad=WINDOW_PAD):
    # The magnitude window of a light curve (quality plan, A1). It lives
    # HERE, not in the chart widget, because the project list's thumbnail
    # has to show the same scale the chart does: with min/max it stretched a
    # 0.17 mag core to fill the box (measured on a real project: the curve
    # spans 11.074 to 13.224 mag, one anomalous frame, while the chart's
    # window is 11.074 to 11.241), so the thumbnail and the chart did not
    # look like the same curve.
    #
    # Three things can decide it, in this order:
    #   1. the observer, when the manual range is on (their eye knows what
    #      they are looking for);
    #   2. the robust core (median +/- K robust sigmas), which keeps one
    #      anomalous frame from flattening the whole curve;
    #   3. the plain min/max, when robust mode is off or the scatter is
    #      degenerate.
    # @args: mags - the finite magnitudes to frame, y_range - a fixed
    #        (lo, hi) that wins over everything (the observer's), robust -
    #        use the robust core, k/min_window/pad - the tuning above
    # @return: (lo, hi) of the window, padded, or None when there is no data
    vals = np.asarray([m for m in mags if m is not None], dtype=float)
    if vals.size == 0:
        return None
    if y_range is not None:
        return float(y_range[0]), float(y_range[1])
    if not robust:
        lo, hi = float(vals.min()), float(vals.max())
    else:
        med = float(np.median(vals))
        mad = float(outliers.scaled_mad(vals, centre=med))
        if mad > 0.0:
            lo, hi = med - k * mad, med + k * mad
            # the core is intersected with the data: a robust window cannot
            # be WIDER than the curve itself
            lo = max(lo, float(vals.min()))
            hi = min(hi, float(vals.max()))
        else:
            lo, hi = float(vals.min()), float(vals.max())
    if hi - lo < min_window:
        centre = 0.5 * (lo + hi)
        lo, hi = centre - min_window / 2.0, centre + min_window / 2.0
    air = (hi - lo) * pad
    return lo - air, hi + air


def build_payload(fu, sn_type_fallback=None, hads=None, variable=None):
    # Builds the light-curve drawing payload (points, template, peak
    # alignment, fold + schematic) in the single place it can live.
    # @args: fu - the follow-up dict ({"points": [...], "sn_type": ?,
    #        "peak_mjd": ?, "peak_mag": ?}; any key may be missing),
    #        sn_type_fallback - the caller's best SN type (project context
    #           or Simbad otype), only used when fu has none of its own,
    #        hads - HADS catalog entry (period_h/amp/max/min) or None,
    #        variable - VSX variable entry (period_d/epoch_mjd/amp/max/min)
    #           or None
    # @return: dict with "points", "sn_type", "peak_mjd", "peak_mag" and,
    #          when folded, "fold_period_d", "epoch_mjd", "schematic"
    fu = fu or {}
    # Drop points without a usable (mjd, mag): they would crash the maps
    pts = [p for p in (fu.get("points") or [])
           if p.get("mjd") is not None and p.get("mag") is not None]
    out = {
        "points": pts,
        "sn_type": fu.get("sn_type") or sn_type_fallback,
        "peak_mjd": fu.get("peak_mjd"),
        "peak_mag": fu.get("peak_mag"),
    }

    def _amp(entry):
        # @return: the peak-to-peak amplitude: the stored one, else the
        #          min - max span. Kept signed on purpose: the magnitude
        #          axis is inverted, so a negative value is exactly what
        #          sawtooth_template needs to mirror the shape
        a = entry.get("amp")
        if a is None and entry.get("max") is not None \
                and entry.get("min") is not None:
            a = entry["min"] - entry["max"]
        return a

    def _schematic(entry, period_d):
        # @args: entry - the catalog dict, period_d - fold period in days
        # @return: the sawtooth reference shape [(phase, mag)], or None
        amp = _amp(entry)
        if not amp or entry.get("max") is None or entry.get("min") is None:
            return None
        from . import hads as hads_mod
        med = (entry["max"] + entry["min"]) / 2.0
        return hads_mod.sawtooth_template(period_d * 24.0, amp, med)

    # ADR-034 (D.4): a HADS star folds by its catalog period
    h = hads or {}
    if h.get("period_h"):
        out["fold_period_d"] = h["period_h"] / 24.0
        sc = _schematic(h, h["period_h"] / 24.0)
        if sc:
            out["schematic"] = sc
    # ADR-035: a long-period variable folds by its VSX period, with the
    # real epoch, reusing the same schematic shape
    v = variable or {}
    if "fold_period_d" not in out and v.get("period_d"):
        out["fold_period_d"] = v["period_d"]
        if v.get("epoch_mjd") is not None:
            out["epoch_mjd"] = v["epoch_mjd"]
        sc = _schematic(v, v["period_d"])
        if sc:
            out["schematic"] = sc
    return out
