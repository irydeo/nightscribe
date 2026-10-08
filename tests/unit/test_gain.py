############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: system gain from the frames (quality plan,
# phase G)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The gain measurement against synthetic frames of a KNOWN gain and read
noise: the pair of frames at one exposure must recover the gain, a second
pair at another level must also pin the read noise, and the guard rails
(different exposures, saturated frames, a narrow level range, a
mis-typed value) must refuse instead of inventing a number. No network.
"""

import math

import numpy as np
import pytest

from nightscribe.core import gain as gn


def _frame(level_adu, gain, ron, shape=(192, 192), seed=1, flat=1.0):
    # A pure photon+read-noise frame in ADU: the sky is a Poisson source
    # of level_adu/g electrons, then the read noise, then the conversion.
    rng = np.random.default_rng(seed)
    electrons = rng.poisson(level_adu / gain * flat, shape)
    adu = electrons / gain + rng.normal(0.0, ron / gain, shape)
    return adu


def test_one_pair_recovers_the_gain():
    gain, ron, level = 0.8, 8.0, 4000.0
    f1 = _frame(level, gain, ron, seed=1)
    f2 = _frame(level, gain, ron, seed=2)
    fit = gn.estimate_from_frames(f1, f2, box=48)
    assert fit["gain"] == pytest.approx(gain, rel=0.05)
    assert fit["n_points"] > 4


def test_a_second_level_pins_the_read_noise():
    gain, ron = 0.8, 8.0
    # one exposure: the sky level varies only with the flat/vignetting
    pairs = []
    for seed in (1, 2):
        pairs.append(gn.frame_boxes(_frame(1200.0, gain, ron, seed=seed,
                                           flat=1.0),
                                    _frame(1200.0, gain, ron, seed=seed + 10,
                                           flat=1.0), box=48))
    # a second, much higher level (a twilight flat, a longer exposure):
    # the level range is what separates gain from read noise
    for seed in (3, 4):
        pairs.append(gn.frame_boxes(
            _frame(6000.0, gain, ron, seed=seed, flat=1.25),
            _frame(6000.0, gain, ron, seed=seed + 10, flat=1.25), box=48))
    fit = gn.fit_pair(pairs)
    assert fit["intercept_used"] is True
    assert fit["gain"] == pytest.approx(gain, rel=0.1)
    assert fit["ron"] == pytest.approx(ron, rel=0.35)


def test_a_narrow_level_range_measures_the_gain_only():
    gain, ron = 2.0, 5.0
    a = gn.frame_boxes(_frame(4000.0, gain, ron, seed=5),
                       _frame(4000.0, gain, ron, seed=6), box=48)
    fit = gn.fit_pair(a)
    assert fit["gain"] == pytest.approx(gain, rel=0.05)
    assert fit["intercept_used"] is False
    assert fit["ron"] is None
    assert any("ruido de lectura" in n["es"] for n in fit["notes"])


def test_a_silly_gain_is_refused_not_rounded():
    # frames whose "difference" has almost no variance: the fit would
    # answer a gain of thousands
    f1 = np.full((128, 128), 4000.0)
    f2 = np.full((128, 128), 4000.0)
    fit = gn.fit_pair(gn.frame_boxes(f1, f2, box=32))
    assert fit["gain"] is None
    assert fit["notes"]


def test_too_few_clean_boxes_is_said():
    f1 = np.full((64, 64), 4000.0)
    f2 = np.full((64, 64), 4000.0)
    fit = gn.fit_pair(gn.frame_boxes(f1, f2, box=32))
    assert fit["gain"] is None
    assert any("cajas" in n["es"] for n in fit["notes"])


def test_localised_structure_is_clipped_out():
    # a star cancels in the DIFFERENCE of two frames; what does not cancel
    # is a cosmic ray, a hot pixel or a satellite trail in one of them
    # alone. The robust clip must remove those pixels and keep the boxes.
    rng = np.random.default_rng(9)
    gain, ron = 0.8, 8.0
    f1 = _frame(4000.0, gain, ron, shape=(256, 256), seed=9)
    f2 = _frame(4000.0, gain, ron, shape=(256, 256), seed=10)
    for _ in range(40):
        x, y = rng.integers(4, 252, 2)
        f1[y, x] += 30000.0
    boxes = gn.frame_boxes(f1, f2, box=64)
    fit = gn.fit_pair(boxes)
    assert fit["n_points"] > 0
    assert fit["gain"] == pytest.approx(gain, rel=0.1)


def test_exposures_must_match():
    ha = {"EXPTIME": 40.0}
    hb = {"EXPTIME": 40.0}
    hc = {"EXPTIME": 20.0}
    assert gn.same_exposure(ha, hb) is True
    assert gn.same_exposure(ha, hc) is False
    assert gn.same_exposure({}, hb) is False


def test_the_settings_win_over_everything():
    est = {"gain": 0.5, "ron": 9.0, "gain_err": 0.01, "notes": []}
    out = gn.resolve(settings_gain=1.2, settings_ron=4.0,
                     header={"GAIN": 0.9, "RDNOISE": 7.0}, estimate=est)
    assert out["gain"] == 1.2 and out["ron"] == 4.0
    assert out["source"] == "settings"


def test_the_measurement_wins_over_a_header_that_disagrees():
    # The header used to win, on the reasoning that it is "a fact of the
    # camera". It is not a fact: it can carry the camera's gain SETTING or
    # a placeholder (the author's own QHY42Pro frames: GAIN = 5,
    # EGAIN = 1.0, real gain 0.11 e-/ADU). When the measurement of the
    # very frames disagrees, the measurement wins and the note says so.
    est = {"gain": 0.5, "ron": 9.0, "gain_err": 0.01, "notes": []}
    out = gn.resolve(header={"EGAIN": 1.0, "READNOIS": 6.5}, estimate=est)
    assert out["gain"] == 0.5 and out["source"] == "frames"
    assert out["ron"] == 9.0
    assert any("cabecera" in n["es"] for n in out["notes"])


def test_a_header_that_agrees_is_not_called_a_liar():
    # When the card and the measurement are the same number, there is
    # nothing to warn about: the note stays silent.
    est = {"gain": 0.72, "ron": 9.0, "gain_err": 0.01, "notes": []}
    out = gn.resolve(header={"EGAIN": 0.75, "READNOIS": 6.5}, estimate=est)
    assert out["gain"] == 0.72 and out["source"] == "frames"
    assert not any("cabecera" in n["es"] for n in out["notes"])


def test_the_header_is_used_when_there_is_no_measurement():
    # No estimate (no pair of frames to measure): the header is the only
    # word, and the read noise rides with it.
    out = gn.resolve(header={"EGAIN": 0.75, "READNOIS": 6.5})
    assert out["gain"] == 0.75 and out["ron"] == 6.5
    assert out["source"] == "header"


def test_the_measurement_is_the_last_resort_and_keeps_its_name():
    est = {"gain": 0.76, "ron": None, "gain_err": 0.02,
           "notes": [{"es": "x", "en": "x"}]}
    out = gn.resolve(estimate=est)
    assert out["gain"] == 0.76 and out["source"] == "frames"
    assert out["gain_err"] == 0.02
    assert out["notes"]


def test_no_gain_anywhere_says_so():
    out = gn.resolve()
    assert out["gain"] is None and out["source"] is None
    msg = gn.summary(out)
    assert "ganancia" in msg["es"].lower() or "Ganancia" in msg["es"]
    assert "CCD" in msg["es"] and "CCD" in msg["en"]


def test_summary_names_the_origin():
    out = gn.resolve(estimate={"gain": 0.76, "ron": 8.0, "notes": []})
    msg = gn.summary(out)
    assert "0.76" in msg["es"] and "tomas" in msg["es"]
    assert "0.76" in msg["en"] and "frames" in msg["en"]


def test_loss_less_than_the_physics_promises():
    # the variance of the difference must follow the model: if the frames
    # are ideal, the recovered gain is the injected one to a few percent
    gain, ron, level = 1.5, 4.0, 3000.0
    big = _frame(level, gain, ron, shape=(512, 512), seed=21)
    big2 = _frame(level, gain, ron, shape=(512, 512), seed=22)
    fit = gn.estimate_from_frames(big, big2, box=64)
    assert fit["gain"] == pytest.approx(gain, rel=0.03)
    # the model says: var = 2*level/g + 2*ron^2/g^2
    want = 2.0 * level / gain + 2.0 * ron ** 2 / gain ** 2
    got = fit["slope"] * level
    assert got == pytest.approx(want, rel=0.05)


def test_odd_shape_is_refused():
    with pytest.raises(ValueError):
        gn.frame_boxes(np.zeros((10, 10)), np.zeros((8, 8)), box=8)
