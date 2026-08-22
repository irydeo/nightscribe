############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Supernova blink rendering module (ADR-018)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import logging

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

from . import style

logger = logging.getLogger(__name__)

# Renders of the aligned blink pair (user image + geometry-matched survey
# cutout, see core/blink.py): stretches, side-by-side PNG, animated GIF.
# Frames are drawn with matplotlib (ADR-010) and assembled with Pillow.

GIF_MAX = 1024          # max GIF/video dimension, keeps files attachable
BLINK_MS = 500          # default dwell per frame in blink mode
FADE_MS = 60            # frame time in fade mode
FADE_STEPS = 10         # blend steps per direction in fade mode
VIDEO_FPS = 30          # MP4 frame rate
VIDEO_MIN_S = 6.0       # videos do not loop like GIFs: repeat the cycle
                        # until the clip lasts at least this long

# Export captions are single-language (the UI language), not bilingual
_CAPTIONS = {"es": {"before": "Antes", "after": "Después"},
             "en": {"before": "Before", "after": "After"}}
_OBS_FALLBACK = {"es": "observatorio", "en": "observatory"}


def auto_limits(data, lo=1.0, hi=99.5):
    # Robust black/white points from percentiles, NaN-safe.
    # @args: data - 2D array, lo, hi - percentiles
    # @return: (black, white) with white > black guaranteed
    flat = data[np.isfinite(data)]
    if flat.size == 0:
        return 0.0, 1.0
    black, white = np.percentile(flat, [lo, hi])
    if white <= black:
        white = black + 1.0
    return float(black), float(white)


def apply_stretch(data, black, white, gamma=1.0):
    # Linear stretch between black/white points with a gamma curve.
    # @args: data - 2D array, black, white - limits, gamma - <1 brightens
    # @return: float array 0..1
    gamma = max(gamma, 1e-3)
    span = max(white - black, 1e-12)
    out = np.clip((data - black) / span, 0.0, 1.0)
    return np.power(out, gamma)


def auto_gain(ref_f, obs_f):
    # Gain that equalizes the sky background level of the stretched pair
    # (median-matched), so blinking does not pump brightness.
    # @args: ref_f, obs_f - stretched float arrays 0..1
    # @return: gain to multiply the survey by, clamped to [0.25, 4]
    med_r = float(np.nanmedian(ref_f))
    med_o = float(np.nanmedian(obs_f))
    if med_r < 1e-6:
        return 1.0
    return float(np.clip(med_o / med_r, 0.25, 4.0))


def apply_gain(img_f, gain):
    # @args: img_f - stretched float array, gain - multiplicative factor
    # @return: float array 0..1
    return np.clip(img_f * gain, 0.0, 1.0)


def to_uint8(img):
    # @args: img - float array 0..1
    # @return: uint8 array 0..255
    return (np.nan_to_num(img) * 255.0 + 0.5).astype(np.uint8)


