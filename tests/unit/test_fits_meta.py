############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: FITS metadata extractor (Track B, B1)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

from nightscribe.core.fits_meta import meta_from_header, _parse_fits_date


def test_meta_full_header():
    h = {"DATE-OBS": "2026-09-09T22:30:00", "FILTER": "Clear",
         "EXPTIME": 300.0, "OBJECT": "SN 2026abc"}
    m = meta_from_header(h)
    assert m["date_obs"] == "2026-09-09T22:30:00"
    assert m["filter"] == "Clear"
    assert m["exptime_s"] == 300.0
    assert m["object"] == "SN 2026abc"
    assert m["mjd"] is not None
    # MJD for 2026-09-09T22:30:00 UTC = 61292.9375 (computed via coords)
    assert abs(m["mjd"] - 61292.9375) < 0.1


def test_meta_date_only():
    h = {"DATE-OBS": "2026-09-09"}
    m = meta_from_header(h)
    assert m["mjd"] is not None
    assert m["filter"] is None
    assert m["exptime_s"] is None


def test_meta_fallback_date_keys():
    # Some pipelines write DATE instead of DATE-OBS
    h = {"DATE": "2026-09-09T22:30:00"}
    m = meta_from_header(h)
    assert m["date_obs"] == "2026-09-09T22:30:00"
    assert m["mjd"] is not None


def test_meta_legacy_date_format():
    h = {"DATE-OBS": "09/09/26"}
    m = meta_from_header(h)
    assert m["mjd"] is not None


def test_meta_fallback_filter_keys():
    h = {"FILTERS": "R", "DATE-OBS": "2026-09-09"}
    m = meta_from_header(h)
    assert m["filter"] == "R"


def test_meta_fallback_exptime_keys():
    h = {"EXPOSURE": 120, "DATE-OBS": "2026-09-09"}
    m = meta_from_header(h)
    assert m["exptime_s"] == 120.0


def test_meta_empty_header():
    m = meta_from_header({})
    assert m["date_obs"] is None
    assert m["mjd"] is None
    assert m["filter"] is None
    assert m["exptime_s"] is None
    assert m["object"] is None


def test_meta_unparseable_date():
    h = {"DATE-OBS": "not-a-date"}
    m = meta_from_header(h)
    assert m["mjd"] is None


def test_parse_fits_date_with_fractional_seconds():
    dt = _parse_fits_date("2026-09-09T22:30:00.123456")
    assert dt is not None
    assert dt.year == 2026
    assert dt.second == 0
    assert dt.microsecond == 123456


def test_meta_object_stripped():
    h = {"OBJECT": "  SN 2026abc  ", "DATE-OBS": "2026-09-09"}
    m = meta_from_header(h)
    assert m["object"] == "SN 2026abc"


def test_meta_exptime_fortran_d_notation():
    # fits_io._parse_card_value converts Fortran D notation to float, so by
    # the time the header dict reaches meta_from_header, EXPTIME is already
    # a float. We simulate that directly.
    h = {"EXPTIME": 300.0, "DATE-OBS": "2026-09-09"}
    m = meta_from_header(h)
    assert m["exptime_s"] == 300.0
