############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Exoplanet transit light curve chart
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import logging

from . import style

logger = logging.getLogger(__name__)

# Simple trapezoid light curve for posts: depth, duration and tonight's
# window (see docs/VIZ).


def draw_transit(transit, out=None, fmt="facebook", watermark="NightScribe"):
    # @args: transit - dict from transits.py, out - PNG path,
    #        fmt - size preset, watermark - footer
    # @return: matplotlib figure (and writes PNG if out is given)
    fig, ax = style.new_fig(fmt)

    depth = (transit.get("depth_mmag") or 10.0) / 1000.0  # mmag -> relative flux
    dur_h = transit.get("duration_h") or 2.0
    mid = transit["mid"]
    mid_h = mid.hour + mid.minute / 60.0

    # trapezoid: flat, linear drop, flat bottom, linear rise
    t_ing = dur_h * 0.15
    xs = [mid_h - dur_h / 2 - 0.5, mid_h - dur_h / 2, mid_h - dur_h / 2 + t_ing,
          mid_h + dur_h / 2 - t_ing, mid_h + dur_h / 2, mid_h + dur_h / 2 + 0.5]
    ys = [1.0, 1.0, 1.0 - depth, 1.0 - depth, 1.0, 1.0]
    ax.plot(xs, ys, color=style.ACCENT2, lw=2.2)
    ax.fill_between(xs, ys, 1.0, color=style.ACCENT2, alpha=0.15)

    star = transit.get("star") or ""
    depth_pct = depth * 100
    ax.set_title(f"{transit.get('name')} ({star})", loc="left")
    ax.set_xlabel("UTC (h)")
    ax.set_ylabel("Brillo relativo / Relative brightness")
    ax.set_ylim(1.0 - depth * 1.4, 1.001)
    ax.text(mid_h, 1.0 - depth * 1.15,
            f"−{depth_pct:.1f}% · {dur_h:.1f} h",
            ha="center", color=style.ACCENT, fontsize=10, fontweight="bold")
    ax.grid(True, alpha=0.2)
    style.watermark(fig, watermark)
    if out:
        style.save(fig, out)
        logger.info("transit chart written to %s", out)
    return fig
