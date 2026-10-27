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


def test_meta_mjd_obs_fallback():
    # MicroObservatory (and several amateur rigs) write the numeric UTC
    # MJD instead of a DATE-OBS with a numeric zone offset.
    h = {"DATE-OBS": "2017-12-19T18:33:43.317-0700", "MJD-OBS": 58107.065,
         "EXPTIME": 60.0}
    m = meta_from_header(h)
    assert m["mjd"] == 58107.065


def test_meta_mjd_card_wins_over_unparseable_date():
    h = {"DATE-OBS": "garbage", "MJD": "58107.5"}
    m = meta_from_header(h)
    assert m["mjd"] == 58107.5


def test_the_plate_declares_its_own_site_and_airmass():
    # Measured 2026-10-21 on a Las Cumbres plate (a 1 m at McDonald) reduced
    # from a site in Spain: the engine computed the airmass from the
    # OBSERVER's Settings, so it came out rising to 5.2 through the night
    # while the plate's own header said 1.16 -> 1.03. That number feeds the
    # scintillation term of the error, which grew from 0.05 to 0.39 mag with
    # it. The plate knows where it was taken.
    from nightscribe.core.fits_meta import (airmass_from_header,
                                            site_from_header)
    h = {"LATITUDE": 30.679833, "LONGITUD": -104.015173,
         "AIRMASS": 1.1570632}
    assert site_from_header(h) == (30.679833, -104.015173)
    assert abs(airmass_from_header(h) - 1.1570632) < 1e-9
    # the other spelling of the same two cards, and SECZ as the airmass
    h2 = {"SITELAT": "31.68", "SITELONG": "-110.88", "SECZ": "1.4645"}
    assert site_from_header(h2) == (31.68, -110.88)
    assert abs(airmass_from_header(h2) - 1.4645) < 1e-9


def test_a_plate_that_says_nothing_keeps_the_observer_settings():
    # The fallback has to be there: an amateur rig that writes no site is
    # measured with the observer's own, which IS the right one.
    from nightscribe.core.fits_meta import (airmass_from_header,
                                            site_from_header)
    assert site_from_header({"FILTER": "V"}) == (None, None)
    assert airmass_from_header({"FILTER": "V"}) is None
    # 1.0 is the zenith: anything below it is not an airmass
    assert airmass_from_header({"AIRMASS": 0.4}) is None
    # a half-declared or impossible site is not a site
    assert site_from_header({"LATITUDE": 30.68}) == (None, None)
    assert site_from_header({"LATITUDE": 200.0, "LONGITUD": 0.0}) == (None, None)


def test_meta_carries_the_site_and_the_airmass():
    h = {"DATE-OBS": "2026-09-09T22:30:00", "LATITUDE": 30.68,
         "LONGITUD": -104.02, "AIRMASS": 1.16}
    m = meta_from_header(h)
    assert m["site_lat"] == 30.68 and m["site_lon"] == -104.02
    assert abs(m["airmass"] - 1.16) < 1e-9
    # and they are None when the plate does not say, never a made-up value
    m2 = meta_from_header({"DATE-OBS": "2026-09-09T22:30:00"})
    assert m2["site_lat"] is None and m2["site_lon"] is None
    assert m2["airmass"] is None


def test_the_plate_says_how_big_its_telescope_is_when_it_says_it():
    # Las Cumbres writes the aperture into the telescope's own name, and that
    # number feeds the scintillation term: a 1 m plate measured with the
    # observer's 10" gets that term 2.5 times too big (0.032 mag against the
    # honest 0.013), and it is the term that dominates a quiet night.
    from nightscribe.core.fits_meta import aperture_from_header
    assert aperture_from_header({"TELID": "0m4c"}) == 0.4
    assert aperture_from_header({"TELID": "1m0a"}) == 1.0
    assert aperture_from_header({"TELESCOP": "2m0a"}) == 2.0
    assert aperture_from_header({"TELESCOP": "0m4-63"}) == 0.4
    assert aperture_from_header({"TELID": "1m0-06"}) == 1.0
    assert meta_from_header({"TELID": "1m0a"})["aperture_m"] == 1.0


def test_a_name_that_says_nothing_is_not_a_number():
    # 'Cecilia' (MicroObservatory) and 'CDK17' (a model) say nothing about
    # the size: inventing one would be worse than falling back to the
    # observer's Settings, which for the observer's OWN telescope is the
    # right answer anyway.
    from nightscribe.core.fits_meta import aperture_from_header
    assert aperture_from_header(
        {"TELESCOP": "Cecilia", "INSTRUME": "Main"}) is None
    assert aperture_from_header({"TELESCOP": "CDK17"}) is None
    assert aperture_from_header({"TELESCOP": "CFF300"}) is None
    assert aperture_from_header({}) is None
    # a degenerate id is not a size either
    assert aperture_from_header({"TELID": "0m0a"}) is None
