############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Sun today panel (SDO + own region map)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import logging
import re

import matplotlib.pyplot as plt
from matplotlib.patches import Circle

from . import style

logger = logging.getLogger(__name__)

# Sun panel: latest SDO image (public domain) plus our own active-region
# map drawn from NOAA coordinates (see ADR-008 / docs/VIZ).

# Region locations look like "S10W25" or "N05E12"
_LOC_RE = re.compile(r"([NS])(\d+)([EW])(\d+)")


def draw_sun(sdo_path, sun_data, out=None, fmt="instagram",
             watermark="NightScribe"):
    # @args: sdo_path - local JPEG Path (or None), sun_data - dict from
    #        solar.solar_now(), out - PNG path, fmt - size, watermark - footer
    # @return: matplotlib figure (and writes PNG if out is given)
    fig = plt.figure(figsize=(10.8, 10.8), dpi=100)
    style.apply_style()
    fig.patch.set_facecolor(style.BG)

    # left: SDO image
    ax_img = fig.add_axes([0.06, 0.30, 0.55, 0.62])
    ax_img.set_xticks([])
    ax_img.set_yticks([])
    if sdo_path:
        img = plt.imread(str(sdo_path))
        ax_img.imshow(img)
    else:
        ax_img.text(0.5, 0.5, "SDO\nno disponible / unavailable", ha="center",
                    va="center", color=style.MUTED)
    ax_img.set_title("NASA SDO — hoy / today", color=style.FG, fontsize=11,
                     loc="left")

    # right: our own active-region map from NOAA coordinates
    ax_map = fig.add_axes([0.68, 0.34, 0.28, 0.52])
    _draw_region_map(ax_map, sun_data.get("regions") or [])

    # bottom: the numbers that matter
    ax_txt = fig.add_axes([0.06, 0.04, 0.9, 0.22])
    ax_txt.axis("off")
    lines = []
    if sun_data.get("ssn") is not None:
        lines.append(f"Manchas / Sunspot number: {sun_data['ssn']:.0f}"
                     f"   ·   F10.7: {sun_data.get('f107'):.0f} sfu")
    if sun_data.get("flare_7d"):
        fl = sun_data["flare_7d"]
        lines.append(f"Fulguración semanal / Weekly flare: "
                     f"{fl['class']}{fl['value']}")
    if sun_data.get("kp") is not None:
        aur = {"possible": "¡Auroras posibles! / Auroras possible!",
               "unlikely": "Sin auroras en latitudes medias / No mid-latitude auroras"
               }.get(sun_data.get("aurora"), "")
        lines.append(f"Kp: {sun_data['kp']:.1f}   ·   {aur}")
    ax_txt.text(0, 0.95, "\n".join(lines), va="top", color=style.FG,
                fontsize=12, family="monospace")
    fig.suptitle("El Sol ahora / The Sun now", color=style.FG, fontsize=15,
                 fontweight="bold", x=0.06, ha="left")
    style.watermark(fig, watermark + " · NASA/SDO")
    if out:
        style.save(fig, out)
        logger.info("sun panel written to %s", out)
    return fig


def _draw_region_map(ax, regions):
    # Disc with active regions plotted by heliographic coordinates.
    # @args: ax - axes, regions - list from noaa.active_regions()
    ax.set_facecolor(style.BG)
    ax.set_aspect("equal")
    disc = Circle((0, 0), 1.0, facecolor="#f5c542", edgecolor=style.SUN,
                  lw=1.5, alpha=0.9)
    ax.add_patch(disc)
    seen = set()
    for r in regions:
        m = _LOC_RE.search(r.get("location") or "")
        if not m:
            continue
        ns, lat, ew, lon = m.groups()
        lat = float(lat) * (1 if ns == "N" else -1)
        lon = float(lon) * (1 if ew == "E" else -1)
        # orthographic-ish projection of the visible disc
        import math
        x = math.cos(math.radians(lat)) * math.sin(math.radians(lon))
        y = math.sin(math.radians(lat))
        reg = str(r.get("region") or "")
        if reg in seen:
            continue
        seen.add(reg)
        ax.plot(x, y, "o", color=style.DANGER, ms=5, zorder=5)
        ax.annotate(reg, (x, y), textcoords="offset points", xytext=(4, 4),
                    color=style.BG, fontsize=7, fontweight="bold")
    ax.set_xlim(-1.25, 1.25)
    ax.set_ylim(-1.25, 1.25)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
