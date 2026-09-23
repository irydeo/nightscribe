############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Calibrated single-plate photometry module (UFE phase G)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Calibrated photometry for one plate (UFE Measure tab, phase G).

Sits one level above core/series.py and never re-invents the aperture
math: the primitives (centroid, radii, saturation margin) are reused from
series, and this module adds the saturation plateau check, the honest
guards, and the calibration layer: pure numpy, nothing else:

  1. measure_point():          click -> centroid -> net flux, sky, peak,
                               honest guards (bilingual reasons, no raise);
  2. ccd_flux_error():         the CCD equation (source + sky + RON)
                               anchored in the gain, or None without it;
  3. calibrate_zero_point():   ZP = median(cat - inst) over the comps,
                               with residuals and the stars used;
  4. calibrated_mag():         the target in catalog magnitudes with a
                               combined error.

No Qt, no network. Every degraded case becomes a plain-language reason
pair {"es", "en"} (same shape as compstars._why); the panel picks the
language and says it the way the app already says things.
"""

import logging
import math

import numpy as np

from . import series

logger = logging.getLogger(__name__)

# Apertures: one truth, re-exported from series so the quick-look and the
# Measure tab can never silently drift apart.
R_AP = series.R_AP
R_ANN_IN = series.R_ANN_IN
R_ANN_OUT = series.R_ANN_OUT

# Sky sigma-clip (decision D3): 2.5 sigma, two rounds, on by default.
# The median alone already shrugs at a few outliers; the clip is extra
# skin for crowded cores and satellite trails.
SIG_LEVEL = 2.5
SIG_ITERS = 2
_SIG_MIN_KEEP = 5   # never clip an annulus down to fewer than this

# Saturation (from series, adapted): a clipped star leaves a plateau of
# pixels stuck at the detector ceiling, not just a high peak (the
# brightest star in frame is a target, not a proof of clipping).
# 25 pixels at the exact frame maximum is a clipped core, not a gaussian.
_CLIP_MIN_PIXELS = 25
SAT_FRAC = series._SAT_FRAC     # margin below an explicit ceiling (ADU)

# One comparison star tells us nothing about the scatter; the quoted
# uncertainty floors at a generous constant instead of pretending to be zero.
SINGLE_COMP_ZP_ERR = 0.2   # mag


def _fail(reason_es, reason_en):
    # @args: reason_es, reason_en - plain-language pair for the panel
    # @return: the standard "not ok" dict; callers fill any part that
    #          was already measured before the guard tripped
    return {"x": None, "y": None, "flux": None, "sky_pp": None,
            "peak": None, "n_pix": 0, "saturated": False,
            "ok": False, "reason": {"es": reason_es, "en": reason_en}}


def _sigma_clipped_median(values, level=SIG_LEVEL, iters=SIG_ITERS):
    # Robust median: `iters` rounds of |v - median| <= level * sigma.
    # @args: values - 1D array of sky samples, level/iters - clip params
    # @return: (median, n_kept), or (None, 0) when there is nothing to
    #          measure; iters=0 means a plain median over every sample
    arr = np.asarray(values, dtype=np.float64)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return None, 0
    for _ in range(max(0, int(iters))):
        if arr.size <= _SIG_MIN_KEEP:
            break
        med = float(np.median(arr))
        sd = float(np.std(arr))
        if sd <= 0.0:
            break
        kept = arr[np.abs(arr - med) <= level * sd]
        if kept.size <= _SIG_MIN_KEEP or kept.size == arr.size:
            break
        arr = kept
    return float(np.median(arr)), int(arr.size)


def measure_point(data, x, y, r_ap=R_AP, r_ann_in=R_ANN_IN,
                  r_ann_out=R_ANN_OUT, sigma_clip=True, sat_adu=None):
    # One click on one plate (decision D4): sub-pixel centroid, aperture
    # net flux, sky per pixel, peak, and honest guards. Never raises for
    # a bad star: the reason is the bilingual pair, the panel decides.
    # @args: data - 2D array (DN, or ADU if the plate is already linear),
    #        x, y - click position in plate pixels,
    #        r_ap, r_ann_in, r_ann_out - apertures (defaults = series),
    #        sigma_clip - robust sky median (D3, on by default),
    #        sat_adu - the detector ceiling in ADU, when known (settings
    #        or header); the plateau check always runs on top of it
    # @return: {"x", "y" (centroided where possible), "flux", "sky_pp",
    #          "peak", "n_pix", "saturated", "ok", "reason"}
    if data is None or data.size == 0:
        return _fail("no hay imagen cargada", "no image loaded")
    h, w = data.shape
    if not (0 <= x < w and 0 <= y < h):
        return _fail("el clic cae fuera del marco", "the click is out of frame")
    # the whole sky annulus must fit inside the frame (same rule as the
    # quick-look candidate culling)
    if min(x, y, w - x, h - y) < r_ann_out:
        return _fail("demasiado cerca del borde", "too close to the edge")
    cx, cy = series._centroid(data, x, y)
    yy, xx = np.ogrid[:h, :w]
    r2 = (xx - cx) ** 2 + (yy - cy) ** 2
    ap_pixels = data[r2 <= r_ap ** 2]
    if ap_pixels.size == 0:
        out = _fail("sin píxeles de apertura", "no aperture pixels")
        out.update(x=cx, y=cy)
        return out
    n_pix = int(ap_pixels.size)
    total = float(np.nansum(ap_pixels))
    peak = float(np.nanmax(ap_pixels))
    ann_pixels = data[(r2 >= r_ann_in ** 2) & (r2 <= r_ann_out ** 2)]
    if ann_pixels.size:
        iters = SIG_ITERS if sigma_clip else 0
        sky_pp, _kept = _sigma_clipped_median(ann_pixels, iters=iters)
        if sky_pp is None:
            sky_pp = 0.0
    else:
        sky_pp = 0.0
    flux = total - sky_pp * n_pix
    frame_max = float(np.nanmax(data))
    # A star that clipped the detector leaves a plateau: many pixels
    # stuck at exactly the frame maximum (a gaussian core has one
    # unique max pixel). A flat plate is a background level, not a star,
    # and an explicit ceiling (sat_adu, e.g. the full well) makes the
    # check direct: peak within SAT_FRAC of the ceiling.
    saturated = sat_adu is not None and frame_max > 0.0 \
        and peak >= SAT_FRAC * float(sat_adu)
    if not saturated and frame_max > sky_pp:
        eps = 1e-6 * max(1.0, frame_max)
        plateau = int(np.count_nonzero(
            (r2 <= r_ann_in ** 2) & (data > frame_max - eps)))
        saturated = plateau >= _CLIP_MIN_PIXELS
    if saturated:
        return _fail("saturada", "saturated") | {
            "x": cx, "y": cy, "sky_pp": sky_pp, "peak": peak,
            "n_pix": n_pix, "saturated": True}
    if flux is None or not math.isfinite(flux) or flux <= 0.0:
        return _fail("sin señal medible", "no measurable signal") | {
            "x": cx, "y": cy, "sky_pp": sky_pp, "peak": peak,
            "n_pix": n_pix}
    return {"x": cx, "y": cy, "flux": flux, "sky_pp": sky_pp,
            "peak": peak, "n_pix": n_pix, "saturated": False,
            "ok": True, "reason": None}


def ccd_flux_error(flux, sky_pp, n_pix, gain=None, ron=None, exptime=None):
    # Honest CCD equation for the net flux, everything anchored in gain:
    #   sigma^2 (ADU^2) = flux/g + n*sky/g + n*ron^2/g^2
    # (source and sky shot noise counted in electrons, RON per pixel;
    # exptime stays for the dark current, not modelled yet).
    # @args: flux - net flux in ADU, sky_pp - sky in ADU per pixel,
    #        n_pix - aperture pixels, gain - e-/ADU, ron - read noise in e-,
    #        exptime - reserved for the dark (unused for now)
    # @return: sigma of the flux in ADU, or None when there is no usable
    #          gain: the caller then falls back to the comps' scatter
    if gain is None or gain <= 0.0 or flux is None or flux < 0.0:
        return None
    var = flux / gain
    n = int(n_pix or 0)
    if sky_pp is not None and sky_pp >= 0.0:
        var += n * sky_pp / gain
    if ron is not None and ron >= 0.0 and n > 0:
        var += n * (ron ** 2) / (gain ** 2)
    return math.sqrt(var)


def mag_error(flux, flux_err):
    # Magnitude error: dm = 1.086 * dF / F (1.086 = 2.5/ln 10).
    # @args: flux - net flux (> 0), flux_err - its sigma in the same units
    # @return: the magnitude error, or None when it cannot be computed
    if flux is None or flux <= 0.0 or flux_err is None:
        return None
    return 1.086 * flux_err / flux


def calibrate_zero_point(inst_mags, cat_mags):
    # Zero-point from the comparison stars, one truth per star:
    #   ZP = median(cat - inst), so the target calibrates as inst + ZP.
    # The error comes from the median absolute deviation of the residuals,
    # which is what the panel should quote (honest, per this plate).
    # @args: inst_mags - instrumental magnitudes of the comps,
    #        cat_mags - their catalog magnitudes in the same order
    #        (None entries or non-finite pairs are skipped)
    # @return: {"zp", "zp_err", "n", "residuals" (cat - inst - zp per
    #          comp used, in the given order), "used" (indexes kept)}
    pairs, used = [], []
    for i, (im, cm) in enumerate(zip(inst_mags, cat_mags)):
        if im is None or cm is None:
            continue
        if not (math.isfinite(im) and math.isfinite(cm)):
            continue
        pairs.append(cm - im)
        used.append(i)
    n = len(pairs)
    if n == 0:
        logger.warning("zero-point: no usable comparison star")
        return {"zp": None, "zp_err": None, "n": 0,
                "residuals": [], "used": []}
    values = np.asarray(pairs, dtype=np.float64)
    zp = float(np.median(values))
    if n == 1:
        zp_err = SINGLE_COMP_ZP_ERR
    else:
        mad = float(np.median(np.abs(values - zp)))
        zp_err = 1.4826 * mad / math.sqrt(n)
    if n < 3:
        logger.warning("only %d comparison star(s) on this plate; the "
                       "quoted uncertainty is floor-bounded", n)
    return {"zp": zp, "zp_err": zp_err, "n": n,
            "residuals": [p - zp for p in pairs], "used": used}


def calibrated_mag(inst_target, zp, zp_err=None, target_err=None):
    # The target in catalog magnitudes.
    # @args: inst_target - its instrumental magnitude,
    #        zp - the zero-point (from calibrate_zero_point),
    #        zp_err, target_err - their errors in mag, either or both
    #        may be None (treated as "no contribution")
    # @return: (mag, err) with err the quadrature sum of the two;
    #          (None, None) when there is no zero-point to apply
    if inst_target is None or zp is None:
        return None, None
    err = math.hypot(target_err or 0.0, zp_err or 0.0)
    return inst_target + zp, err


def header_instrument(header):
    # Instrument parameters straight out of the FITS header, numbers only
    # (decision D2): a card written as a string with units degrades to
    # None instead of guessing. Keywords are matched case-insensitively.
    # @args: header - the header dict from core/fits_io (or None)
    # @return: {"gain", "ron", "exptime"} with None for every absent or
    #          non-numeric key
    out = {"gain": None, "ron": None, "exptime": None}
    if not header:
        return out
    by_key = {str(k).upper(): v for k, v in header.items()}

    def _num(key):
        # @return: the value as float, or None (including non-numeric and
        #          boolean cards, which are not instrument numbers)
        v = by_key.get(key)
        if v is None or isinstance(v, bool):
            return None
        if isinstance(v, (int, float)):
            return float(v)
        try:
            return float(str(v).strip())
        except ValueError:
            return None

    out["gain"] = _num("GAIN")
    out["ron"] = _num("RDNOISE")
    out["exptime"] = _num("EXPTIME")
    return out
