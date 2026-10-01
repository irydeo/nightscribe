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

import numpy as np

from . import style
from ..core import sn_templates

logger = logging.getLogger(__name__)

# The magnitude window follows the core of the curve: median ± K robust
# sigmas, never min/max (quality plan, phase A). A systematic wider than
# this share of the window is NOT drawn as a band (it would fill the
# panel): the caption says the number instead.
_ROBUST_K = 6.0
_SYSTEM_BAND_MAX_FRAC = 0.5


def _bar_error(p):
    # @args: p - a point dict
    # @return: the sigma its bar should draw: its OWN error when the CCD
    #          equation could be evaluated, else the total (or None)
    if p.get("err_internal") is not None:
        return float(p["err_internal"])
    return None if p.get("err") is None else float(p["err"])


def _systematic(p):
    # @args: p - a point dict
    # @return: the part of the error that is NOT the point's own photons
    #          (the zero point, the flat), or None
    total = p.get("err")
    inner = p.get("err_internal")
    if total is None:
        return None
    if inner is None:
        return float(total)
    var = float(total) ** 2 - float(inner) ** 2
    return float(np.sqrt(var)) if var > 0.0 else 0.0


def _mag_span(mags):
    # @return: the span of the magnitudes, or 0
    if not mags:
        return 0.0
    return float(np.max(mags) - np.min(mags))

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


_SURVEY_COLOUR = "#8a90a6"   # B12 survey-catalog points: faint grey


def _source_class(src):
    # @args: src - the point's source (manual|paste|file|quicklook|survey:…)
    # @return: "manual" | "quicklook" | "survey"
    src = src or "manual"
    if src.startswith("survey"):
        return "survey"
    if src == "quicklook":
        return "quicklook"
    return "manual"


def _series_label(filt, src_class, lang):
    # @args: filt - filter name, src_class - _source_class(), lang - "es"|"en"
    # @return: the legend label of one (filter, source) series
    label = _filter_label(filt, lang)
    if src_class == "quicklook":
        label += " · " + style.pick(lang, "indicativo", "indicative")
    elif src_class == "survey":
        label += " · " + style.pick(lang, "catálogo", "catalog")
    return label


def _series_style(src_class):
    # @args: src_class - "manual" | "quicklook" | "survey"
    # @return: (colour, marker face, linestyle); a None colour means
    #          "use the filter's own colour"
    if src_class == "survey":
        return _SURVEY_COLOUR, "none", "--"
    if src_class == "quicklook":
        return None, "none", "--"
    return None, "auto", "-"


