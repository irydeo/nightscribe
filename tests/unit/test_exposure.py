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
