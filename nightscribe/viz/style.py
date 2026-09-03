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

import logging
from pathlib import Path

import matplotlib

logger = logging.getLogger(__name__)

# One style for every chart, used by the GUI canvas and the PNG exports
# alike (see ADR-010). Dark space theme, consistent accents.

BG = "#0b0d17"
FG = "#e8eaf2"
ACCENT = "#ffb347"      # warm orange: the object
ACCENT2 = "#6ec1ff"     # cool blue: Earth
MUTED = "#8a90a6"       # labels and grids
SUN = "#ffd76e"
DANGER = "#ff6b6b"

SIZES = {"instagram": (1080, 1080), "facebook": (1200, 630),
         "panel": (1200, 675)}


def pick(lang, es, en):
    # Single-language string: exported charts follow the configured UI
    # language instead of hard-coding "es / en" (ADR-018, 2026-09-02).
    # @args: lang - "es"|"en" (default "es"), es / en - the two strings
    # @return: the Spanish one when lang is not "en", else the English
    if (lang or "es") == "en":
        return en
    return es


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


def new_fig(fmt="instagram", dpi=100, size=None):
    # @args: fmt - "instagram" | "facebook" | "panel", dpi - output dpi,
    #        size - (w, h) px overrides for the preset (the panel's
    #        re-render mode draws 2× for crispness in big slots)
    # @return: (fig, ax) with the NightScribe style applied
    apply_style()
    w, h = SIZES.get(fmt, SIZES["instagram"])
    if size:
        w, h = size
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(w / dpi, h / dpi), dpi=dpi)
    if fmt == "panel":
        # in-GUI chart: squeeze the default matplotlib margins down so the
        # plot owns the PNG (the wasted dark border is space for nothing)
        fig.subplots_adjust(left=0.06, right=0.985, top=0.855, bottom=0.115)
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
    p = Path(path)
    # Output folders are created on demand: a fresh install has none of them
    # yet and savefig() would raise if the parent dir is missing.
    p.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(p, dpi=fig.dpi, facecolor=fig.get_facecolor(),
                bbox_inches="tight")
