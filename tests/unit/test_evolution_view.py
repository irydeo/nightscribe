############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: SN evolution animation (Track B, B6)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import os
import math

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nightscribe.viz.evolution_view import (
    align_frame, _compute_affine, _date_label,
    make_evolution_gif, make_evolution_video,
)
from nightscribe.core.wcs import Wcs


# ---------------- helpers: synthetic WCS + frames ----------------

def _make_wcs(ra=100.0, dec=20.0, scale=0.5, rot=0.0, w=200, h=200):
    # @args: scale - arcsec/pixel, rot - rotation deg
    # @return: a Wcs with a TAN projection at the given centre
    cdelt = scale / 3600.0
    rot_r = math.radians(rot)
    cd = [[cdelt * math.cos(rot_r), -cdelt * math.sin(rot_r)],
          [cdelt * math.sin(rot_r), cdelt * math.cos(rot_r)]]
    return Wcs(ra, dec, w / 2.0 + 0.5, h / 2.0 + 0.5, cd, w, h)


def _make_frame_data(w, h, star_pos, flux=5000.0, sky=100.0):
    # @args: star_pos - (x, y), flux - peak value
    # @return: 2D numpy array with a Gaussian PSF star
    data = np.full((h, w), sky, dtype=np.float32)
    yy, xx = np.ogrid[:h, :w]
    x, y = star_pos
    data += flux * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * 3 ** 2))
    return data


# ---------------- affine alignment ----------------

def test_compute_affine_identity():
    # Same WCS → near-identity transform (gnomonic curvature adds
    # a tiny error; we tolerate it at the 1e-4 level, not 1e-6)
    wcs = _make_wcs()
    a, b, c, d, e, f = _compute_affine(wcs, wcs)
    assert abs(a - 1.0) < 1e-4 and abs(b) < 1e-4
    assert abs(d) < 1e-4 and abs(e - 1.0) < 1e-4


def test_compute_affine_translation():
    # Shifted WCS → translation in the affine (a≈1, c≈pixel offset)
    wcs_ref = _make_wcs(ra=100.0, dec=20.0)
    wcs_shift = _make_wcs(ra=100.01, dec=20.0)   # ~0.01° shift
    a, b, c, d, e, f = _compute_affine(wcs_shift, wcs_ref)
    assert abs(a - 1.0) < 0.01
    assert abs(e - 1.0) < 0.01


def test_align_frame_basic():
    wcs = _make_wcs()
    data = _make_frame_data(200, 200, (100, 100))
    img8, sn = align_frame(data, wcs, wcs, (100, 100))
    assert img8.shape[0] <= 256   # crop cap
    assert img8.dtype == np.uint8


def test_align_frame_no_wcs():
    # Frame without WCS: no warp, just stretch+crop
    data = _make_frame_data(200, 200, (100, 100))
    img8, sn = align_frame(data, None, None, (100, 100))
    assert img8.dtype == np.uint8
    assert sn is not None


def test_align_frame_different_scale():
    # Frame with 2x scale → affine warps it to match the reference
    wcs_ref = _make_wcs(scale=0.5)
    wcs_frame = _make_wcs(scale=1.0)
    data = _make_frame_data(200, 200, (100, 100))
    img8, sn = align_frame(data, wcs_frame, wcs_ref, (100, 100))
    assert img8.dtype == np.uint8


# ---------------- date label ----------------

def test_date_label_es():
    # MJD 60600.0 → 2026-09-09ish; just check format
    lbl = _date_label(60600.0, lang="es")
    assert "/" in lbl   # dd/mm/YYYY
    assert lbl


def test_date_label_en():
    lbl = _date_label(60600.0, lang="en")
    assert "-" in lbl   # YYYY-MM-DD


def test_date_label_none():
    assert _date_label(None) == ""


# ---------------- GIF / MP4 output ----------------

def test_make_evolution_gif(tmp_path):
    # Build 3 synthetic aligned frames and write a GIF
    frames_data = []
    for i in range(3):
        data = _make_frame_data(200, 200, (100, 100), flux=5000 - i * 500)
        img8, sn = align_frame(data, _make_wcs(), _make_wcs(), (100, 100))
        frames_data.append((img8, sn))
    out = tmp_path / "evo.gif"
    result = make_evolution_gif(
        frames_data, dates=["2026-09-08", "2026-09-10", "2026-09-12"],
        sn_xy_s=[(100, 100)] * 3, out=str(out), names=["SN2026abc"] * 3)
    assert result is not None
    assert out.exists()
    assert out.stat().st_size > 1000


def test_make_evolution_video(tmp_path):
    frames_data = []
    for i in range(3):
        data = _make_frame_data(200, 200, (100, 100), flux=5000 - i * 500)
        img8, sn = align_frame(data, _make_wcs(), _make_wcs(), (100, 100))
        frames_data.append((img8, sn))
    out = tmp_path / "evo.mp4"
    result = make_evolution_video(
        frames_data, dates=["2026-09-08", "2026-09-10", "2026-09-12"],
        sn_xy_s=[(100, 100)] * 3, out=str(out), names=["SN2026abc"] * 3)
    assert result is not None
    assert out.exists()


def test_make_evolution_gif_empty():
    # No frames → returns None, does not crash
    assert make_evolution_gif([], [], [], "/dev/null.gif") is None


def test_make_evolution_gif_single_frame(tmp_path):
    # One frame → valid GIF (no animation, just one image)
    data = _make_frame_data(200, 200, (100, 100))
    img8, sn = align_frame(data, _make_wcs(), _make_wcs(), (100, 100))
    out = tmp_path / "single.gif"
    make_evolution_gif([(img8, sn)], dates=["2026-09-08"],
                       sn_xy_s=[(100, 100)], out=str(out))
    assert out.exists()
