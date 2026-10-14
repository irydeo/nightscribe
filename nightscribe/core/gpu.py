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


def warp_batch(frame_list, offsets, box, shape, loader=None, order=None,
               preloaded=None):
    # @args: frame_list - list[Frame], offsets - one (dx, dy) per frame, box -
    #        the output box in reference (x0, y0, x1, y1), shape - the native
    #        frame, loader - optional array reader, order - the interpolation
    #        order, preloaded - optional list of (array, box) already in RAM
    # @return: (stack (n, h, w) float32, masks (n, h, w) bool), or None when
    #          the backend cannot serve this call (the caller then uses numpy)
    # The mirror of track_stack._warp_batch. The frames are read on the CPU
    # (the page cache makes that cheap and the disk is the same either way),
    # uploaded, warped on the device and downloaded as ONE stack: the whole
    # point is that the reduction happens on the device, so the per-frame
    # round trip is never paid.
    if not available():
        return None
    from . import track_stack
    cp, cnd = _state["cp"], _state["cnd"]
    try:
        cp_order = track_stack.WARP_ORDER if order is None else int(order)
        n = len(frame_list)
        out_h = box[3] - box[1]
        out_w = box[2] - box[0]
        if out_h <= 0 or out_w <= 0 or n == 0:
            return None
        stack = np.empty((n, out_h, out_w), dtype=np.float32)
        masks = np.empty((n, out_h, out_w), dtype=bool)
        out_o = np.array([float(box[1]), float(box[0])])
        for k in range(n):
            frame = frame_list[k]
            A, b = _affine_matrix(track_stack, frame.transform, offsets[k])
            src_box = track_stack._source_box(A, b, box, shape)
            if src_box is None:
                # this frame does not cover the box: no data here, and saying
                # so is the honest answer (the same None the CPU path returns)
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
            stack[k] = cp.asnumpy(warped)
            masks[k] = cp.asnumpy(ones) > 0.5
        return stack, masks
    except Exception as err:
        # A kernel that fails (an out-of-memory on a huge stack, a driver
        # hiccup) must NOT take the run down: the caller falls back to numpy
        # and the run finishes, only slower.
        logger.warning("GPU warp failed, falling back to CPU: %s", err)
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
        g = cp.asarray(np.asarray(stack, dtype=np.float32))
        if mask is not None:
            g = cp.where(cp.asarray(mask), g, cp.nan)
        if method == "weighted":
            out = _combine_weighted(cp, g, weights, sigma, iterations)
        else:
            out = _combine_masked(cp, g, method, sigma, iterations)
        return cp.asnumpy(out).astype(np.float32)
    except Exception as err:
        logger.warning("GPU combine failed, falling back to CPU: %s", err)
        return None


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
