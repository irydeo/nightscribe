############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Stretch engine: histogram, limits, gamma, invert (ADR-044)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The single stretch engine for every FITS-ish display in NightScribe
(ADR-044, phase B): percentiles to black/white points, linear stretch with
a gamma curve, gain matching, uint8 conversion, inversion, histograms and
the 2x2 display downscale. Pure numpy, no Qt, no network; the GUI (UFE)
and the legacy dialogs (via viz/blink_view's compatibility re-exports)
share exactly this code, so a fix here reaches everyone at once.
"""

import numpy as np

DISPLAY_CAP = 4096   # max display side in px; bigger plates get 2x2 steps


def auto_limits(data, lo=1.0, hi=99.5):
    # Robust black/white points from percentiles, NaN-safe.
    # @args: data - 2D array, lo, hi - percentiles
    # @return: (black, white) with white > black guaranteed
    flat = data[np.isfinite(data)]
    if flat.size == 0:
        return 0.0, 1.0
    black, white = np.percentile(flat, [lo, hi])
    if white <= black:
        white = black + 1.0
    return float(black), float(white)


def apply_stretch(data, black, white, gamma=1.0):
    # Linear stretch between black/white points with a gamma curve.
    # @args: data - 2D array, black, white - limits, gamma - <1 brightens
    # @return: float array 0..1
    gamma = max(gamma, 1e-3)
    span = max(white - black, 1e-12)
    out = np.clip((data - black) / span, 0.0, 1.0)
    return np.power(out, gamma)


def auto_gain(ref_f, obs_f):
    # Gain that equalizes the sky background level of the stretched pair
    # (median-matched), so blinking does not pump brightness.
    # @args: ref_f, obs_f - stretched float arrays 0..1
    # @return: gain to multiply the survey by, clamped to [0.25, 4]
    med_r = float(np.nanmedian(ref_f))
    med_o = float(np.nanmedian(obs_f))
    if med_r < 1e-6:
        return 1.0
    return float(np.clip(med_o / med_r, 0.25, 4.0))


def apply_gain(img_f, gain):
    # @args: img_f - stretched float array, gain - multiplicative factor
    # @return: float array 0..1
    return np.clip(img_f * gain, 0.0, 1.0)


def to_uint8(img):
    # @args: img - float array 0..1
    # @return: uint8 array 0..255
    return (np.nan_to_num(img) * 255.0 + 0.5).astype(np.uint8)


def invert(img):
    # Black-for-white swap: faint things pop against the sky background.
    # @args: img - float array 0..1 (post-stretch, post-gamma)
    # @return: float array 0..1
    return 1.0 - img


def histogram(data, nbins=256, bounds=None):
    # Histogram of the finite pixels, NaN-safe.
    # @args: data - 2D array, nbins - bin count,
    #        bounds - (lo, hi) in DN or None for the data range
    # @return: (edges, counts); edges has nbins+1 entries
    flat = data[np.isfinite(data)]
    if flat.size == 0:
        return np.linspace(0.0, 1.0, nbins + 1), np.zeros(nbins, int)
    lo, hi = bounds if bounds is not None else (flat.min(), flat.max())
    lo, hi = float(lo), float(hi)
    if hi <= lo:
        hi = lo + 1.0
    counts, edges = np.histogram(flat, bins=nbins, range=(lo, hi))
    return edges, counts


def display_downscale(data, cap=DISPLAY_CAP):
    # 2x2 block-averaging steps until the frame fits the display cap (odd
    # edges are cropped before each reshape). No new dependencies.
    # @args: data - 2D array, cap - max side in px
    # @return: 2D float32 array (the input itself when it already fits)
    out = data
    while max(out.shape) > cap and min(out.shape) >= 2:
        out = downscale2x2(out)
    return out


def downscale2x2(arr):
    # One 2x2 averaging step; odd rows/cols are cropped before the reshape.
    # @args: arr - 2D array
    # @return: 2D float32 array with half the size on each axis
    h, w = arr.shape
    arr = arr[:h // 2 * 2, :w // 2 * 2]
    return arr.reshape(h // 2 * 2 // 2, 2, w // 2 * 2 // 2,
                       2).mean(axis=(1, 3), dtype=np.float32)
