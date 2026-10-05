############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: recovering a visit's second run (P0)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""A visit that mixes two runs must not lose half its frames.

Measured on the real 2025 UR visit: its two runs are 884 px and 0.12 deg
apart, the translation-only fit leaves 1.5 px of residual (rejected), the
rigid fit leaves 0.80 px (accepted on a 3.56 px PSF), and the old absolute
0.75 px gate threw 62 of the 140 frames away. Recovering them took the
star stack's SNR from 1826 to 2702 (x1.48) on that same data.

These tests pin the four pieces that make that work, all offline and
synthetic: the residual gate follows the session's FWHM, the correlation
fallback cannot certify a rotation, a rotated run is recovered on the
second attempt, and the report says WHAT happened (how many came back, how,
and whether the visit is really two runs).
"""

import math

import numpy as np
import pytest
from astropy.io import fits

from nightscribe.core import register as reg
from nightscribe.core import track_stack as ts

SIZE = 220
SIGMA = 1.6


def _write(path, data):
    fits.PrimaryHDU(np.asarray(data, dtype=np.int16)).writeto(str(path),
                                                              overwrite=True)
    return str(path)


def _field(seed=1, size=SIZE, n=30):
    rng = np.random.default_rng(seed)
    img = rng.normal(1000.0, 3.0, (size, size))
    yy, xx = np.mgrid[0:size, 0:size]
    for _ in range(n):
        x, y = rng.uniform(20, size - 20), rng.uniform(20, size - 20)
        amp = rng.uniform(1500.0, 6000.0)
        img += amp * np.exp(-((xx - x) ** 2 + (yy - y) ** 2)
                            / (2 * SIGMA ** 2))
    return img


def _wcs(size=SIZE):
    from astropy.wcs import WCS
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [10.0, 20.0]
    w.wcs.crpix = [size / 2.0 + 0.5, size / 2.0 + 0.5]
    w.wcs.cd = [[-2.0 / 3600, 0.0], [0.0, 2.0 / 3600]]
    w.pixel_shape = (size, size)
    return w


def _two_runs(tmp_path, n1=6, n2=6, dx=-40.0, dy=18.0, angle_deg=1.0):
    # @return: (paths, the second run's offset). Run 1 jitters a couple of
    #          pixels; run 2 is a re-point: shifted AND turned, which is
    #          exactly what a translation alone cannot fit.
    base = _field(seed=7)
    paths = []
    for i in range(n1):
        img = np.roll(base, (i % 3 - 1, i % 2 - 1), axis=(0, 1))
        paths.append(_write(tmp_path / f"a{i:02d}.fits", img))
    ang = math.radians(angle_deg)
    for i in range(n2):
        img = reg.apply_transform(base, ang, dx, dy)
        img = np.roll(img, (i % 3 - 1, i % 2 - 1), axis=(0, 1))
        paths.append(_write(tmp_path / f"b{i:02d}.fits", img))
    return paths, (dx, dy)


def _register(paths):
    frames = ts.load_sequence(paths)
    frames[0].wcs = _wcs()
    ts.register_sequence(frames)
    return frames


# ------------------------------------------------------------- the gate

def test_the_residual_gate_follows_the_session_fwhm():
    # A misregistration broadens the stacked PSF in PROPORTION to the
    # seeing, so the gate is a fraction of the FWHM, not a fixed pixel
    # figure: 0.8 px is harmless on 3.5 px seeing and a lot on 1.2 px.
    assert reg.rms_limit(None) == reg.MAX_RMS_PX          # no FWHM: fallback
    assert reg.rms_limit(3.56) == pytest.approx(0.89, abs=0.01)
    assert reg.rms_limit(1.2) == reg.MIN_RMS_PX           # floored
    tr = {"n": 20, "rms_px": 0.80, "quality": 0.0}
    assert reg.trusted(tr) is False                       # the old absolute
    assert reg.trusted(tr, 3.56) is True                  # 0.80 < 0.89


def test_the_correlation_fallback_cannot_certify_a_rotation():
    # Measured on 2025 UR: a frame whose star voting failed (n=0) was then
    # handed a -106 deg rotation certified by TWO paired stars and a
    # correlation of 635. The fallback says "these are the same sky",
    # never "this is the mapping": two stars cannot certify a rotation.
    tr = {"n": 2, "rms_px": 0.29, "quality": 635.0, "angle_deg": -106.6}
    assert reg.trusted(tr, 3.56) is True                  # the fallback
    assert reg.trusted(tr, 3.56, require_stars=True) is False


# --------------------------------------------------------- the recovery

def test_a_rotated_second_run_is_recovered(tmp_path):
    paths, _ = _two_runs(tmp_path)
    frames = _register(paths)
    assert all(not f.failed_register for f in frames)
    notes = [f.register_note for f in frames]
    assert notes.count("rotation") >= 1
    report = ts.registration_report(frames)
    assert report["n_ok"] == len(paths)
    assert report["n_failed"] == 0
    assert report["n_rotation"] >= 1


def test_the_report_finds_the_two_runs(tmp_path):
    # The point of the report: a visit that is really two runs has to say
    # so, with the offset and the gap, instead of "N frames were left out".
    paths, (dx, dy) = _two_runs(tmp_path, n1=6, n2=6)
    frames = _register(paths)
    report = ts.registration_report(frames)
    assert report["multi_run"] is True
    assert len(report["blocks"]) == 2
    assert report["blocks"][0]["n"] == 6
    assert report["blocks"][1]["n"] == 6
    second = report["blocks"][1]
    # estimate_transform returns the INVERSE of apply_transform (the same
    # convention the sibling test above pins: the angle comes back
    # negated), so the distance between the runs is what is compared
    assert math.hypot(second["dx"], second["dy"]) == pytest.approx(
        math.hypot(dx, dy), abs=3.0)
    # _two_runs turns the second run by 1.0 deg (its default), and the
    # inverse convention makes the recovered angle negative
    assert second["angle_deg"] == pytest.approx(-1.0, abs=0.3)


def test_a_single_run_is_one_block(tmp_path):
    base = _field(seed=3)
    paths = [_write(tmp_path / f"f{i:02d}.fits",
                    np.roll(base, (i % 3 - 1, i % 2 - 1), axis=(0, 1)))
             for i in range(6)]
    frames = _register(paths)
    report = ts.registration_report(frames)
    assert report["multi_run"] is False
    assert len(report["blocks"]) == 1
    assert report["blocks"][0]["n"] == 6


def test_a_frame_that_cannot_be_aligned_says_why(tmp_path):
    # A bad frame (a cloud, a satellite) is dropped, and the report says
    # the reason: "too few stars" and "the stars disagree" need different
    # fixes, so a bare count teaches nothing.
    paths, _ = _two_runs(tmp_path, n1=6, n2=0)
    rng = np.random.default_rng(11)
    junk = _write(tmp_path / "junk.fits", rng.normal(1000.0, 300.0,
                                                     (SIZE, SIZE)))
    paths.append(junk)
    frames = _register(paths)
    report = ts.registration_report(frames)
    assert report["n_failed"] >= 1
    assert report["reasons"]
    assert report["n_ok"] + report["n_failed"] == len(paths)
