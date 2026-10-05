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
import warnings

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
    # an empty sequence has no observations: clamping n_obs to the frame
    # count left it at ZERO and the division blew up (a tab repainted with
    # an empty visit crashed here)
    assert ts.split_groups([], 3) == []


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


def test_the_star_stack_freezes_the_stars_and_the_object_stack_the_object(
        tmp_path):
    # Two alignments, two jobs (ADR-062). The object's stack concentrates
    # its light, which is the only way a faint NEO can be measured at all;
    # the STAR stack is the only place the comparison stars are points,
    # and a zero point cannot be set from a streak. Same frames, same
    # method: what changes is what the frames are aligned on.
    frames = _sequence(tmp_path, n=12, size=64, rate_px=1.5)
    q = (24.0 + 1.5 * 5.5, 34.0)          # the object at the middle instant
    box = (0, 0, 64, 64)
    tracked, _ = ts.stack_group(frames, (0, 12), q, "mean", box, (64, 64))
    stars, _ = ts.stack_group(frames, (0, 12), q, "mean", box, (64, 64),
                              track=False)
    assert not np.allclose(tracked, stars)
    yy, xx = np.mgrid[0:64, 0:64]
    # the sky is the same in both (same frames): what is compared is the
    # light ABOVE it, or the background would drown the difference
    sky_t = float(np.median(tracked))
    sky_s = float(np.median(stars))
    # ON the object: tracking concentrates it, the star stack spreads it
    # along the 16.5 px trail
    ap = np.hypot(xx - q[0], yy - q[1]) <= 2.0
    obj_t = tracked[ap].sum() - sky_t * ap.sum()
    obj_s = stars[ap].sum() - sky_s * ap.sum()
    assert obj_t > 3.0 * obj_s
    # and a STAR away from the trail is the other way round
    far = np.abs(yy - 34.0) > 10.0
    sy, sx = np.unravel_index(int(np.argmax(np.where(far, stars, -np.inf))),
                              stars.shape)
    star_ap = np.hypot(xx - sx, yy - sy) <= 2.0
    star_s = stars[star_ap].sum() - sky_s * star_ap.sum()
    star_t = tracked[star_ap].sum() - sky_t * star_ap.sum()
    assert star_s > 3.0 * star_t


def test_stack_groups_carries_the_alignment_to_every_observation(tmp_path):
    # The per-observation star stacks are what the photometry reads, so
    # the flag has to travel through the plural entry point too.
    frames = _sequence(tmp_path, n=8, size=64, rate_px=1.5)
    groups = ts.split_groups(frames, 2)
    qs = [(24.0 + 1.5 * 1.5, 34.0), (24.0 + 1.5 * 5.5, 34.0)]
    boxes = [(0, 0, 64, 64)] * 2
    tracked = ts.stack_groups(frames, groups, qs, "mean", boxes, (64, 64))
    stars = ts.stack_groups(frames, groups, qs, "mean", boxes, (64, 64),
                            track=False)
    assert len(stars) == len(tracked) == 2
    assert not np.allclose(stars[0][0], tracked[0][0])
    assert not np.allclose(stars[1][0], tracked[1][0])


def test_the_stack_does_not_warn_about_its_own_footprint():
    # The pixels outside the frames' footprint are all-NaN by construction
    # (the mask says so), and the NaN-aware reductions warned about them on
    # every stack: two lines of noise per stack that hid the warnings that
    # do matter. The answer there is NaN, which is what those pixels
    # deserve, so the warning is silenced where it is expected.
    data = np.full((4, 6, 6), 100.0, dtype=np.float32)
    mask = np.ones((4, 6, 6), dtype=bool)
    mask[:, 0, :] = False                 # a row outside the footprint
    for method in ("sum", "mean", "median", "sigma"):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            out = ts.combine(data, method, mask=mask)
        noisy = [w for w in caught
                 if "NaN" in str(w.message) or "empty" in str(w.message)]
        assert not noisy, (method, [str(w.message) for w in noisy])
        # inside the footprint: the sum adds the four frames, the other
        # three average them
        assert out[3, 3] == pytest.approx(400.0 if method == "sum" else 100.0)
        if method != "sum":
            # nansum treats NaN as zero, so outside the footprint it gives
            # 0; the other three propagate the NaN, which is the honest
            # answer for a pixel no frame ever covered
            assert np.isnan(out[0, 0]), method


# ------------------------------------------- P1: the weighted combination

def test_without_weights_the_weighted_method_is_the_sigma_clip():
    # The new method degrades into the PROVEN one, never into something
    # new: same clip, and an unweighted average of the survivors.
    rng = np.random.default_rng(3)
    stack = np.asarray([1000.0 + rng.normal(0.0, 5.0, (24, 24))
                        for _ in range(5)], dtype=np.float32)
    stack[2, 12, 12] = 9000.0            # a trail the clip must reject
    a = ts.combine(stack, "sigma", sigma=2.0, iterations=3)
    b = ts.combine(stack, "weighted", sigma=2.0, iterations=3)
    assert np.allclose(a, b, atol=1e-3, equal_nan=True)


