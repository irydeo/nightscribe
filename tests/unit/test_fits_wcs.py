############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: minimal FITS reader and TAN WCS
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import math

import numpy as np
import pytest

from nightscribe.core import fits_io, wcs


def _fits_bytes(cards_text, payload=b""):
    # Builds a minimal-but-legal FITS blob: padded header + padded data.
    cards = [line.encode("ascii").ljust(80)[:80]
             for line in cards_text.strip().splitlines()]
    cards.append(b"END".ljust(80))
    header = b"".join(cards)
    header += b" " * ((-len(header)) % 2880)
    payload += b"\0" * ((-len(payload)) % 2880)
    return header + payload


def _write(tmp_path, cards_text, payload=b"", name="test.fits"):
    path = tmp_path / name
    path.write_bytes(_fits_bytes(cards_text, payload))
    return path


BASE_CARDS = """
SIMPLE  =                    T / conforms to FITS standard
BITPIX  =                  -32 / array data type
NAXIS   =                    2 / number of array dimensions
NAXIS1  =                  100
NAXIS2  =                   80
CTYPE1  = 'RA---TAN'           / Right ascension, gnomonic projection
CTYPE2  = 'DEC--TAN'           / Declination, gnomonic projection
CRVAL1  =              187.705 / [deg] Coordinate value at reference point
CRVAL2  =               12.391 / [deg] Coordinate value at reference point
CRPIX1  =                 50.0 / Pixel coordinate of reference point
CRPIX2  =                 40.0 / Pixel coordinate of reference point
CDELT1  =              -0.0005 / [deg] Coordinate increment at reference point
CDELT2  =               0.0005 / [deg] Coordinate increment at reference point
OBSERVER= 'John / Jane Doe'    / observer names
"""


def test_read_float32_image(tmp_path):
    data = np.arange(8000, dtype=np.float32).reshape(80, 100)
    path = _write(tmp_path, BASE_CARDS, data.astype(">f4").tobytes())
    header, got = fits_io.read_fits(path)
    assert got.shape == (80, 100)
    assert got.dtype == np.float32
    assert got[7, 42] == pytest.approx(7 * 100 + 42)
    assert header["CRVAL1"] == pytest.approx(187.705)
    # strings keep slashes inside quotes, booleans and numbers are typed
    assert header["OBSERVER"] == "John / Jane Doe"
    assert header["SIMPLE"] is True


def test_read_uint16_camera_image(tmp_path):
    # typical camera file: BITPIX=16 with BZERO=32768 -> unsigned 16 bit
    raw = np.arange(2000, dtype=">i2").reshape(40, 50)
    cards = """
SIMPLE  =                    T
BITPIX  =                   16
NAXIS   =                    2
NAXIS1  =                   50
NAXIS2  =                   40
BSCALE  =                    1
BZERO   =                32768
"""
    path = _write(tmp_path, cards, raw.tobytes())
    _, got = fits_io.read_fits(path)
    assert got.shape == (40, 50)
    assert got[0, 0] == pytest.approx(32768.0)
    assert got[39, 49] == pytest.approx(1999 + 32768.0)


def test_rgb_collapse_and_cube_first_plane(tmp_path):
    rgb = np.stack([np.full((10, 20), 10.0, dtype=">f4"),
                    np.full((10, 20), 20.0, dtype=">f4"),
                    np.full((10, 20), 60.0, dtype=">f4")])
    cards_rgb = """
SIMPLE  =                    T
BITPIX  =                  -32
NAXIS   =                    3
NAXIS1  =                   20
NAXIS2  =                   10
NAXIS3  =                    3
"""
    path = _write(tmp_path, cards_rgb, rgb.astype(">f4").tobytes())
    _, got = fits_io.read_fits(path)
    assert got.shape == (10, 20)
    assert got[5, 5] == pytest.approx(30.0)
    cube = np.stack([np.full((6, 7), 1.0, dtype=">f4"),
                     np.full((6, 7), 2.0, dtype=">f4")] + [np.zeros((6, 7), dtype=">f4")] * 8)
    cards_cube = (cards_rgb.replace("NAXIS1  =                   20",
                                    "NAXIS1  =                    7")
                           .replace("NAXIS2  =                   10",
                                    "NAXIS2  =                    6")
                           .replace("NAXIS3  =                    3",
                                    "NAXIS3  =                   10"))
    path = _write(tmp_path, cards_cube, cube.astype(">f4").tobytes(),
                  name="cube.fits")
    _, got = fits_io.read_fits(path)
    assert got.shape == (6, 7)
    assert np.all(got == 1.0)


