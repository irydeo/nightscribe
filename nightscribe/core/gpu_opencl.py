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

* the per-frame warp: 4.0 ms against the CuPy library call's 10.7 ms (x2.7
  FASTER), because a purpose-built bilinear kernel beats a general N-d
  transform;
* the mean combine: 1.3 ms against 1.5 ms (x1.15), and both are pure
  bandwidth, so the bus decides and the two agree;
* the median combine: 64.7 ms against 202.4 ms (x3.1), because a per-pixel
  selection beats sorting the whole cube.

What this module covers: the WARP, the COMBINE and, since ADR-091, the
registration (`frame_stars`: the source image's block medians and background,
and the star detection's decimation, noise and local maxima). The estimate's
two medians are the whole reason the registration is worth porting (measured
on a 2048^2 frame: 101 ms of a 170 ms estimate), and OpenCL has no median, so
they are a radix SELECT on the sortable bit pattern of the float. Measured on
the author's RTX 3090, the whole per-frame estimate goes from 169.5 ms on the
CPU to 12.5 ms (x13.6).

The COMBINE has TWO kernels and the frame count alone picks: a private-array
one that holds the column in registers (the fast path for the short cubes the
stacking groups make) and a SCALABLE one that walks the column in GLOBAL
memory, so the frame ceiling is gone and the base stack (the WHOLE sequence, a
real visit is hundreds of frames) stays on the device. Measured on 539 frames
of 1024^2: the sigma combine 0.93 s on the device against 10.6 s on the CPU,
and the whole base stack 1.2 s against 6.3 s.

The registration runs in FLOAT by default and there is a DOUBLE build (the
exact-parity one) one line away: measured, the float star list is the same as
the CPU's (positions to 1.35e-7 px) and the double one is bit-identical, but
the double is 2.6x slower on a consumer card (fp64 runs at 1/64 of fp32
there). See _FORCE_WIDE.

The public surface is the same as the CUDA backend's, and every entry point
answers None when it cannot serve the call, so the caller keeps its numpy
path. Nothing is imported at module load.
"""

import logging
import math

import numpy as np

logger = logging.getLogger(__name__)

# What the facade reports as the active backend.
NAME = "opencl"

# The methods, as the kernel's own enum (they mirror track_stack.METHODS).
M_SUM, M_MEAN, M_MEDIAN, M_SIGMA, M_WEIGHTED = range(5)
_METHODS = {"sum": M_SUM, "mean": M_MEAN, "median": M_MEDIAN,
            "sigma": M_SIGMA, "weighted": M_WEIGHTED}

# The PRIVATE combine kernel keeps one column in its work-item's private
# memory, so its arrays are [128] and it can never see a taller cube. Measured
# on 2048^2 it is FASTER than the scalable one only while the column is SHORT:
# the median ~2x at n=32-64 and the sigma clip ~2.5x, they tie near n=96 and
# the scalable wins from ~128 up (measured 2026-10-15). So it serves the short
# cubes the stacking groups and the star stack make, and the SCALABLE one
# serves the base stack, which is the WHOLE sequence (a real visit at 539
# frames). This is the dispatch line, a little under the kernel's own hard
# limit on purpose.
_PRIVATE_COMBINE_MAX = 96

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

// ======================================================================
// The SCALABLE combine: ANY number of frames.
//
// The combine above holds one column in the work-item's PRIVATE memory and so
// caps at 128 frames; a base stack is the WHOLE sequence and a real visit is
// hundreds (measured: the author's Sar2949, 539 frames), which left those
// cubes to the CPU. These kernels instead walk the column in GLOBAL memory,
// so the ceiling is gone (measured on 539 x 1024^2: the sigma combine 10.6 s
// on the CPU against 0.93 s here, and the median is exact).
//
// The median is a per-pixel RADIX SELECT on the sortable bit pattern of the
// float, the same trick the registration uses (float_bits/bits_float): four
// 8-bit passes, each one a 256-bin histogram over the column, so a NaN-aware
// median costs no sort.
// ======================================================================

// The sortable mapping: a float's bits reordered so that the UNSIGNED
// comparison of two mapped values IS the float comparison. Negatives flip
// every bit, positives only the sign. It mirrors the registration's
// real_bits/bits_real (the float case); that one is templated for the double
// build, this one is float-only because the cube is float32.
static uint float_bits(float x) {
    const uint u = as_uint(x);
    return (u & 0x80000000u) ? ~u : (u | 0x80000000u);
}

static float bits_float(uint u) {
    return as_float((u & 0x80000000u) ? (u & 0x7fffffffu) : ~u);
}

// The rank-th smallest FINITE value of this pixel's column (the mask and NaN
// are skipped, exactly as nanmedian_axis0 skips them), by radix select. With
// `dev` set it selects |v - centre| instead, which is what the MAD needs.
static float select_rank(__global const float *cube,
                         __global const uchar *mask,
                         const int hw, const int p, const int n,
                         int rank, const int dev, const float centre) {
    uint prefix = 0;
    for (int pass = 0; pass < 4; ++pass) {
        uint hist[256];
        for (int i = 0; i < 256; ++i) hist[i] = 0;
        const int shift = 24 - 8 * pass;
        for (int k = 0; k < n; ++k) {
            if (mask != 0 && mask[(long)k * hw + p] == 0) continue;
            float x = cube[(long)k * hw + p];
            if (!(x == x)) continue;
            if (dev) x = fabs(x - centre);
            const uint u = float_bits(x);
            if (pass > 0 && (u >> (shift + 8)) != prefix) continue;
            hist[(u >> shift) & 0xFF]++;
        }
        int cum = 0, d = 0;
        for (d = 0; d < 256; ++d) {
            if (cum + (int)hist[d] > rank) break;
            cum += (int)hist[d];
        }
        // the rank is relative to the values still in play: the ones the next
        // pass will look at start AFTER this digit's bin, so the digit's
        // cumulative count comes off it (the same step _select_device does)
        rank -= cum;
        prefix = (prefix << 8) | (uint)d;
    }
    return bits_float(prefix);
}

// The median of the column: the mean of the two central order statistics for
// an even count, which is what outliers.nanmedian_axis0 returns.
static float column_median(__global const float *cube,
                           __global const uchar *mask,
                           const int hw, const int p, const int n,
                           const int count) {
    const int lo = (count - 1) / 2, hi = count / 2;
    const float a = select_rank(cube, mask, hw, p, n, lo, 0, 0.0f);
    const float b = (hi == lo) ? a
                               : select_rank(cube, mask, hw, p, n, hi, 0, 0.0f);
    return (count % 2 == 0) ? 0.5f * (a + b) : a;
}

// sum (0) | mean (1): a streaming reduction, one pass, no frame ceiling.
__kernel void combine_stream(
    __global const float *cube, __global const uchar *mask,
    __global float *out, const int n, const int hw, const int method) {
    const int p = get_global_id(0);
    if (p >= hw) return;
    float s = 0.0f;
    int c = 0;
    for (int k = 0; k < n; ++k) {
        if (mask != 0 && mask[(long)k * hw + p] == 0) continue;
        const float x = cube[(long)k * hw + p];
        if (x == x) { s += x; c += 1; }
    }
    if (c == 0) { out[p] = NAN; return; }
    out[p] = (method == 1) ? s / (float)c : s;
}

// median: the per-pixel radix select, no frame ceiling.
__kernel void combine_median(
    __global const float *cube, __global const uchar *mask,
    __global float *out, const int n, const int hw) {
    const int p = get_global_id(0);
    if (p >= hw) return;
    int count = 0;
    for (int k = 0; k < n; ++k) {
        if (mask != 0 && mask[(long)k * hw + p] == 0) continue;
        const float x = cube[(long)k * hw + p];
        if (x == x) count += 1;
    }
    out[p] = (count == 0) ? NAN
                          : column_median(cube, mask, hw, p, n, count);
}

// sigma (the clipped mean) and weighted (the inverse-variance mean) share the
// clip: the MEDIAN centre, the MAD scale, `iterations` passes, the keep
// CUMULATIVE (a pixel rejected in one pass stays out) and the centre moving to
// the mean of the survivors each time. It is the same walk as
// track_stack._sigma_clip_keep, step for step, with the medians as radix
// selects. The MAD is over the FINITE values and not the survivors, which is
// what the CPU does (its data still holds every finite frame); `keep`
// (n * hw bytes) carries the cumulative veto.
__kernel void combine_clip(
    __global const float *cube, __global const uchar *mask,
    __global uchar *keep, __global const float *weights,
    __global float *out, const int n, const int hw,
    const float sigma, const int iterations, const int weighted) {
    const int p = get_global_id(0);
    if (p >= hw) return;
    int fcount = 0;
    for (int k = 0; k < n; ++k) {
        const float x = cube[(long)k * hw + p];
        const uchar v = ((mask == 0 || mask[(long)k * hw + p]) && (x == x))
                        ? (uchar)1 : (uchar)0;
        keep[(long)k * hw + p] = v;
        fcount += v;
    }
    if (fcount == 0) { out[p] = NAN; return; }
    float centre = column_median(cube, mask, hw, p, n, fcount);
    const int mlo = (fcount - 1) / 2, mhi = fcount / 2;
    for (int it = 0; it < iterations; ++it) {
        const float da = select_rank(cube, mask, hw, p, n, mlo, 1, centre);
        const float db = (mhi == mlo) ? da
                                      : select_rank(cube, mask, hw, p, n, mhi,
                                                    1, centre);
        float mad = 1.4826f * ((fcount % 2 == 0) ? 0.5f * (da + db) : da);
        if (!(mad > 0.0f)) mad = INFINITY;
        float s = 0.0f;
        int c = 0;
        for (int k = 0; k < n; ++k) {
            if (keep[(long)k * hw + p] == 0) continue;
            const float x = cube[(long)k * hw + p];
            if (fabs(x - centre) <= sigma * mad) { s += x; c += 1; }
            else keep[(long)k * hw + p] = 0;
        }
        if (c > 0) centre = s / (float)c;
    }
    // the average of the survivors: the plain mean when there are no weights
    // (w = 1), the inverse-variance mean when there are
    float num = 0.0f, den = 0.0f;
    for (int k = 0; k < n; ++k) {
        if (keep[(long)k * hw + p] == 0) continue;
        const float w = (weights != 0) ? weights[k] : 1.0f;
        num += cube[(long)k * hw + p] * w;
        den += w;
    }
    out[p] = (den > 0.0f) ? num / den : NAN;
}
"""

_state = {"checked": False, "ok": False, "cl": None, "ctx": None,
          "queue": None, "program": None, "name": "", "mem": 0}


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
                      name=ctx.devices[0].name.strip(),
                      mem=int(ctx.devices[0].global_mem_size))
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
            # (enqueue_fill_buffer is a MODULE function in pyopencl, not a
            # method of the queue: calling it on the queue is an
            # AttributeError that a frame covering the box never triggers)
            cl.enqueue_fill_buffer(queue, stack, np.float32(0.0),
                                   k * out_h * out_w * 4, out_h * out_w * 4)
            cl.enqueue_fill_buffer(queue, masks, np.uint8(0),
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
    # ANY number of frames: a cube taller than the private arrays goes to the
    # SCALABLE combine, so the ceiling that used to send the base stack to the
    # CPU is gone (ADR-091 note, 2026-10-15).
    if not available():
        return None
    out_h = box[3] - box[1]
    out_w = box[2] - box[0]
    # A card that cannot hold the cube, its masks and (for the clip) the keep
    # buffer is a normal "cannot serve this call": better to know it BEFORE
    # uploading hundreds of frames.
    keep = _METHODS.get(method, M_SIGMA) in (M_SIGMA, M_WEIGHTED)
    if not _device_has_room(len(frame_list), out_h, out_w, keep=keep):
        return None
    try:
        got = _warp_stack(frame_list, offsets, box, shape, loader, preloaded)
        if got is None:
            return None
        stack, masks = got
        n = len(frame_list)
        out = _combine_device(stack, masks, n, out_h, out_w, method, sigma,
                              iterations, weights)
        return _read(out, (out_h, out_w)).astype(np.float32)
    except Exception as err:                                   # noqa: BLE001
        logger.warning("OpenCL stack failed, falling back to CPU: %s", err)
        return None


# ---------------------------------------------------------------- combine

def _device_has_room(n, h, w, keep=False):
    # @args: n/h/w - the cube's shape, keep - True when the combine also needs
    #        the cumulative `keep` buffer (the clip methods)
    # @return: True when the estimated device footprint fits the card
    # The fused path holds the cube, its masks, the output and (for the clip)
    # the keep buffer on the device AT ONCE. A card that cannot hold them is a
    # normal "cannot serve this call": the caller keeps numpy and the run
    # finishes. The estimate leaves a fifth of the card for the driver and the
    # warp's own source buffers.
    mem = _state.get("mem") or 0
    if mem <= 0:
        return True
    hw = int(h) * int(w)
    need = int(n) * hw * 4          # the warped cube
    need += int(n) * hw             # its masks (uchar)
    if keep:
        need += int(n) * hw         # the clip's cumulative veto
    need += hw * 4 * 2              # the output and a scratch
    return need <= 0.8 * mem


def _combine_scalable(stack, masks, n, h, w, method, sigma, iterations,
                      weights):
    # @args: stack - the (n, h, w) cube ON the device, masks - the (n, h, w)
    #        validity ON the device (or None), the rest - the method's knobs
    # @return: the combined (h, w) ON the device
    # The combine for a cube TALLER than the private arrays: the column is
    # walked in GLOBAL memory, so there is no frame ceiling. The median is a
    # per-pixel radix select; sigma and weighted carry a cumulative `keep`
    # (n * hw bytes) for the clip.
    cl = _state["cl"]
    queue = _state["queue"]
    hw = h * w
    out = _empty((h, w))
    wbuf = _f32_buffer(np.asarray(weights, dtype=np.float32)) \
        if weights is not None else None
    m = _METHODS.get(method, M_SIGMA)
    if m in (M_SUM, M_MEAN):
        kern = _kernel("combine_stream")
        kern(queue, (hw,), None, stack, masks, out,
             np.int32(n), np.int32(hw), np.int32(m))
    elif m == M_MEDIAN:
        kern = _kernel("combine_median")
        kern(queue, (hw,), None, stack, masks, out, np.int32(n), np.int32(hw))
    else:
        keep = cl.Buffer(_state["ctx"], cl.mem_flags.READ_WRITE, n * hw)
        kern = _kernel("combine_clip")
        kern(queue, (hw,), None, stack, masks, keep, wbuf, out,
             np.int32(n), np.int32(hw), np.float32(sigma),
             np.int32(iterations), np.int32(1 if m == M_WEIGHTED else 0))
    return out


def _combine_device(stack, masks, n, h, w, method, sigma, iterations,
                    weights):
    # @args: stack - the (n, h, w) cube ON the device, masks - the (n, h, w)
    #        validity ON the device (or None), the rest - the method's knobs
    # @return: the combined (h, w) ON the device
    # TWO kernels, one job, and the frame count alone decides. The private
    # one keeps the column in registers (no global buffer, one pass over the
    # cube) and is the fast path for the SHORT cubes the stacking groups and
    # the star stack make; the SCALABLE one removes the frame ceiling for the
    # base stack, which is the WHOLE sequence (measured: a real visit at 539).
    if n > _PRIVATE_COMBINE_MAX:
        return _combine_scalable(stack, masks, n, h, w, method, sigma,
                                 iterations, weights)
    cl = _state["cl"]
    queue = _state["queue"]
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
    data = np.ascontiguousarray(stack, dtype=np.float32)
    if data.ndim != 3:
        return None
    n, h, w = data.shape
    keep = _METHODS.get(method, M_SIGMA) in (M_SIGMA, M_WEIGHTED)
    if not _device_has_room(n, h, w, keep=keep):
        return None
    try:
        cl = _state["cl"]
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


# ======================================================================
# The registration (ADR-091): the per-frame estimate's two halves, the SOURCE
# IMAGE (block medians + a smooth background) and the STARS (decimation, the
# noise's global MAD, the local maxima). A line-by-line mirror of
# core/register.source_image and core/register.detect_stars.
#
# WHY A SECOND PROGRAM. These kernels want `double` for exact parity with the
# CPU, and the warp/combine program must keep building on a device without it
# (an Intel iGPU). So the registration is its own program, built lazily, with
# REAL = double when the device compiles it and float otherwise; if even the
# float build fails, frame_stars answers None and the CPU does the estimate.
#
# WHY A RADIX SELECT AND NOT A SORT. The estimate's cost on the CPU is TWO
# medians: measured on a 2048^2 frame, 56 ms the per-block one and 45 ms the
# global MAD over ~2.1M values, of a 170 ms estimate. OpenCL has no median, so
# the median is a radix SELECT on the sortable bit pattern of the float (8
# passes of 8 bits for a double, 4 for a float), each pass one histogram over
# the array. Measured on the author's RTX 3090: the per-block median 4.4 ms
# against the CPU's 56 (x12.6) and the two global medians 3.6 ms against 45
# (x12.5), both EXACT.
# ======================================================================

KERNELS_REG = r"""
// No FMA contraction. The compiler is allowed to fuse `a*b + c` into one
// fma(), which skips the rounding of the product and moves the background by
// ~1 ulp (measured on a frame that does not divide by the block: 1.1e-13 on a
// 1000 ADU sky). The CPU does NOT fuse, so to be BIT-EXACT with it the
// contraction has to go: the arithmetic is a handful of operations per pixel
// and the FMA buys nothing here.
#pragma OPENCL FP_CONTRACT OFF

// The real type. FLOAT is the default (fast, and the only one an Intel iGPU
// can build); DOUBLE is the exact-parity build, reached through _FORCE_WIDE.
#ifdef USE_DOUBLE
typedef double real;
typedef ulong ubits;
#define REAL_ONE 1.0
#else
typedef float real;
typedef uint ubits;
#define REAL_ONE 1.0f
#endif

// The sortable mapping: a float's bits reordered so that the UNSIGNED
// comparison of two mapped values is the float comparison. Negatives flip
// every bit, positives only the sign. It is what lets a radix pass work on
// floats at all.
static ubits real_bits(real x) {
#ifdef USE_DOUBLE
    const ulong u = as_ulong(x);
    return (u & 0x8000000000000000ul) ? ~u : (u | 0x8000000000000000ul);
#else
    const uint u = as_uint(x);
    return (u & 0x80000000u) ? ~u : (u | 0x80000000u);
#endif
}

static real bits_real(ubits u) {
#ifdef USE_DOUBLE
    return as_double((u & 0x8000000000000000ul)
                     ? (u & 0x7FFFFFFFFFFFFFFFul) : ~u);
#else
    return as_float((u & 0x80000000u) ? (u & 0x7fffffffu) : ~u);
#endif
}

// --------------------------- the block median ---------------------------
// One work-item per block, the block in LOCAL memory. The work-group is ONE
// on purpose: __local is per work-group, so a bigger group would share one
// buffer and race. An exact Hoare quickselect; the CPU's np.median averages
// the two central order statistics for an even count, which is what the two
// kth() calls reproduce.
#define BLK_MAX 1089

static real median3(real a, real b, real c) {
    return fmax(fmin(a, b), fmin(fmax(a, b), c));
}

static real kth(__local real *v, int n, int k) {
    int lo = 0, hi = n - 1;
    while (lo < hi) {
        const real pivot = median3(v[lo], v[(lo + hi) >> 1], v[hi]);
        int i = lo, j = hi;
        while (i <= j) {
            while (v[i] < pivot) ++i;
            while (v[j] > pivot) --j;
            if (i <= j) { const real t = v[i]; v[i] = v[j]; v[j] = t; ++i; --j; }
        }
        if (k <= j) hi = j;
        else if (k >= i) lo = i;
        else break;
    }
    return v[k];
}

__kernel void block_median(
    __global const real *img, const int w,
    __global const int *ys, __global const int *xs,
    const int bw, __global real *grid)
{
    const int g = get_global_id(0);
    const int j = g / bw;
    const int i = g % bw;
    int y0 = ys[j], y1 = ys[j + 1];
    int x0 = xs[i], x1 = xs[i + 1];
    if (y1 <= y0) y1 = y0 + 1;          // a one-pixel block at the edge
    if (x1 <= x0) x1 = x0 + 1;
    __local real buf[BLK_MAX];
    int m = 0;
    for (int y = y0; y < y1; ++y)
        for (int x = x0; x < x1; ++x)
            buf[m++] = img[y * w + x];
    const real a = kth(buf, m, (m - 1) >> 1);
    const real b = kth(buf, m, m >> 1);
    grid[g] = (real)0.5 * (a + b);
}

// ---------------------------- the background ----------------------------
// The grid is re-expanded along x with np.interp's own formula
// (slope*(x-xp)+fp), clamped outside the centres and exact on one.
__kernel void bg_expand_x(
    __global const real *grid, __global const real *cx,
    const int bw, const int w, __global real *tmp)
{
    const int x = get_global_id(0);
    const int j = get_global_id(1);
    if (bw <= 1) { tmp[j * w + x] = grid[j * bw]; return; }
    const real px = (real)x;
    if (px <= cx[0]) { tmp[j * w + x] = grid[j * bw]; return; }
    if (px >= cx[bw - 1]) { tmp[j * w + x] = grid[j * bw + bw - 1]; return; }
    int lo = 0, hi = bw - 1;
    while (hi - lo > 1) {
        const int mid = (lo + hi) >> 1;
        if (cx[mid] <= px) lo = mid; else hi = mid;
    }
    const real slope = (grid[j * bw + lo + 1] - grid[j * bw + lo])
                     / (cx[lo + 1] - cx[lo]);
    tmp[j * w + x] = slope * (px - cx[lo]) + grid[j * bw + lo];
}

// The source image: the y blend (jy/wy come from the host, the same
// searchsorted the CPU does) and the clip that makes it the image the stars
// are found on.
__kernel void source_image(
    __global const real *arr, __global const real *tmp,
    __global const int *jy, __global const real *wy,
    const int w, __global real *src)
{
    const int x = get_global_id(0);
    const int y = get_global_id(1);
    const int j = jy[y];
    const real bg = tmp[j * w + x] * (REAL_ONE - wy[y])
                  + tmp[(j + 1) * w + x] * wy[y];
    const real v = arr[y * w + x] - bg;
    src[y * w + x] = v > (real)0.0 ? v : (real)0.0;
}

// --------------------------- star detection -----------------------------
// The factor-f box average the CPU does with reshape().mean(). numpy sums
// ROW BY ROW and then adds the row sums ((a+b)+(c+d) for a 2x2 block,
// measured), which is a different rounding from a plain left-to-right sum;
// the peaks are compared with a threshold, so it is worth matching.
__kernel void decimate(
    __global const real *src, const int w, const int f,
    const int sw, __global real *small)
{
    const int x = get_global_id(0);
    const int y = get_global_id(1);
    real total = (real)0.0;
    for (int dy = 0; dy < f; ++dy) {
        real row = (real)0.0;
        for (int dx = 0; dx < f; ++dx)
            row += src[(y * f + dy) * w + (x * f + dx)];
        total += row;
    }
    small[y * sw + x] = total / (real)(f * f);
}

// The pixel-to-pixel differences of the decimated image, laid out exactly as
// np.concatenate([np.diff(small, axis=1).ravel(), np.diff(small, axis=0)...]).
__kernel void diffs(
    __global const real *small, const int sh, const int sw,
    __global real *out)
{
    const int j = get_global_id(0);
    const int i = get_global_id(1);
    const int nh = sh * (sw - 1);
    if (j < sw - 1)
        out[i * (sw - 1) + j] = small[i * sw + j + 1] - small[i * sw + j];
    if (i < sh - 1)
        out[nh + i * sw + j] = small[(i + 1) * sw + j] - small[i * sw + j];
}

// One radix pass: the 8-bit digit at `shift` of every FINITE value whose high
// bits already equal `prefix` (skipped on the first pass, where the shift
// would be the full width and is undefined). The histogram lives in local
// memory and is merged once per work-group, which keeps the global atomics
// down to 256 per group.
__kernel void radix_hist(
    __global const real *v, const uint n, const ulong prefix,
    const int shift, const int use_prefix, __global uint *hist)
{
    const uint gid = get_global_id(0);
    const uint gsz = get_global_size(0);
    __local uint lh[256];
    for (int i = get_local_id(0); i < 256; i += get_local_size(0)) lh[i] = 0;
    barrier(CLK_LOCAL_MEM_FENCE);
    for (uint i = gid; i < n; i += gsz) {
        const real x = v[i];
        if (!(x == x)) continue;                    // nanmedian skips NaN
        const ubits u = real_bits(x);
        if (use_prefix && ((ulong)(u >> (shift + 8)) != prefix)) continue;
        atomic_inc(&lh[(int)((u >> shift) & (ubits)0xFF)]);
    }
    barrier(CLK_LOCAL_MEM_FENCE);
    for (int i = get_local_id(0); i < 256; i += get_local_size(0))
        atomic_add(&hist[i], lh[i]);
}

// |v - centre|: the deviation the second median reduces.
__kernel void abs_dev(
    __global const real *v, __global real *out, const uint n,
    const real centre)
{
    const uint i = get_global_id(0);
    if (i >= n) return;
    out[i] = fabs(v[i] - centre);
}

// The local maxima above k*noise, outside the margin, compacted with an
// atomic counter (the list is short: the CPU keeps the brightest 60). The
// border is dropped BEFORE the comparison, which is the same as the CPU's
// drop after it and frees the comparison from reproducing np.roll's wrap.
__kernel void local_maxima(
    __global const real *small, const int sh, const int sw,
    const int margin, const real thresh, const real sat, const int has_sat,
    const int cap, __global int *out_y, __global int *out_x,
    __global real *out_p, __global int *counter)
{
    const int j = get_global_id(0);
    const int i = get_global_id(1);
    if (i >= sh || j >= sw) return;
    if (i < margin || i >= sh - margin
            || j < margin || j >= sw - margin) return;
    const real v = small[i * sw + j];
    for (int dy = -1; dy <= 1; ++dy) {
        for (int dx = -1; dx <= 1; ++dx) {
            if (dy == 0 && dx == 0) continue;
            int yy = i + dy, xx = j + dx;
            if (yy < 0) yy = 0; else if (yy >= sh) yy = sh - 1;
            if (xx < 0) xx = 0; else if (xx >= sw) xx = sw - 1;
            if (v < small[yy * sw + xx]) return;
        }
    }
    if (!(v > thresh)) return;
    if (has_sat && !(v < sat)) return;
    const int idx = atomic_inc(counter);
    if (idx >= cap) return;
    out_y[idx] = i;
    out_x[idx] = j;
    out_p[idx] = v;
}
"""

# The registration's own state: the lazily built program, whether it is the
# double one, and the radix shifts that go with it.
_reg = {"checked": False, "ok": False, "program": None, "wide": True,
        "dtype": np.float64, "shifts": (56, 48, 40, 32, 24, 16, 8, 0)}

# How many work-items the radix passes launch (independent of the array).
_RADIX_G = 1 << 18

# WHICH build: float is the DEFAULT. It is 2.6x faster than the double one on
# a consumer card (measured on an RTX 3090: 12.5 ms against 32.5 ms for the
# whole estimate), because consumer GPUs do fp64 at 1/64 of fp32 AND the
# double doubles every transfer. The star list comes out the same: measured,
# the positions agree to 1.35e-7 px and the peaks to 2.4e-4 ADU.
#
# This hook forces the DOUBLE build (the exact-parity one, one line away) so
# it is not dead code: a test exercises it. None keeps the default.
_FORCE_WIDE = None


def _reg_build():
    # @return: True when the registration program is built
    # Built ONCE and cached. FLOAT first (the fast one, and the only one an
    # Intel iGPU can build); the DOUBLE build is the exact-parity path and is
    # reached through _FORCE_WIDE (see above).
    if _reg["checked"]:
        return _reg["ok"]
    _reg["checked"] = True
    if not available():
        return False
    cl = _state["cl"]
    order = (False, True) if _FORCE_WIDE is None else (_FORCE_WIDE,)
    for wide in order:
        try:
            program = cl.Program(_state["ctx"], KERNELS_REG).build(
                options="-D USE_DOUBLE" if wide else "")
        except Exception as err:                               # noqa: BLE001
            logger.info("no %s registration kernels: %s",
                        "double" if wide else "float", err)
            continue
        _reg.update(program=program, wide=wide, ok=True,
                    dtype=np.float64 if wide else np.float32,
                    shifts=((56, 48, 40, 32, 24, 16, 8, 0) if wide
                            else (24, 16, 8, 0)))
        return True
    return False


def _reg_kernel(name):
    # @args: name - a kernel in KERNELS_REG
    # @return: the compiled kernel, or None when there is no backend
    if not _reg_build():
        return None
    return _state["cl"].Kernel(_reg["program"], name)


def _int_buffer(array):
    # @return: a read-only int32 device buffer with a copy of it
    cl = _state["cl"]
    return cl.Buffer(_state["ctx"],
                     cl.mem_flags.READ_ONLY | cl.mem_flags.COPY_HOST_PTR,
                     hostbuf=np.ascontiguousarray(array, dtype=np.int32))


def _int_empty(n):
    # @return: a write-only int32 device buffer of n ints
    cl = _state["cl"]
    return cl.Buffer(_state["ctx"], cl.mem_flags.READ_WRITE, int(n) * 4)


def _real_buffer(array):
    # @return: a read-only buffer of the backend's real type
    cl = _state["cl"]
    return cl.Buffer(_state["ctx"],
                     cl.mem_flags.READ_ONLY | cl.mem_flags.COPY_HOST_PTR,
                     hostbuf=np.ascontiguousarray(array, dtype=_reg["dtype"]))


def _real_empty(n):
    # @return: a write-only buffer of the backend's real type
    cl = _state["cl"]
    size = int(n) * np.dtype(_reg["dtype"]).itemsize
    return cl.Buffer(_state["ctx"], cl.mem_flags.READ_WRITE, size)


def _real_read(buf, n):
    # @return: n values of the backend's real type, as a numpy array
    out = np.empty(int(n), dtype=_reg["dtype"])
    _state["cl"].enqueue_copy(_state["queue"], out, buf)
    _state["queue"].finish()
    return out


def _grid_edges(h, w, block):
    # The block edges, exactly as register._block_grid builds them (the
    # TRUNCATED linspace, so a frame that does not divide by the block gets the
    # same ragged grid on both sides).
    bh = max(1, h // block)
    bw = max(1, w // block)
    ys = np.linspace(0, h, bh + 1).astype(np.int64).astype(np.int32)
    xs = np.linspace(0, w, bw + 1).astype(np.int64).astype(np.int32)
    return bh, bw, ys, xs


def _y_weights(h, ys, bh):
    # The y row indexes and weights of register._background, on the host: they
    # are h values, not h*w, and doing them here keeps the kernel to the
    # arithmetic (and the searchsorted EXACT).
    cy = (ys[:-1] + ys[1:] - 1) / 2.0
    py = np.arange(h, dtype=np.float64)
    jy = np.clip(np.searchsorted(cy, py) - 1, 0, bh - 2).astype(np.int32)
    dy = cy[jy + 1] - cy[jy]
    wy = np.where(dy > 0, (py - cy[jy]) / np.where(dy > 0, dy, 1.0), 0.0)
    return jy, wy


def _block_median_device(arrbuf, w, ys, xs, bh, bw):
    # @args: arrbuf - the frame ON the device (uploaded ONCE by the caller),
    #        w - its width, the rest - the grid
    # @return: the (bh*bw) grid of block medians ON the device
    queue = _state["queue"]
    n = bh * bw
    grid = _real_empty(n)
    kern = _reg_kernel("block_median")
    kern(queue, (n,), (1,), arrbuf, np.int32(w),
         _int_buffer(ys), _int_buffer(xs), np.int32(bw), grid)
    return grid


def _background_device(grid, cx, bh, bw, w):
    # @return: the (bh, w) grid expanded along x, ON the device
    queue = _state["queue"]
    tmp = _real_empty(bh * w)
    kern = _reg_kernel("bg_expand_x")
    kern(queue, (w, bh), None, grid, _real_buffer(cx), np.int32(bw),
         np.int32(w), tmp)
    return tmp


def _source_image_device(arrbuf, tmp, jy, wy, h, w):
    # @args: arrbuf - the frame ON the device (the SAME upload the block
    #        median used: a 2048^2 frame is 32 MB as a double, and uploading
    #        it twice cost 5.5 ms of the estimate), the rest - the blend
    # @return: the (h, w) source image ON the device
    queue = _state["queue"]
    src = _real_empty(h * w)
    kern = _reg_kernel("source_image")
    kern(queue, (w, h), None, arrbuf, tmp, _int_buffer(jy),
         _real_buffer(wy), np.int32(w), src)
    return src


def _decimate_device(src, h, w, f):
    # @return: (small, sh, sw) with the factor-f box average ON the device
    queue = _state["queue"]
    sh, sw = h // f, w // f
    small = _real_empty(sh * sw)
    kern = _reg_kernel("decimate")
    kern(queue, (sw, sh), None, src, np.int32(w), np.int32(f),
         np.int32(sw), small)
    return small, sh, sw


def _diffs_device(small, sh, sw):
    # @return: (diffs ON the device, its length)
    queue = _state["queue"]
    n = sh * (sw - 1) + (sh - 1) * sw
    out = _real_empty(n)
    kern = _reg_kernel("diffs")
    kern(queue, (sw, sh), None, small, np.int32(sh), np.int32(sw), out)
    return out, n


def _hist_pass(vbuf, n, prefix, shift, use_prefix):
    # @return: the 256-bin histogram of one radix pass, on the host
    cl = _state["cl"]
    queue = _state["queue"]
    zeros = np.zeros(256, np.uint32)
    b_h = cl.Buffer(_state["ctx"],
                    cl.mem_flags.READ_WRITE | cl.mem_flags.COPY_HOST_PTR,
                    hostbuf=zeros)
    kern = _reg_kernel("radix_hist")
    kern(queue, (_RADIX_G,), (256,), vbuf, np.uint32(n), np.uint64(prefix),
         np.int32(shift), np.int32(use_prefix), b_h)
    out = np.empty(256, np.uint32)
    cl.enqueue_copy(queue, out, b_h)
    queue.finish()
    return out


def _bits_to_real(u):
    # @args: u - a sortable bit pattern (the inverse of real_bits)
    # @return: the float it came from
    if _reg["wide"]:
        bits = (u & 0x7FFFFFFFFFFFFFFF) if (u >> 63) \
            else (~u & 0xFFFFFFFFFFFFFFFF)
        return float(np.uint64(bits).view(np.float64))
    bits = (u & 0x7FFFFFFF) if (u >> 31) else (~u & 0xFFFFFFFF)
    return float(np.uint32(bits).view(np.float32))


def _select_device(vbuf, n, rank, h0, shifts):
    # @args: vbuf - the array ON the device, n - its length, rank - the order
    #        statistic to find (0-based, over the FINITE values), h0 - the
    #        first pass's histogram (shared by the two ranks of a median),
    #        shifts - the radix shifts
    # @return: the rank-th smallest finite value, EXACTLY
    # One histogram per pass: each pins 8 more bits of the answer. There is no
    # final "read the value" pass because after the last shift the prefix IS
    # the full bit pattern.
    hist = h0
    prefix = 0
    for idx, shift in enumerate(shifts):
        cum = np.cumsum(hist)
        d = min(int(np.searchsorted(cum, rank, side="right")), 255)
        prefix = (prefix << 8) | d
        rank -= int(cum[d - 1]) if d > 0 else 0
        if idx + 1 < len(shifts):
            hist = _hist_pass(vbuf, n, prefix, shifts[idx + 1], 1)
    return _bits_to_real(prefix)


def _median_device(vbuf, n):
    # @return: np.nanmedian of the array ON the device, EXACTLY (the mean of
    #          the two central order statistics for an even count of FINITE
    #          values, which is what nanmedian does)
    shifts = _reg["shifts"]
    h0 = _hist_pass(vbuf, n, 0, shifts[0], 0)
    m = int(h0.sum())                      # the finite count, for free
    if m == 0:
        return float("nan")
    a = _select_device(vbuf, n, (m - 1) // 2, h0, shifts)
    b = _select_device(vbuf, n, m // 2, h0, shifts)
    return 0.5 * (a + b)


def _noise_device(diffs, n):
    # @return: register's noise, outliers.scaled_mad(diffs)/sqrt(2)
    m = _median_device(diffs, n)
    dev = _real_empty(n)
    kern = _reg_kernel("abs_dev")
    kern(_state["queue"], (n,), None, diffs, dev, np.uint32(n),
         _reg["dtype"](m))
    mad = _median_device(dev, n)
    return 1.4826 * mad / math.sqrt(2.0)


def _local_maxima_device(small, sh, sw, margin, thresh, sat):
    # @return: (ys, xs, peaks) of the candidates, in ROW-MAJOR order (the CPU
    #          gets that order from np.where, and the later argsort depends on
    #          it for a tie)
    cl = _state["cl"]
    queue = _state["queue"]
    cap = sh * sw
    out_y, out_x, out_p = _int_empty(cap), _int_empty(cap), _real_empty(cap)
    counter = cl.Buffer(_state["ctx"],
                        cl.mem_flags.READ_WRITE | cl.mem_flags.COPY_HOST_PTR,
                        hostbuf=np.zeros(1, np.int32))
    has_sat = 1 if (sat is not None and sat > 0) else 0
    kern = _reg_kernel("local_maxima")
    kern(queue, (sw, sh), None, small, np.int32(sh), np.int32(sw),
         np.int32(margin), _reg["dtype"](thresh),
         _reg["dtype"](sat if has_sat else 0.0), np.int32(has_sat),
         np.int32(cap), out_y, out_x, out_p, counter)
    count = np.empty(1, np.int32)
    cl.enqueue_copy(queue, count, counter)
    queue.finish()
    k = min(int(count[0]), cap)
    if k == 0:
        return (np.empty(0, np.int64), np.empty(0, np.int64),
                np.empty(0, np.float64))
    ys = np.empty(k, np.int32)
    xs = np.empty(k, np.int32)
    cl.enqueue_copy(queue, ys, out_y)
    cl.enqueue_copy(queue, xs, out_x)
    peaks = _real_read(out_p, k)
    queue.finish()
    # the atomic compaction scrambles the order; np.where did not, and the
    # argsort below needs the same input to break a tie the same way
    order = np.lexsort((xs, ys))
    return (ys[order].astype(np.int64), xs[order].astype(np.int64),
            peaks[order].astype(np.float64))


def _detect_stars_device(src, src_buf, h, w, sat, nmax=60, k=8.0,
                         margin=8, factor=2):
    # @return: (N, 3) [x, y, peak] like register.detect_stars, or an empty
    #          array. The candidate SEEDS are found on the device; the refine
    #          is register._refine on the source image, which is a handful of
    #          stars and 0.1 ms on the CPU.
    from . import register
    f = int(max(1, factor))
    if f > 1 and min(h, w) >= 4 * f:
        small, sh, sw = _decimate_device(src_buf, h, w, f)
    else:
        f = 1
        small, sh, sw = src_buf, h, w
    diffs, nd = _diffs_device(small, sh, sw)
    noise = _noise_device(diffs, nd)
    empty = np.empty((0, 3), dtype=np.float64)
    if not math.isfinite(noise) or noise <= 0.0:
        return empty
    m = max(2, int(round(margin / f)))
    if 2 * m >= min(h, w):
        return empty
    ys, xs, peaks = _local_maxima_device(small, sh, sw, m, k * noise, sat)
    if xs.size == 0:
        return empty
    order = np.argsort(peaks)[::-1][:nmax]
    xs = (xs[order] + 0.5) * f
    ys = (ys[order] + 0.5) * f
    peaks = peaks[order]
    fx, fy = register._refine(src, xs, ys)
    return np.column_stack([fx, fy, peaks])


def frame_stars(data, sat=None):
    # @args: data - a frame's pixels (ADU, any shape), sat - the saturation
    #        ceiling (None keeps every peak, as the CPU path does)
    # @return: (source image (numpy), stars (N, 3) numpy) or None when the
    #          backend cannot serve the call (the caller then uses the CPU)
    # ONE upload per frame for BOTH halves: the frame goes up once, the source
    # image and the star seeds are built on the device, and the source image
    # and the refined stars come back. The two medians are the reason this is
    # worth doing at all (see the module's header).
    if not available() or not _reg_build():
        return None
    try:
        return _frame_stars(data, sat)
    except Exception as err:                                   # noqa: BLE001
        logger.warning("OpenCL registration failed, falling back to CPU: %s",
                       err)
        return None


def _frame_stars(data, sat):
    from . import register
    arr = np.asarray(data, dtype=_reg["dtype"])
    h, w = arr.shape
    block = register._BG_BLOCK
    bh, bw, ys, xs = _grid_edges(h, w, block)
    if bh < 2:
        return None                       # the y blend needs two grid rows
    # a block that does not fit the kernel's local buffer is a frame this
    # backend does not serve (the CPU keeps it)
    if int((ys[1:] - ys[:-1]).max()) * int((xs[1:] - xs[:-1]).max()) > 1089:
        return None
    arrbuf = _real_buffer(arr)              # ONE upload, shared below
    grid = _block_median_device(arrbuf, w, ys, xs, bh, bw)
    cx = (xs[:-1] + xs[1:] - 1) / 2.0
    tmp = _background_device(grid, cx, bh, bw, w)
    jy, wy = _y_weights(h, ys, bh)
    src_buf = _source_image_device(arrbuf, tmp, jy, wy, h, w)
    src = _real_read(src_buf, h * w).reshape(h, w)
    stars = _detect_stars_device(src, src_buf, h, w, sat)
    return src, stars
