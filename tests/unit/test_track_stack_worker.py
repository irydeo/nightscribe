############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: track & stack worker helpers
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The worker's velocity seed, offline. It sampled +/- 30 s and divided by
two as if the baseline were two minutes, returning exactly HALF the real
rate (measured on 2025 UR: 15.25 instead of 30.6"/min)."""

import pytest

from nightscribe.gui.workers import _rate_pa


def test_rate_pa_is_not_halved():
    # a synthetic motion of exactly 1 arcsec/min towards +dec (PA 0)
    def motion(jd):
        minutes = (jd - 2460000.0) * 1440.0
        return (10.0, 20.0 + minutes * (1.0 / 3600.0))
    rate, pa = _rate_pa(motion, 2460000.0)
    assert rate == pytest.approx(1.0, abs=0.01)
    assert pa == pytest.approx(0.0, abs=0.1)


def test_rate_pa_pa_is_north_through_east():
    # 1 arcsec/min towards +RA only (PA 90) at dec 0
    def motion(jd):
        minutes = (jd - 2460000.0) * 1440.0
        return (10.0 + minutes * (1.0 / 3600.0), 0.0)
    rate, pa = _rate_pa(motion, 2460000.0)
    assert rate == pytest.approx(1.0, abs=0.01)
    assert pa == pytest.approx(90.0, abs=0.1)


def test_rate_pa_without_an_ephemeris_is_none():
    assert _rate_pa(lambda jd: None, 2460000.0) == (None, None)


# ------------------------------------------------- the brightness' centre

def _worker():
    # @return: a worker with no frames: the helpers under test are pure
    from nightscribe.gui.workers import TrackStackWorker
    return TrackStackWorker(["a.fits", "b.fits"], "2025 UR", 1)


def test_the_brightness_centre_prefers_the_measured_centroid():
    # The astrometric measurement already found the object on this very
    # stack: reusing its centroid puts the aperture on the light instead
    # of on the ephemeris, which can be a couple of pixels away. The box
    # origin is subtracted, because the stack's pixels are its own.
    from nightscribe.core import astrometry
    worker = _worker()
    sp = astrometry.AstrometryPoint(ra=1.0, dec=2.0, x=110.0, y=90.0)
    assert worker._object_centre(sp, (100.0, 100.0), (0, 0, 2048, 2048)) \
        == (110.0, 90.0)
    assert worker._object_centre(sp, None, (10, 20, 100, 100)) == (100.0, 70.0)


def test_the_brightness_centre_falls_back_to_the_ephemeris():
    # Without a measured position (the point was flagged, or the group had
    # no measurable stack) the ephemeris is the honest fallback, and the
    # flag on the point says so.
    from nightscribe.core import astrometry
    worker = _worker()
    nan = float("nan")
    sp = astrometry.AstrometryPoint(ra=nan, dec=nan, x=nan, y=nan)
    assert worker._object_centre(sp, (100.0, 200.0), (0, 0, 10, 10)) \
        == (100.0, 200.0)
    assert worker._object_centre(None, None, (0, 0, 10, 10)) is None


def test_the_aperture_follows_the_recipe_and_not_a_constant():
    # The recipe is the Fotometria tab's, and the rule is its own: the
    # observer's radii win, a hand edit wins over the seeing rule, and
    # only when they never touched them does the measured FWHM size the
    # aperture.
    from nightscribe.core import photometry
    worker = _worker()
    assert worker._radii({"rap": 5.0, "rin": 9.0, "rout": 14.0}, 3.0) \
        == (5.0, 9.0, 14.0)
    assert worker._radii({"rap": 5.0, "rin": 9.0, "rout": 14.0,
                          "seeing": True, "radii_manual": True}, 3.0) \
        == (5.0, 9.0, 14.0)
    assert worker._radii({"seeing": True}, 3.0) \
        == photometry.aperture_for_fwhm(3.0)
    # no recipe at all: the plate's own defaults, which is None
    assert worker._radii({}, 3.0) is None
