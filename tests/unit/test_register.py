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


def _field(seed=0, n=45):
    rng = np.random.default_rng(seed)
    data = np.full((H, W), 100.0)
    yy, xx = np.ogrid[:H, :W]
    for _ in range(n):
        x, y = rng.uniform(25, W - 25), rng.uniform(25, H - 25)
        amp = rng.uniform(400, 3000)
        data += amp * np.exp(-((xx - x) ** 2 + (yy - y) ** 2)
                             / (2 * SIGMA ** 2))
    data += rng.normal(0.0, 2.0, (H, W))
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
