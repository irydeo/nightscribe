############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Scientific figures for a report (quality plan, A1)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The white, publication-style figure a colleague or a journal expects.

The charts inside the application are dark, because a dark screen at night
protects the observer's adaptation. A figure that leaves the application,
however, is read on paper or in a report, and there the convention is the
opposite: white background, black frame, ticks pointing inwards, the
magnitude axis on round numbers and the error bars with caps.

That is the whole point of this module: the same numbers, drawn the way a
published light curve is drawn. It reuses `core/ticks` for the axis
arithmetic, so the round numbers and the decimals match what the panel
shows, and it follows the same honesty rules (a flagged point is marked,
a hand-excluded point is marked, nothing is silently dropped).
"""

import logging
import math

import numpy as np

from ..core import ticks as ticks_mod

logger = logging.getLogger(__name__)

# Cap size of an error bar, in points: the small horizontal stroke that
# turns a line into a measurement.
_CAP = 3.0
# The figure size in inches at 150 dpi: a single-column report figure.
_FIGSIZE = (9.0, 5.2)
_DPI = 150


def _plan(lo, hi, target=6):
    # The axis plan (ticks + labels) with the offset already taken out,
    # plus the limit the axis must show.
    # @args: lo, hi - the data range, target - desired number of ticks
    # @return: (limits, ticks, labels, offset_label)
    pad = (hi - lo) * 0.08 or 0.05
    limits = (lo - pad, hi + pad)
    plan = ticks_mod.axis_plan(limits[0], limits[1], target=target)
    if not plan["ticks"]:
        return limits, [], [], ""
    return limits, plan["ticks"], plan["labels"], plan["offset_label"]


def draw_scientific(points, out=None, title="", subtitle="", lang="es",
                    y_label=None, x_label=None, invert_y=True,
                    watermark="NightScribe", figsize=_FIGSIZE, dpi=_DPI):
    # A light curve as a published figure.
    #
    # Every point is drawn with its own error (the photon error when the
    # engine could compute it, the total otherwise); the flagged ones are
    # hollow, the hand-excluded ones are grey crosses, and the axis lands
    # on round magnitudes because a reader should never have to do
    # arithmetic to know how bright a star was.
    #
    # @args: points - [{"mjd", "mag", "err", "err_internal", "flags",
    #        "source", "filter"}], out - the PNG path (None: return the
    #        figure), title - the figure's title, subtitle - a second line
    #        (the object, the night, the instrument), lang - "es"|"en",
    #        y_label/x_label - axis labels, invert_y - magnitude axis
    #        (brighter up), watermark - the footer, figsize/dpi - the size
    # @return: the figure, or the path when `out` is given
    import matplotlib
    matplotlib.use("Agg", force=False)
    import matplotlib.pyplot as plt

    pts = [p for p in (points or []) if p.get("mjd") is not None
           and p.get("mag") is not None]
    es = (lang or "es") != "en"
    if y_label is None:
        y_label = self_label_y(es)
    if x_label is None:
        x_label = "MJD"

    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    for spine in ax.spines.values():
        spine.set_color("black")
        spine.set_linewidth(1.2)
    ax.tick_params(direction="in", top=True, right=True, length=5,
                   width=1.0, colors="black", labelsize=9)
    ax.grid(False)

    # three families, drawn in this order so nothing hides anything:
    # the measurements, the flagged ones and the hand-excluded ones
    drawn = {"plain": 0, "flagged": 0, "excluded": 0}
    for kind in ("plain", "flagged", "excluded"):
        sel = [p for p in pts if _kind_of(p) == kind]
        if not sel:
            continue
        xs = [p["mjd"] for p in sel]
        ys = [p["mag"] for p in sel]
        errs = [_bar_error(p) for p in sel]
        errs = [e if e is not None else float("nan") for e in errs]
        drawn[kind] = len(sel)
        if kind == "excluded":
            ax.plot(xs, ys, linestyle="none", marker="x", markersize=4,
                    markeredgewidth=1.0, color="#888888", zorder=2,
                    label=_label(es, "excluido a mano", "excluded by hand"))
            continue
        col = "#1f3b73" if kind == "plain" else "#a8443a"
        label = _label(es, "medida", "measurement") if kind == "plain" \
            else _label(es, "marcado (puerta de calidad)",
                        "flagged (quality gate)")
        if kind == "flagged":
            ax.errorbar(xs, ys, yerr=errs, linestyle="none", marker="o",
                        markerfacecolor="none", markeredgecolor=col,
                        markersize=4.0, ecolor=col, elinewidth=0.8,
                        capsize=_CAP, capthick=0.8, color=col, zorder=3,
                        label=label)
        else:
            ax.errorbar(xs, ys, yerr=errs, linestyle="none", marker="o",
                        markerfacecolor=col, markeredgecolor=col,
                        markersize=4.0, ecolor=col, elinewidth=0.8,
                        capsize=_CAP, capthick=0.8, color=col, zorder=3,
                        label=label)

    if not pts:
        ax.text(0.5, 0.5, _label(es, "sin puntos que representar",
                                 "no points to plot"),
                transform=ax.transAxes, ha="center", va="center",
                color="#666666")
    else:
        mags = [p["mag"] for p in pts]
        lo, hi = min(mags), max(mags)
        limits, tick_vals, tick_labels, offset = _plan(lo, hi, target=6)
        ax.set_ylim(limits[1], limits[0]) if invert_y else \
            ax.set_ylim(limits)
        if tick_vals:
            ax.set_yticks(tick_vals)
            ax.set_yticklabels(tick_labels)
        if offset:
            ax.text(0.995, 0.02, offset, transform=ax.transAxes,
                    ha="right", va="bottom", fontsize=8.5, color="black")
        mjds = [p["mjd"] for p in pts]
        limits_x, xt, xl, xoff = _plan(min(mjds), max(mjds), target=6)
        ax.set_xlim(limits_x)
        if xt:
            ax.set_xticks(xt)
            ax.set_xticklabels(xl)
        if xoff:
            ax.text(0.005, 0.02, xoff, transform=ax.transAxes, ha="left",
                    va="bottom", fontsize=8.5, color="black")

    ax.set_xlabel(x_label, fontsize=11, color="black")
    ax.set_ylabel(y_label, fontsize=11, color="black")
    if title:
        ax.set_title(title, fontsize=13, color="black", loc="left",
                     pad=18 if subtitle else 8)
    if subtitle:
        ax.text(0.0, 1.015, subtitle, transform=ax.transAxes, fontsize=9.5,
                color="#333333", ha="left", va="bottom")
    handles, labels = ax.get_legend_handles_labels()
    if handles:
        ax.legend(handles, labels, fontsize=8.5, frameon=False,
                  loc="upper left", bbox_to_anchor=(1.01, 1.0),
                  borderaxespad=0.0)
    if watermark:
        fig.text(0.99, 0.005, watermark, ha="right", va="bottom",
                 fontsize=8, color="#777777")
    fig.tight_layout()
    if out:
        fig.savefig(out, dpi=dpi, facecolor="white",
                    bbox_inches="tight")
        plt.close(fig)
        logger.info("scientific chart written: %s", out)
        return out
    return fig


def _kind_of(p):
    # Which of the three families a point belongs to.
    # @args: p - a point dict
    # @return: "excluded" | "flagged" | "plain"
    from ..core.series_measure import has_data_flag
    if "user_excluded" in (p.get("flags") or []):
        return "excluded"
    return "flagged" if has_data_flag(p.get("flags")) else "plain"


def _bar_error(p):
    # @return: the sigma the bar should show: the point's own error when
    #          the CCD equation could be evaluated, the total otherwise
    if p.get("err_internal") is not None:
        return float(p["err_internal"])
    return None if p.get("err") is None else float(p["err"])


def _label(es, spanish, english):
    # @return: the string in the requested language
    return spanish if es else english


def self_label_y(es):
    # @return: the magnitude axis label, saying which way is brighter
    return "Magnitud (más brillante arriba)" if es \
        else "Magnitude (brighter up)"
