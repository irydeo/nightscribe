############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - The night's conditions as a figure (phase A1)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Two small figures that explain a light curve as much as the curve does.

A night that "came out noisy" usually has a reason, and the reason is
written in two places the observer rarely looks at:

  * the AIRMASS, which says how much atmosphere each point had to cross
    (a curve that fades and comes back is often the sky, not the star);
  * the POSITION, which says what the telescope did (a mount that drifts
    walks the stars across the flat-field, and a jump mid-series changes
    the aperture's neighbours).

Both are drawn as scientific figures (white, black frame, round ticks)
because they end up in the same report as the light curve. The values
themselves are computed by the series engine per point; this module only
arranges them into a picture.
"""

import logging
import math

import numpy as np

from ..core import ticks as ticks_mod

logger = logging.getLogger(__name__)

_FIGSIZE = (9.0, 3.4)
_DPI = 150


def _series(points, key):
    # The finite (time, value) pairs of one magnitude of the night, in
    # time order: what is missing must not become a zero.
    # @args: points - SeriesPoints or point dicts, key - the attribute name
    # @return: (times, values) as numpy arrays
    t, v = [], []
    for p in points or []:
        mjd = p.get("mjd") if isinstance(p, dict) else getattr(p, "mjd", None)
        val = p.get(key) if isinstance(p, dict) else getattr(p, key, None)
        if mjd is None or val is None:
            continue
        if not (math.isfinite(float(mjd)) and math.isfinite(float(val))):
            continue
        t.append(float(mjd))
        v.append(float(val))
    order = np.argsort(t) if t else []
    return np.asarray(t, dtype=float)[order], np.asarray(v, dtype=float)[order]


def draw_airmass(points, out=None, title="", subtitle="", lang="es"):
    # The airmass of every point: the honest "how low was it" of a night.
    #
    # The engine computes it from the site's coordinates and the target's
    # position, so a point without them simply is not drawn: inventing an
    # airmass would be worse than the empty chart.
    # @args: points - SeriesPoints with `mjd` and `airmass`, out - PNG
    #        path (None: the figure), title/subtitle - the figure's texts
    # @return: the figure, or the path
    t, air = _series(points, "airmass")
    return _figure(t, air, out=out, title=title or _L(lang, "Masa de aire",
                                                     "Airmass"),
                   subtitle=subtitle,
                   y_label=_L(lang, "Masa de aire (menos es mejor)",
                              "Airmass (lower is better)"),
                   lang=lang, kind="airmass")


def draw_drift(points, out=None, title="", subtitle="", lang="es",
               reference=None):
    # The position of the target through the night, in pixels.
    #
    # That position is the one the engine MEASURED on the reference grid,
    # so what this figure shows depends on how the series was measured,
    # and saying which is part of being honest:
    #
    #   * with the alignment OFF, it is the telescope's real drift (a
    #     series that moves tens of pixels walks its stars across the
    #     flat-field, and the sky residual changes with the night);
    #   * with the alignment ON, the drift has already been removed, so
    #     what is left is the GUIDE RESIDUAL: how far the centroid landed
    #     from where the alignment said it should. It is the figure that
    #     tells a good night from a jumpy one.
    #
    # The real drift of an aligned series is in the alignment block of the
    # run, and the panel says it there.
    # @args: as draw_airmass, plus reference - (x0, y0) to measure from
    #        (default: the first point)
    # @return: the figure, or the path
    t, x = _series(points, "x")
    _t2, y = _series(points, "y")
    if x.size == 0 or y.size != x.size:
        return _figure([], [], out=out,
                       title=title or _L(lang, "Deriva de posición",
                                         "Position drift"),
                       subtitle=subtitle, y_label="",
                       lang=lang, kind="drift")
    x0, y0 = reference if reference else (x[0], y[0])
    dx, dy = x - x0, y - y0
    return _figure(t, None, out=out,
                   title=title or _L(lang, "Deriva de posición",
                                     "Position drift"),
                   subtitle=subtitle,
                   y_label=_L(lang, "Posición medida (px)",
                              "Measured position (px)"),
                   lang=lang, kind="drift", extra={"dx": dx, "dy": dy})


def _L(lang, es, en):
    # @return: the string in the requested language
    return es if (lang or "es") != "en" else en


def _figure(t, y, out=None, title="", subtitle="", y_label="", lang="es",
            kind="airmass", extra=None):
    # One white scientific figure with the axis arithmetic of core/ticks.
    # @args: t - times, y - the single series (None when `extra` is used),
    #        out - PNG path, title/subtitle/y_label - the texts,
    #        kind - "airmass" | "drift", extra - {"dx","dy"} for the drift
    # @return: the figure, or the path when `out` is given
    import matplotlib
    matplotlib.use("Agg", force=False)
    import matplotlib.pyplot as plt

    t = np.asarray(t, dtype=float)
    y = None if y is None else np.asarray(y, dtype=float)
    fig, ax = plt.subplots(figsize=_FIGSIZE, dpi=_DPI)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    for spine in ax.spines.values():
        spine.set_color("black")
        spine.set_linewidth(1.1)
    ax.tick_params(direction="in", top=True, right=True, length=4,
                   colors="black", labelsize=9)

    if kind == "drift" and extra:
        ax.plot(t, extra["dx"], "-o", ms=3.0, lw=0.8, color="#1f3b73",
                label=_L(lang, "ΔX (px)", "ΔX (px)"))
        ax.plot(t, extra["dy"], "-s", ms=3.0, lw=0.8, color="#a8443a",
                label=_L(lang, "ΔY (px)", "ΔY (px)"))
        ax.axhline(0.0, color="#999999", lw=0.8)
    elif t.size:
        ax.plot(t, y, "-o", ms=3.0, lw=0.8, color="#1f3b73")
        # the airmass is read with the eye: the lower the better, and the
        # evening's rise is the part that usually explains a trend
        ax.invert_yaxis()
    else:
        ax.text(0.5, 0.5, _L(lang, "sin datos suficientes",
                             "not enough data"),
                transform=ax.transAxes, ha="center", va="center",
                color="#666666")

    values = np.empty(0)
    for candidate in ([y] if y is not None else []) + \
            ([extra["dx"], extra["dy"]] if extra else []):
        if candidate is not None and len(candidate):
            values = np.concatenate([values, np.asarray(candidate,
                                                        dtype=float)])
    if values.size:
        plan = ticks_mod.axis_plan(float(values.min()),
                                   float(values.max()), target=5)
        ax.set_ylim(values.min() - 0.05 * (values.max() - values.min() or 1),
                    values.max() + 0.05 * (values.max() - values.min() or 1))
        if kind == "airmass":
            ax.set_ylim(ax.get_ylim()[::-1])       # low airmass on top
        if plan["ticks"]:
            ax.set_yticks(plan["ticks"])
            ax.set_yticklabels(plan["labels"])
        if plan["offset_label"]:
            ax.text(0.995, 0.02, plan["offset_label"],
                    transform=ax.transAxes, ha="right", va="bottom",
                    fontsize=8)
    if t.size:
        xplan = ticks_mod.axis_plan(float(t.min()), float(t.max()), target=6)
        if xplan["ticks"]:
            ax.set_xticks(xplan["ticks"])
            ax.set_xticklabels(xplan["labels"])
        if xplan["offset_label"]:
            ax.text(0.0, -0.22, xplan["offset_label"],
                    transform=ax.transAxes, ha="left", va="top",
                    fontsize=8, color="#333333")

    ax.set_xlabel("MJD", fontsize=10, color="black")
    if y_label:
        ax.set_ylabel(y_label, fontsize=10, color="black")
    if title:
        ax.set_title(title, fontsize=12, color="black", loc="left",
                     pad=16 if subtitle else 6)
    if subtitle:
        ax.text(0.0, 1.02, subtitle, transform=ax.transAxes, fontsize=9,
                color="#333333", ha="left", va="bottom")
    if kind == "drift":
        ax.legend(fontsize=8.5, frameon=False, loc="upper left",
                  bbox_to_anchor=(1.01, 1.0))
    fig.tight_layout()
    if out:
        fig.savefig(out, dpi=_DPI, facecolor="white", bbox_inches="tight")
        plt.close(fig)
        logger.info("night figure written: %s", out)
        return out
    return fig
