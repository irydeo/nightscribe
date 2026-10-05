############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: track & stack worker helpers
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The worker's velocity seed, offline. It sampled +/- 30 s and divided by
two as if the baseline were two minutes, returning exactly HALF the real
rate (measured on 2025 UR: 15.25 instead of 30.6"/min)."""

import pytest

from nightscribe.gui.workers import _rate_pa


def test_rate_pa_is_not_halved():
    # a synthetic motion of exactly 1 arcsec/min towards +dec (PA 0)
    def motion(jd):
        minutes = (jd - 2460000.0) * 1440.0
        return (10.0, 20.0 + minutes * (1.0 / 3600.0))
    rate, pa = _rate_pa(motion, 2460000.0)
    assert rate == pytest.approx(1.0, abs=0.01)
    assert pa == pytest.approx(0.0, abs=0.1)


def test_rate_pa_pa_is_north_through_east():
    # 1 arcsec/min towards +RA only (PA 90) at dec 0
    def motion(jd):
        minutes = (jd - 2460000.0) * 1440.0
        return (10.0 + minutes * (1.0 / 3600.0), 0.0)
    rate, pa = _rate_pa(motion, 2460000.0)
    assert rate == pytest.approx(1.0, abs=0.01)
    assert pa == pytest.approx(90.0, abs=0.1)


def test_rate_pa_without_an_ephemeris_is_none():
    assert _rate_pa(lambda jd: None, 2460000.0) == (None, None)
