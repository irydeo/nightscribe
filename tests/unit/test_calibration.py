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


# --------------------------------------------------- never calibrate twice

def test_export_calibrated_marks_the_copy(tmp_path):
    # The marker is what keeps a calibrated copy from being calibrated again:
    # the recipe cards survive the export, so without it a second run would
    # subtract the dark and divide the flat twice.
    data = np.full((4, 4), 10.0, dtype=np.float32)
    out = cal.export_calibrated(data, {"INSTRUME": "TestCam"},
                                tmp_path / "cal.fits")
    with fits.open(out) as h:
        header = dict(h[0].header)
    assert header[cal.CALIBRATED_CARD] is True
    assert cal.is_calibrated(header) is True


def test_is_calibrated_reads_a_raw_frame_as_not_calibrated(tmp_path):
    raw = _write_fits(tmp_path / "light.fits", np.ones((4, 4)),
                      INSTRUME="TestCam")
    with fits.open(raw) as h:
        header = dict(h[0].header)
    assert cal.is_calibrated(header) is False
    # the string forms a header card may come back as are honoured too
    assert cal.is_calibrated({cal.CALIBRATED_CARD: "T"}) is True
    assert cal.is_calibrated({cal.CALIBRATED_CARD: "F"}) is False


def test_calibrate_paths_skips_an_already_calibrated_frame(tmp_db, tmp_path):
    # A light that already carries the marker and a matching dark in the
    # library: the dark must NOT be subtracted a second time, and the report
    # has to say it was skipped instead of pretending the recipe ran.
    dark_path = _add(tmp_db, tmp_path, "dark.fits", "dark",
                     np.full((6, 6), 50.0), exptime_s=30.0)
    light = np.full((6, 6), 500.0, dtype=np.float32)
    light_path = _write_fits(tmp_path / "light.fits", light, INSTRUME="TestCam",
                             GAIN=1.0, CCD__TEMP=-10.0, EXPTIME=30.0,
                             FILTER="R", NSCALIB=True)
    arrays = {dark_path: np.full((6, 6), 50.0, dtype=np.float32)}
    results = cal.calibrate_paths([light_path], tmp_db,
                                  master_loader=_loader(arrays))
    _path, data_cal, _header, report = results[0]
    assert report.already is True
    assert report.ok is True
    assert np.allclose(data_cal, 500.0)          # the dark was NOT subtracted
    assert any("already calibrated" in w for w in report.warnings)


def test_frame_calibrator_skips_an_already_calibrated_frame(tmp_db, tmp_path):
    # The track & stack reads through FrameCalibrator: the same guard has to
    # hold there, and its summary has to count the frame as skipped.
    _add(tmp_db, tmp_path, "dark.fits", "dark",
         np.full((6, 6), 50.0), exptime_s=30.0)
    light_path = _write_fits(tmp_path / "light.fits",
                             np.full((6, 6), 500.0, dtype=np.float32),
                             INSTRUME="TestCam", GAIN=1.0, CCD__TEMP=-10.0,
                             EXPTIME=30.0, FILTER="R", NSCALIB=True)
    fc = cal.FrameCalibrator(tmp_db, None)
    out = fc(light_path)
    assert np.allclose(out, 500.0)               # untouched
    assert fc.reports[0][1].already is True
    summary = fc.summary()
    assert summary["already"] == 1
    assert summary["offsets"] == [] and summary["flats"] == []


# ------------------------------------------------------ building masters

def _cal_frame(path, value, kind="Dark", **cards):
    # @args: path - where, value - the constant level, kind - IMAGETYP,
    #        cards - extra header cards (CCD__TEMP writes CCD-TEMP)
    # @return: the path (str). A calibration frame with a small pattern, so
    #          the median of several can be told from a single one.
    data = np.full((8, 8), float(value), dtype=np.float32)
    data[2:4, 2:4] += 10.0
    return _write_fits(path, data, IMAGETYP=kind, INSTRUME="TestCam",
                       **cards)


def _index_dark(db, tmp_path, name, project_id, **meta):
    # @args: db - Database, tmp_path - the test folder, name - the file,
    #        project_id - who owns it (None for a SHARED master)
    # @return: the master's path
    path = _write_fits(tmp_path / name, np.full((6, 6), 50.0),
                       IMAGETYP="Dark", INSTRUME="TestCam", GAIN=1.0,
                       CCD__TEMP=-10.0, EXPTIME=30.0)
    cal.add_master(db, path, {"kind": "dark"}, project_id=project_id)
    return path


