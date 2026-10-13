############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Capture recipe module (dither, autofocus, camera)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The values a capture wants, and the reason for each one (ADR-083).

Dithering and autofocus are decisions, not knobs: each one trades observing
time for image quality, and the trade depends on WHAT is being observed. A
moving object already changes the field by itself, so an explicit dither is
wasted; a transit cannot afford the gap a dither opens; a supernova wants both
and can pay for them. This module turns that reasoning into numbers, using the
same data the rest of the app already holds (plate scale, camera noise, the
object's rate).

What is NOT here: the brightness tables themselves. The sub-exposure and the
frame count ARE here, because they are decisions too: the table in
`core/exposure.py` is the empirical anchor, and this module corrects it for the
camera, the plate scale, the object's rate and (for a moving object) the field
it must not leave. The recipe points the observer at the criterion
(explain.SUBEXPOSURE, explain.FIELD_CROSSING) instead of hiding it.

The reasoning behind each number lives in the comments, because the code is
documentation too (AGENTS.md): a value that is not explained is a value that
will be lost.
"""

import logging

from . import exposure

logger = logging.getLogger(__name__)

# The kinds whose object MOVES against the stars: between two frames the field
# has already shifted on the sensor, so a hot pixel lands elsewhere by itself.
# An explicit dither would only spend settle time for nothing.
MOVING_KINDS = ("neo", "comet", "pccp", "alert")

# The kinds measured with a FAST cadence, where a dither gap or a mid-run
# autofocus would punch a hole in the light curve. Dither off; refocus only
# before the run.
FAST_KINDS = ("transit", "hads")

# The fraction of the HALF short side of the sensor a moving object may use
# before it reaches the edge. The goto centres it, so it starts with half the
# short side ahead; the 5% margin only covers the ephemeris uncertainty (the
# astrometric goto already absorbs the pointing error by plate-solving), because
# a frame with the object off the field is a lost frame. A preliminary orbit can
# be arcminutes off, so a fresh NEOCP may want a shorter run than this allows.
FIELD_TRAVEL_FRACTION = 0.95


def _scale(cfg):
    # @args: cfg - the Config
    # @return: the plate scale in arcsec/pixel (0 when unknown)
    return exposure.plate_scale(cfg.get("pixel_um"), cfg.get("focal_mm"),
                                cfg.get("pixel_binning"))


def _preset(cfg):
    # @args: cfg - the Config
    # @return: the camera preset dict (None when no preset is chosen)
    try:
        from . import cameras
        return cameras.preset(cfg.get("cam_preset"))
    except Exception:
        return None


def _fov_arcmin(cfg):
    # The camera's true field of view, from the preset's sensor size and the
    # focal length. None when there is no preset (the config does not carry
    # the sensor size on its own), which the caller must SAY: without it the
    # run cannot be bounded by the field.
    # @args: cfg - the Config
    # @return: (w, h) in arcmin, or None
    preset = _preset(cfg)
    if not preset:
        return None
    return exposure.fov_arcmin(preset.get("sensor_w_mm"),
                               preset.get("sensor_h_mm"),
                               cfg.get("focal_mm"))


def _field_crossing_s(kind, ctx, cfg):
    # How long a MOVING object takes to cross the usable field: it starts
    # centred, so it has half the SHORT side (the worst case for an unknown
    # direction of motion) minus the safety margin.
    # @args: kind - object kind, ctx - project context (rate), cfg - the Config
    # @return: (seconds, (fov_w, fov_h)) or (None, None) when the object does
    #          not move, or the rate or the field of view is unknown
    if kind not in MOVING_KINDS:
        return None, None
    rate = ctx.get("rate_arcsec_min")
    fov = _fov_arcmin(cfg)
    if not rate or not fov:
        return None, None
    travel_arcsec = min(fov) * 60.0 / 2.0 * FIELD_TRAVEL_FRACTION
    return travel_arcsec / float(rate) * 60.0, fov


def _dither(kind, cfg):
    # Dithering, decided by what the object does (see explain.DITHER).
    #
    # The amplitude grows with the plate scale: a hot pixel must land on a
    # DIFFERENT pixel, and the coarser the sampling the fewer pixels a small
    # nudge crosses. Five pixels is the common floor; 8 to 10 when the scale
    # is around or above an arcsecond per pixel, where the field is coarse.
    # The cadence is every 3 frames: often enough that a bad pixel moves in a
    # good fraction of the stack, rare enough that the settle time does not
    # eat the session.
    # @args: kind - object kind id, cfg - the Config
    # @return: {"on", "every", "pixels", "settle_s"}
    scale = _scale(cfg)
    if scale >= 2.0:
        pixels = 10
    elif scale >= 1.0:
        pixels = 8
    else:
        pixels = 5
    if kind in MOVING_KINDS or kind in FAST_KINDS:
        # the object moves (or the cadence is sacred): no dither
        return {"on": False, "every": 0, "pixels": pixels, "settle_s": 0}
    return {"on": True, "every": 3, "pixels": pixels, "settle_s": 5}


def _autofocus(kind, cfg):
    # Autofocus, decided by the cadence the object needs (see
    # explain.AUTOFOCUS). The temperature trigger (1 °C) is the usual figure
    # for an amateur refractor: focus moves about as fast as the tube cools.
    # @args: kind - object kind id, cfg - the Config
    # @return: {"on", "every", "minutes", "delta_c", "on_filter"}
    if kind in FAST_KINDS:
        # refocus before the run only: a mid-run autofocus breaks the curve
        return {"on": True, "every": 0, "minutes": 0, "delta_c": 0.0,
                "on_filter": False}
    if kind in ("sn", "variable"):
        # multi-filter work: refocus on the filter change and on temperature
        return {"on": True, "every": 0, "minutes": 45, "delta_c": 1.0,
                "on_filter": True}
    # moving objects: focus matters for the centroid; a longer cadence is fine
    return {"on": True, "every": 0, "minutes": 60, "delta_c": 1.0,
            "on_filter": False}


def _camera(kind, cfg):
    # Gain, offset and binning: the camera's OWN settings, not the photometry
    # ones. The system gain (e-/ADU) lives in the profile and is used only for
    # the linearity ceiling and the read-noise maths, NEVER sent to the capture
    # software (which wants the camera's gain index). So gain and offset default
    # to None = "leave the camera as it is"; the GUI fills them from what the
    # observatory reports when it is connected (ADR-083 rev).
    # @args: kind - object kind id, cfg - the Config
    # @return: {"gain", "offset", "binning"}
    return {"gain": None,
            "offset": None,
            "binning": cfg.get("pixel_binning") or "1x1"}


def _delay(kind, cfg):
    # Delay between frames: 0 by default. A positive delay only makes sense to
    # let a bright star cool or to dodge a passing cloud, which the observer
    # knows better than any rule.
    # @return: seconds (int)
    return 0


# ---- the sub-exposure (the numbers the observer cares about) -------------
#
# The brightness tables in core/exposure.py are the EMPIRICAL anchor: they
# were calibrated on a "typical" amateur setup, so they already know how long
# a mag-15 supernova or a V-11 host wants. Two corrections turn them into
# THIS observer's numbers, and each one is a single documented constant so it
# can be calibrated against real frames later.

# The linearity ceiling the tables assume (electrons). A camera with a SMALLER
# well must expose proportionally LESS: the peak pixel scales with the
# exposure, so half the well means half the time. This is the guard for the
# sensitive sCMOS (QHY42/GSENSE400 and friends) that saturate in seconds.
REF_LINEARITY_E = 20000.0

# The plate scale the tables assume (arcsec/pixel). The peak flux per pixel
# grows with the SQUARE of the scale (a coarse plate puts the same starlight
# on fewer pixels), so an 11 um sensor on a short focal saturates far sooner.
REF_SCALE_ARCSEC_PX = 1.0

# The sky the sub-exposure should beat: the criterion is sky electrons per
# pixel >= RON_FACTOR * read_noise^2. 10 is the usual "swamping" factor (the
# read noise then adds under 5% to the total noise).
RON_FACTOR = 10.0
# Electrons per second per pixel from a 21 mag/arcsec2 sky at 1 arcsec/pixel,
# for a typical amateur scope. A DOCUMENTED reference to calibrate; the dark
# sky scales as 10^(-0.4 * (mu - 21)) and with the plate scale squared.
SKY_E_PER_S_PX_AT_21 = 1.0


def _ceiling_e(cfg):
    # The linearity ceiling in ELECTRONS: the lesser of the full well and the
    # linearity limit (converted from ADU with the system gain). Either may be
    # unknown; None means "no ceiling we can name", and the caller keeps the
    # table's exposure.
    # @args: cfg - the Config
    # @return: electrons (float) or None
    caps = []
    fw = cfg.get("cam_full_well_e")
    if fw:
        caps.append(float(fw))
    lin_adu = cfg.get("cam_linearity_adu")
    gain = cfg.get("ccd_gain")
    if lin_adu and gain:
        caps.append(float(lin_adu) * float(gain))
    return min(caps) if caps else None


def _sky_rate(sky_mpsas, scale_arcsec_px):
    # @args: sky_mpsas - sky brightness (mag/arcsec2), scale_arcsec_px - plate
    #        scale (arcsec/pixel)
    # @return: sky electrons per pixel per second (float)
    if not sky_mpsas or not scale_arcsec_px:
        return 0.0
    brightness = SKY_E_PER_S_PX_AT_21 * 10.0 ** (-0.4 * (float(sky_mpsas) - 21.0))
    return brightness * float(scale_arcsec_px) ** 2


def _base_exposure(kind, ctx, cfg):
    # @args: kind - object kind id, ctx - project context, cfg - the Config
    # @return: (seconds, is_transit) -- the table's starting exposure; the
    #          transit table already scales with the plate scale, the others
    #          do not, so the caller must not scale it twice
    mag = ctx.get("mag")
    max_exp = cfg.get("cam_max_exposure_s")
    scale = _scale(cfg)
    if kind == "transit":
        return (exposure.recommended_transit_exposure(mag, scale, max_exp)
                or 60, True)
    if kind in ("sn", "variable"):
        return (exposure.recommended_sn_exposure(mag, max_exp) or 60, False)
    # HADS, moving objects and the rest: a neutral starting point; the trail
    # cap and the camera ceiling will move it
    return (60, False)


def _exposure(kind, ctx, cfg):
    # The suggested sub-exposure and frame count, with the reasons the observer
    # will read (returned as KEYS: core has no tr(), the GUI owns the wording).
    # @args: kind - object kind id, ctx - project context, cfg - the Config
    # @return: {"exposure_s", "n_frames", "warnings": [key, ...]}
    scale = _scale(cfg)
    base, is_transit = _base_exposure(kind, ctx, cfg)
    warnings = []

    # 1) the camera's linearity ceiling: a smaller well means LESS time. The
    #    factor only ever SHORTENS: the table is the recommended exposure for a
    #    typical setup, and a camera that saturates sooner gets a proportionally
    #    shorter one (never a longer one, which would be unrealistic)
    t = float(base)
    ceiling = _ceiling_e(cfg)
    if ceiling:
        t *= min(1.0, ceiling / REF_LINEARITY_E)

    # 2) the plate scale (skip for transit: its table already scaled). A coarse
    #    plate puts the starlight on fewer pixels and saturates sooner, so this
    #    shortens too; a fine plate does NOT lengthen (the table stays the cap)
    if scale and not is_transit:
        t *= min(1.0, (REF_SCALE_ARCSEC_PX / scale) ** 2)

    # 3) the hard caps: the camera's own floor, its working maximum, and the
    #    trail cap for a moving object (a trailed frame is worth nothing)
    exp_min = 0.1
    preset = _preset(cfg)
    if preset and preset.get("exp_min_s"):
        exp_min = float(preset["exp_min_s"])
    exp_max = cfg.get("cam_max_exposure_s")
    if exp_max:
        t = min(t, float(exp_max))
    rate = ctx.get("rate_arcsec_min")
    if rate:
        trail = exposure.max_exposure_no_trail(rate, scale)
        if trail:
            if t > trail:
                t = trail
                warnings.append("trail")
    if t < exp_min:
        t = exp_min
        warnings.append("saturation")
    t = max(t, exp_min)

    # 4) is the sub-exposure long enough to beat the read noise? If not, say
    #    so (binning or more frames is the honest fix); never expose past the
    #    saturation we just computed
    ron = cfg.get("ccd_read_noise")
    sky_rate = _sky_rate(cfg.get("sky_brightness_mag"), scale)
    if ron and sky_rate:
        t_ron = RON_FACTOR * float(ron) ** 2 / sky_rate
        if t < t_ron:
            warnings.append("read_noise")

    frames, fw, info = _n_frames(kind, ctx, cfg, t)
    warnings.extend(fw)
    return {"exposure_s": round(float(t), 1),
            "n_frames": frames,
            "warnings": warnings,
            "field_arcmin": info.get("arcmin"),
            "field_crossing_s": info.get("seconds")}


def _window_span_s(ctx):
    # The object's visibility span in seconds: `window_start`/`window_end`
    # first (the full span, independent of the planned duration, so the frame
    # count does NOT depend on whether a plan was saved yet), else the safe
    # window. 0.0 when there is no window to speak of.
    # @args: ctx - project context
    # @return: seconds (float)
    import datetime

    def _span(start, end):
        try:
            return (datetime.datetime.fromisoformat(str(end))
                    - datetime.datetime.fromisoformat(str(start))).total_seconds()
        except (ValueError, TypeError):
            return 0.0

    if ctx.get("window_start") and ctx.get("window_end"):
        span = _span(ctx["window_start"], ctx["window_end"])
        if span > 0:
            return span
    window = ctx.get("safe_window")
    if window and "|" in str(window):
        start, end = str(window).split("|", 1)
        return _span(start, end)
    return 0.0


def _n_frames(kind, ctx, cfg, exposure_s):
    # The frame count: what fills the object's visibility span, BUT never
    # more than what fits before the object crosses the camera's field. A
    # moving object starts centred (the goto does that), so it has half the
    # short side before it reaches the edge; once it is out, every later frame
    # is lost, and a plan of 600 frames that only fits 90 is a plan that
    # wastes the night (2026-10-13). The spin's own maximum (999) is the
    # ceiling.
    # @args: kind, ctx, cfg, exposure_s - the chosen sub-exposure
    # @return: (frames, warnings, info): frames (int), the warning keys, and
    #          {"arcmin": (w, h)|None, "seconds": crossing|None} for the GUI
    per_frame = float(exposure_s) + exposure.frame_overhead_s(cfg)
    if per_frame <= 0:
        per_frame = 1.0          # never divide by zero on a degenerate config
    span = _window_span_s(ctx)
    span_frames = int(span / per_frame) if span > 0 else None
    warnings = []
    t_cross, fov = _field_crossing_s(kind, ctx, cfg)
    info = {"arcmin": fov, "seconds": t_cross}
    if kind in MOVING_KINDS and t_cross is None:
        # it moves and we cannot tell the field or the rate: say so instead of
        # pretending the span is a plan
        warnings.append("field_unknown")
        cross_frames = None
    elif t_cross is not None:
        cross_frames = max(1, int(t_cross / per_frame))
    else:
        cross_frames = None
    if cross_frames is None:
        if span_frames is None:
            return 30, warnings, info            # no window known: a default
        return max(5, min(999, span_frames)), warnings, info
    if span_frames is None or cross_frames <= span_frames:
        # the field crossing is what really bounds the run
        warnings.append("field")
        if cross_frames < 5:
            # not even the five-frame floor fits: the honest count is smaller,
            # and the observer is told (shorter exposure, or re-point mid-run)
            warnings.append("field_short")
        return max(1, min(999, cross_frames)), warnings, info
    return max(5, min(999, span_frames)), warnings, info


def recommend(kind, ctx, cfg):
    # The whole recipe for one project.
    # @args: kind - object kind id, ctx - project context (magnitude, rate,
    #        safe window), cfg - the Config
    # @return: {"exposure_s", "n_frames", "warnings", "dither", "autofocus",
    #           "delay_s", "gain", "offset", "binning"}
    return {"dither": _dither(kind, cfg),
            "autofocus": _autofocus(kind, cfg),
            "delay_s": _delay(kind, cfg),
            **_exposure(kind, ctx, cfg),
            **_camera(kind, cfg)}
