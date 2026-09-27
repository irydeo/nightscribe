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

from ..core import stretch as _stretch
from . import style

logger = logging.getLogger(__name__)

# Renders of the aligned blink pair (user image + geometry-matched survey
# cutout, see core/blink.py): stretches, side-by-side PNG, animated GIF.
# Frames are drawn with matplotlib (ADR-010) and assembled with Pillow.

# ADR-044 (phase B): the stretch engine lives in core/stretch.py now; the
# names below are thin compatibility re-exports so legacy callers (this
# module included) keep working byte-identical.
auto_limits = _stretch.auto_limits
apply_stretch = _stretch.apply_stretch
auto_gain = _stretch.auto_gain
apply_gain = _stretch.apply_gain
to_uint8 = _stretch.to_uint8

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


def _draw_marker(ax, sn_xy, w, h, label, marker_scale=1.0,
                 marker_style="ring"):
    # The SN marker in one place (ADR-046): "ring" is the classic circle
    # with four ticks, "cross" the full-frame crosshair with a central
    # box in the spirit of the tracker charts.
    # @args: ax - the frame axes, sn_xy - (x, y) or None, w, h - frame
    #        size in px, label - SN name, marker_scale - size multiplier,
    #        marker_style - "ring" | "cross"
    if sn_xy is None:
        return
    x, y = sn_xy
    if marker_style == "cross":
        half = 0.025 * min(w, h) * marker_scale
        gap = half * 1.4
        lw = max(1.0, 1.1 * marker_scale)
        for xs, ys in (([-0.5, x - gap], [y, y]), ([x + gap, w - 0.5], [y, y]),
                       ([x, x], [-0.5, y - gap]), ([x, x], [y + gap, h - 0.5])):
            ax.plot(xs, ys, color=style.ACCENT, lw=lw,
                    solid_capstyle="butt")
        ax.add_patch(plt.Rectangle((x - half, y - half), 2 * half,
                                   2 * half, fill=False,
                                   edgecolor=style.ACCENT,
                                   lw=max(1.2, 1.3 * marker_scale)))
        r = half
    else:
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


def _draw_corner_boxes(ax, boxes, caption=""):
    # The metadata corner boxes (ADR-046): one monospace text per corner
    # over a dark plate, in the spirit of the tracker charts. The frame
    # caption heads the top-left box so both stay readable.
    # @args: ax - the frame axes, boxes - chart_annotate.build_boxes
    #        dict, caption - the before/after frame caption
    tl = list(boxes.get("top_left", []))
    if caption:
        tl = [caption] + tl
    corners = (("top_left", tl, 0.008, 0.99, "left", "top"),
               ("top_right", boxes.get("top_right", []), 0.992, 0.99,
                "right", "top"),
               ("bottom_left", boxes.get("bottom_left", []), 0.008, 0.01,
                "left", "bottom"))
    for _key, lines, x, y, ha, va in corners:
        if not lines:
            continue
        ax.text(x, y, "\n".join(lines), ha=ha, va=va, color=style.FG,
                fontsize=8.5, family="monospace", transform=ax.transAxes,
                bbox=dict(facecolor=style.BG, alpha=0.75,
                          edgecolor=style.MUTED, linewidth=0.6, pad=3.5))


def compass_angles(wcs):
    # North and east on-screen angles for a plate WCS, computed
    # numerically so rotation AND mirror both come out right.
    # @args: wcs - core.wcs.Wcs of the shown frame
    # @return: (north_deg, east_deg), from the frame's up axis, positive
    #          toward the right (matplotlib's y-up convention)
    import math
    cx, cy = wcs.naxis1 / 2.0, wcs.naxis2 / 2.0
    ra0, dec0 = wcs.pixel_to_sky(cx, cy)
    ra_c, dec_c = wcs.pixel_to_sky(cx + 1.0, cy)
    ra_r, dec_r = wcs.pixel_to_sky(cx, cy + 1.0)
    cosd = math.cos(math.radians(dec0))
    # sky tangent basis (east, north) per display pixel (x right, y up)
    ex, ey = (ra_c - ra0) * cosd, dec_c - dec0
    nx, ny = (ra_r - ra0) * cosd, dec_r - dec0
    det = ex * ny - nx * ey
    if abs(det) < 1e-18:
        return 0.0, -90.0
    inv = np.array([[ny, -nx], [-ey, ex]]) / det
    v_n = inv @ np.array([0.0, 1.0])      # display vector pointing north
    v_e = inv @ np.array([1.0, 0.0])      # display vector pointing east
    return (math.degrees(math.atan2(v_n[0], v_n[1])),
            math.degrees(math.atan2(v_e[0], v_e[1])))


