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
    group_n: int = 1
    guide_jump_px: float = 2.0      # centroid off the reference (T7)
    cosmic_sigma: float = 8.0       # single-pixel spike over the noise
    zp_outlier_sigma: float = 3.0   # cloud / zero-point outlier (T7)


@dataclass
class SeriesPoint:
    # One point of the curve: the measured fluxes plus every honest flag.
    index: int = 0
    path: str = ""
    mjd: float = None               # mid exposure (T6)
    hjd: float = None
    filter: str = None
    exptime: float = None
    x: float = None
    y: float = None
    flux: float = None
    flux_err: float = None
    inst: float = None              # instrumental mag (goes to mag_raw)
    mag: float = None               # calibrated (catalog) or differential
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
    zp_err = math.sqrt(1.0 / sum(wts)) if sum(wts) > 0 else None
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


def _scintillation(cfg, mjd, span_s):
    # T4/H5: Young's scintillation with the site from Ajustes and the
    # target's altitude from the reference WCS and the point's instant.
    # @return: sigma in mag, or None
    if not span_s or mjd is None or cfg.wcs is None \
            or cfg.site_lon is None or cfg.site_lat is None:
        return None
    try:
        from . import coords
        ra, dec = cfg.wcs.pixel_to_sky(cfg.target_xy[0], cfg.target_xy[1])
        jd = mjd + variables.MJD0
        lst = coords.lst_degrees(jd, float(cfg.site_lon))
        alt, _az = coords.altaz(ra, dec, float(cfg.site_lat), lst)
        return photometry.scintillation_mag(alt, span_s,
                                            cfg.site_aperture_m,
                                            cfg.site_height_m)
    except Exception:
        return None


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

def _run_one(path, cfg):
    # One frame through the shared plate recipe (T1/T2 raw material): the
    # target and the comps' fluxes, plus the guard reason when refused.
    # @return: (frame dict, None) or (None, error string)
    try:
        header, data = fits_io.read_fits(path)
    except fits_io.FitsError as err:
        return None, str(err)
    meta = fits_meta.meta_from_header(header)
    pcfg = photometry.PlateConfig(
        target_xy=cfg.target_xy, entries=list(cfg.comp_set),
        header=header, wcs=cfg.wcs, band=cfg.band,
        fallback_band=cfg.fallback_band, radii=cfg.radii,
        sigmaclip=cfg.sigmaclip, sky_mode=cfg.sky_mode,
        color=cfg.color, target_bv=cfg.target_bv,
        site_gain=cfg.site_gain, site_ron=cfg.site_ron,
        site_flat=cfg.site_flat, site_saturate=cfg.site_saturate,
        site_lon=cfg.site_lon, site_lat=cfg.site_lat,
        site_aperture_m=cfg.site_aperture_m,
        site_height_m=cfg.site_height_m,
        require_catalog=(cfg.zp_mode == "catalog"))
    res = photometry.measure_plate(data, pcfg)
    mjd_mid, exptime = _mid_exposure(meta)
    return {"path": str(path), "data": data, "meta": meta, "res": res,
            "mjd": mjd_mid, "exptime": exptime,
            "filter": meta.get("filter")}, None


def _frame_flux(frame, cfg):
    # @return: (target net flux, its sigma) from the frame's PlateResult
    res = frame["res"]
    target = res.target or {}
    if not res.ok or target.get("flux") is None:
        return None, None
    err = photometry.ccd_flux_error(
        target.get("flux"), target.get("sky_pp"), target.get("n_pix"),
        gain=res.gain, ron=cfg.site_ron, exptime=frame.get("exptime"))
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
                        exptime=f.get("exptime")))
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


def _flag_gates(pt, group, cfg):
    # T7: saturation (the plate recipe refused the target), a cosmic ray
    # in the aperture and a guide jump. Marked, never deleted.
    for f in group:
        if not f["res"].ok:
            reason = (f["res"].reason or {})
            _add_flag(pt, "saturated" if reason.get("en") == "saturated"
                      else "unusable")
            continue
        res = f["res"]
        if res.col is None or res.target is None:
            continue
        sky_pp = res.target.get("sky_pp")
        r_ap = (cfg.radii or (photometry.R_AP,))[0]
        sigma = _sky_sigma(f["data"], res.col, res.row, r_ap)
        if _cosmic_hit(f["data"], res.col, res.row, r_ap, sky_pp, sigma,
                       cfg.cosmic_sigma):
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
    pt = SeriesPoint(path=first["path"], filter=first.get("filter"),
                     exptime=first.get("exptime"))
    pt.members = [f["path"] for f in group]
    fluxes, errs = [], []
    for f in group:
        tf, te = _frame_flux(f, cfg)
        fluxes.append(tf)
        errs.append(te)
    comb, comb_err, _used, _rej = _combine_fluxes(fluxes, errs)
    pt.flux, pt.flux_err = comb, comb_err
    pt.x, pt.y = _group_centroid(group)
    weights = [1.0 / (e ** 2) if (e and e > 0) else 1.0 for e in errs]
    pt.mjd = _weighted_mean([f["mjd"] for f in group], weights)
    pt.hjd = _hjd_of(pt.mjd, cfg.wcs, cfg.target_xy)
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
    good = [(i, p.zp) for i, p in enumerate(points)
            if p.zp is not None and "few_comps" not in p.flags]
    for i, p in enumerate(points):
        if p.zp is not None or "few_comps" not in p.flags:
            continue
        if not good:
            _add_flag(p, "no_zp")
            continue
        prev = [(j, z) for j, z in good if j < i]
        nxt = [(j, z) for j, z in good if j > i]
        if prev and nxt:
            j0, z0 = prev[-1]
            j1, z1 = nxt[0]
            z = z0 + (z1 - z0) * (i - j0) / float(j1 - j0)
        elif prev:
            z = prev[-1][1]
        else:
            z = nxt[0][1]
        p.zp = z
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
    frames = []
    for i, path in enumerate(paths):
        if cancel is not None and cancel():
            result.status = "incomplete"
            break
        frame, err = _run_one(path, cfg)
        if frame is None:
            result.errors[str(path)] = err
        else:
            frames.append(frame)
        if progress is not None:
            progress(i + 1, total)
    frames.sort(key=lambda f: (f["mjd"] if f["mjd"] is not None
                               else float("inf")))
    n = result.group_n
    points = [_build_point(frames[i:i + n], cfg)
              for i in range(0, len(frames), n)]
    _fill_neighbour_zp(points, cfg)
    _flag_clouds(points, cfg)
    for i, p in enumerate(points):
        p.index = i
    result.points = points
    result.band = cfg.band or cfg.fallback_band
    return result