def test_build_masters_combines_with_the_median(tmp_db, tmp_path):
    # The master of a group is the MEDIAN of its frames (outliers.
    # nanmedian_axis0, the app's own combine), it carries the cards the
    # recipe keys on, and the row it is indexed under says WHO owns it.
    from nightscribe.core import outliers
    frames = [_cal_frame(tmp_path / f"d{i}.fits", 100 + i, "Dark",
                         GAIN=2.0, CCD__TEMP=-10.0, EXPTIME=30.0)
              for i in range(3)]
    out = tmp_path / "calib"
    result = cal.build_masters(tmp_db, frames, out, project_id=7)
    assert len(result["built"]) == 1
    master = result["built"][0]
    assert master["kind"] == "dark" and master["n"] == 3
    assert master["single"] is False
    # the pixels are the median of the three frames, not the first one
    want = outliers.nanmedian_axis0(np.stack(
        [cal.read_image(p)[0] for p in frames], axis=0))
    got, header = cal.read_image(master["path"])
    assert np.allclose(got, want)
    assert header["IMAGETYP"] == "Dark"
    assert float(header["GAIN"]) == 2.0
    assert float(header["EXPTIME"]) == 30.0
    assert float(header["CCD-TEMP"]) == -10.0
    ref = cal.list_masters(tmp_db)[0]
    assert ref.project_id == 7 and ref.kind == "dark"


def test_build_refuses_a_light_and_an_ambiguous_frame(tmp_db, tmp_path):
    # A light is never a master, and a frame whose header does not say what
    # it is (no IMAGETYP, a nonzero exposure) is refused too: a dark is
    # recognised by its exposure, not guessed.
    from pathlib import Path
    light = _cal_frame(tmp_path / "light.fits", 500, "Light", EXPTIME=30.0)
    ambiguous = _write_fits(tmp_path / "odd.fits",
                            np.full((8, 8), 5.0, dtype=np.float32),
                            INSTRUME="TestCam", EXPTIME=2.0)
    dark = _cal_frame(tmp_path / "d.fits", 100, "Dark", EXPTIME=30.0)
    result = cal.build_masters(tmp_db, [light, ambiguous, dark],
                               tmp_path / "calib")
    assert [b["kind"] for b in result["built"]] == ["dark"]
    reasons = {Path(p).name: why for p, why in result["skipped"]}
    assert "light.fits" in reasons and "odd.fits" in reasons


def test_a_single_frame_group_is_marked_single(tmp_db, tmp_path):
    # One frame is a COPY, not a master: it carries that frame's own noise,
    # so the build says so instead of pretending it averaged anything.
    frame = _cal_frame(tmp_path / "d.fits", 100, "Dark", EXPTIME=30.0)
    result = cal.build_masters(tmp_db, [frame], tmp_path / "calib")
    assert result["built"][0]["single"] is True
    assert result["built"][0]["n"] == 1


def test_darks_a_few_tenths_apart_are_one_master(tmp_db, tmp_path):
    # The sensor's reading drifts a few tenths over a night, and grouping by
    # the raw value turned one night of darks into a handful of one-frame
    # copies. They are grouped to the nearest degree, and the master carries
    # the MEDIAN temperature of its frames.
    frames = [_cal_frame(tmp_path / f"d{i}.fits", 100 + i, "Dark",
                         EXPTIME=30.0, CCD__TEMP=-20.0 + delta)
              for i, delta in enumerate((0.3, 0.0, -0.3))]
    result = cal.build_masters(tmp_db, frames, tmp_path / "calib")
    assert len(result["built"]) == 1
    assert result["built"][0]["n"] == 3
    assert result["built"][0]["single"] is False
    _data, header = cal.read_image(result["built"][0]["path"])
    assert float(header["CCD-TEMP"]) == -20.0


def test_darks_at_different_setpoints_stay_apart(tmp_db, tmp_path):
    # Two setpoints are two different darks: the thermal current is not the
    # same, and the recipe would not accept one for the other.
    warm = [_cal_frame(tmp_path / f"w{i}.fits", 100, "Dark", EXPTIME=30.0,
                       CCD__TEMP=-10.0) for i in range(2)]
    cold = [_cal_frame(tmp_path / f"c{i}.fits", 100, "Dark", EXPTIME=30.0,
                       CCD__TEMP=-20.0) for i in range(2)]
    result = cal.build_masters(tmp_db, warm + cold, tmp_path / "calib")
    assert len(result["built"]) == 2
    assert sorted(b["n"] for b in result["built"]) == [2, 2]


def test_the_originals_go_only_when_asked(tmp_db, tmp_path):
    # The frames are the observer's data: they are removed only when the
    # caller asked, and the master is indexed first, so a build that died
    # before the row existed cannot leave the observer with no frames AND no
    # master.
    from pathlib import Path
    frames = [_cal_frame(tmp_path / f"d{i}.fits", 100 + i, "Dark",
                         EXPTIME=30.0) for i in range(2)]
    out = tmp_path / "calib"
    result = cal.build_masters(tmp_db, frames, out, delete_sources=True)
    assert all(not Path(p).exists() for p in frames)
    assert len(cal.list_masters(tmp_db)) == 1
    assert Path(result["built"][0]["path"]).exists()
    # without the flag the originals stay
    frames2 = [_cal_frame(tmp_path / f"e{i}.fits", 100 + i, "Dark",
                          EXPTIME=60.0) for i in range(2)]
    cal.build_masters(tmp_db, frames2, out, delete_sources=False)
    assert all(Path(p).exists() for p in frames2)


