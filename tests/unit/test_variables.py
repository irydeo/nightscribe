############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: variable star maths (Track V, V0.5-V0.7)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import pytest

from nightscribe.core import variables


def test_phase_at_basic():
    assert variables.phase_at(1005.0, 10.0, 1000.0) == 0.5
    assert variables.phase_at(1000.0, 10.0, 1000.0) == 0.0
    assert variables.phase_at(1005.0, None, 1000.0) is None
    assert variables.phase_at(1005.0, 10.0, None) is None


def test_next_extremum_pulsating_returns_whichever_first():
    # Mira rule: epoch = maximum. now=1003: max at 1010 (7 d), min at
    # 1005 (2 d) -> the minimum comes first.
    out = variables.next_extremum(10.0, 1000.0, now_mjd=1003.0, var_type="M")
    assert out == {"kind": "min", "mjd": 1005.0, "days": 2.0}


def test_next_extremum_eclipsing_epoch_is_minimum():
    # EA rule: epoch = minimum. now=1003: min at 1010 (7 d), max at
    # 1005 (2 d) -> the maximum comes first.
    out = variables.next_extremum(10.0, 1000.0, now_mjd=1003.0,
                                  var_type="E-DO")
    assert out == {"kind": "max", "mjd": 1005.0, "days": 2.0}


def test_next_extremum_composite_type_uses_first_component():
    # "NR+ELL": NR decides -> epoch = maximum (the ELL is orbital, not
    # an eclipse) — documented limitation (V-e)
    out = variables.next_extremum(10.0, 1000.0, now_mjd=1001.0,
                                  var_type="NR+ELL")
    assert out["kind"] == "min"          # min (epoch+P/2=1005) before max (1010)


def test_next_extremum_incomplete_ephemeris():
    assert variables.next_extremum(None, 1000.0) is None
    assert variables.next_extremum(10.0, None) is None


def test_next_extremum_real_mira_ephemeris():
    # omi Cet from the frozen VSX fixture: P=331.3 d, epoch JD 2458457
    # (that epoch marks the MAXIMUM, Mira type M). now sits just after the
    # 8th minimum (epoch+P/2+8P = 61272.6), so the NEXT maximum (9P) comes
    # before the next minimum: the max must win the "whichever first" race.
    epoch_mjd = 2458457 - 2400000.5
    out = variables.next_extremum(331.3, epoch_mjd, now_mjd=61300.0,
                                  var_type="M")
    assert out["kind"] == "max"
    assert out["mjd"] == pytest.approx(epoch_mjd + 9 * 331.3, abs=1e-6)
