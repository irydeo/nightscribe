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

from . import coords, fits_meta, outliers, series

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
# How far a star's peak must clear the local noise before the second
# moments can measure its width. The window's positive half of the noise
# is a pedestal (about 0.4 sigma per pixel over the 19x19 cutout) and the
# moments integrate it as if it were light: for a PSF of ~1.2 px the
# pedestal overtakes the star's own flux below ~20 sigma, and the FWHM
# comes out three times too large (measured on 2025 UR: 13 px against the
# radial profile's 2.7). Above it the moments are the better of the two.
_MOMENTS_MIN_SNR = 20.0

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
    # The answer is the PATCH the aperture needs, not the whole plate: a
    # (h, w) array per star cost 38 of the 50 ms that measure_point spent
    # on a 2048² plate (measured), and that price was paid for every
    # candidate of a proposal and every frame of a series. A star is a few
    # pixels wide; the plate is not.
    # @args: shape - (h, w) of the plate (the bounds), cx/cy - the star's
    #        centre (in float pixels), r - the aperture radius,
    #        subsample - the grid per axis used on the boundary pixels
    # @return: (cover, y0, x0): the coverages in 0..1 of the pixels around
    #          the aperture, and the plate coordinates of the patch's
    #          top-left corner (empty patch when the star is off-plate)
    h, w = int(shape[0]), int(shape[1])
    y0 = max(0, int(math.floor(cy - r - 1.0)))
    y1 = min(h, int(math.ceil(cy + r + 1.0)) + 1)
    x0 = max(0, int(math.floor(cx - r - 1.0)))
    x1 = min(w, int(math.ceil(cx + r + 1.0)) + 1)
    if x1 <= x0 or y1 <= y0:
        return np.zeros((0, 0), dtype=np.float64), 0, 0
    yy, xx = np.mgrid[y0:y1, x0:x1]
    dist = np.hypot(xx - cx, yy - cy)
    cover = np.zeros(dist.shape, dtype=np.float64)
    cover[dist <= r - 0.8] = 1.0
    maybe = (dist > r - 0.8) & (dist < r + 0.8)
    if not np.any(maybe):
        return cover, y0, x0
    n = max(2, int(subsample))
    offsets = (np.arange(n) + 0.5) / n - 0.5      # sub-pixel centres
    rows, cols = np.nonzero(maybe)
    for py, px in zip(rows, cols):
        # the fraction of THIS pixel inside the circle: how many of the
        # sub-samples fall within the radius. The sub-samples use the
        # PLATE's coordinates (the patch's own indices are local: mixing
        # them up answers about the wrong pixel)
        sx = (px + x0) + offsets[:, None]
        sy = (py + y0) + offsets[None, :]
        inside = ((sx - cx) ** 2 + (sy - cy) ** 2) <= r * r
        cover[py, px] = float(inside.sum()) / float(n * n)
    return cover, y0, x0


def measure_point(data, x, y, r_ap=R_AP, r_ann_in=R_ANN_IN,
                  r_ann_out=R_ANN_OUT, sigma_clip=True, sat_adu=None,
                  linear_adu=None, sky_mode="median",
                  centroid_mode="gaussian", fwhm=None, robust=True):
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
    #        the default), "refined" (sky-subtracted moment, two passes),
    #        "raw" (the legacy one-pass moment) or "none" (the observer's
    #        hand-placed centre, used exactly: a faint SN is never dragged),
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
    if centroid_mode == "none":
        # The observer placed the centre by hand (a very faint SN the
        # algorithm would drag to a neighbour): use it EXACTLY, no search.
        cx, cy = float(x), float(y)
    elif centroid_mode == "raw":
        cx, cy = series._centroid(data, x, y)      # the legacy one-pass
    elif centroid_mode == "refined":
        cen = refined_centroid(data, x, y)
        cx, cy = cen["x"], cen["y"]              # ok=False keeps the click
        cen_ok = cen["ok"]
    else:
        cen = gaussian_centroid(data, x, y, fwhm=fwhm, sky_pp=None,
                                robust=robust)
        cx, cy = cen["x"], cen["y"]              # ok=False keeps the click
        cen_ok = cen["ok"]
    # EVERYTHING BELOW HAPPENS IN A PATCH around the star (the aperture
    # and the sky annulus need nothing else): the plate-wide arrays this
    # used to build per star were 20 times the work of the arithmetic they
    # fed (measured on a 2048² plate: 38 ms of `pixel_coverage` plus the
    # full-frame radius grid).
    pad = int(math.ceil(max(r_ann_out, r_ap))) + 2
    py0 = max(0, int(math.floor(cy)) - pad)
    py1 = min(h, int(math.ceil(cy)) + pad + 1)
    px0 = max(0, int(math.floor(cx)) - pad)
    px1 = min(w, int(math.ceil(cx)) + pad + 1)
    sub = np.asarray(data[py0:py1, px0:px1], dtype=np.float64)
    yy, xx = np.mgrid[py0:py1, px0:px1]
    r2 = (xx - cx) ** 2 + (yy - cy) ** 2
    # the aperture, pixel by pixel: each pixel weighs the fraction of its
    # area that falls inside the circle (see pixel_coverage). The effective
    # AREA is the sum of those weights, and it is what the sky is scaled
    # by: using the pixel COUNT here would subtract too much sky from a
    # small aperture and too little from a big one.
    cover, cy0, cx0 = pixel_coverage((h, w), cx, cy, r_ap)
    weights = np.zeros(sub.shape, dtype=np.float64)
    if cover.size:
        weights[cy0 - py0:cy0 - py0 + cover.shape[0],
                cx0 - px0:cx0 - px0 + cover.shape[1]] = cover
    usable = weights > 0.0
    if not np.any(usable):
        out = _fail("sin píxeles de apertura", "no aperture pixels")
        out.update(x=cx, y=cy)
        return out
    finite = np.isfinite(sub[usable])
    w_eff = np.where(finite, weights[usable], 0.0)
    values = np.where(finite, sub[usable], 0.0)
    area = float(w_eff.sum())
    if area <= 0.0:
        out = _fail("sin píxeles finitos en la apertura",
                    "no finite pixel in the aperture")
        out.update(x=cx, y=cy)
        return out
    n_pix = area
    total = float((values * w_eff).sum())
    peak = float(np.nanmax(sub[usable]))
    ann_mask = (r2 >= r_ann_in ** 2) & (r2 <= r_ann_out ** 2)
    ann_pixels = sub[ann_mask]
    if ann_pixels.size:
        iters = SIG_ITERS if sigma_clip else 0
        if sky_mode == "plane":
            ann_x = np.broadcast_to(xx, sub.shape)[ann_mask]
            ann_y = np.broadcast_to(yy, sub.shape)[ann_mask]
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
    # The sky's own noise per pixel, from the SAME annulus that is already
    # in hand: it is the honest denominator of this star's signal-to-noise,
    # and it is what the limiting-magnitude fit and the matched filter stand
    # on. One robust median over a few hundred pixels, so it is cheap.
    sigma_pp = sky_sigma(ann_pixels) if ann_pixels.size else None
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
            (r2 <= r_ann_in ** 2) & (sub > frame_max - eps)))
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
    snr = None
    if sigma_pp and n_pix > 0:
        # the aperture's signal-to-noise with the sky's noise only: the
        # object's own shot noise is a second-order term for the faint
        # sources this exists for, and it is the CCD equation (below) that
        # carries it in the error budget
        snr = float(flux) / (float(sigma_pp) * math.sqrt(float(n_pix)))
    return {"x": cx, "y": cy, "flux": flux, "sky_pp": sky_pp,
            "peak": peak, "n_pix": n_pix, "n_sky": n_sky, "saturated": False,
            "ok": True, "reason": None, "cen_ok": cen_ok,
            "sigma_pp": (float(sigma_pp) if sigma_pp else None), "snr": snr}


# ------------------------------------------------- the point spread (P2)

# The PSF model's half-size in pixels: big enough to hold the wings of a
# seeing-limited star (measured on 2025 UR: FWHM 5.4 px, so this is a bit
# over 4 FWHM across) and small enough that the matched filter stays a
# patch operation.
PSF_HALF_DEFAULT = 12
# FWHM = 2 * sqrt(2 ln 2) * sigma, the constant that ties a Gaussian's
# width to what the observer measures on the screen.
_FWHM_TO_SIGMA = 2.3548200450309493
# Below this trail (px) the object is called round. Measured on synthetic
# stars of the same seeing: a ROUND star reads up to 1.45 px of trail at
# SNR ~20, because the second moments of a noisy image are not exactly
# isotropic. Calling that a trail would send the observer to shorten an
# exposure that was already fine.
TRAIL_MIN_PX = 1.5


