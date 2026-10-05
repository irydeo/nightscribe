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
import warnings
from dataclasses import dataclass, field

import numpy as np

from . import calibration, coords, fits_meta, outliers, register, solve

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
    register_note: str = ""            # why it failed, or how it was saved
    sky_sigma: float | None = None     # the frame's own noise (ADU), for the
    #                                    inverse-variance weights: the sky
    #                                    dominates for the faint objects this
    #                                    exists for, and a frame with more
    #                                    noise must weigh less
    object_ra: float | None = None
    object_dec: float | None = None
    object_xy: tuple | None = None


@dataclass
class DitherReport:
    dithered: bool
    spread_px: float
    note: str = ""


def usable(frame):
    # @args: frame - a Frame
    # @return: True when the frame can be stacked
    # A frame whose registration was not trusted inherits the previous
    # transform so the pipeline can keep going, but it must NOT be stacked:
    # stacking it misaligned is what dragged the base SNR from 15.8 down to
    # 11.4 on a night with two runs whose pointing jumped a whole field
    # (63 of 140 frames failed and went in crooked). It is left out and
    # counted instead.
    return frame.transform is not None and not frame.failed_register


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
        if not cards and solve.is_cancelled(cancel):
            return None, None
        if not cards:
            if progress is not None:
                progress(0, 1, frame.path)
            cards = solve.solve(frame.path, cancel=cancel)
        if cards:
            frame.wcs = _wcs_from_cards(cards)
            return frame, frame.wcs
    return None, None


# The frame's noise is measured on ONE PIXEL IN 4x4, and that is measured,
# not a hunch. On a real 2048x2048 frame of the 2025 UR visit, the scaled
# MAD of the whole frame takes 94.6 ms and the 4x4-sampled one 4.6 ms, and
# BOTH give 332.10 ADU, to the last digit: the MAD is a robust statistic of
# a stationary field, and 262k samples already fix its median. Over a
# 139-frame visit that is 0.8 s instead of 13.2 s, for the same number.
# The stars and the object are a small fraction of the pixels either way, so
# the median ignores them by construction at any sampling.
_NOISE_STEP = 4


def _frame_noise(data):
    # @args: data - a frame's pixels (ADU)
    # @return: the frame's robust noise in ADU, or None when it cannot be
    #          measured. This is the number the inverse-variance weighting
    #          of P1 stands on.
    try:
        arr = np.asarray(data)
        if arr.ndim == 2 and _NOISE_STEP > 1:
            arr = arr[::_NOISE_STEP, ::_NOISE_STEP]
        sigma = outliers.scaled_mad(arr.ravel())
    except Exception as err:
        logger.warning("the frame's noise could not be measured: %s", err)
        return None
    if sigma is None or not np.isfinite(sigma) or sigma <= 0:
        return None
    return float(sigma)


def session_fwhm(ref_data, ref_stars, sat=None):
    # @args: ref_data - the reference frame's pixels, ref_stars - its
    #        detect_stars output, sat - saturation ceiling
    # @return: the frame's median FWHM in pixels, or None when it cannot be
    #          measured. One call per session: the point spread is what the
    #          registration gate is judged against (register.rms_limit), so
    #          it has to come from the DATA, never from a constant.
    try:
        from . import photometry
        if ref_stars is None or len(ref_stars) == 0:
            return None
        return photometry.estimate_fwhm(ref_data, ref_stars[:, :2],
                                        sat_adu=sat)
    except Exception as err:
        logger.warning("the session's FWHM could not be measured: %s", err)
        return None


