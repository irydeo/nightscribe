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


def test_read_image_box_applies_bscale_bzero(tmp_path):
    # The region is a SLICE of the memmapped frame (not astropy's hdu.section,
    # which reads row by row and is 15x slower), and the scaling still has to
    # be applied to the sliced window.
    raw = np.array([[10, 20, 30], [40, 50, 60], [70, 80, 90]], dtype=np.uint16)
    path = tmp_path / "scaled.fits"
    fits.PrimaryHDU((raw.astype(np.int32) - 32768).astype(np.int16)).writeto(
        str(path))
    with fits.open(str(path), mode="update", do_not_scale_image_data=True) as h:
        h[0].header["BZERO"] = 32768
        h[0].header["BSCALE"] = 1
    region, _ = cal.read_image(str(path), box=(1, 1, 3, 3))
    assert np.array_equal(region, raw[1:3, 1:3].astype(np.float32))


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


def test_a_flat_is_not_matched_by_temperature(tmp_db, tmp_path):
    # ADR-061 rev, the author's own case: a flat taken at -14.6 C with the
    # lights at -20.0 C (5.3 C apart). A flat's SHAPE is the optical
    # train's, which does not care about the sensor's temperature, so it
    # must be used. Before this the recipe answered "no flat for this
    # filter" and the flat did nothing at all.
    _add(tmp_db, tmp_path, "flat.fits", "flat", np.ones((4, 4)),
         temp_c=-14.6, filter="Clear")
    recipe = cal.resolve_recipe(tmp_db, {"camera": "TestCam", "gain": 1.0,
                                         "temp_c": -20.0, "exptime_s": 3.6,
                                         "filter": "Clear"}, tol_c=3.0)
    assert recipe.flat is not None
    assert recipe.flat.path.endswith("flat.fits")


def test_a_bias_is_not_matched_by_temperature(tmp_db, tmp_path):
    # A bias is a read-out pedestal: its pattern barely moves with the
    # temperature, and matching it against the light's would leave the
    # library almost always empty.
    _add(tmp_db, tmp_path, "bias.fits", "bias", np.zeros((4, 4)),
         temp_c=-5.0, exptime_s=0.0)
    recipe = cal.resolve_recipe(tmp_db, {"camera": "TestCam", "gain": 1.0,
                                         "temp_c": -20.0, "exptime_s": 30.0,
                                         "filter": "R"}, tol_c=3.0)
    assert recipe.offset is not None and recipe.offset_kind == "bias"


def test_the_dark_keeps_its_temperature(tmp_db, tmp_path):
    # The dark carries the LEVEL (the thermal current), so a dark 9.4 C
    # away is not the same dark and must not be used.
    _add(tmp_db, tmp_path, "dark.fits", "dark", np.ones((4, 4)),
         temp_c=-14.6, exptime_s=30.0)
    recipe = cal.resolve_recipe(tmp_db, {"camera": "TestCam", "gain": 1.0,
                                         "temp_c": -24.0, "exptime_s": 30.0,
                                         "filter": "R"}, tol_c=3.0)
    assert recipe.offset is None


def test_the_recipe_says_why_a_dark_was_left_out(tmp_db, tmp_path):
    # The observer who can SEE the dark in the library must learn which
    # criterion left it out, with the numbers.
    _add(tmp_db, tmp_path, "dark.fits", "dark", np.ones((4, 4)),
         temp_c=-14.6, exptime_s=30.0)
    recipe = cal.resolve_recipe(tmp_db, {"camera": "TestCam", "gain": 1.0,
                                         "temp_c": -20.0, "exptime_s": 30.0,
                                         "filter": "R"}, tol_c=3.0)
    notes = [n for n in recipe.notes if n["what"] == "dark"]
    assert notes, "a near-miss dark must be explained"
    assert notes[0]["reason"] == "temperature"
    assert notes[0]["master"] == "dark.fits"
    assert notes[0]["value"] == -14.6 and notes[0]["wanted"] == -20.0
    assert notes[0]["tol"] == 3.0


def test_the_recipe_says_why_a_flat_was_left_out(tmp_db, tmp_path):
    _add(tmp_db, tmp_path, "flatR.fits", "flat", np.ones((4, 4)), filter="R")
    recipe = cal.resolve_recipe(tmp_db, {"camera": "TestCam", "gain": 1.0,
                                         "temp_c": -10.0, "exptime_s": 30.0,
                                         "filter": "V"})
    notes = [n for n in recipe.notes if n["what"] == "flat"]
    assert notes and notes[0]["reason"] == "filter"
    assert notes[0]["value"] == "R" and notes[0]["wanted"] == "V"