def gaussian_psf(fwhm_px, half=None, ratio=1.0, pa_deg=0.0):
    # @args: fwhm_px - the point spread's FWHM in px (None: 3 px),
    #        half - the box's half-size in px, ratio - the minor/major axis
    #        ratio (1.0 round, below 1 trailed), pa_deg - the major axis's
    #        position angle in the same convention as the trail
    # @return: a normalised (2*half+1)^2 PSF that SUMS to one
    # Summing to one is what makes the matched filter's amplitude the
    # star's own flux: the filter answers "how much flux, in this shape",
    # and the shape carries no scale of its own.
    fwhm = float(fwhm_px) if fwhm_px else 3.0
    half = int(PSF_HALF_DEFAULT if half is None else half)
    sigma = max(1e-3, fwhm / _FWHM_TO_SIGMA)
    yy, xx = np.mgrid[-half:half + 1, -half:half + 1]
    # the trail: stretch along the position angle and squeeze across it,
    # which moves the light without adding any (the area is kept)
    ang = math.radians(float(pa_deg))
    u = xx * math.cos(ang) + yy * math.sin(ang)
    v = -xx * math.sin(ang) + yy * math.cos(ang)
    sx = sigma / math.sqrt(max(1e-6, float(ratio)))
    sy = sigma * math.sqrt(max(1e-6, float(ratio)))
    m = np.exp(-0.5 * ((u / sx) ** 2 + (v / sy) ** 2))
    total = float(m.sum())
    return (m / total) if total > 0 else m


def empirical_psf(cutouts, half=None):
    # @args: cutouts - list of (2h+1, 2h+1) star patches, already
    #        sky-subtracted and centred on the star, half - the box's
    #        half-size (taken from the patches when None)
    # @return: a normalised PSF (sums to one), or None when nothing is
    #          usable
    # The MEDIAN of the patches, never the mean: a cosmic ray, a hot pixel
    # or a close neighbour in one star must not become part of the shape.
    # The empirical profile is the honest one because it carries the real
    # wings, and the wings are exactly where a matched filter beats an
    # aperture: an aperture gives them the same weight as the core, and
    # they are mostly noise.
    stack = [np.asarray(c, dtype=np.float64) for c in (cutouts or [])]
    stack = [c for c in stack if c.ndim == 2 and c.size]
    if not stack:
        return None
    shapes = {c.shape for c in stack}
    if len(shapes) != 1:
        return None
    cube = np.stack(stack, axis=0)
    med = np.median(cube, axis=0)
    # the patches are sky-subtracted but a residual pedestal can survive
    # (a comp on a faint gradient): removing the corners' median keeps the
    # shape from carrying a pedestal of its own
    h, w = med.shape
    edge = np.concatenate([med[:2].ravel(), med[-2:].ravel(),
                           med[:, :2].ravel(), med[:, -2:].ravel()])
    med = med - float(np.median(edge))
    med = np.clip(med, 0.0, None)
    total = float(med.sum())
    if not np.isfinite(total) or total <= 0:
        return None
    return med / total


def _shift_psf(psf, dx, dy):
    # @args: psf - a normalised PSF on an odd grid, centred, dx/dy - the
    #        sub-pixel shift to apply (in px, the fractional part of the
    #        object's position inside its central pixel)
    # @return: the shifted PSF, renormalised so it still sums to one
    # Bilinear on purpose: the PSF is smooth, and a spline's ringing on a
    # 25x25 grid would put negative "light" in the wings, which a matched
    # filter would then subtract from the star.
    if abs(dx) < 1e-6 and abs(dy) < 1e-6:
        return psf
    m = np.asarray(psf, dtype=np.float64)
    h, w = m.shape
    yy, xx = np.mgrid[0:h, 0:w]
    xs = xx - dx
    ys = yy - dy
    x0 = np.floor(xs).astype(int)
    y0 = np.floor(ys).astype(int)
    fx = xs - x0
    fy = ys - y0
    out = np.zeros_like(m)
    for oy in (0, 1):
        for ox in (0, 1):
            xa = np.clip(x0 + ox, 0, w - 1)
            ya = np.clip(y0 + oy, 0, h - 1)
            weight = (fx if ox else 1.0 - fx) * (fy if oy else 1.0 - fy)
            out += weight * m[ya, xa]
    total = float(out.sum())
    return (out / total) if total > 0 else m


def sky_sigma(values):
    # @args: values - 1D sky samples (ADU)
    # @return: the sky's noise per pixel (ADU), or None when it cannot be
    #          measured
    # The scaled MAD, not the standard deviation: the sky samples of an
    # annulus carry the object's wings and any neighbour that fell inside,
    # and a robust estimator ignores them by construction. This is the
    # sigma the matched filter needs, and it is the SAME one the aperture
    # comparison uses, so the two differ only in their weighting.
    arr = np.asarray(values, dtype=np.float64)
    arr = arr[np.isfinite(arr)]
    if arr.size < 5:
        return None
    sigma = float(outliers.scaled_mad(arr))
    return sigma if np.isfinite(sigma) and sigma > 0 else None


def _matched_fail(ap, reason_es, reason_en, sigma):
    # The shape EVERY failure of the matched filter comes back with.
    #
    # The APERTURE's own numbers are kept (flux_ap): it is a different
    # measurement of the same star and it may well be fine, and the observer
    # is entitled to see it. What is None is the filter's own.
    #
    # ok is False and the reason travels, because the previous version of
    # these paths returned ok=True with flux=None, which is the worst of both
    # worlds: a caller that trusted "ok" then did log10(None) or
    # log10(negative). Fixed on 2026-10-07 after the real 2025 FG18 visit
    # (frame 15, target T18 at 306,1669) came back with flux -845.6 ADU and
    # ok=True, and measure_plate died with "math domain error" instead of
    # marking one point as unmeasurable.
    # @args: ap - the aperture measurement of the same star, reason_es/en -
    #        the plain-language pair, sigma - the sky noise per pixel (None
    #        when it could not be measured either)
    # @return: the dict, with ok=False
    out = dict(ap)
    out.update(ok=False, reason={"es": reason_es, "en": reason_en},
               flux=None, flux_ap=ap.get("flux"), snr=None, snr_ap=None,
               n_eff=None, sigma_pp=sigma)
    return out


def measure_matched(data, x, y, psf, r_ap=R_AP, r_ann_in=R_ANN_IN,
                    r_ann_out=R_ANN_OUT, sat_adu=None, fwhm=None,
                    centroid_mode="gaussian", sigma_clip=True,
                    linear_adu=None, sky_mode="median", robust=True):
    # @args: data - 2D array (ADU), x/y - the object's position, psf - a
    #        normalised PSF (sums to one) on an odd grid, the same
    #        apertures as measure_point, sat_adu - the ceiling, fwhm - the
    #        seeing, centroid_mode/sigma_clip/linear_adu/sky_mode/robust -
    #        as measure_point: the filter has to honour the SAME recipe as
    #        the aperture, or a plate measured one way and the other would
    #        not be comparable
    # @return: {"ok", "reason", "x", "y", "flux", "flux_ap", "snr",
    #          "snr_ap", "n_eff", "n_pix", "sky_pp", "sigma_pp", "peak"}
    # THE MATCHED FILTER. With a known shape m (summing to one) and white
    # noise sigma per pixel, the best estimate of the star's flux is
    #
    #     A = sum(m * (p - sky)) / sum(m^2)
    #
    # and its signal-to-noise is
    #
    #     SNR = sum(m * (p - sky)) / (sigma * sqrt(sum(m^2)))
    #
    # which is the largest SNR any LINEAR filter can reach on that data
    # (Cauchy-Schwarz: the optimal weight is proportional to the shape
    # itself). An aperture is the special case m = 1 inside the circle,
    # and it is not optimal: it gives the noisy wings the same weight as
    # the core. The gain is largest exactly where it matters, at low SNR.
    #
    # Both numbers come out of the SAME centroid and the SAME sky, and
    # both SNRs use the same sigma: the only difference between them is
    # the weighting, so the comparison measures the FILTER and nothing
    # else. A new centroid or a new sky per method would hide the effect
    # inside the difference of two other estimates.
    ap = measure_point(data, x, y, r_ap=r_ap, r_ann_in=r_ann_in,
                       r_ann_out=r_ann_out, sat_adu=sat_adu, fwhm=fwhm,
                       centroid_mode=centroid_mode, sigma_clip=sigma_clip,
                       linear_adu=linear_adu, sky_mode=sky_mode,
                       robust=robust)
    if not ap.get("ok"):
        out = dict(ap)
        out.update(flux=None, flux_ap=None, snr=None, snr_ap=None,
                   n_eff=None, sigma_pp=None)
        return out
    cx, cy = float(ap["x"]), float(ap["y"])
    sky_pp = float(ap.get("sky_pp") or 0.0)
    h, w = data.shape
    half = (np.asarray(psf).shape[0] - 1) // 2
    # the patch has to hold the whole PSF around the object, and the sky
    # annulus is measured on the SAME patch the aperture used (its own)
    pad = int(math.ceil(max(r_ann_out, r_ap, half))) + 2
    py0 = max(0, int(math.floor(cy)) - pad)
    py1 = min(h, int(math.ceil(cy)) + pad + 1)
    px0 = max(0, int(math.floor(cx)) - pad)
    px1 = min(w, int(math.ceil(cx)) + pad + 1)
    sub = np.asarray(data[py0:py1, px0:px1], dtype=np.float64)
    yy, xx = np.mgrid[py0:py1, px0:px1]
    r2 = (xx - cx) ** 2 + (yy - cy) ** 2
    # The noise per pixel is the one the aperture already measured, on the
    # SAME annulus (measure_point returns it), so both SNRs share the
    # denominator and the comparison is about the WEIGHTING alone. The
    # fallback recomputes it if an older caller did not pass it through.
    sigma = ap.get("sigma_pp")
    if sigma is None:
        ann_mask = (r2 >= r_ann_in ** 2) & (r2 <= r_ann_out ** 2)
        sigma = sky_sigma(sub[ann_mask])
    if sigma is None:
        return _matched_fail(ap, "sin ruido de cielo medible",
                             "no measurable sky noise", None)
    # the PSF placed where the object actually is, inside its pixel
    m = _shift_psf(psf, cx - math.floor(cx), cy - math.floor(cy))
    mh = (m.shape[0] - 1) // 2
    ix = int(math.floor(cx)) - px0 - mh
    iy = int(math.floor(cy)) - py0 - mh
    patch = np.full(sub.shape, 0.0)
    sx0, sy0 = max(0, ix), max(0, iy)
    sx1 = min(sub.shape[1], ix + m.shape[1])
    sy1 = min(sub.shape[0], iy + m.shape[0])
    if sx1 <= sx0 or sy1 <= sy0:
        return _matched_fail(ap, "sin píxeles utilizables",
                             "no usable pixels", sigma)
    patch[sy0:sy1, sx0:sx1] = m[sy0 - iy:sy1 - iy, sx0 - ix:sx1 - ix]
    net = sub - sky_pp
    num = float(np.nansum(patch * net))
    gg = float(np.nansum(patch ** 2))
    if gg <= 0:
        return _matched_fail(ap, "sin píxeles utilizables",
                             "no usable pixels", sigma)
    flux = num / gg
    snr = num / (sigma * math.sqrt(gg))
    if not math.isfinite(flux) or flux <= 0.0:
        # THE FILTER CAN COME OUT NEGATIVE, and it is not a rare accident:
        # the matched filter correlates a PSF with the data, and on noise the
        # correlation is as often negative as positive. A negative flux is
        # not a faint measurement, it is the absence of one, and the callers
        # take -2.5*log10(flux) with a truthiness guard that a negative
        # number passes. Measured on the real 2025 FG18 visit (frame 15,
        # target T18 at 306,1669): flux -845.6 ADU, snr -0.97, and the whole
        # 207-frame run died instead of marking one point.
        return _matched_fail(ap, "sin señal medible",
                             "no measurable signal", sigma)
    # the aperture's own SNR with the SAME noise per pixel and the same
    # sky: this is what isolates the weighting (see the docstring)
    n_ap = float(ap.get("n_pix") or 0.0)
    flux_ap = float(ap.get("flux") or 0.0)
    snr_ap = ap.get("snr")
    if snr_ap is None and n_ap > 0:
        snr_ap = flux_ap / (sigma * math.sqrt(n_ap))
    return {"ok": True, "reason": None, "x": cx, "y": cy, "flux": flux,
            "flux_ap": flux_ap, "snr": snr, "snr_ap": snr_ap,
            "n_eff": 1.0 / gg, "n_pix": n_ap, "sky_pp": sky_pp,
            "sigma_pp": sigma, "peak": ap.get("peak"),
            "saturated": ap.get("saturated"), "n_sky": ap.get("n_sky")}


