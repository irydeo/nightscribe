############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Finder / comparison chart (matplotlib export, ADR-042)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Annotated finder chart: the field image (DSS2 colour cutout or the
user's own FITS) with the target centred and marked, catalog magnitudes
labelled, VSX variables ringed so they are never picked as comparisons,
and the photometric sequence (Comp1...N + Check) drawn on top.

The geometry comes from core/field_math.py (synthetic TAN canvas) or from
the image's own core/wcs.py solution (user FITS); labelling keeps SecFot's
collision-avoidance rule (González Farfán & González Carballo 2026). This
is the social/print export; the interactive GUI picker is a QGraphicsView
widget (ADR-029) that reuses the same math.
"""

import logging
import math

import numpy as np

from ..core import field_math
from . import style

logger = logging.getLogger(__name__)

MAX_LABELS = 34          # catalogue mode cap (SecFot's value)
_LABEL_CLEAR = 58.0      # min distance between labelled stars, canvas/1000

# chart colours: the finder palette on top of the shared dark theme
C_COMP = "#4dd0e1"       # comparison rings (turquoise, SecFot's comp)
C_CHECK = "#ff7ad9"      # check star (magenta square)
C_VAR = "#ff6378"        # VSX variables (red)
C_RING = "#58d68d"       # labelled catalog stars (green)


# --------------------------- geometry adapters ---------------------------

class _CanvasGeo:
    # Synthetic TAN canvas (DSS2 mode): 1000x1000. field_math works in the
    # screen convention (y down, 0 at the top/north); this adapter returns
    # PLOT coordinates (y up), so every overlay lands on the image drawn
    # with origin="upper".
    def __init__(self, center, fov_arcmin, inverted):
        self.center = center
        self.field_rad = math.radians(fov_arcmin / 60.0)
        self.inverted = inverted
        self.fov_arcmin = float(fov_arcmin)
        self.width = self.height = int(field_math.CANVAS)

    def to_xy(self, ra, dec):
        x, y = field_math.project(ra, dec, self.center, self.field_rad,
                                  self.inverted)
        return x, field_math.CANVAS - y

    def edge_sky(self, edge, t):
        # @args: edge - "top"|"bottom"|"left"|"right", t - position along
        #        the edge in plot units (y up)
        x, y = {"top": (t, 0.0), "bottom": (t, field_math.CANVAS),
                "left": (0.0, field_math.CANVAS - t),
                "right": (field_math.CANVAS, field_math.CANVAS - t)}[edge]
        return field_math.screen_to_sky(x, y, self.center, self.field_rad,
                                        self.inverted)

    def scale_width(self, scale_arcmin):
        return scale_arcmin / self.fov_arcmin * field_math.CANVAS

    def north_east(self):
        # @return: ((dx, dy) north, (dx, dy) east) in plot units (y up)
        if self.inverted:
            return (0.0, -1.0), (1.0, 0.0)
        return (0.0, 1.0), (-1.0, 0.0)


class _WcsGeo:
    # The user's own FITS: the WCS solution does the projecting, in image
    # pixels (0-based, y up with origin="lower").
    def __init__(self, wcs):
        self.wcs = wcs
        self.width, self.height = wcs.naxis1, wcs.naxis2
        self.fov_arcmin = wcs.naxis1 * wcs.pixel_scale() / 60.0

    def to_xy(self, ra, dec):
        return self.wcs.sky_to_pixel(ra, dec)

    def edge_sky(self, edge, t):
        x, y = {"top": (t, self.height - 1.0), "bottom": (t, 0.0),
                "left": (0.0, t), "right": (self.width - 1.0, t)}[edge]
        return self.wcs.pixel_to_sky(x, y)

    def scale_width(self, scale_arcmin):
        return scale_arcmin * 60.0 / self.wcs.pixel_scale()

    def north_east(self):
        cx, cy = self.width / 2.0, self.height / 2.0
        ra, dec = self.wcs.pixel_to_sky(cx, cy)
        d_dec = 1.0 / 3600.0
        d_ra = d_dec / max(math.cos(math.radians(dec)), 1e-6)
        xn, yn = self.wcs.sky_to_pixel(ra, dec + d_dec)
        xe, ye = self.wcs.sky_to_pixel(ra + d_ra, dec)

        def unit(dx, dy):
            norm = math.hypot(dx, dy) or 1.0
            return dx / norm, dy / norm
        return unit(xn - cx, yn - cy), unit(xe - cx, ye - cy)


# --------------------------- drawing helpers ---------------------------

def _halo_text(ax, x, y, text, size=9, color=None, ha="left", bold=False,
               mono=True):
    # Text with a dark halo so it reads over any sky background.
    import matplotlib.patheffects as pe
    t = ax.text(x, y, text, color=color or style.FG, fontsize=size, ha=ha,
                va="center", fontweight="bold" if bold else "normal",
                family="monospace" if mono else None)
    t.set_path_effects([pe.withStroke(linewidth=2.2, foreground=style.BG)])
    return t


def _label_positions(stars, geo):
    # The label collision rule lives in core/field_math (shared with the
    # GUI widget, ADR-029); here we only project and crop to the frame.
    # @return: the stars that keep a label
    clear = _LABEL_CLEAR * geo.width / field_math.CANVAS
    points = []
    for star in stars:
        x, y = geo.to_xy(star["ra"], star["dec"])
        if not (8 <= x <= geo.width - 8 and 8 <= y <= geo.height - 8):
            continue
        star["_x"], star["_y"] = x, y
        points.append((x, y, star))
    return field_math.label_layout(points, clear, MAX_LABELS)


def _draw_ticks(ax, geo):
    # RA ticks on the bottom edge, Dec ticks on the right (SecFot layout),
    # labels only on the major steps.
    edges = {}
    count = 250
    for edge in ("top", "bottom", "left", "right"):
        size = geo.width if edge in ("top", "bottom") else geo.height
        edges[edge] = [geo.edge_sky(edge, i * size / count)
                       for i in range(count + 1)]
    as_ra = [(i * geo.width / count, s[0] / 15.0 * 3600.0)
             for i, s in enumerate(edges["bottom"])]
    as_dec = [(i * geo.height / count, s[1] * 3600.0)
              for i, s in enumerate(edges["right"])]
    span = max(v for _, v in as_ra) - min(v for _, v in as_ra)
    ra_major, ra_minor = field_math.choose_step(span)
    span = max(v for _, v in as_dec) - min(v for _, v in as_dec)
    dec_major, dec_minor = field_math.choose_step(span)

    major_len = geo.width * 0.015
    minor_len = major_len * 0.5
    for tick in field_math.edge_crossings(as_ra, ra_major, ra_minor):
        length = major_len if tick["major"] else minor_len
        ax.plot([tick["t"], tick["t"]], [0, length], color=style.FG,
                lw=1.4 if tick["major"] else 0.9, solid_capstyle="butt")
        if tick["major"]:
            _halo_text(ax, tick["t"], length * 1.8,
                       field_math.format_ra_tick(tick["value"], ra_major),
                       size=8, ha="center", mono=False)
    for tick in field_math.edge_crossings(as_dec, dec_major, dec_minor):
        length = major_len if tick["major"] else minor_len
        ax.plot([geo.width - length, geo.width], [tick["t"], tick["t"]],
                color=style.FG, lw=1.4 if tick["major"] else 0.9,
                solid_capstyle="butt")
        if tick["major"]:
            _halo_text(ax, geo.width - length * 1.8, tick["t"],
                       field_math.format_dec_tick(tick["value"], dec_major),
                       size=8, ha="right", mono=False)


def _draw_scale(ax, geo, lang):
    scale = field_math.nice_scale(geo.fov_arcmin)
    width = geo.scale_width(scale)
    cx = geo.width / 2.0
    y = geo.height * 0.045
    ax.plot([cx - width / 2, cx + width / 2], [y, y], color=style.FG, lw=2)
    for x in (cx - width / 2, cx + width / 2):
        ax.plot([x, x], [y - y * 0.25, y + y * 0.25], color=style.FG, lw=2)
    _halo_text(ax, cx, y * 1.9, field_math.format_scale(scale, lang),
               size=10, ha="center")


def _draw_compass(ax, geo):
    (ndx, ndy), (edx, edy) = geo.north_east()
    arm = geo.width * 0.055
    vx, vy = geo.width * 0.10, geo.height * 0.90
    for (dx, dy), label in (((ndx, ndy), "N"), ((edx, edy), "E")):
        ax.annotate("", xy=(vx + dx * arm, vy + dy * arm), xytext=(vx, vy),
                    arrowprops=dict(arrowstyle="-", color=style.FG, lw=1.8))
        _halo_text(ax, vx + dx * arm * 1.35, vy + dy * arm * 1.35, label,
                   size=12, bold=True, ha="center", mono=False)


def _draw_target(ax, geo, target, lang):
    from matplotlib.patches import Circle
    if target:
        x, y = geo.to_xy(target["ra"], target["dec"])
    else:
        x, y = geo.width / 2.0, geo.height / 2.0
    r = geo.width * 0.022
    ax.add_patch(Circle((x, y), r, fill=False, ec=style.ACCENT, lw=2.0))
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        ax.plot([x + dx * r * 1.15, x + dx * r * 1.7],
                [y + dy * r * 1.15, y + dy * r * 1.7], color=style.ACCENT,
                lw=2.0)
    if target and target.get("name"):
        _halo_text(ax, x, y - r * 2.2, target["name"], size=12, bold=True,
                   ha="center", mono=False, color=style.ACCENT)


def _draw_variables(ax, geo, variables):
    from matplotlib.patches import Circle
    for var in variables:
        pos = var.get("star") or var
        x, y = geo.to_xy(pos["ra"], pos["dec"])
        if not (0 <= x <= geo.width and 0 <= y <= geo.height):
            continue
        mag = (var.get("star") or {}).get("mag")
        radius = (8 + (14 - mag) * 1.15) if mag is not None else 10.0
        radius *= geo.width / field_math.CANVAS
        radius = max(7.0, min(20.0 * geo.width / field_math.CANVAS, radius))
        ax.add_patch(Circle((x, y), radius, fill=False, ec=C_VAR, lw=1.6))


def _draw_sequence(ax, geo, entries):
    # The saved/proposed sequence: comps as turquoise rings, the check as a
    # magenta square, each with its name.
    from matplotlib.patches import Circle, Rectangle
    for e in entries:
        star = e["star"]
        x, y = geo.to_xy(star["ra"], star["dec"])
        if not (0 <= x <= geo.width and 0 <= y <= geo.height):
            continue
        r = geo.width * 0.012
        if e["kind"] == "check":
            ax.add_patch(Rectangle((x - r, y - r), 2 * r, 2 * r,
                                   fill=False, ec=C_CHECK, lw=1.8))
            colour = C_CHECK
        else:
            ax.add_patch(Circle((x, y), r, fill=False, ec=C_COMP, lw=1.8))
            colour = C_COMP
        right = x > geo.width * 0.78
        _halo_text(ax, x - 1.5 * r if right else x + 1.5 * r, y + 1.2 * r,
                   e["name"], size=10, bold=True, color=colour,
                   ha="right" if right else "left")


# --------------------------- the chart ---------------------------

def draw_finder(field, target=None, entries=None, image=None, wcs=None,
                inverted=False, negative=False, out=None, lang="es",
                watermark="NightScribe", size=None):
    # The finder/comparison chart.
    # @args: field - compstars.load_field result, target - optional dict
    #        {name, ra, dec}, entries - sequence entries (comp/check) or
    #        None for catalogue mode (brightest stars labelled by mag),
    #        image - DSS2 JPEG path / numpy array (2D or RGB) or None,
    #        wcs - core.wcs.Wcs of the user's image (None: synthetic TAN
    #        canvas centred on the field), inverted - rotate 180 deg
    #        (canvas mode), negative - black stars on white (grayscale
    #        images), out - PNG path, lang - "es"|"en", watermark - footer,
    #        size - (w, h) px
    # @return: matplotlib figure
    fig, ax = style.new_fig("instagram", size=size)
    if wcs is not None:
        geo = _WcsGeo(wcs)
    else:
        geo = _CanvasGeo(field["center"], field["fov_arcmin"], inverted)

    if image is None:
        ax.set_facecolor(style.BG)
    else:
        if isinstance(image, (str, bytes)) or hasattr(image, "__fspath__"):
            import matplotlib.image as mpimg
            image = mpimg.imread(image)
        img = np.asarray(image)
        if img.ndim == 2:
            if negative:
                img = 1.0 - img.astype(np.float32)
            ax.imshow(img, cmap="gray", origin="lower",
                      extent=(0, geo.width, 0, geo.height), zorder=0)
        else:
            if negative:
                img = 1.0 - img.astype(np.float32)
            if inverted:
                img = np.rot90(img, 2)
            # canvas convention is y-down: origin="upper" puts row 0 on top
            ax.imshow(img, origin="upper",
                      extent=(0, geo.width, 0, geo.height), zorder=0)

    ax.set_xlim(0, geo.width)
    ax.set_ylim(0, geo.height)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_color(style.FG)
        spine.set_linewidth(1.6)

    _draw_ticks(ax, geo)
    _draw_scale(ax, geo, lang)
    _draw_compass(ax, geo)
    _draw_target(ax, geo, target, lang)

    if entries:
        _draw_sequence(ax, geo, entries)
    else:
        labelled = _label_positions(list(field.get("stars", [])), geo)
        from matplotlib.patches import Circle
        for star in labelled:
            ax.add_patch(Circle((star["_x"], star["_y"]),
                                geo.width * 0.0065, fill=False, ec=C_RING,
                                lw=1.4))
            right = star["_x"] > geo.width * 0.82
            _halo_text(ax,
                       star["_x"] - geo.width * 0.011 if right
                       else star["_x"] + geo.width * 0.011,
                       star["_y"] + geo.width * 0.009,
                       f"{star['mag']:.2f}", size=8,
                       ha="right" if right else "left")
    _draw_variables(ax, geo, field.get("variables", []))

    catalog_name = field.get("catalog_name", "")
    ax.set_title(target["name"] if target and target.get("name")
                 else style.pick(lang, "Campo estelar", "Star field"),
                 loc="left", color=style.FG)
    footer = watermark
    if catalog_name:
        footer += f" · {catalog_name}"
    style.watermark(fig, footer)
    fig.tight_layout()
    if out:
        style.save(fig, out)
        logger.info("finder chart written to %s", out)
    return fig