def test_skips_to_first_image_hdu(tmp_path):
    primary = _fits_bytes("""
SIMPLE  =                    T
BITPIX  =                    8
NAXIS   =                    0
""")  # header only, no data
    ext_data = np.full((4, 5), 7.0, dtype=">f4")
    ext = _fits_bytes("""
XTENSION= 'IMAGE   '
BITPIX  =                  -32
NAXIS   =                    2
NAXIS1  =                    5
NAXIS2  =                    4
PCOUNT  =                    0
GCOUNT  =                    1
""", ext_data.tobytes())
    path = tmp_path / "ext.fits"
    path.write_bytes(primary + ext)
    _, got = fits_io.read_fits(path)
    assert got.shape == (4, 5)
    assert np.all(got == 7.0)


def test_truncated_file_raises(tmp_path):
    path = tmp_path / "bad.fits"
    path.write_bytes(b"SIMPLE  " + b" " * 100)
    with pytest.raises(fits_io.FitsError):
        fits_io.read_fits(path)


def test_wcs_cdelt_crota_forms():
    base = {k: v for k, v in (
        ("NAXIS1", 100), ("NAXIS2", 80), ("CRVAL1", 187.705),
        ("CRVAL2", 12.391), ("CRPIX1", 50.0), ("CRPIX2", 40.0),
        ("CTYPE1", "RA---TAN"), ("CTYPE2", "DEC--TAN"))}
    # plain CDELT (no rotation)
    w = wcs.Wcs.from_header({**base, "CDELT1": -0.0005, "CDELT2": 0.0005})
    assert w.pixel_scale() == pytest.approx(1.8)
    assert w.rotation() == pytest.approx(0.0)
    assert not w.is_mirrored()
    # CROTA2 = 30 -> hips2fits rotation_angle 30
    w = wcs.Wcs.from_header({**base, "CDELT1": -0.0005, "CDELT2": 0.0005,
                             "CROTA2": 30.0})
    assert w.pixel_scale() == pytest.approx(1.8)
    assert w.rotation() == pytest.approx(30.0)
    # explicit CD matrix for the same 30 deg geometry
    c, s = math.cos(math.radians(30)), math.sin(math.radians(30))
    cd = [[-0.0005 * c, -0.0005 * s], [-0.0005 * s, 0.0005 * c]]
    w2 = wcs.Wcs.from_header({**base, "CD1_1": cd[0][0], "CD1_2": cd[0][1],
                              "CD2_1": cd[1][0], "CD2_2": cd[1][1]})
    assert w2.rotation() == pytest.approx(30.0)
    assert w2.pixel_scale() == pytest.approx(1.8)
    # PC + CDELT flavour (what hips2fits returns when rotated)
    w3 = wcs.Wcs.from_header({**base, "PC1_1": -c, "PC1_2": -s,
                              "PC2_1": -s, "PC2_2": c,
                              "CDELT1": 0.0005, "CDELT2": 0.0005})
    assert w3.rotation() == pytest.approx(30.0)
    # mirrored image (east to the right) is detected
    wm = wcs.Wcs.from_header({**base, "CDELT1": 0.0005, "CDELT2": 0.0005})
    assert wm.is_mirrored()


