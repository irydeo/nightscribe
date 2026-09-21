############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - unit tests: finder-field chart math (ADR-042)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import pytest

from nightscribe.core import field_math

CENTER = (291.366, 42.784)
FIELD_RAD = 18.0 / 60.0 * 3.141592653589793 / 180.0


def test_project_center_is_canvas_center():
    x, y = field_math.project(CENTER[0], CENTER[1], CENTER, FIELD_RAD)
    assert x == pytest.approx(500.0)
    assert y == pytest.approx(500.0)


def test_project_orientation_north_up_east_left():
    # canvas y grows down: north is a smaller y, east a smaller x
    xn, yn = field_math.project(CENTER[0], CENTER[1] + 0.05, CENTER,
                                FIELD_RAD)
    assert yn < 500.0 and xn == pytest.approx(500.0, abs=1e-6)
    xe, ye = field_math.project(CENTER[0] + 0.05, CENTER[1], CENTER,
                                FIELD_RAD)
    assert xe < 500.0
    # inverted view swaps both
    xi, yi = field_math.project(CENTER[0], CENTER[1] + 0.05, CENTER,
                                FIELD_RAD, inverted=True)
    assert yi > 500.0
    xi2, _ = field_math.project(CENTER[0] + 0.05, CENTER[1], CENTER,
                                FIELD_RAD, inverted=True)
    assert xi2 > 500.0


def test_roundtrip():
    for ra, dec in ((291.366, 42.784), (291.30, 42.80), (291.45, 42.70),
                    (291.366, 42.90)):
        x, y = field_math.project(ra, dec, CENTER, FIELD_RAD)
        ra2, dec2 = field_math.screen_to_sky(x, y, CENTER, FIELD_RAD)
        assert ra2 == pytest.approx(ra, abs=1e-6)
        assert dec2 == pytest.approx(dec, abs=1e-6)


def test_roundtrip_ra_wrap_continuity():
    # a field centred at RA 0.1 deg: points at 359.9 must come back
    # continuous with the centre (0.1 - 0.15 = -0.05), never as a 24h jump
    center = (0.1, 10.0)
    x, y = field_math.project(359.95, 10.05, center, FIELD_RAD)
    ra2, dec2 = field_math.screen_to_sky(x, y, center, FIELD_RAD)
    assert ra2 % 360.0 == pytest.approx(359.95, abs=1e-6)
    assert abs(ra2 - center[0]) < 1.0
    assert dec2 == pytest.approx(10.05, abs=1e-6)


def test_choose_step():
    assert field_math.choose_step(100.0) == (15, 5)
    assert field_math.choose_step(5.0) == (1, 0.2)
    # beyond the table: the coarsest step
    assert field_math.choose_step(1e6) == field_math.TICK_STEPS[-1]


def test_edge_crossings():
    samples = [(t, float(t)) for t in range(0, 101)]
    ticks = field_math.edge_crossings(samples, 30.0, 10.0)
    values = [t["value"] for t in ticks]
    assert values == [float(v) for v in range(0, 101, 10)]
    majors = [t["value"] for t in ticks if t["major"]]
    assert majors == [0.0, 30.0, 60.0, 90.0]
    # each tick sits at the position of its value (linear edge)
    by_value = {t["value"]: t["t"] for t in ticks}
    assert by_value[50.0] == pytest.approx(50.0)


def test_tick_formatting():
    assert field_math.format_ra_tick(19 * 3600 + 25 * 60 + 27, 1) == \
        "19h25m27s"
    assert field_math.format_ra_tick(19 * 3600 + 25 * 60, 60) == "19h25m"
    assert field_math.format_ra_tick(19 * 3600, 3600) == "19h"
    assert field_math.format_dec_tick(42 * 3600 + 47 * 60 + 3, 1) == \
        "+42\u00b047\u203203\u2033"
    assert field_math.format_dec_tick(-(42 * 3600 + 47 * 60), 60) == \
        "-42\u00b047\u2032"
    assert field_math.format_dec_tick(42 * 3600, 3600) == "+42\u00b0"


def test_nice_scale_and_format():
    assert field_math.nice_scale(18.0) == 5.0
    assert field_math.nice_scale(3.0) == 0.5
    assert field_math.nice_scale(60.0) == 15.0
    assert field_math.format_scale(0.5) == "30\u2033"
    assert field_math.format_scale(5.0) == "5\u2032"
