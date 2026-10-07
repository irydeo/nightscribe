############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: track & stack ingestion (ADR-062)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Phase 2 acceptance: T_mid is the middle of the exposure, the reference
WCS comes from the header when the frame is already solved, the
registration recovers a known shift, the composed WCS lands the reference
pixel where the transform says, the object is evaluated at each frame's
own instant, and the dither warning fires on a sequence that never moved.
All offline: no solver, no Horizons."""

import math

import numpy as np
import pytest
from astropy.io import fits
from astropy.wcs import WCS

from nightscribe.core import track_stack as ts

CD = [[-0.000296, 0.0], [0.0, 0.000296]]      # ~1.07 "/px, north up


def _wcs_header(naxis=64, crval=(30.0, 10.0)):
    hdu = fits.PrimaryHDU(np.zeros((naxis, naxis), dtype=np.int16))
    h = hdu.header
    h["CTYPE1"], h["CTYPE2"] = "RA---TAN", "DEC--TAN"
    h["CRVAL1"], h["CRVAL2"] = crval
    h["CRPIX1"], h["CRPIX2"] = (naxis + 1) / 2, (naxis + 1) / 2
    h["CD1_1"], h["CD1_2"] = CD[0][0], CD[0][1]
    h["CD2_1"], h["CD2_2"] = CD[1][0], CD[1][1]
    h["RADESYS"], h["EQUINOX"] = "ICRS", 2000.0
    h["DATE-OBS"] = "2026-08-16T22:25:18.000"
    h["EXPTIME"] = 5.0
    h["FILTER"] = "Clear"
    return hdu


def _star_field(naxis=64, seed=1):
    rng = np.random.default_rng(seed)
    img = rng.normal(1000.0, 5.0, (naxis, naxis))
    for _ in range(25):
        x = rng.uniform(6, naxis - 6)
        y = rng.uniform(6, naxis - 6)
        yy, xx = np.mgrid[0:naxis, 0:naxis]
        img += 3000.0 * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * 1.5 ** 2))
    return img


def _write(path, data, header=None, **cards):
    hdu = fits.PrimaryHDU(np.asarray(data, dtype=np.int16))
    if header is not None:
        for k, v in header.items():
            if k not in ("SIMPLE", "BITPIX", "NAXIS", "NAXIS1", "NAXIS2",
                         "EXTEND"):
                hdu.header[k] = v
    for k, v in cards.items():
        hdu.header[k.replace("__", "-")] = v
    hdu.writeto(str(path), overwrite=True)
    return str(path)


# ------------------------------------------------------------------ T_mid

def test_t_mid_is_the_middle_of_the_exposure(tmp_path):
    path = _write(tmp_path / "a.fits", np.zeros((8, 8), dtype=np.int16),
                  DATE__OBS="2026-08-16T22:25:18.000", EXPTIME=5.0,
                  FILTER="Clear")
    frames = ts.load_sequence([path])
    assert len(frames) == 1
    f = frames[0]
    assert f.exptime_s == 5.0 and f.filter == "Clear"
    # half of a 5 s exposure = 2.5 s. The difference is taken in seconds:
    # a day is 86400 s and the JD is ~2.5e6, so comparing the tiny day
    # fraction directly would drown in the float64 representation error.
    assert (f.t_mid_jd - f.jd_start) * 86400.0 == pytest.approx(2.5, abs=1e-3)


def test_load_sequence_sorts_by_time(tmp_path):
    a = _write(tmp_path / "a.fits", np.zeros((8, 8), dtype=np.int16),
               DATE__OBS="2026-08-16T22:30:00", EXPTIME=5.0)
    b = _write(tmp_path / "b.fits", np.zeros((8, 8), dtype=np.int16),
               DATE__OBS="2026-08-16T22:20:00", EXPTIME=5.0)
    frames = ts.load_sequence([a, b])
    assert [f.path for f in frames] == [b, a]


# --------------------------------------------------------- solve reference

def test_a_frame_that_cannot_be_read_is_left_out_not_fatal(tmp_path):
    # A real capture ends with a half-written file (the author's own 2025
    # FG18 visit ends with a 0-byte frame). One of those used to take the
    # whole visit down: the exception came out of load_sequence and the
    # Astrometry tab never armed. It is SKIPPED now, and the caller can tell
    # how many were left out by comparing with what it handed over.
    good = _write(tmp_path / "good.fits", np.zeros((8, 8), dtype=np.int16),
                  DATE__OBS="2026-10-06T22:00:00", EXPTIME=5.0)
    empty = tmp_path / "half_written.fits"
    empty.write_bytes(b"")
    frames = ts.load_sequence([good, str(empty)])
    assert len(frames) == 1
    assert frames[0].path == good
    # and a visit where NOTHING can be read is an empty sequence, not a crash
    assert ts.load_sequence([str(empty)]) == []


def test_solve_reference_reads_a_solved_header(tmp_path):
    hdu = _wcs_header()
    path = str(tmp_path / "solved.fits")
    hdu.writeto(path)
    frames = ts.load_sequence([path])
    ref, wcs = ts.solve_reference(frames)
    assert ref is frames[0] and wcs is not None
    # the reference WCS maps its own CRPIX back to CRVAL
    ra, dec = wcs.all_pix2world([[31.5, 31.5]], 0)[0]
    assert ra == pytest.approx(30.0, abs=1e-6)
    assert dec == pytest.approx(10.0, abs=1e-6)


# ---------------------------------------------------------- registration

def test_register_recovers_a_known_shift(tmp_path):
    from scipy import ndimage
    base = _star_field()
    hdu = _wcs_header()
    ref_path = str(tmp_path / "ref.fits")
    hdu.data = base.astype(np.int16)
    hdu.writeto(ref_path, overwrite=True)
    # a frame whose content moved: ndimage.shift takes (dy, dx), so this
    # moves the stars by dx = -2, dy = +3
    moved = ndimage.shift(base, (3.0, -2.0), order=3, mode="nearest")
    path = _write(tmp_path / "moved.fits", moved, header=dict(hdu.header))
    frames = ts.load_sequence([ref_path, path])
    ref, _wcs = ts.solve_reference(frames)
    ts.register_sequence(frames)
    # whichever frame became the grid, the OTHER one carries the shift
    other = frames[0] if frames[1] is ref else frames[1]
    tr = other.transform
    # apply_transform lands the frame on the reference grid, so it undoes
    # the content move: (dx, dy) = (-2, +3)
    assert tr is not None and not other.failed_register
    assert tr["dx"] == pytest.approx(-2.0, abs=1.0)
    assert tr["dy"] == pytest.approx(3.0, abs=1.0)


def test_compose_wcs_moves_the_reference_pixel(tmp_path):
    hdu = _wcs_header()
    path = str(tmp_path / "ref.fits")
    hdu.writeto(path)
    frames = ts.load_sequence([path])
    ref, w0 = ts.solve_reference(frames)
    tr = {"angle": 0.0, "dx": 2.0, "dy": 3.0, "quality": 100.0, "rms_px": 0.0}
    w = ts.compose_wcs(w0, tr, shape=(64, 64))
    # with no rotation, the composed CRPIX is the reference one shifted
    assert w.wcs.crpix[0] == pytest.approx(w0.wcs.crpix[0] + 2.0, abs=1e-6)
    assert w.wcs.crpix[1] == pytest.approx(w0.wcs.crpix[1] + 3.0, abs=1e-6)
    assert np.allclose(w.wcs.cd, w0.wcs.cd, atol=1e-12)


def test_compose_wcs_rotation_keeps_the_scale(tmp_path):
    hdu = _wcs_header()
    path = str(tmp_path / "ref.fits")
    hdu.writeto(path)
    frames = ts.load_sequence([path])
    _ref, w0 = ts.solve_reference(frames)
    w = ts.compose_wcs(w0, {"angle": math.radians(30.0), "dx": 0.0, "dy": 0.0,
                            "quality": 100.0, "rms_px": 0.0}, shape=(64, 64))
    assert ts._arcsec_per_pixel(w) == pytest.approx(
        ts._arcsec_per_pixel(w0), rel=1e-9)


# ------------------------------------------------------------- positions

def test_object_positions_follow_the_motion(tmp_path):
    hdu = _wcs_header()
    path = str(tmp_path / "ref.fits")
    hdu.writeto(path)
    frames = ts.load_sequence([path])
    _ref, w0 = ts.solve_reference(frames)

    def motion(jd):
        return (30.0 + (jd % 1.0) * 0.01, 10.0)
    ts.object_positions(frames, motion)
    f = frames[0]
    assert f.object_xy is not None
    x, y = w0.all_world2pix([[f.object_ra, f.object_dec]], 0)[0]
    assert f.object_xy[0] == pytest.approx(x, abs=1e-6)
    assert f.object_xy[1] == pytest.approx(y, abs=1e-6)


# ---------------------------------------------------------------- dither

def _frame_with_shift(dx, dy):
    f = ts.Frame(path="x")
    f.transform = {"angle": 0.0, "dx": dx, "dy": dy, "quality": 100.0}
    return f


def test_dither_check_warns_when_nothing_moved():
    frames = [_frame_with_shift(0.3 * i % 1.0, 0.2 * i % 1.0) for i in range(6)]
    report = ts.dither_check(frames)
    assert report.dithered is False and "not dithered" in report.note


def test_dither_check_passes_when_the_observer_moved():
    frames = [_frame_with_shift(20.0 * i, -15.0 * i) for i in range(6)]
    report = ts.dither_check(frames)
    assert report.dithered is True and report.spread_px > 5.0