def register_sequence(frames, ref_index=None, allow_rotation=False,
                      progress=None, cancel=None, fwhm_px=None, sat=None):
    # @args: frames - list[Frame] with a solved reference, ref_index -
    #        which frame is the grid (default: the solved one), allow_rotation
    #        - fit a rigid rotation on the FIRST attempt (slower, for alt-az
    #        without derotator; the retry below does it anyway when needed),
    #        progress/cancel - as usual, fwhm_px - the session's point
    #        spread for the quality gate (measured here when None),
    #        sat - saturation ceiling
    # @return: the reference Frame
    # The transform is ESTIMATED by core/register.py (star voting, proven);
    # the RESAMPLING is scipy's spline, which keeps the shape of a point
    # source better than the bilinear used for a quick look. A frame whose
    # registration is not trusted inherits the previous one and is marked;
    # it is never silently trusted.
    #
    # TWO ATTEMPTS PER FRAME, and the second one is what recovers a whole
    # second run. A translation is tried first because it is the common
    # case and the fastest; when it does not pass the gate, the same frame
    # is tried again with a rigid rotation, and only then is it given up
    # on. The reason is measured on the 2025 UR visit: its two runs are
    # 884 px and 0.12 deg apart, the translation leaves 1.5 px of residual
    # (rejected), the rigid fit leaves 0.80 px (accepted on a 3.56 px PSF),
    # and without the retry 62 of the 140 frames were thrown away, which
    # costs a factor sqrt(140/78) = 1.34 in the stack's SNR.
    ref = frames[ref_index] if ref_index is not None else None
    if ref is None or ref.wcs is None:
        # the grid has to be a frame we actually know the sky of
        ref = next((f for f in frames if f.wcs is not None), frames[0])
    ref_data, _ = calibration.read_image(ref.path)
    # ONE source image of the reference for the whole sequence: it is the
    # same frame every time, and rebuilding it per frame was ~140 ms of
    # pure waste on a 2048^2 frame (~20 s over 140 frames). The stars are
    # read from it too, so nothing is computed twice.
    ref_src = register.source_image(ref_data)
    ref_stars = register.detect_stars(ref_src)
    ref.sky_sigma = _frame_noise(ref_data)
    if fwhm_px is None:
        fwhm_px = session_fwhm(ref_data, ref_stars, sat=sat)
    previous = None
    total = len(frames)
    for index, frame in enumerate(frames):
        if solve.is_cancelled(cancel):
            break
        if frame is ref:
            frame.transform = {"angle": 0.0, "dx": 0.0, "dy": 0.0,
                               "quality": 100.0, "rms_px": 0.0}
            frame.register_note = "reference"
        else:
            data, _ = calibration.read_image(frame.path)
            # the frame's own noise, measured here because the pixels are
            # already in hand: the weighted combination needs it and the
            # robust MAD does not care about the stars or the object
            # sitting on top of the sky
            frame.sky_sigma = _frame_noise(data)
            # the guess is the PREVIOUS frame's transform, never the
            # reference's identity: a wrong guess drags the star voting
            # into a bad minimum (measured: a 2 px shift read as -29 px)
            tr = register.estimate_transform(
                ref_data, data, guess=previous, ref_stars=ref_stars,
                ref_src=ref_src, allow_rotation=allow_rotation)
            # "Accepted" is not the same as "good": a translation that
            # could not explain the stars is returned anyway when the
            # rotation is not allowed, so the retry fires both when the
            # gate rejects the answer AND when the answer merely passes
            # while the estimator's own trigger says it did not fit.
            # Measured on 2025 UR: one run-2 frame landed at 1.20 px as a
            # translation (under the gate) where the rigid fit gives 0.6.
            rms = tr.get("rms_px")
            needs_rotation = (not register.trusted(tr, fwhm_px)
                              or (rms is not None
                                  and rms > register.ROTATE_TRIGGER_PX))
            if needs_rotation and not allow_rotation:
                retry = register.estimate_transform(
                    ref_data, data, guess=previous, ref_stars=ref_stars,
                    ref_src=ref_src, allow_rotation=True)
                # The retry has to be PROVEN, not hinted: the stars must
                # certify it (register.trusted's correlation fallback is
                # not enough for a rotation, see require_stars), and the
                # angle has to be a field rotation, not a re-point or a
                # collapsed fit. MAX_STEP_DEG has been in register.py since
                # the beginning and was never enforced; it is enforced
                # here, which is where an angle can now be applied blind.
                angle_deg = abs(float(retry.get("angle_deg") or 0.0))
                if register.trusted(retry, fwhm_px, require_stars=True) \
                        and angle_deg <= register.MAX_STEP_DEG:
                    # the rotation EARNED its place (estimate_transform
                    # only keeps it when it removes a quarter of the
                    # residual), so the frame is kept and the fact is
                    # recorded: the tab says how many were saved this way
                    tr = retry
                    frame.register_note = "rotation"
            if register.trusted(tr, fwhm_px):
                frame.transform = tr
                previous = tr
            else:
                frame.transform = dict(previous) if previous else tr
                frame.failed_register = True
                frame.register_note = _register_reason(tr)
        if frame.transform and frame.wcs is None:
            shape = (int(frame.header.get("NAXIS1", 1)),
                     int(frame.header.get("NAXIS2", 1)))
            frame.wcs = compose_wcs(ref.wcs, frame.transform, shape=shape)
        if progress is not None:
            progress(index + 1, total, frame.path)
    return ref


def _register_reason(tr):
    # @args: tr - a rejected transform
    # @return: a short internal code for WHY the frame was left out, so the
    #          observer reads a reason instead of a bare count. The codes
    #          are turned into words at the edge (the GUI), never here: the
    #          core speaks English keys, the interface speaks the language.
    if tr is None:
        return "no_fit"
    stars = tr.get("stars") or {}
    if int(tr.get("n") or 0) < register.MIN_MATCH:
        return "few_stars" if (stars.get("src") or 0) else "no_stars"
    return "rms"


# A run boundary: the pointing or the field angle steps by more than this
# between two consecutive frames. Inside a run the steps are ~1 px and
# hundredths of a degree (measured on 2025 UR: 0.8 px and 0.01 deg), so the
# thresholds sit an order of magnitude above the tracking and an order of
# magnitude below a re-point (884 px and 0.12 deg in that same visit).
BLOCK_STEP_PX = 40.0
BLOCK_STEP_DEG = 0.5


def _gap_seconds(a, b):
    # @args: a, b - consecutive Frames
    # @return: the seconds between their mid-exposure instants, or None
    #          when either is unknown. The gap is what tells "the observer
    #          paused" from "the pointing moved", and it goes in the words
    #          the tab shows.
    if a is None or b is None or a.t_mid_jd is None or b.t_mid_jd is None:
        return None
    return (float(b.t_mid_jd) - float(a.t_mid_jd)) * 86400.0


