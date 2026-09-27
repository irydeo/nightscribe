############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: chart annotation boxes (ADR-046)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Pure-math checks for core/chart_annotate.py: the corner-box rule set
(name always; position/scale/FOV only with an astrometric solution;
brightness only with a calibrated measurement; empty fields omit their
line) and every formatter. No Qt, no matplotlib, no network.
"""

from nightscribe.core import chart_annotate as ca


# ------------------------------------------------------------- formatters

def test_format_date_ut_full_iso():
    assert ca.format_date_ut("2026-09-20T21:06:28.123") == \
        "2026-09-20 21:06 UT"


def test_format_date_ut_date_only_stays_a_date():
    assert ca.format_date_ut("2026-09-20") == "2026-09-20"


def test_format_date_ut_tolerates_legacy_and_garbage():
    assert ca.format_date_ut("20/09/26") == "2026-09-20"
    assert ca.format_date_ut("not a date at all") == "not a date at all"
    assert ca.format_date_ut(None) is None
    assert ca.format_date_ut("") is None


def test_format_position_sexagesimal():
    ra, dec = ca.format_position(330.5682083, 39.8296111)
    assert ra == "RA: 22 02 16.4"
    assert dec == "Dec: +39 49 46.6"


def test_format_mag_variants():
    assert ca.format_mag(16.391, 0.042, "V") == "Mag: 16.39 ± 0.04 (V)"
    assert ca.format_mag(16.391, None, "V") == "Mag: 16.39 (V)"
    assert ca.format_mag(16.391, 0.042, None) == "Mag: 16.39 ± 0.04"
    assert ca.format_mag(16.391) == "Mag: 16.39"


def test_format_exptime():
    assert ca.format_exptime(10.0) == "Exp: 10.0 s"
    assert ca.format_exptime(10.25) == "Exp: 10.2 s"
    assert ca.format_exptime(600.0) == "Exp: 600 s"
    assert ca.format_exptime(None) is None


def test_format_pixel_scale_and_fov():
    assert ca.format_pixel_scale(1.0734) == "PSc: 1.07″/px"
    assert ca.format_fov((6.82, 6.78)) == "FOV: 6.8 × 6.8′"
    assert ca.format_fov((125.0, 84.0)) == "FOV: 2.1 × 1.4°"


# ------------------------------------------------------------ site block

def test_site_lines_omit_the_empty_fields():
    site = {"observer": "F. Calvo", "measurer": "", "station": "Z41",
            "telescope": "", "camera": "ASI 2600MM"}
    assert ca.site_lines(site) == \
        ["Obs: F. Calvo", "Msr: F. Calvo", "Stn: Z41", "Cam: ASI 2600MM"]


def test_site_lines_measurer_wins_over_the_fallback():
    site = {"observer": "F. Calvo", "measurer": "A. Garcia"}
    assert ca.site_lines(site) == ["Obs: F. Calvo", "Msr: A. Garcia"]


def test_site_lines_empty_means_no_lines():
    assert ca.site_lines({}) == []
    assert ca.site_lines(None) == []


def test_site_from_config_reads_the_keys():
    class _Cfg:
        _d = {"observer_name": "F. Calvo", "mpc_code": "Z41",
              "telescope_desc": "0.43-m f/4.9 reflector"}

        def get(self, key, default=None):
            return self._d.get(key, default)

    assert ca.site_from_config(_Cfg()) == {
        "observer": "F. Calvo", "measurer": "", "station": "Z41",
        "telescope": "0.43-m f/4.9 reflector", "camera": ""}


# ----------------------------------------------------------------- rules

def test_name_only_minimal_chart():
    # No WCS, no header, no site: just the object name, always present.
    assert ca.build_boxes(name="AT 2026acka") == \
        {"top_left": ["AT 2026acka"]}


def test_nothing_at_all_gives_no_boxes():
    assert ca.build_boxes() == {}
    assert ca.build_boxes(name="  ") == {}


def test_position_scale_fov_need_the_wcs():
    meta = {"date_obs": "2026-09-20T21:06:28", "exptime_s": 10.0}
    # without a solution: no RA/Dec, no PSc, no FOV
    boxes = ca.build_boxes(name="AT 2026acka", meta=meta)
    assert boxes["top_right"] == ["Date: 2026-09-20 21:06 UT",
                                  "Exp: 10.0 s"]
    assert "bottom_left" not in boxes
    # with a solution they all appear
    wcs = {"ra_deg": 330.5682, "dec_deg": 39.8296,
           "scale_arcsec_px": 1.07, "fov_arcmin": (6.8, 6.8)}
    boxes = ca.build_boxes(name="AT 2026acka", meta=meta, wcs_info=wcs)
    assert boxes["top_right"] == [
        "Date: 2026-09-20 21:06 UT", "RA: 22 02 16.4",
        "Dec: +39 49 46.6", "Exp: 10.0 s"]
    assert boxes["bottom_left"] == ["PSc: 1.07″/px", "FOV: 6.8 × 6.8′"]


def test_brightness_needs_a_calibrated_measurement():
    # A catalog magnitude is not handed in (build_boxes never sees it):
    # only a measured dict paints the Mag line.
    boxes = ca.build_boxes(name="AT 2026acka")
    assert "top_right" not in boxes
    boxes = ca.build_boxes(name="AT 2026acka",
                           measured={"mag": 16.391, "err": 0.04,
                                     "band": "V"})
    assert boxes["top_right"] == ["Mag: 16.39 ± 0.04 (V)"]
    # a measurement without magnitude is no measurement
    boxes = ca.build_boxes(name="AT 2026acka", measured={"mag": None})
    assert "top_right" not in boxes


def test_full_box_layout():
    boxes = ca.build_boxes(
        name="AT 2026acka",
        meta={"date_obs": "2026-09-20T21:06:28", "exptime_s": 10.0},
        wcs_info={"ra_deg": 330.5682, "dec_deg": 39.8296,
                  "scale_arcsec_px": 1.07, "fov_arcmin": (6.8, 6.8)},
        site={"observer": "F. Calvo", "measurer": "", "station": "Z41",
              "telescope": "0.43-m f/4.9 reflector",
              "camera": "ASI 2600MM"},
        measured={"mag": 17.1, "err": None, "band": "G"})
    assert boxes["top_left"] == ["AT 2026acka"]
    assert boxes["top_right"] == [
        "Date: 2026-09-20 21:06 UT", "RA: 22 02 16.4",
        "Dec: +39 49 46.6", "Mag: 17.10 (G)", "Exp: 10.0 s"]
    assert boxes["bottom_left"] == [
        "Obs: F. Calvo", "Msr: F. Calvo", "Stn: Z41",
        "Tel: 0.43-m f/4.9 reflector", "Cam: ASI 2600MM",
        "PSc: 1.07″/px", "FOV: 6.8 × 6.8′"]
