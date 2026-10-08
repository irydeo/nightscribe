############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Centred sequence of the observations (ADR-062, 5.4)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The one-glance proof: the object in every observation.

Each group's stack is cropped around its own reference point and the crops
are strung into a GIF (or a montage PNG), so the asteroid sits still in the
middle while the stars crawl. If it is there in every panel, the detection
is solid; if one panel is empty, the eye catches it before the MPC does.

It reuses the project's stretch (`core/stretch.py`) so the panels look like
the ones in the editor, and Pillow to write the file (already a
dependency; no ffmpeg needed for a GIF).
"""

import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


def _stretch_to_uint8(img, black=None, white=None, gamma=1.0):
    # @args: img - the crop, black/white - the display range (percentiles
    #        when None), gamma - the display gamma
    # @return: uint8 image
    data = np.asarray(img, dtype=np.float32)
    finite = data[np.isfinite(data)]
    if finite.size == 0:
        return np.zeros(data.shape, dtype=np.uint8)
    if black is None or white is None:
        lo, hi = np.percentile(finite, (5.0, 99.5))
    else:
        lo, hi = black, white
    if hi <= lo:
        hi = lo + 1.0
    out = np.clip((data - lo) / (hi - lo), 0.0, 1.0) ** float(gamma)
    return (out * 255.0).astype(np.uint8)


def _crop(img, center, size):
    # @args: img - the image, center - (x, y), size - the side in px
    # @return: the crop (padded with its own median when it falls outside)
    half = size // 2
    x0 = int(round(center[0])) - half
    y0 = int(round(center[1])) - half
    h, w = img.shape
    out = np.full((size, size), float(np.median(img)), dtype=np.float32)
    sx0, sy0 = max(0, x0), max(0, y0)
    sx1, sy1 = min(w, x0 + size), min(h, y0 + size)
    if sx1 > sx0 and sy1 > sy0:
        out[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = img[sy0:sy1, sx0:sx1]
    return out


def centered_sequence(images, centers, out_path, size=192, fmt="gif",
                      duration_ms=700, gamma=0.7, label=None):
    # @args: images - one stack per observation, centers - the object's
    #        position in each, out_path - where to write, size - the panel
    #        side, fmt - "gif" or "png" (montage), duration_ms - per panel,
    #        gamma - display gamma, label - optional per-panel text
    # @return: the path written
    # The SAME black/white range for every panel: auto-stretching each one
    # separately would make a faint panel look as bright as a real one,
    # which is exactly the illusion this figure exists to break.
    from PIL import Image, ImageDraw
    if not images:
        raise ValueError("no images to show")
    crops = [_crop(np.asarray(img, dtype=np.float32), c, size)
             for img, c in zip(images, centers)]
    flat = np.concatenate([c.ravel() for c in crops])
    lo, hi = np.percentile(flat[np.isfinite(flat)], (5.0, 99.5))
    panels = [Image.fromarray(_stretch_to_uint8(c, lo, hi, gamma), mode="L")
              for c in crops]
    if label:
        for panel, text in zip(panels, label):
            draw = ImageDraw.Draw(panel)
            draw.text((4, 4), str(text), fill=255)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "png":
        cols = min(4, len(panels))
        rows = int(np.ceil(len(panels) / cols))
        montage = Image.new("L", (cols * size, rows * size), 0)
        for i, panel in enumerate(panels):
            montage.paste(panel, ((i % cols) * size, (i // cols) * size))
        montage.save(str(out))
    else:
        panels[0].save(str(out), save_all=True, append_images=panels[1:],
                       duration=duration_ms, loop=0)
    logger.info("centred sequence written: %s (%d panels)", out, len(panels))
    return str(out)
