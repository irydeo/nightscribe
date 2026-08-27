############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Supernova field chart (reference cutout + crosshair)
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

from . import style

logger = logging.getLogger(__name__)

# Supernova field: reference cutout with the SN position marked; optional
# side-by-side with the observatory's own image (see ADR-016 / docs/VIZ).


def draw_sn_field(cutout_path, sn_name="", out=None, fmt="instagram",
                  watermark="NightScribe", size=None):
    # @args: cutout_path - local JPEG Path (or None), sn_name - label,
    #        out - PNG path, fmt - size preset, watermark - footer text,
    #        size - (w, h) px override (panel re-render mode)
    # @return: matplotlib figure (and writes PNG if out is given)
    fig, ax = style.new_fig(fmt, size=size)
    if cutout_path:
        img = plt.imread(str(cutout_path))
        ax.imshow(img)
        h, w = img.shape[0], img.shape[1]
        # crosshair at the SN position (centre of the requested cutout)
        cx, cy = w / 2, h / 2
        ax.plot([cx - w * 0.09, cx - w * 0.03], [cy, cy], color=style.ACCENT,
                lw=1.5)
        ax.plot([cx + w * 0.03, cx + w * 0.09], [cy, cy], color=style.ACCENT,
                lw=1.5)
        ax.plot([cx, cx], [cy - h * 0.09, cy - h * 0.03], color=style.ACCENT,
                lw=1.5)
        ax.plot([cx, cx], [cy + h * 0.03, cy + h * 0.09], color=style.ACCENT,
                lw=1.5)
        ax.annotate(sn_name, (cx, cy - h * 0.11), ha="center",
                    color=style.ACCENT, fontsize=11, fontweight="bold")
    else:
        ax.text(0.5, 0.5, "Campo no disponible / Field unavailable",
                ha="center", va="center", transform=ax.transAxes,
                color=style.MUTED)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(f"{sn_name} — campo / field" if sn_name else "Campo / Field",
                 loc="left")
    style.watermark(fig, watermark + " · DESI Legacy Survey")
    if out:
        style.save(fig, out)
        logger.info("sn field written to %s", out)
    return fig


def draw_sn_blink(reference_path, obs_path, sn_name="", out=None,
                  watermark="NightScribe"):
    # Side-by-side: survey reference vs. the observatory's own image.
    # @args: reference_path - cutout JPEG, obs_path - user's image,
    #        sn_name - label, out - PNG path, watermark - footer
    # @return: matplotlib figure (and writes PNG if out is given)
    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(12, 6.3), dpi=100)
    style.apply_style()
    fig.patch.set_facecolor(style.BG)
    for ax, path, title in ((ax0, reference_path, "Antes / Before (referencia)"),
                            (ax1, obs_path, "Después / After (Z41)")):
        if path:
            ax.imshow(plt.imread(str(path)))
        else:
            ax.text(0.5, 0.5, "—", ha="center", va="center",
                    transform=ax.transAxes, color=style.MUTED)
        ax.set_title(title, color=style.FG, fontsize=10, loc="left")
        ax.set_xticks([])
        ax.set_yticks([])
    fig.suptitle(sn_name, color=style.FG, fontsize=13, fontweight="bold",
                 x=0.02, ha="left")
    style.watermark(fig, watermark)
    if out:
        style.save(fig, out)
        logger.info("sn blink written to %s", out)
    return fig
