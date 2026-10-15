############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Benchmark: OpenCL against CuPy, same machine
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""How much does an OpenCL backend lose against the CuPy one?

The app already has an optional CUDA backend (core/gpu.py, ADR-089). The
question here is whether a PORTABLE backend (OpenCL runs on NVIDIA, AMD and
Intel) is close enough to ship it, or whether it is a second-class citizen.

This is a bench: not imported by the app, not shipped. It implements the two
memory-bound kernels the CUDA path covers (the per-frame WARP and the
COMBINE) in plain OpenCL C, runs them against CuPy on the SAME machine, the
SAME data and the same shapes, and prints the ratio.

Why those two: a warp and a combine read and write frame-sized arrays, so
what decides is MEMORY BANDWIDTH, and both backends share the machine's. The
registration's kernels (a block median, a source image, a star search) are
more interesting to port, but they are not the 90 % of the time.

Run it with the app's own venv:  .venv/bin/python tools/bench/bench_opencl.py
"""

import argparse
import time

import numpy as np

# ------------------------------------------------------------- the kernels

KERNELS = r"""
// The per-frame WARP: the same affine `cupyx.scipy.ndimage.affine_transform`
// applies (output[i, j] samples input[A @ (i, j) + b]), bilinear, zero
// outside. One work-item per output pixel, which is what a memory-bound
// resample wants: no shared memory, no synchronisation, four source reads
// and one write.
__kernel void warp_bilinear(
    __global const float *src, const int sh, const int sw,
    __global float *dst, const int dh, const int dw,
    const float a00, const float a01, const float a10, const float a11,
    const float bx, const float by)
{
    const int j = get_global_id(0);
    const int i = get_global_id(1);
    if (i >= dh || j >= dw) return;
    const float sx = a00 * (float)j + a01 * (float)i + bx;
    const float sy = a10 * (float)j + a11 * (float)i + by;
    if (sx < 0.0f || sy < 0.0f
            || sx > (float)(sw - 1) || sy > (float)(sh - 1)) {
        dst[i * dw + j] = 0.0f;
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
    dst[i * dw + j] = (1.0f - fy) * ((1.0f - fx) * v00 + fx * v01)
                    + fy * ((1.0f - fx) * v10 + fx * v11);
}

// The MEAN over the frames, NaN skipped, one work-item per output pixel. It
// reads the whole cube once: that is the whole cost, which is what makes it
// a bandwidth test rather than a compute one.
__kernel void combine_mean(
    __global const float *cube, __global float *out,
    const int n, const int hw)
{
    const int p = get_global_id(0);
    if (p >= hw) return;
    float s = 0.0f;
    int c = 0;
    for (int k = 0; k < n; ++k) {
        const float v = cube[(long)k * hw + p];
        if (v == v) { s += v; c += 1; }
    }
    out[p] = c > 0 ? s / (float)c : NAN;
}

// The MEDIAN over the frames, per pixel: the work-item copies its own column
// of n values into private memory and selects. n is small (a few dozen
// frames), so an insertion sort is the honest comparison against a device
// sort: both are O(n log n)-ish per pixel and both are dominated by the same
// read of the cube.
__kernel void combine_median(
    __global const float *cube, __global float *out,
    const int n, const int hw)
{
    const int p = get_global_id(0);
    if (p >= hw) return;
    float v[128];
    int m = 0;
    for (int k = 0; k < n && m < 128; ++k) {
        const float x = cube[(long)k * hw + p];
        if (x == x) v[m++] = x;
    }
    if (m == 0) { out[p] = NAN; return; }
    for (int a = 1; a < m; ++a) {
        const float key = v[a];
        int b = a - 1;
        while (b >= 0 && v[b] > key) { v[b + 1] = v[b]; --b; }
        v[b + 1] = key;
    }
    out[p] = (m % 2) ? v[m / 2] : 0.5f * (v[m / 2 - 1] + v[m / 2]);
}

// The SCALABLE median: the same per-pixel selection, but the column is walked
// in GLOBAL memory (a radix select on the sortable bit pattern of the float),
// so it holds ANY number of frames. It is what the app uses above 96 frames,
// because the base stack of a real visit is the WHOLE sequence (hundreds); the
// private one above is the fast path below that. Run the bench with
// --frames 300 to see the difference.
static uint _fb(float x) {
    const uint u = as_uint(x);
    return (u & 0x80000000u) ? ~u : (u | 0x80000000u);
}
static float _bf(uint u) {
    return as_float((u & 0x80000000u) ? (u & 0x7fffffffu) : ~u);
}
static float _select_rank(__global const float *cube, const int hw,
                          const int p, const int n, int rank) {
    uint prefix = 0;
    for (int pass = 0; pass < 4; ++pass) {
        uint hist[256];
        for (int i = 0; i < 256; ++i) hist[i] = 0;
        const int shift = 24 - 8 * pass;
        for (int k = 0; k < n; ++k) {
            const float x = cube[(long)k * hw + p];
            if (!(x == x)) continue;
            const uint u = _fb(x);
            if (pass > 0 && (u >> (shift + 8)) != prefix) continue;
            hist[(u >> shift) & 0xFF]++;
        }
        int cum = 0, d = 0;
        for (d = 0; d < 256; ++d) {
            if (cum + (int)hist[d] > rank) break;
            cum += (int)hist[d];
        }
        rank -= cum;
        prefix = (prefix << 8) | (uint)d;
    }
    return _bf(prefix);
}
__kernel void combine_median_scalable(
    __global const float *cube, __global float *out,
    const int n, const int hw)
{
    const int p = get_global_id(0);
    if (p >= hw) return;
    int count = 0;
    for (int k = 0; k < n; ++k) {
        const float x = cube[(long)k * hw + p];
        if (x == x) count += 1;
    }
    if (count == 0) { out[p] = NAN; return; }
    const int lo = (count - 1) / 2, hi = count / 2;
    const float a = _select_rank(cube, hw, p, n, lo);
    const float b = (hi == lo) ? a : _select_rank(cube, hw, p, n, hi);
    out[p] = (count % 2 == 0) ? 0.5f * (a + b) : a;
}
"""


# ------------------------------------------------------------- the harness

def _time(fn, repeats=3):
    # @args: fn - a callable that BLOCKS until its work is done, repeats -
    #        how many timed runs
    # @return: the MEDIAN seconds of the timed runs, after one warm-up
    # The median and not the mean: a driver hiccup on one run must not decide
    # the comparison, and the warm-up keeps the first-launch cost out of it.
    # Every caller must synchronise: a GPU launch is ASYNCHRONOUS, and timing
    # one without a sync measures the launch, not the work (the first version
    # of this bench read a 1 GB cube in "0.0 ms" because of exactly that).
    fn()                                   # warm-up (compile, allocate)
    out = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        out.append(time.perf_counter() - t0)
    return float(np.median(out))


def _cupy_ctx():
    # @return: (cp, cnd) the CuPy module and its ndimage, or (None, None)
    try:
        import cupy as cp
        from cupyx.scipy import ndimage as cnd
        cp.cuda.Device(0).use()
        return cp, cnd
    except Exception as err:                                   # noqa: BLE001
        print(f"CuPy no disponible: {err}")
        return None, None


def _cl_ctx():
    # @return: (cl, ctx, queue, program) or four Nones
    try:
        import pyopencl as cl
    except Exception as err:                                   # noqa: BLE001
        print(f"pyopencl no disponible: {err}")
        return None, None, None, None
    ctx = None
    for plat in cl.get_platforms():
        for dev in plat.get_devices():
            if any(name in plat.name
                   for name in ("NVIDIA", "AMD", "Intel")):
                ctx = cl.Context([dev])
                break
        if ctx is not None:
            break
    if ctx is None:
        print("ningun dispositivo OpenCL")
        return None, None, None, None
    queue = cl.CommandQueue(ctx)
    program = cl.Program(ctx, KERNELS).build()
    return cl, ctx, queue, program


def _bench_warp(cp, cnd, cl, ctx, queue, program, n, h, w):
    # The warp: the same affine on every frame, at the app's size (a
    # per-frame warp of a 2048^2 frame onto the cutout).
    rng = np.random.default_rng(3)
    frames = rng.normal(1000.0, 50.0, (n, h, w)).astype(np.float32)
    A = np.array([[0.9998, 0.017], [-0.017, 0.9998]], dtype=np.float64)
    offset = np.array([3.0, -2.0], dtype=np.float64)
    dh, dw = h, w

    print(f"\n=== WARP (bilineal, {n} x {h}^2 -> {h}^2) ===")
    cupy_t = None
    if cp is not None:
        g = [cp.asarray(f) for f in frames]
        Ag, og = cp.asarray(A), cp.asarray(offset)

        def cupy_run():
            for f in g:
                cnd.affine_transform(f, Ag, offset=og, output_shape=(dh, dw),
                                     order=1, mode="constant", cval=0.0)
            cp.cuda.Stream.null.synchronize()
        cupy_t = _time(cupy_run)
        print(f"  CuPy    : {1000 * cupy_t:8.1f} ms")
    if cl is not None:
        mf = cl.mem_flags
        # EVERY frame gets its own buffer: warping the same 16 MB buffer 60
        # times would measure the L2 cache and not the memory bus.
        srcs = [cl.Buffer(ctx, mf.READ_ONLY | mf.COPY_HOST_PTR, hostbuf=f)
                for f in frames]
        dst = cl.Buffer(ctx, mf.WRITE_ONLY, frames[0].nbytes)
        f32 = np.float32
        kern = cl.Kernel(program, "warp_bilinear")

        def cl_run():
            for src in srcs:
                kern(queue, (dw, dh), None,
                     src, np.int32(h), np.int32(w),
                     dst, np.int32(dh), np.int32(dw),
                     f32(A[0, 0]), f32(A[0, 1]), f32(A[1, 0]), f32(A[1, 1]),
                     f32(offset[0]), f32(offset[1]))
            queue.finish()
        cl_t = _time(cl_run)
        extra = f"   ratio OpenCL/CuPy {cl_t / cupy_t:.2f}x" if cupy_t else ""
        print(f"  OpenCL  : {1000 * cl_t:8.1f} ms{extra}")
    return cupy_t


def _bench_combine(cp, cl, ctx, queue, program, n, h, w):
    # The combine: the mean and the median over the cube, per pixel.
    rng = np.random.default_rng(7)
    cube = (rng.normal(1000.0, 30.0, (n, h, w)) + 50.0).astype(np.float32)
    hw = h * w

    print(f"\n=== COMBINE ({n} x {h}^2) ===")
    cupy = {}
    if cp is not None:
        g = cp.asarray(cube)
        sync = cp.cuda.Stream.null.synchronize

        def cupy_mean():
            cp.nanmean(g, axis=0)
            sync()

        def cupy_median():
            cp.nanmedian(g, axis=0)
            sync()
        cupy["mean"] = _time(cupy_mean)
        cupy["median"] = _time(cupy_median, repeats=2)
        print(f"  CuPy    : mean {1000 * cupy['mean']:8.1f} ms   "
              f"median {1000 * cupy['median']:8.1f} ms")
    if cl is not None:
        mf = cl.mem_flags
        src = cl.Buffer(ctx, mf.READ_ONLY | mf.COPY_HOST_PTR, hostbuf=cube)
        dst = cl.Buffer(ctx, mf.WRITE_ONLY, 4 * hw)
        for name, kname in (("mean", "combine_mean"),
                            ("median", "combine_median"),
                            ("median_scalable", "combine_median_scalable")):
            kern = cl.Kernel(program, kname)

            def run():
                kern(queue, (hw,), None, src, dst, np.int32(n), np.int32(hw))
                queue.finish()
            t = _time(run, repeats=2)
            ref = cupy.get("median") if name.startswith("median") \
                else cupy.get(name)
            extra = f"   ratio OpenCL/CuPy {t / ref:.2f}x" if ref else ""
            print(f"  OpenCL  : {name} {1000 * t:8.1f} ms{extra}")


def _make_frames(folder, n, size):
    # The synthetic sequence the speed plan's bench builds, so the end-to-end
    # number below is the STACKING and not a kernel in a vacuum.
    from astropy.io import fits
    from nightscribe.core import track_stack
    rng = np.random.default_rng(1)
    base = rng.normal(1000.0, 4.0, (size, size))
    yy, xx = np.mgrid[0:size, 0:size]
    for _ in range(80):
        x, y = rng.uniform(8, size - 8), rng.uniform(8, size - 8)
        base += rng.uniform(1500.0, 4000.0) * np.exp(
            -((xx - x) ** 2 + (yy - y) ** 2) / (2 * 1.5 ** 2))
    frames = []
    for i in range(n):
        img = base.copy()
        x, y = size * 0.35 + 1.0 * i, size * 0.5
        img += 2500.0 * np.exp(-((xx - x) ** 2 + (yy - y) ** 2)
                               / (2 * 1.5 ** 2))
        path = folder / f"f{i:04d}.fits"
        fits.PrimaryHDU(img.astype(np.int16)).writeto(str(path),
                                                      overwrite=True)
        fr = track_stack.Frame(path=str(path),
                               header={"NAXIS1": size, "NAXIS2": size})
        fr.transform = {"angle": 0.0, "dx": 0.0, "dy": 0.0, "quality": 100.0,
                        "rms_px": 0.0}
        fr.object_xy = (x, y)
        fr.t_mid_jd = 2460000.5 + i / 1440.0
        frames.append(fr)
    return frames


def _bench_run(n, size):
    # The app's own entry point, the three backends. It is the number that
    # decides what to ship: the warp and the combine FUSED, as the engine
    # calls them.
    import tempfile
    from pathlib import Path
    from nightscribe.core import track_stack as ts
    folder = Path(tempfile.mkdtemp(prefix="nsopencl_"))
    frames = _make_frames(folder, n, size)
    q = frames[0].object_xy
    final_box = ts.box_around(q, 0, (size, size))
    print(f"\n=== STACK_GROUP (sigma, {n} x {size}^2, whole frame) ===")
    for label, cfg in (("CPU", {"astrometry_gpu": 0}),
                       ("CUDA", {"astrometry_gpu": 1,
                                 "astrometry_gpu_backend": "cuda"}),
                       ("OpenCL", {"astrometry_gpu": 1,
                                   "astrometry_gpu_backend": "opencl"})):
        def run(c=cfg):
            ts.stack_group(frames, (0, len(frames)), q, "sigma", final_box,
                           (size, size), cfg=c)
        try:
            t = _time(run, repeats=1)
        except Exception as err:                               # noqa: BLE001
            print(f"  {label:8s}: {err}")
            continue
        print(f"  {label:8s}: {1000 * t:8.1f} ms")


def _bench_registration(size):
    # The per-frame estimate (the source image and the stars) through the
    # APP's own entry points: the stage ADR-091 added to the OpenCL backend.
    # On the CPU its cost is TWO medians (the per-block one and the global MAD
    # over ~2.1M values), which is why the backend carries a radix select.
    from nightscribe.core import gpu_cuda, gpu_opencl, register
    rng = np.random.default_rng(5)
    img = rng.normal(1000.0, 4.0, (size, size))
    yy, xx = np.mgrid[0:size, 0:size]
    for _ in range(400):
        x, y = rng.uniform(8, size - 8), rng.uniform(8, size - 8)
        img += rng.uniform(1500, 4000) * np.exp(
            -((xx - x) ** 2 + (yy - y) ** 2) / (2 * 1.5 ** 2))
    img = img.astype(np.float32)
    print(f"\n=== REGISTRATION (source image + stars, {size}^2) ===")
    cpu = _time(lambda: register.detect_stars(register.source_image(img)),
                repeats=2)
    print(f"  CPU    : {1000 * cpu:8.1f} ms")
    if gpu_opencl.available():
        ocl = _time(lambda: gpu_opencl.frame_stars(img), repeats=2)
        print(f"  OpenCL : {1000 * ocl:8.1f} ms   ({cpu / ocl:.1f}x)")
    if gpu_cuda.available():
        cuda = _time(lambda: gpu_cuda.frame_stars(img), repeats=2)
        print(f"  CUDA   : {1000 * cuda:8.1f} ms   ({cpu / cuda:.1f}x)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=60)
    ap.add_argument("--size", type=int, default=2048)
    args = ap.parse_args()
    n, h, w = args.frames, args.size, args.size
    print(f"OpenCL contra CuPy: {n} tomas de {h}x{w}")

    cl, ctx, queue, program = _cl_ctx()
    if ctx is not None:
        dev = ctx.devices[0]
        print(f"  OpenCL : {dev.name} ({dev.max_compute_units} CUs)")
    cp, cnd = _cupy_ctx()
    if cp is not None:
        name = cp.cuda.runtime.getDeviceProperties(0)["name"].decode()
        print(f"  CuPy   : {name}")

    _bench_warp(cp, cnd, cl, ctx, queue, program, n, h, w)
    _bench_combine(cp, cl, ctx, queue, program, n, h, w)
    _bench_run(n, h)
    _bench_registration(h)


if __name__ == "__main__":
    main()
