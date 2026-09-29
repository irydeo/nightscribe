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
from dataclasses import dataclass, field

import numpy as np

from . import coords, fits_meta, series

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
_FRAME_CLIP_MIN = 25        # px pinned at the frame maximum across the
                            # plate: the signature of a clipping level
_INFERRED_CEILING_FRAC = 0.94   # flag peaks this close to an INFERRED
                                # ceiling: the CMOS roll-off compresses
                                # cores before they sit exactly on it
_PLATEAU_MAX_FWHM = 4.0     # the 99 %-plateau rule in suggest_apertures
                            # is only believed within this many FWHM

# One comparison star tells us nothing about the scatter; the quoted
# uncertainty floors at a generous constant instead of pretending to be zero.
SINGLE_COMP_ZP_ERR = 0.2   # mag

# Phase H (PRECISION.es appendix): quality knobs for the single plate.
# Colour-term fit needs this much B-V spread among the comps, else a
# slope would be a fantasy and we fall back to the plain zero-point.
_COLOR_MIN_SPREAD = 0.2    # mag of B-V between the reddest and bluest
_COLOR_MIN_STARS = 6       # weighted 2-parameter fit floor
# Residual outlier rejection in the calibration (H7): residuals beyond
# this many robust sigmas are dropped, at most twice.
_CLIP_SIGMA = 3.0
_CLIP_ROUNDS = 2
# Aperture from the seeing (H3): r_ap = k x FWHM, annulus in proportion
_APER_K_DEFAULT = 1.35
# Scintillation (H5), Young (1967): the fractional intensity fluctuation
# 0.064 * D^(-2/3) * X^1.75 * (2t)^(-1/2) * exp(-h/8000), D in metres,
# t in seconds, h in metres above sea level.
_SCINT_K = 0.064


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


def pixel_coverage(shape, cx, cy, r, subsample=8):
    # How much of each pixel lies inside the aperture circle.
    #
    # A star is a continuous thing and a sensor is a grid, so the honest
    # question is not "is this pixel's CENTRE inside the circle?" but "how
    # much of this pixel is?". Counting whole pixels is the staircase
    # approximation: fine for a large aperture (the missing and the extra
    # bits cancel along the circle), plainly wrong for a small one, where
    # the boundary is a sizeable fraction of the area (r = 2 px: 13
    # pixels counted against 12.57 of true area, a 3 % flux error that
    # lands straight in the magnitude).
    #
    # Strategy: a pixel well inside is fully covered, a pixel well outside
    # is not covered at all, and only the BOUNDARY pixels (about 2·pi·r of
    # them) are measured by subsampling a grid inside the pixel. A few
    # dozen small computations per star, not one per plate pixel.
    #
    # @args: shape - (h, w) of the plate, cx/cy - the star's centre (in
    #        float pixels), r - the aperture radius, subsample - the grid
    #        per axis used on the boundary pixels
    # @return: a (h, w) float array of coverages in 0..1
    h, w = shape
    yy, xx = np.ogrid[:h, :w]
    dist = np.hypot(xx - cx, yy - cy)
    cover = np.zeros((h, w), dtype=np.float64)
    cover[dist <= r - 0.8] = 1.0
    maybe = (dist > r - 0.8) & (dist < r + 0.8)
    if not np.any(maybe):
        return cover
    n = max(2, int(subsample))
    offsets = (np.arange(n) + 0.5) / n - 0.5      # sub-pixel centres
    rows, cols = np.nonzero(maybe)
    for py, px in zip(rows, cols):
        # the fraction of THIS pixel inside the circle: how many of the
        # sub-samples fall within the radius
        sx = px + offsets[:, None]
        sy = py + offsets[None, :]
        inside = ((sx - cx) ** 2 + (sy - cy) ** 2) <= r * r
        cover[py, px] = float(inside.sum()) / float(n * n)
    return cover


def measure_point(data, x, y, r_ap=R_AP, r_ann_in=R_ANN_IN,
                  r_ann_out=R_ANN_OUT, sigma_clip=True, sat_adu=None,
                  linear_adu=None, sky_mode="median",
                  centroid_mode="gaussian", fwhm=None):
    # One click on one plate (decision D4): sub-pixel centroid, aperture
    # net flux, sky per pixel, peak, and honest guards. Never raises for
    # a bad star: the reason is the bilingual pair, the panel decides.
    # @args: data - 2D array (DN, or ADU if the plate is already linear),
    #        x, y - click position in plate pixels,
    #        r_ap, r_ann_in, r_ann_out - apertures (defaults = series),
    #        sigma_clip - robust sky median (D3, on by default),
    #        sat_adu - the detector ceiling in ADU, when known (settings
    #        or header); the plateau check always runs on top of it,
    #        sky_mode - "median" (flat sky) or "plane" (H2: a tilted sky
    #        plane fitted to the annulus, for galactic cores),
    #        centroid_mode - "gaussian" (matched-filter, parabola-fined;
    #        the default), "refined" (sky-subtracted moment, two passes)
    #        or "raw" (the legacy one-pass moment),
    #        fwhm - the plate's seeing in px when the caller knows it
    #        (the Measure tab's comps-based estimate): the centroid
    #        template then matches the stars instead of trusting a local
    #        guess, which a galaxy glow inflates
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
    cen_ok = None                     # the raw mode carries no verdict
    if centroid_mode == "raw":
        cx, cy = series._centroid(data, x, y)      # the legacy one-pass
    elif centroid_mode == "refined":
        cen = refined_centroid(data, x, y)
        cx, cy = cen["x"], cen["y"]              # ok=False keeps the click
        cen_ok = cen["ok"]
    else:
        cen = gaussian_centroid(data, x, y, fwhm=fwhm)
        cx, cy = cen["x"], cen["y"]              # ok=False keeps the click
        cen_ok = cen["ok"]
    yy, xx = np.ogrid[:h, :w]
    r2 = (xx - cx) ** 2 + (yy - cy) ** 2
    # the aperture, pixel by pixel: each pixel weighs the fraction of its
    # area that falls inside the circle (see pixel_coverage). The effective
    # AREA is the sum of those weights, and it is what the sky is scaled
    # by: using the pixel COUNT here would subtract too much sky from a
    # small aperture and too little from a big one.
    weights = pixel_coverage((h, w), cx, cy, r_ap)
    usable = weights > 0.0
    if not np.any(usable):
        out = _fail("sin píxeles de apertura", "no aperture pixels")
        out.update(x=cx, y=cy)
        return out
    finite = np.isfinite(data[usable])
    w_eff = np.where(finite, weights[usable], 0.0)
    values = np.where(finite, data[usable], 0.0)
    area = float(w_eff.sum())
    if area <= 0.0:
        out = _fail("sin píxeles finitos en la apertura",
                    "no finite pixel in the aperture")
        out.update(x=cx, y=cy)
        return out
    n_pix = area
    total = float((values * w_eff).sum())
    peak = float(np.nanmax(data[usable]))
    ann_mask = (r2 >= r_ann_in ** 2) & (r2 <= r_ann_out ** 2)
    ann_pixels = data[ann_mask]
    if ann_pixels.size:
        iters = SIG_ITERS if sigma_clip else 0
        if sky_mode == "plane":
            ann_x = np.broadcast_to(xx, data.shape)[ann_mask]
            ann_y = np.broadcast_to(yy, data.shape)[ann_mask]
            sky_pp = _sky_plane_at(ann_x, ann_y,
                                   ann_pixels, cx, cy, iters=iters)
        else:
            sky_pp, _kept = _sigma_clipped_median(ann_pixels, iters=iters)
        if sky_pp is None:
            sky_pp = 0.0
    else:
        sky_pp = 0.0
    flux = total - sky_pp * n_pix
    n_sky = int(ann_pixels.size)
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
    if not saturated and sat_adu is None and linear_adu is None:
        # No ceiling anywhere (no SATURATE card, no setting, no camera
        # profile): infer it from the plate itself. A soft CMOS roll-off
        # compresses cores that never form a 25-px plateau, and those
        # "almost saturated" stars poison a zero point just the same (the
        # plateau test above stays blind to them).
        ceiling = frame_ceiling(data, frame_max)
        if ceiling is not None and peak >= _INFERRED_CEILING_FRAC * ceiling:
            return _fail(f"comprimida: el pico llega al recorte de la "
                         f"placa (~{ceiling:.0f} ADU)",
                         f"clipped: the peak reaches the plate ceiling "
                         f"(~{ceiling:.0f} ADU)") | {
                "x": cx, "y": cy, "sky_pp": sky_pp, "peak": peak,
                "n_pix": n_pix, "n_sky": n_sky, "saturated": True}
    if saturated:
        return _fail("saturada", "saturated") | {
            "x": cx, "y": cy, "sky_pp": sky_pp, "peak": peak,
            "n_pix": n_pix, "n_sky": n_sky, "saturated": True}
    if linear_adu is not None and frame_max > 0.0 \
            and peak >= SAT_FRAC * float(linear_adu):
        # over the camera's linearity limit: the flux is no longer
        # proportional (the star calibrates nothing), named distinctly from
        # a hard saturation so the panel can say which limit was hit
        return _fail("no lineal: el pico supera el límite de linealidad "
                     "de tu cámara",
                     "nonlinear: the peak is above your camera's linearity "
                     "limit") | {
            "x": cx, "y": cy, "sky_pp": sky_pp, "peak": peak,
            "n_pix": n_pix, "n_sky": n_sky, "saturated": False, "nonlinear": True}
    if flux is None or not math.isfinite(flux) or flux <= 0.0:
        return _fail("sin señal medible", "no measurable signal") | {
            "x": cx, "y": cy, "sky_pp": sky_pp, "peak": peak,
            "n_pix": n_pix, "n_sky": n_sky}
    return {"x": cx, "y": cy, "flux": flux, "sky_pp": sky_pp,
            "peak": peak, "n_pix": n_pix, "n_sky": n_sky, "saturated": False,
            "ok": True, "reason": None, "cen_ok": cen_ok}


