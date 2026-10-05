############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: calibrating on read (the astrometry loader)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The astrometry calibrates AS IT READS, not into copies.

ADR-061 promised calibration in memory, and the stacking engine reads each
frame many times and in pieces (the registration wants the whole frame, the
warp wants a box per candidate of the sweep), so writing calibrated copies
would cost gigabytes of I/O per visit. `calibration.FrameCalibrator` is a
loader that applies the recipe on the way in, resolves the recipe from each
frame's own header and caches it (a visit is one camera, one filter, one
temperature), and `track_stack.read_pixels` closes the two loader
conventions (array, or array and header) in one place.

These tests pin that the pixels really come out calibrated, that the
pseudo-flat is used only when the library has no flat, and that both loader
conventions are accepted.
"""

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nightscribe.core import calibration as cal       # noqa: E402
from nightscribe.core import track_stack as ts        # noqa: E402

SIZE = 64


def _write(path, data, **cards):
    from astropy.io import fits
    hdu = fits.PrimaryHDU(np.asarray(data, dtype=np.float32))
    for key, value in cards.items():
        hdu.header[key] = value
    hdu.writeto(str(path), overwrite=True)
    return str(path)


def _vignetting(size=SIZE, strength=0.4):
    yy, xx = np.mgrid[0:size, 0:size]
    r2 = (((xx - size / 2.0) ** 2 + (yy - size / 2.0) ** 2)
          / ((size / 2.0) ** 2))
    return 1.0 - strength * r2


def _light(tmp_path, name="light.fits", sky=1000.0):
    # a flat sky with the train's vignetting on it, exactly what a flat fixes
    data = np.full((SIZE, SIZE), sky) * _vignetting()
    return _write(tmp_path / name, data, EXPTIME=3.0, INSTRUME="TestCam",
                  **{"CCD-TEMP": -10.0}, FILTER="R", GAIN=2.0)


def test_the_loader_applies_the_recipe_from_the_library(tmp_path, tmp_db):
    light = _light(tmp_path)
    flat = _write(tmp_path / "flat.fits", _vignetting() * 1200.0)
    cal.add_master(tmp_db, flat, {"kind": "flat", "camera": "TestCam",
                                  "gain": 2.0, "temp_c": -10.0,
                                  "exptime_s": 3.0, "filter": "R"})
    loader = cal.FrameCalibrator(tmp_db, None)
    out = loader(light)
    assert out.shape == (SIZE, SIZE)
    # the vignetting is gone: what is left is flat sky
    centre = float(np.median(out[SIZE // 2 - 5:SIZE // 2 + 5,
                                 SIZE // 2 - 5:SIZE // 2 + 5]))
    corner = float(np.median(np.concatenate([
        out[2:10, 2:10].ravel(), out[2:10, -10:-2].ravel()])))
    assert abs(corner / centre - 1.0) < 0.03
    summary = loader.summary()
    assert summary["flats"] == ["flat.fits"]
    assert summary["n"] == 1


def test_the_pseudo_flat_is_used_only_when_the_library_has_none(tmp_path,
                                                               tmp_db):
    light = _light(tmp_path)
    fake = np.full((SIZE, SIZE), 2.0, dtype=np.float32)
    # nothing in the library: the pseudo-flat the caller built is applied
    loader = cal.FrameCalibrator(tmp_db, None, pseudo_flat=fake)
    out = loader(light)
    # the fake flat is a constant, so it divides but cannot remove the
    # vignetting: what is left is the sky divided by two, vignetting and all
    expected = 1000.0 * float(np.median(_vignetting())) / 2.0
    assert float(np.median(out)) == pytest.approx(expected, rel=0.05)
    assert loader.summary()["flats"] == ["pseudo-flat"]
    # with a real flat in the library, the real one wins
    flat = _write(tmp_path / "flat.fits", np.full((SIZE, SIZE), 1000.0))
    cal.add_master(tmp_db, flat, {"kind": "flat", "camera": "TestCam",
                                  "gain": 2.0, "temp_c": -10.0,
                                  "exptime_s": 3.0, "filter": "R"})
    loader2 = cal.FrameCalibrator(tmp_db, None, pseudo_flat=fake)
    out2 = loader2(light)
    assert loader2.summary()["flats"] == ["flat.fits"]
    assert not np.allclose(out, out2)


def test_the_recipe_is_resolved_once_per_visit(tmp_path, tmp_db, monkeypatch):
    # A visit is one camera, one filter and one temperature within a degree:
    # the resolution is cached by that key, so it is one query and not one
    # per frame (a visit is hundreds of frames).
    from nightscribe.core import calibration as cal_mod
    paths = [_light(tmp_path, f"l{i}.fits") for i in range(4)]
    calls = {"n": 0}
    real = cal_mod.resolve_recipe

    def _spy(*a, **k):
        calls["n"] += 1
        return real(*a, **k)
    monkeypatch.setattr(cal_mod, "resolve_recipe", _spy)
    loader = cal_mod.FrameCalibrator(tmp_db, None)
    for path in paths:
        loader(path)
    assert calls["n"] == 1
    assert loader.summary()["n"] == 4


def test_read_pixels_accepts_both_loader_conventions(tmp_path):
    # calibration.read_image gives (array, header) and the calibrating
    # loader gives the array: the engine accepts both, and the ambiguity is
    # closed in ONE place instead of in each call site.
    path = _light(tmp_path)
    from_calibration = ts.read_pixels(None, path)
    assert from_calibration.ndim == 2
    assert ts.read_pixels(lambda p, b=None: np.ones((4, 4)), path).shape == \
        (4, 4)
    assert ts.read_pixels(lambda p, b=None: (np.ones((4, 4)), {"A": 1}),
                          path).shape == (4, 4)


def test_the_settings_offer_the_pseudo_flat_default(qapp=None):
    # The setting has a widget, which is the rule: a setting nobody can find
    # is a setting that does not exist. It lives in Settings > Calibration,
    # next to the master library it belongs to.
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from nightscribe.gui.main_window import _load_ui
    dlg = _load_ui("settings_dialog")
    assert dlg.chk_calib_pseudo_flat.text()
    assert dlg.lblH_calib_pseudo_flat.text()
    dlg.deleteLater()
