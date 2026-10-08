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


def _frames(tmp_path, n=10, dither_px=3.0, stars=True, seed=3,
            star_peak=2500.0):
    # @return: (paths, the true pattern). The stars walk `dither_px` per
    #          frame; with dither_px=0 they sit still, which is the case the
    #          percentile cannot clean. `star_peak` is in ADU over the sky of
    #          1000: the default is a modest star, and the mask tests raise it
    #          to the brightness of a real one, which is where the difference
    #          between masking and not masking becomes impossible to miss
    #          (measured on FG18: the real flat's maximum is 1.11 and the flat
    #          that carried the stars reached 2.83).
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
                frame = frame + star_peak * np.exp(
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


def test_a_static_sequence_gets_a_star_free_flat(tmp_path):
    # THE CHANGE OF 2026-10-07 (ADR-069). Without dithering the stars do not
    # move, so the percentile keeps them: the old version looked for them
    # afterwards, gave up and returned a smooth model of the vignetting, which
    # is not a flat (it does not correct the dust). Now the sources are MASKED
    # BEFORE the statistic, the masked pixels are dropped and the flat is
    # interpolated there, so a static field gives a full flat WITH the dust and
    # with NO star in it.
    #
    # Measured on the author's own 2025 FG18 visit (2 px of drift over 207
    # frames, 17 to 33 stars matched): the maximum went from 2.83 (the real
    # flat's is 1.11) to 1.1137, and the deviation over the masked pixels from
    # 33.83 % to 2.11 %.
    os.makedirs(tmp_path / "still", exist_ok=True)
    still, vig = _frames(tmp_path / "still", dither_px=0.0, seed=5)
    flat, info = cal.pseudo_flat(still, window=21)
    assert flat is not None, info.get("note")
    assert info["kind"] == "pseudo_flat"        # a flat, not a model
    assert info["filled_pct"] > 0.0             # the stars were masked
    assert info["n_sources"] > 0
    assert info["verify_pct"] < cal.PSEUDO_FLAT_VERIFY_PCT
    # THE POINT: no star bump. The true pattern's own maximum (normalised) is
    # about 1.2, and a flat carrying the stars (2500 ADU of star over a sky of
    # 1000) would go past three, which is what the old version did.
    want_norm = vig / float(np.median(vig))
    assert float(flat.max()) < float(want_norm.max()) * 1.15
    assert float(flat.max()) < 1.6
    # and what it does recover is the real pattern, dust included
    inner = slice(20, SIZE - 20)
    got = flat[inner, inner] / float(np.median(flat[inner, inner]))
    want = vig[inner, inner] / float(np.median(vig[inner, inner]))
    assert float(np.median(np.abs(got / want - 1.0))) < 0.05
    # the check that replaced the scaled MAD actually looks at the sources
    assert info["verify_pct"] is not None
    assert info["residual_pct"] is not None


def test_the_static_flat_is_better_than_the_one_without_the_mask(tmp_path):
    # The same static set, with the mask disabled by asking for a mask that
    # finds nothing (sigma astronomically high): the flat then carries the
    # stars, and the two numbers that say so are the maximum and the deviation
    # over the sources. This is the guard that keeps the mask from being
    # removed as "unnecessary" one day.
    os.makedirs(tmp_path / "still", exist_ok=True)
    still, _vig = _frames(tmp_path / "still", dither_px=0.0, seed=5,
                          star_peak=40000.0)
    masked, info_m = cal.pseudo_flat(still, window=21)
    unmasked, info_u = cal.pseudo_flat(still, window=21,
                                       mask_sigma=1e9)
    assert masked is not None and unmasked is not None
    assert float(unmasked.max()) > 1.5            # the stars are in it
    assert float(masked.max()) < 1.4              # they are not
    assert info_u["filled_pct"] == 0.0
    assert info_m["filled_pct"] > 0.0


def test_a_hot_pixel_stays_in_the_flat_so_the_division_removes_it(tmp_path):
    # A hot pixel is FIXED on the sensor, so it belongs in the flat: dividing
    # by it is what removes it. It must not be masked (it is not a star) and
    # it must be put back AFTER the smoothing, or the box filter dilutes a
    # single pixel 1681 times and the division leaves it exactly where it was.
    # Measured on FG18: 10,150 isolated spikes (0.242 % of the frame, up to
    # 9,232 ADU on a sky of 1,488) and 1,484 ADU left in the smoothed flat.
    from astropy.io import fits
    os.makedirs(tmp_path / "hot", exist_ok=True)
    paths, _vig = _frames(tmp_path / "hot", dither_px=3.0, n=8, seed=9)
    for path in paths:
        data = fits.getdata(path).astype(np.float32)
        data[40, 40] += 8000.0                   # the same pixel, every frame
        fits.PrimaryHDU(data).writeto(path, overwrite=True)
    flat, info = cal.pseudo_flat(paths, window=21)
    assert flat is not None
    assert info["hot_px"] >= 1
    # the flat has the spike in it (12x the sky), so the light divided by it
    # comes back to the sky; a flat without the restoration would leave the
    # spike exactly where it was
    assert float(flat[40, 40]) > 2.0
    data = fits.getdata(paths[0]).astype(np.float64)
    corrected = data / flat
    sky = float(np.median(corrected))
    assert float(corrected[40, 40]) == pytest.approx(sky, rel=0.3)


def test_the_masked_pixels_are_filled_and_never_left_empty(tmp_path):
    # The fill is a normalised convolution, so the pixels under a star (which
    # hold no data in ANY frame of a static field) come out of the sky around
    # them and not as a hole: a NaN in a flat would poison every division.
    os.makedirs(tmp_path / "still", exist_ok=True)
    still, _vig = _frames(tmp_path / "still", dither_px=0.0, seed=5)
    flat, info = cal.pseudo_flat(still, window=21)
    assert flat is not None
    assert np.isfinite(flat).all()
    assert (flat > 0).all()
    assert info["filled_pct"] > 0.0
    # the filled area is smooth: it is not carrying the star it replaced
    assert info["verify_pct"] < cal.PSEUDO_FLAT_VERIFY_PCT


def test_the_library_flat_always_wins(tmp_path):
    # A real flat measures the train's response; a pseudo-flat measures the
    # response times the sky's shape. The real one is used when it exists.
    real_flat = _write(tmp_path / "flat.fits", np.full((SIZE, SIZE), 1200.0))

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


def test_the_vignetting_model_is_the_last_resort(tmp_path, monkeypatch):
    # ADR-069: `vignette_model` stopped being the answer to a static field and
    # became what is left when there is not enough sky to build anything. The
    # threshold is lowered here instead of faking a crowded frame, so the
    # branch is exercised on a case whose answer is known.
    os.makedirs(tmp_path / "crowd", exist_ok=True)
    paths, _vig = _frames(tmp_path / "crowd", dither_px=0.0, seed=5)
    monkeypatch.setattr(cal, "PSEUDO_FLAT_MAX_FILLED_PCT", 0.1)
    flat, info = cal.pseudo_flat(paths, window=21)
    assert flat is not None
    assert info["kind"] == "vignette_model"
    assert info["note"]                       # it says what it is
    assert info["filled_pct"] > 0.1
    # it is a SMOOTH surface: no star bump in it either
    assert float(flat.max()) < 1.6
    # and it is not claimed to be a full flat
    assert "dust" in info["note"]


def test_without_any_sky_left_it_says_so_and_builds_nothing(tmp_path):
    # The other side of the same branch: if the sources cover everything there
    # is nothing to fit, and the honest answer is no flat and a reason.
    os.makedirs(tmp_path / "all", exist_ok=True)
    paths, _vig = _frames(tmp_path / "all", dither_px=0.0, seed=5)
    flat, info = cal.pseudo_flat(paths, window=21, mask_sigma=0.0)
    assert flat is None
    assert info["note"]


def test_a_cancelled_build_returns_nothing(tmp_path):
    paths, _vig = _frames(tmp_path, n=4, dither_px=3.0)
    flat, info = cal.pseudo_flat(paths, cancel=lambda: True)
    assert flat is None
    assert info["note"] == "cancelled"
