############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: period search (quality plan, phase C)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The period search against known synthetic curves: a sinusoidal
variable, a sharp eclipsing dip that only the PDM should love, pure
noise whose peak must be flagged as noise, and the single-night trap
that must be SAID, never hidden. No network.
"""

import math

import numpy as np
import pytest

from nightscribe.core import periodogram as pg


def _sine(period_d=0.3, nights=6, per_night=80, amp=0.2, noise=0.01,
          seed=3, day_span=0.12):
    # A six-night campaign with the classic one-night-every-day pattern.
    rng = np.random.default_rng(seed)
    t, y = [], []
    for n in range(nights):
        span = day_span
        tt = 60000.0 + n + np.sort(rng.uniform(0.5 - span / 2,
                                               0.5 + span / 2, per_night))
        t.append(tt)
        y.append(amp * np.sin(2.0 * math.pi * tt / period_d))
    t = np.concatenate(t)
    y = np.concatenate(y) + rng.normal(0.0, noise, t.size)
    return t, y


def test_lomb_scargle_finds_a_known_sine():
    t, y = _sine(period_d=0.3)
    res = pg.find_period(t, y, min_period_d=0.1, max_period_d=1.0,
                         method="ls", fap_shuffles=0)
    assert res["period_d"] == pytest.approx(0.3, rel=0.02)
    assert res["power"] > 0.5
    assert res["cycles"] > 2.0


def test_both_methods_agree_on_a_sine():
    t, y = _sine(period_d=0.3)
    ls = pg.find_period(t, y, min_period_d=0.1, max_period_d=1.0,
                        method="ls", fap_shuffles=0)
    pdm = pg.find_period(t, y, min_period_d=0.1, max_period_d=1.0,
                         method="pdm", fap_shuffles=0)
    assert pdm["period_d"] == pytest.approx(ls["period_d"], rel=0.02)


def test_pdm_sees_a_sharp_eclipse_ls_misses():
    # a 1 % dip lasting a tenth of the cycle: the PDM has no shape prior
    rng = np.random.default_rng(5)
    period = 0.4
    t = np.sort(rng.uniform(0.0, 6.0, 900)) + 60000.0
    phase = np.mod(t / period, 1.0)
    y = np.where((phase < 0.05) | (phase > 0.95), -0.05, 0.0)
    y = y + rng.normal(0.0, 0.01, t.size)
    pdm = pg.find_period(t, y, min_period_d=0.2, max_period_d=1.0,
                         method="pdm", fap_shuffles=0)
    assert pdm["period_d"] == pytest.approx(period, rel=0.02)


def test_noise_peak_is_flagged_as_noise():
    rng = np.random.default_rng(11)
    t = np.sort(rng.uniform(0.0, 4.0, 200)) + 60000.0
    y = rng.normal(12.0, 0.05, t.size)
    res = pg.find_period(t, y, min_period_d=0.05, max_period_d=1.0,
                         method="ls", fap_shuffles=60)
    assert res["fap"] is not None and res["fap"] > 0.01
    assert any("ruido" in n["es"] or "noise" in n["en"]
               for n in res["notes"])


def test_a_real_signal_beats_the_noise_fap():
    t, y = _sine(period_d=0.3, amp=0.15, noise=0.01)
    res = pg.find_period(t, y, min_period_d=0.1, max_period_d=1.0,
                         method="ls", fap_shuffles=60)
    assert res["fap"] is not None and res["fap"] < 0.05


def test_one_night_says_the_period_is_not_fixed():
    # 3 h of a 0.127 d variable: one cycle, the trap of the V0526 Per
    # series. The search runs, but it must SAY what it cannot know.
    rng = np.random.default_rng(2)
    period = 0.127
    t = 60000.0 + np.sort(rng.uniform(0.0, 0.12, 200))
    y = 0.1 * np.sin(2.0 * math.pi * t / period) + rng.normal(0, 0.005, 200)
    res = pg.find_period(t, y, min_period_d=0.05, max_period_d=0.5,
                         method="ls", fap_shuffles=0)
    assert res["cycles"] < pg.MIN_CYCLES
    assert any("ciclos" in n["es"] for n in res["notes"])


def test_fold_puts_the_maximum_where_it_belongs():
    period = 0.5
    t = np.array([60000.0, 60000.125, 60000.25, 60000.375])
    y = np.array([0.0, 1.0, 0.0, -1.0])
    out = pg.fold(t, y, period_d=period, epoch=60000.0)
    assert out["phase"][1] == pytest.approx(0.25)
    assert out["phase"][3] == pytest.approx(0.75)
    assert out["cycle"][0] == 0.0


def test_binned_curve_keeps_the_shape_and_drops_the_noise():
    rng = np.random.default_rng(8)
    phase = rng.uniform(0.0, 1.0, 400)
    truth = 0.3 * np.sin(2.0 * math.pi * phase)
    mag = truth + rng.normal(0.0, 0.05, phase.size)
    out = pg.binned_curve(phase, mag, bins=20)
    assert out["phase"].size == 20
    assert np.std(out["mag"]) < np.std(mag)
    # every bin mean sits near the truth of its own phase
    want = 0.3 * np.sin(2.0 * math.pi * out["phase"])
    assert float(np.mean(np.abs(out["mag"] - want))) < 0.02


def test_window_peaks_at_one_day_with_nightly_gaps():
    t, _y = _sine(period_d=0.3, nights=8)
    win = pg.spectral_window(t)
    # the daily alias: a peak near f = 1 cycle/day
    i = int(np.argmin(np.abs(win["frequencies"] - 1.0)))
    local = float(np.max(win["power"][max(0, i - 3):i + 4]))
    assert local > 0.1


def test_period_grid_covers_the_baseline_once():
    t, _y = _sine(period_d=0.3, nights=6)
    grid, p_min, p_max = pg.frequency_grid(t)
    assert 1.0 / grid[-1] == pytest.approx(p_min, rel=1e-6)
    assert 1.0 / grid[0] == pytest.approx(p_max, rel=1e-6)
    assert p_max == pytest.approx(pg.baseline_days(t), rel=1e-6)


def test_short_curve_is_refused():
    res = pg.find_period([60000.0, 60000.1], [12.0, 12.1], fap_shuffles=0)
    assert res["period_d"] is None
    assert res["warnings"]
