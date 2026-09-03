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
                  watermark="NightScribe", size=None, lang="es"):
    # @args: cutout_path - local JPEG Path (or None), sn_name - label,
    #        out - PNG path, fmt - size preset, watermark - footer,
    #        size - (w, h) px override (panel re-render mode),
    #        lang - string language ("es"|"en"); charts follow the UI language
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
        ax.text(0.5, 0.5,
                style.pick(lang, "Campo no disponible", "Field unavailable"),
                ha="center", va="center", transform=ax.transAxes,
                color=style.MUTED)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(
        style.pick(lang,
                   f"{sn_name} — campo" if sn_name else "Campo",
                   f"{sn_name} — field" if sn_name else "Field"),
        loc="left")
    style.watermark(fig, watermark + " · DESI Legacy Survey")
    if out:
        style.save(fig, out)
        logger.info("sn field written to %s", out)
    return fig


def draw_sn_blink(reference_path, obs_path, sn_name="", out=None,
                  watermark="NightScribe", lang="es"):
    # Side-by-side: survey reference vs. the observatory's own image.
    # @args: reference_path - cutout JPEG, obs_path - user's image,
    #        sn_name - label, out - PNG path, watermark - footer,
    #        lang - string language ("es"|"en")
    # @return: matplotlib figure (and writes PNG if out is given)
    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(12, 6.3), dpi=100)
    style.apply_style()
    fig.patch.set_facecolor(style.BG)
    titles = (style.pick(lang, "Antes (referencia)", "Before (reference)"),
              style.pick(lang, "Después (Z41)", "After (Z41)"))
    for ax, path, title in ((ax0, reference_path, titles[0]),
                            (ax1, obs_path, titles[1])):
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
