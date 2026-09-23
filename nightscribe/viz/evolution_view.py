############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - SN evolution animation (Track B, B6)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""N-frame evolution animation for the SN follow-up.

Reuses the stretch/crop/encode machinery from blink_view (ADR-018) but
works on **N stacked images** (one per night) instead of a 2-frame ref/obs pair. Each
frame is aligned to the reference geometry via an affine transform derived from
the per-frame WCS (so stars stay fixed and the SN stays at the same pixel), crop around
the SN, labelled with the date, and assembled into a GIF and an MP4.

The affine is approximated by sampling 3 points through the WCS chain
(frame pixel → sky → reference pixel) and solving for the 2x3 matrix — robust
for small fields (<1-2°) where the gnomonic curvature error is a few pixels at
the edges (same tolerance as ADR-018).
"""

import datetime
import logging

import numpy as np
from PIL import Image

from ..core import stretch
from . import blink_view, style

logger = logging.getLogger(__name__)

GIF_MAX = blink_view.GIF_MAX
VIDEO_FPS = blink_view.VIDEO_FPS
VIDEO_MIN_S = blink_view.VIDEO_MIN_S


# ---------------- affine alignment ----------------

def _compute_affine(frame_wcs, ref_wcs):
    # @args: frame_wcs - Wcs of the frame to align, ref_wcs - reference Wcs
    # @return: (a, b, c, d, e, f) PIL affine transform coefficients that map
    #         **reference (output) pixels to frame (input) pixels** — the
    #         direction PIL's Image.transform(AFFINE) samples with: for each
    #         output pixel (x, y) it reads the input at
    #         (a·x + b·y + c, d·x + e·y + f).
    # Sample 3 points in reference space, map them through the inverse WCS
    # chain (reference pixel → sky → frame pixel), and solve for the 2x3
    # matrix. (Until the C1 fire-test this sampled the opposite direction,
    # which warps by the inverse transform — invisible for near-identical
    # WCS, wrong for shifted fields.)
    h, w = ref_wcs.naxis2, ref_wcs.naxis1
    pts_ref = np.array([[w * 0.25, h * 0.25],
                         [w * 0.75, h * 0.25],
                         [w * 0.5, h * 0.75]], dtype=np.float64)
    pts_frame = []
    for px, py in pts_ref:
        ra, dec = ref_wcs.pixel_to_sky(px, py)
        fx, fy = frame_wcs.sky_to_pixel(ra, dec)
        pts_frame.append([fx, fy])
    pts_frame = np.array(pts_frame, dtype=np.float64)
    # Augment ref points with a 1 column [x, y, 1] and solve least-squares.
    ref_aug = np.hstack([pts_ref, np.ones((3, 1))])
    # lstsq solves A·x = b; here A=ref_aug (3x3), b=pts_frame (3x2) →
    # coeffs is (3,2): each column is the coefficients for one frame axis.
    coeffs, *_ = np.linalg.lstsq(ref_aug, pts_frame, rcond=None)
    # coeffs[:, 0] = (a, b, c) for fx; coeffs[:, 1] = (d, e, f) for fy
    a, b, c = coeffs[:, 0]
    d, e, f = coeffs[:, 1]
    return (a, b, c, d, e, f)


def align_frame(data, frame_wcs, ref_wcs, sn_xy, crop_size=None):
    # Warps a frame to the reference geometry (affine from WCS) and crops
    # around the SN. Frames without WCS are returned aligned by their own
    # geometry (no warp) so the animation can still show them — stars
    # may drift but the SN stays put.
    # @args: data - 2D numpy array, frame_wcs - this frame's Wcs or None,
    #        ref_wcs - reference Wcs, sn_xy - (x, y) SN pixel in this frame,
    #        crop_size - (w, h) of the crop (default: min of frame and 256)
    # @return: (cropped uint8 array, sn_xy_in_crop)
    h, w = data.shape
    if crop_size is None:
        cs = min(w, h, 256)
        crop_size = (cs, cs)
    cw, ch = crop_size
    if frame_wcs is not None and ref_wcs is not None:
        a, b, c, d, e, f = _compute_affine(frame_wcs, ref_wcs)
        pil = Image.fromarray(np.nan_to_num(data, nan=0.0), mode="F")
        pil = pil.transform((w, h), Image.AFFINE, (a, b, c, d, e, f),
                            resample=Image.BILINEAR)
        data = np.asarray(pil, dtype=np.float32)
        # SN pixel in the reference frame
        sn_ra, sn_dec = frame_wcs.pixel_to_sky(*sn_xy)
        sn_xy = ref_wcs.sky_to_pixel(sn_ra, sn_dec)
    # stretch + crop (core engine, ADR-044)
    black, white = stretch.auto_limits(data)
    stretched = stretch.apply_stretch(data, black, white)
    img8 = stretch.to_uint8(stretched)
    img8, sn_crop = blink_view.crop_zoom(img8, sn_xy, 1)
    return img8, sn_crop


# ---------------- frame rendering ----------------

def _date_label(mjd, lang="es"):
    # @args: mjd - Modified Julian Date (float), lang - "es"|"en"
    # @return: a short date string for the frame caption
    if mjd is None:
        return ""
    from ..core.coords import datetime_from_jd
    try:
        dt = datetime_from_jd(mjd + 2400000.5)
    except (ValueError, OverflowError):
        return ""
    if (lang or "es") == "en":
        return dt.strftime("%Y-%m-%d")
    return dt.strftime("%d/%m/%Y")


def _evolution_frames(frames_data, dates, sn_xy_s, names, watermark, lang,
                     zoom, marker_scale, interval_ms):
    # Shared frame pipeline for the animated exports (GIF and MP4).
    # @args: frames_data - list of (uint8 array, sn_xy) aligned+stretched+cropped,
    #        dates - list of date strings (one per frame), sn_xy_s - list of SN pixels,
    #        names - list of SN name strings, watermark - footer,
    #        lang - "es"|"en", zoom - crop factor, marker_scale - marker size,
    #        interval_ms - dwell per frame
    # @return: (list of PIL RGB frames, dwell per frame in ms)
    frames = []
    for i, (img8, sn) in enumerate(frames_data):
        h, w = img8.shape
        if max(h, w) > GIF_MAX:
            img8 = blink_view._downscale8(img8, max_dim=GIF_MAX)
            if sn is not None:
                sn = (sn[0] * w / max(h, w) if max(h, w) > GIF_MAX else 1,
                       sn[1] * h / max(h, w) if max(h, w) > GIF_MAX else 1)
        cap = dates[i] if i < len(dates) else ""
        name = names[i] if i < len(names) else ""
        frames.append(blink_view._fig_to_image(blink_view._frame_fig(
            img8, sn, name, cap, watermark, marker_scale)))
    duration = interval_ms or 500
    return frames, duration


# ---------------- public API ----------------

def make_evolution_gif(frames_data, dates, sn_xy_s, out, names=None,
                        watermark="NightScribe", lang="es", zoom=1,
                        marker_scale=1.0, interval_ms=None):
    # Animated GIF of the SN evolution: one aligned frame per night.
    # @args: frames_data - list of (uint8 array, sn_xy) aligned frames,
    #        dates - list of date strings (one per frame),
    #        sn_xy_s - list of SN pixel positions (one per frame),
    #        out - GIF path, names - list of SN name labels,
    #        watermark - footer, lang - caption language,
    #        zoom - crop factor, marker_scale - marker size,
    #        interval_ms - dwell per frame (default 500 ms)
    # @return: output Path
    if not frames_data:
        logger.warning("evolution GIF: no frames, skipping")
        return None
    names = names or [""] * len(frames_data)
    frames, duration = _evolution_frames(
        frames_data, dates, sn_xy_s, names, watermark, lang,
        zoom, marker_scale, interval_ms)
    frames[0].save(str(out), save_all=True, append_images=frames[1:],
                   duration=duration, loop=0)
    logger.info("evolution GIF written to %s", out)
    return out


def make_evolution_video(frames_data, dates, sn_xy_s, out, names=None,
                           watermark="NightScribe", lang="es", zoom=1,
                           marker_scale=1.0, interval_ms=None, fps=VIDEO_FPS,
                           min_seconds=VIDEO_MIN_S):
    # MP4 (H.264) version of the evolution GIF.
    # @args: same as make_evolution_gif, plus fps, min_seconds
    # @return: output Path
    if not frames_data:
        logger.warning("evolution video: no frames, skipping")
        return None
    import imageio_ffmpeg
    names = names or [""] * len(frames_data)
    frames, duration = _evolution_frames(
        frames_data, dates, sn_xy_s, names, watermark, lang,
        zoom, marker_scale, interval_ms)
    cycle_ms = duration * len(frames)
    loops = max(1, -(-int(min_seconds * 1000) // cycle_ms))
    frames = frames * loops
    w, h = frames[0].size
    if w % 2 or h % 2:
        even = (w + w % 2, h + h % 2)
        padded = []
        for frame in frames:
            canvas = Image.new("RGB", even)
            canvas.paste(frame, (0, 0))
            padded.append(canvas)
        frames = padded
        w, h = even
    per_frame = max(1, round(fps * duration / 1000))
    writer = imageio_ffmpeg.write_frames(
        str(out), (w, h), fps=fps, codec="libx264", pix_fmt_in="rgb24",
        quality=7, macro_block_size=1, ffmpeg_log_level="error",
        output_params=["-movflags", "+faststart"])
    writer.send(None)
    for frame in frames:
        arr = np.asarray(frame)
        for _ in range(per_frame):
            writer.send(arr)
    writer.close()
    logger.info("evolution video written to %s", out)
    return out
