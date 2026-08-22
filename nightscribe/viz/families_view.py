############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Solar system families chart ("you are here")
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

# Radial bands of the solar system families with a "you are here" marker.

_BANDS = [
    ("NEOs", 0.6, 1.3, style.DANGER),
    ("Cinturón / Belt", 2.06, 3.28, style.MUTED),
    ("Hilda", 3.7, 4.2, style.MUTED),
    ("Troyanos / Trojans", 5.0, 5.4, style.ACCENT2),
    ("Centauros / Centaurs", 5.5, 30.0, "#7d6bc9"),
    ("TNOs", 30.0, 50.0, "#4f8a8b"),
]


def draw_families(family, obj_name="", a=None, out=None, fmt="instagram",
                  watermark="NightScribe"):
    # @args: family - key from orbits.classify, obj_name - label,
    #        a - semi-major axis (AU) for the marker, out - PNG path,
    #        fmt - size preset, watermark - footer
    # @return: matplotlib figure (and writes PNG if out is given)
    import matplotlib.pyplot as plt
    from matplotlib.patches import Wedge

    fig, ax = style.new_fig(fmt)
    ax.set_aspect("equal")

    # log scale radii so the inner system stays readable
    def radius(au):
        import math
        return math.log10(max(au, 0.2))

    r_max = radius(50)
    for label, a0, a1, color in _BANDS:
        w = Wedge((0, 0), radius(a1), 0, 360, width=radius(a1) - radius(a0),
                  facecolor=color, alpha=0.22, edgecolor=color, lw=0.6)
        ax.add_patch(w)
        ax.text(0, radius((a0 + a1) / 2), label, ha="center", va="center",
                color=style.FG, fontsize=8)

    ax.plot(0, 0, "o", color=style.SUN, ms=10)
    ax.annotate("Sol / Sun", (0, 0), textcoords="offset points",
                xytext=(6, -10), color=style.SUN, fontsize=8)

    if a:
        import math
        rr = radius(a)
        mx, my = rr * math.cos(math.radians(45)), rr * math.sin(math.radians(45))
        ax.plot(mx, my, "o", color=style.ACCENT, ms=12, zorder=8)
        ax.annotate(f"{obj_name} — aquí / you are here", (mx, my),
                    textcoords="offset points", xytext=(10, 8),
                    color=style.ACCENT, fontsize=9, fontweight="bold")
    ax.set_xlim(-r_max * 1.1, r_max * 1.1)
    ax.set_ylim(-r_max * 1.1, r_max * 1.1)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title("¿Dónde vive? / Where does it live?", loc="left")
    style.watermark(fig, watermark)
    if out:
        style.save(fig, out)
        logger.info("families chart written to %s", out)
    return fig
