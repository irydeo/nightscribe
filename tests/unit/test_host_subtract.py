############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: host-galaxy subtraction (H2b)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen checks for core/host_subtract.py: the reference is registered
to the frame (not trusted to the WCS), the survey's masked pixels are
excluded and never painted black, and the target survives the subtraction.
No network, no Qt.
"""

import numpy as np
import pytest

from nightscribe.core import host_subtract, photometry, register

SHAPE = (180, 180)
SIGMA = 3.0
TARGET = (90.0, 90.0)
# enough stars for the registration's star vote (register.MIN_MATCH is 6)
COMPS = [(30, 30), (150, 30), (30, 150), (150, 150), (90, 25), (25, 90),
         (155, 90), (90, 155), (60, 60), (120, 60), (60, 120), (120, 120)]


def _field(positions, amp=1200.0, sky=500.0, seed=7):
    # @return: a synthetic plate: flat sky + gaussians at the positions
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:SHAPE[0], 0:SHAPE[1]]
    img = np.full(SHAPE, sky) + rng.normal(0.0, 1.0, SHAPE)
    for cx, cy in positions:
        img += amp * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2)
                            / (2 * SIGMA ** 2))
    return img


def _shift(img, dx, dy):
    # A reference that is off by a subpixel shift: the real-world case the
    # WCS-only path could not fix (SIP ignored, hips2fits rounding)
    return register.apply_transform(img, 0.0, dx, dy)


def test_align_reference_lands_the_shifted_reference_on_the_frame():
    obs = _field(COMPS + [TARGET])
    ref = _field(COMPS)
    shifted = _shift(ref, 0.8, -0.5)
    warped, valid, tr = host_subtract.align_reference(obs, shifted)
    assert warped.shape == obs.shape and valid.any()
    # the registered reference is closer to the frame than the raw one
    assert np.nanstd(obs - warped) < np.nanstd(obs - shifted)


def test_align_reference_handles_a_scale_mismatch():
    # The survey cutout's pixel scale is not the frame's (the real case:
    # ~0.15 %): a rigid fit leaves the stars off by more and more toward
    # the edges; the similarity absorbs it.
    obs = _field(COMPS + [TARGET])
    ref = _field(COMPS)
    scaled = register.apply_transform(ref, 0.0, 0.0, 0.0, scale=0.99)
    warped, valid, tr = host_subtract.align_reference(obs, scaled)
    assert tr["scale"] == pytest.approx(1.0 / 0.99, abs=0.004)
    # the warp fills the out-of-frame corners with zeros: compare only the
    # pixels that carry real reference data
    assert np.nanstd((obs - warped)[valid]) \
        < np.nanstd((obs - scaled)[valid])


def test_subtract_masks_the_survey_holes_and_keeps_the_target():
    obs = _field(COMPS + [TARGET])
    ref = _field(COMPS)
    shifted = _shift(ref, 0.6, 0.3)
    # a survey mask on a comp's core: PanSTARRS saturations arrive as NaN
    shifted[28:34, 28:34] = np.nan
    comp_xy = [(float(x), float(y)) for x, y in COMPS]
    res = host_subtract.subtract(obs, shifted, comp_xy)
    assert res["diff"] is not None and res["gain"] > 0.0
    # the hole is excluded (NaN), never a black pixel, and counted
    assert np.isnan(res["diff"][31, 31])
    assert res["masked"] >= 36
    # the target survives the subtraction and reads a positive flux
    m = photometry.measure_point(res["diff"], *TARGET)
    assert m["ok"] and m["flux"] > 0.0


def test_subtract_without_comps_has_no_star_gain():
    # No comparison stars: no star scale. The subtraction can still run from
    # the host's own scale when there is an extended host (ADR-073), so the
    # point here is that `used` and the star gain are empty, not that the
    # difference is.
    obs = _field(COMPS + [TARGET])
    ref = _field(COMPS)
    res = host_subtract.subtract(obs, ref, [])
    assert res["used"] == 0
    assert res["star_gain"] is None


def test_subtract_scales_the_reference_so_the_comps_vanish():
    # the survey is a different filter/epoch: a constant flux scale must
    # absorb it, or every comp would survive as a residual
    obs = _field(COMPS + [TARGET], amp=1200.0)
    ref = _field(COMPS, amp=3000.0)          # 2.5x brighter survey
    comp_xy = [(float(x), float(y)) for x, y in COMPS]
    res = host_subtract.subtract(obs, ref, comp_xy)
    assert res["gain"] == pytest.approx(0.4, rel=0.15)
    # the comps' own residual on the difference is a small fraction of
    # their flux on the frame (they were scaled away, not left behind)
    comp = photometry.measure_point(res["diff"], *COMPS[0])
    frame = photometry.measure_point(obs, *COMPS[0])
    assert abs(comp["flux"]) < 0.1 * frame["flux"]