def registration_report(frames):
    # @args: frames - list[Frame] after register_sequence
    # @return: the honest summary of the registration, for the tab to say
    #          in words:
    #            {"n_total", "n_ok", "n_failed", "n_rotation", "rms_median",
    #             "blocks": [{"n", "dx", "dy", "angle_deg", "gap_s"}],
    #             "multi_run"}
    #          `blocks` is the RUN structure of the visit. A visit that
    #          mixes two runs (the observer re-pointed, or stopped and
    #          restarted the sequence) shows up as a step in the transform,
    #          and that is what has to be said out loud instead of a bare
    #          "N frames were left out": the frames of the second run are
    #          perfectly good, they are simply pointing elsewhere.
    ok = [f for f in frames if usable(f)]
    report = {"n_total": len(frames), "n_ok": len(ok),
              "n_failed": sum(1 for f in frames if f.failed_register),
              "n_rotation": sum(1 for f in frames
                                if f.register_note == "rotation"),
              "rms_median": None, "blocks": [], "multi_run": False,
              "reasons": {}}
    # WHY the ones that were left out failed, counted: a bare number
    # teaches nothing, and the fix is different for "too few stars" (a
    # short exposure, a cloud) than for "the stars disagree" (a wrong
    # guess, a trailed frame).
    for frame in frames:
        if frame.failed_register:
            key = frame.register_note or "rms"
            report["reasons"][key] = report["reasons"].get(key, 0) + 1
    rms = [f.transform.get("rms_px") for f in ok
           if f.transform and f.transform.get("rms_px") is not None]
    if rms:
        report["rms_median"] = float(np.median(rms))
    blocks = []
    prev = None
    for frame in ok:
        tr = frame.transform
        step = turn = None
        gap = _gap_seconds(prev, frame)
        if prev is not None:
            ptr = prev.transform
            step = math.hypot(tr["dx"] - ptr["dx"], tr["dy"] - ptr["dy"])
            turn = abs(tr.get("angle_deg", 0.0)
                       - ptr.get("angle_deg", 0.0))
        if prev is None or step > BLOCK_STEP_PX or turn > BLOCK_STEP_DEG:
            # dx/dy are the block's offset from the reference grid, which
            # is what the message needs ("the second run is 884 px away")
            blocks.append({"n": 0, "dx": tr["dx"], "dy": tr["dy"],
                           "angle_deg": tr.get("angle_deg", 0.0),
                           "gap_s": gap})
        blocks[-1]["n"] += 1
        prev = frame
    report["blocks"] = blocks
    report["multi_run"] = len(blocks) > 1
    return report


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
        if solve.is_cancelled(cancel):
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


# ======================================================================
# Stacking (phase 3)
# ======================================================================

# How much memory the stacking may use before it switches to strips. The
# whole point of the region read is that the cutout path never gets near
# this; the full-frame final stack is where the budget matters.
MEMORY_BUDGET_BYTES = 2 * 1024 ** 3
# Combination methods, in the order the UI offers them.
METHODS = ("sum", "mean", "median", "sigma", "weighted")


@dataclass
class StackReport:
    method: str = "sigma"
    n_frames: int = 0
    box: tuple | None = None
    streamed: bool = False
    sigma: float = 3.0
    iterations: int = 3


def split_groups(frames, n_obs):
    # @args: frames - list[Frame] (time ordered), n_obs - how many
    #        observations the user wants
    # @return: list of (start, end) index pairs, contiguous and as equal
    #          as they can be
    # The user says how many observations; the software decides the cut.
    # Contiguous groups keep each observation's own T_mid meaningful.
    n = len(frames)
    if n == 0:
        # no frames, no observations: clamping n_obs to n below would leave
        # it at ZERO and the division would blow up (a tab repainted with
        # an empty visit crashed here)
        return []
    if n_obs is None or n_obs < 1:
        n_obs = 1
    n_obs = min(n_obs, n)
    base = n // n_obs
    extra = n % n_obs
    out = []
    start = 0
    for i in range(n_obs):
        size = base + (1 if i < extra else 0)
        out.append((start, start + size))
        start += size
    return out


def group_mid_jd(frames, group):
    # @args: frames - list[Frame], group - (start, end)
    # @return: the group's T_mid (mean of its frames' T_mid, in JD)
    stamps = [frames[i].t_mid_jd for i in range(*group)
              if frames[i].t_mid_jd is not None]
    return sum(stamps) / len(stamps) if stamps else None


def group_q(frames, group, w0, motion):
    # @args: frames - list[Frame], group - (start, end), w0 - the reference
    #        WCS, motion - callable(jd) -> (ra, dec)
    # @return: (t_mid_jd, q) where q is the object's pixel position in the
    #          REFERENCE grid at the group's own T_mid
    # This is what makes each observation represent its own instant: the
    # object is placed where the ephemeris puts it at the group's T_mid,
    # not where it was at the first frame (D23).
    t_mid = group_mid_jd(frames, group)
    if t_mid is None or motion is None or w0 is None:
        return t_mid, None
    pos = motion(t_mid)
    if not pos:
        return t_mid, None
    x, y = w0.all_world2pix([[pos[0], pos[1]]], 0)[0]
    return t_mid, (float(x), float(y))


def track_offsets(frames, group, q, shape):
    # @args: frames - list[Frame], group - (start, end) or a list of
    #        indices, q - the group's reference point, shape - (naxis1, naxis2)
    # @return: list of (dx, dy), one per USABLE frame, in order
    # delta_i = p_i - T_i(q): the object's native position minus where the
    # transform would put q. With the frames registered on the reference
    # grid, this is what freezes the object while the stars trail.
    out = []
    for i in _indices(frames, group):
        frame = frames[i]
        tx, ty = register.ref_to_src_point(frame.transform, q,
                                           (shape[1], shape[0]))
        out.append((frame.object_xy[0] - tx, frame.object_xy[1] - ty))
    return out


def inside_frame(frame, margin=0.0):
    # @args: frame - a Frame with object_xy and a header, margin - pixels of
    #        slack around the sensor
    # @return: True when the object's position falls on the frame
    # A frame whose object is OUTSIDE the sensor has nothing to say about
    # this observation: its pixels are sky where the object should be, so
    # stacking it only adds noise to the very place being measured. It is
    # the case a visit with two runs produces (the telescope re-pointed, so
    # the second run's frames cover a shifted field) and it used to be
    # invisible because those frames never registered at all. Saying it out
    # loud beats a silent hole in the stack.
    if frame is None or frame.object_xy is None:
        return False
    try:
        nx = int(frame.header.get("NAXIS1", 0))
        ny = int(frame.header.get("NAXIS2", 0))
    except (TypeError, ValueError):
        return True
    if nx <= 0 or ny <= 0:
        return True
    x, y = float(frame.object_xy[0]), float(frame.object_xy[1])
    return (-margin <= x < nx + margin) and (-margin <= y < ny + margin)