def ccd_flux_error(flux, sky_pp, n_pix, gain=None, ron=None, exptime=None,
                   dark_e_s=None, n_sky=None):
    # Honest CCD equation for the net flux (Merline & Howell, Handbook of
    # CCD Astronomy), everything anchored in gain:
    #   sigma^2 (ADU^2) = flux/g + n*(1 + n/n_sky)*(sky/g + ron^2/g^2
    #                     + dark*t/g^2)
    # The (1 + n/n_sky) factor prices the noise of the sky annulus
    # itself: with a small annulus the sky estimate is noisy and the
    # subtraction adds variance. Without n_sky the factor degrades to 1
    # (the annulus is assumed infinitely fine), never below the truth.
    # @args: flux - net flux in ADU, sky_pp - sky in ADU per pixel,
    #        n_pix - aperture pixels, gain - e-/ADU, ron - read noise in
    #        e-, exptime - exposure in s (for the dark), dark_e_s - dark
    #        current in e-/pixel/s (camera profile), n_sky - annulus
    #        pixels (all optional but the first three)
    # @return: sigma of the flux in ADU, or None when there is no usable
    #          gain: the caller then falls back to the comps' scatter
    if gain is None or gain <= 0.0 or flux is None or flux < 0.0:
        return None
    var = flux / gain
    # n_pix is the EFFECTIVE aperture area (a float when the aperture used
    # fractional pixel coverage), so it stays a float here: rounding it
    # would quietly change the noise of a small aperture.
    n = float(n_pix or 0.0)
    sky_factor = 1.0
    if n_sky is not None and n_sky > 0 and n > 0:
        sky_factor = 1.0 + n / float(n_sky)
    if sky_pp is not None and sky_pp >= 0.0:
        var += sky_factor * n * sky_pp / gain
    if ron is not None and ron >= 0.0 and n > 0:
        var += sky_factor * n * (ron ** 2) / (gain ** 2)
    if dark_e_s is not None and dark_e_s >= 0.0 and exptime and n > 0:
        var += sky_factor * n * float(dark_e_s) * float(exptime) \
            / (gain ** 2)
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
    # None instead of guessing. Keywords are matched case-insensitively,
    # and the gain/read noise accept the names real cameras write (GAIN,
    # EGAIN, CCDGAIN, GAIN1; RDNOISE, READNOIS, RON, ENF? no).
    # @args: header - the header dict from core/fits_io (or None)
    # @return: {"gain", "ron", "exptime"} with None for every absent or
    #          non-numeric key
    out = {"gain": None, "ron": None, "exptime": None}
    if not header:
        return out
    by_key = {str(k).upper(): v for k, v in header.items()}

    def _num(*keys):
        # @args: keys - the card names to try, in order
        # @return: the first present value as float, or None (including
        #          non-numeric and boolean cards, which are not numbers)
        for key in keys:
            v = by_key.get(key)
            if v is None or isinstance(v, bool):
                continue
            if isinstance(v, (int, float)):
                return float(v)
            try:
                return float(str(v).strip())
            except ValueError:
                continue
        return None

    out["gain"] = _num("GAIN", "EGAIN", "CCDGAIN", "GAIN1", "GAINX")
    out["ron"] = _num("RDNOISE", "READNOIS", "RON", "READNOISE")
    out["exptime"] = _num("EXPTIME", "EXP0TIME")
    return out


# ---------------- phase H: quality on a single plate (PRECISION.es) ----

def _sky_plane_fit(ann_x, ann_y, ann_v, x0, y0, iters=SIG_ITERS):
    # A tilted sky plane fitted to the annulus, with sigma-clip first (a
    # hot pixel or a neighbour must not tilt the plane).
    # @args: ann_x, ann_y, ann_v - annulus pixel coordinates and values,
    #        x0, y0 - the reference point, iters - clip rounds
    # @return: (level at (x0, y0), slope_x, slope_y), or None
    v = np.asarray(ann_v, dtype=np.float64)
    xs = np.asarray(ann_x, dtype=np.float64) - x0
    ys = np.asarray(ann_y, dtype=np.float64) - y0
    keep = np.isfinite(v)
    v, xs, ys = v[keep], xs[keep], ys[keep]
    if v.size < 6:
        return None
    for _ in range(max(0, int(iters))):
        med = float(np.median(v))
        sd = float(np.std(v))
        if sd <= 0.0:
            break
        m = np.abs(v - med) <= SIG_LEVEL * sd
        if m.sum() == v.size or m.sum() < 6:
            break
        v, xs, ys = v[m], xs[m], ys[m]
    a = np.column_stack([np.ones(v.size), xs, ys])
    try:
        coef, *_ = np.linalg.lstsq(a, v, rcond=None)
    except np.linalg.LinAlgError:
        return None
    return float(coef[0]), float(coef[1]), float(coef[2])


