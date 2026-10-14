############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the optional GPU backend (ADR-089)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The GPU backend must be a faster ROAD to the same answer, never a different
answer.

CuPy cannot be a hard dependency, so the whole file SKIPS on a machine without
it (which is the normal case, and the CI). When it is there, the two things
that matter are pinned: the backend is OFF unless the observer asks for it, and
its warp and combine agree with the numpy path to within a float32 rounding
(they cannot be bit-identical: a GPU reduces in a different order, and the
measured worst case is under a third of an ADU on a sky of a thousand).
"""

import numpy as np
import pytest

from nightscribe.core import gpu
from nightscribe.core import track_stack as ts

pytestmark = pytest.mark.skipif(not gpu.available(),
                                reason="no GPU backend on this machine")


def test_the_backend_is_off_unless_it_is_asked_for():
    # The observer's explicit choice is one gate and the hardware is the
    # other; a GPU that is merely PRESENT must not change a result.
    assert gpu.enabled(None) is False
    assert gpu.enabled({"astrometry_gpu": 0}) is False
    assert gpu.enabled({"astrometry_gpu": 1}) is True


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
    on_gpu = gpu.combine(cube, method, mask=mask, weights=weights)
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
    gpu_s = gpu.warp_batch([frame], [(0.0, 0.0)], box, (size, size))
    assert gpu_s is not None
    gpu_stack, gpu_mask = gpu_s
    assert np.array_equal(cpu_m, gpu_mask)
    assert np.nanmax(np.abs(cpu_s - gpu_stack)) < 0.5


def test_the_engine_takes_the_gpu_path_when_it_is_on(tmp_path):
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
        fits.PrimaryHDU(img.astype(np.int16)).writeto(str(path), overwrite=True)
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
    on_gpu, _ = ts.stack_group(frames, (0, len(frames)), q, "sigma", box,
                               (size, size), cfg={"astrometry_gpu": 1})
    assert np.nanmax(np.abs(cpu - on_gpu)) < 0.5
