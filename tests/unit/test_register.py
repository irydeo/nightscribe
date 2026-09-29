############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: frame registration (series plan, 7B)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Register a synthetic star field shifted and rotated by a known
similarity and check that the transform is recovered and the residual
drops. No network."""

import math

import numpy as np
import pytest

from nightscribe.core import register as reg

H = W = 260
SIGMA = 2.5


def _field(seed=0, n=45, sky=100.0, gradient=0.0, vignette=0.0,
           noise=2.0):
    rng = np.random.default_rng(seed)
    data = np.full((H, W), sky)
    yy, xx = np.ogrid[:H, :W]
    if gradient:
        # the smooth sky a real plate carries: it used to poison the
        # Fourier correlation and send the alignment to a nonsense angle
        data = data + gradient * (xx - W / 2.0) + 0.4 * gradient * (yy - H / 2.0)
    if vignette:
        r = ((xx - W / 2.0) ** 2 + (yy - H / 2.0) ** 2) / (W / 2.0) ** 2
        data = data * (1.0 - vignette * r)
    for _ in range(n):
        x, y = rng.uniform(25, W - 25), rng.uniform(25, H - 25)
        amp = rng.uniform(400, 3000)
        data += amp * np.exp(-((xx - x) ** 2 + (yy - y) ** 2)
                             / (2 * SIGMA ** 2))
    if noise > 0.0:
        data += rng.normal(0.0, noise, (H, W))
    return data


def _resid(a, b):
    return float(np.abs(a[45:-45, 45:-45] - b[45:-45, 45:-45]).mean())


@pytest.mark.parametrize("angle_deg,dx,dy", [(12.0, 7, -5),
                                             (-18.0, -12, 9), (0.0, 20, 6)])
def test_registration_recovers_the_transform(angle_deg, dx, dy):
    ref = _field(seed=1)
    ang = math.radians(angle_deg)
    src = reg.apply_transform(ref, ang, dx, dy)
    tr = reg.estimate_transform(ref, src)
    # the inverse rotation comes back, and the translation keeps its
    # magnitude (the exact composition is rotation about the centre plus
    # shift; what matters is that the two frames align)
    assert math.degrees(tr["angle"]) == pytest.approx(-angle_deg, abs=0.5)
    assert math.hypot(tr["dx"], tr["dy"]) == pytest.approx(
        math.hypot(dx, dy), abs=1.5)
    warped = reg.apply_transform(src, tr["angle"], tr["dx"], tr["dy"])
    assert _resid(warped, ref) < 0.75 * _resid(src, ref)


def test_identity_transform_is_an_exact_no_op():
    ref = _field(seed=2)
    out = reg.apply_transform(ref, 0.0, 0, 0)
    assert np.allclose(out, ref, atol=1e-9)


def test_downsample_keeps_the_size_ratio():
    a = _field(seed=3)
    small, f = reg._downsample(a, target=100)
    assert small.shape[0] == (H // f)
    assert small.shape[1] == (W // f)


def test_a_realistic_plate_is_still_registered():
    # The V0526 Per case in miniature: a bright sky with a gradient and
    # vignetting, a big drift AND a rotation. The old Fourier angle
    # search answered -166 deg with a confident score on frames like
    # these; the star vote cannot.
    ref = _field(seed=9, gradient=1.5, vignette=0.35)
    src = reg.apply_transform(ref, math.radians(2.0), 60.0, -25.0)
    tr = reg.estimate_transform(ref, src)
    assert math.degrees(tr["angle"]) == pytest.approx(-2.0, abs=0.5)
    assert tr["n"] >= reg.MIN_MATCH
    assert tr["rms_px"] <= reg.MAX_RMS_PX
    assert reg.trusted(tr)
    warped = reg.apply_transform(src, tr["angle"], tr["dx"], tr["dy"])
    # the star residual drops: what the whole feature exists for
    assert _resid(warped, ref) < 0.6 * _resid(src, ref)


def test_a_translation_seed_is_not_turned_into_a_rotation():
    # A field that only slides must come back as a pure translation: a
    # rotation that is not there is a wrong answer, however small the
    # residual it reaches on a few clustered stars.
    #
    # Sign convention of the module: apply_transform(data, a, dx, dy)
    # SAMPLES the source at p + d, so the content moves by -d, while the
    # transform's (dx, dy) is the position of the reference feature in
    # the source frame. A content drift of (-33, +18) is therefore
    # apply_transform(..., 33, -18) and answers dx = -33.
    ref = _field(seed=4)
    src = reg.apply_transform(ref, 0.0, 33.0, -18.0)
    tr = reg.estimate_transform(ref, src)
    assert abs(math.degrees(tr["angle"])) < 0.2
    assert tr["spread"] > reg._MIN_SPREAD
    assert tr["dx"] == pytest.approx(-33.0, abs=1.0)
    assert tr["dy"] == pytest.approx(18.0, abs=1.0)


def test_a_frame_with_no_stars_falls_back_to_the_correlation():
    # A star-poor (or a purely nebulous) frame still has to be alignable,
    # and the fallback must say it is a correlation, not a verification.
    ref = _field(seed=6)
    src = reg.apply_transform(ref, 0.0, -12.0, 7.0)
    tr = reg.estimate_transform(ref, src, ref_stars=np.empty((0, 3)))
    assert tr["source"] == "correlation"
    assert tr["dx"] == pytest.approx(12.0, abs=1.5)
    assert tr["dy"] == pytest.approx(-7.0, abs=1.5)