def _sky_plane_at(ann_x, ann_y, ann_v, x0, y0, iters=SIG_ITERS):
    # A tilted sky plane fitted to the annulus and evaluated at the star:
    # near a galactic core the background is a ramp, and the flat median
    # of the ring is biased by it (H2a).
    # @args: ann_x, ann_y, ann_v - annulus pixel coordinates and values,
    #        x0, y0 - where to evaluate (the centroid), iters - clip rounds
    # @return: the sky level at (x0, y0), or None when unsolvable
    fit = _sky_plane_fit(ann_x, ann_y, ann_v, x0, y0, iters=iters)
    return fit[0] if fit is not None else None


def estimate_fwhm(data, positions, sat_adu=None):
    # Median seeing FWHM from bright, unsaturated stars, by second
    # moments on the sky-subtracted cutout (H3).
    # @args: data - 2D array, positions - [(x, y)] star pixels,
    #        sat_adu - ceiling in ADU, stars near it are skipped
    # @return: the median FWHM in px, or None when nothing is usable
    if data is None:
        return None
    fwhms = []
    for x, y in positions:
        half = 9   # a 19x19 cutout: enough for any sane seeing disc
        y0, y1 = max(0, int(y) - half), min(data.shape[0], int(y) + half + 1)
        x0, x1 = max(0, int(x) - half), min(data.shape[1], int(x) + half + 1)
        sub = data[y0:y1, x0:x1]
        if sub.size == 0:
            continue
        peak = float(np.nanmax(sub))
        if sat_adu is not None and peak >= SAT_FRAC * float(sat_adu):
            continue
        sky = float(np.nanmedian(sub))
        bright = sub - sky
        bright[bright < 0] = 0.0
        total = float(bright.sum())
        if total <= 0.0:
            continue
        ys, xs = np.mgrid[y0:y1, x0:x1]
        mx = float((xs * bright).sum() / total)
        my = float((ys * bright).sum() / total)
        var = float((((xs - mx) ** 2 + (ys - my) ** 2) * bright).sum()
                    / total)
        sigma = math.sqrt(var / 2.0)     # the 2-D gaussian's per-axis sigma
        if 0.3 < sigma < 20.0:
            fwhms.append(2.3548 * sigma)
    if not fwhms:
        return None
    return float(np.median(fwhms))


def aperture_for_fwhm(fwhm, k=_APER_K_DEFAULT):
    # Aperture radii that follow the seeing (H3): r_ap = k x FWHM, the
    # annulus in the same proportion as the series defaults.
    # @args: fwhm - measured seeing in px, k - the multiplier
    # @return: (r_ap, r_ann_in, r_ann_out) in px, or the defaults when the
    #          FWHM is missing or absurd
    if fwhm is None or not (0.5 <= fwhm <= 50.0):
        return R_AP, R_ANN_IN, R_ANN_OUT
    r_ap = k * fwhm
    ratio_in = R_ANN_IN / R_AP
    ratio_out = R_ANN_OUT / R_AP
    return (float(min(max(r_ap, 2.0), 20.0)),
            float(max(r_ap * ratio_in, r_ap + 3.0)),
            float(max(r_ap * ratio_out, r_ap + 6.0)))


def frame_ceiling(data, frame_max=None):
    # The plate's clipping level in ADU, inferred from the data alone when
    # no SATURATE card and no setting exist: dozens of pixels pinned at
    # the very frame maximum are a clipping level, not one star's apex
    # (an honest core owns one or two pixels up there).
    # @args: data - 2D array, frame_max - precomputed maximum (optional)
    # @return: the ceiling in ADU, or None when nothing can be said
    if data is None or data.size == 0:
        return None
    if frame_max is None:
        frame_max = float(np.nanmax(data))
    if not math.isfinite(frame_max) or frame_max <= 0.0:
        return None
    eps = 1e-6 * max(1.0, frame_max)
    if int(np.count_nonzero(data >= frame_max - eps)) >= _FRAME_CLIP_MIN:
        return frame_max
    return None


def saturation_ceiling(header, cfg=None):
    # The detector's saturation level in ADU (H4): the FITS cards first
    # (SATURATE, SATLEVEL), then the ccd_saturate settings key; None when
    # nobody knows (the plateau heuristic in measure_point still runs).
    # @args: header - the plate's header dict, cfg - a config-like object
    #         with .get (or None)
    # @return: the ceiling in ADU, or None
    if header:
        for key in ("SATURATE", "SATLEVEL"):
            try:
                v = header.get(key)
                if v is not None and not isinstance(v, bool):
                    return float(v)
            except (TypeError, ValueError):
                continue
    if cfg is not None:
        try:
            v = cfg.get("ccd_saturate")
            if v is not None and str(v).strip() != "":
                return float(v)
        except (TypeError, ValueError, AttributeError):
            pass
    return None


def linearity_ceiling(cfg):
    # The camera profile's linearity limit in ADU (per the working gain),
    # or None when the user has not set one.
    # @args: cfg - a config-like object with .get (or None)
    # @return: ADU (float) or None
    if cfg is None:
        return None
    try:
        v = cfg.get("cam_linearity_adu")
        if v is not None and str(v).strip() != "":
            return float(v)
    except (TypeError, ValueError, AttributeError):
        pass
    return None


def effective_ceiling(header, cfg=None, linear_adu=None):
    # The single, honest ceiling the photometry obeys: the MINIMUM of the
    # known limits. The camera profile's linearity is usually the strictest
    # (a star above it calibrates nothing even if it is not clipped yet),
    # then the detector saturation (SATURATE card / ccd_saturate); None
    # when nobody knows (measure_point then infers it from the plate).
    # @args: header - the plate's header, cfg - config-like or None,
    #        linear_adu - an explicit linearity limit (overrides cfg)
    # @return: the effective ceiling in ADU, or None
    limits = []
    lin = linear_adu
    if lin is None:
        lin = linearity_ceiling(cfg)
    if lin is not None:
        limits.append(float(lin))
    sat = saturation_ceiling(header, cfg)
    if sat is not None:
        limits.append(float(sat))
    return min(limits) if limits else None