def psf_elongation(data, x, y, fwhm_px=None, r_max=None, sky_pp=None,
                   thresh=1.0):
    # @args: data - 2D array, x/y - the object's position, fwhm_px - the
    #        seeing when the caller knows it, r_max - the moment window's
    #        radius (default: 2x the FWHM, see below), sky_pp - the sky per
    #        pixel when the caller knows it, thresh - how many sigma above
    #        the sky a pixel has to be to count (default 1)
    # @return: {"ok", "reason", "ratio", "pa_deg", "trail_px", "fwhm_px",
    #          "fwhm_major_px", "significant", "sky_pp", "sigma_pp"}
    # The shape of what was measured, from its second moments: the axis
    # ratio (minor over major), the position angle of the MAJOR axis, and
    # the equivalent TRAIL length.
    #
    # The trail is the honest part. A moving object smears along its path,
    # and a uniform line of length L convolved with a round PSF of width
    # sigma comes out as a Gaussian whose long axis carries
    # sigma_long^2 = sigma^2 + L^2/12 (the variance of a uniform segment).
    # Inverting that turns "the object looks elongated" into "the exposure
    # was 2.4 px too long for this motion", which is a number the observer
    # can act on.
    #
    # The window and the threshold are MEASURED, not chosen by taste. A
    # wide window makes the second moments chase the sky noise (measured
    # with a 4-FWHM window on a round, bright star: it reported a 1.56 px
    # trail out of nothing), and a low threshold lets the noise's positive
    # half in. The table below is a synthetic Gaussian of FWHM 3.5 px with
    # sky 1000 ADU and sigma 5, injected trails of 0, 3, 6 and 10 px, ten
    # realisations each:
    #
    #     window   thresh   flux 20000        flux 2000         flux 300
    #     2 FWHM   1.0      0.4 3.4 6.2 9.7   1.5 2.7 5.6 9.1   3.4 3.1 3.0 5.4
    #     2 FWHM   0.0      0.6 4.9 4.9 4.9   1.8 4.9 4.9 4.9   3.6 4.9 4.9 4.9
    #     4 FWHM   1.0      (a round star reads 1.5 px of trail)
    #
    # so the window is 2 FWHM and the threshold 1 sigma, and the result is
    # only called a trail above TRAIL_MIN_PX: a round star reads up to
    # 1.45 px at SNR ~20, and a trail shorter than that is not one.
    if data is None or data.size == 0:
        return _fail("no hay imagen", "no image")
    h, w = data.shape
    if not (0 <= x < w and 0 <= y < h):
        return _fail("fuera del marco", "out of frame")
    if fwhm_px is None:
        # the radial profile, not the moments: on a broad or noisy PSF the
        # radial one is the robust of the two (see estimate_fwhm's table)
        fwhm_px = estimate_fwhm(data, [(x, y)], method="radial")
    fwhm_px = float(fwhm_px) if fwhm_px else 3.0
    if r_max is None:
        r_max = int(max(5, min(30, round(2.0 * fwhm_px))))
    r_max = int(max(4, min(r_max, min(h, w) // 2 - 1)))
    px0 = max(0, int(math.floor(x)) - r_max)
    px1 = min(w, int(math.ceil(x)) + r_max + 1)
    py0 = max(0, int(math.floor(y)) - r_max)
    py1 = min(h, int(math.ceil(y)) + r_max + 1)
    sub = np.asarray(data[py0:py1, px0:px1], dtype=np.float64)
    yy, xx = np.mgrid[py0:py1, px0:px1]
    r2 = (xx - x) ** 2 + (yy - y) ** 2
    ann = (r2 >= (0.75 * r_max) ** 2) & (r2 <= r_max ** 2)
    sigma = None
    if sky_pp is None:
        sky_pp = 0.0
        if np.any(ann):
            med, _n = _sigma_clipped_median(sub[ann])
            sky_pp = float(med or 0.0)
    if np.any(ann):
        sigma = sky_sigma(sub[ann])
    floor = float(sky_pp) + (float(thresh) * sigma if sigma else 0.0)
    weight = np.where(r2 <= r_max ** 2, sub - floor, 0.0)
    weight = np.clip(weight, 0.0, None)
    total = float(weight.sum())
    if total <= 0:
        return _fail("sin luz que medir", "no light to measure")
    mx = float((weight * (xx - x)).sum()) / total
    my = float((weight * (yy - y)).sum()) / total
    vxx = float((weight * (xx - x - mx) ** 2).sum()) / total
    vyy = float((weight * (yy - y - my) ** 2).sum()) / total
    vxy = float((weight * (xx - x - mx) * (yy - y - my)).sum()) / total
    # the eigenvectors of the covariance give the axes without a fit
    half_trace = 0.5 * (vxx + vyy)
    disc = math.sqrt(max(0.0, 0.25 * (vxx - vyy) ** 2 + vxy ** 2))
    major = half_trace + disc
    minor = half_trace - disc
    if major <= 0 or minor <= 0:
        return _fail("la luz no tiene forma medible",
                     "the light has no measurable shape")
    ratio = math.sqrt(max(0.0, minor / major))
    # the position angle of the MAJOR axis, in the image's own convention
    pa = 0.5 * math.atan2(2.0 * vxy, vxx - vyy)
    # the trail: the extra length a line would add along the major axis
    sigma_long = math.sqrt(major)
    sigma_short = math.sqrt(minor)
    extra = max(0.0, major - minor)
    trail = math.sqrt(12.0 * extra) if extra > 0 else 0.0
    return {"ok": True, "reason": None, "ratio": float(ratio),
            "pa_deg": float(math.degrees(pa) % 180.0),
            "trail_px": float(trail),
            "significant": bool(trail >= TRAIL_MIN_PX),
            "fwhm_px": float(sigma_short * _FWHM_TO_SIGMA),
            "fwhm_major_px": float(sigma_long * _FWHM_TO_SIGMA),
            "sky_pp": float(sky_pp),
            "sigma_pp": (float(sigma) if sigma else None)}


# ------------------------------------------------- the night's diagnosis (P3)

# The slope of log10(SNR) against magnitude for a sky-limited star. Every
# magnitude is a factor 10^0.4 = 2.512 in flux, and the noise does not care
# how bright the star is, so the SNR must fall with that same factor. It is
# not a constant to trust blindly: it is a CHECK. A field measured under a
# bright moon, with a very short exposure or with saturated comparisons
# comes out far from it, and then the limiting magnitude is not quotable.
SKY_LIMITED_SLOPE = -0.4
# How far the fitted slope may sit from it and still be called sky-limited.
# A slope of -0.3 means a factor 2.0 per magnitude instead of 2.512, i.e. a
# quarter of the flux unaccounted for at every step: that is already a
# broken field (a bright moon, saturation at the bright end, a very short
# exposure) and the number is not to be quoted. Measured on the synthetic
# cases of test_photometry_diagnostics: a clean sky-limited set lands within
# 0.02 of -0.4, and a set with a factor 4 per magnitude lands at -0.6.
_SLOPE_TOLERANCE = 0.15


def limiting_magnitude(pairs, snr_target=5.0, sigma_clip=2.5):
    # @args: pairs - [(magnitude, snr)] of the field stars, snr_target - the
    #        signal-to-noise the limit is quoted at (5 by convention),
    #        sigma_clip - how far a star may sit from the fitted line
    # @return: {"ok", "reason", "mag", "slope", "intercept", "n", "used",
    #          "mag_range"}
    # "How faint can I go tonight?" answered with THIS night's own stars.
    # For a sky-limited source the signal-to-noise falls as a power law:
    #
    #     log10(SNR) = a + b * mag          with b ~ -0.4
    #
    # and fitting that line to the stars actually measured on the stack, then
    # solving it for SNR = 5, gives the limiting magnitude with the sky, the
    # seeing, the exposure and the aperture all inside the two numbers. No
    # table, no model: the night measures itself.
    #
    # The fit is a plain least squares with one outlier pass, because a
    # single saturated comparison star or a cosmic ray would otherwise drag
    # the line. And the SLOPE is checked against the physics: a fit far from
    # -0.4 means the field is not sky-limited, and the reason says so rather
    # than quoting a figure nobody should trust.
    pts = [(float(m), float(s)) for m, s in (pairs or [])
           if m is not None and s is not None and s > 0]
    if len(pts) < 4:
        return {"ok": False, "reason": "fewer than four stars to fit",
                "mag": None, "slope": None, "intercept": None, "n": len(pts),
                "used": [], "mag_range": None}
    mags = np.asarray([p[0] for p in pts])
    logs = np.log10(np.asarray([p[1] for p in pts]))
    # Theil-Sen: the MEDIAN of the slopes of every PAIR of stars, and the
    # median of the intercepts that slope implies. With a handful of
    # comparisons this is the honest robust estimator and not a taste: a
    # saturated star or a cosmic ray moves a least-squares line (measured on
    # the seven-point case of the tests: it moved the limit by 0.5 mag and
    # the clip could not repair it, because the dragged line inflates the
    # MAD the clip is measured against), and it cannot move a median of 21
    # pairs. It also needs no threshold to tune, which on five points is a
    # guess dressed as a parameter.
    slopes = []
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            dm = mags[j] - mags[i]
            if abs(dm) > 1e-6:
                slopes.append((logs[j] - logs[i]) / dm)
    if not slopes:
        return {"ok": False, "reason": "every star has the same magnitude",
                "mag": None, "slope": None, "intercept": None,
                "n": len(pts), "used": [], "mag_range": None}
    slope = float(np.median(slopes))
    intercept = float(np.median(logs - slope * mags))
    if not np.isfinite(slope) or slope >= 0:
        return {"ok": False, "reason": "the signal-to-noise does not fall "
                "with magnitude", "mag": None, "slope": None,
                "intercept": None, "n": len(pts), "used": [],
                "mag_range": None}
    limit = (math.log10(float(snr_target)) - intercept) / slope
    # `used` is a REPORT, not the fit: it says which stars sit on the line
    # and which do not, so the interface can name the ones that were left
    # out of the picture without having changed the answer.
    resid = logs - (slope * mags + intercept)
    mad = float(outliers.scaled_mad(resid))
    used = ([True] * len(pts) if mad <= 0
            else [bool(abs(r) <= sigma_clip * mad) for r in resid])
    return {"ok": True, "reason": None, "mag": float(limit),
            "slope": slope, "intercept": intercept, "n": len(pts),
            "used": used, "mag_range": (float(mags.min()), float(mags.max())),
            "sky_limited": bool(
                abs(slope - SKY_LIMITED_SLOPE) <= _SLOPE_TOLERANCE)}


def quality_grid(points, shape, n=4):
    # @args: points - [(x, y, residual_arcsec)] of the measured stars,
    #        shape - the plate (h, w) or (naxis1, naxis2), n - divisions per
    #        axis
    # @return: {"ok", "reason", "cells": [[median|None]], "median", "worst",
    #          "spread", "n"}
    # A plate solution can be good in the middle and bad at the corners
    # (distortion, a wrong scale, a tilted chip), and one number for the
    # whole plate hides exactly that. The median residual per cell of an
    # n x n grid says WHERE, in one glance, and the spread between the cells
    # says whether the solution is even. Tycho's Image Statistics draws the
    # same map for the same reason.
    #
    # The MEDIAN per cell, not the mean: one bad match or a cosmic ray must
    # not paint a corner red on its own.
    pts = [(float(x), float(y), float(r)) for x, y, r in (points or [])
           if x is not None and y is not None and r is not None
           and np.isfinite(r)]
    if len(pts) < 4:
        return {"ok": False, "reason": "fewer than four stars to judge",
                "cells": [], "median": None, "worst": None, "spread": None,
                "n": len(pts)}
    width = float(shape[1] if len(shape) > 1 else shape[0])
    height = float(shape[0])
    cells = [[None for _ in range(n)] for _ in range(n)]
    for j in range(n):
        for i in range(n):
            sel = [p[2] for p in pts
                   if (j / n) <= (p[1] / max(height, 1e-9)) < ((j + 1) / n)
                   and (i / n) <= (p[0] / max(width, 1e-9)) < ((i + 1) / n)]
            if sel:
                cells[j][i] = float(np.median(sel))
    filled = [c for row in cells for c in row if c is not None]
    if not filled:
        return {"ok": False, "reason": "no cell has a star in it",
                "cells": cells, "median": None, "worst": None,
                "spread": None, "n": len(pts)}
    return {"ok": True, "reason": None, "cells": cells,
            "median": float(np.median(filled)), "worst": float(max(filled)),
            "spread": float(max(filled) - min(filled)), "n": len(pts)}


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
        zp_err = outliers.MAD_TO_SIGMA * mad / math.sqrt(n)
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
    #
    # THE CONVERSION GAIN IS READ BEFORE THE CAMERA'S GAIN SETTING
    # (2026-10-08). EGAIN and CCDGAIN are electrons per ADU by definition;
    # a bare GAIN is usually the camera's own gain SETTING (a small
    # integer, not an e-/ADU figure). Reading GAIN first took the setting
    # for the conversion gain: on the author's own QHY42Pro frames the
    # header carried GAIN = 5 AND EGAIN = 1, and the code used 5. The
    # order matters because the two numbers are not even in the same unit.
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

    out["gain"] = _num("EGAIN", "CCDGAIN", "GAIN", "GAIN1", "GAINX")
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


def cutout_window(data, x, y, half):
    # The pixel window around a star: clamped to the frame, and a real
    # window or None.
    #
    # This looks like a one-liner with max/min and it is not. A star twenty
    # pixels above the top edge gives `y1 = min(h, y + half + 1) = -19`, and
    # `data[0:-19]` is a VALID, non-empty slice in numpy (a negative index
    # counts from the end, so it silently reads the BOTTOM of the frame)
    # while `np.mgrid[0:-19]` reads that same -19 as a negative SIZE and
    # raises "negative dimensions are not allowed". That is not theory: it
    # killed a real run (HAT-P-32 b, 142 frames, dead at frame ~18) because
    # a comparison star of the sequence fell off the top of the frame.
    #
    # Clipping BOTH ends is the only honest way, and having one function do
    # it means no reader of this module has to remember the trap.
    #
    # @args: data - 2D array, x/y - the star's centre in pixels (float),
    #        half - the window's half-size
    # @return: (y0, y1, x0, x1) with y1 > y0 and x1 > x0, or None when the
    #          window has no pixels at all
    if data is None or getattr(data, "size", 0) == 0:
        return None
    h, w = int(data.shape[0]), int(data.shape[1])
    x0 = int(min(max(math.floor(x - half), 0), w))
    x1 = int(min(max(math.ceil(x + half + 1), 0), w))
    y0 = int(min(max(math.floor(y - half), 0), h))
    y1 = int(min(max(math.ceil(y + half + 1), 0), h))
    if x1 <= x0 or y1 <= y0:
        return None
    return y0, y1, x0, x1


def fwhm_radial(data, x, y, rmax=None, level=None, bin_width=0.5):
    # The seeing, measured as the radius of the HALF MAXIMUM.
    #
    # The alternative is the second moment (the variance of the light),
    # which is a perfectly good definition on a clean, isolated star and a
    # bad one on a real frame: a hot pixel inside the box or a neighbour's
    # wing inflates the variance with a weight proportional to the SQUARE
    # of its distance, and the "seeing" comes out of a night that never
    # happened.
    #
    # This way is built on two robust pieces: each annulus contributes the
    # MEDIAN of its pixels (a single bad pixel cannot move it), and the
    # answer is where the averaged profile crosses half its central value
    # (a wing from a neighbour raises the profile at large radii, but the
    # half-maximum crossing sits well inside where it is still the star's
    # own light).
    #
    # @args: data - 2D array, x/y - the star's centre (float pixels),
    #        rmax - how far to look (default: 12 px), level - the sky
    #        level to subtract (None: the median of the outer annuli),
    #        bin_width - radial step in pixels
    # @return: the FWHM in pixels, or None when no crossing is found
    arr = np.asarray(data, dtype=np.float64)
    rmax = float(rmax if rmax else 12.0)
    win = cutout_window(arr, x, y, rmax + 1)
    if win is None:
        return None
    y0, y1, x0, x1 = win
    sub = arr[y0:y1, x0:x1]
    yy, xx = np.mgrid[y0:y1, x0:x1]
    dist = np.hypot(xx - x, yy - y)
    inside = dist < rmax
    if not np.any(inside):
        return None
    values = sub[inside]
    radii = dist[inside]
    if level is None:
        # the outer half of the profile is sky: its median is the level
        outer = values[radii >= 0.7 * rmax]
        level = float(np.median(outer)) if outer.size else float(
            np.median(values))
    profile = values - float(level)
    nbins = max(3, int(math.ceil(rmax / max(0.1, bin_width))))
    radii_of_bin = np.full(nbins, np.nan)
    heights = np.full(nbins, np.nan)
    for i in range(nbins):
        lo, hi = i * bin_width, (i + 1) * bin_width
        sel = (radii >= lo) & (radii < hi)
        if not np.any(sel):
            continue
        # The bin's radius is the MEDIAN RADIUS OF ITS OWN PIXELS, not the
        # middle of the interval: on a narrow PSF the pixels of a ring sit
        # at discrete radii (1, 1.41, 2, 2.24...) and their median value
        # belongs to the median radius, not to the middle. Plotting it at
        # the middle bends the profile and the half-maximum crossing comes
        # out ~10 % early (measured on a sigma = 1.5 px star: 3.1 px
        # instead of 3.5). With the median radius the same star reads 3.5.
        radii_of_bin[i] = float(np.median(radii[sel]))
        heights[i] = float(np.median(profile[sel]))
    central = heights[0]
    if not math.isfinite(central) or central <= 0.0:
        # a plateau (a saturated core) or a hole: the first bin does not
        # hold the maximum, so take the brightest bin as the centre value
        good = heights[np.isfinite(heights)]
        if good.size == 0:
            return None
        central = float(np.max(good))
        if central <= 0.0:
            return None
    half = central / 2.0
    for i in range(1, nbins):
        prev_v, here_v = heights[i - 1], heights[i]
        prev_r, here_r = radii_of_bin[i - 1], radii_of_bin[i]
        if not (math.isfinite(prev_v) and math.isfinite(here_v)
                and math.isfinite(prev_r) and math.isfinite(here_r)):
            continue
        if here_v < half <= prev_v:
            # linear interpolation between the two profile points: the
            # light falls smoothly through the half maximum
            span = prev_v - here_v
            frac = 0.0 if span <= 0.0 else (prev_v - half) / span
            r_half = prev_r + frac * (here_r - prev_r)
            return float(2.0 * r_half)
    return None


def estimate_fwhm(data, positions, sat_adu=None, method="auto", rmax=12.0):
    # The median seeing of a frame, measured on several stars.
    #
    # Two definitions are available, and which one is right DEPENDS on the
    # sampling. This is the measured table on a synthetic Gaussian sampled
    # at the pixel centres, which is what a plate is:
    #
    #     sigma    true FWHM   "moments"   "radial"
    #      1.0       2.35       2.35        2.79     (radial +18 %)
    #      1.5       3.53       3.53        3.86     (radial  +9 %)
    #      2.0       4.71       4.66        4.95     (radial  +5 %)
    #      3.0       7.06       6.12        7.21     (moments -13 %)
    #      5.0      11.77       6.92       10.88     (moments -41 %)
    #
    #   * a NARROW PSF (FWHM ~ 2-4 px) is under-sampled, so a profile drawn
    #     from a handful of radii cannot resolve it; the moments, which are
    #     an integral of the light, are exact. Hence the default;
    #   * a BROAD PSF is truncated by the fixed 19x19 cutout of the
    #     moments and reads far too small (6.9 against 11.8!); there the
    #     radial profile is right, because it only needs to find where the
    #     light has fallen to half, and it uses a median per annulus, so a
    #     hot pixel cannot move it.
    #
    # So the caller picks: "moments" for the common case, "radial" when
    # the frames are broad or the field is crowded. The engine's seeing
    # features (the aperture scaling and the focus gate) work on RATIOS
    # between frames, where either one is consistent.
    #
    # @args: data - 2D array, positions - [(x, y)] star pixels,
    #        sat_adu - ceiling in ADU, stars near it are skipped,
    #        method - "auto" | "moments" | "radial", rmax - radial reach (px)
    # @return: the median FWHM in px, or None when nothing is usable
    #
    # "auto" (the default) asks the DATA which estimator it can afford: a
    # star whose peak barely clears the noise goes to the radial profile,
    # and a bright one to the moments, which are the more accurate of the
    # two on a narrow PSF. The reason is measured, not aesthetic: on 2025
    # UR the sky noise is 261 ADU and a mag-17.4 comp peaks 816 above it,
    # so the positive half of the noise over the 19x19 window is FIVE times
    # the star's own flux and the moments came out at 13 px where the
    # radial profile says 2.7. Silently handing a 17 px aperture to the
    # observer is worse than a 18 % bias on a narrow star.
    if data is None:
        return None
    if method == "radial":
        fwhms = []
        for x, y in positions:
            value = fwhm_radial(data, x, y, rmax=rmax)
            if value is not None and 0.8 <= value <= 50.0:
                fwhms.append(value)
        if fwhms:
            return float(np.median(fwhms))
        # a frame where no profile crosses its half maximum (a plateau, a
        # cosmic ray, an empty box): fall through to the moments rather
        # than answering None and leaving the caller blind
    fwhms = []
    for x, y in positions:
        half = 9   # a 19x19 cutout: enough for any sane seeing disc
        win = cutout_window(data, x, y, half)
        if win is None:
            # the star is off the frame (a comparison star of the sequence
            # can be): it has no seeing to measure and it is not an error
            continue
        y0, y1, x0, x1 = win
        sub = data[y0:y1, x0:x1]
        peak = float(np.nanmax(sub))
        if sat_adu is not None and peak >= SAT_FRAC * float(sat_adu):
            continue
        sky = float(np.nanmedian(sub))
        noise = float(outliers.scaled_mad(sub))
        if method == "auto" and noise > 0.0 \
                and (peak - sky) < _MOMENTS_MIN_SNR * noise:
            # this star cannot afford the moments: the window's positive
            # noise is a pedestal the second moments integrate as if it
            # were light (see the note above the function)
            value = fwhm_radial(data, x, y, rmax=rmax)
            if value is not None and 0.8 <= value <= 50.0:
                fwhms.append(value)
            continue
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


def star_ceilings(header, cfg=None, linear_adu=None, saturate=None):
    # THE TWO CEILINGS EVERY STAR MUST CLEAR, from ONE place (ADR-066).
    #
    # The rule, asked for as a rule of the house: a star whose peak reaches
    # the detector's saturation OR the camera's linearity limit is NEVER used
    # to build a zero point. A clipped core is not proportional at all, and a
    # star above the linearity limit calibrates nothing even when it is not
    # clipped yet (its flux stopped following the light): the zero point it
    # would set is a number that looks fine and is wrong.
    #
    # Each caller used to pass these two numbers by hand, and one path (the
    # series' aperture tuning) forgot: one home means no path can forget.
    #
    # @args: header - the plate's header dict, cfg - a config-like object
    #        with .get (or None), linear_adu - an explicit linearity limit
    #        (a per-run recipe wins over the camera profile), saturate - an
    #        explicit saturation ceiling (same)
    # @return: (saturation, linearity) in ADU, either of them None when
    #          nobody knows. The header's own SATURATE card still wins over
    #          the setting, exactly as before.
    cfg_like = {"ccd_saturate": saturate} if saturate is not None else cfg
    sat = saturation_ceiling(header, cfg_like)
    lin = linear_adu if linear_adu is not None else linearity_ceiling(cfg)
    return sat, lin


def ceiling_warning(header, cfg=None, linear_adu=None, saturate=None):
    # @args: as star_ceilings
    # @return: a bilingual warning when the camera's LINEARITY limit is not
    #          known (so the app is measuring with the best ceiling it has,
    #          which is not the same thing), or None when it is.
    # Asked for 2026-10-06: with the linearity unset the app used to fall back
    # to the SATURATE card or to the plate's own clip in SILENCE, and a star
    # that is over the (unknown) linearity but under the clip slips through.
    # The observer has to know which limit is being enforced.
    _sat, lin = star_ceilings(header, cfg, linear_adu=linear_adu,
                              saturate=saturate)
    if lin is not None:
        return None
    return {"es": "No sé el límite de linealidad de tu cámara: estoy "
                  "midiendo con el mejor techo que tengo (la tarjeta "
                  "SATURATE o el recorte de la propia placa). Ponlo en "
                  "Ajustes → Perfil de cámara para que la regla se cumpla "
                  "de verdad.",
            "en": "I do not know your camera's linearity limit: I am "
                  "measuring with the best ceiling I have (the SATURATE card "
                  "or the plate's own clip). Set it in Settings → Camera "
                  "profile so the rule really holds."}


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
        sig = float(outliers.scaled_mad(resid))
        sig = max(sig, 0.02)          # the catalog noise floor (mag)
        # deviations are measured from the residuals' own median: a fit
        # pulled by an outlier must not condemn the honest majority
        worst = np.abs(resid - np.median(resid)) > _CLIP_SIGMA * sig
        if not worst.any() or int(keep.sum() - worst.sum()) < 4:
            break
        keep[np.where(keep)[0][worst]] = False
    resid = (cat - inst)[keep] - (zp + k * bv[keep])
    n = int(keep.sum())
    sig = float(outliers.scaled_mad(resid)) if n > 1 else 0.0
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
    noise = float(outliers.scaled_mad(diffs)) / math.sqrt(2.0)
    if noise <= 0:
        # a noiseless plate (synthetic fixtures are flat to the last bit):
        # fall back to the classic global estimator
        noise = float(np.nanstd(clean))
    if noise <= 0:
        return []
    # THE CANDIDATES, IN ONE PASS (2026-10-07). This used to be a Python loop
    # over every pixel of the cutout (1369 iterations on the 45 px window the
    # centroid's deblending uses, measured at 4.7 ms) with a slice and a ring
    # median per local maximum, and on noise it spent all of that to find
    # nothing. The test is the same one: a pixel that is not lower than any of
    # its eight neighbours, with the plateau tie left to the upper-left pixel.
    core = clean[ring:h - ring, ring:w - ring]
    is_max = np.ones(core.shape, dtype=bool)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            is_max &= core >= clean[ring + dy:h - ring + dy,
                                    ring + dx:w - ring + dx]
    is_max &= core != clean[ring:h - ring, ring - 1:w - ring - 1]
    is_max &= core != clean[ring - 1:h - ring - 1, ring:w - ring]
    ys, xs = np.nonzero(is_max)
    if ys.size == 0:
        return []
    # the local sky of every candidate at once: the SAME ring as before (the
    # top and bottom rows and the two side columns), gathered for all of them
    # and medianed along the second axis
    offsets = []
    for dx in range(-ring, ring + 1):
        offsets.append((-ring, dx))
        offsets.append((ring, dx))
    for dy in range(-ring + 1, ring):
        offsets.append((dy, -ring))
        offsets.append((dy, ring))
    yy = ring + ys
    xx = ring + xs
    ring_vals = np.stack([clean[yy + dy, xx + dx] for dy, dx in offsets],
                         axis=1)
    sig = (core[ys, xs] - np.median(ring_vals, axis=1)) / noise
    keep = np.nonzero(sig >= k)[0]
    if keep.size == 0:
        return []
    # the min_sep dedup runs in RASTER order, which is the order the old loop
    # visited the pixels in: the result of a tie must not depend on how the
    # candidates were found
    keep = keep[np.lexsort((xs[keep], ys[keep]))]
    out = []
    for i in keep:
        y, x = int(ys[i]) + ring, int(xs[i]) + ring
        if any((px - x) ** 2 + (py - y) ** 2 < min_sep ** 2
               for px, py, _p, _s in out):
            continue
        out.append((float(x), float(y), float(clean[y, x]), float(sig[i])))
    out.sort(key=lambda s: s[3], reverse=True)
    return [(x, y, pk) for x, y, pk, _s in out[:max_sources]]


def lock_local_peak(data, x, y, max_dist=4.0, k=4.0):
    # The significant local peak nearest to the clicked pixel: the right
    # seed for the centroid. A moment estimator drags toward the brightest
    # wing inside its window (a neighbour star, a galaxy core); the matched
    # filter can only refine around its seed, so the seed must be the
    # source the observer MEANT, not the brightest thing nearby.
    #
    # The source finder runs with a small separation here (3 px) on
    # purpose: this is not building a catalogue, it is answering "which
    # source is under the cursor", and a star 6 px from a brighter one used
    # to disappear under the catalogue rule (min_sep 6), leaving the
    # centroid to work from the raw click and, worse, blind to the
    # neighbour it should be protecting itself from.
    # @args: data - 2D array, x, y - the clicked pixel,
    #        max_dist - how far a peak may be to count as "under the click"
    # @return: (px, py) of the nearest local source, or None
    if data is None or data.size == 0:
        return None
    half = int(max_dist) + 7
    win = cutout_window(data, x, y, half)
    if win is None:
        return None
    y0, y1, x0, x1 = win
    best, best_d = None, max_dist ** 2
    for px, py, _pk in local_sources(data[y0:y1, x0:x1], k=k, min_sep=3):
        d = (px + x0 - x) ** 2 + (py + y0 - y) ** 2
        if d < best_d:
            best, best_d = (px + x0, py + y0), d
    return best


def local_neighbours(data, x, y, seed, reach=12.0, k=4.0,
                     psf_frac=0.15):
    # The OTHER significant sources that share the window of a star, with
    # the distance to the star's own seed.
    #
    # The centroid needs them for two different reasons, and both come
    # from the Photometrica tool of our group:
    #
    #   * a bright neighbour inside the correlation window borrows light
    #     from the star and pulls the fit towards itself, so the WINDOW is
    #     clamped by how close the neighbour is;
    #   * and the pixels that sit closer to the neighbour than to the star
    #     belong to the neighbour: they are masked out, the plain Voronoi
    #     split between two stars.
    #
    # Only what LOOKS LIKE A STAR counts as a neighbour, and that detail
    # is theirs too: a hot pixel or a cosmic ray is a spike, not a source,
    # and treating it as a neighbour would cut the window in half for
    # nothing (measured on the real V0526 Per series: the defence with
    # spikes counted as neighbours cost 0.0026 of correlation for no gain;
    # with the test below it costs nothing and still saves the two cases
    # it is for). A real point spread function spreads: its neighbours
    # hold a fair share of its light, a spike's neighbours do not.
    #
    # @args: data - 2D array, x, y - the clicked pixel, seed - the locked
    #        peak (px, py), reach - how far to look for neighbours,
    #        k - significance for the source finder, psf_frac - share of
    #        the peak that its neighbours must hold for it to be a star
    # @return: [(nx, ny, distance), ...] sorted by distance (nearest first)
    if data is None or seed is None:
        return []
    sx, sy = seed
    half = int(reach) + 7
    win = cutout_window(data, sx, sy, half)
    if win is None:
        return []
    y0, y1, x0, x1 = win
    sub = np.asarray(data[y0:y1, x0:x1], dtype=np.float64)
    background = float(np.median(sub))
    out = []
    for px, py, pk in local_sources(sub, k=k, min_sep=3):
        ax, ay = px + x0, py + y0
        d = math.hypot(ax - sx, ay - sy)
        if d <= 0.5 or d > reach:
            continue
        if not _looks_like_a_star(sub, ax - x0, ay - y0, background,
                                  psf_frac):
            continue
        out.append((float(ax), float(ay), float(d)))
    out.sort(key=lambda item: item[2])
    return out


def _looks_like_a_star(sub, px, py, background, psf_frac):
    # Is the pixel (px, py) the centre of a star, or an isolated spike?
    #
    # A star's core has neighbours carrying a good share of its light (the
    # wings); a hot pixel or a cosmic ray stands alone over the sky. The
    # seed's own finder uses the same test, so the two agree on what a
    # source is.
    # @args: sub - the cutout, px/py - the candidate (integer, in sub),
    #        background - the level it stands on, psf_frac - the share
    # @return: True when it has wings
    h, w = sub.shape
    ix, iy = int(round(px)), int(round(py))
    peak = float(sub[iy, ix]) - float(background)
    if peak <= 0.0:
        return False
    total, count = 0.0, 0
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            ny, nx = iy + dy, ix + dx
            if not (0 <= ny < h and 0 <= nx < w):
                continue
            total += float(sub[ny, nx]) - float(background)
            count += 1
    if count == 0:
        return False
    return (total / count) >= psf_frac * peak


def _core_cap(resid, sx, sy, x0, y0):
    # The brightest value of the 3x3 around the star's centre: no pixel of
    # a real point spread function can carry more light than its own core,
    # so anything above it is a hot pixel or a cosmic ray, and letting it
    # through would drag the centroid (the Gaussian template has weight
    # out there, the spike does not).
    # @args: resid - the sky-subtracted cutout, sx/sy - the seed (float
    #        pixels), x0/y0 - the cutout's origin
    # @return: the cap in ADU (>= 0)
    h, w = resid.shape
    cx = int(round(sx)) - x0
    cy = int(round(sy)) - y0
    box = resid[max(0, cy - 1):cy + 2, max(0, cx - 1):cx + 2]
    if box.size == 0:
        return float(np.nanmax(resid))
    return max(0.0, float(np.nanmax(box)))


def gaussian_centroid(data, x, y, fwhm=None, sky_pp=None, robust=True):
    # The precision centroid: matched-filter correlation of the
    # sky-subtracted cutout with a gaussian template of the measured
    # seeing, on a 0.1 px grid, with parabolic refinement of the
    # correlation surface (~0.01 px). With a fixed sigma this is the
    # optimal estimator in white noise, and the one that does not wander
    # on faint sources. The observer's point is kept (with the bilingual
    # reason) when the fit is too weak to trust: below SNR ~4 there is
    # no centroid worth the name, and pretending otherwise is worse.
    #
    # Two defences are ported from our group's Photometrica tool, because
    # an optimal estimator is only optimal when the data is what it
    # thinks it is:
    #
    #   * DEBLENDING: if another significant source shares the window, the
    #     window shrinks so its core stays out, and the pixels closer to
    #     it than to us are masked out;
    #   * the CORE CAP: a hot pixel or a cosmic ray inside the aperture is
    #     clipped at the star's own core value, because no real point
    #     spread function carries more light than its centre.
    #
    # @args: data - 2D array, x, y - starting pixel, fwhm - seeing in px
    #        (estimated from the cutout when None), sky_pp - local sky
    #        (cutout edge median when None), robust - apply the two
    #        defences above (False reproduces the historical behaviour)
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
    # the neighbours whose light could reach our window (photometry,
    # phase A): they shrink it, and they take their own pixels back below.
    # The reach is generous on purpose (two and a half windows): a
    # neighbour can pull a centroid from well outside the aperture through
    # its wing, which is the very case being defended against.
    neighbours = local_neighbours(data, x, y, seed,
                                  reach=max(6.0, 2.5 * half)) \
        if robust and seed is not None else []
    window = half
    if neighbours:
        # keep the neighbour's core and its bright wing out of the window:
        # half of the distance is inside our own star for any sane PSF
        window = int(max(3, min(half, math.floor(0.5 * neighbours[0][2]))))
    win = cutout_window(data, sx, sy, window)
    if win is None:
        return {"x": float(x), "y": float(y), "ok": False,
                "moved": False, "snr": None,
                "reason": {"es": "sin píxeles utilizables",
                           "en": "no usable pixels"}}
    y0, y1, x0, x1 = win
    sub = np.asarray(data[y0:y1, x0:x1], dtype=np.float64)
    if not np.any(np.isfinite(sub)):
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
    if robust:
        # the core cap: nothing inside a real point spread function is
        # brighter than its centre, so a spike above it is not starlight
        cap = _core_cap(resid, sx, sy, x0, y0)
        if cap > 0.0:
            resid = np.minimum(resid, cap)
    noise = max(float(outliers.scaled_mad(resid)), 1e-9)
    ys, xs = np.mgrid[y0:y1, x0:x1]
    # the deblending mask: a pixel closer to the neighbour than to us is
    # the neighbour's, and our template has no business integrating it
    weights = np.ones_like(resid)
    for nx, ny, _d in neighbours:
        closer = ((xs - nx) ** 2 + (ys - ny) ** 2) < \
            ((xs - sx) ** 2 + (ys - sy) ** 2)
        weights = np.where(closer, 0.0, weights)
    resid = resid * weights
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
        sigma = float(outliers.scaled_mad(resid))
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
    win = cutout_window(data, cx, cy, cut)
    sources = []
    if win is not None:
        y0, y1, x0, x1 = win
        sub = np.ascontiguousarray(data[y0:y1, x0:x1])
        sources = series.detect_sources(sub, k=5.0)
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
    targets: tuple = ()             # SEVERAL targets on the same plate, as
                                    # ((label, x, y) | (label, x, y, bv), ...).
                                    # The label travels with the curve; the
                                    # optional B-V is that object's own
                                    # colour, because the colour term is per
                                    # target even when the comps are shared.
                                    # Empty means "the one in target_xy"
    entries: list = field(default_factory=list)
    header: dict = field(default_factory=dict)
    wcs: object = None
    band: str = None                # the observer's pick, or None
    fallback_band: str = "V"
    radii: tuple = None             # (rap, rin, rout) or None for defaults
    fwhm: float = None              # measured seeing (px), for the centroid
    robust_centroid: bool = True    # the centroid's two defences against a
                                    # hot pixel and a close neighbour (see
                                    # gaussian_centroid); off reproduces the
                                    # historical behaviour
    centroid_mode: str = "gaussian"  # "gaussian" | "refined" | "raw" | "none"
                                    # for the TARGET (the comps always
                                    # centroid): "none" pins the hand-placed
                                    # centre, for a very faint SN
    sigmaclip: bool = True
    # Measure the target AND the comps with the matched filter instead of
    # the aperture, so the zero point comes from the SAME method as the
    # target. ON BY DEFAULT, and that is a measured decision: on real 2025 UR
    # data the filter reaches 1.55 to 1.63x the aperture's signal-to-noise,
    # its zero-point error is 2.6x smaller (0.035 against 0.092 mag) and the
    # brightness bias at low signal-to-noise is halved, for +3 % of runtime.
    # The observer can turn it off, and the aperture's value is kept beside
    # the reported one either way, for the audit.
    matched: bool = True
    sky_mode: str = "median"
    color: bool = False
    target_bv: float = 0.0
    require_catalog: bool = True    # False = relative mode: comps count
                                    # even without a catalog value
    linear_adu: float = None        # the camera profile's linearity limit
                                    # (per gain), or None when unset
    stack_scale: float = 1.0        # how many frames the plate ADDS: N for a
                                    # "sum" stack, 1 for a mean/median/sigma.
                                    # The ceilings are the SENSOR's, in the
                                    # units of ONE frame, so on a sum stack
                                    # they are multiplied by this before the
                                    # plate's own level is compared against
                                    # them. Measured on the author's own 2025
                                    # FG18 visit (sky 1552 ADU, camera
                                    # linearity 53000, 207 frames): the sum's
                                    # sky alone is 321 000 ADU, six times the
                                    # linearity, so every comparison star was
                                    # rejected and the run reported no
                                    # magnitude at all.
    # THE WORKING GAIN, resolved by the caller when it can (2026-10-08):
    # Ajustes -> the gain measured on the very frames -> the header. The
    # callers that walk that chain (the series engine, the Measure tab)
    # hand the result in here; a caller that hands in nothing falls back
    # to `site_gain` and only then to the header. `gain_source` is
    # "settings" | "frames" | "header" and is what the panel prints.
    gain: float = None
    ron: float = None
    gain_source: str = None
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
    # ...or each comp on its OWN small image: a list parallel to `entries`,
    # each (image, x, y) in that image's own pixels, or None. The track &
    # stack builds one small stack per comp instead of stacking the whole
    # frame a second time (measured on 2025 UR: 74 s for the full star
    # stack against a second for the eight windows, same zero point), so
    # the number does not change, only what it costs.
    comp_images: list = None


@dataclass
class PlateResult:
    # The recipe's output: the target, its comps, the zero point, the
    # honest error budget and the check verdict. Never raises.
    ok: bool = False
    reason: dict = None
    target: dict = None
    targets: list = field(default_factory=list)   # every target of the plate,
                                    # each {"label", "target", "col", "row",
                                    # "bv", "ok", "reason", "inst_t", "zp",
                                    # "mag", "err_internal", "err_total",
                                    # "scint", "check"}. The scalar fields
                                    # above mirror the FIRST one, which is
                                    # what a single-target caller reads
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
    gain_source: str = None         # "settings" | "frames" | "header" | None
    # WHAT ACTUALLY MEASURED, and not what the recipe asked for: the filter
    # needs a seeing, and with no FWHM (the comps could not be measured on
    # this stack) the aperture measures instead. A caller that reported the
    # recipe's flag said "measured with the matched filter" while the
    # aperture had done it: the run has to be able to say the truth.
    matched_used: bool = False


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
    if (used.get("flux") or 0.0) <= 0.0:
        # a magnitude needs a POSITIVE flux: the check star goes through the
        # same engine as everything else, and an engine that reports ok with
        # a non-positive flux (the matched filter can, see _matched_fail)
        # must not reach the logarithm
        return None
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
    # THE MEASUREMENT ITSELF, chosen in ONE place (P3 of the SNR campaign).
    # The aperture is the proven path; the matched filter is the one P2
    # measured at 1.55-1.63x its SNR on real data and P4c measured less
    # biased at low SNR. Both share the centroid, the sky and the sigma, so a
    # plate measured one way and a plate measured the other stay comparable,
    # and the ZERO POINT is measured with the same method as the target:
    # mixing them (the target with the filter, the comps with the aperture)
    # would put the difference between the two methods straight into the
    # magnitude.
    _psf = None
    if getattr(cfg, "matched", False) and fwhm:
        # the Gaussian from the measured seeing: P2 measured that on the real
        # 2025 UR stack it agrees with the empirical profile to the last
        # digit, and it does not drag the comps' noise into the shape
        _psf = gaussian_psf(float(fwhm))

    def _one(img, x, y, **kw):
        # @args: img/x/y - where to measure, kw - the aperture, centroid and
        #        sky knobs the call sites pass
        # @return: the measurement dict, from whichever method was asked for
        if _psf is None:
            return measure_point(img, x, y, **kw)
        return measure_matched(img, x, y, _psf, **kw)
    # The ceilings are the SENSOR's, in the units of ONE frame; a stack that
    # ADDS its frames ("sum") has N times the level. A pixel saturates when
    # the FRAME it came from did, and on a sum stack the per-frame equivalent
    # of a plate value V is V/N, so the ceilings are multiplied by the scale
    # and the same test (plate value against ceiling) answers the same
    # question. Without this, a sum stack's own sky (measured on the author's
    # own 2025 FG18 visit: 1552 ADU per frame, 207 frames, so 321 000 ADU in
    # the sum) sat six times above the camera's linearity of 53 000 and EVERY
    # comparison star was thrown out: the run reported no magnitude at all.
    stack_scale = max(1.0, float(getattr(cfg, "stack_scale", 1.0) or 1.0))
    # THE TWO CEILINGS, from their one home (ADR-066). The per-run recipe's
    # linearity and the site's saturation setting travel in the PlateConfig;
    # the header's SATURATE card still wins, as it always did.
    sat, lin = star_ceilings(cfg.header, None, linear_adu=cfg.linear_adu,
                             saturate=cfg.site_saturate)
    sat = (sat * stack_scale) if sat is not None else None
    # the camera profile's linearity limit is in plate ADU; it does not
    # apply to a resampled/downsampled work frame (host subtraction)
    lin = lin if scale == 1.0 else None
    lin = (lin * stack_scale) if lin is not None else None
    res = PlateResult(radii=radii, fwhm=fwhm, sky_mode=cfg.sky_mode,
                      sigma_clip=cfg.sigmaclip, matched_used=_psf is not None)
    # ---- the targets ------------------------------------------------
    # One target is the historical case; several is the campaign pass, and
    # the whole point is what is NOT repeated: the comparison stars are
    # measured ONCE per plate and every target hangs from that same
    # measurement. A project is one object and its curve is its own, so
    # "several targets" never means several curves inside one project: it
    # means one pass over the frames feeding several projects.
    targets = [tuple(t) for t in (cfg.targets or ())]
    if not targets:
        targets = [("", cfg.target_xy[0], cfg.target_xy[1])]
    measured = []
    for entry in targets:
        label, tx, ty = entry[0], float(entry[1]), float(entry[2])
        bv = (float(entry[3]) if len(entry) > 3 and entry[3] is not None
              else cfg.target_bv)
        if cfg.comp_image is not None:
            # H2b: the target on one image, the comps on another. When the
            # two SHARE the plate scale (scale == 1: the object's stack and
            # the star stack of the same frames) the camera's ceilings
            # apply to the target too; on a resampled difference image they
            # do not, because those ADU are not the sensor's.
            target = _one(
                image, tx / scale, ty / scale,
                r_ap=radii[0] / scale, r_ann_in=radii[1] / scale,
                r_ann_out=radii[2] / scale, sigma_clip=cfg.sigmaclip,
                sat_adu=(sat if scale == 1.0 else None),
                linear_adu=(lin if scale == 1.0 else None),
                sky_mode=cfg.sky_mode,
                centroid_mode=cfg.centroid_mode,
                fwhm=(fwhm / scale if fwhm else None))
        else:
            target = _one(
                image, tx, ty, r_ap=radii[0], r_ann_in=radii[1],
                r_ann_out=radii[2], sigma_clip=cfg.sigmaclip, sat_adu=sat,
                linear_adu=lin, sky_mode=cfg.sky_mode,
                centroid_mode=cfg.centroid_mode, fwhm=fwhm,
                robust=cfg.robust_centroid)
        mx, my = target["x"], target["y"]
        if cfg.comp_image is not None:
            mx, my = mx * scale, my * scale
        # A MEASUREMENT IS A POSITIVE FLUX, whatever the engine says. The
        # matched filter used to report ok=True with a negative one (see
        # _matched_fail), and everything below assumes the opposite: the
        # logarithm of the instrumental magnitude, the CCD error budget, the
        # zero point. It is decided ONCE, here, so no later line has to
        # wonder, and a target the engine could not really measure comes back
        # as "unmeasurable" with its reason instead of as a magnitude of a
        # negative number.
        ok = bool(target["ok"]) and (target.get("flux") or 0.0) > 0.0
        measured.append({
            "label": label, "target": target, "col": mx, "row": my,
            "bv": bv, "ok": ok,
            "reason": target.get("reason"),
            "inst_t": (-2.5 * math.log10(target["flux"]) if ok else None),
            # calibrated further down; every key exists from here so a
            # caller writing a curve always reads the same shape
            "zp": None, "mag": None, "err_internal": None,
            "err_total": None, "scint": None, "check": None})
    res.targets = measured
    # the scalar fields describe the FIRST target: a caller that asked for
    # one keeps reading exactly what it always read
    first = measured[0]
    res.target, res.col, res.row = first["target"], first["col"], first["row"]
    res.inst_t = first["inst_t"]
    if not any(m["ok"] for m in measured):
        # nothing could be measured: there is no light to calibrate
        res.reason = first.get("reason")
        return res
    res.ok = True
    band, bands = pick_band(cfg.entries, cfg.band, cfg.fallback_band)
    res.band, res.bands_avail = band, bands
    # the comps on the same plate (or the paired work frame); the ceiling
    # applies to them too: a clipped comp poisons the zero point
    inst, cat, bvs, used_entries = [], [], [], []
    skipped = {}
    for j, e in enumerate(cfg.entries):
        star = e["star"]
        own = (cfg.comp_images[j]
               if cfg.comp_images and j < len(cfg.comp_images) else None)
        if own is not None:
            # the comp on its own small stack, already aligned on the
            # stars: the aperture and the annulus fit inside it by
            # construction (the caller sized the window for them)
            r = _one(
                own[0], own[1], own[2], r_ap=radii[0], r_ann_in=radii[1],
                r_ann_out=radii[2], sigma_clip=cfg.sigmaclip, sat_adu=sat,
                linear_adu=lin, sky_mode=cfg.sky_mode, fwhm=fwhm,
                robust=cfg.robust_centroid)
        else:
            try:
                ccol, crow = cfg.wcs.sky_to_pixel(star["ra"], star["dec"])
            except Exception:
                skipped["off"] = skipped.get("off", 0) + 1
                continue
            if cfg.comp_image is not None:
                r = _one(
                    cfg.comp_image, ccol / scale, crow / scale,
                    r_ap=radii[0] / scale, r_ann_in=radii[1] / scale,
                    r_ann_out=radii[2] / scale, sigma_clip=cfg.sigmaclip,
                    sat_adu=None, sky_mode=cfg.sky_mode,
                    fwhm=(fwhm / scale if fwhm else None))
            else:
                r = _one(image, ccol, crow, r_ap=radii[0],
                                  r_ann_in=radii[1], r_ann_out=radii[2],
                                  sigma_clip=cfg.sigmaclip, sat_adu=sat,
                                  linear_adu=lin, sky_mode=cfg.sky_mode,
                                  fwhm=fwhm,
                                  robust=cfg.robust_centroid)
        value, derived = band_of(star, band)
        if not r["ok"] or (r.get("flux") or 0.0) <= 0.0:
            # a comparison star that cannot give a positive flux cannot
            # calibrate anything: it is skipped like a clipped one, with its
            # reason, instead of reaching the logarithm below
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
    # error budget: CCD equation (gain from header or Ajustes) + the
    # zero point + scintillation + the flat residual + the colour term.
    # The gain and the comps are the frame's, so they are resolved once;
    # the zero point is fitted per target only because the colour term
    # hangs from the target's own B-V.
    inst_header = header_instrument(cfg.header)
    # THE WORKING GAIN, in the order the observer approved (2026-10-08):
    # what the caller resolved wins (it already walked Ajustes -> measured
    # on the frames -> header); a caller that resolved nothing falls back
    # to its Ajustes value and only then to the header, because the header
    # can carry the camera's gain SETTING or a placeholder. Measured on
    # the author's own QHY42Pro frames: SharpCap wrote EGAIN = 1.0 while
    # the real conversion gain was 0.11 e-/ADU, and trusting the card
    # under-reported every error bar by a factor of three.
    if cfg.gain is not None:
        gain, gain_source = cfg.gain, cfg.gain_source
    elif cfg.site_gain is not None:
        gain, gain_source = cfg.site_gain, "settings"
    elif inst_header["gain"] is not None:
        gain, gain_source = inst_header["gain"], "header"
    else:
        gain, gain_source = None, None
    ron = cfg.ron if cfg.ron is not None else (
        cfg.site_ron if cfg.site_ron is not None else inst_header["ron"])
    res.gain = gain
    res.gain_source = gain_source
    for m in measured:
        if not m["ok"]:
            continue
        if cfg.color:
            zp = calibrate_with_color(inst, cat, bvs, target_bv=m["bv"])
        else:
            zp = calibrate_zero_point(inst, cat)
        zp.setdefault("color_used", False)   # the plain path carries none
        m["zp"] = zp
        target = m["target"]
        flux_err = ccd_flux_error(target["flux"], target["sky_pp"],
                                  target["n_pix"], gain=gain, ron=ron,
                                  exptime=inst_header["exptime"],
                                  dark_e_s=cfg.site_dark,
                                  n_sky=target.get("n_sky"))
        m["err_internal"] = mag_error(target["flux"], flux_err)
        m["scint"] = _plate_scintillation(cfg, m["col"], m["row"],
                                          inst_header["exptime"])
        m["err_total"] = combine_errors(
            m["err_internal"], zp["zp_err"], m["scint"], cfg.site_flat,
            zp.get("target_color_err"))
        zp_for_mag = zp["zp"]
        if zp.get("color_used") and zp["k"] is not None:
            # the fit's zero point is at B-V = 0: move the target onto it
            zp_for_mag = zp["zp"] + zp["k"] * m["bv"]
        m["mag"], _e = calibrated_mag(m["inst_t"], zp_for_mag)
        m["check"] = _check_verdict(cfg.entries, used_entries, band, zp,
                                    m["err_total"])
    # the first target's own numbers are the plate's numbers (legacy view)
    if first["ok"]:
        res.zp = first.get("zp")
        res.err_internal = first.get("err_internal")
        res.scint = first.get("scint")
        res.err_total = first.get("err_total")
        res.mag = first.get("mag")
        res.check = first.get("check")
    return res
