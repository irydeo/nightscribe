############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Top-down orbit chart
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
import math

from ..core import coords, ephem_minor, orbit_math
from . import style

logger = logging.getLogger(__name__)

# Top-down (ecliptic, north up) chart: inner planets for scale, the object's
# orbit highlighted, its current position, and an Earth-Moon zoom inset when
# a close approach is given (see docs/VIZ).

# The pure orbit math (sampling a full orbit, current position, hover) lives
# in core/orbit_math.py (no matplotlib), shared with the GUI widget layer
# (ADR-029). `viz/orbit_view.py` only owns the matplotlib rendering; the
# colours (chart + planet hues) come from viz.palette.
from . import palette
_ORBIT_SPAN = {"mercury": 0.47, "venus": 0.73, "earth": 1.0, "mars": 1.67,
               "jupiter": 5.45}
# The label per planet, hand-picked (ES, EN) — proper nouns, not .capitalize()
_NAMES = {"mercury": ("Mercurio", "Mercury"), "venus": ("Venus", "Venus"),
          "earth": ("Tierra", "Earth"), "mars": ("Marte", "Mars"),
          "jupiter": ("Júpiter", "Jupiter")}


def _orbit_xy(elements, n=360):
    # @args: elements - dict with a (or q), e, i, om, w; n - samples
    # @return: (xs, ys) in AU. Delegates to core/orbit_math (ADR-029).
    return orbit_math.orbit_xy(elements, n)


def draw_orbit(elements, jd=None, obj_name="", approach=None, out=None,
                fmt="instagram", watermark="NightScribe", size=None, lang="es"):
    # Renders the object's orbit among the inner planets.
    # @args: elements - SBDB elements dict, jd - Julian date (today),
    #        obj_name - label, approach - dict from cad.next_approach,
    #        out - output PNG path (returns figure if None),
    #        fmt - size preset, watermark - footer text,
    #        size - (w, h) px override (panel re-render mode),
    #        lang - string language ("es"|"en"); charts follow the UI language
    # @return: matplotlib figure (and writes PNG if out is given)
    import matplotlib.pyplot as plt

    jd = jd or coords.jd_from_datetime(
        datetime.datetime.now(datetime.timezone.utc))
    fig, ax = style.new_fig(fmt, size=size)
    ax.set_aspect("equal")

    # ensure a is available (compute from q when SBDB omits it for high-e)
    e = elements.get("e", 0)
    a = elements.get("a")
    if (a is None or a <= 0) and e < 1.0:
        q = elements.get("q")
        if q is not None:
            a = q / (1.0 - e)
            elements = dict(elements, a=a)

    # frame: the smallest square that contains the object's orbit AND the Sun,
    # centred on that union (not the orbit alone — the Sun sits at a focus, so
    # an eccentric orbit's centre is offset and framing it alone left a big
    # empty side). The 1 AU ring is the chart's ruler ("1 AU = Earth–Sun") and
    # always stays in frame; the larger Mars/Jupiter references are drawn only
    # when they already fit inside that square, so small/inner targets keep a
    # tight crop instead of being padded out to Mars (ADR-010, 2026-09-02).
    xs0, ys0 = _orbit_xy(elements)
    ox = list(xs0) + [0.0]
    oy = list(ys0) + [0.0]
    cx = (min(ox) + max(ox)) / 2.0
    cy = (min(oy) + max(oy)) / 2.0
    span = max((max(ox) - min(ox)) / 2.0,
               (max(oy) - min(oy)) / 2.0,
               1.0 + abs(cx), 1.0 + abs(cy)) * 1.06
    planets = ["mercury", "venus", "earth"]
    for r, pname in ((_ORBIT_SPAN["mars"], "mars"),
                     (_ORBIT_SPAN["jupiter"], "jupiter")):
        if span >= r + max(abs(cx), abs(cy)):
            planets.append(pname)
    for pname in planets:
        r = _ORBIT_SPAN[pname]
        circle = plt.Circle((0, 0), r, fill=False, color=style.MUTED,
                            alpha=0.35, lw=0.8)
        ax.add_patch(circle)
        # planet current position (heliocentric) — core/orbit_math (ADR-029)
        xe, ye, _ze, _r = orbit_math.planet_heliocentric(pname, jd)
        ax.plot(xe, ye, "o", color=palette.PLANET_COLORS[pname], ms=7,
                zorder=5)
        # proper nouns: hand-picked pair per planet (viz convention — see
        # style.pick), not a blind .capitalize()
        pair = _NAMES.get(pname, (pname.capitalize(),) * 2)
        ax.annotate(style.pick(lang, *pair), (xe, ye),
                    textcoords="offset points",
                    xytext=(6, 6), color=style.MUTED, fontsize=8)

    # the Sun at the origin
    ax.plot(0, 0, "o", color=style.SUN, ms=12, zorder=6)
    ax.annotate(style.pick(lang, "Sol", "Sun"), (0, 0),
                textcoords="offset points",
                xytext=(8, -12), color=style.SUN, fontsize=8)

    # the object's orbit and current position
    xs, ys = _orbit_xy(elements)
    ax.plot(xs, ys, color=style.ACCENT, lw=1.6, zorder=4)
    # current heliocentric position for the marker — core/orbit_math (ADR-029)
    pos = orbit_math.position_now(elements, jd)
    if pos is not None:
        x, y, z, r, nu = pos
        ax.plot(x, y, "o", color=style.ACCENT, ms=10, zorder=7)
        ax.annotate(obj_name or "?", (x, y), textcoords="offset points",
                    xytext=(8, 8), color=style.ACCENT, fontsize=10,
                    fontweight="bold")

    ax.set_xlim(cx - span, cx + span)
    ax.set_ylim(cy - span, cy + span)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(
        style.pick(lang,
                   f"{obj_name} — órbita" if obj_name else "Órbita",
                   f"{obj_name} — orbit" if obj_name else "Orbit"),
        loc="left")
    ax.text(0.02, 0.98,
            style.pick(
                lang,
                f"1 AU = Tierra–Sol  ·  vista {span * 2:.0f} AU",
                f"1 AU = Earth–Sun  ·  {span * 2:.0f} AU across"),
            transform=ax.transAxes, va="top", color=style.MUTED, fontsize=8)

    # close-approach inset: Earth-Moon system
    if approach and approach.get("dist_ld"):
        _draw_approach_inset(fig, ax, approach, lang=lang)

    style.watermark(fig, watermark)
    if out:
        style.save(fig, out)
        logger.info("orbit chart written to %s", out)
    return fig


