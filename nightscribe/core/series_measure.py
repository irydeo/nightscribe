############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Photometric series engine (series plan, phase 2)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Measure a photometric series as a series (PRECISION appendix B, T1-T7).

One point per frame, with the single-plate recipe applied frame by frame
and the series glued honestly:

  1. per-frame zero point from that frame's own comps (T1), as a weighted
     ensemble with a MAD veto (T2), reusing core/photometry.measure_plate;
  2. per-frame quality gates (T7) that FLAG and never delete: saturation,
     guide jump (centroid off the reference), cosmic ray in the aperture,
     cloud / zero-point outlier;
  3. an honest total error per point (T4): CCD equation + ensemble + the
     Young scintillation over the point's time span + the flat residual;
  4. time at mid exposure (T6): T_mid = T_start + EXPTIME/2, with MJD and
     HJD (variables.jd_to_hjd, Schlyter) on the same instant;
  5. optional grouping (D19): N frames combined in the measurement domain
     (fluxes with 1/sigma^2 weights and a MAD veto, never pixel stacking),
     the time the mean of the members, the scintillation over the span;
  6. fixed comparison set and NO per-frame astrometry (D17): the target
     comes from the reference WCS and its per-frame centroid is the guide
     signal, not a position.

Kind-agnostic by parameters (D11): a transit, a variable, an SN or a HADS
series all run through this engine; the type only picks parameters and the
analysis-layer checklist. No Qt, no network.
"""

import logging
import math
from dataclasses import dataclass, field

import numpy as np

from . import fits_io, fits_meta, photometry, variables

logger = logging.getLogger(__name__)

# MAD veto on the frame ensemble (T2) and on flux grouping (D19): a comp
# or a frame beyond this many robust sigmas of the ensemble is left out
# (flagged, never deleted).
_ENSEMBLE_SIGMA = 3.0
_GROUP_SIGMA = 3.0
# A point with fewer than this many usable comparisons borrows a zero
# point interpolated from the neighbouring frames (D1).
_MIN_COMPS = 3


@dataclass(frozen=True, eq=False)
class SeriesConfig:
    # Everything the engine needs, resolved by the caller (the UI and the
    # live driver read their widgets/Ajustes into this; no dict magic).
    wcs: object = None              # reference WCS (D17: no per-frame)
    target_xy: tuple = (0.0, 0.0)   # target in reference pixels
    comp_set: tuple = ()            # fixed entries (D35), as a tuple
    band: str = None
    fallback_band: str = "V"
    zp_mode: str = "catalog"        # "catalog" | "relative" (D40)
    detrend_policy: str = "off"     # "off" | "airmass" | "auto" (phase 3)
    host_ref: object = None         # reserved (host subtraction, phase 3+)
    radii: tuple = None             # (rap, rin, rout) or None for defaults
    sigmaclip: bool = True
    sky_mode: str = "median"
    color: bool = False
    target_bv: float = 0.0
    site_gain: float = None
    site_ron: float = None
    site_flat: float = 0.007
    site_saturate: float = None
    site_lon: float = None
    site_lat: float = None
    site_aperture_m: float = 0.254
    site_height_m: float = 0.0
    site_linear: float = None       # camera profile linearity limit (ADU)
    site_dark: float = None         # camera profile dark current (e-/px/s)
    group_n: int = 1
    auto_aperture: bool = False     # T3: per-night k sweep (phase 3)
    align: str = "off"              # "off" | "warp"|"similarity" | "coords"
                                    # (register.py, D44): opt-in per-frame
                                    # registration; warp/similarity resample
                                    # onto the reference grid, coords measure
                                    # on the native grid at the mapped coords
    guide_jump_px: float = 2.0      # centroid off the reference (T7)
    cosmic_sigma: float = 8.0       # single-pixel spike over the noise
    zp_outlier_sigma: float = 3.0   # cloud / zero-point outlier (T7)


@dataclass
class SeriesPoint:
    # One point of the curve: the measured fluxes plus every honest flag.
    index: int = 0
    path: str = ""
    mjd: float = None               # mid exposure (T6)
    jd_start: float = None          # start of the group's first exposure (MJD)
    hjd: float = None
    filter: str = None
    exptime: float = None
    x: float = None
    y: float = None
    fwhm: float = None              # seeing in px, measured on the frame
                                    # (median of the group's frames)
    sky: float = None
    airmass: float = None
    flux: float = None
    flux_err: float = None
    inst: float = None              # instrumental mag (goes to mag_raw)
    mag: float = None               # calibrated (catalog) or differential
    mag_detrended: float = None     # after the honest detrend (T5)
    err: float = None               # total error
    err_internal: float = None
    zp: float = None
    zp_err: float = None
    n_comps: int = 0
    flags: list = field(default_factory=list)
    members: list = field(default_factory=list)   # member frame paths


@dataclass
class SeriesResult:
    # The whole run: status "complete" | "incomplete" (cancelled), the
    # points, the unreadable frames, the detrend block (phase 3) and the
    # resolved running parameters for the audit trail.
    status: str = "complete"
    points: list = field(default_factory=list)
    errors: dict = field(default_factory=dict)
    band: str = None
    zp_mode: str = "catalog"
    detrend: dict = None
    group_n: int = 1
    apertures: dict = field(default_factory=dict)   # per-night k (T3)


# ---------------- small numeric helpers ----------------

def _weighted_mean(values, weights):
    # @args: values, weights - same-length sequences (None skipped)
    # @return: the weighted mean, or None when no weight survives
    pairs = [(v, w) for v, w in zip(values, weights)
             if v is not None and w is not None and w > 0]
    if not pairs:
        return None
    num = sum(v * w for v, w in pairs)
    den = sum(w for _v, w in pairs)
    return num / den if den > 0 else None


def _combine_fluxes(fluxes, errs, k=_GROUP_SIGMA):
    # Combine the fluxes of a group (D19): weighted mean with 1/sigma^2
    # weights, a robust MAD veto for an outlier frame, never pixel
    # stacking. Unknown errors get weight 1.
    # @args: fluxes, errs - per-frame net flux and its error
    # @return: (flux, flux_err, used_indexes, rejected_indexes)
    pairs = [(i, f, e) for i, (f, e) in enumerate(zip(fluxes, errs))
             if f is not None and math.isfinite(f) and f > 0.0]
    if not pairs:
        return None, None, [], []
    if len(pairs) == 1:
        i, f, e = pairs[0]
        return f, e, [i], []
    arr = np.asarray([p[1] for p in pairs], dtype=np.float64)
    med = float(np.median(arr))
    mad = float(np.median(np.abs(arr - med)))
    kept, rejected = [], []
    for i, f, e in pairs:
        if mad > 0.0 and abs(f - med) > k * 1.4826 * mad:
            rejected.append(i)
        else:
            kept.append((i, f, e))
    if not kept:
        kept, rejected = pairs, []
    wts = [1.0 / (e ** 2) if (e is not None and e > 0) else 1.0
           for _i, _f, e in kept]
    comb = _weighted_mean([f for _i, f, _e in kept], wts)
    err = math.sqrt(1.0 / sum(wts)) if sum(wts) > 0 else None
    return comb, err, [i for i, _f, _e in kept], rejected


def _ensemble_zp(residuals, errs, k=_ENSEMBLE_SIGMA):
    # The frame's zero point as a weighted ensemble with a MAD veto (T2):
    # drop the comps whose residual (cat - inst) leaves the robust
    # scatter, then a 1/sigma^2 weighted mean.
    # @args: residuals, errs - per-comp (cat - inst) and its sigma
    # @return: (zp, zp_err, n_used, n_rejected)
    pairs = [(r, e) for r, e in zip(residuals, errs)
             if r is not None and math.isfinite(r)]
    if not pairs:
        return None, None, 0, 0
    if len(pairs) == 1:
        r, e = pairs[0]
        return r, e, 1, 0
    arr = np.asarray([r for r, _e in pairs], dtype=np.float64)
    med = float(np.median(arr))
    mad = float(np.median(np.abs(arr - med)))
    kept = [p for p in pairs
            if not (mad > 0.0 and abs(p[0] - med) > k * 1.4826 * mad)]
    rejected = len(pairs) - len(kept)
    if not kept:
        kept, rejected = pairs, 0
    wts = [1.0 / (e ** 2) if (e is not None and e > 0) else 1.0
           for _r, e in kept]
    zp = _weighted_mean([r for r, _e in kept], wts)
    formal_err = math.sqrt(1.0 / sum(wts)) if sum(wts) > 0 else None
    # robust scatter term (MAD) divided by sqrt(N) ensures honest error
    n_kept = len(kept)
    if n_kept > 0:
        arr_kept = np.asarray([r for r, _e in kept], dtype=np.float64)
        med_kept = float(np.median(arr_kept))
        mad_kept = float(np.median(np.abs(arr_kept - med_kept)))
        scatter_err = 1.4826 * mad_kept / math.sqrt(n_kept)
    else:
        scatter_err = None
    if formal_err is None:
        zp_err = scatter_err
    elif scatter_err is None:
        zp_err = formal_err
    else:
        zp_err = max(formal_err, scatter_err)
    return zp, zp_err, len(kept), rejected


def _add_flag(pt, flag):
    if flag not in pt.flags:
        pt.flags.append(flag)


# ---------------- time and site ----------------

def _mid_exposure(meta):
    # T6/D15: every point is timed at T_start + EXPTIME/2.
    # @args: meta - fits_meta.meta_from_header dict
    # @return: (mjd_mid, exptime), either may be None
    mjd = meta.get("mjd")
    exptime = meta.get("exptime_s")
    if mjd is None:
        return None, exptime
    if exptime:
        return mjd + float(exptime) / 2.0 / 86400.0, exptime
    return mjd, exptime


def _hjd_of(mjd, wcs, xy):
    # HJD at the same instant (D16), Earth-to-Sun light time via Schlyter.
    # @return: the HJD, or None when the sky position is unknown
    if mjd is None or wcs is None:
        return None
    try:
        ra, dec = wcs.pixel_to_sky(xy[0], xy[1])
    except Exception:
        return None
    return variables.jd_to_hjd(mjd + variables.MJD0, ra, dec)


def _target_altaz(cfg, mjd):
    # The target's alt-az from the reference WCS and the point's instant.
    # @return: (alt_deg, az_deg) or (None, None)
    if mjd is None or cfg.wcs is None or cfg.site_lon is None \
            or cfg.site_lat is None:
        return None, None
    try:
        from . import coords
        ra, dec = cfg.wcs.pixel_to_sky(cfg.target_xy[0], cfg.target_xy[1])
        jd = mjd + variables.MJD0
        lst = coords.lst_degrees(jd, float(cfg.site_lon))
        return coords.altaz(ra, dec, float(cfg.site_lat), lst)
    except Exception:
        return None, None


def _airmass(cfg, mjd):
    # T5: the airmass is the detrend's minimum regressor.
    # @return: clamped airmass, or None when the geometry is unknown
    alt, _az = _target_altaz(cfg, mjd)
    if alt is None:
        return None
    return photometry.airmass_from_alt(alt)


def _scintillation(cfg, mjd, span_s):
    # T4/H5: Young's scintillation with the site from Ajustes and the
    # target's altitude from the reference WCS and the point's instant.
    # @return: sigma in mag, or None
    if not span_s or mjd is None:
        return None
    alt, _az = _target_altaz(cfg, mjd)
    if alt is None:
        return None
    return photometry.scintillation_mag(alt, span_s, cfg.site_aperture_m,
                                        cfg.site_height_m)


def _sky_sigma(data, x, y, r_ap):
    # Robust sky noise from the neighbourhood of the aperture (pixel to
    # pixel differences, so a smooth gradient barely moves it).
    # @return: sigma in ADU, or None when the cutout is too small
    h, w = data.shape
    x0 = max(0, int(x - r_ap - 4))
    x1 = min(w, int(x + r_ap + 5))
    y0 = max(0, int(y - r_ap - 4))
    y1 = min(h, int(y + r_ap + 5))
    sub = np.asarray(data[y0:y1, x0:x1], dtype=np.float64)
    if sub.size < 16:
        return None
    diffs = np.concatenate([np.diff(sub, axis=1).ravel(),
                            np.diff(sub, axis=0).ravel()])
    return 1.4826 * float(np.median(np.abs(diffs - np.median(diffs)))) \
        / math.sqrt(2.0)


def _cosmic_hit(data, x, y, r_ap, sky_pp, sigma_sky, k):
    # A single hot pixel inside the aperture with its neighbours at sky
    # level is a cosmic ray, not a star (a star's core has a broad wing).
    # @return: True when the aperture holds an isolated spike
    if data is None or sky_pp is None or sigma_sky is None \
            or sigma_sky <= 0:
        return False
    h, w = data.shape
    x0 = max(0, int(math.floor(x - r_ap)))
    x1 = min(w, int(math.ceil(x + r_ap)) + 1)
    y0 = max(0, int(math.floor(y - r_ap)))
    y1 = min(h, int(math.ceil(y + r_ap)) + 1)
    if x1 <= x0 or y1 <= y0:
        return False
    sub = np.asarray(data[y0:y1, x0:x1], dtype=np.float64)
    yy, xx = np.mgrid[y0:y1, x0:x1]
    inside = (xx - x) ** 2 + (yy - y) ** 2 <= r_ap ** 2
    if not np.any(inside):
        return False
    resid = sub - float(sky_pp)
    for py, px in zip(*np.where(inside & (resid > k * sigma_sky))):
        neighbours = []
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ny, nx = py + dy, px + dx
            if 0 <= ny < sub.shape[0] and 0 <= nx < sub.shape[1] \
                    and inside[ny, nx]:
                neighbours.append(resid[ny, nx])
        if neighbours and all(v < 0.5 * resid[py, px] for v in neighbours):
            return True
    return False


# ---------------- frame measurement ----------------

def _read_frame(path):
    # @return: (header, data) or (None, error string)
    try:
        header, data = fits_io.read_fits(path)
    except fits_io.FitsError as err:
        return None, str(err)
    return (header, data), None


def _frame_fwhm(data, res):
    # The frame's own seeing, so every point carries a real FWHM (the T5
    # detrend's "auto" regressor and the report's seeing column). The plate
    # recipe only carries a FWHM when the caller measured one, so the
    # engine measures it here: second moments on the target and on the
    # comps it just used (cheap 19x19 cutouts, one median per frame).
    # @args: data - the frame the recipe ran on, res - its PlateResult
    # @return: the FWHM in px (the recipe's own when it carried one), or
    #          None when nothing is measurable
    if res.fwhm is not None or not res.ok or res.col is None:
        return res.fwhm
    spots = [(res.col, res.row)]
    spots += [(r["x"], r["y"]) for _e, r in res.used
              if r.get("x") is not None and r.get("y") is not None]
    return photometry.estimate_fwhm(data, spots)


def _measure_frame(path, header, data, cfg, apertures=None, wcs_ov=None,
                   target_ov=None):
    # One (already loaded) frame through the shared plate recipe. With
    # registration the frame is measured on its NATIVE grid at the mapped
    # coordinates (wcs_ov/target_ov), so the PSF is never resampled (D44).
    # @return: the frame dict
    meta = fits_meta.meta_from_header(header)
    night = _night_of(meta.get("mjd"))
    radii = None
    if apertures and night in apertures:
        radii = apertures[night].get("radii")
    if radii is None:
        radii = cfg.radii
    rap = (radii if radii else cfg.radii or (photometry.R_AP,))[0]
    pcfg = photometry.PlateConfig(
        target_xy=target_ov if target_ov is not None else cfg.target_xy,
        entries=list(cfg.comp_set),
        header=header, wcs=wcs_ov if wcs_ov is not None else cfg.wcs,
        band=cfg.band,
        fallback_band=cfg.fallback_band, radii=radii,
        sigmaclip=cfg.sigmaclip, sky_mode=cfg.sky_mode,
        color=cfg.color, target_bv=cfg.target_bv,
        site_gain=cfg.site_gain, site_ron=cfg.site_ron,
        site_flat=cfg.site_flat, site_saturate=cfg.site_saturate,
        site_lon=cfg.site_lon, site_lat=cfg.site_lat,
        site_aperture_m=cfg.site_aperture_m,
        site_height_m=cfg.site_height_m,
        linear_adu=cfg.site_linear,
        site_dark=cfg.site_dark,
        require_catalog=(cfg.zp_mode == "catalog"))
    res = photometry.measure_plate(data, pcfg)
    # the seeing is measured here, on the very frame the recipe ran on
    # (native pixels under registration), so each point carries its own
    res.fwhm = _frame_fwhm(data, res)
    mjd_mid, exptime = _mid_exposure(meta)
    return {"path": str(path), "data": data, "meta": meta, "res": res,
            "mjd": mjd_mid, "exptime": exptime, "r_ap": rap,
            "filter": meta.get("filter")}


def _aperture_off_footprint(mask, res, r_ap):
    # True when the target's or any used comp's aperture box touches
    # warp-filled pixels (flux inflated by the zero fill).
    # @args: mask - register.warp_mask output, res - the frame's
    #        PlateResult, r_ap - aperture radius in pixels
    # @return: bool
    h, w = mask.shape
    m = int(math.ceil(r_ap))
    spots = []
    if res.col is not None and res.row is not None:
        spots.append((res.col, res.row))
    for _e, r in res.used:
        if r.get("x") is not None and r.get("y") is not None:
            spots.append((r["x"], r["y"]))
    for x, y in spots:
        x0, x1 = max(0, int(x) - m), min(w, int(x) + m + 1)
        y0, y1 = max(0, int(y) - m), min(h, int(y) + m + 1)
        if x0 >= x1 or y0 >= y1 or not mask[y0:y1, x0:x1].all():
            return True
    return False


def _run_one(path, cfg, apertures=None):
    # One frame through the shared plate recipe (T1/T2 raw material): the
    # target and the comps' fluxes, plus the guard reason when refused.
    # @args: apertures - optional {night: {"radii": ...}} from the T3 sweep
    # @return: (frame dict, None) or (None, error string)
    loaded, err = _read_frame(path)
    if loaded is None:
        return None, err
    header, data = loaded
    return _measure_frame(path, header, data, cfg, apertures), None


def _frame_flux(frame, cfg):
    # @return: (target net flux, its sigma) from the frame's PlateResult
    res = frame["res"]
    target = res.target or {}
    if not res.ok or target.get("flux") is None:
        return None, None
    err = photometry.ccd_flux_error(
        target.get("flux"), target.get("sky_pp"), target.get("n_pix"),
        gain=res.gain, ron=cfg.site_ron, exptime=frame.get("exptime"),
        dark_e_s=cfg.site_dark, n_sky=target.get("n_sky"))
    return target.get("flux"), err


def _group_comp(group, star, cfg):
    # One comp's group flux and instrumental magnitude (D19: combine the
    # measured fluxes, never the pixels).
    # @return: (inst, catalog value or None, mag error)
    fluxes, errs, cat = [], [], None
    for f in group:
        for e, r in f["res"].used:
            if e["star"] is star:
                if r.get("flux") is not None:
                    fluxes.append(r["flux"])
                    errs.append(photometry.ccd_flux_error(
                        r["flux"], r.get("sky_pp"), r.get("n_pix"),
                        gain=f["res"].gain, ron=cfg.site_ron,
                        exptime=f.get("exptime"), dark_e_s=cfg.site_dark,
                        n_sky=r.get("n_sky")))
                value = photometry.band_of(star, cfg.band
                                           or cfg.fallback_band)[0]
                if value is not None:
                    cat = value
    comb, comb_err, _u, _r = _combine_fluxes(fluxes, errs)
    if comb is None or comb <= 0:
        return None, cat, None
    return (-2.5 * math.log10(comb), cat,
            photometry.mag_error(comb, comb_err))


# ---------------- grouping and calibration ----------------

def _group_centroid(group):
    xs = [f["res"].col for f in group if f["res"].col is not None]
    ys = [f["res"].row for f in group if f["res"].row is not None]
    if not xs:
        return None, None
    return float(np.mean(xs)), float(np.mean(ys))


def _group_span(group):
    # T4: the effective exposure for the scintillation is the group's time
    # span (never less than one exposure).
    mids = [f["mjd"] for f in group if f["mjd"] is not None]
    exptimes = [f.get("exptime") or 0.0 for f in group]
    if len(mids) >= 2:
        span = (max(mids) - min(mids)) * 86400.0 + max(exptimes)
    else:
        span = max(exptimes) if exptimes else 0.0
    return span or None


def _guide_jump(pt, cfg):
    # T7: the target's centroid off the reference plate is a guide signal.
    if pt.x is None or cfg.target_xy is None:
        return False
    return math.hypot(pt.x - cfg.target_xy[0],
                      pt.y - cfg.target_xy[1]) > cfg.guide_jump_px


def _cosmic_flag(frame, cfg):
    # T7's cosmic verdict for one frame, computed while its image is
    # still alive: the measure loop releases the array right after, so
    # the gates downstream read this flag instead of the pixels.
    # @args: frame - measured frame dict still holding "data"
    # @return: True when the target aperture holds an isolated spike
    res = frame["res"]
    if not res.ok or res.col is None or res.target is None:
        return False
    sky_pp = res.target.get("sky_pp")
    r_ap = (cfg.radii or (photometry.R_AP,))[0]
    sigma = _sky_sigma(frame["data"], res.col, res.row, r_ap)
    return _cosmic_hit(frame["data"], res.col, res.row, r_ap, sky_pp,
                       sigma, cfg.cosmic_sigma)


def _flag_gates(pt, group, cfg):
    # T7: saturation (the plate recipe refused the target), a cosmic ray
    # in the aperture and a guide jump. Marked, never deleted. The cosmic
    # verdict arrives precomputed per frame: the images never reach this
    # point, they are released in the measure loop.
    for f in group:
        # the alignment verdicts stand even when the plate was refused
        if f.get("align_failed"):
            _add_flag(pt, "align_failed")
        if f.get("align_edge"):
            _add_flag(pt, "align_edge")
        if not f["res"].ok:
            reason = (f["res"].reason or {})
            en = reason.get("en", "")
            if en == "saturated":
                _add_flag(pt, "saturated")
            elif en.startswith("nonlinear"):
                _add_flag(pt, "nonlinear")
            else:
                _add_flag(pt, "unusable")
            continue
        if f.get("cosmic"):
            _add_flag(pt, "cosmic")
    if _guide_jump(pt, cfg):
        _add_flag(pt, "guide_jump")


def _catalog_point(pt, group, cfg):
    # T1/T2: the point's zero point from its own comps (weighted ensemble
    # with a MAD veto); the calibrated magnitude and error.
    residuals, errors = [], []
    for e in cfg.comp_set:
        inst_c, cat_c, err_c = _group_comp(group, e["star"], cfg)
        if inst_c is None or cat_c is None:
            continue
        # the catalogue error of the comp counts too (C4: the ZP error
        # can never be better than the catalogues it hangs from)
        cat_err = None
        for item in e["star"].get("bands", []):
            if item.get("label") == (cfg.band or cfg.fallback_band):
                cat_err = item.get("err")
                break
        if err_c is not None and cat_err:
            err_c = math.sqrt(err_c ** 2 + float(cat_err) ** 2)
        elif cat_err:
            err_c = float(cat_err)
        residuals.append(cat_c - inst_c)
        errors.append(err_c)
    zp, zp_err, kept, _rej = _ensemble_zp(residuals, errors)
    pt.n_comps = kept
    pt.zp, pt.zp_err = zp, zp_err
    if kept < _MIN_COMPS:
        _add_flag(pt, "few_comps")
    pt.mag = pt.inst + zp if (pt.inst is not None and zp is not None) \
        else None


def _relative_point(pt, group, cfg):
    # D40/ADR-048 relative mode: no catalog needed; the point is the
    # differential magnitude against the group's comp ensemble.
    comp_insts = []
    for e in cfg.comp_set:
        inst_c, _cat, _err = _group_comp(group, e["star"], cfg)
        if inst_c is not None:
            comp_insts.append(inst_c)
    pt.n_comps = len(comp_insts)
    if not comp_insts:
        _add_flag(pt, "few_comps")
        pt.mag = None
        return
    ref = float(np.median(comp_insts))
    pt.zp = ref
    pt.zp_err = float(np.std(comp_insts)) / math.sqrt(len(comp_insts))
    pt.mag = pt.inst - ref if pt.inst is not None else None


def _build_point(group, cfg):
    # Collapse one group of measured frames into a single honest point.
    first = group[0]
    # exptime is the group's total integration (None when no frame
    # carries one): the ExoClock start is mjd_mid minus half of it
    exps = [f.get("exptime") for f in group]
    tot_exp = sum(e or 0.0 for e in exps) if any(
        e is not None for e in exps) else None
    pt = SeriesPoint(path=first["path"], filter=first.get("filter"),
                     exptime=tot_exp)
    # ExoClock wants the start of the first exposure of the group, not
    # the mid time minus half the sum (cadence gaps would bias it)
    starts = [f["mjd"] - (f.get("exptime") or 0.0) / 2.0 / 86400.0
              for f in group if f.get("mjd") is not None]
    pt.jd_start = min(starts) if starts else None
    pt.members = [f["path"] for f in group]
    fluxes, errs = [], []
    for f in group:
        tf, te = _frame_flux(f, cfg)
        fluxes.append(tf)
        errs.append(te)
    comb, comb_err, _used, _rej = _combine_fluxes(fluxes, errs)
    pt.flux, pt.flux_err = comb, comb_err
    pt.x, pt.y = _group_centroid(group)
    # the group's seeing is the median of its frames' OWN measurements
    # (never the first frame's: a defocused member would go unnoticed)
    fwhms = [f["res"].fwhm for f in group if f["res"].fwhm is not None]
    pt.fwhm = float(np.median(fwhms)) if fwhms else None
    _tgt = first["res"].target or {}
    pt.sky = _tgt.get("sky_pp")
    weights = [1.0 / (e ** 2) if (e and e > 0) else 1.0 for e in errs]
    pt.mjd = _weighted_mean([f["mjd"] for f in group], weights)
    pt.hjd = _hjd_of(pt.mjd, cfg.wcs, cfg.target_xy)
    pt.airmass = _airmass(cfg, pt.mjd)
    _flag_gates(pt, group, cfg)
    if comb is None:
        _add_flag(pt, "unusable")
        return pt
    pt.inst = -2.5 * math.log10(comb)
    pt.err_internal = photometry.mag_error(pt.flux, pt.flux_err)
    if cfg.zp_mode == "relative":
        _relative_point(pt, group, cfg)
    else:
        _catalog_point(pt, group, cfg)
    span = _group_span(group)
    scint = _scintillation(cfg, pt.mjd, span)
    pt.err = photometry.combine_errors(pt.err_internal, pt.zp_err, scint,
                                       cfg.site_flat)
    return pt


def _fill_neighbour_zp(points, cfg):
    # D1: a point whose own comps cannot set a zero point borrows the
    # interpolation of its neighbours' zero points, flagged, never a
    # global fixed value. Catalog mode only.
    if cfg.zp_mode != "catalog":
        return
    good = [(i, p) for i, p in enumerate(points)
            if p.zp is not None and "few_comps" not in p.flags]
    for i, p in enumerate(points):
        # Skip if already has zp or not flagged as few_comps
        if p.zp is not None or "few_comps" not in p.flags:
            continue
        if not good:
            _add_flag(p, "no_zp")
            continue
        # Find neighbouring good points using mjd for interpolation
        prev = [(j, pts) for j, pts in good if j < i]
        nxt = [(j, pts) for j, pts in good if j > i]
        if prev and nxt:
            j0, pt0 = prev[-1]
            j1, pt1 = nxt[0]
            mjd0, mjd1 = pt0.mjd, pt1.mjd
            mjd_i = points[i].mjd
            # Linear interpolation in time
            if mjd1 != mjd0:
                frac = (mjd_i - mjd0) / float(mjd1 - mjd0)
            else:
                frac = 0.5
            z = pt0.zp + (pt1.zp - pt0.zp) * frac
            # Error propagation: use larger of neighbour errors
            err = max(getattr(pt0, "zp_err", 0.0), getattr(pt1, "zp_err", 0.0))
        elif prev:
            pt0 = prev[-1][1]
            z = pt0.zp
            err = getattr(pt0, "zp_err", 0.0)
        else:
            pt1 = nxt[0][1]
            z = pt1.zp
            err = getattr(pt1, "zp_err", 0.0)
        p.zp = z
        p.zp_err = err
        p.n_comps = max(p.n_comps, 1)
        p.mag = p.inst + z if p.inst is not None else None
        _add_flag(p, "neighbour_zp")


def _flag_clouds(points, cfg):
    # T7: zero points that leave the series' robust scatter are a thin
    # cloud (marked, never deleted). Catalog mode only.
    if cfg.zp_mode != "catalog":
        return
    zps = [p.zp for p in points if p.zp is not None
           and "neighbour_zp" not in p.flags]
    if len(zps) < 4:
        return
    arr = np.asarray(zps, dtype=np.float64)
    med = float(np.median(arr))
    mad = float(np.median(np.abs(arr - med)))
    if mad <= 0.0:
        return
    for p in points:
        if p.zp is not None \
                and abs(p.zp - med) > cfg.zp_outlier_sigma * 1.4826 * mad:
            _add_flag(p, "cloud")


# ---------------- T5: honest detrend ----------------

# a2 on a grid with the bounds EXOTIC uses; a1 (and a3) solved
# analytically at each a2, so the only non-linear parameter is a2.
_A2_GRID = tuple(x / 20.0 for x in range(-20, 21))
_AUTO_IMPROVE = 0.10        # keep the extra terms only if the rms drops
_MIN_NIGHT_POINTS = 4       # below this a night is "short" (D34)
_MIN_AIRMASS_RANGE = 0.05   # below this there is no trend to fit (D34)


def _night_of(mjd):
    # Observing night: the day boundary sits at local noon, so a run that
    # crosses midnight stays one night.
    # @return: an integer night key, or None
    if mjd is None:
        return None
    return int(math.floor(mjd - 0.5))


def _night_label(night):
    # The night key as the evening's civil date (the key is the MJD of
    # the following noon, so noon of key+1 is the night that ends it).
    # @return: "YYYY-MM-DD", or the key itself when it is not numeric
    if night is None:
        return ""
    try:
        from . import coords, variables
        dt = coords.datetime_from_jd(float(night) + 0.5
                                     + variables.MJD0)
        return dt.strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return str(night)


def _rms(values):
    # @return: the plain rms, or None
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    return float(np.sqrt(np.mean(np.square(vals))))


def _robust_std(values):
    # @return: the robust (MAD) scatter, or None
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return None
    arr = np.asarray(vals, dtype=np.float64)
    return float(1.4826 * np.median(np.abs(arr - np.median(arr))))


def _wls(y, cols, w):
    # Weighted least squares for the linear coefficients of `cols`.
    # @return: (coeffs, yhat, weighted rms) or (None, None, None)
    a = np.column_stack(cols)
    aw = a * w[:, None]
    try:
        coef, *_ = np.linalg.lstsq(aw, y * w, rcond=None)
    except np.linalg.LinAlgError:
        return None, None, None
    yhat = a @ coef
    resid = y - yhat
    rms = math.sqrt(float(np.sum((w * resid) ** 2) / np.sum(w ** 2)))
    return coef, yhat, rms


def _columns(x, a2, extra):
    # @return: (design columns, names) for a1*exp(a2*X) + a3 + extras
    cols = [np.exp(a2 * np.asarray(x, dtype=np.float64)),
            np.ones(len(x))]
    names = ["a1", "a3"]
    for name, col in (extra or {}).items():
        cols.append(np.asarray(col, dtype=np.float64))
        names.append(name)
    return cols, names


def _fit_night(x, y, w, extra=None, sigma_clip=3.0):
    # Fit a1*exp(a2*X) + a3 (+ optional extra linear terms) for one night:
    # a2 on the bounded grid, a1 and a3 analytic at each a2, then one
    # robust sigma-clip round so a transit does not bend the trend (the
    # trend is the OUT-of-transit level, never the signal).
    # @args: x - airmass, y - magnitudes, w - weights (1/sigma),
    #        extra - optional {name: column} (FWHM, sky, x, y)
    # @return: (coeffs dict, trend array, rms) or (None, None, None)
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    w = np.asarray(w, dtype=np.float64)
    best = None
    for a2 in _A2_GRID:
        cols, names = _columns(x, a2, extra)
        coef, yhat, rms = _wls(y, cols, w)
        if rms is not None and (best is None or rms < best[3]):
            best = (dict(zip(names, coef)), a2, yhat, rms)
    if best is None:
        return None, None, None
    coeffs, a2, yhat, rms = best
    coeffs["a2"] = a2
    resid = y - yhat
    mad = float(np.median(np.abs(resid - np.median(resid))))
    if mad > 0.0:
        keep = np.abs(resid) <= sigma_clip * 1.4826 * mad
        if max(3, len(y) // 2) <= int(keep.sum()) < len(y):
            cols, names = _columns(x[keep], a2, None if extra is None else
                                   {k: np.asarray(v)[keep]
                                    for k, v in extra.items()})
            coef, yhat, rms = _wls(y[keep], cols, w[keep])
            if coef is not None:
                coeffs = dict(zip(names, coef))
                coeffs["a2"] = a2
    return coeffs, yhat, rms


def _extra_terms(points, ids):
    # @return: the optional phase-H columns for the "auto" policy
    return {"fwhm": [points[i].fwhm if points[i].fwhm is not None
                     else 0.0 for i in ids],
            "sky": [points[i].sky if points[i].sky is not None else 0.0
                    for i in ids],
            "x": [points[i].x if points[i].x is not None else 0.0
                  for i in ids],
            "y": [points[i].y if points[i].y is not None else 0.0
                  for i in ids]}


def detrend_series(points, policy="airmass", auto_improve=_AUTO_IMPROVE):
    # The honest detrend (T5/D13): a1*exp(a2*X) + a3 per night with a1
    # analytic, a2 bounded to [-1, 1] and a robust clip; the "auto"
    # policy adds FWHM/sky/x/y only when the residual rms drops by at
    # least `auto_improve`. A short night or one with too little airmass
    # range falls back to an offset (D34), said in the returned block.
    #
    # T5 honesty: a smooth signal that shares the airmass' timescale can
    # be partly absorbed by the trend (a transit does not: it is sharp),
    # so the RAW curve is always kept beside the detrended one and the
    # phase-7 joint fit (model + detrend solved together) is where a
    # transit is never touched. This function is the standalone minimum.
    # @args: points - SeriesPoints with mag, err, airmass and mjd,
    #        policy - "airmass" | "auto" (caller checks "off")
    # @return: {"detrended": [mag or None per point], "nights": [...],
    #          "policy", "terms", "rms_before", "rms_after"} or None
    idx = [i for i, p in enumerate(points)
           if p.mag is not None and p.airmass is not None]
    if not idx:
        return None
    by_night = {}
    for i in idx:
        by_night.setdefault(_night_of(points[i].mjd), []).append(i)
    detrended = [None] * len(points)
    nights = []
    terms = set()
    for night, ids in sorted(by_night.items(),
                             key=lambda kv: (kv[0] is None, kv[0])):
        xs = [points[i].airmass for i in ids]
        ys = [points[i].mag for i in ids]
        ws = [1.0 / points[i].err if points[i].err else 1.0
              for i in ids]
        short = len(ids) < _MIN_NIGHT_POINTS \
            or (max(xs) - min(xs)) < _MIN_AIRMASS_RANGE
        if short:
            base = float(np.median(ys))
            for i in ids:
                detrended[i] = points[i].mag - base
            nights.append({"night": night, "a1": base, "a2": 0.0,
                           "a3": 0.0, "n": len(ids), "fallback": "offset",
                           "rms_before": _rms(ys),
                           "rms_after": _rms([detrended[i]
                                              for i in ids])})
            continue
        coef, _yhat, rms = _fit_night(xs, ys, ws)
        used = []
        if policy == "auto" and coef is not None:
            coef_x, _yhx, rms_x = _fit_night(xs, ys, ws,
                                             extra=_extra_terms(points, ids))
            if rms_x is not None and rms is not None \
                    and rms_x <= (1.0 - auto_improve) * rms:
                coef, rms = coef_x, rms_x
                used = ["fwhm", "sky", "x", "y"]
        if coef is None:
            continue
        terms.update(used)
        a1, a2, a3 = coef.get("a1"), coef.get("a2"), coef.get("a3")
        for i in ids:
            trend = a1 * math.exp(a2 * points[i].airmass) + a3
            for name in used:
                trend += coef.get(name, 0.0) * (getattr(points[i], name, 0.0)
                                                or 0.0)
            detrended[i] = points[i].mag - trend
        nights.append({"night": night, "a1": a1, "a2": a2, "a3": a3,
                       "n": len(ids), "fallback": None, "terms": used,
                       "rms_before": _rms(ys),
                       "rms_after": _rms([detrended[i] for i in ids])})
    return {"detrended": detrended, "nights": nights, "policy": policy,
            "terms": sorted(terms),
            "rms_before": _rms([points[i].mag for i in idx]),
            "rms_after": _rms([detrended[i] for i in idx])}


# ---------------- T3: aperture sweep per night ----------------

def _check_star(cfg):
    # @return: the check star's star dict, else the first comp's, else None
    for e in cfg.comp_set:
        if e.get("kind") == "check":
            return e.get("star")
    for e in cfg.comp_set:
        if e.get("star"):
            return e.get("star")
    return None


def sweep_aperture(paths, cfg, ks=None):
    # T3: per night, pick the k in [1.0, 2.0] whose check-star scatter is
    # smallest (FWHM measured per frame, so guide defences cannot break
    # the curve). Each frame is read once and released: the sweep keeps
    # per-frame magnitudes and FWHM, never the images.
    # @args: paths - FITS paths, cfg - SeriesConfig with comp_set and wcs,
    #        ks - the multipliers to try (default: 1.0 .. 2.0 step 0.1)
    # @return: {night: {"k", "rms", "radii", "fwhm"}}
    ks = ks or [1.0 + 0.1 * i for i in range(11)]
    star = _check_star(cfg)
    if star is None or cfg.wcs is None:
        return {}
    try:
        cx, cy = cfg.wcs.sky_to_pixel(star["ra"], star["dec"])
    except Exception:
        return {}
    positions = [(cx, cy)]
    by_night = {}       # {night: {k: (mags, fwhms)}}
    for path in paths:
        try:
            header, data = fits_io.read_fits(path)
        except fits_io.FitsError:
            continue
        night = _night_of(fits_meta.meta_from_header(header).get("mjd"))
        fwhm = photometry.estimate_fwhm(data, positions)
        slots = by_night.setdefault(night, {k: ([], []) for k in ks})
        for k in ks:
            r_ap, r_in, r_out = photometry.aperture_for_fwhm(fwhm, k=k)
            r = photometry.measure_point(data, cx, cy, r_ap=r_ap,
                                         r_ann_in=r_in, r_ann_out=r_out)
            if not r["ok"] or r["flux"] is None or r["flux"] <= 0:
                continue
            mags, fwhms = slots[k]
            mags.append(-2.5 * math.log10(r["flux"]))
            if fwhm is not None:
                fwhms.append(fwhm)
    out = {}
    for night, slots in by_night.items():
        best = None
        for k in ks:
            mags, fwhms = slots[k]
            if len(mags) < 3:
                continue
            spread = _robust_std(mags)
            if spread is not None and (best is None or spread < best[1]):
                fwhm = float(np.median(fwhms)) if fwhms else None
                best = (k, spread, photometry.aperture_for_fwhm(fwhm, k=k),
                        fwhm)
        if best is not None:
            out[night] = {"k": best[0], "rms": best[1], "radii": best[2],
                          "fwhm": best[3]}
    return out


def measure_series(paths, cfg, progress=None, cancel=None):
    # Measure a whole series frame by frame (T1-T7), grouping when asked
    # (D19). Never raises for a bad frame: unreadable files are recorded
    # and skipped; a cancelled run returns status "incomplete".
    # @args: paths - FITS paths (visit order), cfg - SeriesConfig,
    #        progress - optional callable(done, total),
    #        cancel - optional callable() -> True to stop
    # @return: a SeriesResult
    paths = list(paths)
    total = len(paths)
    result = SeriesResult(zp_mode=cfg.zp_mode,
                          group_n=max(1, int(cfg.group_n)))
    apertures = {}
    if cfg.auto_aperture and cfg.radii is None:
        apertures = sweep_aperture(paths, cfg)
        result.apertures = apertures
    frames = []
    ref_data = None
    for i, path in enumerate(paths):
        if cancel is not None and cancel():
            result.status = "incomplete"
            break
        loaded, err = _read_frame(path)
        if loaded is None:
            result.errors[str(path)] = err
            if progress is not None:
                progress(i + 1, total)
            continue
        header, data = loaded
        align_info = None
        wcs_ov = None
        target_ov = None
        warped_mask = None
        if cfg.align != "off":
            # the first readable frame is the reference grid (target_xy
            # and the comps live in ITS pixels)
            if ref_data is None:
                ref_data = data
            else:
                from . import register
                align_info = register.estimate_transform(ref_data, data)
                if cfg.align in ("warp", "similarity"):
                    data = register.apply_transform(
                        data, align_info["angle"], align_info["dx"],
                        align_info["dy"])
                    # the warp fills the off-footprint pixels with
                    # zeros; with a near-zero sky that inflates the
                    # flux, so apertures touching them are flagged
                    warped_mask = register.warp_mask(
                        data.shape, align_info["angle"],
                        align_info["dx"], align_info["dy"])
                elif cfg.align == "coords":
                    # measure on the native grid at the mapped
                    # coordinates: the PSF is never resampled
                    if cfg.wcs is not None:
                        wcs_ov = register.compose_wcs(cfg.wcs, align_info)
                    target_ov = register.ref_to_src_point(
                        align_info, cfg.target_xy, data.shape)
        frame = _measure_frame(path, header, data, cfg, apertures,
                               wcs_ov=wcs_ov, target_ov=target_ov)
        if align_info is not None:
            frame["align"] = align_info
            if align_info.get("quality", 0.0) < register.QUALITY_MIN:
                frame["align_failed"] = True
        if warped_mask is not None:
            frame["align_edge"] = _aperture_off_footprint(
                warped_mask, frame["res"], frame["r_ap"])
            warped_mask = None
            if cfg.align == "coords" and frame["res"].col is not None:
                frame["res"].col, frame["res"].row = \
                    register.src_to_ref_point(align_info,
                                              (frame["res"].col,
                                               frame["res"].row),
                                              data.shape)
        # the cosmic gate runs here, while the image is alive; the full
        # array is released right away, so the series holds points and
        # flags, never pixels (one frame in RAM at a time)
        frame["cosmic"] = _cosmic_flag(frame, cfg)
        frame.pop("data", None)
        frames.append(frame)
        if progress is not None:
            progress(i + 1, total)
    ref_data = None       # the alignment grid is no longer needed
    frames.sort(key=lambda f: (f["mjd"] if f["mjd"] is not None
                               else float("inf")))
    n = result.group_n
    points = [_build_point(frames[i:i + n], cfg)
              for i in range(0, len(frames), n)]
    _fill_neighbour_zp(points, cfg)
    _flag_clouds(points, cfg)
    if cfg.detrend_policy != "off":
        info = detrend_series(
            points, "auto" if cfg.detrend_policy == "auto" else "airmass")
        result.detrend = info
        if info:
            for p, d in zip(points, info["detrended"]):
                p.mag_detrended = d
    for i, p in enumerate(points):
        p.index = i
    result.points = points
    result.band = cfg.band or cfg.fallback_band
    return result


# ---------------- D20: cadence guard (analysis layer) ----------------

def _median_cadence(points):
    # @return: the median spacing in seconds, or None with <2 points
    mids = sorted(p.mjd for p in points if p.mjd is not None)
    if len(mids) < 2:
        return None
    gaps = [(mids[i + 1] - mids[i]) * 86400.0 for i in range(len(mids) - 1)]
    gaps = [g for g in gaps if g > 0]
    if not gaps:
        return None
    return float(np.median(gaps))


def _msg(es, en):
    # @return: a bilingual message pair (the panel picks the language)
    return {"es": es, "en": en}


def cadence_guard(points, kind, duration_h=None, period_h=None,
                  period_d=None):
    # D20: warn in plain language when the cadence cannot resolve the
    # type. It never blocks: the observer decides. "red" is reserved for
    # a transit whose ingress is lost (fewer than three points).
    # @args: points - measured SeriesPoints, kind - project kind,
    #        duration_h - transit duration (h), period_h - HADS period (h),
    #        period_d - variable period (days)
    # @return: {"level": ok|warn|red, "cadence_s", "messages": [{es,en}]}
    cad = _median_cadence(points)
    msgs, level = [], "ok"
    if cad is None:
        return {"level": level, "cadence_s": None, "messages": msgs}
    kind = (kind or "").lower()
    if kind == "transit":
        if duration_h:
            ingress_s = 0.15 * float(duration_h) * 3600.0
            pts = ingress_s / cad
            if pts < 3:
                level = "red"
                msgs.append(_msg(
                    "la cadencia deja {:.1f} puntos por ingress: el "
                    "ingress se pierde".format(pts),
                    "the cadence leaves {:.1f} points per ingress: the "
                    "ingress is lost".format(pts)))
            elif pts < 5:
                level = "warn"
                msgs.append(_msg(
                    "solo {:.1f} puntos por ingress: justo para "
                    "resolverlo".format(pts),
                    "only {:.1f} points per ingress: barely enough".format(
                        pts)))
        else:
            level = "warn"
            msgs.append(_msg(
                "sin la duración del tránsito no se puede comprobar el "
                "ingress: revisa la cadencia",
                "without the transit duration the ingress cannot be "
                "checked: review the cadence"))
    elif kind == "hads":
        from . import hads as hads_mod
        if cad > hads_mod.CADENCE_CAP_S:
            level = "warn"
            msgs.append(_msg(
                "cadencia de {:.0f} s: por encima del tope AAVSO de "
                "{:.0f} s".format(cad, hads_mod.CADENCE_CAP_S),
                "cadence {:.0f} s: above the AAVSO cap of {:.0f} s".format(
                    cad, hads_mod.CADENCE_CAP_S)))
        if period_h:
            per_cycle = float(period_h) * 3600.0 / cad
            if per_cycle < hads_mod.POINTS_PER_CYCLE:
                level = "warn"
                msgs.append(_msg(
                    "{:.0f} puntos por ciclo: hacen falta {}".format(
                        per_cycle, hads_mod.POINTS_PER_CYCLE),
                    "{:.0f} points per cycle: {} are needed".format(
                        per_cycle, hads_mod.POINTS_PER_CYCLE)))
    elif kind == "variable" and period_d:
        if cad > float(period_d) * 86400.0 / 2.0:
            level = "warn"
            msgs.append(_msg(
                "cadencia de {:.0f} s: por debajo del criterio de Nyquist "
                "para P = {:.3f} d".format(cad, float(period_d)),
                "cadence {:.0f} s: below Nyquist for P = {:.3f} d".format(
                    cad, float(period_d))))
    return {"level": level, "cadence_s": cad, "messages": msgs}


# ---------------- D35: multi-night QC (ZP and band guard) ----------

def night_qc(points, zp_sigma=3.0):
    # D35: per-night zero-point check against the series median and the
    # band guard. Mixed filters are never combined into one magnitude
    # curve: the guard says so out loud.
    # @args: points - measured SeriesPoints, zp_sigma - offset threshold
    # @return: {"level": ok|warn, "nights": {night: zp}, "filters": [...],
    #          "messages": [{es,en}]}
    msgs, level = [], "ok"
    filters = sorted({p.filter for p in points if p.filter})
    if len(filters) > 1:
        level = "warn"
        msgs.append(_msg(
            "hay varios filtros ({}): no se combinan en una sola curva de "
            "magnitudes".format(", ".join(filters)),
            "several filters ({}): they are not combined into one "
            "magnitude curve".format(", ".join(filters))))
    by_night = {}
    for p in points:
        if p.zp is None:
            continue
        by_night.setdefault(_night_of(p.mjd), []).append(p.zp)
    meds = {n: float(np.median(v)) for n, v in by_night.items() if v}
    if len(meds) >= 2:
        arr = np.asarray(list(meds.values()), dtype=np.float64)
        gm = float(np.median(arr))
        mad = float(np.median(np.abs(arr - gm)))
        if mad > 0.0:
            for night, m in sorted(meds.items(),
                                   key=lambda kv: (kv[0] is None, kv[0])):
                if abs(m - gm) > zp_sigma * 1.4826 * mad:
                    level = "warn"
                    msgs.append(_msg(
                        "la noche {} tiene el punto cero desplazado "
                        "({:+.3f} mag)".format(_night_label(night),
                                              m - gm),
                        "night {} has a shifted zero point "
                        "({:+.3f} mag)".format(_night_label(night),
                                               m - gm)))
    return {"level": level,
            "nights": {str(n): m for n, m in meds.items()},
            "filters": filters, "messages": msgs}
