############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: astrometric measurement (ADR-062, phase 4)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Phase 4 acceptance: the subpixel centroid, the inverse-variance
combination (with the RA weighted by cos(dec)), the contrast of the two
paths, the honest error budget and the magnitude that is omitted when it
cannot be calibrated. Offline and synthetic."""

import math

import numpy as np
import pytest
from astropy.wcs import WCS

from nightscribe.core import astrometry as ast

CD = [[-0.000296, 0.0], [0.0, 0.000296]]


def _wcs(crval=(30.0, 10.0), naxis=128):
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = list(crval)
    w.wcs.crpix = [(naxis + 1) / 2, (naxis + 1) / 2]
    w.wcs.cd = np.asarray(CD)
    w.wcs.radesys = "ICRS"
    w.wcs.equinox = 2000.0
    return w


def _gaussian(size=41, x=20.3, y=18.7, amp=2000.0, fwhm=3.0, noise=5.0,
              seed=2):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:size, 0:size]
    sigma = fwhm / 2.355
    img = rng.normal(1000.0, noise, (size, size))
    img += amp * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * sigma ** 2))
    return img.astype(np.float32)


# ---------------------------------------------------------------- centroid

def test_centroid_recovers_a_subpixel_centre():
    img = _gaussian(x=20.3, y=18.7)
    c = ast.centroid(img, (20.0, 19.0), fwhm=3.0)
    assert c.ok
    assert c.x == pytest.approx(20.3, abs=0.15)
    assert c.y == pytest.approx(18.7, abs=0.15)
    assert c.snr > 50.0
    assert c.roundness > 0.85


def test_centroid_refuses_a_source_on_the_edge():
    img = _gaussian(x=1.0, y=1.0)
    c = ast.centroid(img, (1.0, 1.0), fwhm=3.0)
    assert not c.ok


def test_centroid_error_grows_with_noise():
    quiet = ast.centroid(_gaussian(noise=3.0), (20.0, 19.0), fwhm=3.0)
    noisy = ast.centroid(_gaussian(noise=40.0), (20.0, 19.0), fwhm=3.0)
    assert noisy.err_pix > quiet.err_pix


# ------------------------------------------------------------- combination

def _point(x, y, err, scale=1.0):
    class _C:
        err_pix = err
        snr = 10.0
        roundness = 1.0
        fwhm = 3.0
    return (x, y, _C(), scale)


def test_combine_positions_weights_by_the_inverse_variance():
    # two positions, one four times better: the mean sits near it
    pts = [_point(10.0, 20.0, 0.1), _point(11.0, 20.0, 0.4)]
    ra, dec, scatter = ast.combine_positions(pts)
    assert ra == pytest.approx(10.06, abs=0.05)
    assert dec == pytest.approx(20.0, abs=0.05)


def test_combine_positions_reports_the_observed_scatter():
    # nine points that agree to a hundredth of an arcsec: the scatter is
    # tiny (the error of the mean is computed apart, in measure_frames)
    same = ast.combine_positions([_point(10.0, 20.0, 0.2) for _ in range(9)])
    assert same[2][0] < 0.01 and same[2][1] < 0.01
    assert same[0] == pytest.approx(10.0, abs=1e-6)
    # and points that really differ show it
    spread = ast.combine_positions([_point(10.0, 20.0, 0.2),
                                    _point(10.0 + 2.0 / 3600.0, 20.0, 0.2)])
    assert spread[2][0] == pytest.approx(1.0, abs=0.3)   # arcsec


# ------------------------------------------------------------------ error

def test_error_budget_total_is_at_least_its_parts():
    rms_ra, rms_dec, parts = ast.error_budget(
        0.2, None, 10.0, 1.07, wcs_rms_arcsec=0.1, velocity_arcsec_min=30.0,
        sigma_t_s=1.0)
    assert rms_dec >= parts["centroid_arcsec"]
    assert rms_ra >= parts["centroid_arcsec"]
    assert parts["timing_arcsec"] > 0


def test_error_budget_ra_grows_with_declination():
    low = ast.error_budget(0.2, None, 0.0, 1.07)[0]
    high = ast.error_budget(0.2, None, 80.0, 1.07)[0]
    assert high > low * 3.0      # 1/cos(80) ~ 5.8


# -------------------------------------------------------------- measure

def test_measure_stack_maps_to_sky():
    img = _gaussian(x=20.3, y=18.7)
    wcs = _wcs()
    pt = ast.measure_stack(img, (20.0, 19.0), wcs, mjd=61268.9)
    x, y = wcs.all_world2pix([[pt.ra, pt.dec]], 0)[0]
    assert x == pytest.approx(pt.x, abs=1e-3)
    assert y == pytest.approx(pt.y, abs=1e-3)
    assert pt.source == "stack" and pt.snr > 20


def test_measure_groups_gives_the_loader_only_to_the_per_frame_path():
    # The worker passes loader=<the calibrating loader> (P5b). It belongs to
    # the PER-FRAME path, which reads pixels; measure_stack measures the
    # already-combined image and never reads. Forwarding it blindly to both
    # raised "measure_stack() got an unexpected keyword argument 'loader'"
    # and killed every calibrated run at the measurement step.
    from nightscribe.core import track_stack
    stack = _gaussian(x=20.3, y=18.7, size=41)
    wcs = _wcs()
    calls = []

    def loader(path, box):
        calls.append((path, box))
        w, h = box[2] - box[0], box[3] - box[1]
        yy, xx = np.mgrid[0:h, 0:w]
        img = np.full((h, w), 1000.0, dtype=np.float32)
        img += 2000.0 * np.exp(-((xx - 12.0) ** 2 + (yy - 12.0) ** 2)
                               / (2 * (3.0 / 2.355) ** 2))
        return img

    frame = track_stack.Frame(path="frame0.fits")
    frame.wcs = wcs
    frame.object_xy = (20.0, 19.0)
    out = ast.measure_groups(
        [stack], [(20.0, 19.0)], wcs, frames=[frame], groups=[(0, 1)],
        mjd_by_group=[61268.9], loader=loader, fwhm=3.0)
    assert len(out) == 1
    sp, fp, _flags = out[0]
    assert sp.source == "stack" and sp.snr > 20
    assert fp is not None and fp.source == "frames"
    assert calls and calls[0][0] == "frame0.fits"     # the loader was used
    assert "disagree" not in sp.flags                 # the two paths agree


def test_compare_flags_a_disagreement():
    good = ast.AstrometryPoint(ra=30.0, dec=10.0, rms_ra=0.1, rms_dec=0.1)
    same = ast.AstrometryPoint(ra=30.0, dec=10.0, rms_ra=0.1, rms_dec=0.1)
    far = ast.AstrometryPoint(ra=30.0 + 2.0 / 3600.0, dec=10.0,
                              rms_ra=0.1, rms_dec=0.1)
    assert ast.compare(good, same) == []
    assert ast.compare(good, far) == ["disagree"]


def test_compare_ignores_a_missing_frame_point():
    good = ast.AstrometryPoint(ra=30.0, dec=10.0)
    missing = ast.AstrometryPoint(ra=float("nan"), dec=float("nan"))
    assert ast.compare(good, missing) == []


def test_magnitude_is_omitted_without_calibration():
    img = _gaussian()
    wcs = _wcs()
    assert ast.measure_magnitude(img, (20.0, 19.0), wcs) is None


def test_magnitude_with_a_zero_point():
    img = _gaussian(amp=2000.0)
    wcs = _wcs()
    got = ast.measure_magnitude(img, (20.0, 19.0), wcs, zp=25.0)
    assert got is not None
    mag, band, n = got
    assert 5.0 < mag < 25.0 and n == 0