def test_the_projects_own_dark_wins_over_a_shared_one(tmp_db, tmp_path):
    # A project's own master is tied to ITS nights: at the same key it beats
    # the shared one, because the shared one may be another train.
    shared = _index_dark(tmp_db, tmp_path, "shared.fits", None)
    mine = _index_dark(tmp_db, tmp_path, "mine.fits", 3)
    found = cal.find_master(tmp_db, "dark", "TestCam", 1.0, -10.0, 30.0,
                            None, tol_c=3.0, project_id=3)
    assert found is not None and found.path == mine
    assert found.path != shared


def test_a_project_without_its_own_master_uses_a_shared_one(tmp_db,
                                                            tmp_path):
    shared = _index_dark(tmp_db, tmp_path, "shared.fits", None)
    found = cal.find_master(tmp_db, "dark", "TestCam", 1.0, -10.0, 30.0,
                            None, tol_c=3.0, project_id=9)
    assert found is not None and found.path == shared


def test_another_projects_master_is_invisible_until_adopted(tmp_db,
                                                            tmp_path):
    # Ownership is a WALL: a project does not silently use another project's
    # dark. Adopting it (a LINK, the same file) is what puts it in reach.
    other = _index_dark(tmp_db, tmp_path, "other.fits", 2)
    assert cal.find_master(tmp_db, "dark", "TestCam", 1.0, -10.0, 30.0, None,
                           tol_c=3.0, project_id=5) is None
    row = cal.list_masters(tmp_db, project_id=2)[0]
    assert cal.adopt_master(tmp_db, row.id, 5) is not None
    found = cal.find_master(tmp_db, "dark", "TestCam", 1.0, -10.0, 30.0, None,
                            tol_c=3.0, project_id=5)
    assert found is not None and found.path == other
    # the link did not copy the file: both rows point at the same path
    rows = [m for m in cal.list_masters(tmp_db) if m.path == other]
    assert sorted(m.project_id for m in rows) == [2, 5]


def test_the_recipe_marks_a_master_the_project_does_not_own(tmp_db,
                                                            tmp_path):
    # Falling back to a shared master is allowed and normal, and the recipe
    # CARRIES who asked and which master it was: that is what the tab marks
    # "(shared)" from, so the observer knows the pixels are not from this
    # project's own nights (ADR-061 rev).
    shared = _index_dark(tmp_db, tmp_path, "shared.fits", None)
    meta = {"camera": "TestCam", "gain": 1.0, "temp_c": -10.0,
            "exptime_s": 30.0, "filter": None}
    recipe = cal.resolve_recipe(tmp_db, meta, tol_c=3.0, project_id=4)
    assert recipe.project_id == 4
    assert recipe.offset is not None
    assert recipe.offset.project_id is None          # the project's? no
    # the project's OWN dark is not shared, and it wins
    mine = _index_dark(tmp_db, tmp_path, "mine.fits", 4)
    recipe2 = cal.resolve_recipe(tmp_db, meta, tol_c=3.0, project_id=4)
    assert recipe2.offset.path == mine
    assert recipe2.offset.project_id == 4
    assert shared != mine


def test_delete_master_never_removes_a_file_another_row_uses(tmp_db,
                                                             tmp_path):
    from pathlib import Path
    other = _index_dark(tmp_db, tmp_path, "other.fits", 2)
    row = cal.list_masters(tmp_db, project_id=2)[0]
    cal.adopt_master(tmp_db, row.id, 5)
    # deleting the owner's row leaves the file: project 5 still points at it
    cal.delete_master(tmp_db, row.id, delete_file=True)
    assert Path(other).exists()
    assert cal.master_in_use(tmp_db, other) is True
    # the last row is what takes the file
    last = cal.list_masters(tmp_db)[0]
    cal.delete_master(tmp_db, last.id, delete_file=True)
    assert not Path(other).exists()


def test_calib_root_falls_back_to_the_data_dir():
    # The key existed since ADR-061 and nothing read it: the build needs a
    # folder, and an empty setting means <data dir>/calib.
    class _Cfg:
        def __init__(self, value):
            self._v = value

        def get(self, key, default=None):
            return self._v if key == "calib_root" else default

    assert cal.calib_root(_Cfg("")).name == "calib"
    assert cal.calib_root(_Cfg("/tmp/nsroot")).name == "nsroot"