def _indices(frames, group):
    # @args: frames - list[Frame], group - (start, end) or a list of indices
    # @return: the indices of the group that can actually be stacked
    # Three filters, all of them measured facts about a frame: it registered
    # (usable), the object was placed on it (object_xy), and the object is
    # ON its sensor (inside_frame). The last one is what keeps a shifted
    # field from contributing pure noise where the object is.
    if isinstance(group, (list, tuple)) and len(group) == 2 \
            and all(isinstance(v, int) for v in group):
        candidates = range(group[0], group[1])
    else:
        candidates = group
    return [i for i in candidates if usable(frames[i])
            and inside_frame(frames[i])]


def cutout_box(frames, group, q, margin_px=64, shape=None):
    # @args: frames - list[Frame], group - (start, end), q - the group's
    #        reference point, margin_px - extra margin, shape - (naxis1, naxis2)
    # @return: (x0, y0, x1, y1) in the reference grid
    # The object sits at q, but the STARS trail: in the reference grid the
    # object's trail spans where each frame's object lands once warped, so
    # the box must hold src_to_ref(p_i) for every USABLE frame, plus the
    # margin.
    xs, ys = [q[0]], [q[1]]
    for i in _indices(frames, group):
        frame = frames[i]
        tx, ty = register.src_to_ref_point(frame.transform, frame.object_xy,
                                           (shape[1], shape[0]))
        xs.append(tx)
        ys.append(ty)
    half = max(max(xs) - min(xs), max(ys) - min(ys)) / 2.0 + margin_px
    x0 = int(math.floor(q[0] - half))
    y0 = int(math.floor(q[1] - half))
    x1 = int(math.ceil(q[0] + half))
    y1 = int(math.ceil(q[1] + half))
    if shape is not None:
        x0 = max(0, x0)
        y0 = max(0, y0)
        x1 = min(shape[0], x1)
        y1 = min(shape[1], y1)
    return (x0, y0, x1, y1)


def box_around(q, size, shape):
    # @args: q - the point to centre on, size - the side in px (<= 0 means
    #        the WHOLE frame), shape - (naxis1, naxis2)
    # @return: (x0, y0, x1, y1) in the reference grid
    # The FINAL stack of an observation is a fixed window around the object
    # (or the whole frame), not the trail cutout the sweep uses: the
    # photometry and the eye both want the field, and the object is frozen
    # at q, so a fixed window is all that is needed.
    if size is None or size <= 0:
        return (0, 0, int(shape[0]), int(shape[1]))
    side = min(int(size), int(shape[0]), int(shape[1]))
    half = side // 2
    x0 = int(round(q[0])) - half
    y0 = int(round(q[1])) - half
    x0 = max(0, min(x0, int(shape[0]) - side))
    y0 = max(0, min(y0, int(shape[1]) - side))
    return (x0, y0, x0 + side, y0 + side)


def _ref_to_native_affine(tr, delta):
    # @args: tr - a register transform, delta - the object's offset (px)
    # @return: (A, b) with native = A @ ref + b
    # Mirrors register.apply_transform: the output (reference) pixel is
    # read from the source at R(-angle) about the centre plus the shift.
    angle, dx, dy = tr["angle"], tr["dx"], tr["dy"]
    ca, sa = math.cos(-angle), math.sin(-angle)
    A = np.array([[ca, -sa], [sa, ca]], dtype=float)
    return A, np.array([dx + delta[0], dy + delta[1]], dtype=float)


def _source_box(A, b, box, shape, pad=3):
    # @args: A, b - the affine in (row, col), box - (x0,y0,x1,y1), shape -
    #        (naxis1, naxis2), pad - pixels for the interpolation kernel
    # @return: (x0, y0, x1, y1) in the native frame that the box needs, or
    #          None when the box does not touch the frame AT ALL
    #
    # None is a real answer, not a failure: a frame taken with the telescope
    # pointing elsewhere (a visit that mixes two runs, a re-point) does not
    # contain this observation, and saying so is the honest thing. The
    # previous version clamped the low edge to zero and then forced the high
    # edge to be one pixel above it, so a box entirely off the frame came
    # back as "one pixel just outside": the read was empty, the array came
    # back 1-D and scipy took the 2x2 rotation for a homogeneous matrix and
    # refused it (measured on a real visit: "Expected homogeneous
    # transformation matrix with shape (2, 2) for image shape (0,)"). A
    # crash three layers away from its cause.
    x0, y0, x1, y1 = box
    corners = [(y0, x0), (y0, x1 - 1), (y1 - 1, x0), (y1 - 1, x1 - 1)]
    rs, cs = [], []
    for cr, cc in corners:
        pr, pc = A @ np.array([cr, cc]) + b
        rs.append(pr)
        cs.append(pc)
    lo_c, hi_c = min(cs) - pad, max(cs) + pad
    lo_r, hi_r = min(rs) - pad, max(rs) + pad
    width, height = int(shape[0]), int(shape[1])
    if hi_c <= 0 or lo_c >= width or hi_r <= 0 or lo_r >= height:
        return None
    sc0 = max(0, int(math.floor(lo_c)))
    sr0 = max(0, int(math.floor(lo_r)))
    sc1 = min(width, int(math.ceil(hi_c)))
    sr1 = min(height, int(math.ceil(hi_r)))
    return (sc0, sr0, max(sc1, sc0 + 1), max(sr1, sr0 + 1))


