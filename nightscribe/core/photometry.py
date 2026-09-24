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


def measure_point(data, x, y, r_ap=R_AP, r_ann_in=R_ANN_IN,
                  r_ann_out=R_ANN_OUT, sigma_clip=True, sat_adu=None,
                  sky_mode="median", centroid_mode="gaussian"):
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
    #        or "raw" (the legacy one-pass moment)
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
    if centroid_mode == "raw":
        cx, cy = series._centroid(data, x, y)      # the legacy one-pass
    elif centroid_mode == "refined":
        cen = refined_centroid(data, x, y)
        cx, cy = cen["x"], cen["y"]              # ok=False keeps the click
    else:
        cen = gaussian_centroid(data, x, y)
        cx, cy = cen["x"], cen["y"]
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
    if not saturated and sat_adu is None:
        # No ceiling anywhere (no SATURATE card, no setting): infer it
        # from the plate itself. A soft CMOS roll-off compresses cores
        # that never form a 25-px plateau, and those "almost saturated"
        # stars poison a zero point just the same (the plateau test above
        # stays blind to them).
        ceiling = frame_ceiling(data, frame_max)
        if ceiling is not None and peak >= _INFERRED_CEILING_FRAC * ceiling:
            return _fail(f"comprimida: el pico llega al recorte de la "
                         f"placa (~{ceiling:.0f} ADU)",
                         f"clipped: the peak reaches the plate ceiling "
                         f"(~{ceiling:.0f} ADU)") | {
                "x": cx, "y": cy, "sky_pp": sky_pp, "peak": peak,
                "n_pix": n_pix, "saturated": True}
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
    seed = refined_centroid(data, x, y, sky_pp=sky_pp, fwhm=fwhm)
    sx, sy = seed["x"], seed["y"]
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
    # parabolic refinement of the correlation peak (sub-lattice)
    def _peak(c0, c1, c2, base, step):
        denom = c0 - 2.0 * c1 + c2
        if abs(denom) < 1e-12:
            return base
        return base + 0.5 * step * (c0 - c2) / denom

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
    cen = refined_centroid(data, x, y, fwhm=fwhm)
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
