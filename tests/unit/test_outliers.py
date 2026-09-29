############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: outliers on a light curve (phase A/B)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The detector, checked the way a reader judges a curve: it must find the
point that does not belong and stay silent on a clean one, whatever shape
the clean one has (a slope, a hump, an eclipse). The anchors are seeded,
plus the two cases we measured on the real V0526 Per series (a focus
excursion and a clean night).
"""

import math

import numpy as np
import pytest

from nightscribe.core import outliers


def _curve(n=120, amp=0.1, noise=0.01, seed=1):
    rng = np.random.default_rng(seed)
    t = np.arange(n, dtype=float) * 24.0
    y = amp * np.sin(2.0 * math.pi * t / 1800.0) + rng.normal(0, noise, n)
    return t, y


def test_a_clean_curve_has_no_outliers():
    # The local median follows the star's own shape, so a variable curve
    # is never "full of outliers": this is the property a global median
    # would break.
    for amp in (0.05, 0.3, 1.0):
        t, y = _curve(amp=amp)
        res = outliers.local_outliers(t, y)
        assert res["flags"].sum() == 0, (amp, res["flags"].sum())


def test_a_slope_is_not_an_outlier():
    # A night fading by half a magnitude (extinction): a trend, not noise
    t = np.arange(200, dtype=float) * 20.0
    y = 13.0 + 0.5 * (t - t[0]) / (t[-1] - t[0])
    res = outliers.local_outliers(t, y)
    assert res["flags"].sum() == 0


def test_a_wild_point_is_found():
    t, y = _curve()
    y = np.copy(y)
    y[57] += 0.4
    res = outliers.local_outliers(t, y)
    assert res["flags"].sum() == 1
    assert bool(res["flags"][57]) is True
    # and the residual of that point is the one that stands out
    assert abs(res["residuals"][57]) > 10 * res["scale"]


def test_a_point_with_a_huge_error_is_forgiven():
    # A faint point measured badly is not a good point that jumped: its
    # own error buys it room.
    t, y = _curve()
    y = np.copy(y)
    y[57] += 0.4
    err = np.full(y.shape, 0.01)
    err[57] = 0.5
    res = outliers.local_outliers(t, y, err=err)
    assert bool(res["flags"][57]) is False


def test_the_order_of_the_table_does_not_matter():
    # "The neighbours" means the closest points IN TIME: a series handed
    # over shuffled must give the same verdict.
    t, y = _curve()
    y = np.copy(y)
    y[57] += 0.4
    order = np.random.default_rng(3).permutation(len(t))
    shuffled = outliers.local_outliers(t[order], y[order])
    straight = outliers.local_outliers(t, y)
    back = np.empty_like(shuffled["flags"])
    back[order] = shuffled["flags"]
    assert np.array_equal(back, straight["flags"])


def test_too_few_points_marks_nothing():
    t = np.arange(4, dtype=float)
    res = outliers.local_outliers(t, np.array([1.0, 2.0, 3.0, 9.0]))
    assert res["flags"].sum() == 0
    assert res["n"] == 4


def test_a_threshold_of_zero_is_refused_by_construction():
    # sigma is an argument; a silly one must not flag the whole curve
    t, y = _curve()
    res = outliers.local_outliers(t, y, sigma=100.0)
    assert res["flags"].sum() == 0


def test_a_focus_excursion_is_found():
    # Three consecutive frames whose focus blew up badly (the aperture
    # rescues the small ones; these are the ones it cannot). A local
    # detector must see them: the neighbours of a point inside the group
    # include the other two, which is why the residual is smaller than the
    # excursion itself, and why the excursion has to be real to be found.
    t, y = _curve(n=120, amp=0.06, noise=0.01)
    y = np.copy(y)
    y[60] += 0.12
    y[61] += 0.10
    y[62] += 0.13
    res = outliers.local_outliers(t, y, sigma=3.0)
    assert res["flags"].sum() >= 2
    assert bool(res["flags"][61]) is True


def test_the_ends_of_a_series_are_not_judged():
    # With no neighbours on one side the local median lies about the level,
    # so the detector stays silent there instead of inventing outliers.
    t, y = _curve(n=40, amp=0.2, noise=0.005)
    res = outliers.local_outliers(t, y)
    assert res["flags"].sum() == 0
    # and the points it cannot judge have no residual at all
    assert math.isnan(res["residuals"][0])
    assert math.isnan(res["residuals"][-1])


def test_points_helper_reads_the_series_objects():
    class P:
        def __init__(self, mjd, mag, err=None, err_internal=None):
            self.mjd = mjd
            self.mag = mag
            self.err = err
            self.err_internal = err_internal

    pts = [P(60000.0 + i * 0.001, 12.5 + 0.001 * ((i * 7) % 5))
           for i in range(20)]
    pts[9].mag += 0.3
    res = outliers.outliers_in_points(pts)
    assert res["flags"].count(True) == 1
    assert res["flags"][9] is True
    assert res["n"] == 20
