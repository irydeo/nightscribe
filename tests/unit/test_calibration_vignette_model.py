############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the vignetting model (ADR-061 rev)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The vignetting sampled from the sky, for the observer who has no flat.

The physics is that the train's vignetting is SMOOTH and FIXED on the frame,
and the sky is the light that fills it: a grid of tiles measures it, and the
tiles a star or a dust mote spoiled are thrown away by the fit itself. These
tests build a known vignetting and two known dust spots, add stars (moving
and, worse, still), and check that the model recovers the VIGNETTING, that
it does NOT carry the dust (that is what a real flat is for), that a real
flat always wins, and that applying it flattens the frame.
"""

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nightscribe.core import calibration as cal     # noqa: E402

SIZE = 192
TILE = 24
SKY = 1000.0


def _write(path, data, **cards):
    from astropy.io import fits
    hdu = fits.PrimaryHDU(np.asarray(data, dtype=np.float32))
    for key, value in cards.items():
        hdu.header[key] = value
    hdu.writeto(str(path), overwrite=True)
    return str(path)


def _vignetting(size=SIZE, strength=0.35):
    # @return: the true SMOOTH multiplicative pattern (a radial falloff)
    yy, xx = np.mgrid[0:size, 0:size]
    r2 = (((xx - size / 2.0) ** 2 + (yy - size / 2.0) ** 2)
          / ((size / 2.0) ** 2))
    return 1.0 - strength * r2


def _dust(vig):
    # @return: the vignetting with two dust shadows on it: FINE structure,
    #          which is exactly what a smooth model cannot carry
    yy, xx = np.mgrid[0:SIZE, 0:SIZE]
    out = vig.copy()
    for (cx, cy, rad, depth) in ((54.0, 60.0, 6.0, 0.25),
                                 (138.0, 132.0, 8.0, 0.18)):
        out = out * (1.0 - depth * np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2)
                                            / (2 * rad ** 2))))
    return out


def _frames(tmp_path, n=12, dither_px=0.0, stars=True, seed=3,
            star_peak=2500.0, dust=True, pedestal=0.0):
    # @return: (paths, the smooth vignetting, the pattern with the dust)
    rng = np.random.default_rng(seed)
    vig = _vignetting()
    pattern = _dust(vig) if dust else vig
    yy, xx = np.mgrid[0:SIZE, 0:SIZE]
    paths = []
    for i in range(n):
        frame = np.full((SIZE, SIZE), SKY)
        if stars:
            for k in range(4):
                sx = 26.0 + 40.0 * k + dither_px * i
                sy = 40.0 + 34.0 * k
                frame = frame + star_peak * np.exp(
                    -(((xx - sx) ** 2 + (yy - sy) ** 2) / (2 * 1.8 ** 2)))
        frame = frame * pattern
        frame = frame + pedestal + rng.normal(0.0, 4.0, (SIZE, SIZE))
        paths.append(_write(tmp_path / f"f{i:02d}.fits", frame,
                            EXPTIME=3.0, INSTRUME="TestCam", FILTER="R"))
    return paths, vig, pattern


def _shape_agreement(model, truth):
    # @return: the median absolute deviation of model/truth from 1, over the
    #          inner field (the edges of a radial pattern are the lever)
    inner = slice(TILE, SIZE - TILE)
    got = model[inner, inner] / float(np.median(model[inner, inner]))
    want = truth[inner, inner] / float(np.median(truth[inner, inner]))
    return float(np.median(np.abs(got / want - 1.0)))


# ------------------------------------------------------------- the model

def test_the_model_recovers_the_vignetting(tmp_path):
    # Without dust the model has to come back on the smooth pattern: a few
    # per cent, normalised to a median of one.
    paths, vig, _pat = _frames(tmp_path, dust=False)
    model, info = cal.vignette_model(paths, tile=TILE, order=4)
    assert model is not None, info.get("note")
    assert float(np.median(model)) == pytest.approx(1.0, abs=0.02)
    assert model.shape == (SIZE, SIZE)
    assert _shape_agreement(model, vig) < 0.03
    assert info["kind"] == "vignette_model"
    assert info["tile_px"] == TILE and info["n_frames"] == len(paths)
    assert info["n_kept"] and info["n_kept"] <= info["n_tiles"]


def test_the_dust_is_left_out_on_purpose(tmp_path):
    # ADR-061 rev: the model is SMOOTH and does not carry the dust. It is the
    # honest trade (measured on the author's real master: the dust is worth
    # 2.38 % = 0.026 mag and the vignetting 0.087 mag), and this is the test
    # that pins it: with the dust ON the frames the model still matches the
    # smooth vignetting, and it is NOT the dust that it follows.
    paths, vig, pattern = _frames(tmp_path, dust=True)
    model, info = cal.vignette_model(paths, tile=TILE, order=4)
    assert model is not None, info.get("note")
    assert _shape_agreement(model, vig) < 0.03          # the vignetting, yes
    # and the dust is NOT in it: the model is smoother than the pattern
    assert _shape_agreement(model, pattern) > _shape_agreement(model, vig)


def test_a_static_field_is_fine(tmp_path):
    # The old pseudo-flat needed the stars to MOVE (or a mask). The model
    # does not: a still field is just a field, and the tiles with a star on
    # them are the ones the robust fit throws away.
    paths, vig, _pat = _frames(tmp_path, dither_px=0.0, dust=False)
    model, info = cal.vignette_model(paths, tile=TILE, order=4)
    assert model is not None, info.get("note")
    assert _shape_agreement(model, vig) < 0.03


def test_a_bright_star_does_not_enter_the_model(tmp_path):
    # A model carrying a star would divide every star by itself, which is the
    # failure the old masked flat was built to avoid. The fit's own clip is
    # the guard here: the tiles under a bright star are dropped.
    paths, vig, _pat = _frames(tmp_path, dust=False, star_peak=40000.0,
                               dither_px=0.0)
    model, info = cal.vignette_model(paths, tile=TILE, order=4)
    assert model is not None, info.get("note")
    # a star of 40000 ADU over a sky of 1000 is a bump of 40x. The model's
    # own range is the vignetting's (its centre over its median), and no
    # more: a star in it would take it far past that.
    want = vig / float(np.median(vig))
    assert float(model.max()) < float(want.max()) * 1.1
    assert _shape_agreement(model, vig) < 0.03


def test_the_offset_is_removed_when_a_bias_is_there(tmp_path, tmp_db):
    # The pedestal compresses the model's shape (measured: the correction
    # drops to 44 % on 1 s twilight frames), so the model is built from the
    # frames with the SAME offset removed as the light.
    paths, _vig, _pat = _frames(tmp_path, dust=False, pedestal=900.0)
    bias = _write(tmp_path / "bias.fits", np.full((SIZE, SIZE), 900.0),
                  INSTRUME="TestCam", GAIN=1.0, EXPTIME=0.0, FILTER="R",
                  IMAGETYP="Bias")
    cal.add_master(tmp_db, bias, {"kind": "bias"})
    plain, _i1 = cal.vignette_model(paths, tile=TILE, order=4)
    with_off, info = cal.vignette_model(paths, tile=TILE, order=4,
                                        db=tmp_db)
    assert with_off is not None and plain is not None
    assert info["offset"]["n_applied"] == len(paths)
    # the pedestal is gone, so the two shapes differ by more than noise: the
    # one that kept it is compressed
    assert not np.allclose(with_off, plain, atol=1e-3)


def test_the_library_flat_always_wins(tmp_path):
    # A real flat measures the train's response, dust included; the model is
    # smooth. The real one is used when it exists.
    real_flat = _write(tmp_path / "flat.fits", np.full((SIZE, SIZE), 1200.0))
    from nightscribe.core.calibration import MasterRef, Recipe
    with_flat = Recipe(flat=MasterRef(id=1, kind="flat", path=real_flat))
    without = Recipe()
    fake = np.full((SIZE, SIZE), 2.0, dtype=np.float32)
    _out, rep = cal.calibrate(np.full((SIZE, SIZE), 1000.0), with_flat,
                              vignette_model=fake)
    assert rep.flat_path == real_flat
    _out2, rep2 = cal.calibrate(np.full((SIZE, SIZE), 1000.0), without,
                                vignette_model=fake)
    assert rep2.flat_path == "vignette-model"
    assert rep2.flat_norm == pytest.approx(2.0)


def test_applying_the_model_flattens_the_frame(tmp_path):
    # End to end: a frame divided by its model must lose the radial trend
    # the vignetting put on it.
    paths, _vig, _pat = _frames(tmp_path, dust=False)
    model, info = cal.vignette_model(paths, tile=TILE, order=4)
    assert model is not None, info.get("note")
    data, _h = cal.read_image(paths[0])
    corrected = data / model
    yy, xx = np.mgrid[0:SIZE, 0:SIZE]
    r2 = (((xx - SIZE / 2.0) ** 2 + (yy - SIZE / 2.0) ** 2)
          / ((SIZE / 2.0) ** 2))
    edge = (r2 > 0.7)
    centre = (r2 < 0.2)
    before = float(np.median(data[edge])) / float(np.median(data[centre]))
    after = (float(np.median(corrected[edge]))
             / float(np.median(corrected[centre])))
    assert abs(after - 1.0) < abs(before - 1.0) / 3.0


# --------------------------------------------------------- the refusals

def test_an_empty_set_does_not_build_a_model(tmp_path):
    model, info = cal.vignette_model([])
    assert model is None
    assert info["note"]


def test_a_frame_smaller_than_one_tile_is_refused(tmp_path):
    path = _write(tmp_path / "tiny.fits", np.full((16, 16), 100.0))
    model, info = cal.vignette_model([path], tile=32)
    assert model is None
    assert "tile" in info["note"]


def test_a_cancelled_build_returns_nothing(tmp_path):
    paths, _vig, _pat = _frames(tmp_path, n=4, dust=False)
    model, info = cal.vignette_model(paths, tile=TILE, cancel=lambda: True)
    assert model is None
    assert info["note"] == "cancelled"


def test_the_model_is_written_with_its_own_cards(tmp_path):
    # It is a product of the visit and it can be LOOKED at: the FITS carries
    # what it was built with.
    from astropy.io import fits
    model = np.full((SIZE, SIZE), 1.0, dtype=np.float32)
    info = {"kind": "vignette_model", "n_frames": 20, "tile_px": TILE,
            "order": 6, "n_tiles": 64, "n_kept": 60, "median_adu": 1234.0}
    out = cal.export_vignette_model(model, tmp_path / "model.fits", info=info)
    with fits.open(out) as h:
        head = h[0].header
    assert head["NS_VIGN"] == "vignette_model"
    assert head["NS_TILE"] == TILE and head["NS_KEPT"] == 60
    assert head["IMAGETYP"] == "FLAT"      # it IS a flat to divide by
