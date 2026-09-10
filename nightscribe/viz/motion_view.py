############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - NEO/comet motion animation (Track C, C1)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Motion animation for moving targets (NEO / comet / PCCP): the fire test.

Unlike the SN evolution animation (evolution_view — fixed crop on the SN),
here each session frame is aligned to the **stars** (affine from its WCS
onto the first frame's geometry) and the crop **follows the predicted
position** of the object at the frame's DATE-OBS (ephemeris.position_at),
with a marker on that prediction and a caption carrying the date/time, the
predicted rate/PA and — mandatorily — the ephemeris source.

If a point sits under the marker in every frame while the stars drift past,
it is *that* object: the definitive visual check before measuring for the
MPC, and the classic NEO "movie" for the post. Frames without WCS, without
DATE-OBS or with no resolvable ephemeris are skipped with a notice (same
policy as B6).
"""

import logging

import numpy as np
from PIL import Image

from . import blink_view, evolution_view, style
from ..core import coords, fits_io, fits_meta
from ..core import wcs as wcs_mod

logger = logging.getLogger(__name__)

GIF_MAX = blink_view.GIF_MAX
VIDEO_FPS = blink_view.VIDEO_FPS
VIDEO_MIN_S = blink_view.VIDEO_MIN_S


# ---------------- captions ----------------

def _source_text(source, preliminary, lang):
    # @args: source - position_at source key, preliminary - bool, lang
    # @return: short ephemeris-source label. Always shown on the frame: the
    #          fire test is only as good as the ephemeris behind the marker,
    #          so the observer must know where the prediction came from.
    labels = {"horizons": "Horizons",
              "kepler:sbdb": "Kepler·SBDB",
              "kepler:neofixer": "Kepler·NEOfixer"}
    text = labels.get(source or "", source or "?")
    if preliminary:
        text += " " + style.pick(lang, "(prelim.)", "(prelim.)")
    return text


def position_caption(pos, dt, lang="es"):
    # @args: pos - position_at dict, dt - frame UTC datetime, lang - es|en
    # @return: caption "10/09/2026 21:14 UT · 12.3″/min · PA 87° · Horizons"
    parts = []
    if dt is not None:
        fmt = "%d/%m/%Y %H:%M" if (lang or "es") == "es" else "%Y-%m-%d %H:%M"
        parts.append(dt.strftime(fmt) + " UT")
    rate = (pos or {}).get("rate_arcsec_min")
    if rate is not None:
        parts.append(f"{rate:.1f}″/min")
    pa = (pos or {}).get("pa_deg")
    if pa is not None:
        parts.append(f"PA {pa:.0f}°")
    parts.append(_source_text((pos or {}).get("source"),
                              (pos or {}).get("preliminary"), lang))
    return " · ".join(parts)


# ---------------- frame pipeline ----------------

def _align_crop(data, frame_wcs, ref_wcs, ra_deg, dec_deg, zoom):
    # Warps the frame onto the reference geometry (affine from the WCS pair)
    # and crops around the predicted sky position.
    # @args: data - 2D array, frame_wcs - this frame's Wcs, ref_wcs -
    #        reference Wcs (first frame), ra_deg/dec_deg - predicted sky
    #        position at the frame instant, zoom - crop factor (blink
    #        semantics; 1 = full frame)
    # @return: (cropped uint8 array, predicted (x, y) inside the crop)
    h, w = data.shape
    a, b, c, d, e, f = evolution_view._compute_affine(frame_wcs, ref_wcs)
    pil = Image.fromarray(np.nan_to_num(data, nan=0.0), mode="F")
    pil = pil.transform((w, h), Image.AFFINE, (a, b, c, d, e, f),
                        resample=Image.BILINEAR)
    warped = np.asarray(pil, dtype=np.float32)
    xy = ref_wcs.sky_to_pixel(ra_deg, dec_deg)
    black, white = blink_view.auto_limits(warped)
    img8 = blink_view.to_uint8(blink_view.apply_stretch(warped, black, white))
    return blink_view.crop_zoom(img8, xy, zoom)


def load_motion_frames(image_paths, name, site, fallback_target=None,
                       position_fn=None, zoom=2, lang="es"):
    # Loads the session FITS, resolves the predicted position at each
    # frame's DATE-OBS and builds the aligned, prediction-centred crops.
    # Frames are sorted by DATE-OBS so the animation is chronological
    # regardless of the selection order.
    # @args: image_paths - session FITS paths, name - object designation
    #        (Horizons/packed), site - MPC code, fallback_target - planner
    #        ctx for the NEOCP fallback, position_fn - ephemeris resolver
    #        (injectable for tests; default ephemeris.position_at),
    #        zoom - crop factor, lang - caption language
    # @return: dict {frames_data: [(img8, xy)], dates: [captions],
    #                skipped: [(path, reason)]}
    from ..core import ephemeris
    resolve = position_fn or ephemeris.position_at
    readable = []
    skipped = []
    for path in image_paths:
        try:
            header, data = fits_io.read_fits(path)
        except Exception as err:
            logger.warning("motion: unreadable frame %s: %s", path, err)
            skipped.append((path, "unreadable"))
            continue
        frame_wcs = wcs_mod.Wcs.from_header(header)
        if frame_wcs is None:
            logger.warning("motion: frame without WCS skipped: %s", path)
            skipped.append((path, "no WCS"))
            continue
        meta = fits_meta.meta_from_header(header)
        if meta.get("mjd") is None:
            skipped.append((path, "no DATE-OBS"))
            continue
        readable.append((meta["mjd"], header, data, frame_wcs, path))
    readable.sort(key=lambda r: r[0])
    frames_data, dates = [], []
    ref_wcs = None
    for mjd, header, data, frame_wcs, path in readable:
        dt = coords.datetime_from_jd(mjd + 2400000.5)
        pos = resolve(name, site, when=dt, fallback_target=fallback_target)
        if pos is None:
            skipped.append((path, "no ephemeris"))
            continue
        if ref_wcs is None:
            ref_wcs = frame_wcs
        img8, xy = _align_crop(data, frame_wcs, ref_wcs,
                               pos["ra_deg"], pos["dec_deg"], zoom)
        frames_data.append((img8, xy))
        dates.append(position_caption(pos, dt, lang))
    return {"frames_data": frames_data, "dates": dates, "skipped": skipped}


# ---------------- public API (encoders) ----------------

def make_motion_gif(frames_data, dates, obj_xy_s, out, names=None,
                    watermark="NightScribe", lang="es", marker_scale=1.0,
                    interval_ms=None):
    # Animated GIF of the motion: one aligned, prediction-centred frame per
    # session FITS. Thin wrapper over the evolution pipeline — the frame
    # assembly (marker, caption, dwell) is identical once crops are built.
    # @args: same contract as evolution_view.make_evolution_gif
    # @return: output Path or None when there are no frames
    return evolution_view.make_evolution_gif(
        frames_data, dates, obj_xy_s, out, names=names, watermark=watermark,
        lang=lang, zoom=1, marker_scale=marker_scale, interval_ms=interval_ms)


def make_motion_video(frames_data, dates, obj_xy_s, out, names=None,
                      watermark="NightScribe", lang="es", marker_scale=1.0,
                      interval_ms=None, fps=VIDEO_FPS,
                      min_seconds=VIDEO_MIN_S):
    # MP4 (H.264) version of the motion GIF.
    # @args: same contract as evolution_view.make_evolution_video
    # @return: output Path or None when there are no frames
    return evolution_view.make_evolution_video(
        frames_data, dates, obj_xy_s, out, names=names, watermark=watermark,
        lang=lang, zoom=1, marker_scale=marker_scale, interval_ms=interval_ms,
        fps=fps, min_seconds=min_seconds)
