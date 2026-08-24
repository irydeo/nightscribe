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
import math
import re

import matplotlib.pyplot as plt
from matplotlib.patches import Circle

from . import style

logger = logging.getLogger(__name__)

# Sun panel: latest SDO image (public domain) plus our own active-region
# map drawn from NOAA coordinates (see ADR-008 / docs/VIZ).

# Region locations look like "S10W25" or "N05E12"
_LOC_RE = re.compile(r"([NS])(\d+)([EW])(\d+)")

# SDO 1024px images: the solar disc is roughly centered with this radius
# fraction (empirical value for latest_1024_*.jpg from sdo.gsfc.nasa.gov)
_R_SUN_FRAC = 0.469


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

    # right: annotated HMI continuum image with NOAA region labels
    ax_map = fig.add_axes([0.68, 0.34, 0.28, 0.52])
    hmi_path = sun_data.get("hmi_img")
    if hmi_path:
        draw_annotated_sun(hmi_path, sun_data.get("regions") or [],
                           ax=ax_map)
    else:
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
    for x, y, reg in _project_regions(regions, 1.0):
        ax.plot(x, y, "o", color=style.DANGER, ms=5, zorder=5)
        ax.annotate(reg, (x, y), textcoords="offset points", xytext=(4, 4),
                    color=style.BG, fontsize=7, fontweight="bold")
    ax.set_xlim(-1.25, 1.25)
    ax.set_ylim(-1.25, 1.25)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    # cardinal labels so the orientation matches the SDO image
    ax.text(0, 1.15, "N", ha="center", va="center", color=style.MUTED, fontsize=8)
    ax.text(0, -1.15, "S", ha="center", va="center", color=style.MUTED, fontsize=8)
    ax.text(-1.15, 0, "E", ha="center", va="center", color=style.MUTED, fontsize=8)
    ax.text(1.15, 0, "W", ha="center", va="center", color=style.MUTED, fontsize=8)


def _project_regions(regions, r_sun):
    # Maps NOAA heliographic locations to orthographic x/y on the visible disc.
    # @args: regions - list from noaa.active_regions(), r_sun - disc radius in
    #        the target coordinate system (1.0 for schematic, pixels for image)
    # @return: list of (x, y, region_number) tuples
    seen = set()
    out = []
    for r in regions:
        m = _LOC_RE.search(r.get("location") or "")
        if not m:
            continue
        ns, lat, ew, lon = m.groups()
        lat = float(lat) * (1 if ns == "N" else -1)
        lon = float(lon) * (1 if ew == "E" else -1)
        # orthographic projection as seen from Earth:
        # solar East is on the LEFT, West on the RIGHT
        x = -r_sun * math.cos(math.radians(lat)) * math.sin(math.radians(lon))
        y = r_sun * math.sin(math.radians(lat))
        reg = str(r.get("region") or "")
        if reg in seen:
            continue
        seen.add(reg)
        out.append((x, y, reg))
    return out


def draw_annotated_sun(img_path, regions, out=None, ax=None,
                       watermark="NightScribe"):
    # Draws the real SDO HMI continuum photo with NOAA active-region labels
    # overlaid at their correct heliographic positions (like SolarMonitor).
    # @args: img_path - local JPEG/PNG path, regions - list from
    #        noaa.active_regions(), out - PNG path, ax - existing axes (optional),
    #        watermark - footer
    # @return: matplotlib figure (and writes PNG if out is given)
    own_fig = ax is None
    if own_fig:
        fig = plt.figure(figsize=(3.4, 3.4), dpi=100)
        style.apply_style()
        fig.patch.set_facecolor(style.BG)
        ax = fig.add_axes([0.02, 0.02, 0.96, 0.96])
    else:
        fig = ax.figure
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)

    img = plt.imread(str(img_path))
    h, w = img.shape[:2]
    cx, cy = w / 2.0, h / 2.0
    r_sun = w * _R_SUN_FRAC
    ax.imshow(img, origin="upper", extent=[0, w, h, 0], aspect="equal")
    ax.set_xlim(0, w)
    ax.set_ylim(h, 0)

    for x, y, reg in _project_regions(regions, r_sun):
        px, py = cx + x, cy - y
        ax.plot(px, py, "o", color=style.DANGER, ms=4, zorder=5)
        ax.annotate(reg, (px, py), textcoords="offset points", xytext=(5, 5),
                    color="white", fontsize=7, fontweight="bold", zorder=6)

    if own_fig and watermark:
        fig.text(0.99, 0.01, watermark + " · NASA/SDO", ha="right", va="bottom",
                 color=style.MUTED, fontsize=6, alpha=0.8)
    if out:
        style.save(fig, out)
        logger.info("annotated sun map written to %s", out)
    return fig
