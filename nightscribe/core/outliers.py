############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Outliers on a light curve (quality plan, phase A/B)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Which points of a light curve do not belong to it.

A photometric series carries two very different kinds of "bad point":
the one the ENGINE already knows about (a saturated core, a cosmic ray,
a defocused frame: those come with a flag from the measurement) and the
one only the CURVE knows about, because it is where the eye says "that
one is off". This module finds the second kind.

The rule is deliberately local. A variable star's own shape, its trend
through the night, even a deep eclipse, are part of the curve: a global
median would call all of them outliers, or none. So each point is
compared with the median of its NEIGHBOURS IN TIME (a window of a few
points), and what is measured is the residual against that local level:

    residual[i] = y[i] - median(y of the neighbours of i)

Those residuals are noise around zero, whatever shape the curve has,
which is exactly what a robust scatter needs. The scale is their MAD, and
a point is marked when it leaves it by `sigma` robust sigmas.

Two honest details, both learned from the Photometricica tool of our
group:

  * a point with a large FORMAL error is allowed to sit further from its
    neighbours (the scale becomes max(scatter, its own error)), because a
    faint point measured badly is not the same as a good point that
    jumped;
  * the detector MARKS: excluding a point is a separate, explicit act of
    the observer, and the engine never deletes a measurement.

