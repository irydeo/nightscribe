############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Night altitude curve chart
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import datetime
import logging

from ..core import sky_math
from . import style

logger = logging.getLogger(__name__)

# Altitude vs. time across the night, with twilight phases and the Moon.
# Transits draw their window on top (see docs/VIZ).


def draw_sky(ra_deg, dec_deg, lat, lon, obj_name="", date=None,
              transit=None, out=None, fmt="instagram", watermark="NightScribe",
              horizon=None, margin=0.0, safe_window=None, best_time=None,
              size=None, lang="es"):
    # @args: ra_deg, dec_deg - target, lat, lon - site, obj_name - label,
    #        date - datetime.date (tonight), transit - optional dict from
    #        transits.py (shades ingress/egress), out - PNG path,
    #        fmt - size preset, watermark - footer,
    #        horizon - optional horizon.alt_at(az) callable (ADR-020),
    #        margin - safety margin in degrees,
    #        safe_window - (start_dt, end_dt) the safe span (ADR-020);
    #                      shaded when given,
    #        best_time - datetime to start by (labelled "a lo último"),
    #        size - (w, h) px override (panel re-render mode),
    #        lang - string language ("es"|"en"); charts follow the UI language
    # @return: matplotlib figure (and writes PNG if out is given)
    fig, ax = style.new_fig(fmt, size=size)
    # the night window + the series come from the shared pure sampler
    # (core/sky_math), so this chart and the GUI widget can never drift apart
    # (ADR-029, the same rule the orbit chart follows).
    s = sky_math.sample_night(ra_deg, dec_deg, lat, lon, date,
                              horizon=horizon, margin=margin)
    if not s:
        ax.text(0.5, 0.5,
                style.pick(lang, "Sin noche astronómica",
                           "No astronomical night"),
                ha="center", va="center", transform=ax.transAxes,
                color=style.FG)
        if out:
            style.save(fig, out)
        return fig
    start, end = s["start"], s["end"]
    rel, alts, moon_alts, hor_alts = s["rel"], s["alt"], s["moon"], s["horizon"]

    # x-axis: hours *relative* to astronomical dusk (start of the window).
    # Dusk is always at t=0, dawn a few hours later (up to 24 h), so the axis
    # never shows 26/28 — only real clock hours, one tick per hour. `start` is
    # aware-UTC; planner/test callers pass a mix of aware and naive datetimes,
    # so fold everything into aware-UTC before subtracting.
    def _utc(dt):
        # @args: dt - datetime (aware or naive)
        # @return: aware-UTC equivalent, naive inputs assumed to be UTC
        if dt.tzinfo is None:
            return dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(datetime.timezone.utc)

    def _pos(dt):
        # @return: hours from `start`, keeping across-midnight times positive
        return (_utc(dt) - start).total_seconds() / 3600.0

    # one label per hour boundary of the night, real clock time, no 26/28
    span = (end - start).total_seconds() / 3600.0
    ticks, labels = [], []
    for i in range(-1, int(span) + 2):
        p = float(i)
        if -1.05 <= p <= span + 1.05:
            ticks.append(p)
            labels.append(f"{(start + datetime.timedelta(hours=i)):%H:%M}Z")
    ax.set_xticks(ticks)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)

    ax.plot(rel, alts, color=style.ACCENT, lw=2.2,
            label=obj_name or style.pick(lang, "Objeto", "Object"))
    ax.plot(rel, moon_alts, color="#c9c9c9", lw=1.2, ls=":",
            label=style.pick(lang, "Luna", "Moon"))

    # darkness shading: dusk (0) → dawn (span)
    ax.axvspan(0, span, color=style.ACCENT2, alpha=0.08)
    if horizon:
        ax.plot(rel, hor_alts, color=style.MUTED, lw=1.0, ls="--",
                label=style.pick(lang, "Límite", "Limit"))
    else:
        ax.axhline(30, color=style.MUTED, lw=0.8, ls="--",
                   label=style.pick(lang, "Límite", "Limit"))

    # safe span (ADR-020): the run of the night where the planned session
    # still clears the local horizon; best_time is when to start inside it
    if safe_window:
        sp0, sp1 = _pos(safe_window[0]), _pos(safe_window[1])
        if sp1 < sp0:
            sp1 += 24  # span wraps midnight
        ax.axvspan(sp0, sp1, color=style.ACCENT2, alpha=0.15,
                   label=style.pick(lang, "ventana segura", "safe window"))
        if best_time:
            bt = _pos(best_time)
            ax.axvline(bt, color=style.ACCENT, ls="--", lw=1.2)
            ax.text(bt, 88,
                    style.pick(
                        lang,
                        f"empezar hasta {best_time:%H:%M}Z",
                        f"start by {best_time:%H:%M}Z"),
                    ha="center", color=style.ACCENT, fontsize=8)
    elif best_time:
        bt = _pos(best_time)
        ax.axvline(bt, color=style.ACCENT, ls="--", lw=1.2)
        ax.text(bt, 88,
                style.pick(
                    lang,
                    f"mejor hora {best_time:%H:%M}Z",
                    f"best time {best_time:%H:%M}Z"),
                ha="center", color=style.ACCENT, fontsize=8)

    if transit:
        ing, egr = _pos(transit["ingress"]), _pos(transit["egress"])
        ax.axvspan(ing, egr, color=style.ACCENT, alpha=0.18)
        ax.text((ing + egr) / 2, 88, style.pick(lang, "tránsito", "transit"),
                ha="center", color=style.ACCENT, fontsize=8)

    ax.set_xlim(-1, span + 1)
    ax.set_ylim(0, 90)
    ax.set_xlabel(style.pick(lang, "UTC (h) desde el anochecer",
                             "UTC (h) from dusk"))
    ax.set_ylabel(style.pick(lang, "Altitud (°)", "Altitude (°)"))
    ax.set_title(obj_name or style.pick(lang, "Cielo nocturno", "Night sky"),
                 loc="left")
    ax.legend(loc="upper right", fontsize=8, framealpha=0.2)
    ax.grid(True, alpha=0.2)
    style.watermark(fig, watermark)
    if out:
        style.save(fig, out)
        logger.info("sky chart written to %s", out)
    return fig