def test_without_a_temperature_the_newest_master_wins(tmp_db, tmp_path):
    # The list is newest first and there is no temperature to compare: the
    # first candidate must stand. Walking on would end on the OLDEST.
    _add(tmp_db, tmp_path, "flat_old.fits", "flat", np.ones((4, 4)),
         filter="R")
    _add(tmp_db, tmp_path, "flat_new.fits", "flat", np.ones((4, 4)),
         filter="R")
    recipe = cal.resolve_recipe(tmp_db, {"camera": "TestCam", "gain": 1.0,
                                         "temp_c": -20.0, "exptime_s": 30.0,
                                         "filter": "R"}, tol_c=3.0)
    assert recipe.flat is not None
    assert recipe.flat.path.endswith("flat_new.fits")


def test_a_dark_at_the_flats_exposure_is_the_flats_offset(tmp_db, tmp_path):
    # A "dark of the flats" is a dark, and the exposure tells them apart:
    # the same pool feeds both matches.
    _add(tmp_db, tmp_path, "dark_flat.fits", "dark", np.full((4, 4), 7.0),
         exptime_s=0.005)
    _add(tmp_db, tmp_path, "flat.fits", "flat", np.ones((4, 4)),
         exptime_s=0.005, filter="R")
    recipe = cal.resolve_recipe(tmp_db, {"camera": "TestCam", "gain": 1.0,
                                         "temp_c": -10.0, "exptime_s": 30.0,
                                         "filter": "R"})
    assert recipe.flat is not None
    assert recipe.flat_offset is not None
    assert recipe.flat_offset.path.endswith("dark_flat.fits")


def test_the_flat_age_is_warned(tmp_db, tmp_path):
    # A flat from weeks ago is USED (better than none) but it is SAID: the
    # train's dust moves between nights. Measured on the author's case: a
    # flat 53 days older than the lights.
    path = _write_fits(tmp_path / "flat.fits", np.ones((4, 4)),
                       INSTRUME="TestCam", FILTER="R",
                       DATE__OBS="2026-08-21T19:14:23.603")
    cal.add_master(tmp_db, path, {"kind": "flat"})
    recipe = cal.resolve_recipe(tmp_db, {
        "camera": "TestCam", "gain": 1.0, "temp_c": -10.0, "exptime_s": 30.0,
        "filter": "R", "date_obs": "2026-10-13T19:40:58.875"})
    assert recipe.flat is not None
    ages = [n for n in recipe.notes if n["reason"] == "age"]
    assert ages and ages[0]["days"] == 53


def test_a_fresh_flat_is_not_aged(tmp_db, tmp_path):
    path = _write_fits(tmp_path / "flat.fits", np.ones((4, 4)),
                       INSTRUME="TestCam", FILTER="R",
                       DATE__OBS="2026-10-13T01:00:00")
    cal.add_master(tmp_db, path, {"kind": "flat"})
    recipe = cal.resolve_recipe(tmp_db, {
        "camera": "TestCam", "gain": 1.0, "temp_c": -10.0, "exptime_s": 30.0,
        "filter": "R", "date_obs": "2026-10-13T19:40:58.875"})
    assert not [n for n in recipe.notes if n["reason"] == "age"]


# ------------------------------------------------------- what a frame is

def test_classify_master_reads_imagetyp(tmp_path):
    flat = _write_fits(tmp_path / "f.fits", np.ones((4, 4)), IMAGETYP="Flat")
    dark = _write_fits(tmp_path / "d.fits", np.ones((4, 4)),
                       IMAGETYP="Dark Flat")
    assert cal.classify_master(flat) == ("flat", None)
    assert cal.classify_master(dark) == ("dark", None)


def test_classify_master_falls_back_to_the_exposure(tmp_path):
    # Only where the exposure is unambiguous: a bias really is at zero, and
    # a dark is the usual minutes-long frame. A short non-zero frame (a
    # flat, or a bias-like flat) is NOT guessed.
    bias = _write_fits(tmp_path / "b.fits", np.ones((4, 4)), EXPTIME=0.0)
    dark = _write_fits(tmp_path / "d.fits", np.ones((4, 4)), EXPTIME=300.0)
    flat = _write_fits(tmp_path / "f.fits", np.ones((4, 4)), EXPTIME=0.005)
    assert cal.classify_master(bias) == ("bias", None)
    assert cal.classify_master(dark) == ("dark", None)
    kind, why = cal.classify_master(flat)
    assert kind is None and "IMAGETYP" in why


def test_classify_master_refuses_a_light_and_an_unknown(tmp_path):
    light = _write_fits(tmp_path / "l.fits", np.ones((4, 4)),
                        IMAGETYP="Light")
    kind, why = cal.classify_master(light)
    assert kind is None and "LIGHT" in why
    odd = _write_fits(tmp_path / "x.fits", np.ones((4, 4)), IMAGETYP="Foo")
    kind, why = cal.classify_master(odd)
    assert kind is None and "Foo" in why


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
