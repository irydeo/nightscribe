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
that matter are pinned: the backend needs BOTH the observer's switch (on by
default since the 2026-10-15 revision of ADR-089) and the hardware, and its
warp and combine agree with the numpy path to within a float32 rounding (they
cannot be bit-identical: a GPU reduces in a different order, and the measured
worst case is under a third of an ADU on a sky of a thousand).
"""

import numpy as np
import pytest

from nightscribe.core import gpu
from nightscribe.core import track_stack as ts

pytestmark = pytest.mark.skipif(not gpu.available(),
                                reason="no GPU backend on this machine")


def _needs_registration():
    # @return: None. SKIPS the test when this device cannot serve the
    #          registration: the backend checks its kernels against the CPU
    #          at build time and REFUSES when they disagree (pocl
    #          miscompiles the block median's quickselect, measured
    #          2026-10-15). There is no parity to pin on a device that
    #          cannot produce the answer at all.
    from nightscribe.core import gpu_opencl
    if not gpu_opencl._reg_build():
        pytest.skip("this OpenCL device refuses the registration kernels")


def test_the_backend_is_off_unless_it_is_asked_for():
    # The observer's explicit choice is one gate and the hardware is the
    # other; a GPU that is merely PRESENT must not change a result. The
    # switch now DEFAULTS to on (ADR-089 rev), so the gate is the config
    # value, not the absence of one.
    assert gpu.enabled(None) is False
    assert gpu.enabled({"astrometry_gpu": 0}) is False
    assert gpu.enabled({"astrometry_gpu": 1}) is True


def test_probe_answers_about_a_backend_without_moving_the_dispatch():
    # The Settings dialog asks "which card does THIS backend see?" so the
    # switch is never a blind guess. Asking must NOT change the backend that
    # serves the calls: the answer is a fact about the machine.
    before = gpu._state["requested"]
    name = gpu.probe("opencl")
    assert isinstance(name, str)
    assert gpu.probe("opencl") == name            # stable
    assert gpu.probe("nonsense") == gpu.probe("auto")   # anything else: auto
    assert gpu._state["requested"] == before      # the dispatch did not move


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


def _field(size, seed=1, n=40):
    rng = np.random.default_rng(seed)
    img = rng.normal(1000.0, 3.0, (size, size))
    yy, xx = np.mgrid[0:size, 0:size]
    for _ in range(n):
        x, y = rng.uniform(20, size - 20), rng.uniform(20, size - 20)
        img += rng.uniform(1500.0, 6000.0) * np.exp(
            -((xx - x) ** 2 + (yy - y) ** 2) / (2 * 1.6 ** 2))
    return img


def test_the_registration_kernels_match_the_numpy_path():
    # The source image and the stars are the WHOLE cost of an estimate. Both
    # are deterministic in float64, so the source image matches to the bit and
    # the stars to a fraction of a pixel; anything larger would move the
    # transform and the stack.
    _needs_registration()
    from nightscribe.core import register
    size = 256
    img = _field(size, seed=4)
    src_cpu = register.source_image(img)
    stars_cpu = register.detect_stars(src_cpu)
    got = gpu.frame_stars(img)
    assert got is not None
    src_gpu, stars_gpu = got
    assert np.abs(src_gpu - src_cpu).max() < 1e-6
    assert len(stars_gpu) == len(stars_cpu)
    for x, y, _peak in stars_cpu:
        d = np.hypot(stars_gpu[:, 0] - x, stars_gpu[:, 1] - y).min()
        assert d < 0.1


def test_the_source_image_matches_on_a_ragged_frame():
    # The real camera writes 2008^2, which does NOT divide by the block (32):
    # 2008 % 32 = 24, so the CPU walks RAGGED blocks of 32 and 33 and the
    # device has to reproduce them, or the background (and the stars) move.
    _needs_registration()
    from nightscribe.core import register
    size = 200              # 200 % 32 = 8, a ragged frame
    img = _field(size, seed=6)
    src_cpu = register.source_image(img)
    got = gpu.frame_stars(img)
    assert got is not None
    src_gpu, _stars = got
    assert np.abs(src_gpu - src_cpu).max() < 1e-6


def test_register_sequence_matches_with_the_gpu_on(tmp_path):
    # The point of the whole exercise: the same sequence on the same grid must
    # come out with the SAME transform frame by frame, trusted or not. The
    # estimate is deterministic once the source image and the stars are equal,
    # so any drift here would be a wiring mistake, not a tolerance question.
    from astropy.io import fits
    from astropy.wcs import WCS
    size = 200
    base = _field(size, seed=7)
    paths = []
    for i in range(8):
        img = np.roll(base, (i % 3 - 1, i % 2 - 1), axis=(0, 1))
        p = tmp_path / f"f{i}.fits"
        fits.PrimaryHDU(img.astype(np.int16)).writeto(str(p), overwrite=True)
        paths.append(str(p))

    def _run(cfg):
        frames = ts.load_sequence(paths)
        w = WCS(naxis=2)
        w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
        w.wcs.crval = [10.0, 20.0]
        w.wcs.crpix = [size / 2.0 + 0.5, size / 2.0 + 0.5]
        w.wcs.cd = [[-2.0 / 3600, 0.0], [0.0, 2.0 / 3600]]
        w.pixel_shape = (size, size)
        frames[0].wcs = w
        ts.register_sequence(frames, cfg=cfg)
        return frames

    cpu = _run({"astrometry_gpu": 0})
    on_gpu = _run({"astrometry_gpu": 1})
    assert [f.failed_register for f in cpu] == \
        [f.failed_register for f in on_gpu]
    for a, b in zip(cpu, on_gpu):
        assert a.transform["dx"] == pytest.approx(b.transform["dx"], abs=0.05)
        assert a.transform["dy"] == pytest.approx(b.transform["dy"], abs=0.05)
        assert a.transform.get("angle_deg", 0.0) == pytest.approx(
            b.transform.get("angle_deg", 0.0), abs=0.05)
