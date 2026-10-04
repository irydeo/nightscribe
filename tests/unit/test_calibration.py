############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: image calibration (ADR-061)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Calibration acceptance: the master library matching, the recipe rules
(one dark includes the bias, never both), the arithmetic and its order, the
flat normalisation, the absence warnings (never an exception) and the
region path that keeps the full-frame flat normalisation (D32)."""

import numpy as np
import pytest
from astropy.io import fits

from nightscribe.core import calibration as cal


def _write_fits(path, data, **cards):
    # @args: path - where, data - 2D array, cards - extra header cards
    # @return: the path (str)
    hdu = fits.PrimaryHDU(np.asarray(data))
    for key, value in cards.items():
        hdu.header[key.replace("__", "-")] = value
    hdu.writeto(str(path), overwrite=True)
    return str(path)


def _loader(arrays):
    # @args: arrays - {path: array} for the synthetic masters
    # @return: a master loader(path, box) that slices like read_image would
    def load(path, box=None):
        data = np.asarray(arrays[str(path)], dtype=np.float32)
        if box is not None:
            x0, y0, x1, y1 = box
            data = data[y0:y1, x0:x1]
        return data
    return load


def _add(db, tmp_path, name, kind, array, **meta):
    # Indexes a synthetic master (the file must exist: add_master reads its
    # header to fill whatever meta leaves out).
    path = _write_fits(tmp_path / name, array)
    db_meta = {"kind": kind, "camera": "TestCam", "gain": 1.0,
               "temp_c": -10.0, "exptime_s": 30.0, "filter": "R"}
    db_meta.update(meta)
    cal.add_master(db, path, db_meta)
    return path


# ------------------------------------------------------------------ reading

def test_read_image_applies_bscale_bzero(tmp_path):
    # A CMOS-style frame: uint16 stored as int16 with BZERO. astropy will
    # not memmap it scaled, so read_image reads it raw and scales by hand.
    raw = np.array([[0, 100], [200, 65535]], dtype=np.uint16)
    path = tmp_path / "light.fits"
    fits.PrimaryHDU((raw.astype(np.int32) - 32768).astype(np.int16)).writeto(
        str(path))
    with fits.open(str(path), mode="update", do_not_scale_image_data=True) as h:
        h[0].header["BZERO"] = 32768
        h[0].header["BSCALE"] = 1
    data, header = cal.read_image(str(path))
    assert data.dtype == np.float32
    assert np.array_equal(data, raw.astype(np.float32))
    assert header["BZERO"] == 32768


def test_read_image_box(tmp_path):
    data = np.arange(100, dtype=np.float32).reshape(10, 10)
    path = _write_fits(tmp_path / "box.fits", data)
    region, _ = cal.read_image(path, box=(2, 3, 6, 8))
    assert np.array_equal(region, data[3:8, 2:6])


def test_meta_from_header_tolerant():
    meta = cal.meta_from_header({"INSTRUME": "ASI2600", "GAIN": 100,
                                 "CCD-TEMP": "-10.5C", "EXPTIME": 60,
                                 "FILTER": "R"})
    assert meta["camera"] == "ASI2600"
    assert meta["gain"] == 100.0
    assert meta["temp_c"] == -10.5
    assert meta["exptime_s"] == 60.0
    assert meta["filter"] == "R"


# ------------------------------------------------------------------ library

def test_add_and_list_masters(tmp_db, tmp_path):
    _add(tmp_db, tmp_path, "dark.fits", "dark", np.ones((4, 4)),
         exptime_s=30.0)
    _add(tmp_db, tmp_path, "flat.fits", "flat", np.ones((4, 4)), filter="R")
    assert len(cal.list_masters(tmp_db)) == 2
    assert len(cal.list_masters(tmp_db, kind="dark")) == 1
    assert len(cal.list_masters(tmp_db, camera="other")) == 0


def test_add_master_requires_kind(tmp_db, tmp_path):
    path = _write_fits(tmp_path / "x.fits", np.ones((4, 4)))
    with pytest.raises(ValueError):
        cal.add_master(tmp_db, path, {"camera": "TestCam"})


def test_find_master_nearest_temperature(tmp_db, tmp_path):
    _add(tmp_db, tmp_path, "d1.fits", "dark", np.ones((4, 4)), temp_c=-20.0)
    _add(tmp_db, tmp_path, "d2.fits", "dark", np.ones((4, 4)), temp_c=-5.0)
    near = cal.find_master(tmp_db, "dark", "TestCam", 1.0, -6.0, 30.0,
                           tol_c=3.0)
    assert near is not None and near.temp_c == -5.0
    far = cal.find_master(tmp_db, "dark", "TestCam", 1.0, 0.0, 30.0, tol_c=3.0)
    assert far is None  # both are outside +/-3 C of 0 C


def test_find_master_exposure_is_exact(tmp_db, tmp_path):
    _add(tmp_db, tmp_path, "d.fits", "dark", np.ones((4, 4)), exptime_s=30.0)
    assert cal.find_master(tmp_db, "dark", "TestCam", 1.0, -10.0, 30.0) \
        is not None
    assert cal.find_master(tmp_db, "dark", "TestCam", 1.0, -10.0, 60.0) is None


def test_delete_master(tmp_db, tmp_path):
    path = _add(tmp_db, tmp_path, "d.fits", "dark", np.ones((4, 4)))
    assert cal.delete_master(tmp_db, cal.list_masters(tmp_db)[0].id) == path
    assert cal.list_masters(tmp_db) == []


# ------------------------------------------------------------------ recipe

def test_recipe_prefers_dark_over_bias(tmp_db, tmp_path):
    _add(tmp_db, tmp_path, "bias.fits", "bias", np.zeros((4, 4)),
         exptime_s=0.0)
    _add(tmp_db, tmp_path, "dark.fits", "dark", np.ones((4, 4)),
         exptime_s=30.0)
    recipe = cal.resolve_recipe(tmp_db, {"camera": "TestCam", "gain": 1.0,
                                         "temp_c": -10.0, "exptime_s": 30.0,
                                         "filter": "R"})
    assert recipe.offset_kind == "dark"
    # No "bias was subtracted" warning: the dark already includes the bias.
    assert not any("bias" in w for w in recipe.warnings)


def test_recipe_falls_back_to_bias_with_warning(tmp_db, tmp_path):
    _add(tmp_db, tmp_path, "bias.fits", "bias", np.zeros((4, 4)),
         exptime_s=0.0)
    recipe = cal.resolve_recipe(tmp_db, {"camera": "TestCam", "gain": 1.0,
                                         "temp_c": -10.0, "exptime_s": 30.0,
                                         "filter": "R"})
    assert recipe.offset_kind == "bias"
    assert any("thermal" in w for w in recipe.warnings)


def test_recipe_no_offset_no_flat_warns(tmp_db):
    recipe = cal.resolve_recipe(tmp_db, {"camera": "TestCam", "gain": 1.0,
                                         "temp_c": -10.0, "exptime_s": 30.0,
                                         "filter": "R"})
    assert recipe.offset is None and recipe.flat is None
    assert len(recipe.warnings) >= 2


def test_recipe_flat_is_per_filter(tmp_db, tmp_path):
    _add(tmp_db, tmp_path, "flatR.fits", "flat", np.ones((4, 4)), filter="R")
    in_r = cal.resolve_recipe(tmp_db, {"camera": "TestCam", "gain": 1.0,
                                       "temp_c": -10.0, "exptime_s": 30.0,
                                       "filter": "R"})
    in_v = cal.resolve_recipe(tmp_db, {"camera": "TestCam", "gain": 1.0,
                                       "temp_c": -10.0, "exptime_s": 30.0,
                                       "filter": "V"})
    assert in_r.flat is not None
    assert in_v.flat is None


# ---------------------------------------------------------------- arithmetic

def test_calibrate_subtracts_offset_then_divides_flat(tmp_path):
    light = np.full((4, 4), 1000.0, dtype=np.float32)
    dark = np.full((4, 4), 100.0, dtype=np.float32)
    flat = np.full((4, 4), 2.0, dtype=np.float32)
    recipe = cal.Recipe(offset=cal.MasterRef(1, "dark", "dark.fits"),
                        offset_kind="dark",
                        flat=cal.MasterRef(2, "flat", "flat.fits"))
    arrays = {"dark.fits": dark, "flat.fits": flat}
    out, report = cal.calibrate(light, recipe, loader=_loader(arrays))
    # (1000 - 100) / (2/2) = 900, and the normalisation keeps the level.
    assert np.allclose(out, 900.0)
    assert report.offset_kind == "dark" and report.flat_norm == 2.0
    assert report.pedestal_adu == 100.0


def test_calibrate_does_not_subtract_bias_and_dark(tmp_path):
    # A recipe never carries both: the engine must subtract exactly one
    # offset. Here we prove the arithmetic of the dark path (bias absent).
    light = np.full((4, 4), 1000.0, dtype=np.float32)
    dark = np.full((4, 4), 100.0, dtype=np.float32)
    recipe = cal.Recipe(offset=cal.MasterRef(1, "dark", "dark.fits"),
                        offset_kind="dark")
    out, _ = cal.calibrate(light, recipe, loader=_loader({"dark.fits": dark}))
    assert np.allclose(out, 900.0)   # 1000 - 100, not 1000 - 100 - 100


def test_calibrate_removes_vignetting(tmp_path):
    yy, xx = np.mgrid[0:64, 0:64].astype(np.float32)
    r2 = ((xx - 32) ** 2 + (yy - 32) ** 2) / (32 ** 2)
    flat = (1.0 - 0.4 * r2).astype(np.float32)
    light = (1000.0 * flat).astype(np.float32)   # a uniform sky, vignetted
    recipe = cal.Recipe(flat=cal.MasterRef(2, "flat", "flat.fits"))
    out, _ = cal.calibrate(light, recipe, loader=_loader({"flat.fits": flat}))
    # After the flat, the uniform sky is flat again.
    assert out.std() / out.mean() < 0.01
    raw_std = light.std() / light.mean()
    assert raw_std > 0.1


def test_calibrate_without_masters_is_not_an_exception():
    light = np.full((4, 4), 1000.0, dtype=np.float32)
    out, report = cal.calibrate(light, cal.Recipe())
    assert np.allclose(out, light)
    assert report.ok is False   # nothing was applied, and the report says so


def test_calibrate_region_keeps_full_frame_flat_norm(tmp_path):
    # A flat that is bright in one corner: the normalisation must come from
    # the whole frame, or a crop of the dark corner would be rescaled.
    flat = np.full((10, 10), 1.0, dtype=np.float32)
    flat[:5, :5] = 2.0
    light = np.full((4, 4), 100.0, dtype=np.float32)
    recipe = cal.Recipe(flat=cal.MasterRef(2, "flat", "flat.fits"))
    arrays = {"flat.fits": flat}
    box = (0, 0, 4, 4)   # the bright corner
    out, report = cal.calibrate(light, recipe, loader=_loader(arrays), box=box)
    # norm = median(flat) = 1.0 (half the frame is 1, half is 2 -> median 1.5
    # actually; check the region is divided by the region's own value over
    # the full-frame norm, not re-normalised to the crop).
    expected_norm = float(np.median(flat))
    assert report.flat_norm == expected_norm
    assert np.allclose(out, 100.0 / (2.0 / expected_norm))


def test_calibrate_paths_reads_recipe_from_header(tmp_db, tmp_path):
    # A light whose header carries the metadata: the recipe is resolved and
    # applied frame by frame.
    dark_path = _add(tmp_db, tmp_path, "dark.fits", "dark",
                     np.full((6, 6), 50.0), exptime_s=30.0)
    light = np.full((6, 6), 500.0, dtype=np.float32)
    light_path = _write_fits(tmp_path / "light.fits", light, INSTRUME="TestCam",
                             GAIN=1.0, CCD__TEMP=-10.0, EXPTIME=30.0,
                             FILTER="R")
    arrays = {dark_path: np.full((6, 6), 50.0, dtype=np.float32)}
    results = cal.calibrate_paths([light_path], tmp_db,
                                  master_loader=_loader(arrays))
    assert len(results) == 1
    _path, data_cal, _header, report = results[0]
    assert report.offset_kind == "dark"
    assert np.allclose(data_cal, 450.0)


def test_export_calibrated_writes_provenance(tmp_path):
    data = np.full((4, 4), 10.0, dtype=np.float32)
    report = cal.CalibrationReport(offset_kind="dark", offset_path="/m/dark.fits",
                                   flat_path="/m/flat.fits", flat_norm=1.5)
    out = cal.export_calibrated(data, {"INSTRUME": "TestCam"}, 
                                tmp_path / "cal.fits", report)
    with fits.open(out) as h:
        hist = "\n".join(str(v) for v in h[0].header["HISTORY"])
    assert "dark.fits" in hist and "flat.fits" in hist
