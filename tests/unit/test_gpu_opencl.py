############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the OpenCL GPU backend
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The OpenCL backend must be the SAME road to the same answer as the CUDA
one, and the same as numpy.

pyopencl cannot be a hard dependency, so the whole file SKIPS on a machine
without it (the normal case, and the CI). When it is there, what is pinned is
the parity (the warp and the combine agree with the numpy path to within a
float32 rounding), that the facade can be pointed at it and reaches it, and
that the registration (`frame_stars`) finds the CPU's own stars. The SCALABLE
combine is pinned too: a cube taller than the private kernel's arrays is served
by the radix-select kernels (the base stack of a real visit is hundreds of
frames), and the device-memory guard answers None instead of an OOM.
"""

import numpy as np
import pytest

from nightscribe.core import gpu
from nightscribe.core import gpu_opencl
from nightscribe.core import track_stack as ts

pytestmark = pytest.mark.skipif(not gpu_opencl.available(),
                                reason="no OpenCL backend on this machine")


@pytest.fixture
def forced_opencl():
    # Point the facade at OpenCL for one test and put the choice back: the
    # module keeps it, and a leaked "opencl" would decide the other tests.
    saved = gpu._state["requested"]
    gpu.configure({"astrometry_gpu_backend": "opencl"})
    try:
        yield
    finally:
        gpu._state["requested"] = saved


def test_the_backend_reports_itself():
    assert gpu_opencl.NAME == "opencl"
    assert gpu_opencl.device_name()


def test_the_facade_can_be_pointed_at_it(forced_opencl):
    # The dispatch is what the engine goes through: asking for OpenCL must
    # actually reach the OpenCL module.
    assert gpu.backend_name() == "opencl"
    assert gpu.enabled({"astrometry_gpu": 1,
                        "astrometry_gpu_backend": "opencl"}) is True


@pytest.mark.parametrize("method", ["sum", "mean", "median", "sigma",
                                    "weighted"])
def test_combine_matches_the_numpy_path(method):
    # A cube with a couple of bad frames in it, so the clip has something to
    # reject and the comparison is not just an average.
    rng = np.random.default_rng(5)
    cube = rng.normal(1000.0, 4.0, (24, 96, 96)).astype(np.float32)
    cube[3] += 500.0
    cube[17] += 400.0
    mask = np.ones_like(cube, dtype=bool)
    mask[0, :4, :4] = False            # a footprint corner, as a stack has
    weights = np.linspace(0.5, 2.0, cube.shape[0])
    if method != "weighted":
        weights = None
    cpu = ts.combine(cube, method, mask=mask, weights=weights,
                     cfg={"astrometry_gpu": 0})
    on_gpu = gpu_opencl.combine(cube, method, mask=mask, weights=weights)
    assert on_gpu is not None
    assert np.nanmax(np.abs(cpu - on_gpu)) < 0.5      # ADU, float32 rounding


def test_the_warp_matches_the_numpy_path(tmp_path):
    # One frame, a small rotation and shift, read through the same loader the
    # engine uses, so the geometry (the (row, col) flip included) is the one
    # that matters and not a re-derivation.
    from astropy.io import fits
    rng = np.random.default_rng(9)
    size = 128
    img = rng.normal(1000.0, 4.0, (size, size))
    path = tmp_path / "f.fits"
    fits.PrimaryHDU(img.astype(np.int16)).writeto(str(path), overwrite=True)
    frame = ts.Frame(path=str(path), header={"NAXIS1": size, "NAXIS2": size})
    frame.transform = {"angle": 0.01, "dx": 1.3, "dy": -0.7, "quality": 100.0,
                       "rms_px": 0.0}
    box = (0, 0, size, size)
    cpu_s, cpu_m = ts._warp_batch([frame], [(0.0, 0.0)], box, (size, size),
                                  cfg={"astrometry_gpu": 0})
    got = gpu_opencl.warp_batch([frame], [(0.0, 0.0)], box, (size, size))
    assert got is not None
    stack, mask = got
    assert np.array_equal(cpu_m, mask)
    assert np.nanmax(np.abs(cpu_s - stack)) < 0.5


def test_the_engine_takes_the_opencl_path_when_it_is_on(tmp_path, forced_opencl):
    # The integration point: with the setting on, stack_group must agree with
    # the CPU result. It is the same assertion as above but through the public
    # entry point, which is where a wiring mistake would hide.
    from astropy.io import fits
    rng = np.random.default_rng(2)
    size = 128
    base = rng.normal(1000.0, 4.0, (size, size))
    frames = []
    for i in range(8):
        img = np.roll(base, (i % 3 - 1, i % 2 - 1), axis=(0, 1))
        path = tmp_path / f"f{i}.fits"
        fits.PrimaryHDU(img.astype(np.int16)).writeto(str(path),
                                                      overwrite=True)
        fr = ts.Frame(path=str(path),
                      header={"NAXIS1": size, "NAXIS2": size})
        fr.transform = {"angle": 0.0, "dx": float(i % 3 - 1),
                        "dy": float(i % 2 - 1), "quality": 100.0, "rms_px": 0.0}
        fr.object_xy = (size / 2.0, size / 2.0)
        frames.append(fr)
    q = (size / 2.0, size / 2.0)
    box = ts.box_around(q, 0, (size, size))
    cpu, _ = ts.stack_group(frames, (0, len(frames)), q, "sigma", box,
                            (size, size), cfg={"astrometry_gpu": 0})
    on_gpu, _ = ts.stack_group(
        frames, (0, len(frames)), q, "sigma", box, (size, size),
        cfg={"astrometry_gpu": 1, "astrometry_gpu_backend": "opencl"})
    assert np.nanmax(np.abs(cpu - on_gpu)) < 0.5


def test_the_engine_takes_the_opencl_path_for_a_tall_cube(tmp_path,
                                                          forced_opencl):
    # More frames than the private combine holds: the fused path now serves it
    # with the SCALABLE combine, so the whole stack (base stack of a real
    # visit) stays on the device instead of falling to the CPU. The result
    # must be the CPU's.
    from astropy.io import fits
    rng = np.random.default_rng(3)
    size = 384
    n = gpu_opencl._PRIVATE_COMBINE_MAX + 24
    base = rng.normal(1000.0, 4.0, (size, size))
    frames = []
    for i in range(n):
        img = np.roll(base, (i % 3 - 1, i % 2 - 1), axis=(0, 1))
        path = tmp_path / f"h{i}.fits"
        fits.PrimaryHDU(img.astype(np.int16)).writeto(str(path),
                                                      overwrite=True)
        fr = ts.Frame(path=str(path),
                      header={"NAXIS1": size, "NAXIS2": size})
        fr.transform = {"angle": 0.0, "dx": float(i % 3 - 1),
                        "dy": float(i % 2 - 1), "quality": 100.0, "rms_px": 0.0}
        fr.object_xy = (size / 2.0, size / 2.0)
        frames.append(fr)
    q = (size / 2.0, size / 2.0)
    box = ts.box_around(q, 300, (size, size))
    cpu, _ = ts.stack_group(frames, (0, n), q, "sigma", box, (size, size),
                            cfg={"astrometry_gpu": 0})
    on_gpu, _ = ts.stack_group(
        frames, (0, n), q, "sigma", box, (size, size),
        cfg={"astrometry_gpu": 1, "astrometry_gpu_backend": "opencl"})
    assert np.nanmax(np.abs(cpu - on_gpu)) < 0.5


def _field(size, seed=1, nstars=200):
    # A synthetic star field, the same shape the register bench uses.
    rng = np.random.default_rng(seed)
    img = rng.normal(1000.0, 4.0, (size, size))
    yy, xx = np.mgrid[0:size, 0:size]
    for _ in range(nstars):
        x, y = rng.uniform(8, size - 8), rng.uniform(8, size - 8)
        img += rng.uniform(1200, 5000) * np.exp(
            -((xx - x) ** 2 + (yy - y) ** 2) / (2 * 1.6 ** 2))
    return img.astype(np.float32)


def test_the_registration_stars_match_the_cpu():
    # The whole point of porting the estimate: the stars it finds must be the
    # CPU's. The default build is float, so the positions are compared with a
    # tight tolerance (measured 1.3e-7 px) and not bit for bit.
    from nightscribe.core import register
    img = _field(512, seed=11)
    ref_src = register.source_image(img)
    ref = register.detect_stars(ref_src)
    src, got = gpu_opencl.frame_stars(img)
    assert got.shape == ref.shape
    assert np.max(np.abs(ref[:, :2] - got[:, :2])) < 1e-3     # px
    assert np.max(np.abs(ref[:, 2] - got[:, 2])) < 1e-2       # ADU
    # and the source image itself, which the estimate also keeps
    assert np.max(np.abs(ref_src - src)) < 1e-2               # ADU


def test_the_registration_stars_are_identical_in_the_double_build():
    # The exact-parity build (one line away, see gpu_opencl._FORCE_WIDE): bit
    # for bit with the CPU, which is what the ADR-089 path promises.
    from nightscribe.core import register
    saved = gpu_opencl._FORCE_WIDE
    gpu_opencl._FORCE_WIDE = True
    gpu_opencl._reg.update(checked=False, ok=False, program=None)
    try:
        img = _field(512, seed=12)
        ref_src = register.source_image(img)
        ref = register.detect_stars(ref_src)
        src, got = gpu_opencl.frame_stars(img)
        assert np.array_equal(ref_src, src)
        assert np.array_equal(ref, got)
    finally:
        gpu_opencl._FORCE_WIDE = saved
        gpu_opencl._reg.update(checked=False, ok=False, program=None)


def test_the_registration_feeds_the_estimate():
    # The integration point: the transform the estimate reads from the OpenCL
    # source image and stars must be the CPU's.
    from nightscribe.core import register
    a = _field(256, seed=13)
    b = np.roll(a, (2, -3), axis=(0, 1))
    src_a, stars_a = gpu_opencl.frame_stars(a)
    src_b, stars_b = gpu_opencl.frame_stars(b)
    got = register.estimate_transform(a, b, ref_src=src_a, src_src=src_b,
                                      ref_stars=stars_a, src_stars=stars_b)
    want = register.estimate_transform(a, b)
    assert got["n"] == want["n"] and got["n"] >= register.MIN_MATCH
    assert abs(got["dx"] - want["dx"]) < 0.05
    assert abs(got["dy"] - want["dy"]) < 0.05
    assert abs(got["angle"] - want["angle"]) < 1e-4


@pytest.mark.parametrize("method", ["sum", "mean", "median", "sigma",
                                    "weighted"])
def test_the_scalable_combine_matches_the_numpy_path(method):
    # More frames than the private combine holds: the base stack of a real
    # visit is hundreds, so the SCALABLE combine walks the column in global
    # memory and the ceiling is gone. The parity is the same contract as the
    # short-cube test above; the median is EXACT (the radix select picks the
    # same order statistic the CPU's sort does).
    rng = np.random.default_rng(7)
    n = gpu_opencl._PRIVATE_COMBINE_MAX + 8
    cube = rng.normal(1000.0, 4.0, (n, 64, 64)).astype(np.float32)
    cube[3] += 500.0
    cube[17] -= 400.0
    mask = np.ones_like(cube, dtype=bool)
    mask[0, :4, :4] = False
    weights = np.linspace(0.5, 2.0, n).astype(np.float32)
    if method != "weighted":
        weights = None
    cpu = ts.combine(cube, method, mask=mask, weights=weights,
                     cfg={"astrometry_gpu": 0})
    on_gpu = gpu_opencl.combine(cube, method, mask=mask, weights=weights)
    assert on_gpu is not None
    assert np.nanmax(np.abs(cpu - on_gpu)) < 0.5


def test_the_device_guard_declines_a_cube_that_does_not_fit(monkeypatch):
    # A card that cannot hold the cube, its masks and (for the clip) the keep
    # buffer is a normal "cannot serve this call", and the check runs BEFORE
    # the upload. A fake small card makes it refuse without allocating.
    monkeypatch.setitem(gpu_opencl._state, "mem", 128 * 1024 ** 2)
    assert gpu_opencl._device_has_room(1000, 2048, 2048, keep=True) is False
    assert gpu_opencl._device_has_room(4, 64, 64, keep=True) is True