def _draw_approach_inset(fig, ax, approach, lang="es"):
    # Small inset showing the flyby distance against the Moon's orbit.
    # @args: fig - figure, ax - main axes, approach - dict from cad,
    #        lang - string language ("es"|"en")
    import matplotlib.pyplot as plt
    inset = fig.add_axes([0.66, 0.63, 0.27, 0.27])
    inset.set_facecolor(style.BG)
    ld = approach["dist_ld"]
    span = max(1.6, ld * 1.9)
    moon_orbit = plt.Circle((0, 0), 1.0, fill=False, color=style.MUTED, lw=1.0)
    inset.add_patch(moon_orbit)
    inset.plot(0, 0, "o", color=style.ACCENT2, ms=8)
    inset.annotate(style.pick(lang, "Tierra", "Earth"), (0, 0),
                   textcoords="offset points",
                   xytext=(8, -12), color=style.ACCENT2, fontsize=7)
    inset.plot(1, 0, "o", color="#c9c9c9", ms=5)
    inset.annotate(style.pick(lang, "Luna", "Moon"), (1, 0),
                   textcoords="offset points",
                   xytext=(6, 5), color=style.MUTED, fontsize=7)
    # the flyby, stylised as a straight pass at the given distance
    inset.plot([-span, span], [ld, ld], color=style.ACCENT, lw=1.5, ls="--")
    inset.plot(0, ld, "o", color=style.ACCENT, ms=6)
    inset.annotate(f"{ld:.2f} LD", (0, ld), textcoords="offset points",
                   xytext=(-span * 30, 6), color=style.ACCENT, fontsize=7,
                   fontweight="bold")
    if ld < 0.5:
        inset.text(0.5, 0.02,
                   style.pick(lang, "¡Más cerca que la Luna!",
                              "Closer than the Moon!"),
                   transform=inset.transAxes, ha="center", va="bottom",
                   color=style.ACCENT, fontsize=7, fontweight="bold")
    inset.set_xlim(-span, span)
    inset.set_ylim(-span, span)
    inset.set_aspect("equal")
    inset.set_xticks([])
    inset.set_yticks([])
    date = (approach.get("date") or "")[:11]
    inset.set_title(
        style.pick(lang, f"Aproximación\n{date}", f"Close approach\n{date}"),
        fontsize=8, color=style.FG)
    for spine in inset.spines.values():
        spine.set_color(style.MUTED)
