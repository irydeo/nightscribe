############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Optional GPU backend for the stacking kernels (ADR-089)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""An OPTIONAL GPU path for the two memory-bound stacking kernels.

Why this exists, measured on the author's machine (RTX 3090 against a
16-thread Ryzen 9 5950X, 60 frames of 2048^2, ADR-089):

* the per-frame warp: 1434 ms on 16 CPU threads, **114 ms on the GPU** (x12.5);
* the sigma-clipped combine: 5416 ms on 16 CPU threads, **~1000 ms on the GPU**
  (x5.5), and the whole stack_group numeric part from 6850 ms to ~1250 ms.

The reason is bandwidth, not cores: a warp and a combine read and write
frame-sized arrays, and the machine's memory bus saturates at a handful of
threads (a PURE numpy median only scales x4.6 over 16 threads, measured), while
a GPU's bandwidth is an order of magnitude above it. That is the same reason
the CPU parallel walk of the registration tops out at ~x2.5.

Everything here is OPT-IN and its ABSENCE is the normal case. CuPy is never a
hard dependency: `available()` answers False on a machine without it (or
without a GPU, or with a broken driver) and the caller keeps its numpy path
untouched. Nothing is imported at module load, so a machine without a GPU pays
exactly nothing for this file existing.

The kernels are NOT a second implementation of the algorithm: they mirror
`track_stack._warp_to_box` and `track_stack.combine` line by line, and a unit
test pins the two to agree (they cannot be bit-identical, a GPU reduces in a
different order, so the test pins a tight ADU tolerance instead).
"""

import logging

import numpy as np

logger = logging.getLogger(__name__)

# The setting that turns the backend on. OFF by default: the observer's
# machine may have no GPU, the CPU path is the tested one, and a GPU that
# happens to be present should never change a result without being asked.
SETTING = "astrometry_gpu"

_state = {"checked": False, "ok": False, "cp": None, "cnd": None,
          "name": ""}


def available():
    # @return: True when CuPy and a usable CUDA device are both there
    # The probe runs ONCE and its answer is cached: importing CuPy and asking
    # for a device is not free, and the answer cannot change under a running
    # process. Every failure (no CuPy, no GPU, a driver mismatch) is caught
    # and turned into a plain False, because a missing accelerator is a normal
    # state and never an error the observer should see.
    if _state["checked"]:
        return _state["ok"]
    _state["checked"] = True
    try:
        import cupy as cp
        import cupyx.scipy.ndimage as cnd
        if cp.cuda.runtime.getDeviceCount() < 1:
            return False
        props = cp.cuda.runtime.getDeviceProperties(0)
        _state.update(cp=cp, cnd=cnd, ok=True,
                      name=props["name"].decode("ascii", "replace"))
    except Exception as err:
        logger.info("no GPU backend: %s", err)
        return False
    return True


def device_name():
    # @return: the device's name, or "" when there is no backend. For the
    #          run's own note: an accelerated result has to be able to say on
    #          WHAT it was computed.
    available()
    return _state["name"]


def enabled(cfg):
    # @args: cfg - Config, or None
    # @return: True when the observer asked for the backend AND it is there
    # Two gates, both required: the SETTING (the observer's explicit choice,
    # off by default) and the HARDWARE. Neither alone is enough, which is what
    # keeps a machine without a GPU on the exact path it always took.
    if cfg is None or not available():
        return False
    try:
        return bool(int(cfg.get(SETTING, 0) or 0))
    except (TypeError, ValueError):
        return False


def _affine_matrix(track_stack, tr, delta):
    # The same (row, col) affine `_warp_to_box` builds, so the GPU reads the
    # source exactly where the CPU would.
    # @args: track_stack - the module (imported lazily to avoid a cycle),
    #        tr - a register transform, delta - the object's offset (px)
    # @return: (A, b) in (row, col)
    A_xy, b_xy = track_stack._ref_to_native_affine(tr, delta)
    P = np.array([[0.0, 1.0], [1.0, 0.0]])
    return P @ A_xy @ P, P @ b_xy


def _warp_stack_gpu(cp, cnd, track_stack, frame_list, offsets, box, shape,
                    loader, order, preloaded):
    # @args: the pieces of a warp batch, already unpacked
    # @return: (stack, masks) both ON THE DEVICE, or None when the box is
    #          empty
    # The warp itself, kept on the device so a fused caller never downloads
    # the stack only to upload it again (that round trip was the whole reason
    # the warp measured x1.7 while the kernel is many times faster).
    cp_order = track_stack.WARP_ORDER if order is None else int(order)
    n = len(frame_list)
    out_h = box[3] - box[1]
    out_w = box[2] - box[0]
    if out_h <= 0 or out_w <= 0 or n == 0:
        return None
    stack = cp.empty((n, out_h, out_w), dtype=cp.float32)
    masks = cp.empty((n, out_h, out_w), dtype=cp.bool_)
    out_o = np.array([float(box[1]), float(box[0])])
    for k in range(n):
        frame = frame_list[k]
        A, b = _affine_matrix(track_stack, frame.transform, offsets[k])
        src_box = track_stack._source_box(A, b, box, shape)
        if src_box is None:
            # this frame does not cover the box: no data here, and saying so
            # is the honest answer (the same None the CPU path returns)
            stack[k] = 0.0
            masks[k] = False
            continue
        data = None
        if preloaded is not None:
            data = track_stack._slice_region(preloaded[k], src_box)
        if data is None:
            data = track_stack.read_pixels(loader, frame.path, src_box)
        src_o = np.array([float(src_box[1]), float(src_box[0])])
        offset = A @ out_o + b - src_o
        g = cp.asarray(np.asarray(data, dtype=np.float32))
        warped = cnd.affine_transform(
            g, cp.asarray(A), offset=cp.asarray(offset),
            output_shape=(out_h, out_w), order=cp_order,
            mode="constant", cval=0.0)
        ones = cnd.affine_transform(
            cp.ones_like(g), cp.asarray(A), offset=cp.asarray(offset),
            output_shape=(out_h, out_w), order=1,
            mode="constant", cval=0.0)
        stack[k] = warped
        masks[k] = ones > 0.5
    return stack, masks


def warp_batch(frame_list, offsets, box, shape, loader=None, order=None,
               preloaded=None):
    # @args: frame_list - list[Frame], offsets - one (dx, dy) per frame, box -
    #        the output box in reference (x0, y0, x1, y1), shape - the native
    #        frame, loader - optional array reader, order - the interpolation
    #        order, preloaded - optional list of (array, box) already in RAM
    # @return: (stack (n, h, w) float32, masks (n, h, w) bool), or None when
    #          the backend cannot serve this call (the caller then uses numpy)
    # The mirror of track_stack._warp_batch. Kept for the callers that want
    # the stack itself; the fused stack_ram below is what avoids the round
    # trip when the combine follows.
    if not available():
        return None
    from . import track_stack
    cp, cnd = _state["cp"], _state["cnd"]
    try:
        got = _warp_stack_gpu(cp, cnd, track_stack, frame_list, offsets, box,
                              shape, loader, order, preloaded)
        if got is None:
            return None
        stack, masks = got
        return cp.asnumpy(stack), cp.asnumpy(masks)
    except Exception as err:
        # A kernel that fails (an out-of-memory on a huge stack, a driver
        # hiccup) must NOT take the run down: the caller falls back to numpy
        # and the run finishes, only slower.
        logger.warning("GPU warp failed, falling back to CPU: %s", err)
        return None


def stack_ram(frame_list, offsets, box, shape, loader=None, order=None,
              preloaded=None, method="sigma", sigma=3.0, iterations=3,
              weights=None):
    # @args: the warp batch arguments, plus the combine's (method, sigma,
    #        iterations, weights)
    # @return: the combined (h, w) float32, or None when the backend cannot
    #          serve the call
    # THE FUSED PATH: warp and combine in one trip. The warped stack is built
    # ON the device and reduced there, so the only things that cross the bus
    # are the frames going up and the single combined image coming down. The
    # separate warp_batch + combine would move the whole stack down and up
    # again (measured on 60 x 2048^2: a 1 GB download and a 1 GB upload of
    # pure overhead per stack).
    if not available():
        return None
    from . import track_stack
    cp, cnd = _state["cp"], _state["cnd"]
    try:
        got = _warp_stack_gpu(cp, cnd, track_stack, frame_list, offsets, box,
                              shape, loader, order, preloaded)
        if got is None:
            return None
        stack, masks = got
        out = _combine_gpu(cp, stack, method, masks, sigma, iterations, weights)
        return cp.asnumpy(out).astype(np.float32)
    except Exception as err:
        logger.warning("GPU stack failed, falling back to CPU: %s", err)
        return None


def combine(stack, method, mask=None, sigma=3.0, iterations=3, weights=None):
    # @args: stack - (n, h, w) float32, method - one of track_stack.METHODS,
    #        mask - optional (n, h, w) validity, sigma/iterations - the clip,
    #        weights - optional (n,) per-frame weights
    # @return: the combined (h, w) float32, or None when the backend cannot
    #          serve the call
    # The mirror of track_stack.combine. The mask is applied by turning the
    # invalid pixels into NaN, exactly as the CPU path does, so the two
    # methods see the same data.
    if not available():
        return None
    cp = _state["cp"]
    try:
        out = _combine_gpu(cp, cp.asarray(np.asarray(stack, dtype=np.float32)),
                           method, mask, sigma, iterations, weights)
        return cp.asnumpy(out).astype(np.float32)
    except Exception as err:
        logger.warning("GPU combine failed, falling back to CPU: %s", err)
        return None


def _combine_gpu(cp, data, method, mask, sigma, iterations, weights):
    # @args: data - the cube ON the device, method, mask - (n, h, w) on the
    #        host or the device, sigma/iterations, weights
    # @return: the combined (h, w) ON the device
    # The one place the arithmetic lives, so the public combine and the fused
    # stack_ram cannot drift apart.
    if mask is not None:
        data = cp.where(cp.asarray(mask), data, cp.nan)
    if method == "weighted":
        return _combine_weighted(cp, data, weights, sigma, iterations)
    return _combine_masked(cp, data, method, sigma, iterations)


def _combine_masked(cp, data, method, sigma, iterations):
    # @return: the combined (h, w) on the device, the four methods
    if method == "sum":
        return cp.nansum(data, axis=0)
    if method == "mean":
        return cp.nanmean(data, axis=0)
    if method == "median":
        return cp.nanmedian(data, axis=0)
    keep = _sigma_clip_keep(cp, data, sigma, iterations)
    return cp.nanmean(cp.where(keep, data, cp.nan), axis=0)


def _combine_weighted(cp, data, weights, sigma, iterations):
    # @return: the clip, then the inverse-variance average of the survivors
    keep = _sigma_clip_keep(cp, data, sigma, iterations)
    if weights is None:
        return cp.nanmean(cp.where(keep, data, cp.nan), axis=0)
    w = cp.asarray(np.asarray(weights, dtype=np.float64).ravel()).reshape(
        (-1, 1, 1))
    ww = cp.broadcast_to(w, data.shape)
    num = cp.nansum(cp.where(keep, data * ww, cp.nan), axis=0)
    den = cp.sum(cp.where(keep, ww, 0.0), axis=0)
    return cp.where(den > 0, num / den, cp.nan)


def _sigma_clip_keep(cp, data, sigma, iterations):
    # @return: the (n, h, w) "this pixel survives the clip", the same walk as
    #          track_stack._sigma_clip_keep (median centre, MAD scale, three
    #          passes by default)
    med = cp.nanmedian(data, axis=0)
    keep = cp.isfinite(data)
    for _ in range(max(1, iterations)):
        mad = 1.4826 * cp.nanmedian(cp.abs(data - med), axis=0)
        mad = cp.where(mad > 0, mad, cp.inf)
        keep = keep & (cp.abs(data - med) <= sigma * mad)
        count = keep.sum(axis=0)
        with np.errstate(invalid="ignore"):
            new_med = cp.nansum(cp.where(keep, data, cp.nan), axis=0) \
                / cp.maximum(count, 1)
        med = cp.where(count > 0, new_med, med)
    return keep


# ======================================================================
# The registration's own kernels (ADR-089): the source image and the stars
# are the WHOLE cost of a per-frame estimate, and the block median that made
# the source image slow on the device is now a single kernel.
# ======================================================================

_BG_BLOCK = 32


def _block_grid_gpu(cp, arr, block):
    # @args: arr - the frame on the device, block - the cell size
    # @return: (grid, ys, xs), the block medians and the cell edges
    # The mirror of register._block_grid, ragged blocks INCLUDED: the edges
    # come from linspace TRUNCATED, exactly as on the CPU, so a frame that
    # does not divide by the block (the real 2008^2 case: 2008 % 32 = 24) gets
    # the same grid to the bit.
    #
    # Why not a loop of cp.median: the device then launches one kernel per
    # block and 3844 blocks cost 693 ms. Instead the blocks are SCATTERED into
    # a padded (bh, block+1, bw, block+1) array (NaN where a block is one row
    # or column shorter) and ONE nanmedian reduces them: measured on 2008^2,
    # 4.2 ms against the CPU's 92 ms, parity max 0.
    h, w = arr.shape
    bh = max(1, h // block)
    bw = max(1, w // block)
    ys = cp.linspace(0, h, bh + 1).astype(cp.int64)
    xs = cp.linspace(0, w, bw + 1).astype(cp.int64)
    if h % block == 0 and w % block == 0:
        return cp.median(arr.reshape(bh, block, bw, block),
                         axis=(1, 3)), ys, xs
    max_h = int((ys[1:] - ys[:-1]).max())
    max_w = int((xs[1:] - xs[:-1]).max())
    row_j = cp.clip(cp.searchsorted(ys, cp.arange(h), side="right") - 1,
                    0, bh - 1)
    row_p = cp.arange(h) - ys[row_j]
    col_j = cp.clip(cp.searchsorted(xs, cp.arange(w), side="right") - 1,
                    0, bw - 1)
    col_p = cp.arange(w) - xs[col_j]
    padded = cp.full((bh, max_h, bw, max_w), cp.nan, dtype=cp.float64)
    padded[row_j[:, None], row_p[:, None],
           col_j[None, :], col_p[None, :]] = arr
    flat = padded.transpose(0, 2, 1, 3).reshape(bh * bw, max_h * max_w)
    return cp.nanmedian(flat, axis=1).reshape(bh, bw), ys, xs


def _background_gpu(cp, data, block=_BG_BLOCK):
    # @args: data - the frame on the device, block - the grid block size
    # @return: the smooth background, same shape, on the device
    # The mirror of register._background: block medians, then a bilinear
    # re-expansion. The median shrugs off the stars a mean would drag up.
    arr = cp.asarray(data, dtype=cp.float64)
    h, w = arr.shape
    grid, ys, xs = _block_grid_gpu(cp, arr, block)
    bh = grid.shape[0]
    cy = (ys[:-1] + ys[1:] - 1) / 2.0
    cx = (xs[:-1] + xs[1:] - 1) / 2.0
    px = cp.arange(w, dtype=cp.float64)
    tmp = cp.empty((bh, w), dtype=cp.float64)
    for j in range(bh):
        tmp[j] = cp.interp(px, cx, grid[j])
    py = cp.arange(h, dtype=cp.float64)
    jy = cp.clip(cp.searchsorted(cy, py) - 1, 0, bh - 2)
    dy = cy[jy + 1] - cy[jy]
    wy = cp.where(dy > 0, (py - cy[jy]) / cp.where(dy > 0, dy, 1.0), 0.0)
    return tmp[jy] * (1.0 - wy)[:, None] + tmp[jy + 1] * wy[:, None]


def _source_image_gpu(cp, arr, block=_BG_BLOCK):
    # @return: the source image on the device (sky removed, negatives clipped)
    return cp.clip(cp.asarray(arr, dtype=cp.float64)
                   - _background_gpu(cp, arr, block), 0.0, None)


def _refine_gpu(cp, src, xs, ys):
    # The mirror of register._refine: a 7x7 centroid on the source image, its
    # background from the patch's border ring, the positives weighted.
    h, w = src.shape
    half = 3
    off = cp.arange(-half, half + 1)
    cx = cp.clip(cp.rint(xs).astype(cp.int64), half, w - 1 - half)
    cy = cp.clip(cp.rint(ys).astype(cp.int64), half, h - 1 - half)
    ii = cp.clip(cx[:, None] + off[None, :], 0, w - 1)
    jj = cp.clip(cy[:, None] + off[None, :], 0, h - 1)
    patch = src[jj[:, :, None], ii[:, None, :]]
    border = cp.concatenate([patch[:, 0, :], patch[:, -1, :],
                             patch[:, :, 0], patch[:, :, -1]], axis=1)
    base = cp.median(border, axis=1)[:, None, None]
    weight = cp.clip(patch - base, 0.0, None)
    tot = weight.sum(axis=(1, 2))
    wx = (weight * off[None, None, :]).sum(axis=(1, 2))
    wy = (weight * off[None, :, None]).sum(axis=(1, 2))
    good = tot > 0.0
    out_x = cp.where(good, cx + wx / cp.where(good, tot, 1.0), xs)
    out_y = cp.where(good, cy + wy / cp.where(good, tot, 1.0), ys)
    return out_x.astype(cp.float64), out_y.astype(cp.float64)


def _detect_stars_gpu(cp, src, nmax=60, k=8.0, margin=8, sat=None, factor=2):
    # The mirror of register.detect_stars: local maxima at least k robust
    # sigmas over the pixel noise, brightest first, refined to subpixel. The
    # search runs on a decimated copy and the positions are refined at full
    # resolution, exactly as on the CPU, so the two lists are comparable.
    import math
    empty = cp.empty((0, 3), dtype=cp.float64)
    arr = cp.asarray(src, dtype=cp.float64)
    h, w = arr.shape
    f = int(max(1, factor))
    if f > 1 and min(h, w) >= 4 * f:
        hh, ww = (h // f) * f, (w // f) * f
        small = arr[:hh, :ww].reshape(hh // f, f, ww // f, f).mean(axis=(1, 3))
    else:
        f = 1
        small = arr
    diffs = cp.concatenate([cp.diff(small, axis=1).ravel(),
                            cp.diff(small, axis=0).ravel()])
    diffs = diffs - cp.median(diffs)
    noise = 1.4826 * float(cp.median(cp.abs(diffs))) / math.sqrt(2.0)
    if not (noise > 0.0):
        return empty
    loc = cp.ones(small.shape, dtype=bool)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            loc &= small >= cp.roll(cp.roll(small, -dy, 0), -dx, 1)
    cand = loc & (small > k * noise)
    m = max(2, int(round(margin / f)))
    if 2 * m >= min(h, w):
        return empty
    cand[:m, :] = False
    cand[-m:, :] = False
    cand[:, :m] = False
    cand[:, -m:] = False
    ys, xs = cp.nonzero(cand)
    if xs.size == 0:
        return empty
    peaks = small[ys, xs]
    if sat is not None and sat > 0:
        keep = peaks < float(sat)
        ys, xs, peaks = ys[keep], xs[keep], peaks[keep]
        if xs.size == 0:
            return empty
    order = cp.argsort(peaks)[::-1][:nmax]
    xs = (xs[order] + 0.5) * f
    ys = (ys[order] + 0.5) * f
    peaks = peaks[order]
    fx, fy = _refine_gpu(cp, arr, xs, ys)
    return cp.column_stack([fx, fy, peaks])


def frame_stars(data, sat=None):
    # @args: data - a frame's pixels (ADU, any shape), sat - saturation
    #        ceiling (None keeps every peak, as the CPU path does)
    # @return: (source image (numpy float64), stars (N, 3) numpy) or None when
    #          the backend cannot serve the call
    # ONE upload per frame for BOTH kernels: the frame goes up once, the
    # source image and the stars are built on the device and the two results
    # come back. The source image's block median used to make this a loss (a
    # kernel per block, 693 ms on a frame that does not divide by the block);
    # with the scatter it is 4.2 ms, so both halves now pay.
    if not available():
        return None
    cp = _state["cp"]
    try:
        arr = cp.asarray(np.asarray(data, dtype=np.float64))
        src = _source_image_gpu(cp, arr)
        st = _detect_stars_gpu(cp, src, sat=sat)
        return cp.asnumpy(src), cp.asnumpy(st)
    except Exception as err:
        logger.warning("GPU registration kernels failed, falling back to CPU: "
                       "%s", err)
        return None
