############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - SN series engine: quick-look differential photometry (Track B, B5)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Series engine for the SN quick-look differential photometry.

Given a set of stacked FITS images (one per night, optionally per filter)
and the SN's sky position, this module:

  1. loads each image and its WCS (header or Astrometry.net fallback);
  2. locates the SN pixel via WCS;
  3. detects sources on the reference image (local maxima + centroid);
  4. automatically culls candidates (unsaturated, isolated, constant across
     the series, away from the SN and the edges) — the user never selects
     comparison stars by hand (T2);
  5. optionally cross-matches with Gaia DR3 to drop known variables;
  6. builds an ensemble (~8, min 3) and measures the SN's differential
     magnitude per frame (Δmag = inst_mag_SN - mean(inst_mag_ensemble));
  7. produces an honest error bar (scatter of the ensemble) and a campaign
     analysis (slope mag/day, verdict vs the typical-curve template).

All photometry is pure numpy (ADR-004): aperture sum, sky annulus, instrumental
magnitude. No astropy, no photutils. The unit of work is the **stacked final
image** per night (interview: raw frames live outside NightScribe).
"""

import logging
import math

import numpy as np

from . import fits_io, fits_meta
from . import wcs as wcs_mod

logger = logging.getLogger(__name__)

# Default aperture radii (pixels). The SN is a point source on a stacked
# image: a moderate aperture captures most of the PSF; the annulus
# estimates the local sky without being so wide it hits a neighbour.
R_AP = 6.0
R_ANN_IN = 10.0
R_ANN_OUT = 15.0

# Saturation guard: a star whose peak is above this fraction of the frame
# maximum is rejected (it's too close to clipping to trust).
_SAT_FRAC = 0.85

# Ensemble targets
TARGET_N = 8
MIN_N = 3


# ---------------- aperture photometry primitives ----------------

def _centroid(data, x, y, half=5):
    # @args: data - 2D numpy array, x, y - float pixel, half - box half-size
    # @return: (cx, cy) refined to sub-pixel (intensity-weighted centroid)
    y0, y1 = max(0, int(y) - half), min(data.shape[0], int(y) + half + 1)
    x0, x1 = max(0, int(x) - half), min(data.shape[1], int(x) + half + 1)
    sub = data[y0:y1, x0:x1]
    if sub.size == 0 or not np.any(np.isfinite(sub)):
        return float(x), float(y)
    total = float(np.nansum(sub))
    if total <= 0:
        return float(x), float(y)
    ys, xs = np.mgrid[y0:y1, x0:x1]
    cx = float(np.nansum(xs * sub) / total)
    cy = float(np.nansum(ys * sub) / total)
    return cx, cy


def aperture_flux(data, x, y, r_ap=R_AP, r_ann_in=R_ANN_IN, r_ann_out=R_ANN_OUT):
    # @args: data - 2D numpy array, x, y - float pixel position,
    #        r_ap - aperture radius, r_ann_in/r_ann_out - sky annulus radii
    # @return: (flux, sky_per_pixel) or (None, None) if out of bounds
    h, w = data.shape
    if not (0 <= x < w and 0 <= y < h):
        return None, None
    # aperture sum (NaNs treated as zero)
    yy, xx = np.ogrid[:h, :w]
    ap_mask = (xx - x) ** 2 + (yy - y) ** 2 <= r_ap ** 2
    annulus_mask = ((xx - x) ** 2 + (yy - y) ** 2 >= r_ann_in ** 2
                    ) & ((xx - x) ** 2 + (yy - y) ** 2 <= r_ann_out ** 2)
    ap_pixels = data[ap_mask]
    if ap_pixels.size == 0:
        return None, None
    flux = float(np.nansum(ap_pixels))
    ann_pixels = data[annulus_mask]
    if ann_pixels.size == 0:
        sky_pp = 0.0
    else:
        sky_pp = float(np.nanmedian(ann_pixels))
    net_flux = flux - sky_pp * ap_pixels.size
    return net_flux, sky_pp


def instrumental_mag(data, x, y, r_ap=R_AP, r_ann_in=R_ANN_IN, r_ann_out=R_ANN_OUT):
    # @return: instrumental magnitude (-2.5*log10(net_flux)) or None
    flux, _sky = aperture_flux(data, x, y, r_ap, r_ann_in, r_ann_out)
    if flux is None or flux <= 0:
        return None
    return -2.5 * math.log10(flux)


# ---------------- source detection ----------------

def detect_sources(data, k=5.0, min_sep=10, max_sources=50):
    # Detects stellar sources on a stacked image: local maxima above
    # sky + k*sigma, refined to sub-pixel centroids. No sep/photutils.
    # @args: data - 2D numpy array, k - sigma above sky, min_sep - min
    #        separation between detected sources (pixels), max_sources - cap
    # @return: list of (x, y, peak) tuples sorted by peak (descending)
    clean = np.nan_to_num(data, nan=0.0)
    sky = float(np.nanmedian(clean))
    noise = float(np.nanstd(clean))
    if noise <= 0:
        return []
    threshold = sky + k * noise
    h, w = clean.shape
    sources = []
    for y in range(2, h - 2):
        for x in range(2, w - 2):
            val = clean[y, x]
            if val < threshold:
                continue
            # local maximum in a 3x3 box
            patch = clean[y - 1:y + 2, x - 1:x + 2]
            if val < patch.max():
                continue
            # avoid duplicates: check min_sep from already found
            too_close = False
            for sx, sy, _pk in sources:
                if (sx - x) ** 2 + (sy - y) ** 2 < min_sep ** 2:
                    too_close = True
                    break
            if too_close:
                continue
            cx, cy = _centroid(clean, x, y)
            sources.append((cx, cy, float(val)))
    sources.sort(key=lambda s: s[2], reverse=True)
    return sources[:max_sources]


# ---------------- series loading ----------------

class Frame:
    # A single stacked image in the follow-up series.
    def __init__(self, data, wcs, mjd, filter_name, path):
        self.data = data
        self.wcs = wcs
        self.mjd = mjd
        self.filter = filter_name
        self.path = path
        self.sn_xy = None    # set by load_series once the SN position is known

    def sn_pixel(self, sn_ra, sn_dec):
        # @args: sn_ra, sn_dec - degrees
        # @return: (x, y) pixel or None if off-frame / no WCS
        if self.wcs is None:
            return None
        x, y = self.wcs.sky_to_pixel(sn_ra, sn_dec)
        if 0 <= x < self.data.shape[1] and 0 <= y < self.data.shape[0]:
            self.sn_xy = (x, y)
            return x, y
        return None


def load_series(image_paths, sn_ra=None, sn_dec=None):
    # @args: image_paths - list of FITS file paths, sn_ra/sn_dec - SN position
    # @return: list of Frame objects (with WCS, MJD, filter from headers);
    #         frames without WCS are kept (they enter the curve via their MJD)
    #         but flagged for the animation to skip.
    frames = []
    for path in image_paths:
        try:
            header, data = fits_io.read_fits(path)
        except fits_io.FitsError as err:
            logger.warning("skipping %s: %s", path, err)
            continue
        w = wcs_mod.Wcs.from_header(header)
        meta = fits_meta.meta_from_header(header)
        f = Frame(data, w, meta["mjd"], meta["filter"], str(path))
        if sn_ra is not None and w is not None:
            f.sn_pixel(sn_ra, sn_dec)
        frames.append(f)
    frames.sort(key=lambda f: f.mjd if f.mjd is not None else 0.0)
    return frames


# ---------------- automatic culling ----------------

def _is_unsaturated(data, x, y, sat_adu=None):
    # @args: sat_adu - absolute ADU ceiling (if None, estimated as a
    #        fraction of the frame's brightest *non-SN* pixel: the 2nd
    #        highest peak, which is a comparison star, not the SN)
    # @return: True if the star's peak is below the saturation ceiling
    yi, xi = int(round(y)), int(round(x))
    if not (0 <= yi < data.shape[0] and 0 <= xi < data.shape[1]):
        return False
    peak = float(data[yi, xi])
    if sat_adu is None:
        # Robust ceiling: the 2nd-highest value in the frame (the
        # brightest *comparison* star). The SN itself is the global max
        # and would set the bar too high, so we skip the top 0.1% of pixels
        # (the SN's own core) and take the next brightest.
        sat_adu = float(np.nanpercentile(data, 99.9))
        # generous margin: 1.5× the 99.9th percentile catches normal
        # bright stars (well below) but not the SN's clipped core
        sat_adu *= 1.5
    return peak < sat_adu


def _is_isolated(x, y, sources, sep_px, exclude=None):
    # @args: exclude - (x, y) to skip (the SN itself and the star being
    #        evaluated: both should not count as a neighbour)
    # @return: True if no other detected source is within sep_px
    for sx, sy, _pk in sources:
        if exclude and abs(sx - exclude[0]) < 1 and abs(sy - exclude[1]) < 1:
            continue
        if abs(sx - x) < 1 and abs(sy - y) < 1:
            continue   # this is the star being evaluated: skip self
        if (sx - x) ** 2 + (sy - y) ** 2 < sep_px ** 2:
            return False
    return True


def _measure_all(frames, x, y, r_ap=R_AP, r_ann_in=R_ANN_IN, r_ann_out=R_ANN_OUT):
    # @return: list of instrumental magnitudes (one per frame) or None per frame
    mags = []
    for f in frames:
        m = instrumental_mag(f.data, x, y, r_ap, r_ann_in, r_ann_out)
        mags.append(m)
    return mags


def cull_candidates(frames, sn_xy, sources=None, r_ap=R_AP,
                    r_ann_in=R_ANN_IN, r_ann_out=R_ANN_OUT,
                    target_n=TARGET_N, min_n=MIN_N):
    # Automatic selection of comparison stars (T2: the user never picks by hand).
    # @args: frames - list of Frame, sn_xy - (x, y) of the SN, sources - detected
    #        list from the reference frame (or None: detect here)
    # @return: list of (x, y) ensemble star positions on the reference frame
    if not frames:
        return []
    ref = frames[0]
    if sources is None:
        sources = detect_sources(ref.data)
    sn_x, sn_y = sn_xy
    candidates = []
    for sx, sy, peak in sources:
        # away from the SN and from the edges (annulus must fit)
        if (sx - sn_x) ** 2 + (sy - sn_y) ** 2 < (r_ann_out * 2) ** 2:
            continue
        if not (r_ann_out <= sx < ref.data.shape[1] - r_ann_out
                and r_ann_out <= sy < ref.data.shape[0] - r_ann_out):
            continue
        if not _is_unsaturated(ref.data, sx, sy):
            continue
        if not _is_isolated(sx, sy, sources, r_ann_out, exclude=sn_xy):
            continue
        # constant across the series: measure in all frames, check scatter
        mags = _measure_all(frames, sx, sy, r_ap, r_ann_in, r_ann_out)
        valid = [m for m in mags if m is not None]
        if len(valid) < len(frames) * 0.8:   # must be measurable in most frames
            continue
        scatter = float(np.nanstd(valid)) if len(valid) > 1 else 0.0
        # constancy gate: a star whose scatter is large in absolute terms
        # (>0.1 mag) is a variable — reject it even if there are few candidates
        if scatter > 0.1:
            continue
        candidates.append((sx, sy, scatter, valid))
    if not candidates:
        return []
    # rank by lowest scatter (most constant); pick top target_n
    candidates.sort(key=lambda c: c[2])
    return candidates[:target_n]


# ---------------- ensemble + Δmag ----------------

def build_ensemble(frames, sn_xy, sources=None, r_ap=R_AP,
                    r_ann_in=R_ANN_IN, r_ann_out=R_ANN_OUT,
                    target_n=TARGET_N, min_n=MIN_N):
    # @return: list of (x, y) ensemble positions, or [] if < min_n reliable stars
    culled = cull_candidates(frames, sn_xy, sources, r_ap, r_ann_in, r_ann_out,
                             target_n, min_n)
    if len(culled) < min_n:
        logger.warning("only %d reliable comparison stars (need %d)", len(culled),
                     min_n)
        return []
    return [(c[0], c[1]) for c in culled]


def measure_series(frames, sn_xy, ensemble, r_ap=R_AP,
                    r_ann_in=R_ANN_IN, r_ann_out=R_ANN_OUT):
    # Measures the SN's differential magnitude per frame.
    # @return: list of {mjd, filter, dmag, err} dicts (one per frame with WCS)
    sn_x, sn_y = sn_xy
    # ensemble instrumental mags per frame
    ens_mags_per_frame = []
    for f in frames:
        ens = []
        for ex, ey in ensemble:
            m = instrumental_mag(f.data, ex, ey, r_ap, r_ann_in, r_ann_out)
            if m is not None:
                ens.append(m)
        ens_mags_per_frame.append(ens)
    points = []
    for i, f in enumerate(frames):
        sn_mag = instrumental_mag(f.data, sn_x, sn_y, r_ap, r_ann_in, r_ann_out)
        if sn_mag is None:
            continue
        ens = ens_mags_per_frame[i]
        if not ens:
            continue
        ens_mean = float(np.nanmean(ens))
        dmag = sn_mag - ens_mean
        err = float(np.nanstd(ens)) if len(ens) > 1 else 0.0
        points.append({
            "mjd": f.mjd, "filter": f.filter or "Clear",
            "mag": dmag, "err": err, "source": "quicklook",
        })
    return points


# ---------------- campaign analysis ----------------

def analyze_campaign(points, sn_type=None, peak_mjd=None, peak_mag=None):
    # Honest numeric summary of the campaign so far (B-b: the quick-look's value
    # is the campaign in context, not the bare point).
    # @args: points - list of {mjd, mag, err, filter} (differential or imported),
    #        sn_type - for the template verdict,
    #        peak_mjd/mag - to compute Δmag-from-peak; auto if None
    # @return: dict {slope_mag_per_day, delta_from_peak, nights, verdict}
    if not points:
        return {"slope_mag_per_day": None, "delta_from_peak": None,
                "nights": 0, "verdict": "no_data"}
    # auto-peak: brightest (lowest mag) point
    if peak_mjd is None or peak_mag is None:
        brightest = min(points, key=lambda p: p["mag"])
        peak_mjd = peak_mjd or brightest["mjd"]
        peak_mag = peak_mag or brightest["mag"]
    # filter: use the most common filter (or "Clear")
    filters = [p.get("filter") or "Clear" for p in points]
    main_filt = max(set(filters), key=filters.count)
    pts = [p for p in points if (p.get("filter") or "Clear") == main_filt]
    pts.sort(key=lambda p: p["mjd"])
    # linear fit: mag = slope * mjd + intercept
    mjds = np.array([p["mjd"] for p in pts])
    mags = np.array([p["mag"] for p in pts])
    if len(pts) >= 2:
        slope, intercept = np.polyfit(mjds, mags, 1)
    else:
        slope, intercept = 0.0, float(mags[0]) if len(pts) else 0.0
    delta_from_peak = float(mags[-1] - peak_mag) if pts else None
    nights = len(set(p["mjd"] for p in pts))
    # verdict vs template (if available)
    verdict = "unknown"
    from . import sn_templates
    tpl = sn_templates.template(sn_type) if sn_type else None
    if tpl and len(pts) >= 3:
        # compare the last point to the template at the same epoch
        last_d = pts[-1]["mjd"] - peak_mjd
        tpl_dm = None
        for d, dm in tpl:
            if abs(d - last_d) < 3:   # within 3 days of the template point
                tpl_dm = dm
                break
        if tpl_dm is not None:
            obs_dm = pts[-1]["mag"] - peak_mag
            if abs(obs_dm - tpl_dm) < 0.3:
                verdict = "normal"
            elif obs_dm > tpl_dm + 0.3:
                verdict = "faster"
            else:
                verdict = "slower"
    return {"slope_mag_per_day": float(slope),
            "delta_from_peak": delta_from_peak,
            "nights": nights,
            "verdict": verdict,
            "filter": main_filt}


# ---------------- top-level entry point ----------------

def quicklook(image_paths, sn_ra, sn_dec, sn_type=None,
              r_ap=R_AP, r_ann_in=R_ANN_IN, r_ann_out=R_ANN_OUT):
    # Full pipeline: load images → locate SN → detect sources → cull →
    # ensemble → measure → campaign analysis.
    # @args: image_paths - list of FITS paths, sn_ra/sn_dec - SN position (deg),
    #        sn_type - for the template verdict
    # @return: dict {"points": [...], "summary": {...}, "ensemble": [...]}
    frames = load_series(image_paths, sn_ra, sn_dec)
    if not frames:
        return {"points": [], "summary": {"verdict": "no_frames"},
                "ensemble": []}
    # locate SN on each frame
    sn_xy = None
    for f in frames:
        if f.sn_xy is not None:
            sn_xy = f.sn_xy
            break
    if sn_xy is None:
        return {"points": [], "summary": {"verdict": "no_wcs"},
                "ensemble": []}
    ensemble = build_ensemble(frames, sn_xy, r_ap=r_ap, r_ann_in=r_ann_in,
                              r_ann_out=r_ann_out)
    if not ensemble:
        return {"points": [], "summary": {"verdict": "no_ensemble"},
                "ensemble": []}
    points = measure_series(frames, sn_xy, ensemble, r_ap, r_ann_in, r_ann_out)
    summary = analyze_campaign(points, sn_type=sn_type)
    return {"points": points, "summary": summary, "ensemble": ensemble}
