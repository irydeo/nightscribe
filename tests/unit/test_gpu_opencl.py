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
that the registration says so instead of pretending: `frame_stars` is not
ported and answers None, so the CPU keeps that half.
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


def test_the_registration_is_not_ported_and_says_so():
    # The block median and the star search are a different beast, and a
    # half-port that quietly moved a centroid would be worse than no port. The
    # contract is the same as any other unserved call: None, and the CPU does
    # the work.
    assert gpu_opencl.frame_stars(np.zeros((64, 64), dtype=np.float32)) is None
