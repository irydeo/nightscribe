############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: scientific axis ticks (phase A1)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The axis arithmetic, checked the way a reader reads a chart: the ticks
must fall on numbers a human recognises and the labels must carry exactly
the decimals the step needs. The anchors are the two real cases that
matter: a night of V0526 Per (0.10 mag of variation) and a Julian Date
axis of ten minutes.
"""

import math

import pytest

from nightscribe.core import ticks


def test_a_night_of_variable_star_gets_hundredths():
    # 12.50 to 12.60: the reader must see 12.52, never 12.5 five times
    plan = ticks.axis_plan(12.49, 12.61)
    assert plan["step"] == pytest.approx(0.02, rel=1e-9)
    assert plan["ticks"][0] == pytest.approx(12.50, abs=1e-9)
    assert plan["labels"][:3] == ["12.50", "12.52", "12.54"]
    assert plan["offset"] == 0.0
    assert plan["offset_label"] == ""


def test_a_wide_curve_gets_whole_magnitudes():
    plan = ticks.axis_plan(9.0, 19.0)
    assert plan["step"] == pytest.approx(2.0)
    assert plan["labels"][0] == "10"
    assert all("." not in lab for lab in plan["labels"])


def test_a_julian_date_axis_factors_the_offset_out():
    # ten minutes of a night: lo/hi around 60297.77
    lo, hi = 60297.769, 60297.779
    plan = ticks.axis_plan(lo, hi)
    assert plan["offset"] != 0.0
    # the labels are small, readable numbers...
    assert all(abs(float(lab)) < 1.0 for lab in plan["labels"])
    # ...and the offset says what was taken out, with a real minus sign
    assert plan["offset_label"].startswith(("+", "\u2212"))
    assert "60297" in plan["offset_label"]


def test_ticks_are_round_numbers_inside_the_range():
    for lo, hi in ((0.0, 1.0), (-3.2, 7.9), (12.49, 12.61),
                   (60297.769, 60297.879), (0.0001, 0.0009)):
        plan = ticks.axis_plan(lo, hi)
        assert plan["ticks"], (lo, hi)
        assert plan["ticks"][0] >= lo - 1e-9
        assert plan["ticks"][-1] <= hi + 1e-9
        step = plan["step"]
        assert step > 0.0
        # every tick is a multiple of the step: that is what "round" means.
        # The tolerance is in STEP units (a thousandth of a tick is far
        # below what any pixel can show), because accumulating a step over
        # a value of 60297 leaves a float remainder that no reader sees.
        for value in plan["ticks"]:
            assert abs(value - round(value / step) * step) < 1e-3 * step


def test_the_step_is_always_a_nice_number():
    for lo, hi in ((0.0, 1.0), (12.0, 13.0), (0.0, 0.37), (100.0, 100.5)):
        step = ticks._step_for(hi - lo, 7)
        mantissa = step / math.pow(10.0, math.floor(math.log10(step)))
        assert mantissa in (1.0, 2.0, 2.5, 5.0, 10.0) or \
            mantissa == pytest.approx(1.0, rel=1e-9)


def test_degenerate_ranges_return_nothing_instead_of_raising():
    assert ticks.nice_ticks(1.0, 1.0) == []
    assert ticks.nice_ticks(2.0, 1.0) == []
    assert ticks.nice_ticks(float("nan"), 1.0) == []
    assert ticks.axis_plan(1.0, 1.0)["ticks"] == []


def test_the_decimals_follow_the_step_not_the_magnitude():
    # the same value, three different steps
    assert ticks.tick_label(12.5, 0.02) == "12.50"
    assert ticks.tick_label(12.5, 0.5) == "12.5"
    assert ticks.tick_label(12.5, 2.0) == "12"
    # never a negative zero on an axis
    assert ticks.tick_label(-0.0001, 0.5) == "0"


def test_the_pixel_drift_case_factors_out_too():
    # stars drifting around x = 800 px by a couple of pixels
    plan = ticks.axis_plan(799.6, 801.4)
    assert plan["offset"] == 0.0            # 800 / 0.5 is nowhere near 1e4
    # the nice step for a span of 1.8 px is 0.5: four labels, each one a
    # number the reader recognises (799.5, 800.0, 800.5, 801.0)
    assert plan["step"] == pytest.approx(0.5)
    assert plan["labels"][0] == "800.0" or plan["labels"][0].endswith(".0")
    # but a drift of a thousandth of a pixel does factor the offset out
    tiny = ticks.axis_plan(799.9001, 799.9009)
    assert tiny["offset"] != 0.0
    assert all(len(lab) <= 6 for lab in tiny["labels"])


def test_offset_label_uses_a_real_minus_and_stays_short():
    assert ticks.offset_label(60297.769).startswith("+")
    assert ticks.offset_label(-120.0).startswith("\u2212")
    assert ticks.offset_label(0.0) == ""


def test_the_2_5_step_gets_the_decimal_it_needs():
    # A step of 0.025 written with two decimals gives "0.02, 0.05, 0.07,
    # 0.10": a sequence that lies about its own spacing. The 2.5 family
    # needs one decimal more than the power of ten suggests.
    assert ticks.frac_digits(0.025) == 3
    assert ticks.tick_label(0.025, 0.025) == "0.025"
    assert ticks.frac_digits(2.5) == 1
    assert ticks.tick_label(2.5, 2.5) == "2.5"
    # and the whole-number family is untouched
    assert ticks.frac_digits(0.02) == 2
    assert ticks.frac_digits(2.0) == 0
    assert ticks.frac_digits(0.2) == 1
