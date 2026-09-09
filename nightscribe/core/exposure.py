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

# Session planning maths (ADR-021): plate scale from the camera profile,
# trailing-free exposure for fast NEOs, total session duration and the
# "latest safe start" against the local horizon (ADR-020).


def plate_scale(pixel_um, focal_mm):
    # Arcseconds per pixel from the camera pixel size and telescope focal
    # length: scale = 206.265 * pixel(um) / focal(mm).
    # @args: pixel_um - camera pixel in microns, focal_mm - focal length in mm
    # @return: plate scale in arcsec/pixel
    if not focal_mm:
        return 0.0
    return 206.265 * float(pixel_um) / float(focal_mm)


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


def recommended_sn_exposure(mag):
    # @args: mag - apparent magnitude of the SN (float)
    # @return: recommended single-frame exposure in seconds (int), or None
    #         when the magnitude is unknown
    if mag is None:
        return None
    mag = float(mag)
    for threshold, exp in _SN_EXP_TABLE:
        if mag <= threshold:
            return exp
    return _SN_EXP_TABLE[-1][1]   # fainter than the last entry: cap
