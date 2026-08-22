############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Visual style module (see docs/VIZ)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import matplotlib

# One style for every chart, used by the GUI canvas and the PNG exports
# alike (see ADR-010). Dark space theme, consistent accents.

BG = "#0b0d17"
FG = "#e8eaf2"
ACCENT = "#ffb347"      # warm orange: the object
ACCENT2 = "#6ec1ff"     # cool blue: Earth
MUTED = "#8a90a6"       # labels and grids
SUN = "#ffd76e"
DANGER = "#ff6b6b"

SIZES = {"instagram": (1080, 1080), "facebook": (1200, 630)}


def apply_style():
    # Sets the NightScribe matplotlib rcParams. Call once at import.
    matplotlib.rcParams.update({
        "figure.facecolor": BG,
        "axes.facecolor": BG,
        "savefig.facecolor": BG,
        "axes.edgecolor": MUTED,
        "axes.labelcolor": FG,
        "text.color": FG,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "grid.color": MUTED,
        "grid.alpha": 0.25,
        "font.size": 11,
        "axes.titlesize": 14,
        "axes.titleweight": "bold",
    })


def new_fig(fmt="instagram", dpi=100):
    # @args: fmt - "instagram" | "facebook", dpi - output dpi
    # @return: (fig, ax) with the NightScribe style applied
    apply_style()
    w, h = SIZES.get(fmt, SIZES["instagram"])
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(w / dpi, h / dpi), dpi=dpi)
    return fig, ax


def watermark(fig, text):
    # Small footer with the observatory signature.
    # @args: fig - matplotlib figure, text - e.g. "NightScribe · Irydeo"
    if not text:
        return
    fig.text(0.99, 0.01, text, ha="right", va="bottom",
             color=MUTED, fontsize=8, alpha=0.8)


def save(fig, path):
    # @args: fig - matplotlib figure, path - output PNG path
    fig.savefig(path, dpi=fig.dpi, facecolor=fig.get_facecolor(),
                bbox_inches="tight")
