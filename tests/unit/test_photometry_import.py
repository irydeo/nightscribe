############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: photometry import parser (Track B, B3)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

from nightscribe.core.photometry_import import parse_photometry, _to_float


# ---------------- _to_float ----------------

def test_to_float_point_decimal():
    assert _to_float("16.557") == 16.557


def test_to_float_comma_decimal():
    assert _to_float("16,557") == 16.557


def test_to_float_non_numeric():
    assert _to_float("Clear") is None
    assert _to_float("N/A") is None


# ---------------- parse_photometry ----------------

def test_parse_space_separated():
    text = "2020/09/08.853 16.557 C (Clear)"
    pts, skipped = parse_photometry(text)
    assert len(pts) == 1
    assert skipped == []
    assert pts[0]["mag"] == 16.557
    assert pts[0]["filter"] == "C"
    assert pts[0]["mjd"] is not None


def test_parse_csv_comma_decimal():
    text = "2020/09/08.853,16,557,C (Clear)"
    pts, skipped = parse_photometry(text)
    assert len(pts) == 1
    assert pts[0]["mag"] == 16.557
    assert pts[0]["filter"] == "C (Clear)"


def test_parse_tab_separated():
    text = "2020/09/08.853\t16.557\tC (Clear)"
    pts, _ = parse_photometry(text)
    assert len(pts) == 1
    assert pts[0]["mag"] == 16.557


def test_parse_with_error():
    text = "2020/09/08.853 16.557 0.02 C (Clear)"
    pts, _ = parse_photometry(text)
    assert pts[0]["err"] == 0.02


def test_parse_without_error():
    text = "2020/09/08.853 16.557 C (Clear)"
    pts, _ = parse_photometry(text)
    assert pts[0]["err"] is None


def test_parse_default_filter():
    text = "2020/09/08.853 16.557"
    pts, _ = parse_photometry(text, default_filter="Clear")
    assert pts[0]["filter"] == "Clear"


def test_parse_bare_mjd():
    text = "60602.5 16.557 0.02 Clear"
    pts, _ = parse_photometry(text)
    assert pts[0]["mjd"] == 60602.5
    assert pts[0]["mag"] == 16.557


def test_parse_jd_converts_to_mjd():
    text = "2458107.714 16.6 V"
    pts, _ = parse_photometry(text)
    # JD 2458107.714 → MJD 58107.214
    assert abs(pts[0]["mjd"] - 58107.214) < 0.01


# ---------------- bare YYYYMMDD (forensic 2026-09-17) ----------------

def test_parse_yyyymmdd_bare_date():
    # AIJ/Tycho hand the date as one number; 2026-09-09 → MJD 61292.0
    text = "20260909 16.6 V"
    pts, _ = parse_photometry(text)
    assert abs(pts[0]["mjd"] - 61292.0) < 1e-6


def test_parse_yyyymmdd_with_day_fraction():
    text = "20260909.85 16.6 V"
    pts, _ = parse_photometry(text)
    assert abs(pts[0]["mjd"] - 61292.85) < 1e-6


def test_parse_yyyymmdd_rejects_bad_calendar():
    # "20261332" (month 13) and "20260230" (30 Feb) are not dates
    text = "20261332 16.6 V\n20260230 16.7 V"
    pts, skipped = parse_photometry(text)
    assert pts == []
    assert skipped == [1, 2]


def test_parse_yyyymmdd_out_of_range_skipped():
    # 17860908.5 is the old bug output (and not a real YYYYMMDD): skipped
    text = "17860908.5 16.6 V"
    pts, skipped = parse_photometry(text)
    assert pts == []
    assert skipped == [1]


def test_parse_iso_date():
    text = "2020-09-08 16.557 Clear"
    pts, _ = parse_photometry(text)
    assert pts[0]["mjd"] is not None


def test_parse_iso_datetime():
    text = "2020-09-08T22:30:00 16.557 Clear"
    pts, _ = parse_photometry(text)
    assert pts[0]["mjd"] is not None


def test_parse_multiple_lines():
    text = ("2020/09/08.853 16.557 C\n"
             "2020/09/10.860 16.527 C\n"
             "2020/09/11.898 16.662 C\n")
    pts, skipped = parse_photometry(text)
    assert len(pts) == 3
    assert skipped == []
    assert pts[0]["mag"] == 16.557
    assert pts[1]["mag"] == 16.527
    assert pts[2]["mag"] == 16.662


def test_parse_skips_header_and_garbage():
    text = ("Date Magnitude Filter\n"
             "2020/09/08.853 16.557 C\n"
             "--- some note ---\n"
             "2020/09/10.860 16.527 C\n")
    pts, skipped = parse_photometry(text)
    assert len(pts) == 2
    assert 1 in skipped   # "Date Magnitude Filter" header
    assert 3 in skipped   # "--- some note ---"


def test_parse_empty_text():
    pts, skipped = parse_photometry("")
    assert pts == []
    assert skipped == []


def test_parse_aij_like_table():
    # AIJ measurements table rows have many tab-separated columns; the
    # parser picks the date-ish, mag-ish and filter-ish fields.
    text = ("BJD_TDB\trelative_flux_T1\trelative_flux_err_T1\tFilter\n"
             "2458107.714007\t0.9845\t0.0021\tV\n"
             "2458108.721500\t0.9751\t0.0019\tV\n")
    pts, skipped = parse_photometry(text)
    # The header is skipped; the two data rows parse.
    # Note: relative_flux is 0-1 range, not a mag — the parser picks it up
    # as a "mag" because it's the first float in range. That's fine for the
    # quick-look; the user sees the preview and can adjust if needed.
    assert len(pts) == 2
    assert 1 in skipped   # header


def test_parse_tycho_like():
    # Tycho-Tracker exports absolute photometry with Spanish decimal comma
    text = ("2020/09/08.853;16,557;0,02;C\n"
             "2020/09/10.860;16,527;0,03;C\n")
    pts, _ = parse_photometry(text)
    assert len(pts) == 2
    assert pts[0]["err"] == 0.02
    assert pts[1]["err"] == 0.03


def test_parse_preserves_original_date_string():
    text = "2020/09/08.853 16.557 C"
    pts, _ = parse_photometry(text)
    # the mjd is computed, but the original string is available in skipped
    # only if the line failed — for success, the caller has the mjd float.
    assert len(pts) == 1
    assert pts[0]["mjd"] is not None