def pair_compass(pair):
    # @args: pair - core/blink.prepare_pair's dict
    # @return: compass_angles of the pair's frames (the WCS the pair
    #          carries already matches their orientation, flip
    #          included), or None when the pair carries no WCS
    w = pair.get("wcs")
    if w is None:
        return None
    return compass_angles(w)


def pair_boxes(pair, meta, site, scale_arcsec_px=None):
    # The corner boxes for a blink export (ADR-046): name, date,
    # exposure, the SN position and the plate scale. The FOV stays out:
    # the zoom crops make it meaningless here.
    # @args: pair - prepare_pair's dict, meta - fits_meta.meta_from_header
    #        of the observed plate, site - chart_annotate.site_from_config
    #        output, scale_arcsec_px - the source plate's scale when the
    #        caller knows it (the pair's WCS is the work frame's,
    #        possibly downscaled); None reads the pair's
    # @return: the build_boxes dict
    from ..core import chart_annotate
    wcs_info = None
    w = pair.get("wcs")
    scale = scale_arcsec_px or (w.pixel_scale() if w is not None else None)
    if w is not None or scale is not None:
        wcs_info = {}
        if scale:
            wcs_info["scale_arcsec_px"] = scale
        if pair.get("ra") is not None and pair.get("dec") is not None:
            wcs_info["ra_deg"] = pair["ra"]
            wcs_info["dec_deg"] = pair["dec"]
    return chart_annotate.build_boxes(name=pair.get("name"), meta=meta,
                                      wcs_info=wcs_info, site=site)


def _draw_compass(ax, angles, w, h):
    # The N/E mini-compass at the bottom centre of a frame (ADR-046).
    # @args: ax - the frame axes, angles - compass_angles output,
    #        w, h - frame size in px (for the aspect-corrected length)
    import math
    an, ae = angles
    cx, cy, length = 0.5, 0.075, 0.05
    aspect = w / max(h, 1)
    for label, ang in (("N", an), ("E", ae)):
        dx = math.sin(math.radians(ang)) * length
        dy = math.cos(math.radians(ang)) * length * aspect
        ax.annotate("", xy=(cx + dx, cy + dy), xytext=(cx - dx, cy - dy),
                    xycoords="axes fraction",
                    arrowprops=dict(arrowstyle="-|>", color=style.FG,
                                    lw=1.2))
        ax.text(cx + dx * 1.5, cy + dy * 1.5, label, color=style.FG,
                fontsize=8, ha="center", va="center",
                transform=ax.transAxes)


def _frame_fig(img8, sn_xy, label, caption, watermark, marker_scale=1.0,
               dpi=100, boxes=None, marker_style="ring", compass=None):
    # Builds one frame: stretched image + SN marker + captions.
    # @args: img8 - uint8 2D array, sn_xy - (x, y) or None, label - SN name,
    #        caption - frame caption, watermark - footer text,
    #        marker_scale - multiplier for the marker size,
    #        boxes - chart_annotate corner boxes dict (ADR-046; the
    #        caption joins the top-left box), marker_style - "ring" |
    #        "cross", compass - compass_angles output or None
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
    _draw_marker(ax, sn_xy, w, h, label, marker_scale, marker_style)
    if boxes is not None:
        _draw_corner_boxes(ax, boxes, caption)
        if compass is not None:
            _draw_compass(ax, compass, w, h)
    elif caption:
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
                  lang, observatory, zoom, marker_scale, interval_ms,
                  boxes=None, marker_style="ring", compass=None):
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
                mixed, sn_xy, name, cap, watermark, marker_scale,
                boxes=boxes, marker_style=marker_style, compass=compass)))
        duration = FADE_MS
    else:
        for img, cap in ((ref8, before), (obs8, after)):
            frames.append(_fig_to_image(_frame_fig(
                img, sn_xy, name, cap, watermark, marker_scale,
                boxes=boxes, marker_style=marker_style, compass=compass)))
        duration = interval_ms or BLINK_MS
    return frames, duration