def _warp_to_box(path, tr, delta, box, shape, loader=None, order=3):
    # @args: path - the frame, tr - its transform, delta - the object's
    #        offset, box - the output box in reference (x0,y0,x1,y1),
    #        shape - the native frame (naxis1, naxis2), loader -
    #        callable(path, box) -> array, order - interpolation order
    # @return: (warped, valid) where valid is a boolean mask
    # Only the region the box needs is read from disk (D32): the affine
    # tells us its bounding box, so the frame is never loaded whole. The
    # out-of-frame fill is ZERO and the mask says where it is.
    #
    # ORDER MATTERS and it bit us: scipy's affine_transform works in
    # (row, col), while the rest of the engine speaks (x, y). Passing the
    # (x, y) matrix and offsets straight through swapped the two axes, and
    # with a large box origin (the cutout) the error grew: the cutout stack
    # and the full-frame stack of the SAME observation were not the same
    # image (measured: max 257 ADU apart around the object). Everything
    # below is in (row, col); P flips between the two.
    from scipy import ndimage
    A_xy, b_xy = _ref_to_native_affine(tr, delta)
    P = np.array([[0.0, 1.0], [1.0, 0.0]])
    A = P @ A_xy @ P
    b = P @ b_xy
    x0, y0, x1, y1 = box
    out_o = np.array([float(y0), float(x0)])          # (row, col)
    src_box = _source_box(A, b, box, shape)
    out_shape = (y1 - y0, x1 - x0)
    if src_box is None:
        # This frame does not cover the box at all (the object is off its
        # field, or the frame points elsewhere): the honest answer is an
        # empty frame with a mask that says "no data here", so the
        # combination ignores it instead of adding noise where the object
        # should be. Nothing is read from disk.
        return (np.zeros(out_shape, dtype=np.float32),
                np.zeros(out_shape, dtype=bool))
    if loader is not None:
        data = loader(path, src_box)
    else:
        data, _header = calibration.read_image(path, src_box)
    data = np.asarray(data, dtype=np.float32)
    src_o = np.array([float(src_box[1]), float(src_box[0])])   # (row, col)
    offset = A @ out_o + b - src_o
    warped = ndimage.affine_transform(data, A, offset=offset,
                                      output_shape=out_shape, order=order,
                                      mode="constant", cval=0.0)
    ones = ndimage.affine_transform(np.ones_like(data), A, offset=offset,
                                    output_shape=out_shape, order=1,
                                    mode="constant", cval=0.0)
    return warped, ones > 0.5


def frame_weights(frames):
    # @args: frames - list[Frame], each with sky_sigma when it is known
    # @return: (n,) the inverse-variance weight of each frame, or None when
    #          no frame knows its own noise
    # 1/sigma^2 is the optimal linear weighting of several measurements of
    # the SAME signal with different noise: the frame with less noise
    # carries more of the answer. On a stable night every weight is nearly
    # equal and this changes nothing; on a night with thin cloud, moon or
    # variable transparency it is what keeps one bad frame from dragging
    # the stack down. It is also the noise model the matched filter needs.
    sigmas = [f.sky_sigma for f in frames]
    known = [s for s in sigmas if s]
    if not known:
        return None
    # a frame whose noise could not be measured gets the median of the
    # others: it is a real frame, only an unmeasured one
    median = float(np.median(known))
    values = np.asarray([s if s else median for s in sigmas], dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return 1.0 / np.square(values)


def _weight_row(weights, n):
    # @args: weights - (n,) array or None, n - how many frames
    # @return: the weights shaped (n, 1, 1) for broadcasting, or None
    if weights is None:
        return None
    w = np.asarray(weights, dtype=np.float64).ravel()
    if w.size != n:
        return None
    return w.reshape((-1, 1, 1))


def combine(stack, method, mask=None, sigma=3.0, iterations=3, weights=None):
    # @args: stack - (n, h, w) float32, method - one of METHODS, mask -
    #        optional (n, h, w) validity, sigma/iterations - for sigma-clip,
    #        weights - optional (n,) per-frame weights (see frame_weights)
    # @return: the combined (h, w) float32 image
    # sum and mean are equivalent in signal (mean is sum / n); both are
    # offered because the user will see them in the concept, but the app
    # says they differ only in scale. sigma-clipped keeps almost all of
    # the mean's SNR while rejecting the star trails like the median.
    # "weighted" is the sigma clip with an inverse-variance average of the
    # survivors: the clip removes what is not the object, the weight gives
    # each frame the say its own noise deserves.
    #
    # The pixels OUTSIDE the frames' footprint are all-NaN BY CONSTRUCTION
    # (the mask says so), so every NaN-aware reduction warns about them on
    # every stack: "All-NaN slice encountered" and "Mean of empty slice".
    # The answer there is NaN, which is exactly what those pixels deserve,
    # so the warnings are silenced HERE, where they are expected: a real
    # all-NaN frame somewhere else still shows up in the log.
    if stack.size == 0:
        return stack.reshape(stack.shape[1:]) if stack.ndim == 3 else stack
    data = stack
    if mask is not None:
        data = np.where(mask, stack, np.nan)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="All-NaN slice.*")
        warnings.filterwarnings("ignore", message="Mean of empty slice.*")
        if method == "weighted":
            return _combine_weighted(data, weights, sigma, iterations)
        return _combine_masked(data, method, sigma, iterations)


