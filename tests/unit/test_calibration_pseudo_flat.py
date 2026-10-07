############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the pseudo-flat (P5)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""A flat made from the frames themselves, for the observer who has none.

The physics is the dither: the train's dust and the sensor's vignetting are
FIXED on the frame and survive a low percentile over the frames, while the
stars MOVE and do not. These tests build a known vignetting and two known
dust spots, add stars that dither, and check that the flat recovers the
pattern, that a static sequence is FLAGGED (its flat still carries the
stars), that a real flat from the library always wins, and that applying the
pseudo-flat flattens the frame it was built for.
"""

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nightscribe.core import calibration as cal     # noqa: E402

SIZE = 96
SKY = 1000.0


def _write(path, data, **cards):
    from astropy.io import fits
    hdu = fits.PrimaryHDU(np.asarray(data, dtype=np.float32))
    for key, value in cards.items():
        hdu.header[key] = value
    hdu.writeto(str(path), overwrite=True)
    return str(path)


def _vignetting(size=SIZE, strength=0.35):
    # @return: the true multiplicative pattern: a radial falloff (the
    #          vignetting) plus two dust shadows, all of it FIXED on the
    #          frame
    yy, xx = np.mgrid[0:size, 0:size]
    r2 = (((xx - size / 2.0) ** 2 + (yy - size / 2.0) ** 2)
          / ((size / 2.0) ** 2))
    vig = 1.0 - strength * r2
    for (cx, cy, rad, depth) in ((28.0, 30.0, 5.0, 0.25),
                                 (70.0, 66.0, 7.0, 0.18)):
        vig *= 1.0 - depth * np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2)
                                      / (2 * rad ** 2)))
    return vig


def _frames(tmp_path, n=10, dither_px=3.0, stars=True, seed=3):
    # @return: (paths, the true pattern). The stars walk `dither_px` per
    #          frame; with dither_px=0 they sit still, which is the case the
    #          percentile cannot clean.
    rng = np.random.default_rng(seed)
    vig = _vignetting()
    yy, xx = np.mgrid[0:SIZE, 0:SIZE]
    paths = []
    for i in range(n):
        frame = np.full((SIZE, SIZE), SKY)
        if stars:
            for k in range(4):
                sx = 20.0 + 18.0 * k + dither_px * i
                sy = 30.0 + 14.0 * k
                frame = frame + 2500.0 * np.exp(
                    -(((xx - sx) ** 2 + (yy - sy) ** 2) / (2 * 1.6 ** 2)))
        frame = frame * vig
        frame = frame + rng.normal(0.0, 4.0, (SIZE, SIZE))
        paths.append(_write(tmp_path / f"f{i:02d}.fits", frame,
                            EXPTIME=3.0, INSTRUME="TestCam", FILTER="R"))
    return paths, vig


def test_the_pseudo_flat_recovers_the_pattern(tmp_path):
    # The vignetting and the two dust shadows have to come back: the ratio
    # between the flat and the truth must be flat itself (a few per cent),
    # and the flat must be normalised to a median of one.
    paths, vig = _frames(tmp_path, dither_px=3.0)
    flat, info = cal.pseudo_flat(paths, window=21, passes=3)
    assert flat is not None, info.get("note")
    assert float(np.median(flat)) == pytest.approx(1.0, abs=0.02)
    # A flat's ABSOLUTE scale is arbitrary (calibrate divides by it); what
    # has to come back is its SHAPE, so both are normalised before the
    # comparison.
    inner = slice(20, SIZE - 20)
    got = flat[inner, inner] / float(np.median(flat[inner, inner]))
    want = vig[inner, inner] / float(np.median(vig[inner, inner]))
    assert float(np.median(np.abs(got / want - 1.0))) < 0.03
    assert info["n_frames"] == len(paths)
    assert info["residual_pct"] is not None


def test_a_static_sequence_gets_the_vignetting_model(tmp_path):
    # Without dithering the stars do not move, so the percentile keeps them
    # and the flat carries their bumps: a flat that carries the stars is
    # worse than no flat, because every star is divided by itself (measured
    # on the author's own 2025 FG18 visit: a comparison star sitting on a
    # bright star came out 1.08 mag off, and the whole zero point was scrap).
    # What IS still usable from those frames is the VIGNETTING, which is
    # smooth and fixed: a low-order surface fitted to the percentile where
    # there are no stars, said for what it is.
    os.makedirs(tmp_path / "still", exist_ok=True)
    os.makedirs(tmp_path / "moving", exist_ok=True)
    still, _ = _frames(tmp_path / "still", dither_px=0.0, seed=5)
    moving, _ = _frames(tmp_path / "moving", dither_px=3.0, seed=5)
    flat_still, info_still = cal.pseudo_flat(still, window=21)
    flat_moving, info_moving = cal.pseudo_flat(moving, window=21)
    assert flat_still is not None and flat_moving is not None
    assert info_still["residual_pct"] > info_moving["residual_pct"]
    # the dithered set gives the full flat; the static one the smooth model
    assert info_moving["kind"] == "pseudo_flat"
    assert info_moving["note"] == ""
    assert info_still["kind"] == "vignette_model"
    assert info_still["note"]                     # it says what it is
    assert info_still["mask_pct"] > 0.0           # the stars were found
    # the model recovers the VIGNETTING (the smooth part), not the dust: the
    # fitted surface follows the radial falloff
    inner = slice(20, SIZE - 20)
    got = flat_still[inner, inner] / float(np.median(flat_still[inner, inner]))
    yy, xx = np.mgrid[0:SIZE, 0:SIZE]
    r2 = (((xx - SIZE / 2.0) ** 2 + (yy - SIZE / 2.0) ** 2)
          / ((SIZE / 2.0) ** 2))
    radial = 1.0 - 0.35 * r2
    want = radial[inner, inner] / float(np.median(radial[inner, inner]))
    assert float(np.median(np.abs(got / want - 1.0))) < 0.03


def test_the_library_flat_always_wins(tmp_path):
    # A real flat measures the train's response; a pseudo-flat measures the
    # response times the sky's shape. The real one is used when it exists.
    from nightscribe.core import calibration
    dark = _write(tmp_path / "dark.fits", np.full((SIZE, SIZE), 900.0))
    real_flat = _write(tmp_path / "flat.fits", np.full((SIZE, SIZE), 1200.0))
    meta = {"kind": "flat", "camera": "TestCam", "gain": 2.0,
            "temp_c": -10.0, "exptime_s": 3.0, "filter": "R"}
    class _DB:
        def execute(self, *a, **k):
            raise AssertionError("no database in this test")
    # a recipe built by hand: with a flat, and without one
    from nightscribe.core.calibration import MasterRef, Recipe
    with_flat = Recipe(flat=MasterRef(id=1, kind="flat", path=real_flat))
    without = Recipe()
    fake_flat = np.full((SIZE, SIZE), 2.0, dtype=np.float32)
    _out, rep = cal.calibrate(np.full((SIZE, SIZE), 1000.0), with_flat,
                              pseudo_flat=fake_flat)
    assert rep.flat_path == real_flat
    _out2, rep2 = cal.calibrate(np.full((SIZE, SIZE), 1000.0), without,
                                pseudo_flat=fake_flat)
    assert rep2.flat_path == "pseudo-flat"
    assert rep2.flat_norm == pytest.approx(2.0)


def test_applying_the_pseudo_flat_flattens_the_frame(tmp_path):
    # End to end: a frame divided by its pseudo-flat must lose the radial
    # trend the vignetting put on it.
    paths, vig = _frames(tmp_path, dither_px=3.0)
    flat, info = cal.pseudo_flat(paths, window=21)
    assert flat is not None
    from nightscribe.core import calibration
    data, _h = calibration.read_image(paths[0])
    corrected = data / flat
    yy, xx = np.mgrid[0:SIZE, 0:SIZE]
    r2 = (((xx - SIZE / 2.0) ** 2 + (yy - SIZE / 2.0) ** 2)
          / ((SIZE / 2.0) ** 2))
    edge = (r2 > 0.7)
    centre = (r2 < 0.2)
    before = float(np.median(data[edge])) / float(np.median(data[centre]))
    after = (float(np.median(corrected[edge]))
             / float(np.median(corrected[centre])))
    assert abs(after - 1.0) < abs(before - 1.0) / 3.0


def test_an_empty_set_does_not_build_a_flat(tmp_path):
    flat, info = cal.pseudo_flat([])
    assert flat is None
    assert info["note"]


def test_a_cancelled_build_returns_nothing(tmp_path):
    paths, _vig = _frames(tmp_path, n=4, dither_px=3.0)
    flat, info = cal.pseudo_flat(paths, cancel=lambda: True)
    assert flat is None
    assert info["note"] == "cancelled"