def crop_zoom(img, sn_xy, zoom):
    # Crops the frame around the SN position, clamped at the edges, so the
    # marker and the host galaxy are actually visible in small exports.
    # @args: img - 2D array, sn_xy - (x, y) or None, zoom - factor (1 = full)
    # @return: (cropped array, new sn_xy)
    if zoom <= 1 or sn_xy is None:
        return img, sn_xy
    h, w = img.shape
    cw = max(32, w // zoom)
    ch = max(32, h // zoom)
    x, y = sn_xy
    x0 = int(min(max(x - cw / 2, 0), max(w - cw, 0)))
    y0 = int(min(max(y - ch / 2, 0), max(h - ch, 0)))
    return img[y0:y0 + ch, x0:x0 + cw], (x - x0, y - y0)


def captions(lang, ref_label="", observatory=""):
    # Single-language frame captions (ADR-018: exports follow the UI language).
    # @args: lang - "es"|"en", ref_label - survey name, observatory - name
    # @return: (before, after) caption strings
    c = _CAPTIONS.get(lang, _CAPTIONS["en"])
    obs = observatory or _OBS_FALLBACK.get(lang, _OBS_FALLBACK["en"])
    before = c["before"] + (f" — {ref_label}" if ref_label else "")
    after = f"{c['after']} — {obs}"
    return before, after


def _frame_fig(img8, sn_xy, label, caption, watermark, marker_scale=1.0,
               dpi=100):
    # Builds one frame: stretched image + SN marker + captions.
    # @args: img8 - uint8 2D array, sn_xy - (x, y) or None, label - SN name,
    #        caption - frame caption, watermark - footer text,
    #        marker_scale - multiplier for the marker size
    # @return: matplotlib figure sized to the image
    style.apply_style()
    h, w = img8.shape
    fig = plt.figure(figsize=(w / dpi, h / dpi), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    # float [0,1] with explicit limits: matplotlib 3.11 autoscales uint8
    # arrays (no more implicit 0-255 mapping) and the stretch would be lost
    ax.imshow(img8.astype(np.float32) / 255.0, cmap="gray", origin="lower",
              vmin=0.0, vmax=1.0)
    ax.set_xlim(-0.5, w - 0.5)
    ax.set_ylim(-0.5, h - 0.5)
    ax.set_axis_off()
    if sn_xy is not None:
        x, y = sn_xy
        r = 0.06 * min(w, h) * marker_scale
        lw = max(1.5, 1.5 * marker_scale)
        mark = plt.Circle((x, y), r, fill=False, color=style.ACCENT, lw=lw)
        ax.add_patch(mark)
        ax.plot([x - 1.6 * r, x - 0.5 * r], [y, y], color=style.ACCENT, lw=lw)
        ax.plot([x + 0.5 * r, x + 1.6 * r], [y, y], color=style.ACCENT, lw=lw)
        ax.plot([x, x], [y - 1.6 * r, y - 0.5 * r], color=style.ACCENT, lw=lw)
        ax.plot([x, x], [y + 0.5 * r, y + 1.6 * r], color=style.ACCENT, lw=lw)
        if label:
            ax.text(x, y + 1.8 * r, label, ha="center", color=style.ACCENT,
                    fontsize=11 * max(1.0, marker_scale * 0.8),
                    fontweight="bold")
    if caption:
        ax.text(0.01, 0.985, caption, ha="left", va="top", color=style.FG,
                fontsize=10, transform=ax.transAxes,
                bbox=dict(facecolor=style.BG, alpha=0.6, edgecolor="none",
                          pad=2))
    if watermark:
        ax.text(0.99, 0.01, watermark, ha="right", va="bottom",
                color=style.MUTED, fontsize=8, alpha=0.8,
                transform=ax.transAxes)
    return fig


def _fig_to_image(fig):
    # Rasterizes a frame figure into a PIL RGB image (RGB keeps the orange
    # SN marker distinguishable inside the GIF; grayscale would wash it out).
    # The buffer must be copied BEFORE closing the figure, otherwise we
    # read freed memory (shows up as black frames depending on allocator
    # state — nasty and flaky).
    fig.canvas.draw()
    buf = np.asarray(fig.canvas.buffer_rgba())
    img = Image.fromarray(buf[:, :, :3].copy())
    plt.close(fig)
    return img


def _downscale8(img8, target_wh=None, max_dim=GIF_MAX):
    # Shrinks a uint8 frame for GIF output (PIL, keeps aspect).
    # @args: img8 - uint8 2D array, target_wh - exact (w, h) to force
    #        (keeps the aligned pair pixel-locked), max_dim - size cap
    h, w = img8.shape
    if target_wh is None:
        if max(h, w) <= max_dim:
            return img8
        k = max(h, w) / max_dim
        target_wh = (round(w / k), round(h / k))
    pil = Image.fromarray(img8, mode="L")
    return np.asarray(pil.resize(target_wh, Image.LANCZOS))


def _blink_frames(ref8, obs8, sn_xy, effect, name, ref_label, watermark,
                  lang, observatory, zoom, marker_scale, interval_ms):
    # Shared frame pipeline for the animated exports (GIF and MP4).
    # @args: same as make_blink_gif
    # @return: (list of PIL RGB frames, dwell per frame in ms)
    ref8, sn_ref = crop_zoom(ref8, sn_xy, zoom)
    obs8, sn_obs = crop_zoom(obs8, sn_xy, zoom)
    h, w = obs8.shape
    if max(h, w) > GIF_MAX:
        k = max(h, w) / GIF_MAX
        target = (round(w / k), round(h / k))
        rh, rw = ref8.shape
        ref8 = _downscale8(ref8, target)
        obs8 = _downscale8(obs8, target)
        if sn_obs is not None:
            sn_obs = (sn_obs[0] * target[0] / w, sn_obs[1] * target[1] / h)
        if sn_ref is not None:
            sn_ref = (sn_ref[0] * target[0] / rw, sn_ref[1] * target[1] / rh)
    # frames of the pair share the crop origin; use the observatory's coords
    sn_xy = sn_obs if sn_obs is not None else sn_ref
    before, after = captions(lang, ref_label, observatory)
    frames = []
    if effect == "fade":
        alphas = [i / FADE_STEPS for i in range(FADE_STEPS + 1)]
        alphas += alphas[-2::-1]
        for a in alphas:
            mixed = ((1.0 - a) * ref8 + a * obs8).astype(np.uint8)
            cap = before if a < 0.5 else after
            frames.append(_fig_to_image(_frame_fig(
                mixed, sn_xy, name, cap, watermark, marker_scale)))
        duration = FADE_MS
    else:
        for img, cap in ((ref8, before), (obs8, after)):
            frames.append(_fig_to_image(_frame_fig(
                img, sn_xy, name, cap, watermark, marker_scale)))
        duration = interval_ms or BLINK_MS
    return frames, duration


def make_blink_gif(ref8, obs8, sn_xy, out, effect="blink", name="",
                   ref_label="", watermark="NightScribe", lang="es",
                   observatory="", zoom=1, marker_scale=1.0, interval_ms=None):
    # Animated GIF of the aligned pair: hard blink or smooth cross-fade.
    # @args: ref8, obs8 - uint8 arrays (same shape), sn_xy - SN pixel,
    #        out - GIF path, effect - "blink" | "fade", name - SN label,
    #        ref_label - survey caption, watermark - footer,
    #        lang - caption language ("es"|"en"), observatory - obs name,
    #        zoom - crop factor around the SN, marker_scale - marker size,
    #        interval_ms - blink dwell in ms (default BLINK_MS)
    # @return: output Path
    frames, duration = _blink_frames(
        ref8, obs8, sn_xy, effect, name, ref_label, watermark, lang,
        observatory, zoom, marker_scale, interval_ms)
    # GIF encoder quirk: mixed L/P frames can lose a local palette and come
    # out black; uniform RGB frames keep every frame intact
    frames[0].save(str(out), save_all=True, append_images=frames[1:],
                   duration=duration, loop=0)
    logger.info("blink GIF (%s) written to %s", effect, out)
    return out


def make_blink_video(ref8, obs8, sn_xy, out, effect="blink", name="",
                     ref_label="", watermark="NightScribe", lang="es",
                     observatory="", zoom=1, marker_scale=1.0,
                     interval_ms=None, fps=VIDEO_FPS,
                     min_seconds=VIDEO_MIN_S):
    # MP4 (H.264) version of the blink GIF, for sites that reject GIFs:
    # same frames and timing, encoded with the imageio-ffmpeg binary.
    # @args: same as make_blink_gif, plus fps - video frame rate,
    #        min_seconds - the blink cycle repeats until the clip lasts
    #        at least this long (videos do not auto-loop like GIFs)
    # @return: output Path
    import imageio_ffmpeg
    frames, duration = _blink_frames(
        ref8, obs8, sn_xy, effect, name, ref_label, watermark, lang,
        observatory, zoom, marker_scale, interval_ms)
    cycle_ms = duration * len(frames)
    loops = max(1, -(-int(min_seconds * 1000) // cycle_ms))  # ceil
    frames = frames * loops
    w, h = frames[0].size
    if w % 2 or h % 2:
        # H.264 yuv420p needs even dimensions: pad with a 1 px black edge
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
    logger.info("blink video (%s, %d loops) written to %s", effect, loops, out)
    return out


def draw_pair(ref8, obs8, sn_xy, name="", ref_label="", out=None,
              watermark="NightScribe", lang="es", observatory="", zoom=1,
              marker_scale=1.0):
    # Side-by-side before/after PNG with the SN marked on both panels;
    # this is the image meant to join the social post (ADR-016).
    # @args: ref8, obs8 - uint8 arrays, sn_xy - SN pixel, name - SN label,
    #        ref_label - survey caption, out - PNG path, watermark - footer,
    #        lang - caption language, observatory - observatory name,
    #        zoom - crop factor around the SN, marker_scale - marker size
    # @return: matplotlib figure (and writes PNG if out is given)
    ref8, sn_ref = crop_zoom(ref8, sn_xy, zoom)
    obs8, sn_obs = crop_zoom(obs8, sn_xy, zoom)
    before, after = captions(lang, ref_label, observatory)
    style.apply_style()
    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(12, 6.3), dpi=100)
    fig.patch.set_facecolor(style.BG)
    for ax, img, sn, title in ((ax0, ref8, sn_ref, before),
                               (ax1, obs8, sn_obs, after)):
        ax.imshow(img.astype(np.float32) / 255.0, cmap="gray", origin="lower",
                  vmin=0.0, vmax=1.0)
        if sn is not None:
            x, y = sn
            h, w = img.shape
            r = 0.06 * min(w, h) * marker_scale
            lw = max(1.5, 1.5 * marker_scale)
            ax.add_patch(plt.Circle((x, y), r, fill=False,
                                    color=style.ACCENT, lw=lw))
            ax.annotate(name, (x, y + 1.8 * r), ha="center",
                        color=style.ACCENT,
                        fontsize=10 * max(1.0, marker_scale * 0.8),
                        fontweight="bold")
        ax.set_title(title, color=style.FG, fontsize=10, loc="left")
        ax.set_xticks([])
        ax.set_yticks([])
    fig.suptitle(name, color=style.FG, fontsize=13, fontweight="bold",
                 x=0.02, ha="left")
    style.watermark(fig, watermark)
    if out:
        style.save(fig, out)
        logger.info("blink pair written to %s", out)
    return fig
