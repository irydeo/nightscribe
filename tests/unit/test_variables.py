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


def test_hjd_frozen_reference_wesb1():
    # Frozen 2026-09-11 against the project Sun (Schlyter): +250.09 s
    jd = 2459653.44800
    hjd = variables.jd_to_hjd(jd, 15.2254, 55.0667)
    assert (hjd - jd) * 86400 == pytest.approx(250.09, abs=30.0)


def test_hjd_frozen_reference_tcrb():
    # Frozen 2026-09-11 against the project Sun (Schlyter): -196.45 s
    jd = 2459653.44800
    hjd = variables.jd_to_hjd(jd, 239.87567, 25.92017)
    assert (hjd - jd) * 86400 == pytest.approx(-196.45, abs=30.0)


def test_hjd_is_bounded_by_the_light_time_across_the_earth_sun_distance():
    # The bound is the light time across that date's real Earth-Sun
    # distance (r * c), not across a fixed 1 AU: r swings 0.983-1.017 AU
    # so the cap is ~507 s, not 499 s. The correction is the projection of
    # the Earth-Sun vector onto the line of sight, hence <= r*c by
    # definition (dot product of two unit vectors).
    from nightscribe.core import ephem_minor
    for month in range(12):
        jd = 2460000.0 + 30 * month
        _, _, r = ephem_minor.sun_ra_dec(jd)
        bound_s = r * 499.004784
        for ra in (0.0, 90.0, 180.0, 270.0):
            corr_s = abs(variables.jd_to_hjd(jd, ra, 30.0) - jd) * 86400
            assert corr_s <= bound_s + 1e-6


def test_hjd_sign_towards_and_away_from_the_sun():
    from nightscribe.core import ephem_minor
    jd = 2459653.44800
    sra, sdec, r = ephem_minor.sun_ra_dec(jd)
    towards = (variables.jd_to_hjd(jd, sra, sdec) - jd) * 86400
    away = (variables.jd_to_hjd(jd, (sra + 180) % 360, -sdec) - jd) * 86400
    assert towards == pytest.approx(r * 499.004784, rel=1e-3)
    assert away == pytest.approx(-r * 499.004784, rel=1e-3)


def _pts(mags, filt="V", source="manual"):
    return [{"mjd": 1000.0 + i, "filter": filt, "mag": m, "err": None,
             "source": source} for i, m in enumerate(mags)]


def test_detect_event_drop():
    # flat 12.0, last point fades to 12.8 -> brightness drop (dip)
    ev = variables.detect_event(_pts([12.0, 12.1, 11.9, 12.0, 12.8]))
    assert ev["direction"] == "drop"
    assert ev["delta_mag"] == pytest.approx(0.8, abs=0.05)
    assert ev["filter"] == "V"


def test_detect_event_rise():
    # T CrB erupting: last point much BRIGHTER (mag down)
    ev = variables.detect_event(_pts([10.1, 10.0, 10.1, 10.0, 8.5]))
    assert ev["direction"] == "rise"


def test_detect_event_needs_four_points_and_threshold():
    assert variables.detect_event(_pts([12.0, 12.0, 13.0])) is None
    assert variables.detect_event(_pts([12.0, 12.1, 11.9, 12.0, 12.3])) \
        is None                               # 0.3 < 0.5 threshold


def test_detect_event_ignores_survey_points_and_splits_filters():
    pts = _pts([12.0, 12.0, 12.0, 12.0], source="survey:ztf")
    pts += _pts([12.0, 12.1, 11.9, 12.0, 12.9], filt="B")
    ev = variables.detect_event(pts)
    assert ev["filter"] == "B"                # the survey run never fires
