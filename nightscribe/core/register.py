############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Frame registration module (series plan, phase 7B)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Per-frame registration for series whose frames are not aligned.

Some real series (an alt-az mount without derotation, a re-pointed
telescope, MicroObservatory runs) drift and ROTATE between frames and
carry no WCS. The series engine measures at fixed reference coordinates,
so those frames must be brought back onto the reference grid first. This
module estimates the similarity transform (rotation about the frame
centre plus translation) by Fourier methods (no scipy, no astropy, ADR-004)
and resamples a frame onto the reference grid with bilinear interpolation.

It is opt-in (SeriesConfig.align): the default series assumes aligned,
astrometrically solved frames (D17); registration is the documented escape
hatch for datasets that are not.
"""

import logging
import math

import numpy as np

logger = logging.getLogger(__name__)


def _bilinear(data, xs, ys):
    # Bilinear sample of `data` at float coordinates; out-of-frame -> 0.
    # @return: the sampled values (same shape as xs/ys)
    h, w = data.shape
    xs = np.asarray(xs, dtype=np.float64)
    ys = np.asarray(ys, dtype=np.float64)
    x0 = np.floor(xs).astype(np.int64)
    y0 = np.floor(ys).astype(np.int64)
    x1, y1 = x0 + 1, y0 + 1
    wx = xs - x0
    wy = ys - y0
    out = np.zeros(xs.shape, dtype=np.float64)
    valid = (x0 >= 0) & (y0 >= 0) & (x1 < w) & (y1 < h)
    in_range = (xs >= 0.0) & (xs <= w - 1.0) & (ys >= 0.0) \
        & (ys <= h - 1.0)
    x0c = np.clip(x0, 0, w - 1)
    y0c = np.clip(y0, 0, h - 1)
    x1c = np.clip(x1, 0, w - 1)
    y1c = np.clip(y1, 0, h - 1)
    v00 = data[y0c, x0c]
    v01 = data[y0c, x1c]
    v10 = data[y1c, x0c]
    v11 = data[y1c, x1c]
    val = (v00 * (1 - wx) * (1 - wy) + v01 * wx * (1 - wy)
           + v10 * (1 - wx) * wy + v11 * wx * wy)
    # on the last row/column the x1/y1 neighbour is out of frame: the
    # clamped corner (v00) is exact at an integer coordinate, so use it
    out = np.where(valid, val, np.where(in_range, v00, 0.0))
    return out


def angular_profile(data, ntheta=360, nr=48, rmin=12, rmax=None):
    # The image's angular profile: the mean intensity along rays from the
    # centre, as a function of the position angle. A rotation of the image
    # is a circular shift of this profile (Fourier-Mellin, rotation only).
    # @args: data - 2D array, ntheta - angle bins, nr - radial samples,
    #        rmin/rmax - radial range (px)
    # @return: the ntheta-long profile
    h, w = data.shape
    cx, cy = w / 2.0, h / 2.0
    rmax = rmax if rmax is not None else (min(h, w) / 2.0 - 2.0)
    r = np.linspace(rmin, rmax, nr)
    th = np.arange(ntheta) * (2.0 * math.pi / ntheta)
    ct, st = np.cos(th), np.sin(th)
    prof = np.zeros(ntheta, dtype=np.float64)
    for j in range(ntheta):
        xs = cx + r * ct[j]
        ys = cy + r * st[j]
        prof[j] = float(np.mean(_bilinear(data, xs, ys)))
    return prof


def rotation_between(prof_ref, prof_src):
    # @return: the rotation (radians) that, applied to the source image
    #          about its centre, aligns its angular profile with the ref
    a = prof_ref - np.mean(prof_ref)
    b = prof_src - np.mean(prof_src)
    c = np.fft.ifft(np.fft.fft(a) * np.conj(np.fft.fft(b))).real
    shift = int(np.argmax(c))
    n = len(a)
    if shift > n // 2:
        shift -= n
    return shift * (2.0 * math.pi / n)


def phase_shift(ref, src):
    # 2D phase correlation: the integer (dx, dy) that best aligns `src`
    # onto `ref` (src shifted by (dx, dy) -> ref), plus the peak quality.
    # @return: (dx, dy, quality)
    a = np.fft.fft2(ref - np.mean(ref))
    b = np.fft.fft2(src - np.mean(src))
    cross = a * np.conj(b)
    cross /= np.abs(cross) + 1e-12
    corr = np.fft.ifft2(cross).real
    py, px = np.unravel_index(np.argmax(corr), corr.shape)
    h, w = corr.shape
    if py > h // 2:
        py -= h
    if px > w // 2:
        px -= w
    quality = float(corr.max() / (np.std(corr) + 1e-12))
    return int(px), int(py), quality


def _downsample(data, target=150):
    # Box-average downsample so the short side is about `target`.
    # @return: (small image, integer factor)
    h, w = data.shape
    f = max(1, int(min(h, w) / float(target)))
    if f == 1:
        return np.asarray(data, dtype=np.float64), 1
    hh, ww = (h // f) * f, (w // f) * f
    a = np.asarray(data[:hh, :ww], dtype=np.float64)
    return a.reshape(hh // f, f, ww // f, f).mean(axis=(1, 3)), f


def _subpixel_peak(corr):
    # Parabolic refinement of the correlation peak around the integer
    # maximum, in both axes.
    h, w = corr.shape
    py, px = np.unravel_index(np.argmax(corr), corr.shape)
    def _par(c0, c1, c2):
        denom = c0 - 2.0 * c1 + c2
        return 0.0 if abs(denom) < 1e-12 else 0.5 * (c0 - c2) / denom
    dy = _par(corr[(py - 1) % h, px], corr[py, px],
              corr[(py + 1) % h, px])
    dx = _par(corr[py, (px - 1) % w], corr[py, px],
              corr[py, (px + 1) % w])
    ys = py + dy
    xs = px + dx
    if ys > h / 2:
        ys -= h
    if xs > w / 2:
        xs -= w
    return float(xs), float(ys), float(corr[py, px])


def _phase_corr(ref, src):
    # @return: (dx, dy, quality) with subpixel precision
    a = np.fft.fft2(ref - np.mean(ref))
    b = np.fft.fft2(src - np.mean(src))
    cross = a * np.conj(b)
    cross /= np.abs(cross) + 1e-12
    corr = np.fft.ifft2(cross).real
    dx, dy, peak = _subpixel_peak(corr)
    quality = float(peak / (np.std(corr) + 1e-12))
    return -dx, -dy, quality


def estimate_transform(ref, src, coarse_deg=2.0, fine_deg=0.25,
                       target_px=150):
    # Estimate the similarity transform (rotation about the frame centre
    # plus translation) that maps `src` onto `ref`, robustly: a brute-force
    # rotation search on a downsampled image (phase correlation scores each
    # angle), a fine rotation sweep around the winner, then a subpixel
    # shift at full resolution.
    # @args: ref, src - 2D arrays (same shape), coarse_deg/fine_deg - angle
    #        steps, target_px - downsample size for the coarse search
    # @return: {"angle","dx","dy","quality"}
    ref_s, f = _downsample(ref, target_px)
    src_s, _ = _downsample(src, target_px)
    best = None
    for ang in np.arange(-180.0, 180.0, coarse_deg):
        rot = apply_rotation(src_s, math.radians(ang))
        _dx, _dy, q = _phase_corr(ref_s, rot)
        if best is None or q > best[1]:
            best = (float(ang), q)
    ang0 = best[0]
    for ang in np.arange(ang0 - coarse_deg, ang0 + coarse_deg + 1e-9,
                         0.1):
        rot = apply_rotation(src_s, math.radians(ang))
        _dx, _dy, q = _phase_corr(ref_s, rot)
        if q > best[1]:
            best = (float(ang), q)
    # full-resolution angle refinement (a 0.1 deg error over 300 px is a
    # whole pixel on a sharp star)
    ref_f = np.asarray(ref, dtype=np.float64)
    src_f = np.asarray(src, dtype=np.float64)
    bestq = None
    for ang in np.arange(best[0] - 0.3, best[0] + 0.3 + 1e-9, 0.05):
        rot = apply_rotation(src_f, math.radians(ang))
        dx, dy, q = _phase_corr(ref_f, rot)
        if bestq is None or q > bestq[3]:
            bestq = (float(ang), dx, dy, q)
    angle, dx, dy, q = bestq
    return {"angle": math.radians(angle), "dx": dx, "dy": dy,
            "quality": q}


def apply_rotation(data, angle):
    # Rotate `data` about its centre by `angle` (bilinear).
    # @return: the rotated image (same shape)
    return apply_transform(data, angle, 0.0, 0.0)


def apply_transform(data, angle, dx, dy):
    # Resample `data` onto the reference grid: the output pixel (x, y) is
    # read from the source at R(-angle) applied about the centre and then
    # shifted by (dx, dy).
    # @args: data - the frame to warp, angle - rotation applied to the
    #        source before the shift, dx/dy - integer shift
    # @return: the warped frame (same shape)
    h, w = data.shape
    cx, cy = w / 2.0, h / 2.0
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float64)
    px = xs - cx
    py = ys - cy
    ca, sa = math.cos(-angle), math.sin(-angle)
    sx = ca * px - sa * py + cx + dx
    sy = sa * px + ca * py + cy + dy
    return _bilinear(data, sx, sy)


def register_frame(src, ref):
    # Register one frame onto the reference and report the transform.
    # @return: (warped frame, transform dict)
    tr = estimate_transform(ref, src)
    warped = apply_transform(src, tr["angle"], tr["dx"], tr["dy"])
    return warped, tr
