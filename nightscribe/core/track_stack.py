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


# ======================================================================
# Stacking (phase 3)
# ======================================================================

# How much memory the stacking may use before it switches to strips. The
# whole point of the region read is that the cutout path never gets near
# this; the full-frame final stack is where the budget matters.
MEMORY_BUDGET_BYTES = 2 * 1024 ** 3
# Combination methods, in the order the UI offers them.
METHODS = ("sum", "mean", "median", "sigma")


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
    # @args: frames - list[Frame], group - (start, end), q - the group's
    #        reference point, shape - (naxis1, naxis2)
    # @return: list of (dx, dy) per frame: how much the object has to be
    #          moved so it lands on q
    # delta_i = p_i - T_i(q): the object's native position minus where the
    # transform would put q. With the frames registered on the reference
    # grid, this is what freezes the object while the stars trail.
    out = []
    for i in range(*group):
        frame = frames[i]
        if frame.object_xy is None or frame.transform is None:
            out.append((0.0, 0.0))
            continue
        tx, ty = register.ref_to_src_point(frame.transform, q, (shape[1], shape[0]))
        out.append((frame.object_xy[0] - tx, frame.object_xy[1] - ty))
    return out


def cutout_box(frames, group, q, margin_px=64, shape=None):
    # @args: frames - list[Frame], group - (start, end), q - the group's
    #        reference point, margin_px - extra margin, shape - (naxis1, naxis2)
    # @return: (x0, y0, x1, y1) in the reference grid
    # The object sits at q, but the stars move across the cutout, so the
    # box must hold the whole trail. Its size comes from the object's own
    # motion, never from a magic number.
    # The object sits at q, but the STARS trail: in the reference grid the
    # object's trail spans where each frame's object lands once warped, so
    # the box must hold src_to_ref(p_i) for every frame, plus the margin.
    xs, ys = [q[0]], [q[1]]
    for i in range(*group):
        frame = frames[i]
        if frame.object_xy is None or frame.transform is None:
            continue
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
    # @args: A, b - the affine (native = A @ ref + b), box - the output box
    #        in reference coords, shape - the native frame (naxis1, naxis2),
    #        pad - extra pixels for the interpolation kernel (order 3 needs 2)
    # @return: (x0, y0, x1, y1) in the native frame that the box needs
    x0, y0, x1, y1 = box
    corners = [(x0, y0), (x1 - 1, y0), (x0, y1 - 1), (x1 - 1, y1 - 1)]
    xs, ys = [], []
    for cx, cy in corners:
        px, py = A @ np.array([cx, cy]) + b
        xs.append(px)
        ys.append(py)
    sx0 = max(0, int(math.floor(min(xs))) - pad)
    sy0 = max(0, int(math.floor(min(ys))) - pad)
    sx1 = min(shape[0], int(math.ceil(max(xs))) + pad)
    sy1 = min(shape[1], int(math.ceil(max(ys))) + pad)
    return (sx0, sy0, max(sx1, sx0 + 1), max(sy1, sy0 + 1))


def _warp_to_box(path, tr, delta, box, shape, loader=None, order=3):
    # @args: path - the frame, tr - its transform, delta - the object's
    #        offset, box - the output box in reference coords, shape - the
    #        native frame size, loader - callable(path, box) -> array,
    #        order - interpolation order
    # @return: (warped, valid) where valid is a boolean mask
    # Only the region the box needs is read from disk (D32): the affine
    # tells us its bounding box, so the frame is never loaded whole. The
    # out-of-frame fill is ZERO and the mask says where it is, so the
    # combination can drop it; using the sky instead would make the RAM
    # and the strip paths disagree at the edges.
    from scipy import ndimage
    A, b = _ref_to_native_affine(tr, delta)
    src_box = _source_box(A, b, box, shape)
    if loader is not None:
        data = loader(path, src_box)
    else:
        data, _header = calibration.read_image(path, src_box)
    data = np.asarray(data, dtype=np.float32)
    src_o = np.array([src_box[0], src_box[1]], dtype=float)
    out_o = np.array([box[0], box[1]], dtype=float)
    offset = A @ out_o + b - src_o
    out_shape = (box[3] - box[1], box[2] - box[0])
    warped = ndimage.affine_transform(data, A, offset=offset,
                                      output_shape=out_shape, order=order,
                                      mode="constant", cval=0.0)
    ones = ndimage.affine_transform(np.ones_like(data), A, offset=offset,
                                    output_shape=out_shape, order=1,
                                    mode="constant", cval=0.0)
    return warped, ones > 0.5