This is the tool for the daily work, before any period is known. Once a
period is known, `core/periodogram.reject_folded` does the same job on
the folded curve, which is stricter and more informative.
"""

import logging
import math

import numpy as np

logger = logging.getLogger(__name__)

# Neighbours compared with each point. Odd, so the window is symmetric,
# and SMALL on purpose: seven points stay inside a night (a window that
# spans the daily gap would compare a point with the next night's level
# and call the diurnal step an outlier).
WINDOW = 7
# The threshold in robust sigmas. 4.5 marks the wild ones without
# touching a noisy but honest curve; 3.0 also catches the suspicious.
SIGMA = 4.5
# Below this many points the local median means nothing: nothing is
# marked rather than something invented.
_MIN_POINTS = 7


# The MAD of gaussian noise is 0.6745 sigma (0.6745 is the 75th percentile
# of the normal: the deviation below which three quarters of the noise
# falls), so 1 / 0.6745 turns a MAD into a sigma equivalent. It is a
# property of the normal distribution, NOT a tunable, so it is written
# ONCE, here, with its origin, and read from here everywhere else: the
# arithmetic of "how far is far" lives in one readable place.
MAD_TO_SIGMA = 1.4826


def scaled_mad(values, axis=None, centre=None):
    # Median absolute deviation, scaled to be comparable with a standard
    # deviation for gaussian noise. NaN-aware on purpose: a masked pixel
    # (or a frame left out) must not poison the scale of the real ones.
    # @args: values - the sample, any shape, axis - the axis to reduce
    #        (None: the whole array), centre - the level the deviations
    #        are measured from (None: the sample's own median, the usual
    #        case; an iterative clip passes its running level instead)
    # @return: MAD_TO_SIGMA * median(|values - centre|), as a float when
    #          axis is None; 0.0 for an empty or all-NaN sample
    if values is None:
        return 0.0
    arr = np.asarray(values, dtype=np.float64)
    if arr.size == 0:
        return 0.0
    ref = np.nanmedian(arr, axis=axis) if centre is None else centre
    if axis is None and not np.isfinite(ref):
        return 0.0
    return MAD_TO_SIGMA * np.nanmedian(np.abs(arr - ref), axis=axis)


def median_error(values):
    # The standard error of the MEDIAN of a sample: its robust scatter
    # divided by the square root of the count. This is the honest error
    # where the mean cannot be trusted, and a faint object's curve is
    # exactly that case: it carries bright outliers and the mean is
    # dragged by them while the median is not.
    # @args: values - a 1-D sample
    # @return: the standard error (0.0 when it cannot be computed)
    arr = np.asarray(values, dtype=np.float64).ravel()
    arr = arr[np.isfinite(arr)]
    if arr.size < 2:
        return 0.0
    return float(scaled_mad(arr)) / math.sqrt(arr.size)


def local_outliers(t, y, err=None, sigma=SIGMA, window=WINDOW):
    # The points that separate from their neighbours in time.
    #
    # @args: t - times (any unit, only the ORDER matters), y - the values
    #        (magnitudes or anything else), err - their formal errors or
    #        None, sigma - the threshold in robust sigmas, window - how
    #        many neighbours each point is compared with
    # @return: {"flags": boolean array (True = does not belong),
    #          "residuals": array (NaN where it cannot be measured),
    #          "center": float, "scale": float, "n": int, "window": int}
    ta = np.asarray(t, dtype=np.float64)
    ya = np.asarray(y, dtype=np.float64)
    good = np.isfinite(ta) & np.isfinite(ya)
    n_good = int(good.sum())
    out = {"flags": np.zeros(ya.shape, dtype=bool),
           "residuals": np.full(ya.shape, np.nan),
           "center": 0.0, "scale": 0.0, "n": n_good,
           "window": int(max(3, window | 1))}
    if n_good < _MIN_POINTS:
        return out
    # work in time order: "the neighbours" means the closest points in
    # time, not the closest rows of the table
    order = np.argsort(ta[good])
    ids = np.flatnonzero(good)[order]
    values = ya[ids]
    half = max(2, out["window"] // 2)
    residuals = np.full(ids.size, np.nan)
    for k in range(ids.size):
        # A SYMMETRIC window: the same number of neighbours on each side.
        # With fewer points on one side (the ends of the series) the local
        # median leans towards the side that has more, and on a curved
        # night that bias alone looks like an outlier. The ends cannot be
        # judged locally, so the detector does not judge them: the
        # measurement's own gates still can.
        if k < half or k + half >= ids.size:
            continue
        neighbours = np.concatenate([values[k - half:k], values[k + 1:k + 1 + half]])
        # the local level: what the curve was doing right here, without
        # this point in the pot (a wild point must not drag its own
        # reference towards itself)
        residuals[k] = values[k] - float(np.median(neighbours))
    # the scale of the residuals, plus a fallback to the formal errors
    # when the residuals are degenerate (a perfectly smooth curve)
    finite = residuals[np.isfinite(residuals)]
    scale = float(scaled_mad(finite))
    if (not math.isfinite(scale) or scale <= 0.0) and err is not None:
        errors = np.asarray(err, dtype=np.float64)[ids]
        errors = errors[np.isfinite(errors) & (errors > 0)]
        if errors.size:
            scale = float(np.median(errors))
    if not math.isfinite(scale) or scale <= 0.0:
        return out
    center = float(np.median(finite)) if finite.size else 0.0
    errors = None if err is None else np.asarray(err, dtype=np.float64)
    flags = np.zeros(ya.shape, dtype=bool)
    for k in range(ids.size):
        r = residuals[k]
        if not math.isfinite(r):
            continue
        # a point is allowed to be as far from the curve as its own
        # formal error says it may: the bigger of the two scales wins
        point_scale = scale
        if errors is not None:
            e = errors[ids[k]]
            if math.isfinite(e) and e > 0.0:
                point_scale = max(point_scale, float(e))
        if abs(r - center) > sigma * point_scale:
            flags[ids[k]] = True
    out["flags"] = flags
    out["residuals"][ids] = residuals
    out["center"] = center
    out["scale"] = float(scale)
    return out


def outliers_in_points(points, sigma=SIGMA, window=WINDOW):
    # The same detector over the SeriesPoints or point dicts the rest of
    # the application already passes around. It reads whichever keys are
    # there, so the series engine, the chart and the period dialog can all
    # ask the same question of the same data.
    # @args: points - objects (or dicts) with mjd/mag/err, sigma/window
    # @return: {"flags": [bool], "residuals": [float or None],
    #          "scale": float, "n": int}
    def _get(p, key):
        if isinstance(p, dict):
            return p.get(key)
        return getattr(p, key, None)

    t = [p.get("mjd") if isinstance(p, dict) else getattr(p, "mjd", None)
         for p in points]
    y = [p.get("mag") if isinstance(p, dict) else getattr(p, "mag", None)
         for p in points]
    err = []
    for p in points:
        e = _get(p, "err_internal") or _get(p, "err")
        err.append(e)
    res = local_outliers(t, y, err=err, sigma=sigma, window=window)
    return {"flags": [bool(f) for f in res["flags"]],
            "residuals": [None if not math.isfinite(r) else float(r)
                          for r in res["residuals"]],
            "scale": res["scale"], "n": res["n"]}
