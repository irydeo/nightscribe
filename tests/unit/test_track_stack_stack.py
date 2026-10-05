############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: stacking engine (ADR-062, phase 3)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Phase 3 acceptance: the group split, the per-group reference point,
the cutout that holds the whole trail, the four combination methods (the
sigma-clipped rejects a trail the mean keeps), RAM and streaming agreeing,
the sweep's score, the detection gate and the memory discipline. All
offline and synthetic: the object is injected with a known motion."""

import math

import numpy as np
import pytest
from astropy.io import fits

from nightscribe.core import track_stack as ts

IDENTITY = {"angle": 0.0, "dx": 0.0, "dy": 0.0, "quality": 100.0,
            "rms_px": 0.0}


def _write(path, data):
    fits.PrimaryHDU(np.asarray(data, dtype=np.int16)).writeto(str(path),
                                                              overwrite=True)
    return str(path)


def _star_field(size, seed=1):
    rng = np.random.default_rng(seed)
    img = rng.normal(1000.0, 4.0, (size, size))
    for _ in range(15):
        x, y = rng.uniform(5, size - 5), rng.uniform(5, size - 5)
        yy, xx = np.mgrid[0:size, 0:size]
        img += 2500.0 * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * 1.4 ** 2))
    return img


def _sequence(tmp_path, n=8, size=64, rate_px=1.5, amp=2000.0, obj=True,
              stars=True):
    # Stars stay put; the object walks rate_px per frame along +x.
    base = _star_field(size) if stars else np.full((size, size), 1000.0)
    frames = []
    yy, xx = np.mgrid[0:size, 0:size]
    for i in range(n):
        img = base.copy()
        x, y = 24.0 + rate_px * i, 34.0
        if obj:
            img += amp * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * 1.5 ** 2))
        path = _write(tmp_path / f"f{i:03d}.fits", img)
        frame = ts.Frame(path=path, header={"NAXIS1": size, "NAXIS2": size})
        frame.transform = dict(IDENTITY)
        frame.object_xy = (x, y)
        frame.t_mid_jd = 2460000.5 + i / 1440.0
        frame.object_ra = 0.0
        frame.object_dec = 0.0
        frames.append(frame)
    return frames


# ------------------------------------------------------------------ groups

def test_split_groups_is_contiguous_and_equal():
    frames = [ts.Frame(path=str(i)) for i in range(10)]
    groups = ts.split_groups(frames, 3)
    assert groups == [(0, 4), (4, 7), (7, 10)]
    assert ts.split_groups(frames, 1) == [(0, 10)]
    assert ts.split_groups(frames, 99) == [(i, i + 1) for i in range(10)]


def test_preview_groups_snr_falls_with_more_observations():
    frames = [ts.Frame(path="x", t_mid_jd=2460000.5 + i) for i in range(12)]
    preview = ts.preview_groups(frames, 3, base_snr=20.0)
    assert len(preview) == 3
    assert all(p["snr_est"] == pytest.approx(20.0 / math.sqrt(3), abs=0.1)
               for p in preview)


# -------------------------------------------------------------- offsets

def test_track_offsets_freeze_the_object():
    frames = _sequence(None, n=4) if False else [
        ts.Frame(path="x", transform=dict(IDENTITY), object_xy=(10.0 + i, 20.0))
        for i in range(4)]
    q = (13.0, 20.0)          # the object's position in the middle frame
    offsets = ts.track_offsets(frames, (0, 4), q, (64, 64))
    # offset_i = p_i - q (identity transform): frame i must move to q
    assert offsets[0] == pytest.approx((-3.0, 0.0))
    assert offsets[3] == pytest.approx((0.0, 0.0))


def test_cutout_box_holds_the_whole_trail():
    frames = [ts.Frame(path="x", transform=dict(IDENTITY),
                       object_xy=(10.0 + 5 * i, 20.0)) for i in range(5)]
    box = ts.cutout_box(frames, (0, 5), (20.0, 20.0), margin_px=8,
                        shape=(64, 64))
    x0, y0, x1, y1 = box
    # the trail spans x 10..30, so the box must contain it with the margin
    assert x0 <= 10 - 8 and x1 >= 30 + 8
    assert x0 >= 0 and y0 >= 0 and x1 <= 64 and y1 <= 64


# ------------------------------------------------------------- combine

def test_combine_sum_and_mean_differ_only_in_scale():
    stack = np.full((4, 5, 5), 3.0, dtype=np.float32)
    s = ts.combine(stack, "sum")
    m = ts.combine(stack, "mean")
    assert np.allclose(s, 12.0) and np.allclose(m, 3.0)
    assert np.allclose(s / 4.0, m)


def test_sigma_clip_rejects_a_trail_the_mean_keeps():
    # one frame has a bright line through the object's pixel: the mean
    # drags it, the sigma-clipped drops that frame
    stack = np.full((5, 7, 7), 10.0, dtype=np.float32)
    stack[2, 3, :] = 500.0        # a trail crossing the centre
    mean = ts.combine(stack, "mean")
    sig = ts.combine(stack, "sigma", sigma=2.0, iterations=3)
    assert mean[3, 3] > 50.0      # the trail moved the mean
    assert sig[3, 3] == pytest.approx(10.0, abs=2.0)


# ---------------------------------------------------------------- stacking

def test_stack_freezes_the_object_and_detects_it(tmp_path):
    frames = _sequence(tmp_path, n=8, rate_px=2.0, amp=2500.0)
    q = (24.0 + 2.0 * 3.5, 34.0)      # the object's position at the mid
    box = ts.cutout_box(frames, (0, 8), q, margin_px=12, shape=(64, 64))
    stack, report = ts.stack_group(frames, (0, 8), q, "mean", box, (64, 64))
    assert report.n_frames == 8 and not report.streamed
    det = ts.detect(stack, (q[0] - box[0], q[1] - box[1]), snr_sigma=3.5)
    assert det.detected and det.snr > 5.0
    assert det.roundness > 0.6


def test_stack_without_an_object_does_not_detect(tmp_path):
    # pure noise: no object, no stars, so a detection would be a false one
    frames = _sequence(tmp_path, n=8, obj=False, stars=False)
    q = (24.0 + 2.0 * 3.5, 34.0)
    box = ts.cutout_box(frames, (0, 8), q, margin_px=12, shape=(64, 64))
    stack, _ = ts.stack_group(frames, (0, 8), q, "mean", box, (64, 64))
    det = ts.detect(stack, (q[0] - box[0], q[1] - box[1]), snr_sigma=3.5)
    assert not det.detected
    assert det.mag_limit is None or det.mag_limit > 0


def test_ram_and_streaming_agree(tmp_path):
    frames = _sequence(tmp_path, n=6, rate_px=1.0)
    q = (24.0 + 1.0 * 2.5, 34.0)
    box = ts.cutout_box(frames, (0, 6), q, margin_px=10, shape=(64, 64))
    ram, _ = ts.stack_group(frames, (0, 6), q, "median", box, (64, 64),
                            budget_bytes=10 ** 9)
    streamed, report = ts.stack_group(frames, (0, 6), q, "median", box,
                                      (64, 64), budget_bytes=6 * 8 * 4)
    assert report.streamed
    # The two paths agree to ~1e-4 relative: scipy's order-3 spline
    # prefilters each region, so a strip's edges differ in the last digits
    # (the strips overlap to keep it there). Anything larger would be a
    # bug, not rounding.
    assert np.allclose(ram, streamed, rtol=1e-3, atol=0.05, equal_nan=True)


def test_stack_does_not_read_more_than_the_cutout(tmp_path):
    # the loader records the boxes it is asked for: none may be the whole
    # frame (that is the point of the region read, D32)
    frames = _sequence(tmp_path, n=4, size=64, rate_px=1.0)
    q = (24.0 + 1.0 * 1.5, 34.0)
    box = ts.cutout_box(frames, (0, 4), q, margin_px=8, shape=(64, 64))
    seen = []

    def loader(path, box_=None):
        seen.append(box_)
        return np.zeros((box_[3] - box_[1], box_[2] - box_[0]),
                        dtype=np.float32)
    ts.stack_group(frames, (0, 4), q, "mean", box, (64, 64), loader=loader)
    assert seen and all(b is not None for b in seen)
    assert all((b[2] - b[0]) < 64 or (b[3] - b[1]) < 64 for b in seen)


# ------------------------------------------------------------- roundness

def test_roundness_penalises_an_elongated_source():
    size = 41
    yy, xx = np.mgrid[0:size, 0:size]
    c = size // 2
    round_img = np.exp(-((xx - c) ** 2 + (yy - c) ** 2) / (2 * 1.5 ** 2))
    line_img = np.exp(-((yy - c) ** 2) / (2 * 1.0 ** 2))     # a horizontal line
    round_r = ts._roundness(round_img.astype(np.float32), c, c)
    line_r = ts._roundness(line_img.astype(np.float32), c, c)
    assert round_r > 0.7
    # the window clips the line, so it is not 0; what matters is that the
    # score clearly prefers the round source
    assert line_r < round_r - 0.2


def test_detect_reports_a_magnitude_limit_with_a_zero_point():
    stack = np.full((41, 41), 1000.0, dtype=np.float32)
    rng = np.random.default_rng(3)
    stack += rng.normal(0, 5.0, stack.shape).astype(np.float32)
    det = ts.detect(stack, (20.0, 20.0), snr_sigma=3.5, zp=25.0)
    assert not det.detected
    assert det.mag_limit is not None and det.mag_limit > 0


def test_failed_frames_are_left_out_of_the_stack(tmp_path):
    # A frame whose registration was not trusted inherits the previous
    # transform so the pipeline keeps going, but stacking it misaligned
    # only adds noise: it is left out and counted (measured on a real
    # night: 63 of 140 frames failed and dragged the base SNR from 15.8
    # to 11.4 until they were excluded).
    frames = _sequence(tmp_path, n=4, rate_px=1.0)
    frames[1].failed_register = True
    assert ts.usable(frames[0]) and not ts.usable(frames[1])
    q = (24.0 + 1.0 * 1.5, 34.0)
    box = ts.cutout_box(frames, (0, 4), q, margin_px=10, shape=(64, 64))
    stack, report = ts.stack_group(frames, (0, 4), q, "mean", box, (64, 64))
    assert report.n_frames == 3        # the failed one is not stacked


def test_a_group_with_no_usable_frame_returns_no_stack(tmp_path):
    frames = _sequence(tmp_path, n=3, rate_px=1.0)
    for f in frames:
        f.failed_register = True
    q = (24.0, 34.0)
    box = ts.cutout_box(frames, (0, 3), q, margin_px=10, shape=(64, 64))
    stack, report = ts.stack_group(frames, (0, 3), q, "mean", box, (64, 64))
    assert stack is None and report.n_frames == 0


def test_the_cutout_and_the_full_frame_are_the_same_image(tmp_path):
    # The resampling must not depend on the output window. scipy's
    # affine_transform works in (row, col) while the engine speaks (x, y),
    # and passing the (x, y) matrix and offsets straight through shifted
    # the frames by an amount that grew with the box origin: the cutout
    # stack and the full-frame stack of the SAME observation were different
    # images (measured on real data: 257 ADU apart around the object), so
    # the astrometry and the photometry were reading a shifted sky. A
    # rotation is needed to expose it (the identity hides the mix-up).
    frames = _sequence(tmp_path, n=5, size=96, rate_px=1.2)
    for frame in frames:
        frame.transform = {"angle": 0.06, "dx": 3.0, "dy": -2.0,
                           "quality": 100.0, "rms_px": 0.0}
    q = (24.0 + 1.2 * 2.0, 34.0)
    small = ts.box_around(q, 40, (96, 96))
    full = ts.box_around(q, 0, (96, 96))
    a, _ = ts.stack_group(frames, (0, 5), q, "mean", small, (96, 96))
    b, _ = ts.stack_group(frames, (0, 5), q, "mean", full, (96, 96))
    qx, qy = int(round(q[0])), int(round(q[1]))
    xs, ys = qx - small[0], qy - small[1]
    assert np.allclose(a[ys - 5:ys + 6, xs - 5:xs + 6],
                       b[qy - 5:qy + 6, qx - 5:qx + 6])
