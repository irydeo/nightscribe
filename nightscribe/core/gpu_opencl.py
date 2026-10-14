############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Optional GPU backend: the OpenCL implementation (ADR-091)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The OpenCL backend of the optional GPU path (pyopencl).

OpenCL is the PORTABLE one: it runs on NVIDIA, AMD and Intel, and it is the
one the app can ship. Measured on the author's RTX 3090 against the CuPy path
(`tools/bench/bench_opencl.py`, 60 frames of 2048^2), it is not slower:

* the per-frame warp: 4.3 ms against the CuPy library call's 12.3 ms (x2.9
  FASTER), because a purpose-built bilinear kernel beats a general N-d
  transform;
* the mean combine: 1.2 ms against 1.5 ms (x1.25), and both are pure
  bandwidth, so the bus decides and the two agree;
* the median combine: 64.1 ms against 202.5 ms (x3.2), because a per-pixel
  selection beats sorting the whole cube.

What this module covers, and what it does NOT: the WARP and the COMBINE (the
two memory-bound kernels, and the 90 % of the time). The registration's
kernels (`frame_stars`) are NOT implemented here yet: its block median and
its star search are a different beast, and until they are ported the
registration falls back to the CPU on an OpenCL-only machine. Saying so is
better than a half-port that quietly changes a centroid.

The public surface is the same as the CUDA backend's, and every entry point
answers None when it cannot serve the call, so the caller keeps its numpy
path. Nothing is imported at module load.
"""

import logging

import numpy as np

logger = logging.getLogger(__name__)

# What the facade reports as the active backend.
NAME = "opencl"

# The methods, as the kernel's own enum (they mirror track_stack.METHODS).
M_SUM, M_MEAN, M_MEDIAN, M_SIGMA, M_WEIGHTED = range(5)
_METHODS = {"sum": M_SUM, "mean": M_MEAN, "median": M_MEDIAN,
            "sigma": M_SIGMA, "weighted": M_WEIGHTED}

# The most frames a single work-item can hold in private memory. A visit is
# dozens, not hundreds (the stacking groups are small), and the ceiling keeps
# the kernel's register use bounded; a bigger cube is served by the CPU.
_MAX_FRAMES = 128

KERNELS = r"""
// The per-frame WARP: the same affine `cupyx.scipy.ndimage.affine_transform`
// applies (output[i, j] samples input[A @ (i, j) + b]), bilinear, zero
// outside. One work-item per output pixel: no shared memory, no
// synchronisation, four source reads and one write.
__kernel void warp_bilinear(
    __global const float *src, const int sh, const int sw,
    __global float *dst, __global uchar *mask,
    const int dh, const int dw, const long dbase, const long mbase,
    const float a00, const float a01, const float a10, const float a11,
    const float bx, const float by)
{
    const int j = get_global_id(0);
    const int i = get_global_id(1);
    if (i >= dh || j >= dw) return;
    // dbase/mbase are this frame's SLICE of the whole stack: one buffer holds
    // every frame, so the kernel is told where its own output starts instead
    // of one buffer per frame (which is what a sub-buffer would cost).
    const long o = (long)i * dw + j;
    // scipy's convention, and it is not the one a (x, y) reading suggests:
    // `output[i, j] = input[A[0,0]*i + A[0,1]*j + b[0], A[1,0]*i + A[1,1]*j
    // + b[1]]`, i.e. the FIRST row of A builds the source ROW. Swapping them
    // transposes the warp, and the mask is what shows it first.
    const float sy = a00 * (float)i + a01 * (float)j + by;
    const float sx = a10 * (float)i + a11 * (float)j + bx;
    // scipy's `mode="constant", cval=0`: a coordinate OUTSIDE the source is
    // the cval for the WHOLE pixel (no partial coverage; measured, and it is
    // what the mask of a field of ones reproduces). Inside, the neighbour
    // that falls off the edge is CLAMPED, which is what scipy does too.
    if (sx < 0.0f || sy < 0.0f
            || sx > (float)(sw - 1) || sy > (float)(sh - 1)) {
        dst[dbase + o] = 0.0f;
        mask[mbase + o] = 0;
        return;
    }
    const int x0 = (int)sx;
    const int y0 = (int)sy;
    const int x1 = min(x0 + 1, sw - 1);
    const int y1 = min(y0 + 1, sh - 1);
    const float fx = sx - (float)x0;
    const float fy = sy - (float)y0;
    const float v00 = src[y0 * sw + x0];
    const float v01 = src[y0 * sw + x1];
    const float v10 = src[y1 * sw + x0];
    const float v11 = src[y1 * sw + x1];
    dst[dbase + o] = (1.0f - fy) * ((1.0f - fx) * v00 + fx * v01)
                   + fy * ((1.0f - fx) * v10 + fx * v11);
    mask[mbase + o] = 1;
}