def test_the_weighted_average_beats_the_plain_one():
    # The optimal combination of measurements of the SAME signal with
    # different noise is the inverse-variance average: the frame with less
    # noise carries more of the answer. Here four clean frames and one with
    # fifteen times the noise, over thirty realisations so the number is a
    # statistic and not a coin toss. The clip is wide on purpose: what is
    # being measured is the WEIGHT, not the rejection.
    rng = np.random.default_rng(7)
    truth, size = 1000.0, 32
    weights = np.asarray([1 / 4.0] * 4 + [1 / 900.0])
    err_w, err_e = [], []
    for _ in range(30):
        frames = [truth + rng.normal(0.0, 2.0, (size, size))
                  for _ in range(4)]
        frames.append(truth + rng.normal(0.0, 30.0, (size, size)))
        stack = np.asarray(frames, dtype=np.float32)
        w = ts.combine(stack, "weighted", sigma=100.0, weights=weights)
        e = ts.combine(stack, "weighted", sigma=100.0,
                       weights=np.ones(5))
        err_w.append(float(np.abs(w - truth).mean()))
        err_e.append(float(np.abs(e - truth).mean()))
    # measured: the weighted average lands ~6x closer to the truth, which
    # is what 1/sigma^2 promises (sigma 6.05 -> 1.00)
    assert float(np.mean(err_w)) < 0.5 * float(np.mean(err_e))


def test_frame_weights_are_the_inverse_variance():
    def _frame(sigma):
        f = ts.Frame(path="x.fits")
        f.sky_sigma = sigma
        return f
    w = ts.frame_weights([_frame(1.0), _frame(2.0), _frame(4.0)])
    assert list(w) == pytest.approx([1.0, 0.25, 0.0625])
    # no frame knows its noise: no weights, and the caller falls back
    assert ts.frame_weights([_frame(None), _frame(None)]) is None
    # a frame that could not be measured gets the median of the others: it
    # is a real frame, only an unmeasured one
    w = ts.frame_weights([_frame(2.0), _frame(2.0), _frame(None)])
    assert list(w) == pytest.approx([0.25, 0.25, 0.25])


def test_the_noise_of_a_frame_is_measured_from_its_sky():
    rng = np.random.default_rng(9)
    data = 1000.0 + rng.normal(0.0, 7.0, (64, 64))
    sigma = ts._frame_noise(data)
    assert sigma == pytest.approx(7.0, rel=0.15)
    assert ts._frame_noise(np.zeros((4, 4))) is None      # no noise at all


def test_the_two_paths_agree_with_weights(tmp_path):
    # The weights are a property of the FRAME, not of a strip, so the RAM
    # and the streaming paths must use the same ones (they are pinned to
    # agree for every method).
    frames = _sequence(tmp_path, n=6)
    for i, f in enumerate(frames):
        f.sky_sigma = 2.0 + i          # deliberately different per frame
    box = (16, 16, 48, 48)
    ram, _ = ts.stack_group(frames, (0, 6), (32.0, 32.0), "weighted", box,
                            (64, 64), budget_bytes=10 ** 9)
    streamed, report = ts.stack_group(frames, (0, 6), (32.0, 32.0),
                                      "weighted", box, (64, 64),
                                      budget_bytes=1)
    assert report.streamed is True
    assert np.allclose(ram, streamed, atol=1e-4, equal_nan=True)


# ------------------------------- a frame that does not cover the observation

def test_source_box_says_none_when_the_box_is_off_the_frame():
    # The box is 1024..1359 in x on a 2048 frame; a transform that pushes it
    # 3000 px away leaves NOTHING of it on the sensor, and that is a real
    # answer, not a failure: the frame does not contain this observation.
    A, b = ts._ref_to_native_affine({"angle": 0.0, "dx": -3000.0,
                                     "dy": 0.0}, (0.0, 0.0))
    assert ts._source_box(A, b, (1024, 1024, 1359, 1359), (2048, 2048)) is None
    # and a box that only PARTLY falls off keeps its overlap: what is off
    # the frame is clamped away and the box stays ON the sensor
    A, b = ts._ref_to_native_affine({"angle": 0.0, "dx": -1000.0,
                                     "dy": 0.0}, (0.0, 0.0))
    box = ts._source_box(A, b, (1024, 1024, 1359, 1359), (2048, 2048))
    assert box is not None
    assert 0 <= box[0] < box[2] <= 2048
    assert 0 <= box[1] < box[3] <= 2048


def test_warping_a_box_off_the_frame_does_not_read_or_crash():
    # The real bug, in one call: the path does NOT exist on purpose, so if
    # anything tried to read it the test would fail with a file error
    # instead of a wrong answer. Measured on a real visit: the read came
    # back 1-D and scipy took the 2x2 rotation for a homogeneous matrix and
    # refused it ("...for image shape (0,)").
    tr = {"angle": 0.0, "dx": -3000.0, "dy": 0.0}
    warped, valid = ts._warp_to_box("/no/such/frame.fits", tr, (0.0, 0.0),
                                    (1024, 1024, 1359, 1359), (2048, 2048))
    assert warped.shape == (335, 335)
    assert not warped.any()
    assert not valid.any()


def test_a_frame_whose_object_is_off_the_sensor_is_left_out(tmp_path):
    # A visit with two runs points the second one at a shifted field, and
    # the object can fall off the sensor. Such a frame registered, but it
    # has sky where the object should be: stacking it adds noise to the very
    # place being measured, so it is left out AND counted.
    frames = _sequence(tmp_path, n=6, rate_px=1.5)
    frames[2].object_xy = (-40.0, 30.0)          # off the 64x64 sensor
    assert ts.inside_frame(frames[2]) is False
    assert ts.inside_frame(frames[0]) is True
    q = (24.0 + 1.5 * 2.5, 34.0)
    stack, report = ts.stack_group(frames, (0, 6), q, "mean",
                                   (0, 0, 64, 64), (64, 64))
    assert stack is not None
    assert report.n_frames == 5                  # the off-sensor one is out
    assert ts._indices(frames, (0, 6)) == [0, 1, 3, 4, 5]


def test_a_frame_without_an_object_position_is_still_left_out(tmp_path):
    # The old rule has to survive: no object position, no stack entry.
    frames = _sequence(tmp_path, n=4)
    frames[1].object_xy = None
    assert ts.inside_frame(frames[1]) is False
    assert ts._indices(frames, (0, 4)) == [0, 2, 3]
