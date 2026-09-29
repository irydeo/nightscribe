############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Period + phase chart (quality plan, phase C)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The report the observer asked for: the periodogram and the folded
curve, side by side.

Layout and content follow the reports the ObsN group already exchanges
(PerWin + PhaseWin): the search at the left with the peak marked and the
false-alarm levels, the folded curve at the right with one colour per
night so a phase shift between nights is visible at a glance, and the
plain-language verdict under both.

The PNG path follows the other charts (ADR-010); the GUI shows it
through the chart viewer.
"""

import logging
import math

import numpy as np

from . import style

logger = logging.getLogger(__name__)

# one colour per night, cycled: a night is a real variable of the plot
_NIGHT_COLOURS = (style.ACCENT, style.ACCENT2, "#6a9fd8", "#d8a06a",
                  "#d86a9f", "#8fd86a", "#c86ad8", "#6ad8c8")


def _fap_levels(t, y, dy, frequencies, power_max, shuffles=30, seed=7):
    # The power level reached by the best peak of a shuffled light curve,
    # for a few probabilities: the dashed lines of the classic plots.
    # The grid is decimated (only the highest peak matters here) or a
    # decade-long baseline would make this take a minute.
    # @return: [{"p": 0.1, "level": w}] sorted by probability (descending)
    from ..core import periodogram as pg
    t = np.asarray(t, dtype=float)
    y = np.asarray(y, dtype=float)
    if t.size < 8 or not shuffles:
        return []
    frequencies = pg.fap_grid(np.asarray(frequencies, dtype=float),
                              t.size, shuffles)
    rng = np.random.default_rng(seed)
    peaks = []
    for _i in range(int(shuffles)):
        res = pg.lomb_scargle(t, rng.permutation(y), None,
                              frequencies=frequencies)
        if res["power"].size:
            peaks.append(float(np.max(res["power"])))
    if not peaks:
        return []
    peaks.sort()
    levels = []
    for p in (0.1, 0.01):
        idx = int(min(len(peaks) - 1, round((1.0 - p) * (len(peaks) - 1))))
        levels.append({"p": p, "level": peaks[idx]})
    return levels


def draw_phase(mags, found=None, out=None, fmt="instagram",
               watermark="NightScribe", lang="es", nights=None,
               fap_levels=True, png_dpi=100):
    # The period + phase report as one PNG.
    # @args: mags - [{"mjd", "mag", "err"}] the curve to fold,
    #        found - the find_period() result (the period, the search,
    #        the notes), out - output path (None: only the figure),
    #        fmt - the style preset, lang - "es"|"en", nights - optional
    #        per-point night keys (computed when None),
    #        fap_levels - draw the shuffled-peak lines (they cost a few
    #        hundred periodograms)
    # @return: the matplotlib figure
    import matplotlib.pyplot as plt
    from ..core import periodogram as pg
    pts = [p for p in (mags or []) if p.get("mjd") is not None
           and p.get("mag") is not None]
    found = found or {}
    period = found.get("period_d")
    t = np.asarray([p["mjd"] for p in pts], dtype=float)
    y = np.asarray([p["mag"] for p in pts], dtype=float)
    dy = None
    if any(p.get("err_internal") or p.get("err") for p in pts):
        # the point's OWN error when the CCD equation could be evaluated;
        # the total (which is mostly the night's calibration systematic)
        # as the fallback, and then the bars are dropped if they are
        # wider than the plot can carry (see below)
        dy = np.asarray([p.get("err_internal") or p.get("err") or 0.0
                         for p in pts], dtype=float)
        dy = np.where(dy > 0.0, dy, np.nan)
    err_ok = dy is not None and bool(np.any(np.isfinite(dy)))
    fig = plt.figure()
    style.apply_style()
    fig.set_size_inches(*tuple(v / png_dpi for v in
                               style.SIZES.get(fmt,
                                               style.SIZES["instagram"])))
    fig.set_dpi(png_dpi)
    fig.patch.set_facecolor(style.BG)
    ax1 = fig.add_axes([0.07, 0.13, 0.40, 0.72])
    ax2 = fig.add_axes([0.55, 0.13, 0.40, 0.72])
    gram = found.get("periodogram")
    freq = gram.get("frequencies") if gram else None
    if freq is not None and len(freq):
        periods = 1.0 / np.asarray(freq, dtype=float)
        power = np.asarray(gram["power"], dtype=float)
        ax1.plot(periods, power, color=style.ACCENT, lw=1.4)
        if fap_levels:
            for j, lvl in enumerate(_fap_levels(t, y, dy,
                                                gram["frequencies"],
                                                float(np.max(power)))):
                ax1.axhline(lvl["level"], color=style.MUTED, ls="--",
                            lw=0.9, alpha=0.9)
                # the two levels sit close together on a real curve: the
                # labels take one side each so they never collide
                ax1.text(0.02, lvl["level"],
                         "FAP {:.0%}".format(lvl["p"]),
                         color=style.MUTED, fontsize=8,
                         va="top" if j == 0 else "bottom", ha="left",
                         transform=ax1.get_yaxis_transform())
        if period:
            ax1.axvline(period, color=style.ACCENT2, ls=":", lw=1.4)
        ax1.set_xlabel(style.pick(lang, "Período (d)", "Period (d)"))
        ax1.set_ylabel(style.pick(lang, "Potencia", "Power"))
        ax1.set_title(style.pick(lang, "Período", "Period"), fontsize=12)
        ax1.set_xscale("log")
        ax1.grid(True, alpha=0.25)
    else:
        ax1.text(0.5, 0.5, style.pick(lang, "Sin búsqueda", "No search"),
                 color=style.MUTED, ha="center", va="center",
                 transform=ax1.transAxes)
        ax1.set_axis_off()
    # the folded curve: solid markers for the first night, hollow for the
    # rest, so a phase drift between nights shows up as a colour band
    if period and len(t):
        if nights is None:
            nights = [pg.phase_of_night(v) for v in t]
        keys = []
        for k in nights:
            if k not in keys:
                keys.append(k)
        folded = pg.fold(t, y, dy, period_d=period)
        # error bars wider than this carry no information at the plot's
        # scale (a bad calibration says so wherever it wants, but not by
        # painting the whole panel); the binned mean still shows the shape
        draw_err = err_ok and float(np.nanmedian(folded["err"])) <= 0.1
        for j, key in enumerate(keys):
            sel = np.asarray([k == key for k in nights], dtype=bool)
            community = str(key) == "AAVSO"
            colour = style.MUTED if community \
                else _NIGHT_COLOURS[j % len(_NIGHT_COLOURS)]
            err = None if (not draw_err or community) else folded["err"][sel]
            marker = dict(fmt="o", ms=2.8 if not community else 2.2,
                          mew=0.0, color=colour, ecolor=colour,
                          elinewidth=0.5,
                          alpha=0.35 if community
                          else (0.75 if j == 0 else 0.45))
            if community:
                marker.update({"markerfacecolor": "none"})
            ax2.errorbar(folded["phase"][sel], folded["mag"][sel],
                         yerr=err, label=str(key) if not community
                         else style.pick(lang, "comunidad AAVSO",
                                         "AAVSO community"), **marker)
            ax2.errorbar(folded["phase2"][sel], folded["mag"][sel],
                         yerr=err, **marker)
        binned = pg.binned_curve(folded["phase"], folded["mag"],
                                 bins=25, phase_max=1.0)
        ax2.plot(binned["phase"], binned["mag"], color=style.FG, lw=1.6,
                 alpha=0.9)
        ax2.plot(binned["phase"] + 1.0, binned["mag"], color=style.FG,
                 lw=1.6, alpha=0.9,
                 label=style.pick(lang, "media binneada",
                                  "binned mean"))
        ax2.set_xlim(0.0, 2.0)
        ax2.invert_yaxis()
        ax2.set_xlabel(style.pick(lang, "Fase", "Phase"))
        ax2.set_ylabel(style.pick(lang, "Magnitud", "Magnitude"))
        ax2.set_title(style.pick(lang, "Fase", "Phase"), fontsize=12)
        ax2.grid(True, alpha=0.25)
        if len(keys) > 1:
            ax2.legend(fontsize=7, loc="best", framealpha=0.15)
    else:
        ax2.text(0.5, 0.5, style.pick(
            lang, "Sin período todavía", "No period yet"), color=style.MUTED,
            ha="center", va="center", transform=ax2.transAxes)
        ax2.set_axis_off()
    head = _headline(found, period, lang)
    fig.suptitle(head["title"], fontsize=13, y=0.965)
    if head["sub"]:
        fig.text(0.5, 0.025, head["sub"], color=style.MUTED, fontsize=8.5,
                 ha="center", va="bottom", wrap=True)
    style.watermark(fig, watermark)
    if out:
        style.save(fig, out)
        plt.close(fig)
        logger.info("period chart written: %s", out)
        return out
    return fig


def _headline(found, period, lang):
    # The two lines of plain language at the top and the bottom: what was
    # found and, above all, what the data cannot say.
    # @return: {"title", "sub"}
    if not period:
        return {"title": style.pick(lang, "Búsqueda de período",
                                    "Period search"), "sub": ""}
    cycles = found.get("cycles")
    fap = found.get("fap")
    title = style.pick(lang, "P = {:.5f} d".format(period),
                       "P = {:.5f} d".format(period))
    bits = []
    if cycles is not None:
        bits.append(style.pick(
            lang, "{:.1f} ciclos cubiertos".format(cycles),
            "{:.1f} cycles covered".format(cycles)))
    if fap is not None:
        bits.append(style.pick(lang, "FAP {:.3f}".format(fap),
                               "FAP {:.3f}".format(fap)))
    method = found.get("method")
    if method:
        bits.append(method.upper())
    sub = " · ".join(bits)
    notes = [n.get(lang) or n.get("en") for n in (found.get("notes") or [])]
    if notes:
        sub = (sub + " · " if sub else "") + notes[0]
    return {"title": title, "sub": sub}


def fold_summary(found, lang="es"):
    # The verdict as plain text for a panel or a log line.
    # @return: a multi-line string
    if not found or not found.get("period_d"):
        return style.pick(lang, "Sin período.", "No period.")
    lines = [style.pick(
        lang, "Período: {:.5f} d ({:.2f} ciclos/día)",
        "Period: {:.5f} d ({:.2f} cycles/day)").format(
            found["period_d"], 1.0 / found["period_d"])]
    if found.get("cycles") is not None:
        lines.append(style.pick(
            lang, "La línea base cubre {:.1f} ciclos",
            "The baseline covers {:.1f} cycles").format(found["cycles"]))
    if found.get("fap") is not None:
        lines.append(style.pick(lang, "FAP: {:.3f}", "FAP: {:.3f}").format(
            found["fap"]))
    for note in found.get("notes") or []:
        lines.append("· " + (note.get(lang) or note.get("en") or ""))
    return "\n".join(lines)