def calibrate_with_color(inst_mags, cat_mags, bvs, target_bv=None):
    # Calibration with a colour term (H1+H7): fit
    #   (cat - inst) = ZP + k * (B-V)
    # by weighted least squares over the comps, with two rounds of
    # robust-sigma residual clipping. When the comps carry too little
    # colour spread (or too few survive), the honest answer is the plain
    # median zero-point with color_used=False.
    # @args: inst_mags, cat_mags, bvs - per-comp instrumental mag,
    #        catalog mag and B-V (None entries skipped),
    #        target_bv - the target's B-V when known (None allowed)
    # @return: {"zp", "k", "zp_err", "k_err", "n", "residuals", "used",
    #          "color_used", "target_color_err"} - k/k_err None on fallback
    triples = []
    for i, (im, cm, bv) in enumerate(zip(inst_mags, cat_mags, bvs)):
        if im is None or cm is None:
            continue
        if not (math.isfinite(im) and math.isfinite(cm)):
            continue
        ok_bv = bv is not None and math.isfinite(bv)
        triples.append((i, float(im), float(cm),
                        float(bv) if ok_bv else None))
    n_with_colour = sum(1 for t in triples if t[3] is not None)
    spread = 0.0
    if n_with_colour >= _COLOR_MIN_STARS:
        vals = [t[3] for t in triples if t[3] is not None]
        spread = max(vals) - min(vals)
    if n_with_colour < _COLOR_MIN_STARS or spread < _COLOR_MIN_SPREAD:
        out = calibrate_zero_point([t[1] for t in triples],
                                   [t[2] for t in triples])
        # the fallback's "used" indexes point into the filtered list;
        # map them back to the caller's order
        out["used"] = [triples[j][0] for j in out["used"]]
        out.update({"k": None, "k_err": None, "color_used": False,
                    "target_color_err": None})
        return out
    # initial fit, then clip the worst residuals and refit (H7). The
    # clip threshold has a 0.06 mag floor: the MAD collapses to ~0 when
    # the majority fits exactly (and a real outlier then clips
    # EVERYTHING); below the catalog's own noise there is nothing to
    # reject anyway. And never clip below 4 survivors: a ZP on 3 points
    # is fragile but a ZP on 0 is fiction.
    idx = [t[0] for t in triples if t[3] is not None]
    inst = np.asarray([t[1] for t in triples if t[3] is not None])
    cat = np.asarray([t[2] for t in triples if t[3] is not None])
    bv = np.asarray([t[3] for t in triples if t[3] is not None])
    keep = np.ones(len(idx), dtype=bool)
    zp = k = None
    for _ in range(_CLIP_ROUNDS + 1):
        a = np.column_stack([np.ones(keep.sum()), bv[keep]])
        coef, *_ = np.linalg.lstsq(a, (cat - inst)[keep], rcond=None)
        zp, k = float(coef[0]), float(coef[1])
        resid = (cat - inst)[keep] - (zp + k * bv[keep])
        if len(resid) < 4:
            break
        sig = 1.4826 * float(np.median(np.abs(resid - np.median(resid))))
        sig = max(sig, 0.02)          # the catalog noise floor (mag)
        # deviations are measured from the residuals' own median: a fit
        # pulled by an outlier must not condemn the honest majority
        worst = np.abs(resid - np.median(resid)) > _CLIP_SIGMA * sig
        if not worst.any() or int(keep.sum() - worst.sum()) < 4:
            break
        keep[np.where(keep)[0][worst]] = False
    resid = (cat - inst)[keep] - (zp + k * bv[keep])
    n = int(keep.sum())
    sig = 1.4826 * float(np.median(np.abs(resid - np.median(resid)))) \
        if n > 1 else 0.0
    zp_err = sig / math.sqrt(n) if n > 1 else SINGLE_COMP_ZP_ERR
    bv_spread = float(np.std(bv[keep])) if n > 1 else 0.0
    k_err = (sig / (math.sqrt(n) * bv_spread)) if bv_spread > 0 else None
    color_err = None
    if target_bv is not None and k_err is not None:
        color_err = abs(k_err * (float(target_bv)
                                 - float(np.mean(bv[keep]))))
    used = [i for i, kf in zip(idx, keep) if kf]
    return {"zp": zp, "k": k, "zp_err": zp_err, "k_err": k_err,
            "n": n, "residuals": [float(r) for r in resid],
            "used": used, "color_used": True,
            "target_color_err": color_err}


def airmass_from_alt(alt_deg):
    # Plane-parallel airmass, clamped to the altitudes photometry lives at.
    # @args: alt_deg - object altitude in degrees
    # @return: X ~ 1/sin(alt), clamped to [1, 6]
    alt = math.radians(min(max(float(alt_deg), 9.6), 90.0))
    return 1.0 / math.sin(alt)


def scintillation_mag(alt_deg, exptime_s, aperture_m, height_m):
    # Scintillation noise in magnitudes, Young (1967): grows with the
    # airmass, shrinks with the telescope aperture and the square root of
    # the exposure, and with the site's height (H5).
    # @args: alt_deg - object altitude, exptime_s - exposure seconds,
    #        aperture_m - telescope aperture in metres, height_m - site
    #        height above sea level in metres
    # @return: sigma in mag, or None when the exposure is unknown
    if not exptime_s or exptime_s <= 0.0:
        return None
    x = airmass_from_alt(alt_deg)
    aperture_m = max(float(aperture_m or 0.0), 1e-3)
    height_m = max(float(height_m or 0.0), 0.0)
    sigma_i = _SCINT_K * aperture_m ** (-2.0 / 3.0) * x ** 1.75 \
        * (2.0 * exptime_s) ** (-0.5) * math.exp(-height_m / 8000.0)
    return 1.086 * sigma_i


def combine_errors(*terms):
    # Independent error terms in quadrature; None terms are skipped.
    # @return: the combined sigma, or None when every term is None
    vals = [float(t) for t in terms if t is not None]
    if not vals:
        return None
    return math.hypot(*vals)


# ---------------- precision centroid + suggested apertures (phase I) ---

def local_sources(data, k=4.0, min_sep=6, ring=4, max_sources=50):
    # Source finding for structured backgrounds (galaxy cores, nebulosity):
    # the noise is the MAD of pixel-to-pixel differences (a smooth gradient
    # barely moves it, where a global std explodes), and every candidate's
    # significance is measured against the median of a ring around it, not
    # the frame's sky. Built for cutouts (the snap's 48 px, the centroid's
    # seed box), in the same plain style as series.detect_sources, which
    # keeps serving the full-plate quick-look.
    # @args: data - 2D array, k - significance in local sigmas,
    #        min_sep - minimum separation between sources (px),
    #        ring - radius of the local-sky ring (px), max_sources - cap
    # @return: list of (x, y, peak) sorted by significance (descending)
    if data is None or data.size == 0:
        return []
    clean = np.nan_to_num(np.asarray(data, dtype=np.float64), nan=0.0)
    h, w = clean.shape
    if h < 2 * ring + 3 or w < 2 * ring + 3:
        return []
    diffs = np.concatenate([np.diff(clean, axis=1).ravel(),
                            np.diff(clean, axis=0).ravel()])
    noise = 1.4826 * float(np.median(np.abs(diffs - np.median(diffs)))) \
        / math.sqrt(2.0)
    if noise <= 0:
        # a noiseless plate (synthetic fixtures are flat to the last bit):
        # fall back to the classic global estimator
        noise = float(np.nanstd(clean))
    if noise <= 0:
        return []
    out = []
    for y in range(ring, h - ring):
        for x in range(ring, w - ring):
            v = clean[y, x]
            if v < clean[y - 1:y + 2, x - 1:x + 2].max():
                continue
            if v == clean[y, x - 1] or v == clean[y - 1, x]:
                continue        # plateau tie: the upper-left px speaks
            loc = np.concatenate([clean[y - ring, x - ring:x + ring + 1],
                                  clean[y + ring, x - ring:x + ring + 1],
                                  clean[y - ring + 1:y + ring, x - ring],
                                  clean[y - ring + 1:y + ring, x + ring]])
            sig = (v - float(np.median(loc))) / noise
            if sig < k:
                continue
            if any((px - x) ** 2 + (py - y) ** 2 < min_sep ** 2
                   for px, py, _p, _s in out):
                continue
            out.append((float(x), float(y), float(v), float(sig)))
    out.sort(key=lambda s: s[3], reverse=True)
    return [(x, y, pk) for x, y, pk, _s in out[:max_sources]]


