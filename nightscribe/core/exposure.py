############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Exposure calculator module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import datetime
import math

# Session planning maths (ADR-021): plate scale from the camera profile,
# trailing-free exposure for fast NEOs, total session duration and the
# "latest safe start" against the local horizon (ADR-020), plus the rough
# limiting magnitude the Welcome step starts from.


def binning_factor(binning):
    # On-chip binning as a number. The config stores it as text ("2x2", the
    # same string the EXOTIC handoff writes) and a binned pixel is that many
    # sensor pixels wide, so the plate scale grows with it: 2x2 on a 3.76 um
    # sensor gives an 7.52 um effective pixel.
    # @args: binning - "1x1" | "2x2" | "3x3" | a number | None
    # @return: the factor (float); 1.0 when unknown or unusable
    if binning in (None, ""):
        return 1.0
    if isinstance(binning, (int, float)):
        return float(binning) or 1.0
    text = str(binning).strip().lower().replace(" ", "")
    if "x" in text:
        text = text.split("x", 1)[0]
    try:
        return float(text) or 1.0
    except ValueError:
        return 1.0


def plate_scale(pixel_um, focal_mm, binning=None):
    # Arcseconds per pixel from the camera pixel size and telescope focal
    # length: scale = 206.265 * pixel(um) / focal(mm). The binning enters
    # because the pixel the light falls on is the BINNED one: without it a
    # 2x2 plate reads half its real scale, and everything that hangs off the
    # scale (the transit exposure, the solver's hint, the field of view, the
    # sampling verdict) would be off by that factor. It was left out until
    # 2026-10-07: the value only mattered for someone who bins, and nothing
    # said so.
    # @args: pixel_um - camera pixel in microns, focal_mm - focal length in
    #        mm, binning - "2x2" or a number, None = 1x1
    # @return: plate scale in arcsec/pixel
    if not focal_mm:
        return 0.0
    px = float(pixel_um) * binning_factor(binning)
    return 206.265 * px / float(focal_mm)


# The band where the image is sampled the way its resolution wants: a star's
# FWHM landing on two or three pixels. A typical amateur site sees a couple
# of arcseconds, so the useful plate scale sits roughly between 0.5 and 2.0
# arcsec/pixel. Below the fine edge the sensor spends pixels it cannot
# resolve (more read noise per star, bigger files); above the coarse edge the
# star falls on barely a pixel and the image loses detail. The edges are a
# rule of thumb, not a law: the right number depends on the seeing of the
# site, which no form can tell us.
SAMPLE_FINE_MAX_ARCSEC_PX = 0.5
SAMPLE_COARSE_MIN_ARCSEC_PX = 2.0


def sampling(scale_arcsec_px):
    # @args: scale_arcsec_px - plate scale in arcsec/pixel (0/None = unknown)
    # @return: "fine" | "ok" | "coarse", or None when there is no scale
    try:
        scale = float(scale_arcsec_px)
    except (TypeError, ValueError):
        return None
    if scale <= 0:
        return None
    if scale < SAMPLE_FINE_MAX_ARCSEC_PX:
        return "fine"
    if scale > SAMPLE_COARSE_MIN_ARCSEC_PX:
        return "coarse"
    return "ok"


# ---------------- a starting limiting magnitude (Welcome step) -----------

# The Welcome step asks for the aperture and needs a number to put in the
# limiting magnitude field, so it estimates one. The physics: for a point
# source the signal the telescope collects grows with its AREA, D^2, and the
# magnitude reached grows as 5*log10(D). The constant is anchored on a typical
# amateur stacked image, where an 8-inch telescope reaches about magnitude
# 18.5 (4" -> 17.0, 6" -> 17.9, 12" -> 19.4, 16" -> 20.0). It is deliberately
# rough: the real limit also depends on the sky, the exposure and the
# reduction, which no first-run form can know. That is why the field says it is
# a starting point and the `inject` command measures the number that counts.
_LIMIT_ANCHOR = 7.0


def limit_from_aperture(aperture_in):
    # @args: aperture_in - telescope aperture in inches (0/None = unknown)
    # @return: an estimated limiting magnitude (float), or None when the
    #          aperture is unusable
    try:
        d_mm = float(aperture_in) * 25.4
    except (TypeError, ValueError):
        return None
    if d_mm <= 0:
        return None
    return _LIMIT_ANCHOR + 5.0 * math.log10(d_mm)


def max_exposure_no_trail(rate_arcsec_min, plate_scale_arcsec_px, tol_px=1.0):
    # Maximum single-frame exposure before the target trails more than tol_px
    # pixels. rate is arcsec/min; plate scale is arcsec/pixel.
    # @args: rate_arcsec_min - apparent rate, plate_scale_arcsec_px - arcsec/px,
    #        tol_px - tolerable drift in pixels (default 1)
    # @return: seconds (float), or None when the rate is unknown/zero
    if not rate_arcsec_min or rate_arcsec_min <= 0 or not plate_scale_arcsec_px:
        return None
    return tol_px * plate_scale_arcsec_px * 60.0 / float(rate_arcsec_min)


def session_duration_s(n_frames, exp_s, overhead_s=15.0):
    # Total wall-clock seconds of a capture sequence.
    # @args: n_frames - frame count, exp_s - exposure per frame in seconds,
    #        overhead_s - readout/slew per frame in seconds
    # @return: seconds (float)
    return int(n_frames) * (float(exp_s) + float(overhead_s))