def combine(stack, method, mask=None, sigma=3.0, iterations=3):
    # @args: stack - (n, h, w) float32, method - one of METHODS, mask -
    #        optional (n, h, w) validity, sigma/iterations - for sigma-clip
    # @return: the combined (h, w) float32 image
    # sum and mean are equivalent in signal (mean is sum / n); both are
    # offered because the user will see them in the concept, but the app
    # says they differ only in scale. sigma-clipped keeps almost all of
    # the mean's SNR while rejecting the star trails like the median.
    if stack.size == 0:
        return stack.reshape(stack.shape[1:]) if stack.ndim == 3 else stack
    data = stack
    if mask is not None:
        data = np.where(mask, stack, np.nan)
    if method == "sum":
        return np.nansum(data, axis=0).astype(np.float32)
    if method == "mean":
        return np.nanmean(data, axis=0).astype(np.float32)
    if method == "median":
        return np.nanmedian(data, axis=0).astype(np.float32)
    # sigma-clipped: clip around the median and average the survivors
    med = np.nanmedian(data, axis=0)
    keep = np.isfinite(data)
    for _ in range(max(1, iterations)):
        with np.errstate(invalid="ignore"):
            mad = np.nanmedian(np.abs(data - med), axis=0) * 1.4826
        mad = np.where(mad > 0, mad, np.inf)
        keep = keep & (np.abs(data - med) <= sigma * mad)
        count = keep.sum(axis=0)
        with np.errstate(invalid="ignore"):
            new_med = np.nansum(np.where(keep, data, np.nan), axis=0) \
                / np.maximum(count, 1)
        med = np.where(count > 0, new_med, med)
    return np.nanmean(np.where(keep, data, np.nan), axis=0).astype(np.float32)


def stack_group(frames, group, q, method, box, shape, cfg=None, loader=None,
                budget_bytes=MEMORY_BUDGET_BYTES, sigma=3.0, iterations=3):
    # @args: frames - list[Frame], group - (start, end), q - the group's
    #        reference point, method - one of METHODS, box - the output box,
    #        shape - the native frame size, cfg - Config, loader - array
    #        reader, budget_bytes - the RAM budget
    # @return: (stack, report)
    # In RAM when the warped frames fit the budget (the cutout path always
    # does); otherwise the output is walked in strips and only the region
    # each strip needs is read. The two paths are tested to agree, because
    # a streaming that does not match the RAM is a silent source of error.
    offsets = track_offsets(frames, group, q, shape)
    out_h = box[3] - box[1]
    out_w = box[2] - box[0]
    n = group[1] - group[0]
    need = n * out_h * out_w * 4
    report = StackReport(method=method, n_frames=n, box=box, sigma=sigma,
                         iterations=iterations)
    if need <= budget_bytes:
        stack = np.empty((n, out_h, out_w), dtype=np.float32)
        masks = np.empty((n, out_h, out_w), dtype=bool)
        for k, i in enumerate(range(*group)):
            warped, valid = _warp_to_box(frames[i].path, frames[i].transform,
                                         offsets[k], box, shape, loader=loader)
            stack[k] = warped
            masks[k] = valid
        return combine(stack, method, mask=masks, sigma=sigma,
                       iterations=iterations), report
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
        for k, i in enumerate(range(*group)):
            warped, valid = _warp_to_box(frames[i].path, frames[i].transform,
                                         offsets[k], sub_box, shape,
                                         loader=loader)
            strip[k] = warped
            masks[k] = valid
        combined = combine(strip, method, mask=masks, sigma=sigma,
                           iterations=iterations)
        out[y0:y1] = combined[y0 - py0:y1 - py0]
    return out, report


def stack_groups(frames, groups, q_by_group, method, boxes, shape, cfg=None,
                 loader=None, progress=None, cancel=None):
    # @args: frames, groups, q_by_group (one q per group), method, boxes
    #        (one box per group), shape, cfg, loader, progress, cancel
    # @return: list[(stack, report)] one per observation
    out = []
    total = len(groups)
    for index, group in enumerate(groups):
        if cancel is not None and cancel():
            break
        stack, report = stack_group(frames, group, q_by_group[index], method,
                                    boxes[index], shape, cfg=cfg, loader=loader)
        out.append((stack, report))
        if progress is not None:
            progress(index + 1, total, f"observation {index + 1}")
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
    sig = 1.4826 * float(np.median(np.abs(stack[ann] - sky))) or 1e-6
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
            if cancel is not None and cancel():
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
    offsets = []
    for frame in frames:
        if frame.transform is None or frame.object_xy is None:
            offsets.append((0.0, 0.0))
            continue
        tx, ty = register.ref_to_src_point(frame.transform, q,
                                            (shape[1], shape[0]))
        base_delta = (frame.object_xy[0] - tx, frame.object_xy[1] - ty)
        dt_min = ((frame.t_mid_jd or t0) - t0) * 1440.0
        d_rate = (rate - base_rate) * dt_min
        d_pa = math.radians(pa - base_pa)
        dra = d_rate * math.sin(d_pa) / max(scale, 1e-6)
        ddec = d_rate * math.cos(d_pa) / max(scale, 1e-6)
        offsets.append((base_delta[0] - dra, base_delta[1] + ddec))
    # stack with the candidate offsets
    n = len(frames)
    out_h = box[3] - box[1]
    out_w = box[2] - box[0]
    stack = np.empty((n, out_h, out_w), dtype=np.float32)
    masks = np.empty((n, out_h, out_w), dtype=bool)
    for k, frame in enumerate(frames):
        warped, valid = _warp_to_box(frame.path, frame.transform or
                                     {"angle": 0.0, "dx": 0.0, "dy": 0.0},
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
        sig = 1.4826 * float(np.median(np.abs(stack[ann] - sky))) or 1e-6
        limit_flux = snr_sigma * sig * math.sqrt((d <= 4.0).sum())
        if limit_flux > 0:
            report.mag_limit = float(zp - 2.5 * math.log10(limit_flux))
    if not report.detected:
        report.notes = ("below the detection gate: no fine-tuning sweep "
                        "was run")
    return report