def lock_local_peak(data, x, y, max_dist=4.0, k=4.0):
    # The significant local peak nearest to the clicked pixel: the right
    # seed for the centroid. A moment estimator drags toward the brightest
    # wing inside its window (a neighbour star, a galaxy core); the matched
    # filter can only refine around its seed, so the seed must be the
    # source the observer MEANT, not the brightest thing nearby.
    # @args: data - 2D array, x, y - the clicked pixel,
    #        max_dist - how far a peak may be to count as "under the click"
    # @return: (px, py) of the nearest local source, or None
    if data is None or data.size == 0:
        return None
    h, w = data.shape
    half = int(max_dist) + 7
    y0, y1 = max(0, int(round(y)) - half), min(h, int(round(y)) + half + 1)
    x0, x1 = max(0, int(round(x)) - half), min(w, int(round(x)) + half + 1)
    best, best_d = None, max_dist ** 2
    for px, py, _pk in local_sources(data[y0:y1, x0:x1], k=k):
        d = (px + x0 - x) ** 2 + (py + y0 - y) ** 2
        if d < best_d:
            best, best_d = (px + x0, py + y0), d
    return best


def gaussian_centroid(data, x, y, fwhm=None, sky_pp=None):
    # The precision centroid: matched-filter correlation of the
    # sky-subtracted cutout with a gaussian template of the measured
    # seeing, on a 0.1 px grid, with parabolic refinement of the
    # correlation surface (~0.01 px). With a fixed sigma this is the
    # optimal estimator in white noise, and the one that does not wander
    # on faint sources. The observer's point is kept (with the bilingual
    # reason) when the fit is too weak to trust: below SNR ~4 there is
    # no centroid worth the name, and pretending otherwise is worse.
    # @args: data - 2D array, x, y - starting pixel, fwhm - seeing in px
    #        (estimated from the cutout when None), sky_pp - local sky
    #        (cutout edge median when None)
    # @return: {"x", "y", "ok", "moved", "reason", "snr"} - ok=False
    #          keeps the start position
    if data is None or data.size == 0:
        return {"x": float(x), "y": float(y), "ok": False,
                "moved": False, "snr": None,
                "reason": {"es": "no hay imagen cargada",
                           "en": "no image loaded"}}
    h, w = data.shape
    if not (0 <= x < w and 0 <= y < h):
        return {"x": float(x), "y": float(y), "ok": False,
                "moved": False, "snr": None,
                "reason": {"es": "el punto cae fuera del marco",
                           "en": "the point is out of frame"}}
    if fwhm is None:
        fwhm = estimate_fwhm(data, [(x, y)]) or 4.0
    sigma_psf = max(fwhm / 2.3548, 0.7)
    half = max(5, int(round(2.0 * sigma_psf)) + 1)
    # the seed is the significant peak nearest the click (lock_local_peak):
    # a moment centroid drags toward the brightest wing in its window and
    # the lattice below can only refine around the seed, so seeding from
    # the moment could land the whole fit on a bright neighbour (the
    # 2026-09 AT2026acka case). No peak nearby: seed at the click itself
    # and let the SNR gate below judge whatever is there.
    seed = lock_local_peak(data, x, y)
    sx, sy = seed if seed is not None else (float(x), float(y))
    y0 = max(0, int(round(sy)) - half)
    y1 = min(h, int(round(sy)) + half + 1)
    x0 = max(0, int(round(sx)) - half)
    x1 = min(w, int(round(sx)) + half + 1)
    sub = np.asarray(data[y0:y1, x0:x1], dtype=np.float64)
    if sub.size == 0 or not np.any(np.isfinite(sub)):
        return {"x": float(x), "y": float(y), "ok": False,
                "moved": False, "snr": None,
                "reason": {"es": "sin píxeles utilizables",
                           "en": "no usable pixels"}}
    if sky_pp is None:
        ring = np.concatenate([sub[0, :], sub[-1, :], sub[:, 0],
                               sub[:, -1]])
        ring = ring[np.isfinite(ring)]
        sky = float(np.median(ring)) if ring.size else 0.0
    else:
        sky = float(sky_pp)
    resid = np.nan_to_num(sub - sky)
    mad = float(np.median(np.abs(resid - np.median(resid))))
    noise = max(1.4826 * mad, 1e-9)
    ys, xs = np.mgrid[y0:y1, x0:x1]
    # matched-filter grid: correlate the residual with the seeing
    # gaussian on a 0.1 px lattice around the moment seed
    best = (None, -np.inf)
    for dy in np.arange(-1.0, 1.0001, 0.1):
        for dx in np.arange(-1.0, 1.0001, 0.1):
            g = np.exp(-(((xs - (sx + dx)) ** 2
                          + (ys - (sy + dy)) ** 2) / (2 * sigma_psf ** 2)))
            gg = float((g * g).sum())
            if gg <= 0.0:
                continue
            amp = float((resid * g).sum()) / gg
            snr = amp * math.sqrt(gg) / noise
            if snr > best[1]:
                best = ((sx + dx, sy + dy, amp, gg), snr)
    (bx, by, amp, gg), snr = best
    # parabolic refinement of the correlation peak (sub-lattice). The
    # vertex is never extrapolated past the lattice cell: on structured
    # backgrounds (a galaxy core, a bright neighbour's wing) the surface
    # can be near-flat or flipped, and a tiny denominator would otherwise
    # run the centroid several pixels away from the winning lattice point
    # (the 2026-09 AT2026acka case).
    def _peak(c0, c1, c2, base, step):
        denom = c0 - 2.0 * c1 + c2
        if abs(denom) < 1e-12:
            return base
        delta = 0.5 * step * (c0 - c2) / denom
        if abs(delta) > step:
            return base
        return base + delta

    def _corr(cx, cy):
        g = np.exp(-(((xs - cx) ** 2 + (ys - cy) ** 2)
                     / (2 * sigma_psf ** 2)))
        gg2 = float((g * g).sum())
        return float((resid * g).sum()) / max(gg2, 1e-12) \
            * math.sqrt(max(gg2, 1e-12))
    step = 0.1
    fx = _peak(_corr(bx - step, by), _corr(bx, by), _corr(bx + step, by),
               bx, step)
    fy = _peak(_corr(bx, by - step), _corr(bx, by), _corr(bx, by + step),
               by, step)
    if snr < 4.0:
        return {"x": float(x), "y": float(y), "ok": False,
                "moved": False, "snr": float(snr),
                "reason": {"es": "demasiado débil para centrarla "
                                "(medida donde pulsaste)",
                           "en": "too faint to centroid (measured where "
                                "you clicked)"}}
    if abs(fx - x) > half or abs(fy - y) > half:
        return {"x": float(x), "y": float(y), "ok": False,
                "moved": False, "snr": float(snr),
                "reason": {"es": "el centroide se escapó del píxel "
                                "clicado",
                           "en": "the centroid ran away from the "
                                "clicked pixel"}}
    return {"x": float(fx), "y": float(fy), "ok": True,
            "moved": math.hypot(fx - x, fy - y) > 0.01,
            "snr": float(snr), "reason": None}


