############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: capture recipe (ADR-083)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The recipe turns the object's nature into numbers: a moving object does not
need an explicit dither (the field already shifts), a transit cannot afford the
gap, and a supernova wants both dither and refocus. These tests pin that, plus
the amplitude that grows with the plate scale.
"""

from nightscribe.core import capture_recipe


def _cfg(**kw):
    base = {"pixel_um": 3.76, "focal_mm": 2000.0, "pixel_binning": "1x1",
            "ccd_gain": 1.5, "ccd_read_noise": 6.0}
    base.update(kw)
    return base


def test_moving_object_needs_no_dither():
    # the object moves against the stars: the field is dithered for free
    for kind in ("neo", "comet", "pccp", "alert"):
        rec = capture_recipe.recommend(kind, {}, _cfg())
        assert rec["dither"]["on"] is False, kind


def test_fast_cadence_has_no_dither_and_refocuses_only_before():
    for kind in ("transit", "hads"):
        rec = capture_recipe.recommend(kind, {}, _cfg())
        assert rec["dither"]["on"] is False, kind
        assert rec["autofocus"]["on"] is True, kind
        assert rec["autofocus"]["minutes"] == 0, kind   # before the run only
        assert rec["autofocus"]["delta_c"] == 0.0, kind


def test_supernova_wants_dither_and_temperature_refocus():
    rec = capture_recipe.recommend("sn", {}, _cfg())
    assert rec["dither"] == {"on": True, "every": 3, "pixels": 5,
                             "settle_s": 5}
    af = rec["autofocus"]
    assert af["on"] is True and af["delta_c"] == 1.0 and af["on_filter"] is True


def test_dither_amplitude_grows_with_the_plate_scale():
    # a coarse plate (long focal, small pixels) needs a bigger nudge for a hot
    # pixel to land on a different pixel
    fine = capture_recipe.recommend(
        "sn", {}, _cfg(pixel_um=2.0, focal_mm=400.0))    # ~1.0 arcsec/px
    coarse = capture_recipe.recommend(
        "sn", {}, _cfg(pixel_um=6.0, focal_mm=600.0))    # ~2.1 arcsec/px
    assert fine["dither"]["pixels"] == 8
    assert coarse["dither"]["pixels"] == 10


def test_camera_options_do_not_use_the_system_gain():
    # ADR-083 rev: gain/offset are the camera's OWN settings (filled from the
    # observatory when connected), never the system gain in e-/ADU
    rec = capture_recipe.recommend("sn", {}, _cfg(ccd_gain=2.0,
                                                  pixel_binning="2x2"))
    assert rec["gain"] is None            # leave the camera as it is
    assert rec["offset"] is None
    assert rec["binning"] == "2x2"        # binning stays the profile's


# ---------------- the sub-exposure (ADR-083) ----------------

def _sn_cfg(**kw):
    base = {"pixel_um": 3.76, "focal_mm": 2000.0, "pixel_binning": "1x1",
            "ccd_gain": 1.0, "ccd_read_noise": 2.0,
            "cam_full_well_e": 50000.0, "cam_max_exposure_s": 3600.0,
            "sky_brightness_mag": 21.0, "cam_readout_s": 15.0}
    base.update(kw)
    return base


def test_a_small_full_well_means_a_shorter_exposure():
    # the guard for the sensitive sCMOS: half the well, half the time
    big = capture_recipe.recommend("sn", {"mag": 15.0},
                                   _sn_cfg(cam_full_well_e=50000.0))
    small = capture_recipe.recommend("sn", {"mag": 15.0},
                                     _sn_cfg(cam_full_well_e=2000.0))
    assert small["exposure_s"] < big["exposure_s"]


def test_a_coarse_plate_scale_saturates_sooner():
    fine = capture_recipe.recommend("sn", {"mag": 15.0},
                                    _sn_cfg(focal_mm=2000.0))   # ~0.4 "/px
    coarse = capture_recipe.recommend("sn", {"mag": 15.0},
                                      _sn_cfg(focal_mm=400.0))  # ~1.9 "/px
    assert coarse["exposure_s"] < fine["exposure_s"]


def test_a_moving_object_is_capped_by_the_trail():
    ctx = {"mag": 19.0, "rate_arcsec_min": 5.0}
    rec = capture_recipe.recommend("neo", ctx, _sn_cfg())
    # 1 px of trail at 0.39 "/px and 5 "/min is about 4.7 s
    assert rec["exposure_s"] <= 5.0
    assert "trail" in rec["warnings"]


def test_frame_count_fills_the_safe_window():
    ctx = {"mag": 15.0,
           "safe_window": "2026-10-13T20:00:00+00:00|"
                          "2026-10-13T22:00:00+00:00"}
    rec = capture_recipe.recommend("sn", ctx, _sn_cfg())
    # 2 h / (exposure + 15 s overhead)
    assert rec["n_frames"] == int(7200 / (rec["exposure_s"] + 15))


def test_read_noise_warning_when_the_sky_is_dark():
    rec = capture_recipe.recommend(
        "sn", {"mag": 18.0},
        _sn_cfg(ccd_read_noise=10.0, sky_brightness_mag=21.8))
    assert "read_noise" in rec["warnings"]


def test_frame_count_is_stable_with_or_without_a_saved_window():
    # the visibility SPAN (window_start/end) drives the count, not the safe
    # window that only appears once a plan is saved: the number must not flip
    span = {"mag": 15.0, "window_start": "2026-10-13T20:00:00+00:00",
            "window_end": "2026-10-13T22:00:00+00:00"}
    with_span = capture_recipe.recommend("sn", span, _sn_cfg())
    with_both = capture_recipe.recommend(
        "sn", {**span, "safe_window": "2026-10-13T20:30:00+00:00|"
                                     "2026-10-13T21:30:00+00:00"}, _sn_cfg())
    assert with_span["n_frames"] == with_both["n_frames"] == 36


def test_frame_count_without_a_window_is_a_plain_default():
    rec = capture_recipe.recommend("sn", {"mag": 15.0}, _sn_cfg())
    assert rec["n_frames"] == 30


# ---------------- the field crossing (ADR-083 rev) ----------------

# A 6-hour visibility window: the night alone would allow thousands of frames.
_LONG_NIGHT = {"window_start": "2026-10-13T20:00:00+00:00",
               "window_end": "2026-10-14T02:00:00+00:00"}


def test_frame_count_uses_the_field_crossing_time():
    # ADR-083 rev: a moving object starts centred, so it has half the SHORT
    # side of the sensor (times the margin) before it reaches the edge. The
    # count is that crossing divided by the per-frame time.
    cfg = _sn_cfg(cam_preset="imx571")           # 23.5 x 15.7 mm
    ctx = {"rate_arcsec_min": 60.0, **_LONG_NIGHT}
    t_cross, fov = capture_recipe._field_crossing_s("neo", ctx, cfg)
    assert fov == (40.38, 26.98) or abs(fov[1] - 26.98) < 0.05
    frames, warnings, info = capture_recipe._n_frames("neo", ctx, cfg, 10.0)
    assert frames == int(t_cross / (10.0 + 15.0))
    assert "field" in warnings
    assert info["seconds"] == t_cross


def test_a_fast_mover_is_capped_far_below_the_night():
    ctx = {"rate_arcsec_min": 60.0, **_LONG_NIGHT}
    rec = capture_recipe.recommend("neo", ctx, _sn_cfg(cam_preset="imx571"))
    assert "field" in rec["warnings"]
    assert rec["n_frames"] < 200          # not thousands
    assert rec["field_arcmin"] is not None


def test_a_moving_object_without_a_preset_cannot_be_bounded():
    # no camera preset -> no field of view: the app SAYS it, it does not
    # pretend the visibility span is a plan
    rec = capture_recipe.recommend("neo", {"rate_arcsec_min": 5.0}, _sn_cfg())
    assert "field_unknown" in rec["warnings"]


def test_a_moving_object_without_a_rate_cannot_be_bounded():
    rec = capture_recipe.recommend("neo", {}, _sn_cfg(cam_preset="imx571"))
    assert "field_unknown" in rec["warnings"]


def test_a_very_fast_object_warns_the_field_is_too_small():
    rec = capture_recipe.recommend(
        "neo", {"rate_arcsec_min": 5000.0}, _sn_cfg(cam_preset="imx571"))
    assert "field_short" in rec["warnings"]
    assert rec["n_frames"] == 1           # the honest count, not the floor


def test_a_slow_download_means_fewer_frames():
    # the readout/download is part of the per-frame time, so a slow one leaves
    # fewer frames before the object drifts out of the field
    ctx = {"rate_arcsec_min": 60.0}
    fast = capture_recipe.recommend("neo", ctx, _sn_cfg(cam_preset="imx571"))
    slow = capture_recipe.recommend(
        "neo", ctx, _sn_cfg(cam_preset="imx571", cam_readout_s=30.0))
    assert slow["n_frames"] < fast["n_frames"]


def test_a_fixed_object_is_not_bounded_by_the_field():
    # SN/transit/HADS do not move against the stars: the field crossing says
    # nothing about them
    ctx = {"mag": 15.0, "window_start": "2026-10-13T20:00:00+00:00",
           "window_end": "2026-10-13T22:00:00+00:00"}
    rec = capture_recipe.recommend("sn", ctx, _sn_cfg(cam_preset="imx571"))
    assert "field" not in rec["warnings"]
    assert "field_unknown" not in rec["warnings"]
    assert rec["n_frames"] == int(7200 / (rec["exposure_s"] + 15.0))
