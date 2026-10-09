############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Animated exports: GIF and MP4 writers (ADR-062)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""One place to turn a list of frames into a shareable animation.

A GIF is written with Pillow (already a dependency, and it loops by itself);
an MP4 is encoded with the static ffmpeg binary that imageio-ffmpeg ships,
because a social site that rejects a GIF still takes an H.264 clip.

The two used to be written by hand in the blink and the evolution renders
(blink_view.make_blink_video, evolution_view.make_evolution_video) with the
same block copied twice: even dimensions for yuv420p, a minimum duration so a
six-second clip does not flash by, the same encoder flags. It lives here so a
third caller (the astrometry tab's animation) does not make it a third copy.

The frames are PIL RGB images, all the same size.
"""

import logging
from pathlib import Path

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

VIDEO_FPS = 30          # MP4 frame rate
VIDEO_MIN_S = 6.0       # videos do not loop like GIFs: repeat the cycle


def write_gif(frames, out, duration_ms=700):
    # Animated, looping GIF of the frames (Pillow).
    # @args: frames - list of PIL RGB images (same size), out - path,
    #        duration_ms - dwell per frame
    # @return: the path written
    if not frames:
        raise ValueError("no frames to write")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    # GIF encoder quirk (the blink render already documents it): mixed L/P
    # frames can lose a local palette and come out black, so every frame is
    # forced to RGB and the palette is built once for the whole animation.
    frames[0].save(str(out), save_all=True, append_images=frames[1:],
                   duration=duration_ms, loop=0)
    logger.info("animation GIF written: %s (%d frames)", out, len(frames))
    return out


def write_mp4(frames, out, duration_ms=700, fps=VIDEO_FPS,
              min_seconds=VIDEO_MIN_S):
    # MP4 (H.264) version of the frames, for sites that reject GIFs.
    # @args: frames - list of PIL RGB images (same size), out - path,
    #        duration_ms - dwell per frame, fps - video frame rate,
    #        min_seconds - the cycle repeats until the clip lasts at least
    #        this long (videos do not auto-loop like GIFs)
    # @return: the path written
    if not frames:
        raise ValueError("no frames to write")
    import imageio_ffmpeg
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cycle_ms = duration_ms * len(frames)
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
    per_frame = max(1, round(fps * duration_ms / 1000))
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
    logger.info("animation video (%d loops) written: %s", loops, out)
    return out
