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
telescope, a mount that simply drifts) move between frames and carry no
WCS. The series engine measures at fixed reference coordinates, so those
frames must be brought back onto the reference grid first (D17/D44).

The estimate is a cascade, cheapest and safest first:

  1. the sky is removed (block medians), because a vignetted background
     dominates a Fourier correlation and used to send the alignment to a
     nonsense rotation;
  2. the subpixel translation comes from a Hann-windowed phase
     correlation (about 20 ms a frame);
  3. the translation is VERIFIED against the stars actually detected in
     the frame: how many pair up and how far they land from where the
     transform said (the honest quality metric);
  4. only when that residual says the frames do not merely shift does a
     rigid fit (rotation about the frame centre plus translation) enter,
     and only if it really improves the residual. A frame whose stars do
     not verify inherits the previous transform and is flagged, never
     silently trusted.

Pure numpy (ADR-004): no scipy, no astropy.
"""

import logging
import math

import numpy as np

from . import outliers

logger = logging.getLogger(__name__)

# Below this many paired stars the star verification cannot speak: the
# frame falls back to the correlation figure and, if that is weak too,
# the point is flagged "align_failed" instead of silently trusted.
MIN_MATCH = 6
# A paired-star residual above this (px) is not an alignment: the fit and
# the stars disagree, so the frame inherits the previous transform and is
# flagged. A real series lands at a few tenths of a pixel.
MAX_RMS_PX = 0.75
# Residual above which a translation is considered insufficient and the
# rigid fit is tried (px). The point spread of a real star sits here.
_ROTATE_TRIGGER_PX = 0.7
# The rigid fit only wins if it removes this fraction of the residual; a
# spurious rotation never does.
_RIGID_IMPROVE = 0.25
# The paired stars of a translation-only answer must actually SPAN the
# frame: a rotation about the centre leaves the stars near the centre
# almost still, and a handful of them will happily fit any translation.
_MIN_SPREAD = 0.12
# Fallback correlation peak against the robust sigma of the correlation
# map. Measured: a real alignment lands in the hundreds to thousands, a
# pair of frames with no common structure below ten.
QUALITY_MIN = 30.0
# Rotation beyond this between two consecutive frames is a re-point, not
# tracking: it is reported, never applied blind.
MAX_STEP_DEG = 15.0

_BG_BLOCK = 32          # background grid block (px)
_SEEING_REF_PX = 3.0    # a reference star's spread, for the star finder


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


# ---------------- the sky is not a star: remove it first ----------------

def _background(data, block=_BG_BLOCK):
    # A smooth background by block medians, bilinearly re-expanded. The
    # median shrugs off the stars a mean would drag up.
    # @args: data - 2D array, block - grid block size in pixels
    # @return: the background, same shape as data
    arr = np.asarray(data, dtype=np.float64)
    h, w = arr.shape
    bh = max(1, h // block)
    bw = max(1, w // block)
    ys = np.linspace(0, h, bh + 1).astype(np.int64)
    xs = np.linspace(0, w, bw + 1).astype(np.int64)
    grid = np.empty((bh, bw), dtype=np.float64)
    for j in range(bh):
        y0, y1 = ys[j], max(ys[j + 1], ys[j] + 1)
        for i in range(bw):
            x0, x1 = xs[i], max(xs[i + 1], xs[i] + 1)
            grid[j, i] = float(np.median(arr[y0:y1, x0:x1]))
    cy = (ys[:-1] + ys[1:] - 1) / 2.0
    cx = (xs[:-1] + xs[1:] - 1) / 2.0
    # expand along x for every grid row (few rows), then along y
    px = np.arange(w, dtype=np.float64)
    tmp = np.empty((bh, w), dtype=np.float64)
    for j in range(bh):
        tmp[j] = np.interp(px, cx, grid[j])
    py = np.arange(h, dtype=np.float64)
    jy = np.clip(np.searchsorted(cy, py) - 1, 0, bh - 2)
    dy = cy[jy + 1] - cy[jy]
    wy = np.where(dy > 0, (py - cy[jy]) / np.where(dy > 0, dy, 1.0), 0.0)
    return tmp[jy] * (1.0 - wy)[:, None] + tmp[jy + 1] * wy[:, None]


def source_image(data, block=_BG_BLOCK):
    # The image the alignment actually looks at: sky and vignetting
    # removed, negatives clipped. This is what makes the phase
    # correlation answer the real shift instead of the gradient.
    # @args: data - 2D array, block - background grid block size
    # @return: the source image (float64)
    arr = np.asarray(data, dtype=np.float64)
    return np.clip(arr - _background(arr, block), 0.0, None)


def _hann(shape):
    # @return: a separable Hann window of `shape`, so the frame edges do
    #          not leak into the Fourier correlation
    h, w = shape
    return np.outer(np.hanning(h), np.hanning(w))


# ---------------- translation ----------------

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


def _corr_quality(corr):
    # The correlation peak against the robust scatter of the whole map:
    # a figure that only speaks when the frames really share structure.
    # @return: peak / (robust sigma of the map)
    sigma = float(outliers.scaled_mad(corr))
    return float(corr.max()) / (sigma + 1e-12)


def _phase_corr(ref, src, window=None):
    # @args: ref, src - source images of the same shape
    # @return: (dx, dy, quality) where (dx, dy) is the shift that maps
    #          src onto ref (i.e. a feature of ref sits at ref + dx in
    #          src), with subpixel precision
    a = np.asarray(ref, dtype=np.float64)
    b = np.asarray(src, dtype=np.float64)
    if window is not None:
        a = a * window
        b = b * window
    fa = np.fft.fft2(a - np.mean(a))
    fb = np.fft.fft2(b - np.mean(b))
    cross = fa * np.conj(fb)
    cross /= np.abs(cross) + 1e-12
    corr = np.fft.ifft2(cross).real
    dx, dy, _peak = _subpixel_peak(corr)
    return -dx, -dy, _corr_quality(corr)


def phase_shift(ref, src):
    # 2D phase correlation of two raw images: the integer (dx, dy) that
    # best aligns `src` onto `ref` (src shifted by (dx, dy) -> ref),
    # plus the peak quality.
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
    quality = _corr_quality(corr)
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


def estimate_translation(ref_src, src_src, guess=None):
    # The shift that maps `src_src` onto `ref_src` (both source images,
    # see source_image), Hann-windowed and refined to subpixel. When a
    # guess comes from the previous frame it only seeds the window, the
    # correlation still answers for itself.
    # @args: ref_src, src_src - source images (same shape),
    #        guess - optional (dx, dy) from the previous frame
    # @return: {"dx", "dy", "quality"}
    window = _hann(ref_src.shape)
    dx, dy, q = _phase_corr(ref_src, src_src, window=window)
    return {"dx": dx, "dy": dy, "quality": q, "guess": guess}


# ---------------- stars: detect, pair, fit ----------------

_OFF7 = np.arange(-3, 4)


def _refine(src, xs, ys):
    # Subpixel position of each seed by a small centroid on the source
    # image: a 7x7 patch, the local background taken from the patch's
    # border ring (so a neighbour or a gradient does not drag it), and
    # the positives weighted. Good to a few hundredths of a pixel on a
    # bright star.
    # @args: src - source image, xs/ys - integer-ish seeds
    # @return: (x, y) float arrays
    h, w = src.shape
    half = 3
    cx = np.clip(np.rint(xs).astype(np.int64), half, w - 1 - half)
    cy = np.clip(np.rint(ys).astype(np.int64), half, h - 1 - half)
    ii = np.clip(cx[:, None] + _OFF7[None, :], 0, w - 1)
    jj = np.clip(cy[:, None] + _OFF7[None, :], 0, h - 1)
    patch = src[jj[:, :, None], ii[:, None, :]]
    border = np.concatenate([patch[:, 0, :], patch[:, -1, :],
                             patch[:, :, 0], patch[:, :, -1]], axis=1)
    base = np.median(border, axis=1)[:, None, None]
    weight = np.clip(patch - base, 0.0, None)
    tot = weight.sum(axis=(1, 2))
    wx = (weight * _OFF7[None, None, :]).sum(axis=(1, 2))
    wy = (weight * _OFF7[None, :, None]).sum(axis=(1, 2))
    good = tot > 0.0
    out_x = np.where(good, cx + wx / np.where(good, tot, 1.0), xs)
    out_y = np.where(good, cy + wy / np.where(good, tot, 1.0), ys)
    return out_x.astype(np.float64), out_y.astype(np.float64)


def detect_stars(src, nmax=60, k=8.0, margin=8, sat=None, factor=2):
    # Stellar seeds on a source image: local maxima at least k robust
    # sigmas over the pixel-to-pixel noise, brightest first, refined to
    # subpixel. The search runs on a decimated copy (four times cheaper)
    # and the positions are refined at full resolution.
    # @args: src - source image, nmax - cap, k - significance,
    #        margin - border to ignore (px), sat - saturation ceiling in
    #        the source image's units (peaks at or above are dropped),
    #        factor - decimation for the search
    # @return: (N, 3) array of [x, y, peak], brightest first
    empty = np.empty((0, 3), dtype=np.float64)
    arr = np.asarray(src, dtype=np.float64)
    h, w = arr.shape
    f = int(max(1, factor))
    if f > 1 and min(h, w) >= 4 * f:
        hh, ww = (h // f) * f, (w // f) * f
        small = arr[:hh, :ww].reshape(hh // f, f, ww // f, f).mean(axis=(1, 3))
    else:
        f = 1
        small = arr
    diffs = np.concatenate([np.diff(small, axis=1).ravel(),
                            np.diff(small, axis=0).ravel()])
    noise = float(outliers.scaled_mad(diffs)) / math.sqrt(2.0)
    if not np.isfinite(noise) or noise <= 0.0:
        return empty
    loc = np.ones(small.shape, dtype=bool)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            loc &= small >= np.roll(np.roll(small, -dy, 0), -dx, 1)
    cand = loc & (small > k * noise)
    m = max(2, int(round(margin / f)))
    if 2 * m >= min(h, w):
        return empty
    cand[:m, :] = False
    cand[-m:, :] = False
    cand[:, :m] = False
    cand[:, -m:] = False
    ys, xs = np.where(cand)
    if xs.size == 0:
        return empty
    peaks = small[ys, xs]
    if sat is not None and sat > 0:
        keep = peaks < float(sat)
        ys, xs, peaks = ys[keep], xs[keep], peaks[keep]
        if xs.size == 0:
            return empty
    order = np.argsort(peaks)[::-1][:nmax]
    xs = (xs[order] + 0.5) * f
    ys = (ys[order] + 0.5) * f
    peaks = peaks[order]
    fx, fy = _refine(arr, xs, ys)
    return np.column_stack([fx, fy, peaks])


def _vote(ref_xy, src_xy, shape, angles, tol=2.0):
    # The transform seed by a vote among the stars: for every candidate
    # rotation, every (reference, frame) pair implies a translation; the
    # true transform is the one that many independent pairs agree on.
    # This replaces the Fourier rotation search (which a vignetted
    # background used to fool) and costs a few milliseconds, because the
    # star lists are short.
    # @args: ref_xy - (N,2) reference stars, src_xy - (M,2) frame stars,
    #        shape - frame (h, w) (the rotation centre), angles - the
    #        candidate rotations (radians), tol - voting tolerance (px)
    # @return: (angle, dx, dy, votes) or None
    n, m = len(ref_xy), len(src_xy)
    if n == 0 or m == 0:
        return None
    cx, cy = shape[1] / 2.0, shape[0] / 2.0
    best = None
    for ang in angles:
        ca, sa = math.cos(-ang), math.sin(-ang)
        rx = ref_xy[:, 0] - cx
        ry = ref_xy[:, 1] - cy
        px = ca * rx - sa * ry + cx
        py = sa * rx + ca * ry + cy
        ddx = src_xy[None, :, 0] - px[:, None]
        ddy = src_xy[None, :, 1] - py[:, None]
        # a coarse 2D histogram of the implied shift, then the mean of
        # the pairs that sit on the mode (that mean is already subpixel)
        bin_px = 2.0 * tol
        key = (np.round(ddx / bin_px).astype(np.int64) * 100000
               + np.round(ddy / bin_px).astype(np.int64))
        vals, counts = np.unique(key, return_counts=True)
        if vals.size == 0:
            continue
        k = int(np.argmax(counts))
        cx0 = float(np.mean(ddx[key == vals[k]]))
        cy0 = float(np.mean(ddy[key == vals[k]]))
        sel = (np.abs(ddx - cx0) <= tol) & (np.abs(ddy - cy0) <= tol)
        votes = int(sel.sum())
        if votes == 0:
            continue
        dx = float(np.mean(ddx[sel]))
        dy = float(np.mean(ddy[sel]))
        if best is None or votes > best[3]:
            best = (float(ang), dx, dy, votes)
    return best


def predict_xy(ref_xy, dx, dy, angle, shape):
    # Where the reference stars land in the frame under a transform of
    # the module's convention (the inverse of ref_to_src_point, vectorised).
    # @args: ref_xy - (N,2) reference positions, dx/dy/angle - the
    #        transform, shape - the (h, w) frame shape
    # @return: (N,2) predicted frame positions
    cx, cy = shape[1] / 2.0, shape[0] / 2.0
    ca, sa = math.cos(-angle), math.sin(-angle)
    px = ref_xy[:, 0] - cx
    py = ref_xy[:, 1] - cy
    return np.column_stack([ca * px - sa * py + cx + dx,
                            sa * px + ca * py + cy + dy])


def _pair(ref_xy, src_xy, dx, dy, tol, angle=0.0, shape=None):
    # Greedy one-to-one pairing of two star lists under a predicted
    # transform, nearest first.
    # @args: ref_xy - (N,2) reference stars, src_xy - (M,2) frame stars,
    #        dx/dy/angle - predicted transform, shape - frame (h, w) for
    #        the rotation centre, tol - pairing tolerance (px)
    # @return: (ref_indexes, src_indexes) arrays
    if len(ref_xy) == 0 or len(src_xy) == 0:
        return np.empty(0, dtype=np.int64), np.empty(0, dtype=np.int64)
    if angle and shape is not None:
        pred = predict_xy(ref_xy, dx, dy, angle, shape)
    else:
        pred = ref_xy + np.asarray([dx, dy], dtype=float)
    ddx = pred[:, 0][:, None] - src_xy[None, :, 0]
    ddy = pred[:, 1][:, None] - src_xy[None, :, 1]
    dist = np.hypot(ddx, ddy)
    keep = np.flatnonzero(dist.ravel() <= tol)
    ri, si = [], []
    used_r, used_s = set(), set()
    for flat in keep[np.argsort(dist.ravel()[keep])]:
        i, j = divmod(int(flat), dist.shape[1])
        if i in used_r or j in used_s:
            continue
        ri.append(i)
        si.append(j)
        used_r.add(i)
        used_s.add(j)
    return np.asarray(ri, dtype=np.int64), np.asarray(si, dtype=np.int64)


def _fit_rigid(ref_xy, src_xy, shape):
    # Rigid least squares (rotation about the frame centre plus
    # translation) mapping the reference stars onto the frame stars, in
    # the module's convention: a reference pixel p sits in the frame at
    # R(-angle) (p - c) + c + (dx, dy).
    # @args: ref_xy, src_xy - (N,2) matched positions, shape - frame (h, w)
    # @return: {"angle", "dx", "dy", "scale", "rms_px", "n"} or None
    n = len(ref_xy)
    if n < 2:
        return None
    pc = ref_xy.mean(axis=0)
    qc = src_xy.mean(axis=0)
    p = ref_xy - pc
    q = src_xy - qc
    norms = float(np.sum(np.square(p)))
    u, s, vt = np.linalg.svd(p.T @ q)
    rot = vt.T @ u.T
    if np.linalg.det(rot) < 0.0:
        vt[-1, :] *= -1.0
        rot = vt.T @ u.T
    scale = float(np.sum(s)) / norms if norms > 0.0 else 1.0
    phi = math.atan2(rot[1, 0], rot[0, 0])
    delta = qc - rot @ pc
    centre = np.asarray([shape[1] / 2.0, shape[0] / 2.0], dtype=float)
    # the fit works in absolute pixels (src = R(phi) ref + delta); the
    # module's convention keeps the translation in the ROTATED frame, so
    # the two differ by the centre term
    d = delta + rot @ centre - centre
    y = ref_xy @ rot.T + delta
    resid = np.hypot(y[:, 0] - src_xy[:, 0], y[:, 1] - src_xy[:, 1])
    rms = float(np.sqrt(np.mean(np.square(resid))))
    return {"angle": -phi, "dx": float(d[0]), "dy": float(d[1]),
            "scale": scale, "rms_px": rms, "n": int(n)}


def _fit_translation(ref_xy, src_xy, dx, dy):
    # @return: the same shape as _fit_rigid with the rotation pinned to 0
    #          (the shift is the mean of the paired displacements)
    if len(ref_xy) == 0:
        return None
    mx = float(np.mean(src_xy[:, 0] - ref_xy[:, 0]))
    my = float(np.mean(src_xy[:, 1] - ref_xy[:, 1]))
    resid = np.hypot(ref_xy[:, 0] + mx - src_xy[:, 0],
                     ref_xy[:, 1] + my - src_xy[:, 1])
    rms = float(np.sqrt(np.mean(np.square(resid))))
    return {"angle": 0.0, "dx": mx, "dy": my, "scale": 1.0,
            "rms_px": rms, "n": int(len(ref_xy))}


def estimate_transform(ref, src, guess=None, ref_stars=None, sat=None,
                       tol=3.0, allow_rotation=True):
    # Estimate the transform that maps `src` onto `ref` (rotation about
    # the frame centre plus subpixel translation), in the module's
    # convention: {"angle", "dx", "dy"} so that apply_transform(src,
    # angle, dx, dy) lands on the reference grid and ref_to_src_point
    # maps a reference pixel to its frame pixel.
    #
    # The cascade: the sky is removed, the stars vote for the transform
    # (see _vote), the pairs are then refined by a rigid least squares and
    # the answer is only trusted when enough stars verified it and landed
    # where it said. A translation that needs no rotation stays a
    # translation: the rotation has to EARN its place by removing real
    # residual.
    #
    # @args: ref, src - 2D arrays (same shape), guess - optional
    #        {"dx","dy"} from the previous frame (only a hint for the
    #        vote window), ref_stars - optional detect_stars output for
    #        the reference (the caller caches it), sat - saturation
    #        ceiling, tol - star pairing tolerance (px), allow_rotation -
    #        False pins the answer to a translation (the observer asked
    #        for "translation only")
    # @return: {"angle", "dx", "dy", "quality", "rms_px", "n",
    #          "scale", "angle_deg", "shift_px", "stars", "rotated"}
    ref_src = source_image(ref)
    src_src = source_image(src)
    shape = tuple(np.shape(ref))
    if ref_stars is None:
        ref_stars = detect_stars(ref_src, sat=sat)
    src_stars = detect_stars(src_src, sat=sat)
    out = {"angle": 0.0, "dx": 0.0, "dy": 0.0, "quality": 0.0,
           "rms_px": None, "n": 0, "scale": 1.0, "angle_deg": 0.0,
           "shift_px": 0.0, "spread": 0.0,
           "stars": {"ref": int(len(ref_stars)),
                     "src": int(len(src_stars)),
                     "matched": 0},
           "rotated": False, "source": "stars"}
    ref_xy = ref_stars[:, :2]
    src_xy = src_stars[:, :2]
    enough = len(ref_xy) >= MIN_MATCH and len(src_xy) >= MIN_MATCH
    if enough:
        # a smooth series: the previous frame's transform is the best
        # first guess and it costs one pairing
        if guess is not None and guess.get("n"):
            seed = _pair_fit(ref_xy, src_xy, guess["dx"], guess["dy"],
                             guess["angle"], tol, shape)
            if seed is not None and seed["n"] >= MIN_MATCH \
                    and seed["rms_px"] <= _ROTATE_TRIGGER_PX \
                    and seed.get("spread", 0.0) >= _MIN_SPREAD:
                out.update(_from_fit(seed, len(ref_xy), len(src_xy)))
                return out
        # H0: the plain translation. If it already explains the stars
        # across the frame, there is nothing left for a rotation to
        # explain; a translation that only fits the stars near the
        # rotation centre is not proof of anything.
        base = _vote(ref_xy, src_xy, shape, (0.0,), tol=tol)
        if base is not None and base[3] >= MIN_MATCH:
            trans = _pair_fit(ref_xy, src_xy, base[1], base[2], base[0],
                              tol, shape, rigid=False)
            if trans is not None:
                out.update(_from_fit(trans, len(ref_xy), len(src_xy)))
                if trans["rms_px"] <= _ROTATE_TRIGGER_PX \
                        and trans.get("spread", 0.0) >= _MIN_SPREAD:
                    return out
        # H1: a rotation is only worth looking for when H0 could not
        # explain the stars; then the vote scans the circle on a coarse
        # grid (2 deg) and refines around the winner.
        if not allow_rotation:
            return out
        angles = [math.radians(a) for a in range(-180, 180, 2)]
        vote = _vote(ref_xy, src_xy, shape, angles, tol=tol)
        if vote is not None and vote[3] >= MIN_MATCH:
            # refine the angle around the winner: 0.1 deg is far finer
            # than the fit needs (the pairing tolerance absorbs the rest)
            fine = [vote[0] + math.radians(a) for a in
                    (x * 0.1 for x in range(-10, 11))]
            vote2 = _vote(ref_xy, src_xy, shape, fine, tol=tol)
            if vote2 is not None and vote2[3] > vote[3]:
                vote = vote2
            rig = _pair_fit(ref_xy, src_xy, vote[1], vote[2], vote[0],
                            tol, shape)
            if rig is not None:
                if out["rms_px"] is None or out["n"] < MIN_MATCH \
                        or rig["rms_px"] <= (1.0 - _RIGID_IMPROVE) * \
                        out["rms_px"]:
                    out.update(_from_fit(rig, len(ref_xy), len(src_xy)))
    if out["n"] >= MIN_MATCH:
        return out
    # star-poor field: the Fourier correlation is all that is left, and
    # it can only speak for a pure translation
    tr = estimate_translation(ref_src, src_src, guess=guess)
    out.update({"source": "correlation", "dx": float(tr["dx"]),
                "dy": float(tr["dy"]), "quality": float(tr["quality"]),
                "shift_px": float(math.hypot(tr["dx"], tr["dy"]))})
    return out


def _from_fit(fit, n_ref, n_src):
    # @return: the estimate_transform fields a fitted transform fills
    return {"angle": float(fit["angle"]), "dx": float(fit["dx"]),
            "dy": float(fit["dy"]), "rms_px": float(fit["rms_px"]),
            "n": int(fit["n"]), "scale": float(fit["scale"]),
            "angle_deg": math.degrees(float(fit["angle"])),
            "shift_px": float(math.hypot(fit["dx"], fit["dy"])),
            "spread": float(fit.get("spread") or 0.0),
            "rotated": abs(float(fit["angle"])) > 1e-6,
            "stars": {"ref": int(n_ref), "src": int(n_src),
                      "matched": int(fit["n"])}}


def _spread(xy, shape):
    # How much of the frame the given stars span: their rms radius
    # around their own centroid, against the frame's half diagonal.
    # @args: xy - (N,2) positions, shape - frame (h, w)
    # @return: 0..1
    xy = np.asarray(xy, dtype=float)
    if len(xy) < 2:
        return 0.0
    r = xy - xy.mean(axis=0)
    diag = 0.5 * math.hypot(float(shape[0]), float(shape[1]))
    return float(np.sqrt(np.mean(np.sum(np.square(r), axis=1)))) / max(
        diag, 1e-9)


def _pair_fit(ref_xy, src_xy, dx, dy, angle, tol, shape, rigid=True):
    # Pair under a seeded transform and refine it by least squares,
    # widening the tolerance while the pair count grows (a rotation moves
    # the corner stars much further than the centre ones).
    # @args: ref_xy/src_xy - star lists, dx/dy/angle - the seed, tol -
    #        pairing tolerance (px), shape - frame (h, w), rigid - True
    #        fits a rotation, False pins the translation alone
    # @return: a _fit_rigid dict, or None when nothing pairs
    ri, si = _pair(ref_xy, src_xy, dx, dy, tol, angle=angle, shape=shape)
    if len(ri) < 2:
        return None
    fit = _fit_rigid(ref_xy[ri], src_xy[si], shape) if rigid \
        else _fit_translation(ref_xy[ri], src_xy[si], dx, dy)
    prev_n = len(ri)
    for _round in range(3):
        if fit is None:
            break
        grow = max(tol, fit["rms_px"] * 3.0)
        ri2, si2 = _pair(ref_xy, src_xy, fit["dx"], fit["dy"], grow,
                         angle=fit["angle"], shape=shape)
        if len(ri2) < 2:
            break
        fit2 = _fit_rigid(ref_xy[ri2], src_xy[si2], shape) if rigid \
            else _fit_translation(ref_xy[ri2], src_xy[si2], fit["dx"],
                                  fit["dy"])
        if fit2 is None or len(ri2) < prev_n:
            break
        if len(ri2) == prev_n and fit2["rms_px"] >= fit["rms_px"]:
            break
        fit, prev_n = fit2, len(ri2)
    if fit is not None:
        fit["spread"] = _spread(ref_xy[ri], shape)
    return fit


def trusted(tr):
    # The honest quality gate (D44): the transform is trusted when
    # enough stars verified it and they land close to where it said. A
    # star-poor field falls back to the correlation figure, and a frame
    # that fails both is flagged, never silently used.
    # @args: tr - estimate_transform output
    # @return: bool
    if tr is None:
        return False
    n = int(tr.get("n") or 0)
    rms = tr.get("rms_px")
    if n >= MIN_MATCH and rms is not None and rms <= MAX_RMS_PX:
        return True
    if n >= MIN_MATCH and rms is not None:
        return False
    return float(tr.get("quality") or 0.0) >= QUALITY_MIN


# ---------------- resampling on the reference grid ----------------

def apply_rotation(data, angle):
    # Rotate `data` about its centre by `angle` (bilinear).
    # @return: the rotated image (same shape)
    return apply_transform(data, angle, 0.0, 0.0)


def apply_transform(data, angle, dx, dy):
    # Resample `data` onto the reference grid: the output pixel (x, y) is
    # read from the source at R(-angle) applied about the centre and then
    # shifted by (dx, dy).
    # @args: data - the frame to warp, angle - rotation applied to the
    #        source before the shift, dx/dy - the shift (px)
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


def warp_mask(shape, angle, dx, dy):
    # Validity mask of a warp: True where the warped pixel reads a real
    # source pixel, False where the warp fills with zeros (the aperture
    # flux there is inflated when the sky is near zero).
    # @args: shape - (h, w) of the warped frame, angle/dx/dy - the
    #        apply_transform parameters
    # @return: boolean numpy array of `shape`
    h, w = shape
    cx, cy = w / 2.0, h / 2.0
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float64)
    px = xs - cx
    py = ys - cy
    ca, sa = math.cos(-angle), math.sin(-angle)
    sx = ca * px - sa * py + cx + dx
    sy = sa * px + ca * py + cy + dy
    return (sx >= 0) & (sx <= w - 1) & (sy >= 0) & (sy <= h - 1)


def register_frame(src, ref, sat=None):
    # Register one frame onto the reference and report the transform.
    # @return: (warped frame, transform dict) with validity mask and
    #          "failed" when the transform is not trusted
    tr = estimate_transform(ref, src, sat=sat)
    warped = apply_transform(src, tr["angle"], tr["dx"], tr["dy"])
    tr["mask"] = warp_mask(src.shape, tr["angle"], tr["dx"], tr["dy"])
    tr["failed"] = not trusted(tr)
    return warped, tr


def ref_to_src_point(tr, point, shape):
    # Map a reference-frame pixel to its source-frame position.
    # @args: tr - the estimate_transform result, point - (x, y) in the
    #        reference frame, shape - the (h, w) frame shape
    # @return: (x, y) in the source frame
    cx, cy = shape[1] / 2.0, shape[0] / 2.0
    ca, sa = math.cos(-tr["angle"]), math.sin(-tr["angle"])
    px, py = point[0] - cx, point[1] - cy
    return (ca * px - sa * py + cx + tr["dx"],
            sa * px + ca * py + cy + tr["dy"])


def src_to_ref_point(tr, point, shape):
    # The inverse: a source-frame pixel back to reference coordinates.
    # @return: (x, y) in the reference frame
    cx, cy = shape[1] / 2.0, shape[0] / 2.0
    ca, sa = math.cos(tr["angle"]), math.sin(tr["angle"])
    px, py = point[0] - cx - tr["dx"], point[1] - cy - tr["dy"]
    return (ca * px - sa * py + cx, sa * px + ca * py + cy)


def compose_wcs(wcs, tr):
    # A per-frame WCS: the reference WCS composed with the measured
    # transform, so sky_to_pixel maps onto the source frame's native grid
    # (rotation about the centre plus translation; TAN stays linear here).
    # @args: wcs - the reference Wcs, tr - estimate_transform result
    # @return: a Wcs onto the source frame
    from . import wcs as wcs_mod
    angle, dx, dy = tr["angle"], tr["dx"], tr["dy"]
    ca, sa = math.cos(angle), math.sin(angle)
    cd = wcs.cd
    new_cd = [[cd[0][0] * ca + cd[0][1] * sa,
               cd[0][0] * (-sa) + cd[0][1] * ca],
              [cd[1][0] * ca + cd[1][1] * sa,
               cd[1][0] * (-sa) + cd[1][1] * ca]]
    cx, cy = wcs.naxis1 / 2.0, wcs.naxis2 / 2.0
    q0 = (wcs.crpix1 - 1.0, wcs.crpix2 - 1.0)
    px, py = ref_to_src_point(tr, q0, (wcs.naxis2, wcs.naxis1))
    return wcs_mod.Wcs(wcs.crval1, wcs.crval2, px + 1.0, py + 1.0,
                       new_cd, wcs.naxis1, wcs.naxis2)
