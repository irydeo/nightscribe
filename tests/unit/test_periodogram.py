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


def test_the_robust_clip_drops_what_does_not_belong():
    # A clean sine plus one wild point (a satellite trail, a frame the
    # aperture could not rescue): folded by the period found in the first
    # pass, the point leaves the robust scatter of its phase bin and the
    # search is run again without it (quality plan, B3).
    t, y = _sine(period_d=0.3, noise=0.004)
    y = np.copy(y)
    y[7] += 0.25
    clipped = pg.find_period(t, y, min_period_d=0.1, max_period_d=1.0,
                             method="ls", fap_shuffles=0, clip_outliers=True)
    assert clipped["clipped"]["n_dropped"] == 1
    assert clipped["period_d"] == pytest.approx(0.3, rel=0.02)
    assert any("descartado" in n["es"] for n in clipped["notes"])


def test_the_robust_clip_keeps_the_curve_itself():
    # The clip works on the residual against a running median in time, so
    # the star's own amplitude (or a slow trend) is never an outlier: it
    # must drop exactly nothing on a clean variable curve.
    t, y = _sine(period_d=0.3, amp=0.3, noise=0.01)
    res = pg.find_period(t, y, min_period_d=0.1, max_period_d=1.0,
                         method="ls", fap_shuffles=0, clip_outliers=True)
    assert res["clipped"]["n_dropped"] == 0
    assert res["period_d"] == pytest.approx(0.3, rel=0.02)


def test_a_huge_grid_is_capped_and_said():
    # Ten years of community observations plus one night: the baseline
    # asks for hundreds of thousands of frequencies and the bootstrap
    # would never finish. The grid is capped and the search SAYS so
    # (quality plan, D1).
    rng = np.random.default_rng(4)
    mine_t = 60000.0 + np.sort(rng.uniform(0.0, 0.12, 200))
    mine_y = 0.2 * np.sin(2 * math.pi * mine_t / 0.3)
    old_t = 56000.0 + np.sort(rng.uniform(0.0, 3600.0, 300))
    old_y = 12.5 + 0.2 * np.sin(2 * math.pi * old_t / 0.3) \
        + rng.normal(0, 0.1, 300)
    t = np.concatenate([mine_t, old_t])
    y = np.concatenate([mine_y, old_y])
    grid, p_min, p_max = pg.frequency_grid(t, 0.05, 1.0)
    assert grid.size <= pg.GRID_MAX
    res = pg.find_period(t, y, min_period_d=0.05, max_period_d=1.0,
                         method="ls", fap_shuffles=8)
    assert res["period_d"] is not None
    assert any("tope" in n["es"] for n in res["notes"])


def test_the_fap_is_measured_on_the_grid_it_shuffles():
    # The observed peak and the shuffled peaks must live on the SAME
    # grid: comparing a fine-grid peak against coarse shuffles would
    # flatter the answer.
    t, y = _sine(period_d=0.3, noise=0.02)
    grid, _a, _b = pg.frequency_grid(t, 0.1, 1.0)
    coarse = pg.coarse_grid(grid, 50)
    assert coarse.size <= 50
    fa = pg.false_alarm(t, y, None, frequencies=coarse, shuffles=20)
    assert fa["fap"] is not None
    assert 0.0 < fa["fap"] <= 1.0