// Sort a private array of m floats, ascending (an insertion sort: m is a few
// dozen, and the alternative is a selection network nobody can read).
static void sort_asc(float *v, const int m)
{
    for (int a = 1; a < m; ++a) {
        const float key = v[a];
        int b = a - 1;
        while (b >= 0 && v[b] > key) { v[b + 1] = v[b]; --b; }
        v[b + 1] = key;
    }
}

static float median_sorted(const float *v, const int m)
{
    return (m % 2) ? v[m / 2] : 0.5f * (v[m / 2 - 1] + v[m / 2]);
}

// The COMBINE: one work-item per output pixel, walking its own column of the
// cube. The methods are the app's own (track_stack.METHODS). A NaN is the
// app's "no data here" (a masked pixel), so every method skips it exactly as
// the numpy path does, and a caller that passes a mask gets it applied the
// same way.
__kernel void combine(
    __global const float *cube, __global const uchar *mask,
    __global const float *weights, __global float *out,
    const int n, const int hw, const int method,
    const float sigma, const int iterations)
{
    const int p = get_global_id(0);
    if (p >= hw) return;
    float v[128];
    float keep[128];
    int m = 0;
    for (int k = 0; k < n && m < 128; ++k) {
        if (mask != 0 && mask[(long)k * hw + p] == 0) continue;
        const float x = cube[(long)k * hw + p];
        if (x == x) v[m++] = x;
    }
    if (m == 0) { out[p] = NAN; return; }

    if (method == 0 || method == 1) {            // sum | mean
        float s = 0.0f;
        for (int i = 0; i < m; ++i) s += v[i];
        out[p] = (method == 1) ? s / (float)m : s;
        return;
    }
    if (method == 2) {                           // median
        sort_asc(v, m);
        out[p] = median_sorted(v, m);
        return;
    }

    // sigma (the clipped mean) and weighted (the inverse-variance mean) share
    // the clip: the MEDIAN centre, the MAD scale, `iterations` passes, the
    // keep CUMULATIVE (a pixel rejected in one pass stays out) and the centre
    // moving to the mean of the survivors each time. It is the same walk as
    // track_stack._sigma_clip_keep, step for step.
    float work[128];
    for (int i = 0; i < m; ++i) { work[i] = v[i]; keep[i] = 1.0f; }
    sort_asc(work, m);
    float centre = median_sorted(work, m);
    for (int it = 0; it < iterations; ++it) {
        float dev[128];
        for (int i = 0; i < m; ++i) dev[i] = fabs(v[i] - centre);
        sort_asc(dev, m);
        float mad = 1.4826f * median_sorted(dev, m);
        if (!(mad > 0.0f)) mad = INFINITY;
        float s = 0.0f;
        int c = 0;
        for (int i = 0; i < m; ++i) {
            if (keep[i] > 0.5f && fabs(v[i] - centre) <= sigma * mad) {
                s += v[i];
                c += 1;
            } else {
                keep[i] = 0.0f;
            }
        }
        if (c > 0) centre = s / (float)c;
    }
    if (method == 3) {                           // sigma: the mean of the rest
        float s = 0.0f;
        int c = 0;
        for (int i = 0; i < m; ++i) {
            if (keep[i] > 0.5f) { s += v[i]; c += 1; }
        }
        out[p] = c > 0 ? s / (float)c : NAN;
        return;
    }
    // weighted: sum(w * v) / sum(w) over the survivors, w per FRAME
    float num = 0.0f;
    float den = 0.0f;
    for (int k = 0, i = 0; k < n && i < m; ++k) {
        if (mask != 0 && mask[(long)k * hw + p] == 0) continue;
        const float x = cube[(long)k * hw + p];
        if (!(x == x)) continue;
        const float w = (weights != 0) ? weights[k] : 1.0f;
        if (keep[i] > 0.5f) { num += x * w; den += w; }
        i += 1;
    }
    out[p] = den > 0.0f ? num / den : NAN;
}
"""

_state = {"checked": False, "ok": False, "cl": None, "ctx": None,
          "queue": None, "program": None, "name": ""}


def _build():
    # @return: True when pyopencl and a device are both there
    # The probe runs ONCE and its answer is cached: importing pyopencl and
    # asking for a device is not free, and the answer cannot change under a
    # running process. Every failure (no pyopencl, no ICD, a broken driver) is
    # caught and turned into a plain False, because a missing accelerator is a
    # normal state and never an error the observer should see.
    if _state["checked"]:
        return _state["ok"]
    _state["checked"] = True
    try:
        import pyopencl as cl
        ctx = None
        for plat in cl.get_platforms():
            devices = plat.get_devices()
            if devices:
                ctx = cl.Context(devices[:1])
                break
        if ctx is None:
            return False
        queue = cl.CommandQueue(ctx)
        program = cl.Program(ctx, KERNELS).build()
        _state.update(cl=cl, ctx=ctx, queue=queue, program=program, ok=True,
                      name=ctx.devices[0].name.strip())
    except Exception as err:                                   # noqa: BLE001
        logger.info("no OpenCL backend: %s", err)
        return False
    return True


def available():
    # @return: True when pyopencl and a usable OpenCL device are both there
    return _build()


def device_name():
    # @return: the device's name, or "" when there is no backend
    _build()
    return _state["name"]


def _kernel(name):
    # @args: name - the kernel's name in KERNELS
    # @return: the compiled kernel, or None when there is no backend
    # cl.Kernel and not `program.name`: retrieving a kernel twice builds it
    # twice, and the warning pyopencl raises about it is a real cost.
    if not available():
        return None
    return _state["cl"].Kernel(_state["program"], name)


def _f32_buffer(array):
    # @args: array - a numpy array
    # @return: a read-only device buffer with a copy of it
    cl = _state["cl"]
    return cl.Buffer(_state["ctx"],
                     cl.mem_flags.READ_ONLY | cl.mem_flags.COPY_HOST_PTR,
                     hostbuf=np.ascontiguousarray(array))


def _empty(shape):
    # @return: a write-only device buffer of that byte size
    cl = _state["cl"]
    nbytes = int(np.prod(shape)) * 4
    return cl.Buffer(_state["ctx"], cl.mem_flags.WRITE_ONLY, nbytes)


def _read(buf, shape, dtype=np.float32):
    # @args: buf - a device buffer, shape - the array's shape
    # @return: the host array
    out = np.empty(shape, dtype=dtype)
    _state["cl"].enqueue_copy(_state["queue"], out, buf)
    _state["queue"].finish()
    return out


# ------------------------------------------------------------------- warp

def _affine_matrix(track_stack, tr, delta):
    # The same (row, col) affine `_warp_to_box` builds, so the GPU reads the
    # source exactly where the CPU would.
    A_xy, b_xy = track_stack._ref_to_native_affine(tr, delta)
    P = np.array([[0.0, 1.0], [1.0, 0.0]])
    return P @ A_xy @ P, P @ b_xy


def _warp_stack(frame_list, offsets, box, shape, loader, preloaded):
    # @args: the pieces of a warp batch, already unpacked
    # @return: (stack, masks) both ON THE DEVICE, or None when the box is
    #          empty
    # The warp itself, kept on the device so the fused stack_ram below never
    # downloads the stack only to upload it again.
    from . import track_stack
    cl = _state["cl"]
    queue = _state["queue"]
    kern = _kernel("warp_bilinear")
    n = len(frame_list)
    out_h = box[3] - box[1]
    out_w = box[2] - box[0]
    if out_h <= 0 or out_w <= 0 or n == 0:
        return None
    stack = cl.Buffer(_state["ctx"], cl.mem_flags.READ_WRITE,
                      n * out_h * out_w * 4)
    masks = cl.Buffer(_state["ctx"], cl.mem_flags.READ_WRITE,
                      n * out_h * out_w)
    out_o = np.array([float(box[1]), float(box[0])])
    for k in range(n):
        frame = frame_list[k]
        A, b = _affine_matrix(track_stack, frame.transform, offsets[k])
        src_box = track_stack._source_box(A, b, box, shape)
        if src_box is None:
            # this frame does not cover the box: no data here, and saying so
            # is the honest answer (the same None the CPU path returns)
            queue.enqueue_fill_buffer(stack, np.float32(0.0),
                                      k * out_h * out_w * 4,
                                      out_h * out_w * 4)
            queue.enqueue_fill_buffer(masks, np.uint8(0),
                                      k * out_h * out_w, out_h * out_w)
            continue
        data = None
        if preloaded is not None:
            data = track_stack._slice_region(preloaded[k], src_box)
        if data is None:
            data = track_stack.read_pixels(loader, frame.path, src_box)
        src_o = np.array([float(src_box[1]), float(src_box[0])])
        offset = A @ out_o + b - src_o
        src_arr = np.ascontiguousarray(data, dtype=np.float32)
        src = _f32_buffer(src_arr)
        # the SOURCE is the crop, not the whole frame: its own height and
        # width are what the bilinear sampling indexes, exactly as scipy and
        # cupyx do on the array they are handed
        kern(queue, (out_w, out_h), None,
             src, np.int32(src_arr.shape[0]), np.int32(src_arr.shape[1]),
             stack, masks, np.int32(out_h), np.int32(out_w),
             np.int64(k * out_h * out_w), np.int64(k * out_h * out_w),
             np.float32(A[0, 0]), np.float32(A[0, 1]),
             np.float32(A[1, 0]), np.float32(A[1, 1]),
             np.float32(offset[1]), np.float32(offset[0]))
    return stack, masks


def warp_batch(frame_list, offsets, box, shape, loader=None, order=None,
               preloaded=None):
    # @return: (stack (n, h, w) float32, masks (n, h, w) bool), or None
    if not available():
        return None
    try:
        got = _warp_stack(frame_list, offsets, box, shape, loader, preloaded)
        if got is None:
            return None
        stack, masks = got
        out_h = box[3] - box[1]
        out_w = box[2] - box[0]
        n = len(frame_list)
        return (_read(stack, (n, out_h, out_w)),
                _read(masks, (n, out_h, out_w), dtype=np.uint8) > 0)
    except Exception as err:                                   # noqa: BLE001
        # A kernel that fails must NOT take the run down: the caller falls
        # back to numpy and the run finishes, only slower.
        logger.warning("OpenCL warp failed, falling back to CPU: %s", err)
        return None


def stack_ram(frame_list, offsets, box, shape, loader=None, order=None,
              preloaded=None, method="sigma", sigma=3.0, iterations=3,
              weights=None):
    # @return: the combined (h, w) float32, or None
    # THE FUSED PATH: warp and combine in one trip, so the only things that
    # cross the bus are the frames going up and the single image coming down.
    if not available():
        return None
    try:
        got = _warp_stack(frame_list, offsets, box, shape, loader, preloaded)
        if got is None:
            return None
        stack, masks = got
        n = len(frame_list)
        out_h = box[3] - box[1]
        out_w = box[2] - box[0]
        out = _combine_device(stack, masks, n, out_h, out_w, method, sigma,
                              iterations, weights)
        return _read(out, (out_h, out_w)).astype(np.float32)
    except Exception as err:                                   # noqa: BLE001
        logger.warning("OpenCL stack failed, falling back to CPU: %s", err)
        return None


# ---------------------------------------------------------------- combine

def _combine_device(stack, masks, n, h, w, method, sigma, iterations,
                    weights):
    # @args: stack - the (n, h, w) cube ON the device, masks - the (n, h, w)
    #        validity ON the device (or None), the rest - the method's knobs
    # @return: the combined (h, w) ON the device
    cl = _state["cl"]
    queue = _state["queue"]
    if n > _MAX_FRAMES:
        raise ValueError(f"the OpenCL combine holds {_MAX_FRAMES} frames")
    hw = h * w
    out = _empty((h, w))
    wbuf = _f32_buffer(np.asarray(weights, dtype=np.float32)) \
        if weights is not None else None
    kern = _kernel("combine")
    kern(queue, (hw,), None, stack, masks, wbuf, out,
         np.int32(n), np.int32(hw), np.int32(_METHODS.get(method, M_SIGMA)),
         np.float32(sigma), np.int32(iterations))
    return out


def combine(stack, method, mask=None, sigma=3.0, iterations=3, weights=None):
    # @return: the combined (h, w) float32, or None
    if not available():
        return None
    try:
        cl = _state["cl"]
        data = np.ascontiguousarray(stack, dtype=np.float32)
        n, h, w = data.shape
        cube = cl.Buffer(_state["ctx"],
                         cl.mem_flags.READ_ONLY | cl.mem_flags.COPY_HOST_PTR,
                         hostbuf=data)
        mbuf = None
        if mask is not None:
            m = np.ascontiguousarray(mask).astype(np.uint8)
            mbuf = cl.Buffer(_state["ctx"],
                             cl.mem_flags.READ_ONLY
                             | cl.mem_flags.COPY_HOST_PTR, hostbuf=m)
        out = _combine_device(cube, mbuf, n, h, w, method, sigma, iterations,
                              weights)
        return _read(out, (h, w)).astype(np.float32)
    except Exception as err:                                   # noqa: BLE001
        logger.warning("OpenCL combine failed, falling back to CPU: %s", err)
        return None


# ------------------------------------------------------------ registration

def frame_stars(data, sat=None):
    # @args: data - a frame's pixels, sat - the saturation ceiling
    # @return: ALWAYS None, for now: the registration's kernels are not ported
    # The source image's block median and the star search are a different
    # beast from the two memory-bound kernels this backend covers, and a
    # half-port that quietly moved a centroid would be worse than no port. So
    # the registration keeps the CPU on an OpenCL-only machine, and the app
    # says which backend it used (the run's note).
    return None
