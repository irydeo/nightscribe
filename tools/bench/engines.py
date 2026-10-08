############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Photometry engine benchmark: the engines
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Two photometry engines behind ONE interface, for the migration study.

This is bench code: it is not imported by the app and it is not shipped.
It exists to answer one question with numbers instead of opinions: would a
photutils-based engine measure better (or only faster) than ours?

The interface is deliberately the exact signature `photometry.measure_plate`
uses, because `measure_plate` calls `photometry.measure_point(...)` as a
module-global name: replacing that name is the whole seam, and the series
engine then runs end to end on whichever engine is installed (see
`use_engine`).

Four engines, so a difference can be attributed to a PIECE and not to the
whole swap:

    ours          our centroid + our aperture/sky   (the baseline)
    ours_pu_cen   photutils centroid + our aperture/sky
    pu_cen_ours   our centroid + photutils aperture/sky
    pu            photutils centroid + photutils aperture/sky

plus two cheap references:

    ours_refined  our one-pass moment centroid (the cheap path we already
                  have, `centroid_mode="refined"`)
    ours_none     no centroid at all: measure exactly where the click landed
                  (the floor any centroid has to beat)

The guards are OURS in every engine, on purpose: photutils knows nothing
about the camera's saturation or its linearity limit (ADR-066), and the
bilingual reasons are the app's contract. photutils gives the number; the
judgement stays here.
"""

import math

import numpy as np
from astropy.stats import SigmaClip
from photutils.aperture import (ApertureStats, CircularAnnulus,
                                CircularAperture, aperture_photometry)
from photutils.centroids import centroid_2dg, centroid_quadratic

from nightscribe.core import photometry

# The original function, bound at import time: `use_engine` replaces the
# module global, and an engine that called `photometry.measure_point` by
# name would then call itself forever.
ORIGINAL = photometry.measure_point

# The same sky clip our engine uses (photometry.SIG_LEVEL/SIG_ITERS): the
# comparison has to differ in the ESTIMATOR, not in the rejection.
_CLIP = SigmaClip(sigma=photometry.SIG_LEVEL, maxiters=photometry.SIG_ITERS)


def _fail(es, en, **kw):
    # Same shape as photometry._fail, and that includes the KEYS THAT ARE
    # None: measure_plate reads target["x"] unconditionally, so a failure
    # that omits "x" is a KeyError in the middle of a series and not a
    # skipped star. The first run of this bench found exactly that.
    out = {"x": None, "y": None, "flux": None, "sky_pp": None, "peak": None,
           "n_pix": 0, "saturated": False, "ok": False,
           "reason": {"es": es, "en": en}}
    out.update(kw)
    return out


# photutils works on the WHOLE frame and wants float64, while our engine
# converts only the patch a star needs. A 2048x2048 int16 frame copied to
# float64 is 32 MB, and doing that per star per frame is 11 copies of 32 MB
# for a series frame: the conversion, not the arithmetic, becomes the cost.
# One entry of cache, keyed on the array's identity and holding a strong
# reference (so the id cannot be recycled), gives the engine what the app
# would give it anyway: the frame converted ONCE.
_FLOAT_CACHE = {}


def _as_float(data):
    # @args: data - any 2D array
    # @return: the float64 view of it, converted once per frame
    key = id(data)
    ent = _FLOAT_CACHE.get(key)
    if ent is not None and ent[0] is data:
        return ent[1]
    out = np.asarray(data, dtype=np.float64)
    _FLOAT_CACHE.clear()
    _FLOAT_CACHE[key] = (data, out)
    return out


def _ring(data, x, y, half):
    # @return: the (y0, y1, x0, x1) window around (x, y), clipped to the frame
    h, w = data.shape
    y0 = max(0, int(round(y)) - half)
    y1 = min(h, int(round(y)) + half + 1)
    x0 = max(0, int(round(x)) - half)
    x1 = min(w, int(round(x)) + half + 1)
    return y0, y1, x0, x1


def _local_sky(data, x, y, half):
    # The cutout's border median, exactly as gaussian_centroid does it: the
    # star owns the middle, not the frame.
    y0, y1, x0, x1 = _ring(data, x, y, half)
    sub = np.asarray(data[y0:y1, x0:x1], dtype=np.float64)
    if sub.size == 0:
        return 0.0
    ring = np.concatenate([sub[0, :], sub[-1, :], sub[:, 0], sub[:, -1]])
    ring = ring[np.isfinite(ring)]
    return float(np.median(ring)) if ring.size else 0.0


def pu_centroid(data, x, y, fwhm=None, func="2dg", robust=True):
    # photutils' centroid on a local cutout: the background is removed first
    # (both centroid_2dg and centroid_quadratic assume it is gone), and the
    # window is the same size ours uses, so the two see the same pixels.
    #
    # The runaway guard is ours: photutils happily returns a position a few
    # pixels away when the fit is unconstrained, and a series would follow it
    # off the star. `ok=False` means "keep the click", never a raise.
    # @args: data - 2D array, x, y - the click, fwhm - seeing in px,
    #        func - "2dg" (2D Gaussian fit) or "quadratic" (good on
    #        undersampled PSFs), robust - kept for signature parity
    # @return: (x, y, ok)
    h, w = data.shape
    sigma_psf = max((fwhm or 4.0) / 2.3548, 0.7)
    half = max(5, int(round(2.0 * sigma_psf)) + 1)
    y0, y1, x0, x1 = _ring(data, x, y, half)
    sub = np.asarray(data[y0:y1, x0:x1], dtype=np.float64)
    if sub.size == 0 or not np.any(np.isfinite(sub)):
        return float(x), float(y), False
    sky = _local_sky(data, x, y, half)
    resid = np.nan_to_num(sub - sky)
    try:
        if func == "quadratic":
            # the peak hint is NOT passed: photutils 3.0 deprecated xpeak/
            # ypeak (removed in 4.0) and it finds the brightest pixel itself,
            # which on a small cutout around the click is what we want
            cx, cy = centroid_quadratic(resid)
        else:
            cx, cy = centroid_2dg(resid)
        cx = float(cx) + x0
        cy = float(cy) + y0
    except Exception:
        return float(x), float(y), False
    if not (math.isfinite(cx) and math.isfinite(cy)):
        return float(x), float(y), False
    if abs(cx - x) > half or abs(cy - y) > half:
        return float(x), float(y), False
    return cx, cy, True


def _aperture_stats(data, x, y, r_ap, r_ann_in, r_ann_out, sigma_clip):
    # photutils does the two sums: the exact circle (analytic pixel overlap)
    # and the sigma-clipped annulus. Both in ONE place so every engine that
    # uses photutils' arithmetic reads the same numbers.
    # @return: (flux_sum, area, sky_pp, sigma_pp, peak)
    pos = [(float(x), float(y))]
    aper = CircularAperture(pos, r=float(r_ap))
    ann = CircularAnnulus(pos, r_in=float(r_ann_in), r_out=float(r_ann_out))
    clip = _CLIP if sigma_clip else None
    arr = _as_float(data)
    tbl = aperture_photometry(arr, aper, method="exact")
    total = float(np.atleast_1d(tbl["aperture_sum"])[0])
    area = float(np.atleast_1d(
        ApertureStats(arr, aper).sum_aper_area)[0].value)
    stats = ApertureStats(arr, ann, sigma_clip=clip)
    sky_pp = float(np.atleast_1d(stats.median)[0])
    sigma_pp = float(np.atleast_1d(stats.mad_std)[0])
    # the peak inside the aperture: our saturation test reads the brightest
    # pixel of the star, so it is measured the same way here
    y0, y1, x0, x1 = _ring(data, x, y, int(math.ceil(float(r_ap))) + 2)
    sub = np.asarray(data[y0:y1, x0:x1], dtype=np.float64)
    yy, xx = np.mgrid[y0:y1, x0:x1]
    inside = (xx - x) ** 2 + (yy - y) ** 2 <= float(r_ap) ** 2
    peak = float(np.nanmax(sub[inside])) if np.any(inside) else float("nan")
    return total, area, sky_pp, sigma_pp, peak


def measure_photutils(data, x, y, r_ap=photometry.R_AP,
                      r_ann_in=photometry.R_ANN_IN,
                      r_ann_out=photometry.R_ANN_OUT, sigma_clip=True,
                      sat_adu=None, linear_adu=None, sky_mode="median",
                      centroid_mode="gaussian", fwhm=None, robust=True,
                      centroid_func="2dg", centroid_from="pu"):
    # A whole measurement with photutils doing the arithmetic.
    #
    # @args: the exact signature of photometry.measure_point (so
    #        measure_plate can call it through the same seam), plus
    #        centroid_func - "2dg" | "quadratic", centroid_from - "pu"
    #        (photutils) or "ours" (our matched filter, to isolate the
    #        arithmetic alone)
    # @return: the same dict measure_point returns
    if data is None or data.size == 0:
        return _fail("no hay imagen cargada", "no image loaded")
    h, w = data.shape
    if not (0 <= x < w and 0 <= y < h):
        return _fail("el clic cae fuera del marco", "the click is out of frame")
    if min(x, y, w - x, h - y) < r_ann_out:
        return _fail("demasiado cerca del borde", "too close to the edge")
    cen_ok = None
    if centroid_mode == "none":
        cx, cy = float(x), float(y)
    elif centroid_from == "ours":
        cen = photometry.gaussian_centroid(data, x, y, fwhm=fwhm, robust=robust)
        cx, cy, cen_ok = float(cen["x"]), float(cen["y"]), bool(cen["ok"])
    else:
        cx, cy, cen_ok = pu_centroid(data, x, y, fwhm=fwhm,
                                     func=centroid_func, robust=robust)
    if sky_mode != "median":
        # the plane sky is ours only: photutils has no per-aperture tilted
        # plane. Measured as a median here, and the caller is told.
        pass
    total, area, sky_pp, sigma_pp, peak = _aperture_stats(
        data, cx, cy, r_ap, r_ann_in, r_ann_out, sigma_clip)
    flux = total - sky_pp * area
    n_pix = area
    frame_max = float(np.nanmax(data))
    saturated = sat_adu is not None and frame_max > 0.0 \
        and peak >= photometry.SAT_FRAC * float(sat_adu)
    if not saturated and frame_max > sky_pp:
        eps = 1e-6 * max(1.0, frame_max)
        y0, y1, x0, x1 = _ring(data, cx, cy, int(math.ceil(r_ann_in)) + 2)
        sub = np.asarray(data[y0:y1, x0:x1], dtype=np.float64)
        yy, xx = np.mgrid[y0:y1, x0:x1]
        inside = (xx - cx) ** 2 + (yy - cy) ** 2 <= float(r_ann_in) ** 2
        plateau = int(np.count_nonzero(inside & (sub > frame_max - eps)))
        saturated = plateau >= photometry._CLIP_MIN_PIXELS
    if not saturated and sat_adu is None and linear_adu is None:
        ceiling = photometry.frame_ceiling(data, frame_max)
        if ceiling is not None \
                and peak >= photometry._INFERRED_CEILING_FRAC * ceiling:
            out = _fail(f"comprimida: el pico llega al recorte de la placa "
                        f"(~{ceiling:.0f} ADU)",
                        f"clipped: the peak reaches the plate ceiling "
                        f"(~{ceiling:.0f} ADU)")
            out.update(x=cx, y=cy, sky_pp=sky_pp, peak=peak, n_pix=n_pix,
                       saturated=True)
            return out
    if saturated:
        out = _fail("saturada", "saturated")
        out.update(x=cx, y=cy, sky_pp=sky_pp, peak=peak, n_pix=n_pix,
                   saturated=True)
        return out
    if linear_adu is not None and frame_max > 0.0 \
            and peak >= photometry.SAT_FRAC * float(linear_adu):
        out = _fail("no lineal: el pico supera el límite de linealidad "
                    "de tu cámara",
                    "nonlinear: the peak is above your camera's linearity "
                    "limit")
        out.update(x=cx, y=cy, sky_pp=sky_pp, peak=peak, n_pix=n_pix,
                   nonlinear=True)
        return out
    if not math.isfinite(flux) or flux <= 0.0:
        out = _fail("sin señal medible", "no measurable signal")
        out.update(x=cx, y=cy, sky_pp=sky_pp, peak=peak, n_pix=n_pix)
        return out
    snr = None
    if sigma_pp and n_pix > 0:
        snr = float(flux) / (float(sigma_pp) * math.sqrt(float(n_pix)))
    return {"x": cx, "y": cy, "flux": flux, "sky_pp": sky_pp, "peak": peak,
            "n_pix": n_pix, "n_sky": None, "saturated": False, "ok": True,
            "reason": None, "cen_ok": cen_ok, "sigma_pp": sigma_pp, "snr": snr}


def measure_ours_pu_centroid(data, x, y, **kw):
    # Our arithmetic, photutils' centroid: the centroid is resolved first and
    # handed to our engine with centroid_mode="none", which uses the position
    # EXACTLY as given. That is the cleanest way to swap one piece alone: the
    # aperture, the sky and the error stay bit-for-bit ours.
    fwhm = kw.get("fwhm")
    func = kw.pop("centroid_func", "2dg")
    kw.pop("centroid_from", None)
    kw.pop("centroid_mode", None)     # ours is replaced by photutils here
    cx, cy, ok = pu_centroid(data, x, y, fwhm=fwhm, func=func)
    if not ok:
        # photutils could not say: fall back to our own centroid rather than
        # measuring on the click, so the engine is never worse for a reason
        # that belongs to the fallback and not to the estimator
        return ORIGINAL(data, x, y, **kw)
    out = ORIGINAL(data, cx, cy, centroid_mode="none", **kw)
    out["pu_centroid_ok"] = True
    return out


def measure_pu_centroid_ours_arith(data, x, y, **kw):
    # photutils' arithmetic, our centroid: `centroid_from="ours"`.
    return measure_photutils(data, x, y, centroid_from="ours", **kw)


ENGINES = {
    "ours": lambda data, x, y, **kw: ORIGINAL(data, x, y, **kw),
    "ours_norobust": lambda data, x, y, **kw: ORIGINAL(
        data, x, y, **dict(kw, robust=False)),
    "ours_refined": lambda data, x, y, **kw: ORIGINAL(
        data, x, y, centroid_mode="refined", **kw),
    "ours_none": lambda data, x, y, **kw: ORIGINAL(
        data, x, y, centroid_mode="none", **kw),
    "ours_pu_cen": measure_ours_pu_centroid,
    "pu_cen_ours": measure_pu_centroid_ours_arith,
    "pu": measure_photutils,
}

ENGINE_LABELS = {
    "ours": "nuestro centroide + nuestra apertura/cielo",
    "ours_refined": "centroide de momentos (barato) + nuestra apertura",
    "ours_none": "sin centroide (se mide donde se pulsa)",
    "ours_pu_cen": "centroide photutils + nuestra apertura/cielo",
    "pu_cen_ours": "nuestro centroide + apertura/cielo photutils",
    "pu": "centroide + apertura/cielo photutils",
}


class _UseEngine:
    # A context manager that installs an engine in photometry.measure_point,
    # so `measure_plate` (and therefore the whole series engine) runs on it
    # without a single line of production code changing.
    #
    # @args: name - a key of ENGINES, extra - kwargs for that engine
    def __init__(self, name, **extra):
        self.name = name
        self.extra = extra
        self._saved = None

    def _fn(self):
        base = ENGINES[self.name]
        if not self.extra:
            return base

        def wrapped(data, x, y, **kw):
            kw.update(self.extra)
            return base(data, x, y, **kw)
        return wrapped

    def __enter__(self):
        self._saved = photometry.measure_point
        photometry.measure_point = self._fn()
        return self

    def __exit__(self, *exc):
        photometry.measure_point = self._saved
        return False


def use_engine(name, **extra):
    # @args: name - a key of ENGINES, extra - engine kwargs
    # @return: the context manager that installs it
    if name not in ENGINES:
        raise KeyError(f"unknown engine {name!r}; known: {sorted(ENGINES)}")
    return _UseEngine(name, **extra)


def measure_with(name, data, x, y, **kw):
    # One measurement through a named engine, without touching the module
    # global: the A/B on single measurements does not need the seam.
    # @return: the measurement dict
    if name not in ENGINES:
        raise KeyError(f"unknown engine {name!r}")
    return ENGINES[name](data, x, y, **kw)