def latest_safe_start(window_end_dt, duration_s):
    # Latest instant a session of the given duration can begin and still end
    # exactly when the object leaves the safe horizon window.
    # @args: window_end_dt - UTC datetime the window closes,
    #        duration_s - session duration in seconds
    # @return: UTC datetime, or None when the window end is unknown
    if window_end_dt is None:
        return None
    return window_end_dt - datetime.timedelta(seconds=duration_s)


def feasible(window_start_dt, window_end_dt, duration_s):
    # Whether the observable window is long enough for the planned session.
    # @args: window_start_dt/window_end_dt - UTC datetimes, duration_s - seconds
    # @return: bool
    if not window_start_dt or not window_end_dt:
        return False
    return (window_end_dt - window_start_dt).total_seconds() >= float(duration_s)


# ---------------- SN exposure by brightness (Track B, B8) ----------------

# Honest heuristic: a point source of mag M on a typical amateur setup
# (no SNR model — "guía, no promesa"). The table is a starting point the
# observer refines with a test shot (interview: "probar hasta no saturar").
# Exposures are capped at 300 s (5 min) for very faint targets — beyond that,
# the session duration dominates and a deeper survey is the better call.
_SN_EXP_TABLE = [
    (8.0,   30),    # very bright: short to avoid saturation
    (10.0,  60),
    (12.0,  90),
    (14.0, 120),
    (16.0, 180),
    (18.0, 240),
    (20.0, 300),   # faint: cap at 5 min
]


def recommended_sn_exposure(mag, max_exposure_s=None):
    # @args: mag - apparent magnitude of the SN (float),
    #        max_exposure_s - the camera profile's working maximum (None =
    #        no cap). For an extremely sensitive sCMOS the cap can be a few
    #        seconds; the extra integration comes from grouping frames.
    # @return: recommended single-frame exposure in seconds (int), or None
    #         when the magnitude is unknown
    if mag is None:
        return None
    mag = float(mag)
    exp = _SN_EXP_TABLE[-1][1]
    for threshold, e in _SN_EXP_TABLE:
        if mag <= threshold:
            exp = e
            break
    if max_exposure_s:
        exp = min(exp, float(max_exposure_s))
    return max(int(round(exp)), 1)


# ---------------- Transit exposure by star brightness (Track D) ----------

# Same philosophy as the SN table: an honest starting point the observer
# refines with a test shot (the pre-flight checklist demands a peak below
# saturation — "probar hasta no saturar"). Values at the reference plate
# scale of 1.0 arcsec/pixel, no defocus. The magnitude of a transit host
# star is small (V 8-14), so the table lives in the bright regime where
# saturation — not signal — is the binding constraint.
_TRANSIT_EXP_TABLE = [
    (9.0,   15),    # very bright star: short to stay well below saturation
    (10.0,  25),
    (11.0,  40),
    (12.0,  60),
    (13.0,  90),
    (14.0, 120),
    (99.0, 180),   # faintest hosts: cap
]

# The table scales with the SQUARE of the plate-scale ratio: for a
# seeing-limited point source the peak pixel flux grows with
# (arcsec/px)^2, so a finer plate (more px per arcsec) spreads the star
# over more pixels and tolerates a longer exposure before saturation.
# The correction is clamped to x0.25..x4 to stay in the sane regime.
_TRANSIT_REF_SCALE = 1.0


def recommended_transit_exposure(v_mag, plate_scale_arcsec_px=None,
                                 max_exposure_s=None):
    # @args: v_mag - host star V magnitude (float),
    #        plate_scale_arcsec_px - camera/telescope plate scale (None or 0
    #        means "unknown": the reference-scale value is returned),
    #        max_exposure_s - the camera profile's working maximum (None =
    #        no cap; the sCMOS needs few-second frames)
    # @return: recommended single-frame exposure in seconds (int, 5..300),
    #         or None when the magnitude is unknown
    if v_mag is None:
        return None
    v_mag = float(v_mag)
    exp = _TRANSIT_EXP_TABLE[-1][1]
    for threshold, e in _TRANSIT_EXP_TABLE:
        if v_mag <= threshold:
            exp = e
            break
    if plate_scale_arcsec_px:
        factor = (_TRANSIT_REF_SCALE / float(plate_scale_arcsec_px)) ** 2
        factor = min(max(factor, 0.25), 4.0)
        exp = int(round(exp * factor))
    exp = min(max(exp, 5), 300)
    if max_exposure_s:
        exp = min(exp, max(1, int(round(float(max_exposure_s)))))
    return exp


def group_n_for_span(target_span_s, exposure_s):
    # Frames to group so one point spans roughly the target time: the
    # sCMOS recipe (short exposures + grouping to beat scintillation and
    # keep the sky background down) without ever changing the cadence
    # recipe. It never replaces the ingress cadence.
    # @args: target_span_s - the wanted effective integration per point (s),
    #        exposure_s - the single-frame exposure (s)
    # @return: the group size (int >= 1)
    try:
        span = float(target_span_s)
        exp = float(exposure_s)
    except (TypeError, ValueError):
        return 1
    if exp <= 0 or span <= 0:
        return 1
    return max(1, int(round(span / exp)))