def refined_centroid(data, x, y, sky_pp=None, fwhm=None):
    # The photometric centroid: local sky subtracted, only significant
    # pixels weighted, the box scaled to the seeing, two passes with
    # re-centring. The raw series._centroid (sky included, one fixed
    # pass) pulls faint sources toward the box centre; this one does not.
    # The legacy quick-look keeps using series._centroid unchanged.
    # @args: data - 2D array, x, y - starting pixel, sky_pp - local sky
    #        level or None (then the cutout's edge median), fwhm - seeing
    #        in px or None (box ~11 px)
    # @return: {"x", "y", "ok", "moved", "reason"} - ok=False keeps the
    #          start position (bilingual reason)
    if data is None or data.size == 0:
        return {"x": float(x), "y": float(y), "ok": False,
                "moved": False,
                "reason": {"es": "no hay imagen cargada",
                           "en": "no image loaded"}}
    h, w = data.shape
    if not (0 <= x < w and 0 <= y < h):
        return {"x": float(x), "y": float(y), "ok": False,
                "moved": False,
                "reason": {"es": "el punto cae fuera del marco",
                           "en": "the point is out of frame"}}
    half = max(5, int(round(1.5 * fwhm))) if fwhm else 5
    cx, cy = float(x), float(y)
    for _pass in range(2):
        y0 = max(0, int(round(cy)) - half)
        y1 = min(h, int(round(cy)) + half + 1)
        x0 = max(0, int(round(cx)) - half)
        x1 = min(w, int(round(cx)) + half + 1)
        sub = np.asarray(data[y0:y1, x0:x1], dtype=np.float64)
        if sub.size == 0 or not np.any(np.isfinite(sub)):
            break
        if sky_pp is None:
            # local sky from the cutout's outer ring (the star owns the
            # middle, not the border)
            ring = np.concatenate([sub[0, :], sub[-1, :], sub[:, 0],
                                   sub[:, -1]])
            ring = ring[np.isfinite(ring)]
            sky = float(np.median(ring)) if ring.size else 0.0
        else:
            sky = float(sky_pp)
        resid = sub - sky
        mad = float(np.median(np.abs(resid - np.median(resid))))
        sigma = 1.4826 * mad
        keep = resid > max(2.0 * sigma, 0.0)
        if int(keep.sum()) < 5:
            return {"x": float(x), "y": float(y), "ok": False,
                    "moved": False,
                    "reason": {"es": "señal demasiado débil para "
                                    "centrarla",
                               "en": "too faint to centroid"}}
        total = float(resid[keep].sum())
        if total <= 0.0:
            break
        ys, xs = np.mgrid[y0:y1, x0:x1]
        nx = float((xs[keep] * resid[keep]).sum() / total)
        ny = float((ys[keep] * resid[keep]).sum() / total)
        if abs(nx - cx) > half or abs(ny - cy) > half:
            return {"x": float(x), "y": float(y), "ok": False,
                    "moved": False,
                    "reason": {"es": "el centroide se escapó del píxel "
                                    "clicado",
                               "en": "the centroid ran away from the "
                                    "clicked pixel"}}
        if abs(nx - cx) < 0.01 and abs(ny - cy) < 0.01:
            cx, cy = nx, ny
            break
        cx, cy = nx, ny
    moved = math.hypot(cx - x, cy - y) > 0.01
    return {"x": cx, "y": cy, "ok": True, "moved": moved, "reason": None}


def _growth_curve(data, cx, cy, r_max, sky_pp):
    # Net flux inside growing radii, and the relative SNR per radius
    # (source + sky shot terms only; the shape is what matters).
    # @return: list of (r, net_flux, snr)
    h, w = data.shape
    yy, xx = np.ogrid[:h, :w]
    r2 = (xx - cx) ** 2 + (yy - cy) ** 2
    out = []
    for r in range(2, r_max + 1):
        px = data[r2 <= r * r]
        n = px.size
        net = float(np.nansum(px)) - sky_pp * n
        snr = net / math.sqrt(max(net, 1e-9) + n * max(sky_pp, 0.0))
        out.append((r, net, snr))
    return out


def suggest_apertures(data, x, y, fwhm=None, sky_pp=None):
    # Suggested aperture radii for this target in this environment, with
    # the plain-language reasons (the observer keeps the last word: the
    # suggestion is applied by a button, never silently).
    # @args: data - 2D array, x, y - target pixel, fwhm - seeing in px
    #        (measured when None), sky_pp - local sky (measured when None)
    # @return: {"r_ap", "r_ann_in", "r_ann_out", "reasons": [{"es","en"}],
    #          "diag": {...}}
    reasons = []
    # center on the peak the observer meant: gaussian_centroid seeds from
    # lock_local_peak, so a bright neighbour's wing cannot drag the whole
    # growth curve onto itself (ok=False keeps the clicked point)
    cen = gaussian_centroid(data, x, y, fwhm=fwhm)
    cx, cy = cen["x"], cen["y"]
    # seeing from the target itself when nobody measured one
    if fwhm is None:
        fwhm = estimate_fwhm(data, [(cx, cy)])
    if fwhm is None:
        fwhm = 4.0          # a sane default seeing disc (px)
    # sky and its noise from the default annulus
    h, w = data.shape
    yy, xx = np.ogrid[:h, :w]
    r2 = (xx - cx) ** 2 + (yy - cy) ** 2
    ann = data[(r2 >= R_ANN_IN ** 2) & (r2 <= R_ANN_OUT ** 2)]
    if sky_pp is None:
        sky_pp = float(np.nanmedian(ann)) if ann.size else 0.0
    sky_sig = float(np.nanstd(ann)) if ann.size else 0.0
    # the growth curve
    r_max = min(20, int(min(cx, cy, w - cx, h - cy)) - 1)
    curve = _growth_curve(data, cx, cy, max(r_max, 6), sky_pp)
    plateau = None
    total = curve[-1][1]
    for r, net, _snr in curve:
        if total > 0 and net >= 0.99 * total:
            plateau = float(r)
            break
    snr_peak = max(curve, key=lambda t: t[2])
    peak_snr = snr_peak[2]
    # environment: nearest detected neighbour around the target
    cut = max(32, int(4 * R_ANN_OUT))
    y0, y1 = max(0, int(cy) - cut), min(h, int(cy) + cut)
    x0, x1 = max(0, int(cx) - cut), min(w, int(cx) + cut)
    sub = np.ascontiguousarray(data[y0:y1, x0:x1])
    sources = series.detect_sources(sub, k=5.0) if sub.size else []
    nearest = None
    for sx, sy, _pk in sources:
        d = math.hypot(sx + x0 - cx, sy + y0 - cy)
        if d > 1.0 and (nearest is None or d < nearest):
            nearest = d
    # background gradient across the annulus (core detection)
    gradient = 0.0
    if ann.size:
        mask = (r2 >= R_ANN_IN ** 2) & (r2 <= R_ANN_OUT ** 2)
        ann_x = np.broadcast_to(xx, data.shape)[mask]
        ann_y = np.broadcast_to(yy, data.shape)[mask]
        fit = _sky_plane_fit(ann_x, ann_y, ann, cx, cy)
        if fit is not None:
            gradient = math.hypot(fit[1], fit[2])
    # ---------------- the rules (environment only, the signed choice)
    # The 99 % plateau is only trustworthy at a point-source radius: the
    # growth curve is cumulative, so a sky level off by a couple of ADU
    # (or a blend) keeps it "growing" forever and the rule would inflate
    # the aperture to the scan cap. Beyond _PLATEAU_MAX_FWHM x FWHM the
    # honest answer is the seeing aperture plus saying so.
    plateau_ok = plateau is not None and plateau <= _PLATEAU_MAX_FWHM * fwhm
    if peak_snr < 30.0:
        r_ap = snr_peak[0]
    elif plateau_ok:
        r_ap = plateau
    else:
        r_ap = max(1.35 * fwhm, snr_peak[0])
    r_in = r_ap * (R_ANN_IN / R_AP)
    r_out = r_ap * (R_ANN_OUT / R_AP)
    if peak_snr < 30.0:
        reasons.append({
            "es": "objetivo débil: la apertura maximiza la SNR "
                  f"(r = {r_ap:.1f} px)",
            "en": f"faint target: the aperture maximises the SNR "
                  f"(r = {r_ap:.1f} px)"})
    elif plateau_ok:
        reasons.append({
            "es": f"objetivo brillante: la apertura llega a la meseta "
                  f"del 99 % del flujo (r = {r_ap:.1f} px)",
            "en": f"bright target: the aperture reaches the 99 % flux "
                  f"plateau (r = {r_ap:.1f} px)"})
    else:
        reasons.append({
            "es": f"la curva de crecimiento no se aplana a "
                  f"{_PLATEAU_MAX_FWHM:.0f}×FWHM (¿mezcla o fondo mal "
                  f"restado?): propongo la apertura de seeing "
                  f"(r = {r_ap:.1f} px)",
            "en": f"the growth curve never flattens by "
                  f"{_PLATEAU_MAX_FWHM:.0f}×FWHM (a blend, or a "
                  f"mis-subtracted sky?): the seeing aperture is the "
                  f"honest choice (r = {r_ap:.1f} px)"})
    if nearest is not None and nearest < 2.0 * r_out:
        r_ap = max(2.0, min(r_ap, nearest / 2.5))
        r_in = max(r_ap + 2.0, min(r_in, nearest * 0.6))
        r_out = max(r_in + 3.0, min(r_out, nearest * 0.9))
        reasons.append({
            "es": f"vecino a {nearest:.0f} px: apertura y anillo se "
                  "acortan para no tocarlo",
            "en": f"neighbour at {nearest:.0f} px: aperture and annulus "
                  "pulled in so they never touch it"})
    # core mode: the ramp's swing across the annulus exceeds the noise
    swing = gradient * 2.0 * R_ANN_OUT
    if sky_sig > 0 and swing > sky_sig:
        reasons.append({
            "es": "fondo con gradiente (¿núcleo de galaxia?): apertura "
                  "corta y cielo por plano recomendado",
            "en": "the background has a gradient (a galactic core?): "
                  "short aperture, and the plane sky is recommended"})
    return {"r_ap": float(r_ap), "r_ann_in": float(r_in),
            "r_ann_out": float(r_out), "reasons": reasons,
            "diag": {"fwhm": fwhm, "plateau_r": plateau,
                     "snr_peak_r": snr_peak[0], "peak_snr": peak_snr,
                     "nearest": nearest, "gradient": gradient,
                     "sky_pp": sky_pp}}