def _combine_weighted(data, weights, sigma, iterations):
    # @args: data - (n, h, w) float32 with the invalid pixels already NaN,
    #        weights - (n,) per-frame weights or None, sigma/iterations -
    #        the same clip the "sigma" method uses
    # @return: the combined (h, w) float32 image
    # The clip first, the weighted average after: the star trails the clip
    # removes are the same ones the plain "sigma" method removes, and the
    # weight only decides how much each SURVIVING frame counts. Without
    # weights it is exactly the plain sigma-clipped mean, so the method
    # degrades into the proven one instead of into something new.
    keep = _sigma_clip_keep(data, sigma, iterations)
    w = _weight_row(weights, data.shape[0])
    if w is None:
        with np.errstate(invalid="ignore"):
            return np.nanmean(np.where(keep, data, np.nan),
                              axis=0).astype(np.float32)
    ww = np.broadcast_to(w, data.shape)
    num = np.nansum(np.where(keep, data * ww, np.nan), axis=0)
    den = np.sum(np.where(keep, ww, 0.0), axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(den > 0, num / den, np.nan)
    return out.astype(np.float32)


def _combine_masked(data, method, sigma, iterations):
    # @args: data - (n, h, w) float32 with the invalid pixels already NaN,
    #        method - one of METHODS, sigma/iterations - for sigma-clip
    # @return: the combined (h, w) float32 image
    # The arithmetic of the four methods, with no mask left to apply: the
    # caller has already turned the invalid pixels into NaN.
    if method == "sum":
        return np.nansum(data, axis=0).astype(np.float32)
    if method == "mean":
        return np.nanmean(data, axis=0).astype(np.float32)
    if method == "median":
        return np.nanmedian(data, axis=0).astype(np.float32)
    # sigma-clipped: clip around the median and average the survivors
    keep = _sigma_clip_keep(data, sigma, iterations)
    return np.nanmean(np.where(keep, data, np.nan), axis=0).astype(np.float32)


def _sigma_clip_keep(data, sigma, iterations):
    # @args: data - (n, h, w) with the invalid pixels already NaN,
    #        sigma/iterations - the clip
    # @return: the boolean (n, h, w) "this pixel survives the clip"
    # The clip walks the median: it starts from the median of the frames
    # and, each pass, keeps what is within sigma MAD of it and re-centres
    # on the survivors. ONE implementation, because the plain sigma-clipped
    # mean and the weighted one MUST reject the same pixels: the only
    # difference between the two methods is how the survivors are averaged.
    med = np.nanmedian(data, axis=0)
    keep = np.isfinite(data)
    for _ in range(max(1, iterations)):
        with np.errstate(invalid="ignore"):
            mad = outliers.scaled_mad(data, axis=0, centre=med)
        mad = np.where(mad > 0, mad, np.inf)
        keep = keep & (np.abs(data - med) <= sigma * mad)
        count = keep.sum(axis=0)
        with np.errstate(invalid="ignore"):
            new_med = np.nansum(np.where(keep, data, np.nan), axis=0) \
                / np.maximum(count, 1)
        med = np.where(count > 0, new_med, med)
    return keep


def stack_group(frames, group, q, method, box, shape, cfg=None, loader=None,
                budget_bytes=MEMORY_BUDGET_BYTES, sigma=3.0, iterations=3,
                track=True):
    # @args: frames - list[Frame], group - (start, end), q - the group's
    #        reference point, method - one of METHODS, box - the output box,
    #        shape - the native frame size, cfg - Config, loader - array
    #        reader, budget_bytes - the RAM budget, track - True freezes the
    #        OBJECT (the stars trail), False freezes the STARS (the object
    #        trails)
    # @return: (stack, report)
    # In RAM when the warped frames fit the budget (the cutout path always
    # does); otherwise the output is walked in strips and only the region
    # each strip needs is read. The two paths are tested to agree, because
    # a streaming that does not match the RAM is a silent source of error.
    # Frames that could not be registered are LEFT OUT (usable): stacking
    # them misaligned only adds noise.
    #
    # The two alignments are both needed and they answer different
    # questions: the object's stack is where its light is concentrated (so
    # a faint NEO can be measured at all), and the STAR stack is where the
    # comparison stars are points instead of streaks, which is the only
    # way their flux can set a zero point. Measuring a streak with a
    # circular aperture calibrates nothing.
    indices = _indices(frames, group)
    report = StackReport(method=method, n_frames=len(indices), box=box,
                         sigma=sigma, iterations=iterations)
    if not indices:
        return None, report
    offsets = (track_offsets(frames, indices, q, shape) if track
               else [(0.0, 0.0)] * len(indices))
    # the per-frame weights are a property of the FRAME, not of a strip, so
    # they are computed once here and the RAM and the streaming paths use
    # the same ones (the two are pinned to agree)
    weights = (frame_weights([frames[i] for i in indices])
               if method == "weighted" else None)
    out_h = box[3] - box[1]
    out_w = box[2] - box[0]
    n = len(indices)
    need = n * out_h * out_w * 4
    if need <= budget_bytes:
        stack = np.empty((n, out_h, out_w), dtype=np.float32)
        masks = np.empty((n, out_h, out_w), dtype=bool)
        for k, i in enumerate(indices):
            warped, valid = _warp_to_box(frames[i].path, frames[i].transform,
                                         offsets[k], box, shape, loader=loader)
            stack[k] = warped
            masks[k] = valid
        return combine(stack, method, mask=masks, sigma=sigma,
                       iterations=iterations, weights=weights), report
    report.streamed = True
    out = np.empty((out_h, out_w), dtype=np.float32)
    strip_h = max(1, int(budget_bytes / max(1, n * out_w * 4)))
    # Strips OVERLAP by the interpolation kernel's reach: a strip whose
    # source region ends where the kernel still needs pixels would read
    # zeros at its edge and disagree with the RAM path (measured: 30 ADU
    # at the object's peak). Only the central rows are kept. The pad is
    # generous because scipy's order-3 spline prefilters the whole region,
    # so a truncated region changes its own edges slightly.
    pad = 8
    for y0 in range(0, out_h, strip_h):
        y1 = min(out_h, y0 + strip_h)
        py0 = max(0, y0 - pad)
        py1 = min(out_h, y1 + pad)
        sub_box = (box[0], box[1] + py0, box[2], box[1] + py1)
        strip = np.empty((n, py1 - py0, out_w), dtype=np.float32)
        masks = np.empty((n, py1 - py0, out_w), dtype=bool)
        for k, i in enumerate(indices):
            warped, valid = _warp_to_box(frames[i].path, frames[i].transform,
                                         offsets[k], sub_box, shape,
                                         loader=loader)
            strip[k] = warped
            masks[k] = valid
        combined = combine(strip, method, mask=masks, sigma=sigma,
                           iterations=iterations, weights=weights)
        out[y0:y1] = combined[y0 - py0:y1 - py0]
    return out, report


def stack_groups(frames, groups, q_by_group, method, boxes, shape, cfg=None,
                 loader=None, progress=None, cancel=None, track=True):
    # @args: frames, groups, q_by_group (one q per group), method, boxes
    #        (one box per group), shape, cfg, loader, progress, cancel,
    #        track - as stack_group (False gives the star stacks)
    # @return: list[(stack, report)] one per observation
    out = []
    total = len(groups)
    for index, group in enumerate(groups):
        if solve.is_cancelled(cancel):
            break
        stack, report = stack_group(frames, group, q_by_group[index], method,
                                    boxes[index], shape, cfg=cfg,
                                    loader=loader, track=track)
        if progress is not None:
            progress(index + 1, total, f"observation {index + 1}")
        # one entry PER GROUP even when it is empty, so the caller's index
        # alignment survives (a group whose frames all failed to register
        # has nothing to measure and is reported as such, not as a cancel)
        out.append((stack, report))
    return out


def preview_groups(frames, n_obs, base_snr=None):
    # @args: frames - list[Frame], n_obs - how many observations, base_snr
    #        - the SNR of the whole sequence (when known)
    # @return: list of dicts {n_frames, t_mid, snr_est}
    # The SNR grows with the square root of the frame count, so asking for
    # more observations splits the signal; the UI shows this before the
    # user accepts (D22).
    groups = split_groups(frames, n_obs)
    out = []
    for group in groups:
        n = group[1] - group[0]
        est = None
        if base_snr is not None and len(frames):
            est = float(base_snr) * math.sqrt(n / len(frames))
        out.append({"n_frames": n, "t_mid": group_mid_jd(frames, group),
                    "snr_est": est})
    return out


@dataclass
class SweepResult:
    best: dict | None = None
    grid: list = field(default_factory=list)
    method: str = "median"


def _score(stack, q_box, cfg=None):
    # @args: stack - the combined image, q_box - the object's position in
    #        the box, cfg - Config
    # @return: (score, snr, roundness)
    # score = SNR x roundness: a bright but elongated source is penalised,
    # which is what separates the right velocity from a nearby one that
    # smears the object along a line.
    from . import photometry
    x, y = q_box
    res = photometry.measure_point(stack, x, y, r_ap=4.0, r_ann_in=8.0,
                                   r_ann_out=12.0)
    if not res.get("ok"):
        return 0.0, 0.0, 0.0
    yy, xx = np.mgrid[0:stack.shape[0], 0:stack.shape[1]]
    d = np.hypot(xx - x, yy - y)
    ann = (d >= 8.0) & (d <= 12.0)
    sky = float(np.median(stack[ann]))
    sig = float(outliers.scaled_mad(stack[ann], centre=sky)) or 1e-6
    ap = d <= 4.0
    snr = float(res["flux"]) / (sig * math.sqrt(ap.sum()))
    roundness = _roundness(stack, x, y)
    return snr * roundness, snr, roundness


def _roundness(stack, x, y, radius=4.0):
    # @args: stack, x, y - the source, radius - the moments window
    # @return: b/a of the second moments (1 = circular)
    yy, xx = np.mgrid[0:stack.shape[0], 0:stack.shape[1]]
    d = np.hypot(xx - x, yy - y)
    win = d <= radius
    sky = float(np.median(stack[~win])) if (~win).any() else 0.0
    w = np.where(win, stack - sky, 0.0)
    w = np.clip(w, 0, None)
    total = w.sum()
    if total <= 0:
        return 0.0
    mx = (w * xx).sum() / total - x
    my = (w * yy).sum() / total - y
    cxx = (w * (xx - x - mx) ** 2).sum() / total
    cyy = (w * (yy - y - my) ** 2).sum() / total
    cxy = (w * (xx - x - mx) * (yy - y - my)).sum() / total
    tr = cxx + cyy
    det = cxx * cyy - cxy ** 2
    disc = max(0.0, tr * tr / 4.0 - det)
    l1 = tr / 2.0 + math.sqrt(disc)
    l2 = tr / 2.0 - math.sqrt(disc)
    if l1 <= 0:
        return 0.0
    return float(math.sqrt(max(l2, 0.0) / l1))


def sweep(frames, q, base_rate, base_pa, box, shape, pct=5.0, steps=5,
          method="median", cfg=None, loader=None, sigma=3.0, iterations=3,
          progress=None, cancel=None):
    # @args: frames - list[Frame] (the whole sequence), q - the reference
    #        point, base_rate - arcsec/min, base_pa - degrees, box/shape,
    #        pct - the +/- percentage of the grid, steps - per axis,
    #        method - the fast combination, cfg/loader/sigma/iterations,
    #        progress/cancel
    # @return: SweepResult
    # A 5x5 grid around the theoretical velocity: 5 factors of the modulus
    # by 5 position-angle offsets. Modulus and PA are used, not RA/Dec
    # components, because the real errors are of speed and heading (the
    # mount and the ephemeris fail on those two axes).
    grid = []
    best = None
    factors = np.linspace(1.0 - pct / 100.0, 1.0 + pct / 100.0, steps)
    pas = np.linspace(-pct / 100.0, pct / 100.0, steps) * 180.0
    total = len(factors) * len(pas)
    done = 0
    for factor in factors:
        for dpa in pas:
            if solve.is_cancelled(cancel):
                break
            rate = base_rate * factor
            pa = base_pa + dpa
            # move each frame's object from the base position along the
            # new velocity, relative to the base one
            _rescore(frames, q, base_rate, base_pa, rate, pa, box, shape,
                     method, cfg, loader, sigma, iterations, grid, best)
            done += 1
            if progress is not None:
                progress(done, total, f"rate {rate:.2f} PA {pa:.1f}")
    for item in grid:
        if best is None or item["score"] > best["score"]:
            best = item
    return SweepResult(best=best, grid=grid, method=method)


def _rescore(frames, q, base_rate, base_pa, rate, pa, box, shape, method,
             cfg, loader, sigma, iterations, grid, _best):
    # @args: internal: shifts the object along (rate, pa) instead of the
    #        ephemeris, stacks the box and scores it
    # @return: None (appends to grid)
    # The per-frame displacement is the difference between the new and the
    # base velocity over the elapsed time, in pixels.
    t0 = group_mid_jd(frames, (0, len(frames))) or 0.0
    scale = _arcsec_per_pixel_guess(frames)
    usable_frames = [f for f in frames if usable(f) and f.object_xy is not None]
    offsets = []
    for frame in usable_frames:
        tx, ty = register.ref_to_src_point(frame.transform, q,
                                            (shape[1], shape[0]))
        base_delta = (frame.object_xy[0] - tx, frame.object_xy[1] - ty)
        dt_min = ((frame.t_mid_jd or t0) - t0) * 1440.0
        d_rate = (rate - base_rate) * dt_min
        d_pa = math.radians(pa - base_pa)
        dra = d_rate * math.sin(d_pa) / max(scale, 1e-6)
        ddec = d_rate * math.cos(d_pa) / max(scale, 1e-6)
        offsets.append((base_delta[0] - dra, base_delta[1] + ddec))
    if not usable_frames:
        grid.append({"rate": rate, "pa": pa, "score": 0.0, "snr": 0.0,
                     "roundness": 0.0})
        return
    # stack with the candidate offsets (only the frames that registered)
    n = len(usable_frames)
    out_h = box[3] - box[1]
    out_w = box[2] - box[0]
    stack = np.empty((n, out_h, out_w), dtype=np.float32)
    masks = np.empty((n, out_h, out_w), dtype=bool)
    for k, frame in enumerate(usable_frames):
        warped, valid = _warp_to_box(frame.path, frame.transform,
                                     offsets[k], box, shape, loader=loader)
        stack[k] = warped
        masks[k] = valid
    combined = combine(stack, method, mask=masks, sigma=sigma,
                       iterations=iterations)
    score, snr, roundness = _score(combined, (q[0] - box[0], q[1] - box[1]), cfg)
    grid.append({"rate": rate, "pa": pa, "score": score, "snr": snr,
                 "roundness": roundness})


def _arcsec_per_pixel_guess(frames):
    # @args: frames - list[Frame]
    # @return: the plate scale in arcsec/px from the first WCS that has a CD
    for frame in frames:
        if frame.wcs is not None:
            return _arcsec_per_pixel(frame.wcs)
    return 1.0


@dataclass
class DetectionReport:
    detected: bool = False
    snr: float = 0.0
    x: float = 0.0
    y: float = 0.0
    fwhm: float | None = None
    roundness: float = 0.0
    mag_limit: float | None = None
    notes: str = ""


def detect(stack, q_box, cfg=None, snr_sigma=3.5, zp=None, exptime_s=None):
    # @args: stack - the combined image, q_box - the object's position in
    #        the box, cfg - Config, snr_sigma - the detection gate, zp -
    #        zero point (mag_limit when known), exptime_s - total exposure
    # @return: DetectionReport
    # The SNR is measured with a local sky annulus (the star trails cross
    # the box, so a global sigma would be inflated). Below the gate the
    # caller must NOT run the fine-tuning sweep: sweeping over noise and
    # keeping the best is the definition of overfitting.
    score, snr, roundness = _score(stack, q_box, cfg)
    report = DetectionReport(snr=snr, x=q_box[0], y=q_box[1],
                             roundness=roundness)
    report.detected = snr >= snr_sigma
    if zp is not None:
        # the flux that would give exactly the gate, in magnitudes
        from . import photometry
        res = photometry.measure_point(stack, q_box[0], q_box[1], r_ap=4.0,
                                       r_ann_in=8.0, r_ann_out=12.0)
        yy, xx = np.mgrid[0:stack.shape[0], 0:stack.shape[1]]
        d = np.hypot(xx - q_box[0], yy - q_box[1])
        ann = (d >= 8.0) & (d <= 12.0)
        sky = float(np.median(stack[ann]))
        sig = float(outliers.scaled_mad(stack[ann], centre=sky)) or 1e-6
        limit_flux = snr_sigma * sig * math.sqrt((d <= 4.0).sum())
        if limit_flux > 0:
            report.mag_limit = float(zp - 2.5 * math.log10(limit_flux))
    if not report.detected:
        report.notes = ("below the detection gate: no fine-tuning sweep "
                        "was run")
    return report
