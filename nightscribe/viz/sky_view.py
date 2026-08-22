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

from ..core import coords, ephem_minor
from . import style

logger = logging.getLogger(__name__)

# Altitude vs. time across the night, with twilight phases and the Moon.
# Transits draw their window on top (see docs/VIZ).


def draw_sky(ra_deg, dec_deg, lat, lon, obj_name="", date=None,
             transit=None, out=None, fmt="instagram", watermark="NightScribe"):
    # @args: ra_deg, dec_deg - target, lat, lon - site, obj_name - label,
    #        date - datetime.date (tonight), transit - optional dict from
    #        transits.py (shades ingress/egress), out - PNG path,
    #        fmt - size preset, watermark - footer
    # @return: matplotlib figure (and writes PNG if out is given)
    fig, ax = style.new_fig(fmt)
    window = coords.tonight_window(lat, lon, date)
    if not window:
        ax.text(0.5, 0.5, "Sin noche astronómica / No astronomical night",
                ha="center", va="center", transform=ax.transAxes,
                color=style.FG)
        if out:
            style.save(fig, out)
        return fig
    start, end = window

    times, alts, moon_alts = [], [], []
    t = start - datetime.timedelta(hours=1)
    t_end = end + datetime.timedelta(hours=1)
    while t <= t_end:
        jd = coords.jd_from_datetime(t)
        lst = coords.lst_degrees(jd, lon)
        alt, _ = coords.altaz(ra_deg, dec_deg, lat, lst)
        m = ephem_minor.moon(jd)
        malt, _ = coords.altaz(m["ra"], m["dec"], lat, lst)
        times.append(t)
        alts.append(alt)
        moon_alts.append(malt)
        t += datetime.timedelta(minutes=10)

    hours = [t.hour + t.minute / 60.0 + (24 if t.hour < 12 else 0)
             for t in times]
    ax.plot(hours, alts, color=style.ACCENT, lw=2.2, label=obj_name or "Objeto/Object")
    ax.plot(hours, moon_alts, color="#c9c9c9", lw=1.2, ls=":",
            label="Luna / Moon")

    # darkness shading
    h0 = start.hour + start.minute / 60.0
    h1 = end.hour + end.minute / 60.0 + 24
    ax.axvspan(h0 if h0 > 12 else h0 + 24, h1, color=style.ACCENT2, alpha=0.08)
    ax.axhline(30, color=style.MUTED, lw=0.8, ls="--")
    ax.text(0.01, 0.32, "30°", transform=ax.get_yaxis_transform(),
            color=style.MUTED, fontsize=8)

    if transit:
        ing = transit["ingress"].hour + transit["ingress"].minute / 60.0
        egr = transit["egress"].hour + transit["egress"].minute / 60.0
        ing += 24 if ing < 12 else 0
        egr += 24 if egr < 12 else 0
        ax.axvspan(ing, egr, color=style.ACCENT, alpha=0.18)
        ax.text((ing + egr) / 2, 88, "tránsito / transit", ha="center",
                color=style.ACCENT, fontsize=8)

    ax.set_ylim(0, 90)
    ax.set_xlabel("UTC (h)")
    ax.set_ylabel("Altitud / Altitude (°)")
    ax.set_title(obj_name or "Cielo nocturno / Night sky", loc="left")
    ax.legend(loc="upper right", fontsize=8, framealpha=0.2)
    ax.grid(True, alpha=0.2)
    style.watermark(fig, watermark)
    if out:
        style.save(fig, out)
        logger.info("sky chart written to %s", out)
    return fig
