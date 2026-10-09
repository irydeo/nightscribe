############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: exposure calculator (ADR-021)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import datetime

from nightscribe.core import exposure


def test_plate_scale_formula():
    # 3.76um pixels, 2000mm focal -> ~0.387 arcsec/px
    s = exposure.plate_scale(3.76, 2000.0)
    assert abs(s - 0.3876) < 1e-3


def test_plate_scale_zero_focal():
    assert exposure.plate_scale(3.76, 0.0) == 0.0


def test_plate_scale_with_binning():
    # The config's pixel is the SENSOR's, so a 2x2-binned plate is twice as
    # coarse: without it every consumer of the scale was off by that factor.
    base = exposure.plate_scale(3.76, 2000.0)
    assert abs(exposure.plate_scale(3.76, 2000.0, "2x2") - 2 * base) < 1e-9
    assert abs(exposure.plate_scale(3.76, 2000.0, "3x3") - 3 * base) < 1e-9
    # 1x1, empty, junk and a bare number all land on something sane
    assert exposure.plate_scale(3.76, 2000.0, "1x1") == base
    assert exposure.plate_scale(3.76, 2000.0, "") == base
    assert exposure.plate_scale(3.76, 2000.0, None) == base
    assert exposure.plate_scale(3.76, 2000.0, "junk") == base
    assert abs(exposure.plate_scale(3.76, 2000.0, 2) - 2 * base) < 1e-9
    assert exposure.binning_factor("2x2") == 2.0
    assert exposure.binning_factor(" 3X3 ") == 3.0
    assert exposure.binning_factor(None) == 1.0
    assert exposure.binning_factor("junk") == 1.0


def test_sampling_verdict():
    # The band where a star's FWHM lands on two or three pixels: 0.5-2.0
    # arcsec/pixel for the seeing of a typical site. The edges belong to the
    # band (the verdict is a rule of thumb, not a cliff).
    assert exposure.sampling(0.39) == "fine"
    assert exposure.sampling(0.5) == "ok"
    assert exposure.sampling(1.55) == "ok"
    assert exposure.sampling(2.0) == "ok"
    assert exposure.sampling(2.58) == "coarse"
    assert exposure.sampling(0) is None
    assert exposure.sampling(None) is None
    assert exposure.sampling("junk") is None


def test_the_welcome_limit_grows_with_the_aperture():
    # The Welcome step's starting point (the real one is measured; the
    # tooltip and ADR-058 say so). The anchor is a typical amateur stacked
    # image where an 8-inch telescope reaches about magnitude 18.5.
    assert abs(exposure.limit_from_aperture(8) - 18.5) < 0.05
    assert abs(exposure.limit_from_aperture(4) - 17.0) < 0.05
    assert abs(exposure.limit_from_aperture(16) - 20.0) < 0.05
    # monotonic: more aperture never means less depth
    depths = [exposure.limit_from_aperture(d) for d in (3, 6, 10, 14, 20)]
    assert depths == sorted(depths)
    # a non-positive or unusable aperture has no estimate
    assert exposure.limit_from_aperture(0) is None
    assert exposure.limit_from_aperture(None) is None
    assert exposure.limit_from_aperture("junk") is None


def test_max_exposure_no_trail():
    # rate 10"/min, scale 0.5"/px, tol 1px -> 1*0.5*60/10 = 3 s
    t = exposure.max_exposure_no_trail(10.0, 0.5)
    assert abs(t - 3.0) < 1e-6


def test_max_exposure_unknown_rate():
    assert exposure.max_exposure_no_trail(0.0, 0.5) is None
    assert exposure.max_exposure_no_trail(None, 0.5) is None


def test_session_duration():
    # 30 frames x (60s + 15s) = 2250 s
    d = exposure.session_duration_s(30, 60.0, 15.0)
    assert d == 2250


def test_latest_safe_start():
    end = datetime.datetime(2026, 8, 24, 3, 0, tzinfo=datetime.timezone.utc)
    start = exposure.latest_safe_start(end, 2250)
    assert start == end - datetime.timedelta(seconds=2250)


def test_latest_safe_start_none():
    assert exposure.latest_safe_start(None, 1000) is None


def test_feasible_true_and_false():
    a = datetime.datetime(2026, 8, 24, 22, 0, tzinfo=datetime.timezone.utc)
    b = datetime.datetime(2026, 8, 25, 3, 0, tzinfo=datetime.timezone.utc)
    assert exposure.feasible(a, b, 3600) is True
    assert exposure.feasible(a, b, 999999) is False
    assert exposure.feasible(None, b, 60) is False


def test_transit_exposure_respects_the_camera_cap():
    # an sCMOS caps the recommended exposure (the rest comes from grouping)
    from nightscribe.core import exposure
    assert exposure.recommended_transit_exposure(14.0) == 120
    assert exposure.recommended_transit_exposure(14.0, max_exposure_s=30) \
        == 30
    assert exposure.recommended_transit_exposure(9.0, max_exposure_s=30) == 15


def test_sn_exposure_respects_the_camera_cap():
    from nightscribe.core import exposure
    assert exposure.recommended_sn_exposure(20.0) == 300
    assert exposure.recommended_sn_exposure(20.0, max_exposure_s=10) == 10


def test_group_n_for_span():
    from nightscribe.core import exposure
    # 5 s frames grouped to reach a ~60 s effective point
    assert exposure.group_n_for_span(60, 5) == 12
    assert exposure.group_n_for_span(60, 10) == 6
    assert exposure.group_n_for_span(3, 10) == 1     # never below one
    assert exposure.group_n_for_span(0, 5) == 1
    assert exposure.group_n_for_span(None, 5) == 1
