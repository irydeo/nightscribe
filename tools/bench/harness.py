############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Photometry engine benchmark: shared harness
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Shared pieces of the engine benchmark: datasets, seeing, empty sky.

Bench code: not imported by the app, not shipped. Everything here is
read-only with respect to the user's data (frames are opened, never
written), and the injection works on an in-memory copy.
"""

import glob
import math
import os

import numpy as np

from nightscribe.core import fits_io, photometry, register, wcs as wcs_mod

# The local corpus, as measured 2026-10-07 (see the plan). Each entry says
# whether the header carries a real CD matrix (PY9, HatP32) or only
# CRVAL+SECPIX (the rest), in which case the benchmark builds the TAN WCS it
# needs from the header's own plate scale. That is legitimate here and only
# here: the comps' sky coordinates are generated FROM pixel positions with
# that same WCS, so the round trip is exact whatever the rotation convention
# is. It would NOT be legitimate to publish an astrometric position with it.
DATASETS = {
    "2025FG18": {
        "glob": "/home/boreal/Develop/astronomy/dataset/2025FG18/20250331/*.fits",
        "kind": "neo", "real_wcs": False,
    },
    "2025HL5": {
        "glob": "/home/boreal/Develop/astronomy/dataset/2025HL5/20250427/*.fits",
        "kind": "neo", "real_wcs": False,
    },
    "2025UR": {
        "glob": "/home/boreal/Develop/astronomy/dataset/2025UR/20251018/*.fits",
        "kind": "neo", "real_wcs": False,
    },
    "2026PY9": {
        "glob": "/home/boreal/Develop/astronomy/dataset/2026PY9/20260816/*.fits",
        "kind": "neo", "real_wcs": True,
    },
    "HatP32": {
        "glob": ("/home/boreal/Develop/astronomy/dataset/"
                 "EXOTIC_sampledata-1.0.0/HatP32Dec202017/*.FITS"),
        "kind": "transit", "real_wcs": True,
    },
}


def dataset_paths(name, limit=None):
    # @args: name - a key of DATASETS, limit - keep only the first N frames
    # @return: the sorted list of FITS paths
    paths = sorted(glob.glob(DATASETS[name]["glob"]))
    return paths[:limit] if limit else paths


def load(path):
    # @return: (header, data) from the app's own reader
    return fits_io.read_fits(path)


def build_wcs(header, name):
    # The WCS the series engine needs to project the comps. A real CD matrix
    # is used when the header has one; otherwise a TAN WCS is built from the
    # header's own CRVAL and plate scale (see DATASETS).
    # @return: a wcs_mod.Wcs, or None
    w = wcs_mod.Wcs.from_header(header)
    if w is not None:
        return w
    scale = header.get("SECPIX1") or header.get("SCALE")
    if not scale:
        return None
    s = float(scale) / 3600.0
    naxis1 = int(header.get("NAXIS1", 0))
    naxis2 = int(header.get("NAXIS2", 0))
    if naxis1 <= 0 or naxis2 <= 0:
        return None
    crpix1 = naxis1 / 2.0 + 0.5
    crpix2 = naxis2 / 2.0 + 0.5
    return wcs_mod.Wcs(float(header["CRVAL1"]), float(header["CRVAL2"]),
                       crpix1, crpix2, [[-s, 0.0], [0.0, s]], naxis1, naxis2)


def detect_sources(data, nmax=200):
    # The benchmark's source list: the app's own detector on the app's own
    # source image (cheap and already tested). Positions in pixels, brightest
    # first, with the peak over the local sky.
    # @return: (N, 3) array of [x, y, peak]
    return register.detect_stars(register.source_image(data), nmax=nmax)


def saturation_hint(header, data):
    # The ceiling the guards should use on THIS plate: the header's own
    # SATURATE card, and failing that the plate's inferred clip
    # (photometry.frame_ceiling: many pixels pinned at the frame maximum are
    # a clip level, not one star's apex).
    #
    # It is not a detail: the EXOTIC sample frames are 12 bit and clip at
    # 4095, so judging them with the settings' 53000 ADU would call every
    # saturated star a good comparison, and the first run of this bench
    # picked exactly those as the ensemble.
    # @return: the ceiling in ADU, or None when the plate says nothing
    if header:
        for key in ("SATURATE", "SATLEVEL"):
            try:
                val = header.get(key)
            except Exception:                              # noqa: BLE001
                val = None
            if val:
                return float(val)
    try:
        return photometry.frame_ceiling(data)
    except Exception:                                      # noqa: BLE001
        return None


def seeing_of(data, sources, n=6):
    # The frame's seeing, measured on the brightest sources with the app's
    # own estimator (radial profile, with the moment fallback). Used both to
    # inject a realistic PSF and to size the aperture: the same number for
    # every engine.
    # @return: FWHM in px
    spots = [(float(s[0]), float(s[1])) for s in sources[:n]]
    fwhm = photometry.estimate_fwhm(data, spots) if spots else None
    return float(fwhm) if fwhm else 4.0


def empty_spots(data, sources, n, min_sep=25.0, margin=25.0, seed=0):
    # Positions where there is nothing: far from every detected source and
    # from the frame edge. Injecting a star on top of a real one would
    # measure the pair, not the pipeline.
    # @args: n - how many, min_sep - px away from any source, margin - px
    #        from the edge
    # @return: [(x, y), ...]
    h, w = data.shape
    rng = np.random.default_rng(seed)
    pts = []
    tries = 0
    while len(pts) < n and tries < 4000:
        tries += 1
        x = float(rng.uniform(margin, w - margin))
        y = float(rng.uniform(margin, h - margin))
        if sources is not None and len(sources):
            d = np.hypot(sources[:, 0] - x, sources[:, 1] - y)
            if float(np.min(d)) < min_sep:
                continue
        if any(math.hypot(px - x, py - y) < min_sep for px, py in pts):
            continue
        pts.append((x, y))
    return pts


def inject(data, x, y, flux, fwhm, seed=0):
    # A star of a KNOWN total flux, at a KNOWN place, on a copy of the real
    # frame: the same Gaussian the app's own injection module uses, with the
    # frame's own seeing (a source sharper than the night's PSF would measure
    # the bench and not the pipeline).
    #
    # The sub-pixel phase is drawn at random on purpose: two sources of the
    # same flux must not land on the same fraction of a pixel every time, or
    # the measurement would be measuring that fraction.
    # @args: data - the real frame (not modified), x/y - where, flux - total
    #        ADU above the sky, fwhm - the session's seeing, seed - phase
    # @return: (new_data, x_true, y_true)
    rng = np.random.default_rng(seed)
    fx = float(rng.uniform(-0.5, 0.5))
    fy = float(rng.uniform(-0.5, 0.5))
    xt, yt = x + fx, y + fy
    sigma = float(fwhm) / 2.3548200450309493
    half = int(math.ceil(2.5 * sigma)) + 1
    x0 = int(math.floor(xt)) - half
    y0 = int(math.floor(yt)) - half
    size = 2 * half + 1
    h, w = data.shape
    if x0 < 0 or y0 < 0 or x0 + size > w or y0 + size > h:
        return None, None, None
    yy, xx = np.mgrid[0:size, 0:size]
    spot = np.exp(-0.5 * (((xx - (xt - x0)) ** 2 + (yy - (yt - y0)) ** 2)
                          / sigma ** 2))
    spot *= float(flux) / float(spot.sum())
    out = np.array(data, dtype=np.float64, copy=True)
    out[y0:y0 + size, x0:x0 + size] += spot
    return out, xt, yt


def click_off(x, y, rng, spread=1.5):
    # The observer's click is not the star's centre: every engine is started
    # from a position drawn around the truth, so the centroid has to work.
    # @return: (x_click, y_click)
    return (float(x + rng.uniform(-spread, spread)),
            float(y + rng.uniform(-spread, spread)))


def mag_err(measured, true_flux):
    # The error of a recovered flux in magnitudes, the unit the observer
    # reads. A recovered flux that is 1 % high is 0.0108 mag high.
    # @return: measured magnitude minus true magnitude
    if measured is None or measured <= 0 or true_flux <= 0:
        return None
    return -2.5 * math.log10(float(measured) / float(true_flux))


def robust_stats(values):
    # @args: values - a list of numbers (None allowed)
    # @return: (n, median, robust_sigma) with sigma = 1.4826 * MAD
    vals = [v for v in values if v is not None and np.isfinite(v)]
    if not vals:
        return 0, None, None
    arr = np.asarray(vals, dtype=np.float64)
    med = float(np.median(arr))
    mad = float(np.median(np.abs(arr - med)))
    return len(vals), med, float(1.4826 * mad)


def rms_of(values, clip=3.0, iters=2):
    # The scatter of a light curve, with the outliers the observer would
    # throw away anyway (a cosmic ray, a cloud) clipped. Same rule for every
    # engine, so the comparison is of the ENGINE and not of the cleaning.
    # @return: (n_used, rms, std) or (0, None, None)
    vals = [float(v) for v in values if v is not None and np.isfinite(v)]
    if len(vals) < 3:
        return len(vals), None, None
    arr = np.asarray(vals, dtype=np.float64)
    for _ in range(iters):
        med = float(np.median(arr))
        mad = float(np.median(np.abs(arr - med)))
        sig = 1.4826 * mad
        if sig <= 0:
            break
        keep = np.abs(arr - med) <= clip * sig
        if keep.all() or keep.sum() < 3:
            break
        arr = arr[keep]
    return len(arr), float(np.sqrt(np.mean((arr - arr.mean()) ** 2))), \
        float(np.std(arr, ddof=1)) if len(arr) > 1 else None


def results_dir():
    # Where the JSON and the tables go (bench output, never in the repo's
    # shipped tree).
    d = os.environ.get("NIGHTSCRIBE_BENCH_OUT", "/tmp/opencode/nsbench")
    os.makedirs(d, exist_ok=True)
    return d