# ---------------- single-plate recipe extraction (series plan, phase 1) -
#
# The whole single-plate recipe (H3..H7) as one pure function so the UFE
# Measure tab and the series engine can never drift apart: the GUI is a
# facade that reads its widgets into a PlateConfig and paints the result.

def band_of(star, band):
    # The star's value in one photometric band.
    # @args: star - a sequence star dict, band - a label like "V"
    # @return: (value, derived), or (None, False) when the star lacks it
    for item in star.get("bands", []):
        if item.get("label") == band and item.get("value") is not None:
            return item["value"], bool(item.get("derived"))
    return None, False


def available_bands(entries):
    # @args: entries - the comparison sequence
    # @return: the photometric bands present (colour indices like B-V are
    #          not bands), V first
    labels = []
    for e in entries:
        for item in e["star"].get("bands", []):
            lab = item.get("label") or ""
            if item.get("value") is None or "-" in lab:
                continue
            if lab not in labels:
                labels.append(lab)
    return sorted(labels, key=lambda l: (l != "V", l))


def pick_band(entries, preferred=None, fallback="V"):
    # The band this plate calibrates in: the observer's pick when the
    # sequence carries it, else the first available band, else the
    # fallback (a plate with no usable band still reports honestly).
    # @return: (band, available bands)
    bands = available_bands(entries)
    band = preferred or fallback
    if bands and band not in bands:
        band = bands[0]
    return band, bands


@dataclass
class PlateConfig:
    # Every knob of the single-plate recipe, resolved by the caller (the
    # GUI reads its widgets and Ajustes; the series engine its own cfg).
    target_xy: tuple = (0.0, 0.0)   # the click, in plate pixels
    entries: list = field(default_factory=list)
    header: dict = field(default_factory=dict)
    wcs: object = None
    band: str = None                # the observer's pick, or None
    fallback_band: str = "V"
    radii: tuple = None             # (rap, rin, rout) or None for defaults
    fwhm: float = None              # measured seeing (px), for the centroid
    sigmaclip: bool = True
    sky_mode: str = "median"
    color: bool = False
    target_bv: float = 0.0
    require_catalog: bool = True    # False = relative mode: comps count
                                    # even without a catalog value
    linear_adu: float = None        # the camera profile's linearity limit
                                    # (per gain), or None when unset
    # site (Ajustes, ADR-028): the same values the panel has always used
    site_gain: float = None
    site_ron: float = None
    site_flat: float = 0.007
    site_saturate: float = None
    site_lon: float = None
    site_lat: float = None
    site_aperture_m: float = 0.254
    site_height_m: float = 0.0
    site_dark: float = None         # dark current e-/pixel/s (profile)
    # host subtraction (H2b): the comps read on another frame, in the
    # plate orientation, at comp_scale plate px per comp-image px
    comp_image: object = None
    comp_scale: float = 1.0


@dataclass
class PlateResult:
    # The recipe's output: the target, its comps, the zero point, the
    # honest error budget and the check verdict. Never raises.
    ok: bool = False
    reason: dict = None
    target: dict = None
    col: float = None               # measured centroid, in plate pixels
    row: float = None
    fwhm: float = None
    radii: tuple = None
    band: str = None
    bands_avail: list = field(default_factory=list)
    used: list = field(default_factory=list)   # [(entry, result), ...]
    skipped: dict = field(default_factory=dict)
    derived: bool = False
    inst_t: float = None
    zp: dict = None
    mag: float = None
    err_total: float = None
    err_internal: float = None
    scint: float = None
    check: dict = None
    sky_mode: str = "median"
    sigma_clip: bool = True
    gain: float = None


def _check_verdict(entries, used_entries, band, zp, err_total):
    # H6: measure the check star on this same plate and compare with its
    # catalog value; beyond 2.5 sigma the night is not trusted.
    # @args: zp - the calibration dict (with the colour term, when fitted:
    #        the check's OWN B-V moves its zero point)
    # @return: None or {"delta", "ok", "name", "mag", "catalog"}
    check = next((e for e in entries if e["kind"] == "check"), None)
    if check is None or zp.get("zp") is None or err_total is None:
        return None
    used = next((r for e, r in used_entries
                 if e["star"] is check["star"]), None)
    if used is None:
        return None
    catalog, _d = band_of(check["star"], band)
    if catalog is None:
        return None
    zp_check = zp["zp"]
    if zp.get("color_used") and zp.get("k") is not None \
            and check["star"].get("bv") is not None:
        zp_check = zp["zp"] + zp["k"] * check["star"]["bv"]
    measured = -2.5 * math.log10(used["flux"]) + zp_check
    delta = measured - catalog
    return {"delta": delta, "ok": abs(delta) <= 2.5 * err_total,
            "name": check["name"], "mag": measured, "catalog": catalog}


