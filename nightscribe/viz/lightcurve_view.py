############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - SN light curve chart (Track B, B4)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""SN photometric light curve for posts and the GUI panel.

Renders magnitude vs date with an inverted Y axis (fainter = up), one series
per filter, error bars, and an optional schematic template overlay for the
SN's type (the "evoluciona normal" visual reference — interview block 2).

The PNG path (draw_lightcurve) follows transit_view / sn_view (ADR-010);
the GUI widget lives in gui/widgets/lightcurve_widget.py (ADR-029).
"""

import logging

from . import style
from ..core import sn_templates

logger = logging.getLogger(__name__)

# Distinct colours per filter (theme accents). "Clear"/"None" is the default
# no-filter path (B-f) and gets the primary accent.
_FILTER_COLOURS = {
    "Clear": style.ACCENT, "None": style.ACCENT,
    "V": style.ACCENT2, "R": style.ACCENT2,
    "B": "#6a9fd8", "I": "#d8a06a", "NIR": "#d86a9f",
}


def _filter_colour(filt):
    # @args: filt - filter name string
    # @return: a matplotlib colour for this filter
    return _FILTER_COLOURS.get(filt or "Clear", style.ACCENT)


def _filter_label(filt, lang):
    # @args: filt - filter name, lang - "es"|"en"
    # @return: a human label for the legend
    if not filt or filt in ("Clear", "None"):
        return style.pick(lang, "Sin filtro", "No filter")
    return filt


def draw_lightcurve(points, out=None, fmt="facebook", watermark="NightScribe",
                    size=None, lang="es", sn_type=None,
                    peak_mjd=None, peak_mag=None):
    # @args: points - list of {mjd, mag, err, filter} dicts,
    #        out - PNG path (None = return figure without saving),
    #        fmt - size preset, watermark - footer text,
    #        size - (w, h) px override,
    #        lang - "es"|"en" (chart labels follow the UI language),
    #        sn_type - string for the template overlay (e.g. "SN Ia"),
    #        peak_mjd - MJD of the peak (to align the template); if None,
    #            the brightest point in the data is used,
    #        peak_mag - mag at peak (to offset the template); if None,
    #            the brightest point in the data is used.
    # @return: matplotlib figure (and writes PNG if out is given)
    fig, ax = style.new_fig(fmt, size=size)

    # group points by filter
    by_filter = {}
    for p in points:
        f = p.get("filter") or "Clear"
        by_filter.setdefault(f, []).append(p)

    # find the peak (brightest = lowest mag) for template alignment
    if peak_mjd is None or peak_mag is None:
        all_pts = [p for pts in by_filter.values() for p in pts]
        if all_pts:
            brightest = min(all_pts, key=lambda p: p["mag"])
            peak_mjd = peak_mjd if peak_mjd is not None else brightest["mjd"]
            peak_mag = peak_mag if peak_mag is not None else brightest["mag"]

    # template overlay (schematic, fainter = positive delta_mag → up on screen)
    tpl = sn_templates.template(sn_type) if sn_type else None
    if tpl and peak_mjd is not None and peak_mag is not None:
        tpl_x = [peak_mjd + d for d, _dm in tpl]
        tpl_y = [peak_mag + dm for d, dm in tpl]
        ax.plot(tpl_x, tpl_y, color=style.MUTED, lw=1.2, ls="--",
                alpha=0.5, zorder=1,
                label=style.pick(lang, "Plantilla típica (esquemática)",
                                  "Typical template (schematic)"))

    # data series per filter
    for filt in sorted(by_filter):
        pts = sorted(by_filter[filt], key=lambda p: p["mjd"])
        xs = [p["mjd"] for p in pts]
        ys = [p["mag"] for p in pts]
        errs = [p.get("err") for p in pts]
        # matplotlib rejects None in yerr; use NaN to skip a bar
        errs = [e if e is not None else float("nan") for e in errs]
        colour = _filter_colour(filt)
        # source style: quicklook = hollow (open marker), others = filled
        is_quicklook = any(p.get("source") == "quicklook" for p in pts)
        marker = "o" if not is_quicklook else "o"
        facecolor = colour if not is_quicklook else "none"
        ax.errorbar(xs, ys, yerr=errs, color=colour, marker=marker,
                     markerfacecolor=facecolor, markersize=5, lw=1.5,
                     capsize=0, label=_filter_label(filt, lang), zorder=3)

    ax.set_title(style.pick(lang, "Curva de luz", "Light curve"), loc="left")
    ax.set_xlabel(style.pick(lang, "Fecha (MJD)", "Date (MJD)"))
    ax.set_ylabel(style.pick(lang, "Magnitud", "Magnitude"))
    ax.invert_yaxis()   # brighter (lower mag) at the bottom — standard
    ax.grid(True, alpha=0.2)
    if by_filter or tpl:
        ax.legend(fontsize=9, loc="best")
    style.watermark(fig, watermark)
    if out:
        style.save(fig, out)
        logger.info("light curve written to %s", out)
    return fig