def draw_lightcurve(points, out=None, fmt="facebook", watermark="NightScribe",
                    size=None, lang="es", sn_type=None,
                    peak_mjd=None, peak_mag=None, fold_period_d=None,
                    epoch_mjd=None, schematic=None):
    # @args: points - list of {mjd, mag, err, filter} dicts,
    #        out - PNG path (None = return figure without saving),
    #        fmt - size preset, watermark - footer text,
    #        size - (w, h) px override,
    #        lang - "es"|"en" (chart labels follow the UI language),
    #        sn_type - string for the template overlay (e.g. "SN Ia"),
    #        peak_mjd - MJD of the peak (to align the template); if None,
    #            the brightest point in the data is used,
    #        peak_mag - mag at peak (to offset the template); if None,
    #            the brightest point in the data is used,
    #        fold_period_d - pulsation period in days: fold the x axis to
    #            phase 0..2 (two cycles, ADR-034; mirrors the GUI widget),
    #        epoch_mjd - phase-0 reference (default: the first point),
    #        schematic - [(phase, mag)] reference curve (dashed), never
    #            real data (e.g. hads.sawtooth_template)
    # @return: matplotlib figure (and writes PNG if out is given)
    fig, ax = style.new_fig(fmt, size=size)

    # fold mode: the x coordinate of every point becomes its phase (twice:
    # cycle 0 and cycle 1, so the curve reads across the seam)
    if fold_period_d and points:
        epoch = epoch_mjd if epoch_mjd is not None \
            else min(p["mjd"] for p in points)
        folded = []
        for p in points:
            ph = ((p["mjd"] - epoch) / fold_period_d) % 1.0
            folded += [dict(p, mjd=ph), dict(p, mjd=ph + 1.0)]
        points = folded

    # group points by (filter, source): a campaign band and a survey
    # band of the same filter are separate series with their own style
    by_series = {}
    for p in points:
        f = p.get("filter") or "Clear"
        key = (f, _source_class(p.get("source")))
        by_series.setdefault(key, []).append(p)

    # find the peak (brightest = lowest mag) for template alignment
    if peak_mjd is None or peak_mag is None:
        all_pts = list(points)
        if all_pts:
            brightest = min(all_pts, key=lambda p: p["mag"])
            peak_mjd = peak_mjd if peak_mjd is not None else brightest["mjd"]
            peak_mag = peak_mag if peak_mag is not None else brightest["mag"]

    # template overlay: schematic reference in fold mode (never real data),
    # the SN type template otherwise
    tpl = None if fold_period_d else (sn_templates.template(sn_type)
                                      if sn_type else None)
    if fold_period_d and schematic:
        sx = [ph for ph, _m in schematic] + [ph + 1.0 for ph, _m in schematic]
        sy = [m for _ph, m in schematic] + [m for _ph, m in schematic]
        ax.plot(sx, sy, color=style.MUTED, lw=1.2, ls="--", alpha=0.5,
                zorder=1,
                label=style.pick(lang, "esquemática (diente de sierra)",
                                  "schematic (sawtooth)"))
    elif tpl and peak_mjd is not None and peak_mag is not None:
        tpl_x = [peak_mjd + d for d, _dm in tpl]
        tpl_y = [peak_mag + dm for d, dm in tpl]
        ax.plot(tpl_x, tpl_y, color=style.MUTED, lw=1.2, ls="--",
                alpha=0.5, zorder=1,
                label=style.pick(lang, "Plantilla típica (esquemática)",
                                  "Typical template (schematic)"))

    # data series per (filter, source)
    systematic = None
    for (filt, src_class) in sorted(by_series):
        pts = sorted(by_series[(filt, src_class)], key=lambda p: p["mjd"])
        xs = [p["mjd"] for p in pts]
        ys = [p["mag"] for p in pts]
        # the BAR is the point's own error (its photons): the zero-point
        # systematic is common to the whole night and belongs in a band,
        # not in N bars that hide the curve (quality plan, phase A)
        errs = [_bar_error(p) for p in pts]
        errs = [e if e is not None else float("nan") for e in errs]
        syss = [_systematic(p) for p in pts]
        syss = [s for s in syss if s is not None]
        if syss:
            sys = float(np.median(syss))
            systematic = sys if systematic is None else max(systematic, sys)
        colour, face, linest = _series_style(src_class)
        if colour is None:
            colour = _filter_colour(filt)
        if face == "auto":
            face = colour
        ax.errorbar(xs, ys, yerr=errs, color=colour, marker="o",
                    markerfacecolor=face, markersize=5, lw=1.5,
                    ls=linest,
                    capsize=0, label=_series_label(filt, src_class, lang),
                    zorder=3)
        # the calibration band of this series, behind the points
        if syss and systematic and sys <= _SYSTEM_BAND_MAX_FRAC * _mag_span(
                ys):
            med = float(np.median(ys))
            ax.axhspan(med - sys, med + sys, color=style.MUTED, alpha=0.10,
                       zorder=1, lw=0)
    if systematic and systematic >= 0.005:
        ax.text(0.01, 0.02, style.pick(
            lang, "Sistema de calibración ±{0:.3f} mag",
            "Calibration systematic ±{0:.3f} mag").format(systematic),
            transform=ax.transAxes, color=style.MUTED, fontsize=8,
            va="bottom", ha="left")

    ax.set_title(style.pick(lang, "Curva de luz", "Light curve"), loc="left")
    if fold_period_d:
        ax.set_xlabel(style.pick(lang, "Fase", "Phase"))
        ax.set_xlim(0, 2)
    else:
        ax.set_xlabel(style.pick(lang, "Fecha (MJD)", "Date (MJD)"))
    ax.set_ylabel(style.pick(lang, "Magnitud", "Magnitude"))
    ax.invert_yaxis()   # brighter (lower mag) at the bottom — standard
    # the magnitude window follows the CORE of the curve, so one
    # anomalous point cannot flatten the rest (quality plan, phase A)
    all_mags = [p["mag"] for pts in by_series.values() for p in pts]
    if fold_period_d and schematic:
        all_mags += [m for _ph, m in schematic]
    if all_mags:
        med = float(np.median(all_mags))
        mad = 1.4826 * float(np.median(np.abs(np.asarray(all_mags) - med)))
        if mad > 0.0:
            lo = max(med - _ROBUST_K * mad, float(np.min(all_mags)))
            hi = min(med + _ROBUST_K * mad, float(np.max(all_mags)))
            if hi - lo < 0.05:
                hi, lo = med + 0.025, med - 0.025
            pad = (hi - lo) * 0.10
            ax.set_ylim(hi + pad, lo - pad)
    ax.grid(True, alpha=0.2)
    if by_series or tpl or (fold_period_d and schematic):
        ax.legend(fontsize=9, loc="best")
    style.watermark(fig, watermark)
    if out:
        style.save(fig, out)
        logger.info("light curve written to %s", out)
    return fig