def _plate_scintillation(cfg, col, row, exptime):
    # H5: Young's formula with the site from Ajustes and the target's
    # altitude from the plate's WCS + DATE-OBS. None when it cannot be
    # computed (the combiner skips it).
    meta = fits_meta.meta_from_header(cfg.header or {})
    if meta["mjd"] is None or cfg.wcs is None:
        return None
    try:
        ra, dec = cfg.wcs.pixel_to_sky(col, row)
        jd = meta["mjd"] + 2400000.5
        lst = coords.lst_degrees(jd, float(cfg.site_lon))
        alt, _az = coords.altaz(ra, dec, float(cfg.site_lat), lst)
        return scintillation_mag(alt, exptime, cfg.site_aperture_m,
                                 cfg.site_height_m)
    except Exception:
        return None


def measure_plate(image, cfg):
    # The single-plate recipe as one pure function: target, comps on the
    # same plate (or the paired work frame while subtracting the host),
    # zero point with the colour term, honest error budget, check
    # semaphore. No Qt, never raises: the guards become bilingual reasons.
    # @args: image - the work frame the target reads on (the plate, or
    #        the difference when cfg.comp_image is set), cfg - PlateConfig
    # @return: a PlateResult
    scale = float(cfg.comp_scale) if cfg.comp_image is not None else 1.0
    radii = tuple(cfg.radii) if cfg.radii else (R_AP, R_ANN_IN, R_ANN_OUT)
    fwhm = cfg.fwhm
    sat = saturation_ceiling(cfg.header,
                             {"ccd_saturate": cfg.site_saturate})
    # the camera profile's linearity limit is in plate ADU; it does not
    # apply to a resampled/downsampled work frame (host subtraction)
    lin = cfg.linear_adu if scale == 1.0 else None
    res = PlateResult(radii=radii, fwhm=fwhm, sky_mode=cfg.sky_mode,
                      sigma_clip=cfg.sigmaclip)
    tx, ty = cfg.target_xy
    if cfg.comp_image is not None:
        # H2b: the target on the difference, the comps on the work frame
        target = measure_point(
            image, tx / scale, ty / scale,
            r_ap=radii[0] / scale, r_ann_in=radii[1] / scale,
            r_ann_out=radii[2] / scale, sigma_clip=cfg.sigmaclip,
            sat_adu=None, sky_mode=cfg.sky_mode,
            fwhm=(fwhm / scale if fwhm else None))
    else:
        target = measure_point(
            image, tx, ty, r_ap=radii[0], r_ann_in=radii[1],
            r_ann_out=radii[2], sigma_clip=cfg.sigmaclip, sat_adu=sat,
            linear_adu=lin, sky_mode=cfg.sky_mode, fwhm=fwhm)
    res.target = target
    if not target["ok"]:
        res.reason = target.get("reason")
        return res
    mx, my = target["x"], target["y"]
    if cfg.comp_image is not None:
        mx, my = mx * scale, my * scale
    res.col, res.row = mx, my
    res.ok = True
    band, bands = pick_band(cfg.entries, cfg.band, cfg.fallback_band)
    res.band, res.bands_avail = band, bands
    inst_t = -2.5 * math.log10(target["flux"])
    res.inst_t = inst_t
    # the comps on the same plate (or the paired work frame); the ceiling
    # applies to them too: a clipped comp poisons the zero point
    inst, cat, bvs, used_entries = [], [], [], []
    skipped = {}
    for e in cfg.entries:
        star = e["star"]
        try:
            ccol, crow = cfg.wcs.sky_to_pixel(star["ra"], star["dec"])
        except Exception:
            skipped["off"] = skipped.get("off", 0) + 1
            continue
        if cfg.comp_image is not None:
            r = measure_point(
                cfg.comp_image, ccol / scale, crow / scale,
                r_ap=radii[0] / scale, r_ann_in=radii[1] / scale,
                r_ann_out=radii[2] / scale, sigma_clip=cfg.sigmaclip,
                sat_adu=None, sky_mode=cfg.sky_mode,
                fwhm=(fwhm / scale if fwhm else None))
        else:
            r = measure_point(image, ccol, crow, r_ap=radii[0],
                              r_ann_in=radii[1], r_ann_out=radii[2],
                              sigma_clip=cfg.sigmaclip, sat_adu=sat,
                              linear_adu=lin, sky_mode=cfg.sky_mode,
                              fwhm=fwhm)
        value, derived = band_of(star, band)
        if not r["ok"]:
            if r.get("saturated"):
                key = "sat"
            elif r.get("nonlinear"):
                key = "nonlinear"
            else:
                key = "other"
            skipped[key] = skipped.get(key, 0) + 1
            continue
        if value is None and cfg.require_catalog:
            skipped["band"] = skipped.get("band", 0) + 1
            continue
        if value is not None:
            inst.append(-2.5 * math.log10(r["flux"]))
            cat.append(value)
            bvs.append(star.get("bv"))
        used_entries.append((e, r))
    res.used = used_entries
    res.skipped = skipped
    res.derived = any(band_of(e["star"], band)[1]
                      for e, _r in used_entries)
    if cfg.color:
        zp = calibrate_with_color(inst, cat, bvs,
                                  target_bv=cfg.target_bv)
    else:
        zp = calibrate_zero_point(inst, cat)
    zp.setdefault("color_used", False)   # the plain path carries none
    res.zp = zp
    # error budget: CCD equation (gain from header or Ajustes) + the
    # zero point + scintillation + the flat residual + the colour term
    inst_header = header_instrument(cfg.header)
    gain = (inst_header["gain"] if inst_header["gain"] is not None
            else cfg.site_gain)
    ron = (inst_header["ron"] if inst_header["ron"] is not None
           else cfg.site_ron)
    res.gain = gain
    flux_err = ccd_flux_error(target["flux"], target["sky_pp"],
                              target["n_pix"], gain=gain, ron=ron,
                              exptime=inst_header["exptime"],
                              dark_e_s=cfg.site_dark,
                              n_sky=target.get("n_sky"))
    ccd_mag_err = mag_error(target["flux"], flux_err)
    res.err_internal = ccd_mag_err
    scint = _plate_scintillation(cfg, mx, my, inst_header["exptime"])
    res.scint = scint
    color_err = zp.get("target_color_err")
    err_total = combine_errors(ccd_mag_err, zp["zp_err"], scint,
                               cfg.site_flat, color_err)
    res.err_total = err_total
    zp_for_mag = zp["zp"]
    if zp.get("color_used") and zp["k"] is not None:
        # the fit's zero point is at B-V = 0: move the target onto it
        zp_for_mag = zp["zp"] + zp["k"] * cfg.target_bv
    mag, _e = calibrated_mag(inst_t, zp_for_mag)
    res.mag = mag
    res.check = _check_verdict(cfg.entries, used_entries, band, zp,
                               err_total)
    return res
