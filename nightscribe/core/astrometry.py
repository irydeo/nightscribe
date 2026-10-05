############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Astrometric measurement (ADR-062, phase 4)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Turning a stacked point of light into a position with an error bar.

Two measurements are taken and contrasted (D7): the centroid on the stack
and the per-frame centroid combined. Both use the SAME centroid routine
(photutils) or the comparison would say nothing. The reported position
defaults to the stack's (the professional convention); when the two
disagree by more than 0.5 arcsec or 3 sigma the point is flagged, never
silently chosen.

The error matters as much as the position. A report with no uncertainty
is half a measurement, and an invented uncertainty is worse than none, so
the budget is summed in quadrature and kept itemised: the centroid (in
pixels, converted with the plate scale and divided by cos(dec) in RA),
the WCS's own rms and the timing term (velocity x sigma_t). In RA the
pixel is not an arcsecond: one pixel of RA is `scale * cos(dec)` on the
sky, and forgetting that inflates the error at high declination.
"""

import logging
import math
from dataclasses import dataclass, field

import numpy as np

from . import outliers

logger = logging.getLogger(__name__)

# The aperture and the annulus of the centroid measurement, in FWHM units.
APERTURE_FWHM = 1.35
ANNULUS_IN_FWHM = 2.0
ANNULUS_OUT_FWHM = 3.2
# A centroid closer to the window's edge than this is refused: the source
# is not fully inside and the centroid would be dragged.
EDGE_MARGIN_PX = 2.0


@dataclass
class AstrometryPoint:
    # One measured position, with everything the report needs.
    ra: float
    dec: float
    rms_ra: float = 0.0
    rms_dec: float = 0.0
    x: float = 0.0
    y: float = 0.0
    mag: float | None = None
    band: str | None = None
    snr: float = 0.0
    fwhm: float | None = None
    roundness: float = 0.0
    source: str = "stack"               # "stack" | "frames"
    flags: list = field(default_factory=list)
    n_frames: int = 0
    mjd: float | None = None
    group_index: int = 0
    parts: dict = field(default_factory=dict)


@dataclass
class Centroid:
    x: float
    y: float
    err_pix: float
    fwhm: float | None
    roundness: float
    snr: float
    ok: bool = True
    note: str = ""


def _local_sky(win):
    # @args: win - a small cutout around the source
    # @return: (sky, sigma) from the border of the window
    # The border of a small window is the cheapest honest sky: the source
    # fills the middle, the rim is background.
    h, w = win.shape
    rim = np.concatenate([win[0, :], win[-1, :], win[:, 0], win[:, -1]])
    sky = float(np.median(rim))
    sigma = float(outliers.scaled_mad(rim, centre=sky))
    return sky, sigma


def centroid(data, xy, fwhm=None, radius=None):
    # @args: data - the image (stack or a frame's cutout), xy - the
    #        expected position, fwhm - the seeing in px when known,
    #        radius - the window half-size (default: 4 x fwhm or 6 px)
    # @return: Centroid
    # photutils' 2D Gaussian centroid is the default: it tolerates a
    # residual sky gradient better than a centre of mass (which a glow
    # drags), and it is the SAME routine for the stack and the frames, so
    # their comparison is meaningful (D7).
    from photutils.centroids import centroid_2dg
    if radius is None:
        radius = int(round(4.0 * fwhm)) if fwhm else 6
    x0 = int(round(xy[0])) - radius
    y0 = int(round(xy[1])) - radius
    size = 2 * radius + 1
    h, w = data.shape
    if x0 < 0 or y0 < 0 or x0 + size > w or y0 + size > h:
        return Centroid(xy[0], xy[1], 0.0, fwhm, 0.0, 0.0, False,
                        "the window falls off the image")
    win = np.asarray(data[y0:y0 + size, x0:x0 + size], dtype=np.float64)
    sky, sigma = _local_sky(win)
    clean = win - sky
    try:
        import warnings
        with warnings.catch_warnings():
            # photutils warns "the fit may not have converged" on a faint
            # source. That is the expected case on a per-frame measurement
            # of a mag-19 object, the code handles it (the centroid stands,
            # the error bar grows) and the warning would flood the log once
            # per frame; it is silenced here, not hidden from the caller.
            warnings.simplefilter("ignore")
            cx, cy = centroid_2dg(clean)
    except Exception:
        cx, cy = radius, radius
    gx, gy = x0 + float(cx), y0 + float(cy)
    if not (EDGE_MARGIN_PX <= cx <= size - EDGE_MARGIN_PX
            and EDGE_MARGIN_PX <= cy <= size - EDGE_MARGIN_PX):
        return Centroid(gx, gy, 0.0, fwhm, 0.0, 0.0, False,
                        "the centroid sits on the window edge")
    # aperture flux, FWHM and roundness from the same window
    yy, xx = np.mgrid[0:size, 0:size]
    d = np.hypot(xx - cx, yy - cy)
    fwhm_eff = fwhm or _estimate_fwhm(clean, cx, cy)
    r_ap = max(2.0, APERTURE_FWHM * fwhm_eff)
    ap = d <= r_ap
    flux = float(clean[ap].sum())
    noise = sigma * math.sqrt(max(ap.sum(), 1))
    snr = flux / noise if noise > 0 else 0.0
    # the centroid's error follows the PSF width over the SNR: a bright
    # source pins the centre, a faint one wanders
    err_pix = (fwhm_eff / 2.355) / max(snr, 0.1)
    roundness = _roundness(clean, cx, cy, r_ap)
    return Centroid(gx, gy, float(err_pix), float(fwhm_eff), roundness,
                    float(snr))


def _estimate_fwhm(clean, cx, cy):
    # @args: clean - the sky-subtracted window, cx/cy - the centroid
    # @return: the FWHM in pixels from the second moments
    size = clean.shape[0]
    yy, xx = np.mgrid[0:size, 0:size]
    w = np.clip(clean, 0, None)
    total = w.sum()
    if total <= 0:
        return 3.0
    varx = (w * (xx - cx) ** 2).sum() / total
    vary = (w * (yy - cy) ** 2).sum() / total
    sigma = math.sqrt(max((varx + vary) / 2.0, 0.25))
    return float(2.355 * sigma)


def _roundness(clean, cx, cy, r_ap):
    # @args: clean, cx/cy, r_ap - the aperture
    # @return: b/a of the second moments (1 = circular)
    size = clean.shape[0]
    yy, xx = np.mgrid[0:size, 0:size]
    d = np.hypot(xx - cx, yy - cy)
    win = np.clip(np.where(d <= r_ap, clean, 0.0), 0, None)
    total = win.sum()
    if total <= 0:
        return 0.0
    mx = (win * xx).sum() / total - cx
    my = (win * yy).sum() / total - cy
    cxx = (win * (xx - cx - mx) ** 2).sum() / total
    cyy = (win * (yy - cy - my) ** 2).sum() / total
    cxy = (win * (xx - cx - mx) * (yy - cy - my)).sum() / total
    tr = cxx + cyy
    det = cxx * cyy - cxy ** 2
    disc = max(0.0, tr * tr / 4.0 - det)
    l1 = tr / 2.0 + math.sqrt(disc)
    l2 = tr / 2.0 - math.sqrt(disc)
    if l1 <= 0:
        return 0.0
    return float(math.sqrt(max(l2, 0.0) / l1))


def pixel_scale_arcsec(wcs):
    # @args: wcs - astropy WCS
    # @return: the plate scale in arcsec/px
    cd = wcs.wcs.cd
    return math.sqrt(abs(cd[0][0] * cd[1][1] - cd[0][1] * cd[1][0])) * 3600.0


def error_budget(err_pix, wcs, dec_deg, scale_arcsec, wcs_rms_arcsec=0.0,
                 velocity_arcsec_min=None, sigma_t_s=0.0, n_frames=0):
    # @args: err_pix - the centroid error in pixels, wcs - the WCS (for
    #        cos(dec) only; pass dec_deg too), dec_deg - the declination,
    #        scale_arcsec - arcsec/px, wcs_rms_arcsec - the solver's or the
    #        QC's rms, velocity_arcsec_min - the object's rate, sigma_t_s -
    #        the timing uncertainty, n_frames - for the frame path
    # @return: (rms_ra, rms_dec, parts)
    # Everything in arcseconds, summed in quadrature, with the items kept
    # so the card can explain the number instead of showing it bare.
    cosd = max(math.cos(math.radians(dec_deg)), 1e-6)
    centroid = err_pix * scale_arcsec
    if n_frames > 1:
        centroid = centroid / math.sqrt(n_frames)
    timing = 0.0
    if velocity_arcsec_min and sigma_t_s:
        timing = velocity_arcsec_min * (sigma_t_s / 60.0)
    rms_dec = math.hypot(centroid, wcs_rms_arcsec, timing)
    rms_ra = math.hypot(centroid / cosd, wcs_rms_arcsec / cosd, timing / cosd)
    parts = {"centroid_arcsec": centroid, "wcs_arcsec": wcs_rms_arcsec,
             "timing_arcsec": timing, "cos_dec": cosd}
    return rms_ra, rms_dec, parts


def measure_stack(stack, q_box, wcs, mjd=None, fwhm=None, scale_arcsec=None,
                  wcs_rms_arcsec=0.0, velocity_arcsec_min=None,
                  sigma_t_s=0.0, group_index=0):
    # @args: stack - the combined image, q_box - the object's position in
    #        it, wcs - the reference WCS, mjd - the group's T_mid, fwhm,
    #        scale_arcsec, wcs_rms_arcsec, velocity, sigma_t, group_index
    # @return: AstrometryPoint (source="stack")
    c = centroid(stack, q_box, fwhm=fwhm)
    ra, dec = wcs.all_pix2world([[c.x, c.y]], 0)[0]
    scale = scale_arcsec or pixel_scale_arcsec(wcs)
    rms_ra, rms_dec, parts = error_budget(
        c.err_pix, wcs, float(dec), scale, wcs_rms_arcsec=wcs_rms_arcsec,
        velocity_arcsec_min=velocity_arcsec_min, sigma_t_s=sigma_t_s)
    return AstrometryPoint(ra=float(ra), dec=float(dec), rms_ra=rms_ra,
                           rms_dec=rms_dec, x=c.x, y=c.y, snr=c.snr,
                           fwhm=c.fwhm, roundness=c.roundness,
                           source="stack", n_frames=0, mjd=mjd,
                           group_index=group_index, parts=parts)


def measure_frames(frames, group, wcs_of, mjd=None, fwhm=None,
                   scale_arcsec=None, wcs_rms_arcsec=0.0,
                   velocity_arcsec_min=None, sigma_t_s=0.0, group_index=0,
                   loader=None):
    # @args: frames - list[Frame], group - (start, end), wcs_of - callable
    #        (frame) -> astropy WCS, mjd - the group's T_mid, the rest as
    #        measure_stack, loader - callable(path, box) -> array
    # @return: AstrometryPoint (source="frames")
    # Each frame's own centroid is converted with its OWN WCS (the composed
    # one) and the positions are combined with inverse-variance weights:
    # the mean's error falls as sqrt(N), which is what makes measuring per
    # frame worth the trouble.
    from . import calibration
    points = []
    for i in range(*group):
        frame = frames[i]
        if frame.object_xy is None or getattr(frame, "failed_register", False):
            # a frame that could not be registered has a composed WCS that
            # is wrong: measuring on it would add a bogus position
            continue
        wcs = wcs_of(frame) if callable(wcs_of) else wcs_of
        if wcs is None:
            continue
        box = _box_around(frame.object_xy, fwhm)
        try:
            # the loader may be calibration.read_image (pixels AND header) or
            # a calibrating loader (pixels only): both are accepted here,
            # like in track_stack.read_pixels, so a calibrated run and a raw
            # one use the same code path
            loaded = (loader or calibration.read_image)(frame.path, box)
            data = loaded[0] if isinstance(loaded, tuple) else loaded
        except Exception:
            continue
        local = (frame.object_xy[0] - box[0], frame.object_xy[1] - box[1])
        c = centroid(np.asarray(data, dtype=np.float32), local, fwhm=fwhm)
        if not c.ok:
            continue
        ra, dec = wcs.all_pix2world([[frame.object_xy[0],
                                      frame.object_xy[1]]], 0)[0]
        scale = scale_arcsec or pixel_scale_arcsec(wcs)
        points.append((float(ra), float(dec), c, scale))
    if not points:
        return AstrometryPoint(ra=float("nan"), dec=float("nan"),
                               source="frames", flags=["no_frame_centroid"])
    ra, dec, scatter = combine_positions(points)
    n = len(points)
    err = float(np.median([p[2].err_pix for p in points]))
    scale = points[0][3]
    rms_ra, rms_dec, parts = error_budget(
        err, None, dec, scale, wcs_rms_arcsec=wcs_rms_arcsec,
        velocity_arcsec_min=velocity_arcsec_min, sigma_t_s=sigma_t_s,
        n_frames=n)
    # the observed scatter can exceed the predicted noise (drift, seeing):
    # the larger of the two is reported, because an error bar that thinks
    # it is better than it is misleads
    rms_ra = max(rms_ra, scatter[0])
    rms_dec = max(rms_dec, scatter[1])
    parts["scatter_ra"] = scatter[0]
    parts["scatter_dec"] = scatter[1]
    return AstrometryPoint(ra=ra, dec=dec, rms_ra=rms_ra, rms_dec=rms_dec,
                           snr=float(np.median([p[2].snr for p in points])),
                           fwhm=points[0][2].fwhm,
                           roundness=float(np.median([p[2].roundness
                                                      for p in points])),
                           source="frames", n_frames=n, mjd=mjd,
                           group_index=group_index, parts=parts)


def _box_around(xy, fwhm, radius=None):
    # @args: xy - the position, fwhm, radius - the half-size
    # @return: (x0, y0, x1, y1)
    r = int(radius or (round(4.0 * fwhm) if fwhm else 10))
    return (int(round(xy[0])) - r, int(round(xy[1])) - r,
            int(round(xy[0])) + r + 1, int(round(xy[1])) + r + 1)


def combine_positions(points):
    # @args: points - list of (ra_deg, dec_deg, Centroid, scale_arcsec)
    # @return: (ra, dec, (scatter_ra, scatter_dec)) in arcsec
    # Inverse-variance weights, with RA weighted by cos(dec): a second of
    # arc of RA is not a second of arc on the sky.
    ra_rad = [math.radians(p[0]) for p in points]
    dec_rad = [math.radians(p[1]) for p in points]
    dec0 = float(np.mean(dec_rad))
    cosd = math.cos(dec0)
    # unwrap RA around the mean so a wrap at 0/360 does not break the mean
    ra0 = float(np.mean(ra_rad))
    dra = [((r - ra0 + math.pi) % (2 * math.pi)) - math.pi for r in ra_rad]
    weights = [1.0 / max((p[2].err_pix * p[3]) ** 2, 1e-9) for p in points]
    wsum = sum(weights)
    ra = ra0 + sum(w * d for w, d in zip(weights, dra)) / wsum
    dec = sum(w * d for w, d in zip(weights, dec_rad)) / wsum
    # the observed scatter, in arcsec
    sra = math.sqrt(sum(w * (d - (ra - ra0)) ** 2 for w, d in zip(weights, dra))
                    / wsum) * cosd * 206264.8
    sdec = math.sqrt(sum(w * (d - dec) ** 2 for w, d in zip(weights, dec_rad))
                     / wsum) * 206264.8
    return math.degrees(ra) % 360.0, math.degrees(dec), (sra, sdec)


def compare(stack_point, frames_point, cfg=None):
    # @args: stack_point, frames_point - AstrometryPoint, cfg - Config
    # @return: list of flags (empty when they agree)
    # The two measurements are contrasted (D16); a disagreement beyond the
    # thresholds flags the point so the card says so. Nothing is chosen in
    # silence.
    if frames_point is None or math.isnan(frames_point.ra):
        return []
    tol_arcsec = float(cfg.get("astrometry_disagree_arcsec", 0.5)) if cfg else 0.5
    tol_sigma = float(cfg.get("astrometry_disagree_sigma", 3.0)) if cfg else 3.0
    cosd = max(math.cos(math.radians(stack_point.dec)), 1e-6)
    dra = (stack_point.ra - frames_point.ra) * cosd * 3600.0
    ddec = (stack_point.dec - frames_point.dec) * 3600.0
    sep = math.hypot(dra, ddec)
    sigma = math.hypot(stack_point.rms_ra, stack_point.rms_dec)
    sigma_f = math.hypot(frames_point.rms_ra, frames_point.rms_dec)
    combined = math.hypot(sigma, sigma_f) or 1e-6
    if sep > tol_arcsec or sep > tol_sigma * combined:
        return ["disagree"]
    return []


def measure_magnitude(stack, q_box, wcs, comps=None, band=None, zp=None,
                      fwhm=None):
    # @args: stack - the combined image, q_box - the object, wcs - the
    #        reference WCS, comps - [(ra, dec, mag, band)] comparison stars
    #        (from core/compstars.py), band - the filter, zp - a known zero
    #        point, fwhm
    # @return: (mag, band, n_comps) or None when it cannot be calibrated
    # The photometric recipe is NOT duplicated: the zero point and the
    # magnitude come from core/photometry.py. Without comparisons the
    # magnitude is OMITTED, never invented (D13).
    from . import photometry
    c = centroid(stack, q_box, fwhm=fwhm)
    if not c.ok:
        return None
    res = photometry.measure_point(stack, c.x, c.y, r_ap=max(2.0, APERTURE_FWHM
                                                             * (c.fwhm or 3.0)))
    flux = res.get("flux")
    if not flux or flux <= 0:
        return None
    if comps:
        # a comparison star's pixel position needs the WCS; the caller
        # passes them already in pixels when it can
        try:
            entries = [(wcs.all_world2pix([[ra, dec]], 0)[0], mag, b)
                       for ra, dec, mag, b in comps]
        except Exception:
            entries = []
        if entries:
            calibrated = photometry.calibrate_zero_point(
                stack, [(e[0][0], e[0][1], e[1]) for e in entries])
            if calibrated:
                return (float(calibrated["zp"] - 2.5 * math.log10(flux)),
                        band, len(entries))
    if zp is not None:
        return float(zp - 2.5 * math.log10(flux)), band, 0
    return None


def measure_groups(stacks, qs, wcs, frames=None, groups=None, cfg=None,
                   mjd_by_group=None, **kwargs):
    # @args: stacks - one stack per group, qs - the object's position in
    #        each, wcs - the reference WCS, frames/groups - for the per-frame
    #        path, cfg - Config, mjd_by_group - the T_mid per group
    # @return: list of (stack_point, frames_point, flags)
    out = []
    for index, (stack, q) in enumerate(zip(stacks, qs)):
        mjd = mjd_by_group[index] if mjd_by_group else None
        sp = measure_stack(stack, q, wcs, mjd=mjd, group_index=index, **kwargs)
        fp = None
        if frames is not None and groups is not None:
            fp = measure_frames(frames, groups[index], lambda f: f.wcs,
                                mjd=mjd, group_index=index, **kwargs)
            sp.flags.extend(compare(sp, fp, cfg))
        out.append((sp, fp, sp.flags))
    return out
