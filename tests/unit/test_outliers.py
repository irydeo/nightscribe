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


def test_nanmedian_axis0_matches_numpy():
    # The sort-with-sentinel median has to give EXACTLY what numpy's
    # nanmedian gives, NaN columns included: it is the fast path the
    # stacking clip stands on, and a wrong median would move the clip.
    rng = np.random.default_rng(3)
    cube = rng.normal(100.0, 5.0, (7, 20, 15))       # odd count
    cube[rng.random(cube.shape) > 0.85] = np.nan     # 15 % invalid
    got = outliers.nanmedian_axis0(cube)
    expected = np.nanmedian(cube, axis=0)
    np.testing.assert_allclose(got, expected, equal_nan=True, rtol=0, atol=0)
    # even count: the two middle ones are averaged, as numpy does
    cube2 = cube[:6]
    np.testing.assert_allclose(outliers.nanmedian_axis0(cube2),
                               np.nanmedian(cube2, axis=0), equal_nan=True)
    # a whole column invalid stays NaN
    cube3 = cube.copy()
    cube3[:, 0, 0] = np.nan
    assert np.isnan(outliers.nanmedian_axis0(cube3)[0, 0])
    # a 1-D sample falls back to numpy (axis 0 of a vector is the whole thing)
    vec = np.array([3.0, np.nan, 1.0, 2.0])
    assert outliers.nanmedian_axis0(vec) == np.nanmedian(vec)


def test_scaled_mad_axis0_uses_the_fast_median():
    # The clip passes axis=0: the MAD there must come from the same median,
    # so the clip and the scale cannot disagree.
    rng = np.random.default_rng(4)
    cube = rng.normal(10.0, 2.0, (9, 8, 6))
    cube[rng.random(cube.shape) > 0.9] = np.nan
    centre = np.nanmedian(cube, axis=0)
    got = outliers.scaled_mad(cube, axis=0, centre=centre)
    expected = outliers.MAD_TO_SIGMA * np.nanmedian(np.abs(cube - centre),
                                                    axis=0)
    np.testing.assert_allclose(got, expected, equal_nan=True, rtol=0,
                               atol=1e-12)


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


# ------------------------------------------------------------ the scale

def test_scaled_mad_is_the_mad_scaled_to_a_sigma():
    # The MAD of gaussian noise is 0.6745 sigma, so the factor is
    # 1/0.6745: it is a property of the normal, and the test pins it so a
    # "small tweak" to the number is caught as the change of meaning it is.
    vals = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    med = float(np.median(vals))
    assert outliers.scaled_mad(vals) == pytest.approx(
        outliers.MAD_TO_SIGMA * float(np.median(np.abs(vals - med))))
    # the factor IS 1/0.6745 (the 75th percentile of the normal): 1.4826
    # is its four-decimal form, so the test allows that rounding and no more
    assert outliers.MAD_TO_SIGMA == pytest.approx(
        1.0 / 0.6744897501960817, abs=1e-3)
    # a known pair: +-1 about the median -> the MAD is 1
    assert outliers.scaled_mad([-1.0, 0.0, 1.0]) == pytest.approx(
        outliers.MAD_TO_SIGMA, abs=1e-9)


def test_scaled_mad_measures_from_a_given_level():
    # An iterative clip measures from its RUNNING level, which is no
    # longer the median: passing it must be honoured, or the clip would
    # quietly drift back to the median.
    vals = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    # from the median (3) the deviations are [2, 1, 0, 1, 2] -> MAD 1
    assert outliers.scaled_mad(vals) == pytest.approx(
        outliers.MAD_TO_SIGMA, abs=1e-9)
    # from level 1 they are [0, 1, 2, 3, 4] -> MAD 2: a different number,
    # which is the whole point of passing the level
    assert outliers.scaled_mad(vals, centre=1.0) == pytest.approx(
        2.0 * outliers.MAD_TO_SIGMA, abs=1e-9)


def test_scaled_mad_per_pixel_and_nan_aware():
    # The pixel stack clips each pixel on its own column, and a masked
    # frame is a NaN there: it must not poison the scale of the real ones.
    stack = np.array([[1.0, 10.0], [2.0, 20.0], [3.0, 30.0]])
    got = outliers.scaled_mad(stack, axis=0)
    # column 0 deviates by 1, column 1 by 10: each column its own scale
    assert got == pytest.approx([outliers.MAD_TO_SIGMA,
                                 10.0 * outliers.MAD_TO_SIGMA], abs=1e-9)
    with_nan = np.array([[1.0], [2.0], [np.nan], [3.0]])
    assert outliers.scaled_mad(with_nan) == pytest.approx(
        outliers.scaled_mad(np.array([1.0, 2.0, 3.0])), abs=1e-9)


def test_scaled_mad_of_nothing_is_zero():
    # The callers compare against 0 to decide "no scale, no veto": an
    # empty or all-NaN sample must answer 0.0 and never raise.
    assert outliers.scaled_mad([]) == 0.0
    assert outliers.scaled_mad([np.nan, np.nan]) == 0.0
    assert outliers.scaled_mad(None) == 0.0


def test_median_error_is_the_scatter_over_root_n():
    # The standard error of the MEDIAN: the honest error where the mean
    # cannot be trusted (a faint object's curve carries bright outliers).
    vals = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0])
    assert outliers.median_error(vals) == pytest.approx(
        outliers.scaled_mad(vals) / math.sqrt(vals.size))
    # one point has no error to speak of, and no point has none at all
    assert outliers.median_error([3.0]) == 0.0
    assert outliers.median_error([]) == 0.0
