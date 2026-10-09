############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: optimal PSF matching (ADR-073)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen checks for core/difference.py: a synthetic field whose stars
are broadened by a known kernel, so the fit can be checked against the
answer. No network, no Qt."""

import numpy as np
import pytest

from nightscribe.core import difference

SHAPE = (320, 320)
SKY = 500.0


def _field(sigma, seed=3, n=40):
    # @return: a synthetic star field with a Gaussian point spread
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:SHAPE[0], 0:SHAPE[1]]
    img = np.full(SHAPE, SKY) + rng.normal(0.0, 2.0, SHAPE)
    pts = rng.uniform(30, SHAPE[0] - 30, size=(n, 2))
    for x, y in pts:
        img += rng.uniform(3000, 9000) * np.exp(
            -((xx - x) ** 2 + (yy - y) ** 2) / (2 * sigma ** 2))
    return img


def test_find_stars_returns_the_bright_unsaturated_ones():
    obs = _field(sigma=2.5)
    obs[160, 160] = 65535.0                     # a saturated star
    stars = difference.find_stars(obs, ceil=0.9 * np.max(obs))
    assert len(stars) >= 10
    # the saturated star is left out: no star sits on it
    assert not any(abs(x - 160) < 3 and abs(y - 160) < 3 for x, y in stars)


def test_gaussian_match_recovers_the_broadening():
    # obs is the same field as ref but with a broader point spread: the
    # match must narrow the residual toward zero
    ref = _field(sigma=1.5, seed=4)
    obs = _field(sigma=2.6, seed=4)             # same stars, same noise seed
    stars = difference.find_stars(obs)
    before = difference._stamp_residual(obs, ref, stars)
    m = difference.match(obs, ref, stars)
    assert m["kind"] in ("gaussian", "kernel")
    assert m["residual"] < before


def test_fit_kernel_recovers_a_known_kernel_model():
    # obs = ref * K_true: the regularized fit must reproduce the MODEL
    # (the kernel itself is ill-determined; the difference image is not)
    ref = _field(sigma=2.0, seed=5)
    k_true = difference._gauss2d(1.0, 3)
    obs = difference.convolve2d(ref, k_true)
    stars = difference.find_stars(obs)
    kernel, bg, ok = difference.fit_kernel(obs, ref, stars)
    assert ok
    model = difference.convolve2d(ref, kernel) + bg
    noise = np.std(obs - model)
    # the fitted model matches to the noise level, far better than the
    # uncorrected reference
    raw = np.std(obs - (ref - ref.mean()) * 0.4)
    assert noise < 0.2 * raw


def test_match_never_returns_a_worse_subtraction():
    # the chosen match is never worse than leaving the reference alone
    ref = _field(sigma=2.0, seed=6)
    obs = _field(sigma=3.0, seed=6)
    stars = difference.find_stars(obs)
    base = difference._stamp_residual(obs, ref, stars)
    m = difference.match(obs, ref, stars)
    assert m["residual"] <= base + 1e-9


def test_background_removes_a_smooth_pedestal_not_the_target():
    # a smooth bulge plus a bright point: the polynomial takes the bulge
    # away and leaves the point (a SN) untouched
    yy, xx = np.mgrid[0:240, 0:240]
    bulge = 300.0 * np.exp(-((xx - 120) ** 2 + (yy - 120) ** 2)
                           / (2 * 45.0 ** 2))
    diff = 50.0 + bulge
    diff[180, 180] = 50000.0
    bg = difference.background(diff)
    assert bg is not None
    resid = diff - bg
    # the smooth pedestal is largely gone over the bulge...
    assert abs(float(np.median(resid[100:140, 100:140]))) \
        < 0.6 * float(np.median(diff[100:140, 100:140]))
    # ...and the bright point survives
    assert resid[180, 180] > 40000.0


def test_host_gain_is_fitted_on_the_galaxy_not_the_stars():
    # a galaxy (extended) with one scale and stars with another: the host's
    # scale must come from the galaxy, not from the stars
    yy, xx = np.mgrid[0:200, 0:200]
    gal = 3000.0 * np.exp(-((xx - 100) ** 2 + (yy - 100) ** 2)
                          / (2 * 25.0 ** 2))
    rng = np.random.default_rng(1)
    ref = 100.0 + gal
    obs = 100.0 + 0.7 * gal
    stars = []
    for _ in range(8):
        x, y = rng.uniform(20, 180, 2)
        stars.append((float(x), float(y)))
        amp = rng.uniform(2000, 6000)
        g2 = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * 2.5 ** 2))
        ref = ref + amp * g2
        obs = obs + 0.4 * amp * g2
    g = difference.host_gain(obs, ref, stars)
    assert g == pytest.approx(0.7, abs=0.05)


def test_convolve2d_matches_a_manual_sum():
    img = np.arange(25, dtype=float).reshape(5, 5)
    k = np.array([[0.0, 0.25, 0.0], [0.25, 0.0, 0.25], [0.0, 0.25, 0.0]])
    out = difference.convolve2d(img, k)
    # centre pixel = the average of its four neighbours (true convolution)
    assert out[2, 2] == pytest.approx(
        (img[1, 2] + img[3, 2] + img[2, 1] + img[2, 3]) / 4.0)


def test_smooth_convolve_is_the_separable_gaussian():
    img = _field(sigma=2.0, seed=7)
    k = difference._gauss2d(1.2, 4)
    a = difference.convolve2d(img, k)
    b = difference._smooth_convolve(img, k)
    # the separable path and the direct sum agree to floating point
    assert np.allclose(a[20:-20, 20:-20], b[20:-20, 20:-20], atol=1e-6)