def make_blink_gif(ref8, obs8, sn_xy, out, effect="blink", name="",
                   ref_label="", watermark="NightScribe", lang="es",
                   observatory="", zoom=1, marker_scale=1.0, interval_ms=None,
                   boxes=None, marker_style="ring", compass=None):
    # Animated GIF of the aligned pair: hard blink or smooth cross-fade.
    # @args: ref8, obs8 - uint8 arrays (same shape), sn_xy - SN pixel,
    #        out - GIF path, effect - "blink" | "fade", name - SN label,
    #        ref_label - survey caption, watermark - footer,
    #        lang - caption language ("es"|"en"), observatory - obs name,
    #        zoom - crop factor around the SN, marker_scale - marker size,
    #        interval_ms - blink dwell in ms (default BLINK_MS),
    #        boxes - chart_annotate corner boxes dict (ADR-046) or None,
    #        marker_style - "ring" | "cross", compass - compass_angles
    #        output or None
    # @return: output Path
    frames, duration = _blink_frames(
        ref8, obs8, sn_xy, effect, name, ref_label, watermark, lang,
        observatory, zoom, marker_scale, interval_ms, boxes=boxes,
        marker_style=marker_style, compass=compass)
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
                     min_seconds=VIDEO_MIN_S,
                     boxes=None, marker_style="ring", compass=None):
    # MP4 (H.264) version of the blink GIF, for sites that reject GIFs:
    # same frames and timing, encoded with the imageio-ffmpeg binary.
    # @args: same as make_blink_gif, plus fps - video frame rate,
    #        min_seconds - the blink cycle repeats until the clip lasts
    #        at least this long (videos do not auto-loop like GIFs),
    #        and the ADR-046 boxes / marker_style / compass
    # @return: output Path
    import imageio_ffmpeg
    frames, duration = _blink_frames(
        ref8, obs8, sn_xy, effect, name, ref_label, watermark, lang,
        observatory, zoom, marker_scale, interval_ms, boxes=boxes,
        marker_style=marker_style, compass=compass)
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
              marker_scale=1.0, boxes=None, marker_style="ring",
              compass=None):
    # Side-by-side before/after PNG with the SN marked on both panels;
    # this is the image meant to join the social post (ADR-016).
    # @args: ref8, obs8 - uint8 arrays, sn_xy - SN pixel, name - SN label,
    #        ref_label - survey caption, out - PNG path, watermark - footer,
    #        lang - caption language, observatory - observatory name,
    #        zoom - crop factor around the SN, marker_scale - marker size,
    #        boxes - chart_annotate corner boxes dict (ADR-046; drawn on
    #        the after panel, the observed plate), marker_style - "ring" |
    #        "cross", compass - compass_angles output or None
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
        h, w = img.shape
        _draw_marker(ax, sn, w, h, name, marker_scale, marker_style)
        ax.set_title(title, color=style.FG, fontsize=10, loc="left")
        ax.set_xticks([])
        ax.set_yticks([])
    if boxes is not None:
        _draw_corner_boxes(ax1, boxes)
        if compass is not None:
            _draw_compass(ax1, compass, w, h)
    fig.suptitle(name, color=style.FG, fontsize=13, fontweight="bold",
                 x=0.02, ha="left")
    style.watermark(fig, watermark)
    if out:
        style.save(fig, out)
        logger.info("blink pair written to %s", out)
    return fig
