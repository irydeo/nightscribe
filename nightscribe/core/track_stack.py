############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Track & stack: ingestion, solve and registration
# (ADR-062, phase 2)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Turning a visit's frames into something stackable.

Three questions have to be answered before a single pixel is added:

1. **When** was each frame taken. The instant that represents an
   observation is the MIDDLE of the exposure, not its start: an object
   that moves is at its reported position at the middle, and using the
   start biases it by `rate * EXPTIME / 2`.
2. **Where** is the frame in the sky. Solving every one of the hundreds
   of frames is unaffordable, so the first one is solved with ASTAP and
   the rest are registered against it (rotation about the centre plus a
   subpixel translation, `core/register.py`); the per-frame WCS is the
   reference WCS composed with that transform. The risk is the field's
   differential distortion, so a quality control solves a couple of
   frames directly and compares.
3. **Was the sequence dithered?** The MPC is emphatic: without dithering
   the pattern noise stacks into detections that look real. The
   registration translations already tell us whether the observer moved
   the telescope, so the warning is free.

Reading a frame is not obvious either: the camera writes unsigned 16-bit
as int16 with BZERO, and astropy refuses to memory-map that, so
`core.calibration.read_image` is reused here (D32).
"""

import datetime
import logging
import math
from dataclasses import dataclass, field

import numpy as np

from . import calibration, coords, fits_meta, register, solve

logger = logging.getLogger(__name__)

# A sequence whose frames all land within this many pixels of each other
# was not dithered: the pattern noise of the sensor stays put and stacks
# into phantom detections (the MPC's own warning).
DITHER_MIN_SPREAD_PX = 5.0
# The composed WCS is accepted when it agrees with a direct solve within
# this many arcseconds; beyond it the differential distortion is biting.
WCS_QC_TOL_ARCSEC = 0.3


@dataclass
class Frame:
    # One light frame, with everything the stacking needs to know.
    path: str
    header: dict = field(default_factory=dict)
    filter: str | None = None
    exptime_s: float | None = None
    date_obs: str | None = None
    mjd: float | None = None
    jd_start: float | None = None
    t_mid_jd: float | None = None
    t_mid_mjd: float | None = None
    wcs: object = None                 # astropy WCS of this frame
    transform: dict | None = None      # register.estimate_transform result
    failed_register: bool = False
    object_ra: float | None = None
    object_dec: float | None = None
    object_xy: tuple | None = None


@dataclass
class DitherReport:
    dithered: bool
    spread_px: float
    note: str = ""


@dataclass
class WcsQCReport:
    checked: int = 0
    max_offset_arcsec: float = 0.0
    ok: bool = True
    note: str = ""


def load_sequence(paths, cfg=None):
    # @args: paths - the visit's FITS paths, cfg - Config (unused for now,
    #        kept for the callers that will pass thresholds)
    # @return: list[Frame]
    # The header is all we read here: the pixels are not touched until the
    # stacking asks for them (and then only the region it needs).
    out = []
    for path in paths:
        header = calibration.read_header(path)
        meta = fits_meta.meta_from_header(header)
        frame = Frame(path=str(path), header=header,
                      filter=meta.get("filter"), exptime_s=meta.get("exptime_s"),
                      date_obs=meta.get("date_obs"), mjd=meta.get("mjd"))
        if frame.mjd is not None:
            frame.jd_start = frame.mjd + 2400000.5
        if frame.jd_start is not None and frame.exptime_s:
            # the middle of the exposure: half the exposure in days
            frame.t_mid_jd = frame.jd_start + float(frame.exptime_s) / 172800.0
            frame.t_mid_mjd = frame.t_mid_jd - 2400000.5
        else:
            frame.t_mid_jd = frame.jd_start
            frame.t_mid_mjd = frame.mjd
        out.append(frame)
    out.sort(key=lambda f: f.t_mid_jd if f.t_mid_jd is not None else 0.0)
    return out


def _wcs_from_cards(cards):
    # @args: cards - WCS cards (dict)
    # @return: an astropy WCS
    from astropy.io import fits
    from astropy.wcs import WCS
    header = fits.Header()
    for key, value in (cards or {}).items():
        try:
            header[key] = value
        except (ValueError, TypeError):
            continue
    return WCS(header)


def solve_reference(frames, cfg=None, cancel=None, progress=None):
    # @args: frames - list[Frame], cfg - Config, cancel - callable,
    #        progress - callable(done, total, label)
    # @return: (reference Frame, astropy WCS) or (None, None)
    # The reference is the first frame that carries a WCS already (a
    # solved frame) or, failing that, the one the solver resolves. The
    # first frame is the convention (the plan): it keeps the grid stable
    # and the registration direction constant.
    if not frames:
        return None, None
    for frame in frames:
        cards = solve.solved_cards(frame.path)
        if not cards and cancel is not None and cancel():
            return None, None
        if not cards:
            if progress is not None:
                progress(0, 1, frame.path)
            cards = solve.solve(frame.path, cancel=cancel)
        if cards:
            frame.wcs = _wcs_from_cards(cards)
            return frame, frame.wcs
    return None, None


def register_sequence(frames, ref_index=None, allow_rotation=False,
                      progress=None, cancel=None):
    # @args: frames - list[Frame] with a solved reference, ref_index -
    #        which frame is the grid (default: the solved one), allow_rotation
    #        - also fit a rigid rotation (slower, for alt-az without derotator),
    #        progress/cancel - as usual
    # @return: the reference Frame
    # The transform is ESTIMATED by core/register.py (star voting, proven);
    # the RESAMPLING is scipy's spline, which keeps the shape of a point
    # source better than the bilinear used for a quick look. A frame whose
    # registration is not trusted inherits the previous one and is marked;
    # it is never silently trusted.
    ref = frames[ref_index] if ref_index is not None else None
    if ref is None or ref.wcs is None:
        # the grid has to be a frame we actually know the sky of
        ref = next((f for f in frames if f.wcs is not None), frames[0])
    ref_data, _ = calibration.read_image(ref.path)
    ref_stars = register.detect_stars(register.source_image(ref_data))
    previous = None
    total = len(frames)
    for index, frame in enumerate(frames):
        if cancel is not None and cancel():
            break
        if frame is ref:
            frame.transform = {"angle": 0.0, "dx": 0.0, "dy": 0.0,
                               "quality": 100.0, "rms_px": 0.0}
        else:
            data, _ = calibration.read_image(frame.path)
            # the guess is the PREVIOUS frame's transform, never the
            # reference's identity: a wrong guess drags the star voting
            # into a bad minimum (measured: a 2 px shift read as -29 px)
            tr = register.estimate_transform(
                ref_data, data, guess=previous, ref_stars=ref_stars,
                allow_rotation=allow_rotation)
            if register.trusted(tr):
                frame.transform = tr
                previous = tr
            else:
                frame.transform = dict(previous) if previous else tr
                frame.failed_register = True
        if frame.transform and frame.wcs is None:
            shape = (int(frame.header.get("NAXIS1", 1)),
                     int(frame.header.get("NAXIS2", 1)))
            frame.wcs = compose_wcs(ref.wcs, frame.transform, shape=shape)
        if progress is not None:
            progress(index + 1, total, frame.path)
    return ref


def compose_wcs(w0, tr, shape=None):
    # @args: w0 - the reference astropy WCS, tr - a register transform,
    #        shape - (naxis1, naxis2) of the frames (a WCS built only from
    #        cards has no pixel_shape, and the rotation centre needs it)
    # @return: the frame's astropy WCS (TAN stays linear)
    # Same algebra as core/register.compose_wcs: the frame's CD is the
    # reference CD with the rotation applied on the right, and its CRPIX
    # is where the reference's CRPIX lands on the frame's grid. Confusing
    # the direction of the transform is the classic bug here, so this
    # delegates to register.ref_to_src_point.
    from astropy.wcs import WCS
    angle, dx, dy = tr["angle"], tr["dx"], tr["dy"]
    ca, sa = math.cos(angle), math.sin(angle)
    cd = w0.wcs.cd
    new_cd = np.array([
        [cd[0][0] * ca + cd[0][1] * sa, cd[0][0] * (-sa) + cd[0][1] * ca],
        [cd[1][0] * ca + cd[1][1] * sa, cd[1][0] * (-sa) + cd[1][1] * ca]])
    if shape is not None:
        naxis1, naxis2 = int(shape[0]), int(shape[1])
    elif w0.pixel_shape is not None:
        naxis1, naxis2 = int(w0.pixel_shape[0]), int(w0.pixel_shape[1])
    else:
        naxis1, naxis2 = 1, 1
    q0 = (w0.wcs.crpix[0] - 1.0, w0.wcs.crpix[1] - 1.0)
    px, py = register.ref_to_src_point(tr, q0, (naxis2, naxis1))
    w = WCS(naxis=2)
    w.wcs.ctype = list(w0.wcs.ctype)
    w.wcs.crval = list(w0.wcs.crval)
    w.wcs.crpix = [px + 1.0, py + 1.0]
    w.wcs.cd = new_cd
    w.wcs.radesys = w0.wcs.radesys or "ICRS"
    if w0.wcs.equinox:
        w.wcs.equinox = w0.wcs.equinox
    return w


def object_positions(frames, motion):
    # @args: frames - list[Frame], motion - callable(jd) -> (ra_deg, dec_deg)
    #        (core.ephemeris.motion_interpolator)
    # @return: the frames, with object_ra/object_dec/object_xy filled
    # The object is evaluated at each frame's own T_mid, which is what
    # makes the stacked point represent the instant that gets reported.
    for frame in frames:
        if frame.t_mid_jd is None or frame.wcs is None:
            continue
        pos = motion(frame.t_mid_jd)
        if not pos:
            continue
        ra, dec = pos
        frame.object_ra, frame.object_dec = ra, dec
        try:
            x, y = frame.wcs.all_world2pix([[ra, dec]], 0)[0]
        except Exception:                       # a WCS that cannot invert
            continue
        frame.object_xy = (float(x), float(y))
    return frames


def dither_check(frames):
    # @args: frames - list[Frame] with transforms
    # @return: DitherReport
    # The translations of the registration are the dither, measured: if
    # every frame landed on the same spot, the telescope never moved and
    # the sensor's fixed pattern will stack (the MPC's warning).
    shifts = [(f.transform["dx"], f.transform["dy"]) for f in frames
              if f.transform and not f.failed_register]
    if len(shifts) < 3:
        return DitherReport(True, 0.0, "too few registered frames to tell")
    xs = np.asarray([s[0] for s in shifts])
    ys = np.asarray([s[1] for s in shifts])
    spread = float(math.hypot(xs.std(), ys.std()))
    if spread < DITHER_MIN_SPREAD_PX:
        return DitherReport(False, spread,
                            "the frames were not dithered: the sensor's "
                            "pattern noise stacks into phantom detections")
    return DitherReport(True, spread, "")


def verify_composed_wcs(frames, sample=2, tol_arcsec=WCS_QC_TOL_ARCSEC,
                        cancel=None):
    # @args: frames - list[Frame], sample - how many frames to solve again,
    #        tol_arcsec - agreement threshold, cancel - callable
    # @return: WcsQCReport
    # The composed WCS assumes the field is rigid. Solving a frame again
    # and comparing where the two put the same sky point measures how much
    # the distortion moved it; beyond the tolerance the caller warns (and
    # a future phase would interpolate the distortion).
    candidates = [f for f in frames if f.wcs is not None and not f.failed_register]
    if len(candidates) < 3 or sample <= 0:
        return WcsQCReport(0, 0.0, True, "not enough frames to check")
    step = max(1, len(candidates) // (sample + 1))
    report = WcsQCReport()
    for frame in candidates[::step][:sample]:
        if cancel is not None and cancel():
            break
        cards = solve.solve(frame.path, cancel=cancel)
        if not cards:
            continue
        direct = _wcs_from_cards(cards)
        naxis1 = int(frame.header.get("NAXIS1", 1))
        naxis2 = int(frame.header.get("NAXIS2", 1))
        points = [(0.0, 0.0), (naxis1 - 1.0, 0.0),
                  (0.0, naxis2 - 1.0), (naxis1 - 1.0, naxis2 - 1.0)]
        for x, y in points:
            sky = frame.wcs.all_pix2world([[x, y]], 0)[0]
            dx, dy = direct.all_world2pix([sky], 0)[0]
            offset = math.hypot(dx - x, dy - y) * _arcsec_per_pixel(frame.wcs)
            report.max_offset_arcsec = max(report.max_offset_arcsec, offset)
        report.checked += 1
    report.ok = report.max_offset_arcsec <= tol_arcsec
    if not report.ok:
        report.note = (f"the composed WCS is off by up to "
                       f"{report.max_offset_arcsec:.2f}\" against a direct "
                       f"solve: the field's distortion is biting")
    return report


def _arcsec_per_pixel(wcs):
    # @args: wcs - astropy WCS
    # @return: the plate scale in arcsec/pixel (mean of the two axes)
    cd = wcs.wcs.cd
    scale = math.sqrt(abs(cd[0][0] * cd[1][1] - cd[0][1] * cd[1][0]))
    return scale * 3600.0


def sequence_motion(frames, name, site="", lat=None, lon=None):
    # @args: frames - list[Frame], name - Horizons designation, site - MPC
    #        code, lat/lon - site coordinates when known
    # @return: a callable(jd) -> (ra_deg, dec_deg), or None
    # A thin wrapper so the caller does not have to remember the Horizons
    # step: one minute over the sequence's own span, interpolated.
    from . import ephemeris
    from .sources import horizons
    stamps = [f.t_mid_jd for f in frames if f.t_mid_jd is not None]
    if not stamps:
        return None
    day = coords.datetime_from_jd(min(stamps)).date()
    rows = horizons.ephemeris(name, center=site or "",
                              start=str(day),
                              stop=str(day + datetime.timedelta(days=1)),
                              step="1 m")
    return ephemeris.motion_interpolator(rows) if rows else None
