############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the night's diagnosis (P3)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""How faint this night goes, and whether the solution is even.

Two questions the observer asks after a run, both answered with the night's
OWN stars and not with a table:

* the limiting magnitude, from the slope of log10(SNR) against magnitude.
  For a sky-limited source that slope is -0.4 (a magnitude is a factor
  2.512 in flux and the noise does not care), which makes the fit CHECKABLE:
  a field under a bright moon or with a very short exposure comes out far
  from it, and then the figure is not quotable;
* whether the plate solution is even, from the median residual per cell of
  a 4x4 grid. One number for the whole plate hides the corners, which is
  exactly where a wrong scale or a tilted chip shows up.
"""

import numpy as np
import pytest

from nightscribe.core import photometry as ph


def _sky_limited(limit_mag=20.0, mags=range(16, 21), noise=0.0, seed=1):
    # @return: [(mag, snr)] from the exact power law, optionally with a
    #          multiplicative wobble so the fit is not handed the answer
    rng = np.random.default_rng(seed)
    a = np.log10(5.0) - ph.SKY_LIMITED_SLOPE * limit_mag
    out = []
    for m in mags:
        snr = 10.0 ** (a + ph.SKY_LIMITED_SLOPE * m)
        if noise:
            snr *= float(np.exp(rng.normal(0.0, noise)))
        out.append((float(m), float(snr)))
    return out


def test_the_limiting_magnitude_comes_from_the_night_itself():
    got = ph.limiting_magnitude(_sky_limited(20.0))
    assert got["ok"] is True
    assert got["mag"] == pytest.approx(20.0, abs=0.05)
    assert got["slope"] == pytest.approx(ph.SKY_LIMITED_SLOPE, abs=0.01)
    assert got["sky_limited"] is True
    assert got["n"] == 5


def test_the_fit_survives_noise_and_a_saturated_star():
    # Seven stars over six magnitudes with a 15 % wobble on each, and one
    # comparison that saturated (its SNR is nonsense): the clip has to drop
    # it and the limit must still come out where the sky puts it.
    pairs = _sky_limited(19.5, mags=range(15, 22), noise=0.15, seed=7)
    pairs[3] = (pairs[3][0], pairs[3][1] * 40.0)
    got = ph.limiting_magnitude(pairs)
    assert got["ok"] is True
    assert got["mag"] == pytest.approx(19.5, abs=0.35)
    assert got["used"].count(False) == 1        # the saturated one went


def test_a_field_that_is_not_sky_limited_says_so():
    # A slope far from -0.4 is the signature of a field that is NOT
    # sky-limited (a bright moon, a very short exposure, saturated
    # comparisons): the number is returned but flagged, so the interface
    # can say "not quotable" instead of quoting it.
    # a factor FOUR per magnitude instead of 2.512: log10(0.25) = -0.602
    pairs = [(16.0, 400.0), (17.0, 100.0), (18.0, 25.0), (19.0, 6.25),
             (20.0, 1.5625)]
    got = ph.limiting_magnitude(pairs)
    assert got["ok"] is True
    assert got["slope"] == pytest.approx(-0.6, abs=0.01)
    assert got["sky_limited"] is False


def test_too_few_stars_is_not_a_measurement():
    got = ph.limiting_magnitude([(16.0, 100.0), (17.0, 50.0)])
    assert got["ok"] is False
    assert got["mag"] is None
    assert got["reason"]


def test_a_grid_shows_where_the_solution_is_bad():
    # Twenty stars spread over a 2048x2048 plate, all with the same 0.2
    # arcsec residual except the ones in the top-left corner, which are off
    # by 1.5: the grid has to point at that corner and the spread has to
    # separate the two.
    rng = np.random.default_rng(3)
    pts = []
    for _ in range(20):
        x, y = rng.uniform(0, 2048), rng.uniform(0, 2048)
        bad = (x < 512) and (y < 512)
        pts.append((x, y, 1.5 if bad else 0.2))
    got = ph.quality_grid(pts, (2048, 2048), n=4)
    assert got["ok"] is True
    assert got["median"] == pytest.approx(0.2, abs=0.01)
    assert got["worst"] == pytest.approx(1.5, abs=0.01)
    assert got["spread"] == pytest.approx(1.3, abs=0.02)
    # cells are [row][col] with row 0 at the TOP of the image
    assert got["cells"][0][0] == pytest.approx(1.5, abs=0.01)


def test_an_even_solution_has_no_spread():
    rng = np.random.default_rng(5)
    pts = [(rng.uniform(0, 2048), rng.uniform(0, 2048),
            0.2 + rng.normal(0, 0.005)) for _ in range(40)]
    got = ph.quality_grid(pts, (2048, 2048), n=4)
    assert got["ok"] is True
    assert got["spread"] < 0.05
    assert got["worst"] < 0.3


def test_an_empty_cell_is_none_not_a_zero():
    # A corner with no star is "we do not know", never "0 arcsec of error":
    # a zero would read as a perfect solution where nothing was measured.
    pts = [(100.0, 100.0, 0.2), (200.0, 150.0, 0.2),
           (1900.0, 1900.0, 0.2), (1800.0, 1850.0, 0.2)]
    got = ph.quality_grid(pts, (2048, 2048), n=4)
    assert got["ok"] is True
    assert got["cells"][0][0] is not None       # top-left has stars
    assert got["cells"][1][1] is None           # the middle does not


def test_the_grid_needs_stars_to_judge():
    got = ph.quality_grid([(1.0, 1.0, 0.2)], (100, 100))
    assert got["ok"] is False
    assert got["reason"]