def test_wcs_roundtrip_and_center():
    header = {"NAXIS1": 200, "NAXIS2": 150, "CRVAL1": 10.0, "CRVAL2": -20.0,
              "CRPIX1": 1.0, "CRPIX2": 1.0, "CTYPE1": "RA---TAN-SIP",
              "CTYPE2": "DEC--TAN-SIP", "CDELT1": -0.001, "CDELT2": 0.001}
    w = wcs.Wcs.from_header(header)
    assert w is not None  # SIP suffix tolerated
    for px, py in ((0, 0), (199, 149), (99.5, 74.5), (33.3, 121.7)):
        ra, dec = w.pixel_to_sky(px, py)
        x, y = w.sky_to_pixel(ra, dec)
        assert x == pytest.approx(px, abs=1e-6)
        assert y == pytest.approx(py, abs=1e-6)
    # centre is the central pixel, not CRVAL (reference sits at corner 1,1)
    ra_c, dec_c = w.center()
    assert (ra_c, dec_c) != (10.0, -20.0)
    x, y = w.sky_to_pixel(ra_c, dec_c)
    assert x == pytest.approx(99.5)
    assert y == pytest.approx(74.5)


def test_wcs_missing_or_unsupported():
    assert wcs.Wcs.from_header({"NAXIS1": 10, "NAXIS2": 10}) is None
    assert wcs.Wcs.from_header({
        "NAXIS1": 10, "NAXIS2": 10, "CRVAL1": 0, "CRVAL2": 0,
        "CRPIX1": 5, "CRPIX2": 5, "CTYPE1": "RA---SIN",
        "CTYPE2": "DEC--SIN", "CDELT1": 0.001, "CDELT2": 0.001}) is None


def test_wcs_flipped_x():
    # a mirrored solve (det > 0, east to the right) becomes alignable after
    # flipping the image horizontally (ADR-018)
    w = wcs.Wcs.from_header({"NAXIS1": 2047, "NAXIS2": 2047,
                             "CRVAL1": 301.2674, "CRVAL2": 62.7787,
                             "CRPIX1": 1198.46, "CRPIX2": 1320.94,
                             "CTYPE1": "RA---TAN-SIP", "CTYPE2": "DEC--TAN-SIP",
                             "CD1_1": 0.000295924, "CD1_2": -1.2579e-05,
                             "CD2_1": 1.2569e-05, "CD2_2": 0.000295836})
    assert w.is_mirrored()
    wf = w.flipped_x()
    assert not wf.is_mirrored()
    # the flip is a pure view change: pixel (x, y) of the original and pixel
    # (W-1-x, y) of the flipped image show the same sky position
    for x, y in ((0, 0), (2046, 2046), (1023, 500), (100, 2000)):
        ra0, dec0 = w.pixel_to_sky(x, y)
        ra1, dec1 = wf.pixel_to_sky(2046 - x, y)
        assert ra1 == pytest.approx(ra0, abs=1e-9)
        assert dec1 == pytest.approx(dec0, abs=1e-9)
    # scale and centre survive untouched
    assert wf.pixel_scale() == pytest.approx(w.pixel_scale())
    assert wf.center() == pytest.approx(w.center())


def test_wcs_scaled():
    w = wcs.Wcs.from_header({"NAXIS1": 200, "NAXIS2": 100, "CRVAL1": 50.0,
                             "CRVAL2": 30.0, "CRPIX1": 101.0, "CRPIX2": 51.0,
                             "CTYPE1": "RA---TAN", "CTYPE2": "DEC--TAN",
                             "CDELT1": -0.001, "CDELT2": 0.001})
    w2 = w.scaled(2.0)
    assert w2.naxis1 == 100 and w2.naxis2 == 50
    assert w2.pixel_scale() == pytest.approx(7.2)
    # the same sky position lands at the binned pixel: (x+0.5)/k - 0.5
    ra, dec = w.pixel_to_sky(150.0, 70.0)
    x2, y2 = w2.sky_to_pixel(ra, dec)
    assert x2 == pytest.approx(74.75, abs=1e-9)
    assert y2 == pytest.approx(34.75, abs=1e-9)
