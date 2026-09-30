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


# ------------------------------------------------------------- the band
# The plate's heading (ADR-046 rev.): two lines, a colour per role and a
# documented drop order. The roles are decided here, so the same datum
# cannot come out in two colours in the render.

_META = {"date_obs": "2023-12-19T18:42:06", "exptime_s": 40.0,
         "filter": "Clear"}
_WCS = {"ra_deg": 49.9938, "dec_deg": 49.7803, "scale_arcsec_px": 1.55,
        "fov_arcmin": (42.96, 32.34)}
_GOOD_MAG = {"mag": 12.34, "err": 0.05, "band": "V", "used": [1, 2, 3, 4],
             "check": {"ok": True}}


def _roles(line):
    # @return: [(text, role)] of one band line
    return [(s["text"], s["role"]) for s in line]


def test_the_band_says_identity_then_context():
    # Line 1: who and where and how bright. Line 2: when, with what and how
    # the plate is scaled. Nothing wears a label it does not need: the
    # magnitude is what comes after the position.
    band = ca.build_band(name="V0526 Per", meta=_META, wcs_info=_WCS,
                         measured=_GOOD_MAG, equipment="SXV-H18",
                         site={"station": "Z41"})
    first, second = band["lines"]
    assert _roles(first) == [
        ("V0526 Per", ca.ROLE_NAME),
        ("RA 03 19 58.5 · Dec +49 46 49.1", ca.ROLE_POS),
        ("12.34 ± 0.05 (V)", ca.ROLE_MAG)]
    assert _roles(second) == [
        ("2023-12-19 18:42 UT", ca.ROLE_CONTEXT),
        ("40.0 s", ca.ROLE_CONTEXT),
        ("Clear", ca.ROLE_CONTEXT),
        ("SXV-H18", ca.ROLE_CONTEXT),
        ("Stn Z41", ca.ROLE_CONTEXT),
        ("1.55″/px", ca.ROLE_CONTEXT),
        ("43.0 × 32.3′", ca.ROLE_CONTEXT)]
    # the fields the drop order uses are named, one per segment
    assert [s["field"] for s in second] == [
        "date", "exp", "filter", "equip", "stn", "psc", "fov"]
    assert [s["field"] for s in first] == ["name", "pos", "mag"]


def test_a_plate_without_a_solution_says_what_it_cannot_say():
    # No WCS: the position is the catalogue's (and it says so, because the
    # colour is not enough on a printout) and the scale and the field are
    # not there at all: they belong to the plate's own solution.
    band = ca.build_band(name="V0526 Per", meta=_META, wcs_info=None,
                         catalog_mag=12.0, target=(49.99038, 49.86875),
                         site={"station": "Z41"})
    first, second = band["lines"]
    assert first[1]["role"] == ca.ROLE_POS_CAT
    assert first[1]["text"].endswith(" (cat)")
    assert first[2] == {"text": "12.00 cat", "role": ca.ROLE_MAG_CAT,
                        "field": "mag"}
    assert [s["field"] for s in second] == ["date", "exp", "filter", "stn"]


def test_the_magnitude_wears_the_colour_its_numbers_deserve():
    # Four honest signals, all of them computed by the recipe: the error it
    # declares, how many comparisons hold the zero point, what the check
    # star said, and whether the target's core was clipped.
    assert ca.magnitude_role(_GOOD_MAG) == ca.ROLE_MAG
    assert ca.magnitude_role({**_GOOD_MAG, "err": 0.20}) == \
        ca.ROLE_MAG_DOUBT
    assert ca.magnitude_role({**_GOOD_MAG, "used": [1, 2]}) == \
        ca.ROLE_MAG_DOUBT
    assert ca.magnitude_role({**_GOOD_MAG, "check": {"ok": False}}) == \
        ca.ROLE_MAG_DOUBT
    assert ca.magnitude_role({**_GOOD_MAG, "result": {"saturated": True}}) \
        == ca.ROLE_MAG_DOUBT
    assert ca.magnitude_role(None) is None
    assert ca.magnitude_role({"mag": None}) is None
    # a measurement beats the catalogue, always
    band = ca.build_band(name="X", measured={**_GOOD_MAG, "err": 0.3},
                         catalog_mag=11.0)
    assert band["lines"][0][1]["role"] == ca.ROLE_MAG_DOUBT


def test_the_drop_order_goes_from_the_least_to_the_most_needed():
    # The renderer walks this list: the field of view first, the date last
    # (a chart without a date is not a chart), and never half a field.
    assert ca.DROP_ORDER == ("fov", "psc", "equip", "filter", "stn", "date")
    assert ca.DROP_ORDER_NAME == ("mag", "pos")


def test_the_equipment_comes_from_the_plate_not_from_my_settings():
    # A colleague's frame says SXV-H18: stamping the observer's own camera
    # on it would be a lie, and MIXING the two (his camera with my
    # telescope) would be a worse one. If the header names any of it, the
    # header is the whole answer; the Settings are only for a frame that
    # says nothing at all.
    cfg = {"camera_model": "ASI2600", "telescope_desc": "0.25 m"}
    assert ca.equipment_from_header({"INSTRUME": "SXV-H18"}, cfg) == \
        "SXV-H18"
    assert ca.equipment_from_header({}, {}) is None
    # the field is capped: a chart needs the rig, not its serial number, and
    # a 31-character camera name was eating the field of view out of the
    # band. A name that fits stays whole; a longer one is cut, never leaving
    # a dangling separator. The full value stays in the header.
    assert ca.equipment_from_header({}, cfg) == "ASI2600…"
    assert ca.equipment_from_header({"INSTRUME": "SXV-H18",
                                     "TELESCOP": "0.2 m SCT"}, cfg) == \
        "SXV-H18…"
    long_name = ca.equipment_from_header(
        {"INSTRUME": "QHY42PRO-1d74db4888698d84c-QHYCCD"}, {})
    assert long_name == "QHY42PRO-…"
    assert len(long_name) <= ca.MAX_EQUIP_CHARS


def test_a_band_with_nothing_to_say_is_an_empty_identity_line():
    # No name, no position, no magnitude: nothing to draw (the view skips
    # the band entirely), and the context line is simply empty.
    band = ca.build_band()
    assert band["lines"] == [[], []]
