############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the shared stretch engine (ADR-044, phase B)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Pure-numpy checks for core/stretch.py: percentiles, linear+gamma
stretch, gain matching, uint8 conversion, inversion, histograms and the
2x2 display downscale. No Qt, no network. The compatibility re-exports
through viz/blink_view are pinned too (legacy callers depend on them).
"""

import numpy as np

from nightscribe.core import stretch


def test_auto_limits_basic():
    data = np.arange(1000, dtype=np.float32).reshape(40, 25)
    black, white = stretch.auto_limits(data, 1.0, 99.5)
    assert 0 <= black < white <= 999


def test_auto_limits_flat_and_nan():
    assert stretch.auto_limits(np.full((4, 4), np.nan)) == (0.0, 1.0)
    black, white = stretch.auto_limits(np.full((4, 4), 7.0))
    assert white > black                      # flat plate still stretches


def test_apply_stretch_linear_and_gamma():
    data = np.array([[0.0, 5.0, 10.0]], dtype=np.float32)
    out = stretch.apply_stretch(data, 0.0, 10.0, gamma=1.0)
    assert np.allclose(out, [[0.0, 0.5, 1.0]])
    bright = stretch.apply_stretch(data, 0.0, 10.0, gamma=0.5)
    assert bright[0, 1] > 0.5                 # gamma <1 lifts mid-tones
    dark = stretch.apply_stretch(data, 0.0, 10.0, gamma=2.0)
    assert dark[0, 1] < 0.5


def test_apply_stretch_clips_outside():
    data = np.array([[-100.0, 1e6]], dtype=np.float32)
    out = stretch.apply_stretch(data, 0.0, 10.0)
    assert out.tolist() == [[0.0, 1.0]]


def test_gain_roundtrip():
    ref = np.full((10, 10), 0.40, dtype=np.float32)
    obs = np.full((10, 10), 0.20, dtype=np.float32)
    gain = stretch.auto_gain(ref, obs)   # scales REF down to OBS's level
    assert gain == 0.5
    assert np.allclose(stretch.apply_gain(ref, gain), 0.20)
    assert stretch.auto_gain(np.zeros((4, 4), np.float32), obs) == 1.0


def test_to_uint8_rounding_and_nan():
    out = stretch.to_uint8(np.array([[0.0, 0.5, 1.0, np.nan]]))
    assert out.tolist() == [[0, 128, 255, 0]]
    assert out.dtype == np.uint8


def test_invert():
    img = np.array([[0.0, 0.25, 1.0]], dtype=np.float32)
    assert np.allclose(stretch.invert(img), [[1.0, 0.75, 0.0]])


def test_histogram_counts_and_edges():
    data = np.arange(100, dtype=np.float32).reshape(10, 10)
    edges, counts = stretch.histogram(data, nbins=10, bounds=(0, 100))
    assert len(edges) == 11 and counts.sum() == 100
    assert edges[0] == 0 and edges[-1] == 100


def test_histogram_defaults_and_nans():
    data = np.full((5, 5), np.nan)
    edges, counts = stretch.histogram(data)
    assert counts.sum() == 0
    data[2, 2] = 3.0
    edges, counts = stretch.histogram(data)   # bounds from the data
    assert counts.sum() == 1


def test_display_downscale_steps():
    assert stretch.display_downscale(
        np.zeros((100, 80), np.float32), cap=30).shape == (25, 20)
    big = np.zeros((9000, 9000), np.float32)
    assert stretch.display_downscale(big).shape == (2250, 2250)
    small = np.zeros((100, 100), np.float32)
    assert stretch.display_downscale(small) is small   # already fits


def test_downscale2x2_crops_odd_and_averages():
    data = np.ones((7, 5), dtype=np.float32)
    out = stretch.downscale2x2(data)
    assert out.shape == (3, 2)                # 7->6->3, 5->4->2
    assert np.allclose(out, 1.0)


def test_blink_view_reexports_match():
    from nightscribe.viz import blink_view
    assert blink_view.auto_limits is stretch.auto_limits
    assert blink_view.apply_stretch is stretch.apply_stretch
    assert blink_view.auto_gain is stretch.auto_gain
    assert blink_view.apply_gain is stretch.apply_gain
    assert blink_view.to_uint8 is stretch.to_uint8
